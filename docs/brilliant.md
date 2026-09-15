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

## What is still open

The vendor model `0x0820/0x0001` is bound to our AppKey and its publish address points at us, both confirmed
by the node. **Nothing has yet been observed coming out of it.** Every listening window so far has run with
nobody at the switch, so silence is not evidence. Whether PIR motion and the scene gestures are exposed is the
one question this work has not answered.
