# Brilliant switches, without Brilliant

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

Needs `bleak` and `cryptography`.

## The bridge

    python3 tools/make_secrets.py > esp32-bridge/include/secrets.h   # then add WiFi
    cd esp32-bridge
    pio run -e esp32dev -t upload
    ./watch.sh 180

`platformio.ini` carries environments for classic ESP32 (default), S3, C3, C6 and the usual dev-board
variants. ESP32-S2 is absent on purpose: no Bluetooth radio.

    publish    brilliant/<src>/event   {"src","dst","opcode","kind","params","seq"}
               brilliant/<src>/state   ON | OFF   (retained)
    subscribe  brilliant/<addr>/set    on | off | dim:0-100

## Verifying the firmware crypto without hardware

`test_cmac_native.c` is generated from the live text of `src/mesh_crypto.cpp`, so it tests the real code path:

    clang -O1 -o /tmp/t esp32-bridge/test_cmac_native.c && /tmp/t

## Gotchas

- **One GATT proxy connection per node.** While the bridge holds a node, the laptop tools cannot reach it.
- **The hub's radio is busy.** HA's `bluetooth` integration owns `hci0`; running a bridge there needs a USB
  dongle or giving that up.
- **Incoming segmented access messages are not reassembled on the ESP32** yet. They log as
  `[rx] segmented access`. `tools/explore.py` already does this and can be ported.
