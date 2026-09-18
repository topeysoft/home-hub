# Updating a puck: firmware that reaches a hallway

*Written 18 September 2026, after a bug in the bridge puck's indicator light took four flashes over a cable to
find and fix. Nothing in this document is built. It exists because the fix reaches new pucks and no others: the
two in this house will run the old image until somebody carries a laptop to them, and that is not a property a
product can ship with. What is settled here is the shape and the one decision that cannot be taken twice; what
is not settled is at the foot, honestly marked.*

## Why this needs a plan at all

`docs/updates.md` decided how a hub in somebody else's house stays current: signed manifest, verified before a
byte moves, undone by the hub when it does not come back, installed at night without being asked. That document
is about the brain and the containers around it. It does not mention firmware once, and the gap is not academic.

A puck is an ESP32-S3 on a shelf or behind a sofa, bridging a mesh the hub cannot reach on its own. It is the
piece of this system most likely to be somewhere awkward and least likely to be near a laptop. It is also, right
now, the only piece with **no update path of any kind** — the hub flashes bare boards over a cable and nothing
else, ever.

The LED bug is the honest illustration. It shipped white, and a puck adopted last week shows a light that lies
about what it is doing. The fix exists, is committed, is in `releases/bridge/`, and cannot reach a single puck
already in a house.

## What is true today (18 September 2026)

- **No OTA code in the firmware.** Nothing under `brilliant/esp32-bridge/src/` references `esp_ota`, `Update`,
  `ArduinoOTA` or `esp_https_ota`.
- **No second app slot.** The build uses `huge_app.csv`, which is `app0` at `0x10000` and nothing to switch to.
  There is an `otadata` partition, but OTA works by writing the *other* slot and flipping `otadata` to point at
  it. With one slot there is nothing to flip. **No amount of firmware work makes the current image updatable.**
- **No channel to ask.** A puck subscribes to `<base>/<net>/+/set` and `<base>/<net>/+/brightness/set`. Those
  are lamp commands. There is nothing an update could arrive on or be requested through.
- **The hub flashes cable-only, and only bare boards.** `BridgeCable.flash()` shells esptool at a serial port
  (`brain/hub/bridge.py`), and `_setup()` calls it under `if j["bare"]`. A puck that answers `hello` is never
  reflashed, at any version. This is why `0.2.1` reaches new pucks and no others.
- **The flash is mostly empty.** The board reports 16 MB. `huge_app.csv` maps 4 MB of it. The firmware is 981 KB.
  Twelve megabytes are unaddressed, which is the one piece of luck in this document.
- **The brain already serves static files.** `api.py` mounts `StaticFiles` twice. Serving a firmware image to
  the LAN is a route, not a project.

## The rules this inherits

These are `docs/updates.md`'s, not new, and they are what stops this from becoming a second and weaker way into
somebody's house. Restated only where a puck changes what they mean.

- **Nothing installs that the maker's key did not sign.** The puck image belongs in the existing signed
  `release.json`, by SHA-256, alongside the container digests. **One trust anchor per house, not two.** A second
  signing path for firmware would be a second thing to get wrong and a second key to lose.
- **An update that does not come back is undone by the hub, not by a person with ssh.** On a puck this is not a
  nicety. A household's repair tool is the wall; a puck behind a sofa running an image that cannot reach Wi-Fi
  is not repairable by anyone who lives there.
- **Works with the internet down.** The puck pulls from the hub over the LAN. The hub is where the manifest was
  already verified, so a house with no internet updates its pucks exactly as well as one with.
- **A person can always still decide**, and **the house says what it did** — every puck update, refusal and
  rollback is an event, same as the hub's.
- **A refusal is not a failure.** A puck that will not take an image because the hash is wrong is a puck working
  correctly, and must not be drawn as a broken one.

## Two decisions that cannot be taken twice

Everything else here can be rewritten later. These two cannot, because both are fixed at the moment a puck is
flashed over a cable, and correcting either costs another visit to every puck in every house — which is the exact
cost this whole document exists to remove.

### The partition table

A puck flashed under the wrong layout needs a cable to correct.

**For the 16 MB S3 board, which is what ships:**

```
# Name,     Type, SubType, Offset,    Size,      Flags
nvs,        data, nvs,     0x9000,    0x5000,
otadata,    data, ota,     0xe000,    0x2000,
app0,       app,  ota_0,   0x10000,   0x400000,
app1,       app,  ota_1,   0x410000,  0x400000,
spiffs,     data, spiffs,  0x810000,  0x7E0000,
coredump,   data, coredump,0xFF0000,  0x10000,
```

