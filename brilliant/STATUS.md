# Brilliant switches — state of play (start here)

*Last updated 16 September 2026 (night: config over the cable, firmware 0.2.0). This is the resume-from-here summary; the full chronological story and the
"why" behind every step is in [`../docs/brilliant.md`](../docs/brilliant.md).*

## Where we got to (all proven on a real wall switch, no Brilliant app, no reset)

The Brilliant Control panels are dead-screened but one panel's radio still works. We captured that panel's
mesh keys and can now **read and control the real wall switches directly over BLE mesh**:

| Capability | How | Status |
|---|---|---|
| Read on/off | `Generic OnOff Status` | ✅ |
| Read dim level | `Generic Level Status` | ✅ |
| Read motion (PIR) | vendor field **`0x13`**: a walk-past adds ~5 counts on top of a baseline that tracks the load (~2 lamp off, ~130 lamp full); the bridge learns the baseline per switch | ✅ |
| Write on/off | `Generic OnOff Set` | ✅ light obeyed |
| Write dimming | `Generic Level Set` on a **0–1000 scale** (not SIG −32768…32767) | ✅ full→2%→full, confirmed |
| Restore a reset switch to a dimmer | provision + bind (incl. vendor `0x0820/0x0001`) + write config + power-cycle | ✅ visually confirmed on `0x0005` |

## The keys (the whole game)

`~/.config/brilliant-mesh/panel-net.json` (mode 600, outside the repo, `.bak` alongside). Contains:

