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
  `onoff.py` drives a light; `state.py` reads OnOff and Level back **without writing them** (`verify.py` uses
  an acknowledged Set and so only echoes what it commanded — do not use it to read). `explore.py` binds the
  vendor model and points every model's publish address at us. `listen.py` watches, with timestamps.
  `rawlog.py` logs every PDU at the network layer, decoded or not, and is the tool to reach for whenever the
  answer looks like "nothing arrived".
- `brilliant/esp32-bridge/` — mesh **proxy client** (not a mesh node) that bridges to MQTT. Finds nodes by
  matching the Network ID in their advertisement rather than by address. Builds for classic ESP32, S3, C3, C6
  and the common ESP32 dev-board variants; ESP32-S2 is excluded because it has no Bluetooth radio.
  Self-tests its crypto at boot and prints PASS/FAIL per primitive.
- `brilliant/esp32-bridge/test_cmac_native.c` — generated from the live text of `mesh_crypto.cpp`, so the
  firmware's own AES-CMAC is verified on a workstation against RFC 4493 before it is ever flashed. This caught
  nothing in the end, but it is how we knew.

## The vendor model: reopened

*This section read "asked and answered" until 15 September 2026, when the instruments behind it were
re-examined. Two of its three load-bearing negatives were produced by tools that could not have shown a
positive result. The conclusions below are downgraded to open questions; see **What the instruments could
not see** at the end of the section.*

`0x0820/0x0001` has not yet given up the PIR or the gestures.

**~~The switch transmits nothing on the mesh when touched.~~** This was asserted on the strength of a "raw
network-layer capture", but no such tool exists in the repo or in any surviving scratchpad. What was actually
run was `explore.py` / `listen.py`, which decode at the *application* layer and print nothing at all when that
fails. Their shared `try_decrypt` built the application nonce with **our own address hardcoded as the
destination** and **ASZMIC forced to zero**, so a publication to a group address, or any segmented message
carrying a 64-bit MIC, was discarded in silence — indistinguishable, on screen, from the switch being mute.
Both defects are now fixed and covered by a round-trip test; `tools/rawlog.py` does the network-layer capture
this paragraph claimed. **The 150-second experiment needs re-running before the claim can stand.**

**~~Local touch bypasses the mesh entirely.~~** The "read" here was `verify.py`, which uses an *acknowledged
Generic OnOff Set* — a write that reports the value it has just applied. It can only ever echo what we
commanded, so it cannot detect a state the switch set for itself; the experiment assumed its own conclusion.
No `Generic OnOff Get` (`0x8201`) existed anywhere in the tooling. `tools/state.py` now sends the real
read-only Get, before and after a hand operation. **Also needs re-running.**

**It is not a configuration mistake.** Every link in the chain was verified rather than assumed:

| Check | Result |
|---|---|
| Publication mechanism | works — an unacknowledged Set changes state and the node publishes `Generic OnOff Status` to `0x0001` |
| Publish config on the node | read back: `0x1000`, `0x1002` and the vendor model all → `0x0001`, appkey 0, TTL 7 |
| Vendor model AppKey binding | `Config Vendor Model App Get` → bound appkeys `[0]` |
| All 64 vendor opcodes, no params | no reply from any; node healthy throughout, state unchanged, nothing damaged |
| Vendor model subscription | status `0x08` **Not a Subscribe Model** |

Status `0x08` means only that the model keeps no subscription list, which is normal for a client-shaped model.
Reading it as proof that the model can never be *addressed* goes further than the spec allows: a vendor server
declared without subscription support still accepts unicast messages, and we hold the AppKey to send them.
The 64-opcode sweep that found nothing sent **no parameters**, and a handler that length-checks its payload
drops a zero-length message before dispatch every time — so that sweep is close to vacuous as evidence.

### What the instruments could not see

The three questions the old tooling could not answer, and what now answers them:

| Question | Why it went unanswered | Now |
|---|---|---|
| Does the switch emit anything at all when touched? | app-layer-only listeners, silent on decode failure | `tools/rawlog.py` — logs every PDU by its network header, and names the reason a decrypt failed |
| Does it publish somewhere other than at us? | nonce hardcoded our address as the destination | fixed; `rawlog.py` prints the true `dst` and its address class |
| Does it publish under a key the panel holds and we don't? | never checked | `rawlog.py` compares each message's AID against ours and says so |
| Does the model track the physical switch? | only ever "read" with an acknowledged Set | `tools/state.py` — read-only `Generic OnOff Get` / `Generic Level Get` |

A foreign AID would be the most interesting outcome of the four: it would mean the switch reports exactly as
Brilliant's panel expects, and that what we lack is an application key, not a firmware feature — which the
provisionee work below is already the route to.

**What this costs.** Control works completely: on, off and dimming over MQTT, verified end to end from the
hub's broker. What is lost is feedback — when somebody uses the switch by hand, Home Assistant will not know,
and its state drifts until the next command. Treat these as optimistic-state lights.

**The way to full function** is the nRF52832 and its labelled SWD header, described above. Own firmware would
expose the PIR as a `Sensor Server` and taps as a real `Generic OnOff Server`. That began as a curiosity in
the FCC photographs; it is now the only route to motion and gestures.

## The over-the-air route: DFU over mesh

The switches broadcast, continuously, a service-data advertisement under Nordic's UUID `0xFEE4`:

    feffaf00 01 02 20080000 0100 8671100c <netid4>
    handle 0xFFFE = proprietary-mesh DFU FWID beacon
    company_id 0x0820 (Brilliant), app_id 0x0001, app_version 0x0c107186

That is **DFU over the mesh** — Nordic's proprietary firmware-update transport, riding the advertising bearer,
separate from the BT SIG mesh we use for control. It is almost certainly how the Control panels updated the
switches, and it means firmware can in principle be replaced **over the air, with the switch in the wall** —
no SWD, no pulling it out. Our own claimed node broadcasts the same beacon (its trailing bytes track our
network id), so it can be the guinea pig without disturbing the captive switches.

**The open question is signing.** The proprietary DFU supports ECDSA P-256 signatures
(`NRF_MESH_DFU_PUBLIC_KEY_LEN 64`, `NRF_MESH_DFU_SIGNATURE_LEN 64`), verified by the bootloader against a
public key in its *device page*. Signing is optional and per-device: required only if Brilliant flashed a
public key. If they did, we cannot push our own firmware (no private key) and the SWD reflash is the only
route. If they did not, we own these switches completely, over the air. This cannot be read remotely — it is
determined by attempting a transfer.