Two things about it matter more than the numbers.

**`nvs` stays at `0x9000`, size `0x5000` — byte for byte where `huge_app.csv` puts it.** That is deliberate and
it is the difference between a cable visit that keeps a puck's identity and one that loses it. A puck's Wi-Fi,
broker credentials, netkey, IV index and sequence number all live in NVS. Re-partitioning rewrites the table,
not the NVS contents, so a puck re-flashed with this layout comes back as itself and does not need adopting
again. Get this wrong and every existing puck has to be re-provisioned by hand.

**4 MB app slots are absurd for a 981 KB image, and that is the point.** The alternative is discovering in two
years that the slot is too small, which costs a cable visit to every puck in every house. The flash is free and
sitting unused. Take it.

**For a 4 MB classic ESP32** (`esp32dev` is still the default env), the stock `min_spiffs.csv` already does this
correctly — same `nvs` offset, `app0`/`app1` at `0x1E0000` each. The 981 KB image fits with room. No custom
table needed; just stop using `huge_app.csv`.

### The keys, whether or not anything checks them yet

`docs/updates.md`'s rule is that a hub never adds a signing key after its first install, because a key arriving
afterwards is exactly the push the signature exists to catch. On a puck the same rule bites harder: there is no
filesystem anyone can reach and no ssh, so a key that is not in the image at the cable visit can never be in it.

That gives this whole question an asymmetry worth its own line:

> The verification **code** can ship whenever. The **keys** cannot.

So both public keys — primary and spare, for the same reason `docs/updates.md` insists on two — go into the image
at the partition visit **even if not one line checks a signature yet**. They cost a few hundred bytes and they are
the difference between *we can add this later* and *we can never add this*.

The corollary is the unpleasant one, and it is the strongest argument against ever turning verification on:
**losing the signing key is worse here than for a hub.** A hub that cannot verify an update still has a filesystem
and an owner with a keyboard. A puck has neither, so a lost key means a cable visit to every puck ever shipped.

## The cable visit that cannot be avoided

**OTA cannot bootstrap itself.** Changing the partition table means writing from `0x0`, which is a cable job. So
every puck that exists today — `c8ebba` and `f4a9f3` in this house — needs one more physical visit no matter how
good the rest of this design is.

That is worth saying plainly rather than engineering around, because the engineering around it is worse. It also
sets a deadline that has nothing to do with software: **every puck flashed between now and the day this lands is
a puck that will need that visit.** If pucks are about to go to anyone outside this house, the partition table
should change before they do, even if not one line of OTA code exists yet. An unused `app1` costs nothing.

## The shape

**Pull, not push.** The puck asks; the hub answers. A hub that pushes needs to know which pucks are awake, retry,
and hold state about each one. A puck that pulls needs a timer.

**The manifest already exists and is nearly right.** `releases/bridge/esp32s3-ship.json` carries `fw`, `sha256`,
`chip` and `commit` — which is exactly what an updater needs, written before anyone was thinking about updates.
What changes is where it is trusted from: the fields move into the signed `release.json` so the maker's key
covers the firmware, and the hub serves the verified result at a LAN route.

**The puck compares and decides.** On boot and every few hours: fetch the manifest from the hub, compare `fw`
and `sha256` against its own, and if they differ, download, verify the hash while writing, and reboot into the
new slot. A puck that cannot reach the hub does nothing, which is the correct behaviour and needs no code.

**Older is not an upgrade.** A hash proves a file arrived whole; a signature proves the maker made it. Neither
proves it is *current*. Nothing else here stops a hub — or something wearing a hub's address — from serving an
older image that was genuinely signed, with whatever was wrong with it still in it. So the puck keeps the highest
version it has ever run in NVS and refuses anything below that. A floor, not a comparison against the running
image: a puck that has just rolled back must not be walked down a second time. A deliberate downgrade becomes a
cable job, which is the right price for something that should be rare and deliberate.

**Where the signature is checked, and the honest limit.** The hub verifies the maker's signature, as it already
does for its own release. The puck verifies the SHA-256 of what it downloaded. That means the puck trusts the
hub — anyone who can impersonate the hub on the LAN and hold the broker credentials can put firmware on a puck.
That boundary is already where it sits today: the hub writes a puck's Wi-Fi and netkey over a cable, so a hub
that is not the hub is already the end of the story. Worth writing down as chosen rather than overlooked.