- **netkey** `bb1ce23dad4ff4222a0198216b92578f` — network id `k3` = `3deef9825e444955` (every wall switch's netid)
- **appkey** `4275e046e4828515c87237f50299114f` — AID `0x37`
- **iv_index 7** — decryption fails silently with the wrong IV
- our provisioned unicast (`0x1a`+)

**Back this file up. Never commit it.** With it, the dead panel is irrelevant — we hold everything needed to
read and drive the mesh.

## How to run anything

Tools live in `tools/`, run with the repo venv, pointed at the panel store:

```sh
cd brilliant/tools
export BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json
V=../.venv/bin/python          # bleak + cryptography are installed here

$V census.py 12                # list live panel nodes (netid 3deef…) + signal
$V panel_sniff.py 150          # decode live on/off + dim + vendor from all switches
$V panel_poll.py 000a 150      # poll a switch's vendor fields; POLL_FIELDS=13 for motion only
$V panel_cmd.py 000a on        # control: on | off | dim:<0-100>
$V panel_cmd.py 000a dim:20
```

`PANEL_NODE=<ble-addr>` pins the proxy node (avoids weak-node roulette); otherwise the strongest is chosen.

## Gotchas already solved (don't re-discover these)

- **Proxy nonce**: octet 1 must be `0x00`, not `CTL|TTL` (fixed in `tools/mesh.py`). This is why the proxy
  forwarded nothing before — the fix is what made live reads work.
- **Dim scale is 0–1000**, not the SIG mapping. A standard-mapped level is silently ignored (the switch even
  echoes it back, looking like success). Captured by sniffing the app dim a switch.
- **Generic Level Set is command-inert for the triac on our own claimed switch** but works on panel-configured
  switches — the panel set them to dimmer mode. Don't reset a wall switch; it strips that config and we can't
  yet fully rebuild it.
- **One proxy connection per node**; the link is flaky below ~−80 dBm — reply drops are range, not logic.
- **ESP32 firmware gotchas** (all fixed in `esp32-bridge/`): WiFi modem sleep must stay on or the BT controller
  aborts at boot; the core's Bluedroid BLE library hangs the main loop when a weak link drops mid-write (NimBLE now);
  MTU negotiation fails on some links, so writes honour the real MTU and SAR-segment; a broadcast Get loses replies
  when 11 switches answer at once, so state is resynced per switch.
- **Re-capturing keys** (only if the store is ever lost): the recorder firmware in `mesh-provisionee/` does it
  — flash it, scan a spare switch's QR in the app (QR = 16-byte UUID + 16-byte Static OOB), and it captures
  netkey + appkey. See `docs/brilliant.md` for the full recipe. The keys are already saved, so this is a
  fallback, not a needed step.

## The always-on bridge: built and proven (16 September, evening)

`esp32-bridge/` is now the **panel bridge**: an ESP32 puck on a USB charger that holds one proxy link into the
panel mesh with the captured keys and turns every switch into Home Assistant entities over MQTT discovery. Proven
against the Mac dev stack end to end: 11 switches discovered by one all-nodes Get, on/off and brightness read
live as people touch them, `brightness/set 128` visibly dimmed the hallway to half and its Status came back, and
the MQTT session held for the whole soak.

| Per switch, in HA | From |
|---|---|
| `light.brilliant_switch_<addr>` with brightness | `Generic OnOff/Level Status`, published by the switch on touch and polled every 10 min |
| `binary_sensor..._motion` (device class motion) | vendor field `0x13` polled round-robin every 250 ms, ON while it sits 4 above the switch's learned floor, 20 s hold; plus any switch's own publication of field `0x0c = 1` |
| `sensor..._motion_level` (diagnostic) | the raw `0x13` value |
| `sensor.brilliant_bridge_proxy_node` | which switch the puck is linked to, and its RSSI |

```sh
cd brilliant/esp32-bridge
BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \
  ../.venv/bin/python ../tools/make_secrets.py > /tmp/s.h && mv /tmp/s.h include/secrets.h   # keys; WiFi/MQTT carried over
pio run -e esp32dev -t upload --upload-port /dev/cu.usbserial-0001
../.venv/bin/python monitor.py /dev/cu.usbserial-0001 120        # serial log; --no-reset to attach quietly
../.venv/bin/python ../tools/bridge_watch.py 192.168.86.42        # what the broker sees, per switch
```

Topics: `mesh/<net>/<addr>/{state,brightness,motion,motion_level,event}`, commands on `mesh/<net>/<addr>/set`
(`ON|OFF|dim:<pct>`) and `.../brightness/set` (0-255); `mesh/bridge/<chip>/{status,proxy,iv}`. `<net>` is the
network id (16 hex), `<chip>` six hex from the puck's factory MAC; entity ids are `light.mesh_<net4>_<addr>`.
Full contract at the top of `esp32-bridge/src/main.cpp`; the story of building it is in `docs/brilliant.md`.

**What is still open**

- ~~Point it at the hub.~~ Done: `secrets.h` names the hub (`192.168.86.42`) with the password from the hub's
  `/opt/home-hub/driver-layer/.env` (read over `ssh pi@hub.local`; the Mac's `.env` is a different broker). The hub's
  HA registry holds all 34 entities; they surface under *New devices* on the panel.
- ~~Dimmer mode on a reset switch.~~ **Solved and visually confirmed (16 Sep, night)** on the hallway dimmer,
  re-provisioned as `0x0005` on our network: provision, bind (`0x1000`, `0x1002`, and the vendor model
  `0x0820/0x0001` — the vendor bind is essential or config writes are dropped), write the switch's own captured
  config (`tools/vendor_store.py` reads it), power-cycle. It then dimmed on command with the lamp following, 30→100→10→60→100%.
  The exact ordered sequence, written as a spec a firmware provisioner can replay (and which fields do what), is
  **Spec: adopting a switch** in [`../docs/brilliant.md`](../docs/brilliant.md); `tools/restore_switch.py` is the
  reference implementation (`adopt <captured.json>`, then power-cycle, then `verify <addr>`).
- ~~Confirm motion with a body.~~ Done: a walk past `0x000b` raised `0x13` from ~5 to 8 and the bridge reported motion.
- **Bisect the recipe** (optional): which of the seven fields is the selector; `0x48`/`0x4f` are the reporting enable,
  `0x03`/`0x07` its thresholds, so `0x1a`/`0x1b`/`0x56` are the mode candidates. Nobody walked past a switch during the build. Field `0x13` rests at different
  levels per switch (0x000a ~130, 0x0010 ~285, most 0-2, 0x000b 4-11), which is why the floor is learned rather than
  fixed. Switch `0x0016` publishes vendor field `0x0c = 1` on its own every ~20 s; that is treated as motion too but is
  a guess. Run `bridge_watch.py`, walk past a switch, and see which of the two moves.
- **Puck UX** (Wi-Fi/broker/keys onto the puck without a laptop) is its own session; see memory
  `project-brilliant-puck-ux`.
- **Retire the console.** Nothing depends on it now: a reset switch can be re-provisioned and restored to a dimmer
  with motion by the recipe above. Unplug it when ready; adopt the other switches on the captured keys, or re-key
  them one at a time (the S3 puck bridges the new network while the classic puck bridges the old).

## The puck takes its config over the cable (16 September, night: firmware 0.2.0)

Until now everything a puck needed was compiled in from `include/secrets.h`, which is fine at a desk and useless
in a bag: the hub had nothing it could write to. Now **the config lives in NVS and the header is only a
fallback** -- both desk pucks keep working exactly as their headers say, and a board flashed from the shipped
image with no header at all boots *blank* and waits on the cable to be told. This is half one of
`design/puck/` (board B, the cable), on the firmware side, and it is proven on the S3:

```sh
cd brilliant/esp32-bridge
pio run -e esp32s3-ship -t upload --upload-port /dev/cu.usbmodem101   # the image the hub ships: no secrets, boots blank
cd .. && V=.venv/bin/python
$V tools/puck_cable.py /dev/cu.usbmodem101 hello                        # {'chip': 'c8ebba', 'fw': '0.2.0', 'state': 'blank'}
$V tools/puck_cable.py /dev/cu.usbmodem101 write --from esp32-bridge/include/secrets-s3.h   # wifi, mqtt, keys, base, label; apply; waits for it back
$V tools/puck_cable.py /dev/cu.usbmodem101 status                       # {'wifi': '192.168.86.66', 'mqtt': 'up', 'rssi': '-75', 'sw': '2', 'light': 'heard'}
```

Verified: a blank S3 handed its own config back over the wire came up as a full bridge -- Wi-Fi at 3 s, MQTT up by
10 s, proxy link by 35 s -- and the hub's broker sees it (`bridge/c8eb status online`) next to the classic board.
**The S3 on the desk now runs the ship image with its config in NVS**, not `secrets-s3.h`; the classic board still
runs a desk build (0.2.0 is a drop-in for it: same header, same behaviour).

What is in it: `src/config.{h,cpp}` (the NVS store and the line protocol -- `hello`, `set wifi|mqtt|keys|base|label`,
`status`, `apply`, `wipe`; free text goes hex-encoded so nothing needs quoting), `src/light.{h,cpp}` (the puck's
one light: amber blinking = looking, steady green = a switch answered, breathing red = three empty scans, on the
S3's WS2812 or as rhythms on a plain LED), the `[env:esp32s3-ship]` build, and `tools/puck_cable.py`, which is
the hub's side of the protocol and what the hub will run when a puck appears on its USB.

**Gotchas found on the way, all handled, all worth knowing:**

- **Opening the S3's USB port reboots it** (`rst:0x15 USB_UART_CHIP_RESET`), DTR held low or not: the peripheral
  does it on its own. So the first `hello` lands in the bootloader and is lost; the tool keeps asking for 12 s.
  Consequence: `status` right after open is a fresh boot, not a settled bridge -- hold one connection open to watch it settle.
- **The hardware CDC tears long writes.** The core's `HWCDC::write` drains only while its own guess that a host is
  listening is true, and when that guess is wrong (it is, on a Mac after reopening the port) a longer line comes
  out as head + tail with the middle dropped: `bridge c8ebbat`, `status wifi=192.168.8oking`. Replies now go out
  in ≤60-byte pieces with a flush between, `status` was shortened to fit, and the tool retries any exchange that
  does not come back whole. Ten reboots, 24 exchanges, zero torn lines after that.
- **A serial task on 4 KB corrupts silently.** `status` formatting an `IPAddress::toString()` on a 4 K stack did not
  panic, it produced `wifi=192.looking`. 8 K now, and no `String` temporaries on that task.
- **The S3 clone's LED only has power when the UART-side USB port is plugged in.** The desk S3 is an AYWHP
  N16R8 (the YD-ESP32-S3 design, CH343 bridge, WS2812 on GPIO48 as its manual says, "RGB" pad bridged). Powered
  through the *native* port alone the chip runs and the LED is dead: that port feeds the 3.3 V regulator but not
  the 5 V rail the LED hangs off, unless the board's IN-OUT pads are bridged. Three LED drivers, a solder-pad
  theory and a 25-pin sweep were spent before a second cable in the UART port lit it. Consequences: the serial
  task now listens on BOTH ports (`Serial` = native CDC, `Serial0` = UART) and answers whichever asked, and the
  LED driver runs an RMT channel on GPIO48 and GPIO38 so the image never has to know the board revision. For a
  puck we ship: the hub's cable goes in the **UART** port -- it powers the LED, and its bridge chip has the
  auto-reset esptool wants. The hub tool works on either (`/dev/cu.wchusbserial*` here; `/dev/cu.usbmodem*` is
  the native side).
- **Both desk pucks run 0.2.0** (16 Sep, night): the S3 as the ship image with its config in NVS, the classic
  (`f4a9f3`, 11 switches, the panel network) as the `esp32dev` desk build with `secrets.h` compiled in as its
  fallback -- `hello` says `set` on both, and both reach `light=heard`.
- The mesh keys sit in NVS in the clear, exactly as they sat in flash compiled in; nothing got worse, and flash
  encryption is the answer if it ever has to get better.

Not yet: the hub side (a udev rule like `driver-layer/radios.sh`, esptool + this image shipped in the release, the
brain's `/bridge` state machine the panel already draws), and board A (the puck knocking over BLE). The light's
colours have not been looked at with an eye yet -- `light=heard` above is the state, not the LED.

## The hub does the cable job itself (17 September, small hours: brain/hub/bridge.py)

The brain now owns the whole of design/puck/Cable.dc.html. `Bridges` watches the hub's USB every three
seconds; a serial device that appears and answers `hello` (or, if it is silent, that esptool says is an
ESP32) becomes the job the panel draws -- `knocking` until someone at the wall says it is theirs, which is
behind the code, then `working` through software (a bare board is flashed with `releases/bridge/esp32s3-ship.bin`),
Wi-Fi and keys, then `placing`, with what the puck hears coming back over the broker (`mesh/bridge/<chip>/
{status,net,proxy}` and the switches under its net) until "leave it here" makes it `ready` with the unplaced
count. Routes: `GET /bridge`, `POST /bridge/{adopt,dismiss,placed}`; `POST /bridge/switches` answers 501 in
words until the puck can provision. 23 tests with a fake cable; the real one drove the desk S3 through knock,
adopt and the write in 8.5 s.

- **The house's mesh keys** are made once by the brain (`/data/mesh-keys.json`, 0600) -- a fresh house gets fresh
  keys. A house with a Brilliant panel imports the captured ones: `python -m hub.bridge import
  ~/.config/brilliant-mesh/panel-net.json` on the hub, once.
- **The Wi-Fi is the one thing the hub may not have.** This hub is on Ethernet; its wlan0 connection's password
  is in host config the container cannot read. The brain takes `settings.wifi` (not yet settable from the panel)
  or `PUCK_WIFI_SSID/PUCK_WIFI_PASS` in `.env`, and otherwise ends the job `failed` with `needs: wifi` and a
  sentence, rather than pretending. The "tell it once under This hub" page is the next panel piece.
- **The container needs /dev.** docker-compose now binds `/dev:/dev` for the brain with cgroup rules for ttyUSB
  (188) and ttyACM (166), so a port that appears after start can be opened. `pyserial` and `esptool>=5` are in
  the brain's requirements; `tools/build-bridge.sh` merges the ship image (bootloader, partitions, boot_app0,
  app) into the one file the brain flashes at 0x0, with a manifest beside it. It has not been deployed to the hub
  yet -- that is a push and a `docker compose up -d`.

## Two pucks, two networks (16 September, late)

The same firmware now runs on an **ESP32-S3** (`/dev/cu.usbmodem2101`, `pio run -e esp32s3`) with its own header
`include/secrets-s3.h`, pointed at **our own network** (`mesh-net.json`, node `0x0003` = the factory-reset switch)
and publishing under the same `mesh/` base. Identity comes from the chip (puck) and the network id (switches), so
both pucks live on the hub side by side with nothing hand-named (both boards carry this firmware). Verified: `mesh/0003` state/brightness on
the hub broker, HA entities created, `ON` acknowledged by the switch. Its motion field `0x13` reads a flat 32:
that switch has no PIR reporting since the reset, which is exactly the configuration gap to close next.

```sh
../.venv/bin/python ../tools/make_secrets.py --from include/secrets.h > /tmp/s3.h && mv /tmp/s3.h include/secrets-s3.h
# then edit MQTT_BASE / SWITCH_SEED / SWITCH_EXCLUDE / DEVICE_LABEL in it
pio run -e esp32s3 -t upload --upload-port /dev/cu.usbmodem2101
```

Next on this track: diff the vendor store of the hallway dimmer (`0x000a`, panel appkey) against `0x0003` (ours) to
find the load-type / motion-enable fields, replay them onto `0x0003`, and confirm dimming + `0x13` moving. Then the
console can be unplugged for good, and switches can be adopted or re-keyed one at a time.

## Two switches on one light: the pair carries itself, the hub only watches (17 September: brain/hub/relay.py)

A Brilliant companion switch has no load. It is a radio node that drives nothing itself, and it makes
its partner act by sending that partner a press directly — a vendor message to the unicast stored in
its own field `0x08`. **The console is not in that path and never was**, which we established the hard
way and which retired the "do not unplug the console" rule this section was originally written under.
A pair looks after itself and keeps working with the hub switched off, which is the only acceptable
behaviour for a light switch.

So the relay below is **transitional**, not the mechanism. It earns its place in exactly one case: a
pair whose two ends are on *different* networks during a migration, where no direct message can cross
because the netkeys differ. The stairway was that case for one afternoon. It is not any more — both
ends were migrated the same evening and the link was switched off.

A link is nothing but a rule about topics, which is what makes the stairway possible at all: the
companion is on the house's own network behind one puck, its load is still on the panel's network
behind the other, and the broker is the only place the two meet.

```
mesh/<from-net>/<from-addr>/state       ->  mesh/<to-net>/<to-addr>/set
mesh/<from-net>/<from-addr>/brightness  ->  mesh/<to-net>/<to-addr>/brightness/set
```

Links live in `/data/switch-links.json` behind `GET`/`POST`/`DELETE /bridge/links`, written by hand
today; pairing in the product (the phone scanning both codes at setup, the one extra press on the wall)
will write the same rows. It is fed from `hub/bridge.py`'s single `mesh/#` subscription, so there is one
listener on the broker, not two. 18 tests in `brain/tests/test_relay.py`.

**Four things a naive relay gets wrong, each one held by a test:**

- **A retained message is not a press.** Every puck republishes all of its state, retained, on every
  reconnect to the broker. Retained only ever sets the baseline here; it never acts. Without this the
  house replays every press each time the broker blinks.
- **A message is not a press either — a change is.** The puck resyncs every switch at link-up and again
  every ten minutes, so the same value arrives over and over. This also means a press made while the hub
  was away is still carried when it is next heard, which is correct.
- **What we send comes back.** The puck publishes the state of everything it hears, our own commands
  included; two links facing each other would volley for ever. Anything we just sent is ignored on the
  way back for three seconds.
- **A command can be dropped.** The acknowledgement is the load's own Status, so a send is confirmed by
  the state arriving as asked within two seconds, tried three times, and then said plainly in the log
  rather than counted as a success.

**Proven on hardware, on both networks (17 September):** `mesh/7dcdd6f322c30af4/0004/set OFF` moved the
loadless companion ON -> OFF with nothing visible in the house, and panel-net `0x0011` went OFF -> ON ->
OFF on command, each confirmed by its own Status inside a second, with nothing else on either network
moving. The bench that does this runs the real `Relay` class from a Mac against the live hub broker over
ssh, so a press can be proven with nothing deployed.

**And then the relay was switched off, which is the right ending.** Both of the things left open above
were settled the same evening — a human at the lamp confirmed `0x0011` was the stairway load, and the
puck was moved to −75 dBm — and the relay then carried a simulated press across both networks in under a
second. But the user named the actual requirement: *a two-way pair must keep working with the hub off.*
A relay cannot satisfy that, by construction. So the stairway load was migrated onto the house's own
network (it is `0x0006` there now) and paired to its companion directly, and the hub's link was disabled
rather than left firing at a switch that drives itself.

```
19:55:30  0x0004 -> 0x0006  vendor 0403          the companion presses
19:55:30  0x0006 state ON                         the load turns on
19:55:30  0x0006 -> 0xffff  sig 0x008204 "01"     the main announces to everyone
```

That is the shape to build on: **the pair talks to itself and the hub watches from the side.** The main
broadcasts its state to all-nodes, so the hub learns the outcome without standing in the path — which is
both more robust than overhearing a press and true whichever end was touched. `relay.py` keeps a real but
narrow job: a pair split across two networks during migration, and pairs we cannot write. A same-network
pair must never depend on it. The disabled link is kept in `/data/switch-links.json` as the record.

**The hub's view of a mesh is one node wide, and that is a structural limit worth knowing.** The puck
decodes only what its GATT proxy forwards: `handleNetworkPdu` has one caller, fed by a queue filled only
from the proxy notify path, and the scan reads service data to *choose* a proxy and queues nothing. So a
puck two feet from a switch hears none of it unless its proxy node does — observed exactly that way in
the house. The fix is an advertising-bearer listener (mesh PDUs are AD type `0x2A`; the decoder already
exists), with a low duty cycle, because that radio is shared with Wi-Fi and an aggressive scan is what
starved MQTT above. `PANEL_NODE` pinning is a compile-time `#define`, not NVS config, so it needs a
reflash — and nothing maps BLE addresses to unicasts, which makes pinning an expensive way to test this.

**A puck can go silently mute, and this is the signature:** `mqtt=down` with `rssi=0` and
`light=looking`, Wi-Fi up with an IP, and *no connection attempt at all* in the broker's log. A puck
that cannot find a proxy spends six seconds of every eight in a blocking active BLE scan and the TCP
SYN never gets air. It only bites a puck out of range of its own mesh — exactly when you need it on the
broker to say so — and it self-heals the instant a proxy is found, which makes it look like a reboot
"fixed" it. Fixed by giving Wi-Fi the radio to itself before each scan while the broker is down;
recovery is then about one connect attempt every twelve seconds. Both pucks carry the fix. NVS config
survives a reflash of the ship image, so a desk reflash does not strand a configured puck.

*Scope, so this does not harden into a fact it has not earned:* the signature above was observed, and
the starvation mechanism explains every symptom — but the stuck puck was recovered before it could be
caught in the act, and its serial log was on the cable that was not plugged in, so the mechanism is
**inferred, not reproduced**. What supports it beyond the reasoning is one live observation after the
fix: a puck reporting `status online` together with `proxy none`, a combination the old firmware could
not produce, because starvation made "no proxy" and "on the broker" mutually exclusive. Treat it as
plausible and well supported. If a puck is ever caught in that state again, the current build says which
branch it is parked in.

## Known switch addresses (from the bridge's sweep)

Answered `Generic OnOff Get` to all-nodes: `0x0004 0x0005 0x0006 0x0008 0x000a 0x000b 0x000e 0x0010 0x0011 0x0014
0x0016` (11). `0x0011` is the **stairway load** — confirmed 17 September by blinking it while a person watched the lamp, which **disproves the earlier guess** that `0x0010`/`0x0011` were the live panel's own loads. `0x0010` is untested and that guess should be treated as unsupported too. `0x0002` and `0x0012` are panel elements
that poll switches and are excluded; `0x0018` is polled by the panel and never answers.

## Uncommitted work (all on disk, nothing staged by this pass)

New tools: `ble.py dim.py state.py rawlog.py vendor.py snapshot.py poll.py writable.py setfields.py
pubtest.py test_nonce.py panel_sniff.py panel_poll.py panel_cmd.py bridge_watch.py`.
Modified: `mesh.py` (proxy-nonce fix), `census.py`, `explore.py`, `listen.py`, `onoff.py`, `provision.py`,
`make_secrets.py` (panel store, carries tunables).
Recorder firmware: `mesh-provisionee/src/{main.cpp,recorder.cpp,recorder.h}`.
Bridge: `esp32-bridge/src/main.cpp` (rewritten: panel keys, NimBLE, discovery, motion, HA discovery),
`esp32-bridge/src/mesh_crypto.{h,cpp}` (proxy nonce, ASZMIC, beacon auth), `platformio.ini` (NimBLE),
`monitor.py`, `gen_native_test.py` + regenerated `test_cmac_native.c`.
Docs: `docs/brilliant.md`, `README.md`, this file. Commit when ready (secrets stay out — the keys are in
`~/.config`, and `esp32-bridge/include/secrets.h` is gitignored).


## Where the multi-way work got to (17 September, night)

Everything below was proven against real lamps in this house, not inferred from captures.

**The house has three multi-way lights, not one.** `tools/pairs.py` reads vendor field `0x08` from every
switch over one proxy link, writes nothing and presses nothing, and found `0x0006 -> 0x0005` (the basement
kitchen two-way), `0x0016 -> 0x0002` and `0x0014 -> 0x0012`. The last two name **panel elements** -- the
console's own sliders, which are switch positions in a three-way and not brokers. `0x0002` answered none of
its 55 vendor fields, which is what a panel element looks like and what a switch never does.

**The migration premise is proven end to end.** `pairs.py` said `0x0006`'s partner was `0x0005` before
anything was touched; a controlled four-press run on that pair then produced both documented signatures
(companion sends `0403` and the lamp follows; the lamp end broadcasts with no `0403` at all) and confirmed
it. Four presses, four lamp movements, none dropped -- so the dropped-press worry belongs to the kitchen's
flaky install, not to the protocol.

**Field `0x13` is a load detector and it is not subtle.** Measured on `0x0005` with the lamp switched by
hand: dark 1-3, lit 92-97, settling within ~2 s in both directions. So a provisioner can find which of two
new switches has the lamp by trying each and watching, and never has to ask anybody. Key it on the **jump**,
never on an absolute threshold -- resting values differ per switch across this house.

**`0x1b` is the ANNOUNCE flag, not a role.** Our stairway load `0x0006` was written to `0x1b = 03`, power
cycled and pressed: the lamp came on. So `03` does not stop a switch driving its own load; it adds the
`0403` to the partner in `0x08`. The old "00 drives a load, 03 is a companion" reading is retired, and the
adopt spec's field table is corrected. Our stairway pair is `0x0004 -> 0x0006`; earlier notes saying
`0x0003` are out of date.

### New tools

| | |
|---|---|
| `tools/pairs.py` | reads a whole network's pairings (`0x08`/`0x1b`) over one proxy link. Read-only. Two passes, and reports a silent switch as **unknown, never as unpaired** |
| `tools/vendor_write.py` | writes one vendor field **through a proxy** rather than a direct connection, and reads it back. `setfields.py` needs the laptop beside that exact switch with nothing holding its link, which is true less often than you want |
| `tools/migrate.py` | moves a whole **light**: `plan` (read the pairing while it still exists) → `adopt` per switch → `finish` (rewrite each companion's `0x08` to the main's NEW address) |

**`migrate.py plan` is tested against the real pair** and correctly identified the lamp end; its guard for a
switch whose partner is the console was tested too and refuses to proceed. **`adopt` and `finish` have not
been run end to end** -- the pieces they call are proven, the joins between them are not. First real use
wants a pair nobody minds fiddling with.

**Why the ordering is the whole tool:** `0x08` is readable only while the switch is still on the console. A
factory reset wipes it, and then the only record of which light a companion belonged to is gone with the
hardware.

### Hazards worth not re-learning

- **A read reply is `<value> 00`.** The trailing byte is not part of the value; echoing a raw reply back
  into a write sends one byte too many and the switch drops it **silently**. Two restore attempts on a live
  light read back unchanged before this was spotted.
- **A dropped read is indistinguishable from an absent field**, and here it turns a companion into a light.
  It happened three separate times tonight on `0x0014` and `0x0004`; two passes caught every one.
- **`0x7f30` is our own ESP32 bridge**, not the panel (`0x7000 | chip<<4`). It accounts for most of the
  traffic in any panel-network sniff.
- **Only one thing can hold a proxy link to a node.** Two captures running means one of them is listening to
  nothing. Confirm a live reading before asking somebody to go and press a switch.

### Next

1. **The puck provisioner** -- the one genuinely new build, and what turns all of this into *Add a wall
   switch* for somebody who is not us.
2. **Does the Brilliant app still add a device with no internet?** Decides whether the keep-your-panel path
   has a future or an expiry date set by somebody else.
3. **Do the panel's two gangs serve one light or two?** Decides whether taking the panel down means one
   orphan fix or two.
4. A three-switch star, and what `0x1b` reads on a factory-fresh switch.