**Why attempting it is low-risk.** DFU uses *banking*: an incoming transfer is stored in a spare flash bank
and only copied over the running application once it validates. A rejected (e.g. unsigned) transfer is
discarded and the running firmware is untouched. A device applies a transfer only when the application ID
matches and the version is higher, so the probe is naturally scoped to the one node we aim at.

**What it takes.** Two builds: (1) a replacement nRF52832 mesh application exposing a `Sensor Server` (PIR)
and a real `Generic OnOff Server` (taps), built on the nRF5 SDK for Mesh; and (2) a DFU *source* that can
broadcast raw `0xFEE4` advertising packets. macOS cannot be the source — CoreBluetooth will not broadcast
arbitrary service data — so the source is the ESP32 (raw advertising) or the Pi's BlueZ, or a Nordic dongle
driven by `nrfutil`. This is the active line of work; the SWD reflash remains the fallback if the DFU turns
out to be signed.

### The ESP32 DFU probe, and why unsolicited OTA does not work

`brilliant/dfu-probe/` is an ESP32 that broadcasts a proprietary-mesh DFU **State (Application)** offer — a
correctly-formed `0xFFFD` packet advertising company `0x0820`, app `0x0001`, at a version one higher than the
switches run (`0x0c107187` vs `0x0c107186`). A switch willing to receive a transfer would answer with **DFU
data-request** packets (`0xFFFB`) *before any flash is written*, so the offer alone is a zero-risk reachability
test.

Two engineering notes from getting it on air: the ESP32 must advertise with a **public** address
(`BLE_ADDR_TYPE_RANDOM` without a configured random address silently refuses to start), and a **low-duty scan**
(30 ms window per 320 ms) is needed or the scanner starves the transmitter — verified by sniffing our own
`fdff…` packets from the hub.

**Result: the switches never answer.** Our offer is confirmed on air and the switches are in range (their
FWID beacons arrive fine), but no switch emits a single data-request across repeated runs.

**Why, from Nordic's own source.** Receiving DFU is opt-in at the application layer. A device that hears a
newer-firmware beacon raises `NRF_MESH_EVT_DFU_FIRMWARE_OUTDATED` to its application, and
`doc/.../dfu_integrating_into_app.md` is explicit: *"If the application decides to receive new firmware, it
must call the `nrf_mesh_dfu_request` [function]… If neither `nrf_mesh_dfu_request` nor `nrf_mesh_dfu_relay` is
called… "* nothing happens. Brilliant's firmware does not auto-accept — correctly, since auto-accepting
unsigned OTA from any passing broadcaster would be a glaring hole.

So the transport is open to us, but the **trigger is not**: the Control panel must have sent some proprietary
message that made the switch call `nrf_mesh_dfu_request()`. That trigger is unknown — most likely a Brilliant
vendor-model message. Finding it is the one remaining over-the-air avenue, and it is a needle-in-a-haystack:
the vendor model `0x0820/0x0001` takes unicast messages (we hold the app key), but its opcodes are
undocumented and our earlier no-parameter sweep drew no reply.

**Where that leaves the ladder:** OTA is not closed, but it is now gated behind reverse-engineering an
undocumented trigger, with uncertain odds. The SWD reflash remains the one route certain to work — at the cost
of pulling each switch once.

### Hunting the DFU trigger: the combined oracle

If a Brilliant vendor-model message is what makes the switch call `nrf_mesh_dfu_request()`, we can find it
without guessing blind: run the ESP32 DFU offer continuously (it reports any `0xFFFB` data-request), and send
candidate vendor opcodes to our node over the SIG mesh one at a time. A data-request appearing right after an
opcode would name the trigger. The offer sends no firmware, so the whole hunt stays non-destructive.

`brilliant-mqtt` (`joyfulhouse/brilliant-mqtt`) does not help here: it talks to the panel's *internal* message
bus (a virtual `ble_mesh` device), and the panel's closed software translates that to mesh — the raw vendor
opcodes and the DFU trigger live in the panel firmware, which the dead panels no longer give us.

**Result so far:** all 64 vendor opcodes `0xC0..0xFF` (company `0x0820`), sent with no parameters, produced no
data-request; the node stayed healthy. So no *bare* vendor opcode is the trigger.

That is the tractable case exhausted. A real trigger most likely carries parameters (a target FWID, a transfer
descriptor, an authority token), and that space is effectively unbounded without documentation — the panel
firmware or Brilliant's cloud firmware package would name it, and neither is in hand. The combined-oracle
tooling (`tools/` + `dfu-probe/`) remains, so the hunt can resume if that information ever surfaces; blind
parameter brute-forcing is not a good use of time.

## The vendor model opens: a read/write configuration store

*15 September 2026, later the same day. The section above said the vendor model could not be addressed.
It can. What unlocked it was a detail from the house rather than the protocol: **Brilliant's panel asks, at
setup, whether a switch is a dimmer or a switch.** That choice is not any SIG state — there is no "load type"
in Generic OnOff or Generic Level — so it must be a vendor write. A model that receives a load type is a
command target, and the earlier sweep found nothing only because it sent **no parameters**: a handler that
length-checks its payload drops a zero-length message before dispatch, every time.*

### The protocol

Vendor access PDUs are `0b11xxxxxx` then the Company ID little endian, so every message starts `C1 20 08`.
The payload's first byte is a command, the second a field id:

| | |
|---|---|
| `01 <field>` | get → `03 <field> <value…>`, value padded to a 12-byte block |
| `11 <field>` | get → `13 <field> <value…> 00`, value at its natural width |
| `12 <field> <value…> 00` | **set** → `13 <field> <value…> 00` |
| `04` | bare ack |
| `06 <field>` | echo |

Every other command byte in `0x00–0xFF` is dead; the surface was swept exhaustively. **The trailing `00` on a
set is load-bearing** — omit it and the node ignores the write silently, which reads as "nothing here is
writable" for every field at once.

Writes stick and read back. Field `0x04` was set to 500, re-read as 500, and restored.

### The store

55 fields answer. Two of them are the proof that the decode is right, because they match data obtained by
completely unrelated routes:

| Field | Value | What |
|---|---|---|
| `0x0e` | `017e41f678010007ff8a6b264e9e410a` | **Device UUID** — byte-for-byte the one captured off a real reset switch for `mesh-provisionee` |
| `0x0f` | `af0001028671100c` | **DFU firmware id** — carries app version `8671100c`, exactly the `0xFEE4` FWID beacon |
| `0x04` | 1000 | brightness setpoint, native scale **0–1000** (which is why a `Generic Level Get` returned a present level of 1000 — a value we never sent) |
| `0x13` | ~34 | analogue, rises with activity and decays back; almost certainly temperature |
| `0x1d` | rising | uptime counter |
| `0x2e`, `0x2f` | structured | two parallel tables, shaped like load/dimming profiles |
| `0x47` | `a44f9a64324ac183` | device identifier |

`brilliant/tools/vendor.py` sweeps opcodes and payloads, `snapshot.py` reads all 55 and diffs two reads,
`poll.py` turns a field into an event stream, `writable.py` separates configuration from status.

### What is still not solved

**Dimming is not restored, and blind config-poking has been exhausted.** The load sits in switch mode after
the factory reset wiped the panel's setup, and the mode selector was not found by guessing:

- All four brightness-scale fields — `0x04`, `0x07`, `0x4b`, `0x51`, each reading 1000 — accept a written
  value and report it back, and **none of them drives the triac.** Ramping them bright/dim/bright with the
  lamp watched produced no visible change. They are stored setpoints, not the live output.
- Eight boolean/enum fields (`0x0c 0x1a 0x1b 0x1c 0x28 0x49 0x50 0x56`) were flipped, singly and together,
  with no effect on the load and no visible behaviour change.
- The structured tables `0x2e`/`0x2f` (shaped like load/dimming profiles) were left untouched: mutating a
  15-byte table blind is the riskiest write available and the least likely to read cleanly against a
  human lamp-watch oracle. If the mode lives anywhere in the store, this is the remaining candidate — but it
  is not worth brute-forcing.

The lesson is that the load-type selector is not reachable by guessing single fields, and each guess costs a
visual check. The panel sets this mode once, at setup; the way to learn it is to **watch the panel do it**,
not to search the store — see the recorder route below.

**The PIR is still not visible.** No field behaves like a motion flag: a full 55-field diff across 45 seconds
of waving, tapping and sliding moved only the temperature and uptime fields, and polling every zero-valued
one-byte field for 140 seconds of continuous motion moved nothing. A transient flag could still hide between
polls, but it is not sitting in this store where a reader can see it.

### Control confirmed: driving the real switches

`tools/panel_cmd.py <target> on|off|dim:<pct>` sends an acknowledged Generic OnOff/Level Set to a panel switch
with the captured appkey and prints the Status it reports back. On/off works through Generic OnOff Set. **Dimming needed a captured detail:** sniffing the panel dim a switch
from the app showed it sends **Generic Level Set (0x8206) with the level on a 0-1000 scale** (e.g. `6400`=100
=10%, `e803`=1000=full) plus a transition-time byte -- NOT the SIG -32768..32767 mapping. A standard-mapped
level lands off the switch's range and does nothing (the switch even echoes it back, which is why it looked
like it "acted"). With the 0-1000 scale, `panel_cmd.py 000a dim:<pct>` drove switch `0x000a` across its full
range full -> 2% -> full, the light visibly following each command -- proof of **write**, over BLE mesh, with
no Brilliant app and no reset. Combined with the reads above, the real wall
switches are now fully ours to read and drive: on/off, dim level, and motion. Resetting a configured wall
switch would only strip the panel's dimmer/PIR setup and is not worth it; the keys make the panel's own
configuration work for us.

### PIR, found: vendor field 0x13

Polling switch `0x000a` (a hallway dimmer, ~5 ft of PIR range) for the fields the panel reads, only **field
`0x13`** both answered and tracked movement. With `tools/panel_poll.py` (vendor GET `c1 2008 11 13` over the
proxy, decoded with the appkey), it sat at a floor of ~2 when the person was still and spiked to **7-8 when
they walked past**, settling back on a timer. It is an analogue motion-energy level, not a clean on/off flag,
and the short hallway means there is no true zero baseline -- but it is unmistakably the motion signal, and the
other candidate fields (`0x19`, `0x28`, `0x40`) did not even respond on the configured switch. So motion is
`0x13`, read the same way the panel reads it. `panel_poll.py [target] [secs]` with `POLL_FIELDS=13` polls it;
walk past and watch it rise.

### Reading the live mesh: the original question, answered

With both keys, one more bug stood in the way. `tools/panel_sniff.py` connected to a panel switch's proxy but
received only the Secure Network Beacon -- never any mesh traffic, and never a Filter Status for our
"forward everything" request. The cause was in `mesh.py`: the **Proxy Nonce** (type 0x03) was built with
`CTL|TTL` in octet 1, where the spec mandates a `0x00` pad. Our own switches tolerated the malformed nonce
(both sides used it); the real panel firmware did not, so every proxy-filter command silently failed and the
proxy forwarded nothing. Fixed to emit `0x00` for the proxy nonce.

Immediately, the panel's mesh opened up. Standing at a dimmer and working it, switch `0x000a` flooded its live
state to the all-nodes address, decoded with the captured AppKey:

    0x000a -> 0xffff  Generic OnOff Status: 01 / 00        (tap on/off)
    0x000a -> 0xffff  Generic Level Status: e803 .. 1800   (1000 .. 24 -- the dimmer groove, live)