**But the hash travels on the authenticated channel, not the anonymous one.** The puck already holds broker
credentials the hub wrote at adoption, so the expected `fw` and `sha256` are published to it over MQTT and only
the image itself is fetched over plain HTTP. Something impersonating the hub on the LAN then needs those
credentials before it can name a hash the puck will accept — which closes the cheap attack for no crypto at all.
What it does not close is a hub that has genuinely been taken. That is what a signature is for, and the reason
the keys go in at the first flash even if the checking does not.

On which: it is cheaper than it sounds. **mbedtls does not implement ed25519** — the shipped headers carry
the PSA identifiers (`PSA_ALG_PURE_EDDSA`) and no implementation — but `liblibsodium.a` is already bundled in the
S3 SDK with `crypto_sign_ed25519`, so verification is a link, not a dependency. The cost of this option is not
code. It is the key, and the key is the part that cannot be added later (see *Open decisions*).

## Coming back is the whole feature

The rest of this is plumbing. This part is why it is safe to do at all.

ESP-IDF's rollback exists and must be turned on (`CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE`). A newly written slot
boots **pending verification**; if it is never marked valid, the bootloader returns to the previous slot on the
next reset. The only question a design has to answer is *what counts as valid*, and the wrong answer makes the
whole mechanism decorative.

**Valid is not "it booted."** A puck that boots, joins nothing and bridges nothing is exactly the failure that
strands somebody. The new image marks itself valid only after all three of:

1. Wi-Fi associated and an address held,
2. the broker connected and `status` published,
3. a proxy link up — a switch answered.

Before those, it is a candidate. After a timeout — two minutes is the natural number, since `LINK_DEAD_MS`
already says two minutes of silence means the link is dead — it reboots itself and the bootloader takes it back.

**A power cut mid-download is already safe**: `otadata` is untouched until the image is written and verified, so
a puck that loses power halfway comes up on the old slot with a half-written spare and tries again.

**The lights do not depend on this.** Multi-way in this house is switch to switch, with the hub out of the path
(`docs/brilliant.md`). A puck that fails to come back costs the house its mesh bridge — motion, state, the
panel's view of those switches — but the switch on the wall still turns the light on. That is the difference
between an embarrassment and an emergency, and it is worth keeping true.

## One puck first

The hub's rollout rules apply with more force here, because pucks in one house run the *same* image. An update
that bricks them updates them all into the same hole.

**One puck takes the image. The hub waits until it has been seen healthy — connected, bridging, for a
meaningful stretch, not thirty seconds — before any other puck is offered it.** With two pucks that is barely a
policy; with a house that has five it is the difference between one dark corner and a dead mesh.

**At night, like the hub**, and not while somebody is using the thing it bridges. A reboot is thirty seconds of
a deaf mesh, which at 7pm is a light that did not come on when someone walked in.

## Failure modes

| What happens | What the house sees | What it costs |
|---|---|---|
| Hub unreachable when the puck checks | Nothing | Nothing. It checks again later |
| Hash mismatch | A refusal in the log, not a failure | Nothing. The puck stays on its image |
| Power lost mid-write | Nothing | One retry. `otadata` never moved |
| New image boots but cannot reach Wi-Fi or the broker | Puck offline for ~2 min, then back on the old image | A gap in the log. Self-healed |
| New image is healthy but subtly wrong | Nothing automatic catches it | The same as today: somebody notices. Rollout-one-first bounds it to one puck |
| Partition table wrong at flash time | Nothing, until an update is needed | A cable visit to every puck. This is the one to get right |

## Open decisions

- **Does the puck check a signature itself?** Recommended: not in the first version — the MQTT-delivered hash
  covers the attack that is actually likely — but **the keys go in at the first flash regardless**, because that
  is the half that cannot be deferred. Deferring the code is cheap and reversible. Deferring the keys is neither.
- **How often does a puck ask?** On boot, and then — six hours matches the hub. There is no reason for them to
  differ and a mild reason to match: one number in one place.
- **Does a puck ever refuse to run an old image?** `docs/updates.md` leaves the same question open for the hub.
  The answer should be the same for both.
- **Where the LAN route lives**, and whether it is the brain's FastAPI or caddy. Uninteresting, and deliberately
  so — the signature is what makes the path not matter.
- **What the panel says while a puck is updating.** Probably nothing, which is the correct amount for a
  30-second reboot at 3am, but it should be a decision rather than an oversight.

## What this does not change

`docs/updates.md` is untouched — this extends it to a second kind of thing in the house and borrows its key, its
manifest and its rules whole. The adoption flow in `brain/hub/bridge.py` is untouched: a bare board is still
flashed over a cable, and that remains the only way a puck gets its first image. What changes is that it stops
being the only way it ever gets another.
