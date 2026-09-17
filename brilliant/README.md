# Brilliant switches, without Brilliant

> **Resuming this work?** Read [`STATUS.md`](STATUS.md) first — current state, the captured
> panel keys, the `panel_*` tools, and the next task. Full history in [`../docs/brilliant.md`](../docs/brilliant.md).

The Brilliant Control panels are dead and no more will be bought. The Smart Dimmer Switches they used to
bridge are fine: they speak standard Bluetooth SIG mesh, and this directory owns them directly.

Background and the reasoning: [`docs/brilliant.md`](../docs/brilliant.md).

## Layout

    tools/            Python: provision, inspect and drive nodes from a laptop
    esp32-bridge/     PlatformIO: mesh proxy client -> MQTT, for the house

## The keys

Network keys live **outside this repo**, in `~/.config/brilliant-mesh/mesh-net.json`
(override with `$BRILLIANT_MESH_STORE`). They are gitignored and mode 600.

**Back that file up.** Losing it means factory-resetting every switch and re-provisioning.

## Claiming a switch

Provisioning needs the provisioner within BLE range of the switch (these are Mesh 1.0 devices, so there is no
remote provisioning). Carry the laptop.

    # 1. factory reset the switch: pull the Safety Disconnect, push it back,
    #    hold the touch plate ~10s until the LED goes out
    python3 tools/census.py             # which switches are ours, which still need a reset
    python3 tools/meshscan.py 30        # confirm it now advertises 0x1827
    python3 tools/provision.py          # claim it
    python3 tools/compo.py              # what models does it expose?
    python3 tools/onoff.py blink        # prove it drives the load
    python3 tools/explore.py 90         # bind vendor model, publish events to us

Needs `bleak` and `cryptography`; `bridge_watch.py` needs `paho-mqtt`.

## Reading the switch back

    python3 tools/state.py              # OnOff + Level, read-only, before/after a hand touch
    python3 tools/rawlog.py 180         # every PDU, decoded or not
    python3 tools/test_nonce.py         # the decrypt cases that used to fail silently

`verify.py` is **not** a way to read state: it uses an acknowledged `Generic OnOff Set`, which applies a value
and then reports the value it applied. Use `state.py`, which sends `Generic OnOff Get`.

## The bridge

`esp32-bridge/` is an ESP32 that lives on a USB wall charger near any switch, holds one mesh-proxy link into
the panel network with the captured keys, and speaks MQTT to the hub. Home Assistant learns every switch by
MQTT discovery: a dimmable light, a motion sensor and a diagnostic motion level per switch, plus the bridge
itself. Nothing Brilliant is in the loop.

    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \
      python3 tools/make_secrets.py > /tmp/s.h && mv /tmp/s.h esp32-bridge/include/secrets.h
    # first time: put WIFI_*, MQTT_HOST and the hub's MQTT_USER/MQTT_PASS into that header
    cd esp32-bridge
    pio run -e esp32dev -t upload
    ../.venv/bin/python monitor.py /dev/cu.usbserial-0001 120      # serial log (--no-reset to attach quietly)
    ../.venv/bin/python ../tools/bridge_watch.py <broker>           # what the hub sees, per switch

One puck per mesh network. A second board gets its own header (`include/secrets-s3.h`, selected by the
`esp32s3` environment's `SECRETS_FILE`), generated with `make_secrets.py --from include/secrets.h` against the
other key store. Nothing else differs between pucks: topics and ids come from the chip and the network.

`make_secrets.py` owns only the keys; everything else in `secrets.h` (WiFi, broker, `PANEL_NODE`, `SWITCH_SEED`, `SWITCH_EXCLUDE`, `POLL_MS`, `MOTION_*`) is read back from the existing header,
so regenerating after a key change never clobbers it.

    publish    mesh/bridge/<chip>/status        online | offline (retained, last will)
               mesh/bridge/<chip>/proxy         "<ble addr> rssi <n>"
               mesh/bridge/<chip>/iv            iv index in use
               mesh/<net>/<addr>/state          ON | OFF                      (retained)
               mesh/<net>/<addr>/brightness     0-255                         (retained)
               mesh/<net>/<addr>/motion         ON | OFF                      (retained)
               mesh/<net>/<addr>/motion_level   raw vendor field 0x13         (retained)
               mesh/<net>/<addr>/event          {"src","dst","opcode","kind","params"} for anything else decoded
    subscribe  mesh/<net>/<addr>/set            ON | OFF | on | off | dim:<0-100>
               mesh/<net>/<addr>/brightness/set 0-255
    discovery  homeassistant/{light,binary_sensor,sensor}/mesh_<net>_<addr>.../config

Identity needs no hand-typing. `<chip>` is six hex digits derived from the ESP32's factory MAC and names the
puck (its HA device, its topics, and its mesh unicast block `0x7000 | chip<<4`). `<net>` is the mesh network
id (16 hex) and `<addr>` the switch's unicast (4 hex): a switch is keyed by the network it is on, not by the
puck relaying it, so two pucks on one network map it to the same entity and pucks on different networks share
the one `mesh/` base. HA entity ids are `light.mesh_<net4>_<addr>`. Switches are learned from traffic and from
an all-nodes `Generic OnOff Get` at link-up, kept in flash, and announced again on every MQTT reconnect.

`platformio.ini` carries environments for classic ESP32 (default), S3, C3, C6 and the usual dev-board
variants. ESP32-S2 is absent on purpose: no Bluetooth radio. The BLE stack is NimBLE, not the core's Bluedroid
library, because the latter can block the main loop for ever when a weak link drops mid-write.

## Verifying the firmware crypto without hardware

`test_cmac_native.c` is generated from the live text of `src/mesh_crypto.cpp`, so it tests the real code path:

    python3 esp32-bridge/gen_native_test.py && clang -O1 -o /tmp/t esp32-bridge/test_cmac_native.c && /tmp/t

## Gotchas

- **One GATT proxy connection per node.** While the bridge holds a node, the laptop tools cannot reach that
  node; any other node still works, and the switches relay for each other.
- **The hub's radio is busy.** HA's `bluetooth` integration owns `hci0`, which is one reason the bridge is a
  separate puck: it works the same for a Pi, a NUC or a VM.
- **WiFi and BLE share one radio on the ESP32.** Modem sleep must stay on (the BT controller aborts at boot
  otherwise); the bridge asks the switch for a 50-100 ms connection interval and prefers WiFi in the
  coexistence scheduler so the MQTT session survives. Sequence numbers are 24-bit and every motion poll spends
  one; at the default 250 ms poll the bridge steps to the next unicast address (`BRIDGE_ADDR + n`) about every
  seven weeks on its own.
- **"Nothing arrived" is usually a decode failure, not silence.** The listeners decode at the application
  layer and used to print nothing when that failed, which hid every message published to a group address and
  every segmented message with a 64-bit MIC. Reach for `rawlog.py` before concluding a node is mute: it prints
  each PDU's network header first and names the reason the application layer could not open it — including
  whether the message is under an AppKey we do not hold.
