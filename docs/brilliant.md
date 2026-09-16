# Brilliant: keeping the switches after the panels died

*Written 15 September 2026, from the question "my Brilliant wall controls are broken and I don't want to buy
more — how can I reverse engineer the dimmer switches, because I hate to have to throw them all away?" The
short answer is that almost no reverse engineering was needed: the switches speak standard Bluetooth SIG
mesh, and the panels only ever held the keys. **What was built** at the foot says where each part lives.*

## What was wrong, and what turned out not to be

Two Brilliant Control panels failed the same way — screen blank, unrecoverable. That is not bad luck at a
sample size of two, it is a verdict on the hardware, and the decision was made not to buy a third.

The problem is that Brilliant's own documentation, `README.md`, and this repo's inventory all agreed: the
Smart Dimmer Switches are BLE-mesh accessories that require at least one Control panel. No Control, no
switches. `brilliant-mqtt` runs *on* the panel over its Root SSH, so with both panels dead there was nothing
left to run it on, and a scan confirmed neither panel was on the network at all.

**That requirement turned out to be Brilliant's product rule, not a protocol rule.** A BLE scan found the
switches alive and advertising service `0x1828` — the Bluetooth SIG **Mesh Proxy Service**. Not a Telink-style
vendor mesh, not something proprietary: the open, published SIG mesh profile. The dead panels had not taken
the protocol with them. They had taken the *keys*.

## The three facts that made it recoverable

**A factory reset discards the old network.** A provisioned node advertises `0x1828` (proxy). Reset one — pull
the Safety Disconnect, push it back, hold the touch plate ten seconds — and it advertises `0x1827` (Mesh
Provisioning) instead, unprovisioned and claimable by anyone. The NetKey that died with the panels stops
mattering.

**The node accepts `No OOB` provisioning.** Its Provisioning Capabilities report `Public Key Type 0x00`, so
the ECDH public key is exchanged in-band; there is no secret baked into the device that only Brilliant holds.
Static OOB is *offered*, not required, and the provisioner picks the method. Confirmed by attempting it: the
node returned its own ECDH public key.

**Everything that matters is a standard model.** Composition Data Page 0:

| | |
|---|---|
| Company ID | `0x0820` (Brilliant Home Technology) |
| Features | `Relay, Proxy` |
| Element 0 | Configuration Server, Health Server, **Generic OnOff Server (0x1000)**, **Generic Level Server (0x1002)**, vendor model `0x0820/0x0001` |

On/off and dimming are stock SIG models. No reversing at all. Only the extras — PIR motion, the double-tap
scene gesture — sit behind the vendor model, and those are optional.

## What this costs, and the constraints that shape it

**Provisioning must roam.** `Algorithms 0x0001` means these are Mesh 1.0 devices, and Remote Provisioning is a
Mesh 1.1 feature. The provisioner has to be within direct BLE range of each switch as it claims it. A laptop
walks; the hub does not. *Operation* does not have this problem — once nodes are in one network they relay for
each other, so a fixed bridge reaching any one of them reaches all.

**One proxy connection per node.** While the ESP32 bridge holds a node's GATT link, nothing else can connect
to that node. With several nodes provisioned this stops mattering.

**The hub's radio is taken.** Home Assistant's `bluetooth` integration owns `hci0` on the Pi and LE-scans
continuously, which is why `btmgmt find` returns `Busy`. Running the bridge there means either giving HA up or
adding a USB Bluetooth dongle. `bluez-meshd` is installed on the hub but not enabled.

**The keys are now the fragile thing.** They live in `~/.config/brilliant-mesh/mesh-net.json`, outside this
repo and gitignored. Losing that file means factory-resetting every switch and starting again. Back it up.

## The fallback nobody needed