and node `0x0012` (the panel's controller element) was seen polling a switch's vendor fields:

    0x0012 -> 0x000e  VENDOR op 0x01: 0107080f191c282d2e2f404142

**This is the thing the top of this document called lost.** The switches *do* publish their real physical
state -- on/off and dim level -- and with the panel's netkey + appkey (+ IV 7, + the proxy-nonce fix) we read
it in real time, exactly as Brilliant's own panel does. The earlier "local touch bypasses the mesh" finding was
an artefact of testing an *unconfigured* switch on our own network without the panel's keys; a panel-configured
switch reports everything. PIR is the remaining item: it is one of the vendor fields the panel polls in that
list, readable now by getting those fields from a configured switch with the panel appkey.

### It worked twice over: the recorder captured the AppKey

16 September 2026. `brilliant/mesh-provisionee/` was extended from a netkey grabber into a full **recorder**:
after provisioning it switches from the provisioning service to the **Mesh Proxy Service**, advertises a
**Node Identity** beacon (so the app reconnects to the exact node it just provisioned within a second instead
of timing out after ~60s), and answers the app's configuration sweep with a minimal Config Server —
Composition Data, AppKey Get, NetKey Get, and the model App-Bind / Publication-Set the app issues.

Each missing answer showed up as the app looping one opcode then giving up; they were added one at a time
(`0x8008` Composition Data Get, `0x8001` AppKey Get, `0x8042` NetKey Get, `0x803D` bind, `0x03` publication).
When the sweep completed, the app sent **Config AppKey Add**, and the recorder decrypted it with the DevKey
(derived at provisioning as `k1(ECDH secret, ProvisioningSalt, "prdk")`) and logged the panel **AppKey**. It
then decoded the app's subsequent **vendor writes** live with that AppKey — proof the key is right.

Both keys now live in `~/.config/brilliant-mesh/panel-net.json`: **netkey + appkey (AID 0x37) + IV index 7**.
That is the entire panel mesh — enough to decode every switch's PIR and taps and to send them commands. The app
still reports "failed at configuring" because we don't answer a vendor firmware-id GET (`c1 2008 01 0f`); that
is cosmetic, and irrelevant now that the keys are captured. `tools/panel_sniff.py` loads both keys and decodes
the app layer, so a switch's publications read out as real values.

### The route that does not require guessing

We now know the exact shape of the message we are looking for: `C1 2008 12 <field> <value> 00`. The panel
sends one when it sets a load type, and plausibly another to enable motion reporting. So
`brilliant/mesh-provisionee/` is no longer only a netkey capture — **it is a recorder for the panel's whole
setup transcript.** Posing as a fresh switch, accepting provisioning, and then implementing enough of a
Configuration Server to receive what follows would hand us the AppKey, the bindings, the publication
addresses, and every vendor write the panel makes, verbatim. That turns an unbounded search into a reading
exercise.

### The live panel, and capturing the netkey by being provisioned

A later discovery reframed everything: the wall panel's **screen is dead but the panel is alive** — the mobile
app still controls the six switches still on its network. A dead screen is not a dead panel. That means the
panel is a working mesh *provisioner*, and provisioners hand the network key to devices they provision.

The panel itself is a sealed black box on the LAN — no SSH (Root SSH was never enabled, and the dead screen
can't enable it), no ADB, no HomeKit bridge, nothing inbound; the app reaches it via Brilliant's cloud. So we
cannot log in and read the key. But we don't have to: **if the panel provisions a device, it gives that device
the netkey.**

`brilliant/mesh-provisionee/` is an ESP32 that poses as a fresh Brilliant switch — the device side of the same
provisioning protocol `tools/provision.py` drives, sharing the verified crypto plus ECDH P-256. It advertises
as unprovisioned (No-OOB), accepts the panel's provisioning over PB-GATT, and prints the netkey the panel
delivers. With that key, the panel's whole mesh — every switch's PIR and tap-state, published to the panel —
becomes decryptable, locally, with nothing pulled from the wall.

**First attempt:** the app's "Add a device" flow (which searches for nearby faceplates, not only QR codes) never
listed our spoof. The device presents but does not look authentic — most likely because Brilliant discovers
switches via the **PB-ADV** unprovisioned beacon (a `0x2B` mesh-beacon AD type) rather than the PB-GATT service
we advertise, and/or filters the list by a Brilliant-specific Device UUID. The fix is to capture a real switch's
unprovisioned beacon (by resetting our expendable node `0x0002`) and replicate it exactly.

### The QR code is the whole answer: UUID + Static OOB

The early attempts failed and the reasons were guessed at above. Decoding an actual switch's QR code settled
it. **A Brilliant QR is 32 bytes of ASCII hex — the first 16 are the Device UUID, the last 16 are a 128-bit
Static OOB secret:**

    017e420e39c80007b0d86cdb5d3c622b | 2fb5427e3db145bd8d325dccf3cc456d
    <-------- Device UUID --------->   <--------- Static OOB --------->

The UUID has fixed bytes `01 7e … 00 07 …` (indices 0,1,6,7) across every switch and per-device bytes
elsewhere — the same shape as the UUID we read from vendor field `0x0e`. The app scans the QR, looks for a
device advertising that UUID, and provisions it with **Static OOB** using the trailing 16 bytes.

That explains every earlier failure at once:

- **Two devices, one GUID.** The spoof was hard-coded to a *real* switch's UUID. Factory-reset that switch to
  add it and both it and the spoof broadcast the identical UUID — the collision the user saw.
- **The lone spoof still would not add.** It declared **No-OOB** and held no secret. The app, holding the OOB
  from the QR, drives the confirmation with Static OOB; a device that cannot reproduce that value fails auth.
  No beacon tweak could have fixed this — it is an authentication requirement, not a discovery one.

**The fix, implemented in `mesh-provisionee`:** advertise the UUID from a real QR, declare Static OOB available
in the capabilities (`StaticOOBType = 0x01`), and answer the provisioning confirmation with the QR's 16-byte
OOB value instead of zeros. `fill_auth()` picks the OOB value when the provisioner selects method `0x01`
(what the app does) and falls back to zeros for a No-OOB provisioner, so the listen-after-reset flow still
works too. Builds clean; the UUID/OOB pair at the top of `main.cpp` is the identity of one physical switch and
is swapped for whichever switch's QR is being scanned.

**The one operational catch:** the physical switch whose QR is scanned must not be advertising unprovisioned at
the same time, or the collision returns. Scan a spare switch's QR and keep that switch provisioned or powered
down while the spoof wears its identity.

### It worked: the panel's network key is ours

16 September 2026. With Static OOB implemented and a spare switch's QR, the Brilliant app provisioned the ESP32
spoof end to end:

    <- Invite  ->  Capabilities (Static OOB available)
    <- Start (auth 1 = Static OOB)
    <- Provisioner PublicKey  ->  our PublicKey
    <- Provisioner Confirmation  ->  our Confirmation
    <- Provisioner Random (verified)  ->  our Random
    NETKEY  <captured>   keyIndex 0x0000  flags 0x00  ivIndex 0x00000007  unicast 0x001a

`Provisioner Random (verified)` is the proof the Static OOB value was right — the confirmation CMAC matched.
**And the captured netkey's network-ID (`k3`) is `3deef9825e444955` — byte-for-byte the netid every live
Brilliant switch on the wall advertises**, the one `census.py` labels "Brilliant net - LIVE". So this is not
some isolated key; it is *the* key to the whole panel mesh. It lives in `~/.config/brilliant-mesh/panel-net.json`
(mode 600, outside the repo). Note **IV index 7**, not 0 — decryption fails silently with the wrong IV.

One firmware bug surfaced on the way: `sendPDU` built its PDU in a `uint8_t pdu[64]`, but the 64-byte Public
Key plus its type byte is 65, so sending our key overflowed by one and the stack canary rebooted the chip
mid-provisioning. Every earlier No-OOB attempt had died at discovery and never reached the Public Key send, so
the bug stayed latent until Static OOB got us that far. Fixed to `pdu[80]`.

**What the netkey does and does not give.** The netkey decrypts the *network layer* of the entire panel mesh —
every switch's source, destination and sequence, so we can see who transmits and when, which settles whether
the switches report PIR/taps at all. The PIR/tap *values* are a layer up, under the panel's **AppKey**, which
provisioning does not hand over. The AppKey arrives in the post-provisioning configuration the app tries to
send next (Config AppKey Add, model bindings, publication setup) — and our provisionee stops at netkey capture
and does not answer it, which is why the app hangs at "adding to network". Capturing the AppKey too means
extending the provisionee into a **recorder**: implement enough proxy + Config Server to accept the AppKey Add
and log every vendor write the panel makes. That is the remaining step, and it delivers both the AppKey (to
decode PIR/tap values) and the panel's load-type / motion-enable writes verbatim (to configure our own claimed
switches for dimming and motion).

## The always-on bridge: switches as Home Assistant devices

*16 September 2026, evening. Everything above ran from a laptop over a one-off BLE connection. This makes it a
fixture of the house.*

`brilliant/esp32-bridge/` was rewritten from the own-network prototype into the **panel bridge**: an ESP32 on a
USB charger that holds one mesh-proxy link into the panel network with the captured netkey + appkey, decodes what
the switches say, polls what they will not volunteer, accepts commands, and describes every switch to Home
Assistant over MQTT discovery. One link is enough because the switches relay for each other; the puck just needs
to be within a good GATT range (about −80 dBm) of *any* one of them, which is why it is a puck on a wall charger
and not a radio in the hub: it works the same whether the hub is a Pi, a NUC or a VM.

**What it proved, against the Mac dev stack.** One `Generic OnOff Get` to the all-nodes address made every OnOff
server answer: eleven switches (`0x0004 0x0005 0x0006 0x0008 0x000a 0x000b 0x000e 0x0010 0x0011 0x0014 0x0016`),
three more than anyone had counted; `0x0010`/`0x0011` were guessed to be the live panel's own loads, since a
Control panel replaces a one-to-four-gang switch itself. **That guess is wrong for `0x0011`:** on 17 September it was blinked on command while a person watched, and identified as the stairway switch — the load half of the two-way pair whose companion we had reset. `0x0010` remains untested, so treat the same guess about it as unsupported rather than confirmed. Their on/off and dim levels arrived as they were
touched. `brightness/set 128` over MQTT dimmed the hallway to half — the switch published `Level Status f401`
(500/1000) to all-nodes on its own — and `255` brought it back; HA's brightness went 255 → 128 → 255 on the
retained topic. The MQTT session then held for the whole soak, with commands still landing five minutes in. HA
created 11 lights, 11 motion sensors, 11 diagnostic levels and one bridge sensor from the discovery messages,
and the brain's own classifier maps those domains straight onto *light* and *motion*.

**Four things broke on the way, and each is now a line in the code.**

- *WiFi and BLE share the radio.* Disabling WiFi modem sleep — the usual reflex for a stable TCP session —
  makes the BT controller abort at boot (`Should enable WiFi modem sleep when both WiFi and Bluetooth are
  enabled`), and doing it *after* the controller is up aborts too. Sleep stays on; instead the bridge asks the
  switch for a 50–100 ms connection interval and prefers WiFi in the coexistence scheduler.
- *The core's Bluedroid BLE library can hang the main loop for ever.* Its `writeValue` waits on a semaphore that
  nothing releases if the link drops mid-write, and a −99 dBm link drops often. The broker saw the bridge fall
  silent 29 s after connecting and published its last will. The BLE layer now runs on NimBLE, whose connects and
  writes have timeouts, and the MQTT keepalive is 60 s so a stalled second on the radio is not a lost session.
- *MTU negotiation fails on some links* and leaves the default 23, where a `Generic Level Set` no longer fits one
  ATT write. Writes honour the real MTU and SAR-segment, as the laptop tools always did.
- *A broadcast Get loses replies* when a dozen switches answer at once, so it is used for discovery only; state
  is resynced with unicast Gets to each known switch, at link-up and every ten minutes.

Two firmware bugs inherited from the prototype were also fixed: the proxy nonce carried `CTL|TTL` in octet 1 (the
very bug that had blinded the laptop tools earlier — the panel's firmware rejects it silently), and the
application nonce never set the ASZMIC bit for segmented messages with a 64-bit MIC. Segmented inbound messages
are now reassembled and acknowledged, and Secure Network Beacons are authenticated with the beacon key so an IV
Index change by the panel would be followed rather than turn every message into silence.

**What the live mesh looked like from inside.** The panel elements `0x0002` and `0x0012` poll switches constantly
(`Generic OnOff Get`, `Generic Level Get`, and vendor `11 <field list>` gets with up to fifteen fields in one
message), so the panel is very much alive behind its dead screen. Brilliant's Gets carry a one-byte token that
the Status echoes as a trailing byte, and every `Level Status` ends `04 00 29 00` regardless of switch — vendor
extras after the SIG fields; only the leading present-value is used. Motion field `0x13` rests at a different
level per switch (`0x000a` ~130, `0x0010` ~285, most 0–2, `0x000b` wandering 4–11), so the bridge learns each
switch's floor and calls motion when the level sits 4 above it. Separately, switch `0x0016` publishes vendor
field `0x0c = 1` to all-nodes on its own every twenty seconds or so, and the panel's poll list does not include
`0x13` — so whatever the panel reacts to must arrive unsolicited, and `0x0c` is the candidate. The bridge treats
both as motion and logs both; nobody walked past a switch during the build, so this is the one claim in this
section that a person still has to confirm, with `tools/bridge_watch.py` open.

**The arithmetic that shapes it.** Mesh sequence numbers are 24 bits and every poll spends one. At the default
250 ms round-robin that is four a second, about seven weeks per address. Rather than exhaust one, the bridge
steps to the next unicast (`BRIDGE_ADDR + n`, from `0x0100`) and starts its sequence again; the switches' replay
lists are RAM and forget on any power cut, and a dozen extra entries over years is nothing to them.

**What is left.** The hub's Mosquitto refuses the bridge, correctly: it takes only the password in the hub's own
`driver-layer/.env`, which this laptop does not hold, so `secrets.h` currently names the Mac's broker. Putting
the hub's `MQTT_USER`/`MQTT_PASSWORD` in that header and reflashing is the whole move. Getting WiFi, broker and
keys onto a puck without a laptop at all is its own piece of work, and the right shape for it is the hub
flashing the puck over USB the way it already adopts radio sticks.

**A second puck, on our own network.** Later the same evening an ESP32-S3 took the same firmware with a header of its
own, pointed at `mesh-net.json` and publishing under `mesh/` rather than `brilliant/`. It found the factory-reset
switch (`0x0003`, the only node on that network) at −60 dBm, put it on the hub as `light.mesh_switch_0003` with a
motion sensor, and had an `ON` acknowledged. Two things that proves: the migration off the panel's keys is "same
firmware, different key file", and two pucks on two networks coexist in Home Assistant because every id carries the
MQTT base. One thing it shows plainly: that switch's motion field reads a flat 32 since its reset, and its `Level Set`
draws no `Level Status` — the dimmer/PIR configuration the console wrote is what a reset loses, and finding those
fields by diffing a configured switch against this one is the next job.

## The dimmer-mode diff, and what it turned up (16 September, night)

With the panel appkey in hand, `tools/vendor_store.py` reads a switch's whole vendor store on either network,
and `--diff` compares two reads. The hallway dimmer (`0x000a`, console-configured) against the factory-reset
switch (`0x0003`, ours): 41 of 55 fields identical, 14 different. Identity and counters aside (`0x0d 0x0e 0x1d
0x47`), the console had written `0x1a=2 0x1b=0 0x48=1 0x4f=1 0x56=3`, setpoints `0x03=200 0x07=500`, and
`0x0b=0x37`. Mirroring them onto the reset switch, one group at a time, with an acknowledged `Generic Level Set`
after each:

- **`0x48`/`0x4f` turn on unsolicited reporting.** The moment they were set, the switch began publishing vendor
  field `0x13` to its publish address five times a second. Field `0x13` had only ever answered a Get before.
- **`0x03`/`0x07` are the thresholds for that reporting.** Writing 200 and 500 silenced the flood at once; the
  switch now publishes only on a real change.
- **`0x0c` is published on every on/off change** (`0` on off, `1` on on, and `1` when a command arrives). It is
  a state notice, not motion, which retracts the guess that `0x0016`'s periodic `0c=1` was a PIR.
- **`0x0b` is not the mode**; writing the dimmer's `0x37` only brought the flood back. Restored to `0xff`.
- **Dimming stayed refused throughout.** The reset switch answers `Level Get` (present 1000) but never
  acknowledges a `Level Set` in any shape: 0–1000 with the console's transition bytes, without them, or SIG-mapped.
  The console-configured dimmer acknowledges all of them. So the selector is not among the 55 known fields as
  written live; either it is read only at boot (a power cycle is the next test), or the dimmer carries fields
  outside the swept list (a 256-id sweep of both is the test after that).

**And a refinement the run forced.** Field `0x13` fell to 0 when the load switched off and climbed back after
it came on, and its resting value differs per switch through the bridge (about 130 on the full-bright hallway,
285 on `0x0010`, near zero on switches driving small loads). That does not undo the hallway walk-past, which was
watched: still at ~2, 7–8 on a pass, settling on a timer. It says the value carries a *baseline that tracks the
load* — a PIR element beside a warm triac would read exactly so — and motion is the rise of a few counts above
whatever the baseline is. The bridge already learns a floor per switch and reports on the rise; it now re-learns
the floor after every on/off, because the baseline jumps with the load. A walk-past with the lamp left alone,
watched on `bridge_watch.py`, is the confirmation still owed for the bridge's own thresholds.

### Solved: dimmer mode on a reset switch is the mirrored fields plus a reboot

The missing ingredient was a power cycle. With `0x1a=2 0x1b=0 0x48=1 0x4f=1 0x56=3 0x03=200 0x07=500` written
(`tools/setfields.py 1a=02 1b=00 48=01 4f=01 56=03 03=c800 07=f401`) and the switch's Safety Disconnect pulled
and pushed back, the reset switch acknowledged the next `Generic Level Set`: `Level Status` present 1000, target
300, remaining 0x05, then a publication of 300 — a real ramp, identical to the console-configured hallway
dimmer — and the same on the way back to full. The firmware reads its mode at boot, which is why every live
write looked inert. Which of the seven fields is the selector is not yet bisected; the set as a whole is the
recipe, and it is what the console writes. In the same minute a walk past switch `0x000b` raised its `0x13`
from a floor of ~5 to 8 and the bridge reported motion, with no lamp involved: the thresholds hold on a body.

So a factory-reset Brilliant dimmer can be brought back to full function on our own network without the
console: provision it, bind the models, write the seven fields, power-cycle. Nothing now depends on the panel.


### Fully validated end to end on a re-provisioned dimmer (16 September, night)

The recipe was proven on a real single-pole load with a person watching. The hallway dimmer (`0x000a` on the
panel network) was captured (`tools/vendor_store.py`), factory-reset, provisioned onto our own network as
`0x0005`, bound, given its own captured config, and power-cycled. Then over our network it dimmed on command
and **the lamp visibly followed** — 30, 100, 10, 60, 100 percent, each a real ramp, confirmed by eye, not just
by the `Level Status` on the wire.

Two things this run also settled:

- **The vendor model must be bound to our AppKey too.** `ensure_bound` in `tools/onoff.py` now binds
  `0x0820/0x0001` alongside `0x1000` and `0x1002`; `Node.bind()` takes an optional company id and builds the
  4-byte vendor model identifier. Without it, every `12 <field>` write is under a key the vendor model does not
  hold and is silently dropped — which is exactly what the first attempt on `0x0004` showed (binds fine, every
  config read comes back empty).
- **A companion in a two-way pair has no load.** The first switch tried (`0x0004`, provisioned earlier) turned
  out to be the companion end of a stairway two-way: it acknowledges on/off and dim on the mesh but drives no
  lamp, because the load is wired to the main unit. It is a working loadless wall controller on our network now,
  a candidate for a scene button once the puck provisions and the hub binds one.

**So the console is retirable in full.** A factory-reset Brilliant dimmer becomes a working dimmer with motion
on our own network by: provision, bind (`0x1000`, `0x1002`, `0x0820/0x0001`), write the load-type/config fields
captured from a still-configured switch, power-cycle. Nothing Brilliant remains in the loop.

## Spec: adopting a switch, as a provisioner would replay it

*Written for the firmware/puck provisioner behind "Add a wall switch". This is the exact ordered sequence,
with the two orderings that are load-bearing called out. Proven by hand on two switches (16 September 2026).*

**The one rule that is easy to miss:** the vendor model must be bound to the AppKey **before** any vendor
config write, and the config must be written **before** the power-cycle. Get either order wrong and the switch
looks like it is simply refusing to be configured — writes are accepted on the wire and silently dropped.

### 1. Discover

The switch advertises unprovisioned: PB-GATT service `0x1827`, and a PB-ADV Unprovisioned Device beacon
(AD type `0x2B`). Its **QR code is 32 bytes of ASCII hex: the first 16 are the Device UUID, the last 16 are a
128-bit Static OOB secret.** Match the advertised UUID against the scanned QR's first half.

On macOS, scan with a detection callback rather than a one-shot discover: the switch interleaves its `0xFEE4`
DFU beacon with the `0x1827` beacon, and a scan that keeps only the latest advertisement misses it
(`tools/ble.py`).

### 2. Provision (PB-GATT)

| Step | Notes |
|---|---|
| Invite | attention 0x00 |
| ← Capabilities | |
| Start | algorithm `0x00`, public key `0x00`, **auth method `0x01` (Static OOB)** for a QR add; `0x00` (No OOB) works for a switch we factory-reset ourselves |
| PublicKey ⇄ | P-256 ECDH. **The PDU buffer must hold 65 bytes** (type + 64-byte key) — a 64-byte buffer overflows and reboots the chip mid-handshake |
| Confirmation ⇄ | `CMAC(conf_key, random ‖ auth)`, where `auth` is the QR's 16-byte OOB for method `0x01`, else 16 zero bytes |
| Random ⇄ | verify the provisioner's confirmation |
| Data | netkey, key index, flags, **IV index**, unicast. IV index must match the network or every later message fails to decrypt, silently |
| ← Complete | |

### 3. Configure the node (DevKey-encrypted, to its new unicast)

In this order:

1. **Config AppKey Add** — netkey index 0, appkey index 0, the AppKey → status `0x00`.
2. **Config Model App Bind** → `Generic OnOff Server 0x1000` → status `0x00`.
3. **Config Model App Bind** → `Generic Level Server 0x1002` → status `0x00`.
4. **Config Model App Bind** → **vendor `0x0820/0x0001`** → status `0x00`. The model identifier here is
   *company id LE ‖ model id LE* (4 bytes), not the 2-byte SIG form. **Without this bind, every step 4 write is
   dropped without a reply** — the symptom is a switch that binds fine and then answers no vendor Get at all.
5. **Config Model Publication Set on all three models**, publish address **`0xffff`**, TTL 7, period 0,
   retransmit 0 → status `0x00`. The Status comes back **segmented**, so a reader that ignores segmented
   messages will report failure on a write that succeeded.

**Binding is not publishing, and forgetting step 5 makes a SILENT SWITCH.** A model announces nothing unless
it has a publish address; provisioning and binding leave it at `0x0000`. Such a node answers every Get, obeys
every Set, and volunteers nothing — no tap, no state change, no motion — which reads as a dead switch that is
somehow still reachable. This is exactly what happened to the first switches this house adopted: `0x0004` was
pressed and swiped by hand and published *nothing*, while `0x0003` (same network, same provisioner, but which
had `explore.py` point its models somewhere) published on its own. Reading it back settled it in one line:
`0x0003` had all three models on `0x0001`, `0x0004` had all three on `0x0000`. `tools/publication.py <addr>`
shows it and `--to 0xffff` sets it.

`0xffff` is chosen because it is what the console itself does — a panel switch broadcasts its own touch as a
`Generic OnOff Status` to all-nodes — and because it means any puck on the network hears the switch without
depending on which address happens to be listening.

### 4. Write the load configuration (AppKey-encrypted)

*(Numbering note: the publication step above is part of section 3's config sequence; the field writes below
still come after all of it.)*

Vendor access PDUs are `C1 20 08` (opcode ‖ company id LE), then:

    write   C1 2008 12 <field> <value LE> 00      ->  C1 2008 13 <field> <value> 00
    read    C1 2008 11 <field>                    ->  C1 2008 13 <field> <value> 00

**The trailing `00` on a write is load-bearing** — omit it and the write is ignored silently. Order among the
fields does not matter; they must all come after the binds. Values are the ones captured from a switch the
console had already set up (`tools/vendor_store.py`), because they differ per switch. The hallway dimmer's set,
as a worked reference:

| Field | Value | What it appears to be |
|---|---|---|
| `0x1b` | `00` | **load type candidate** — `00` on both dimmers seen, `03` on the unit stuck in on/off mode |
| `0x56` | `03` | **load type candidate** — `03` on the dimmer, `02` on the unit stuck in on/off mode |
| `0x1a` | `02` | not the load type: two working dimmers differed here (`02` and `01`) |
| `0x48`, `0x4f` | `01`, `01` | **enable unsolicited reporting** of field `0x13`; setting them starts a ~5 Hz publication |
| `0x03`, `0x07` | `c800` (200), `f401` (500) | thresholds for that reporting; leaving them at 0 floods the mesh |
| `0x4c`, `0x4d`, `0x52` | `64`, `00`, `64` | dimming curve/limits, per switch |

**Not bisected.** The set as a whole is the recipe and it works; which single field flips dimmer vs switch was
not isolated, because each guess costs a power-cycle and a human looking at a lamp. `0x1b` and `0x56` are the
two candidates, on the evidence above. Fields deliberately **not** replayed: `0x0e` (Device UUID), `0x47`
(device id), `0x0b` and `0x1d` (free-running counters), `0x13` (live motion reading), `0x0c` (on/off notice).

### 5. Power-cycle the switch

Mains off and on. **The load type is read only at boot** — this is why every live write looked inert for a whole
evening. There is no mesh message that applies it.

**Model publication is read at boot too**, and this is the crueller one because its failure is silent and looks
exactly like the fix not working. Set publication, read it back, and the readback confirms it — and the switch
stays mute until it restarts. Anyone adopting a switch would reasonably conclude the write had failed and go
looking for a different cause. Proven on `0x0004`: set to `0xffff` and verified on readback, it published
nothing at all through a hand pressing it repeatedly; the moment power was cut and restored it broadcast its
heartbeat on its own, the first unsolicited message it had ever sent.

So the power cycle is not a step that applies the load type. **It is the step that applies everything written
in sections 3 and 4**, and nothing written there can be assumed live until it has happened.

### 6. Verify

`Generic Level Set` = `82 06 <level LE> <tid> <transition 0x05> <delay 0x00>`, level on a **0–1000 scale**, not
the SIG `−32768…32767` mapping. A working dimmer answers `Generic Level Status` carrying *present* and *target*
and ramps; the lamp follows. A switch still in on/off mode echoes a level and the lamp does not move.

`tools/restore_switch.py adopt <captured.json>` / `verify <addr>` runs steps 1–4 and 6 from the laptop, and is
the reference implementation of this sequence.


## The multi-way pair protocol: switches talk to each other, and the console is not in it

*17 September 2026. This supersedes an earlier conclusion of mine in this document that switches never address
each other and that multi-way was probably mediated by the Control panel. Both were wrong, and the caveat I
attached to them — that no intact pair had been pressed while anything was capturing — turned out to be the
whole story.*

An intact two-way pair on the panel network (`0x0005` the main with the load, `0x0006` its companion) was
pressed by hand while everything on the mesh was captured. Three companion presses, then three main presses.

**A companion press is a vendor message straight to the main:**

    0x0006 -> 0x0005   C1 2008 04 03      the companion's press command
    0x0005             (its load moves)
    0x0005 -> 0xffff   Generic OnOff Status   the main announces its new state

**A main press is the broadcast alone** — no `0403`, no exchange with the companion. Two distinguishable
signatures, repeated three times each. Separately, when the main changes state it sends the companion a
**zero-length** vendor message, which also appears as its reply to a `0403`; that reads as the ack.

**The console never commands anything.** Across the 150-second capture and both controlled runs there is not a
single `Generic OnOff Set` (`0x8202`/`0x8203`) from any source. The panel elements `0x0002` and `0x0012` appear
only polling *other* switches with Gets. Multi-way on this pair is peer-to-peer and the panel is a bystander.

### What this changes

- **Pairing is discoverable on the wire.** `0403` from A to B names the pair outright, and because a companion
  press and a main press have different signatures, a listener can tell which end was touched. Learning a
  house's existing pairs by watching is back on the table; I had written it off.
- **The hard rule looks retirable.** If the pairs do not go through the console, unplugging it should not kill
  them. Not yet retired: one pair, and it deserves repeats before anyone pulls that plug.
- **A relay must trigger on the press, not on the companion's state.** The companion holds its own independent
  position: at one resync `0x0006` reported OnOff `ON` while `0x0005` reported `OFF`. Copying the companion's
  state onto the load would drive the light to whatever arbitrary position the companion happened to hold.

### Two of my own claims that this corrects

- **`04` is not merely a "bare ack".** The opcode table above catalogues it that way from the old no-parameter
  sweep. It takes an argument, and `04 03` is a press. The sweep found nothing because it sent commands with no
  parameters, not because the command family was empty.
- **Zero-length vendor messages are real and used.** The same sweep concluded a zero-length message is dropped
  before dispatch. A zero-length vendor message is what the main sends its companion in a working exchange. The
  sweep's silence meant "no reply warranted", not "not understood".

**Caveats worth carrying.** Timestamps are arrival time at the Mac, not mesh time, so ordering *within* one
second is soft; everything at second granularity and coarser is solid. One pair, one house. And one line in the
first capture — a main-state change adjacent to the first companion press — cannot be attributed with
confidence either way.

**Field `0x0c` is not settled.** This document earlier called it an on/off notice, on the strength of it
following commanded state on switch `0x0003`. In this capture it reads `01` while the main reports `OFF`, and
falls to `00` only long after, which fits an activity or occupancy flag with a hold better than a load state.
Treat both readings as unconfirmed; it was never the thing anything depended on.

### Pairing is stored in the switch, in vendor field `0x08`

The companion's press is a unicast to its partner, so the companion must know its partner's address — and it
does. Reading the whole vendor store of a **pristine companion** (`0x0006`, panel network, never touched by us)
against the switches already captured:

| Switch | `0x08` | `0x1a` | what it is |
|---|---|---|---|
| `0x0006` | `0500` → **0x0005** | `03` | companion of `0x0005` |
| `0x000a` | `0000` | `02` | single-pole dimmer |
| `0x0011` | `0000` | `01` | main of a two-way pair |

**`0x08` is the partner's unicast address**, little-endian, and it is exactly the address that companion sends
its `0403` to. Every switch that is not a companion carries zero. `0x1a` looks like the role — 3 companion,
1 two-way main, 2 single-pole — though that is one example of each.

This is readable with the **AppKey alone**, which matters more than it sounds: Configuration Server state needs
a device key we will never have for the console's switches, but the vendor store does not. **So the whole
house's pairings can be read off switches we do not own**, without pressing anything, by reading field `0x08`
from each switch on the panel network.

It is writable too, so a provisioner can pair switches itself: write each companion's `0x08` with its partner's
unicast (and `0x1a = 3`). That is the "both codes scanned, one job" flow, implemented.

**And it explains the silent adopted companion.** Our `0x0004` was factory reset, which wiped `0x08` to nothing
— so it had no one to send a press to, and setting model publication to `0xffff` did not help because a
companion's press never goes out by publication at all. It has now been written with `0x08 = 0x0011` (its true
partner, which lives on the panel network where nothing of ours holds that address, so the press goes out, no
switch of ours acts on it, and the puck hears it) and `0x1a = 3`.

**Unverified at the time of writing:** whether this takes effect without a power cycle. The load type is read
only at boot, and pairing may be the same. The test is a power cycle followed by a press.

**n = 1.** One pristine companion, one house. The `0x0005` match is exact and the zeroes are consistent, but a
second pair would make this solid.