The FCC filing for the dimmer (`2APQV-BHS120US`) includes internal photographs. The radio daughterboard is a
**Nordic nRF52832**, and it carries a labelled debug header — `3.3V / TDIO / TCK / TXO / RXD / SWDCLK / SWDIO /
P0.21 / P0.16 / GND` — with the pogo contacts to the mains board silkscreened `DIM`, `ZC`, `GND`, `Curr Sense`,
`PIR`, `VSENSE`, `3.3V`. If the vendor model ever proves undecodable, these are reflashable devices with a
documented toolchain and a known pinout. Worth remembering; not currently needed. (nRF52832 is BLE-only — no
802.15.4 — so Thread and Matter are off the table whatever firmware runs on it.)

## What was built

- `brilliant/tools/mesh.py` — SIG mesh crypto and network layer in Python, checked against the Mesh Profile
  1.0.1 section 8.1 sample data.
- `brilliant/tools/provision.py` — claims a factory-reset switch. `compo.py` dumps its models.
  `onoff.py` / `verify.py` drive a light and read the state back. `explore.py` binds the vendor model and
  points every model's publish address at us. `listen.py` watches, with timestamps.
- `brilliant/esp32-bridge/` — mesh **proxy client** (not a mesh node) that bridges to MQTT. Finds nodes by
  matching the Network ID in their advertisement rather than by address. Builds for classic ESP32, S3, C3, C6
  and the common ESP32 dev-board variants; ESP32-S2 is excluded because it has no Bluetooth radio.
  Self-tests its crypto at boot and prints PASS/FAIL per primitive.
- `brilliant/esp32-bridge/test_cmac_native.c` — generated from the live text of `mesh_crypto.cpp`, so the
  firmware's own AES-CMAC is verified on a workstation against RFC 4493 before it is ever flashed. This caught
  nothing in the end, but it is how we knew.

## The vendor model: asked and answered

`0x0820/0x0001` does not give up the PIR or the gestures, and the reason is structural rather than a
decoding failure we could grind past.

**The switch transmits nothing on the mesh when touched.** Not a publication to the wrong address, not a
message under a key we lacked — nothing at all. A raw network-layer capture decrypts with the NetKey alone,
so it sees every PDU to any destination under any application key, control messages included. Across 150
seconds of somebody standing at the switch tapping, double-tapping, waving and sliding the groove: zero.

**Local touch bypasses the mesh entirely.** Read `Generic OnOff` state, tap the switch so the light changes,
read again: unchanged, twice. The firmware drives the triac directly and never updates the model. So the mesh
state reflects what we commanded, never what the switch is actually doing.

**It is not a configuration mistake.** Every link in the chain was verified rather than assumed:

| Check | Result |
|---|---|
| Publication mechanism | works — an unacknowledged Set changes state and the node publishes `Generic OnOff Status` to `0x0001` |
| Publish config on the node | read back: `0x1000`, `0x1002` and the vendor model all → `0x0001`, appkey 0, TTL 7 |
| Vendor model AppKey binding | `Config Vendor Model App Get` → bound appkeys `[0]` |
| All 64 vendor opcodes, no params | no reply from any; node healthy throughout, state unchanged, nothing damaged |
| Vendor model subscription | status `0x08` **Not a Subscribe Model** |

That last row is the answer. A model that publishes but cannot subscribe is an **event source**, not a command
target — it exists to *send* gestures to a Control, which is why probing opcodes at it produced nothing and
never could. Whatever the Control did to make it start emitting is not reachable through the standard
configuration models, and black-box probing has been taken as far as it sensibly goes.

**What this costs.** Control works completely: on, off and dimming over MQTT, verified end to end from the
hub's broker. What is lost is feedback — when somebody uses the switch by hand, Home Assistant will not know,
and its state drifts until the next command. Treat these as optimistic-state lights.

**The way to full function** is the nRF52832 and its labelled SWD header, described above. Own firmware would
expose the PIR as a `Sensor Server` and taps as a real `Generic OnOff Server`. That began as a curiosity in
the FCC photographs; it is now the only route to motion and gestures.
