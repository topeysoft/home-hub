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

## Built, 24 September 2026: the first version

The routine tier is written, both halves. What exists:

- **The puck** (`brilliant/esp32-bridge/src/fwupdate.{h,cpp}`, firmware 0.6.0). Takes a retained offer on
  `<base>/bridge/<chip>/offer` -- version, size, SHA-256, port, path -- fetches the app from the address
  the broker last answered on, hashes it while writing, and restarts into it. The new image is on trial
  for three minutes and confirms itself only with Wi-Fi, broker and a proxy link all up; otherwise it
  asks the bootloader to take it back. It keeps a floor (the highest version it has confirmed) and gives
  up on a version that came back twice. It publishes `fw` retained on every connect, and `update` with
  what it did. The bootloader already on 0.3.x pucks was built with rollback on, so nothing about the
  boot side needs another visit.
- **The hub** (`brain/hub/bridge_updates.py`). Cuts the app out of the merged image by the partition
  table inside it, serves it at `/bridge/firmware/<sha>.bin` and nothing else, and offers it to one
  behind, online puck at a time in the hub's own part of the night (`Updates.quiet_hours`), only where
  the household lets the hub update itself. Offers are withdrawn on success, on failure, after fifteen
  minutes, and at the end of the window. Updated, went back, and refused-by-hash are written down.
- **The open decisions, as taken:** the puck checks the hash, not the signature; the hub's six-hour
  clock and night window, not a second one; the route is the brain's. The image rides inside the brain's
  container, which the host verifies against the maker's key, so there is still one trust anchor.

Not built: the important and critical tiers (`urgent` is still not carried), the *Needs a look* line
for a puck that went back twice or could not be reached, and the morning card's line. **And 0.3.x cannot
take an update** -- it has the slots and the keys but no code to use them -- so every puck still on it
needs one cable visit to 0.6.0 (`c0e33a` in this house has had its, below) (`puck_cable.py <port> upgrade`, which
keeps its identity). That is the last one.

**Proven on `c0e33a`, 24 September**, at a desk, against the house's own broker, with the images served
from the hub's address by a stand-in server (the running brain predates the route). Cable to 0.5.0 by
writing only otadata and the app: identity, Wi-Fi and mesh kept. Offered 0.5.1: fetched, restarted in
eleven seconds, confirmed itself inside its trial. Offered a 0.5.2 built never to confirm: on trial at
10:14:57, back on 0.5.1 by the bootloader at 10:17:57, said `rolledback 1`, tried once more, back again
at 10:21:48, said `rolledback 2`, and has refused it since with `came back twice`. Two fetches in the
server's log, not three.

**A working-tree build, now, for a hub being worked on.** `tools/dev.sh puck <chip>` builds this
checkout's firmware as `BRIDGE_FW-d<minutes>`, parks it in the brain's data over ssh, and follows
what the puck says. The hub offers it at once, day or night, and only if it follows a branch; a
release hub refuses. A tagged build sorts after the release before it and before its own
(`0.6.0 < 0.6.1-d384085 < 0.6.1`), so `BRIDGE_FW` names the *next* release from the moment the last
one is cut, and a puck used for development still takes the real thing. A 0.6.0 puck reads only the
three numbers, which is enough for its first test build to be newer.

**Which is why the first release is 0.6.0, not 0.5.x.** That puck's floor is now 0.5.1 and 0.5.2 is
marked bad on it, so a release numbered anything up to 0.5.2 would be refused as older, or as the
image that came back twice. A bench test on a puck in a wall leaves marks like these; a bench board
does not.

## What was true on 18 September 2026

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

Getting them into the image is less automatic than it sounds. A `const` array that nothing reads is folded away by
the compiler and then collected by the linker, and the build succeeds either way — an image with no keys in it looks
exactly like an image with keys. `tools/puck-keys.py` marks them `volatile` so every read is a real load, and the
proof is not the build output but searching the built binary for the key bytes.

The corollary is the unpleasant one, and it is the strongest argument against ever turning verification on:
**losing the signing key is worse here than for a hub.** A hub that cannot verify an update still has a filesystem
and an owner with a keyboard. A puck has neither, so a lost key means a cable visit to every puck ever shipped.

## The cable visit that cannot be avoided

**OTA cannot bootstrap itself.** Changing the partition table means writing from `0x0`, which is a cable job. So
every puck that exists today — `c8ebba` and `f4a9f3` in this house — needs one more physical visit no matter how
good the rest of this design is.

**Keeping `nvs` where it is is necessary and not sufficient.** `releases/bridge/esp32s3-ship.bin` is a merged image
starting at `0x0`, and `merge_bin` pads the gaps between the pieces with `0xff` — one of which is `nvs` at
`0x9000..0xe000`. esptool erases before it writes, so flashing that image at `0x0` onto a puck that is already
somebody's erases its Wi-Fi, broker credentials, netkey, IV index and sequence number, and it comes back blank.
Harmless for the bare boards `brain/hub/bridge.py` flashes; wrong for every puck that already exists.

So the visit uses `brilliant/tools/puck_cable.py <port> upgrade`, which puts the image down in two pieces and steps
over the gap — `0x0..0x9000`, then `0xe000..end`, both edges 4 KiB aligned because that is the erase granularity.
It refuses to run if the partition table has moved `nvs`, and afterwards it checks the puck came back `set` rather
than blank. A puck that has forgotten itself is exactly what this guards against, and it should be found on a bench
rather than in a hallway.

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
new slot. A puck that cannot reach the hub does nothing, which is the correct behavior and needs no code.

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

## When it cannot wait: a fix that has to reach a puck already in a hallway

*Added 19 September 2026, from the question this document did not answer: everything above describes a puck
quietly catching up at three in the morning. What happens when a fix cannot wait for three in the morning, and
the puck it is for is behind somebody's sofa?*

The honest starting point is that **a household does not have pucks.** They have switches in a hallway that work.
The word "puck" appears nowhere on the panel today and should not start appearing because the maker has a
firmware problem. Everything below follows from that: what the house says is about the hallway, never about a
version number, and the only time a person is interrupted is the one case where a person is the only thing that
can help.

### Three tiers, and only one of them is allowed to interrupt

**Urgent is a property of the release, not a guess by the hub** — `docs/updates.md`'s rule, and the same field.
A release either says `urgent: true` about its puck image or it does not.

| | When it goes | What the household sees |
|---|---|---|
| **Routine** | The night window, one puck at a time | Nothing. At most a line in the morning's *What's new*, if the fix changed something they would notice |
| **Important** | The next quiet moment, not the next window | Nothing at the time. A line under *This hub* for whoever goes looking |
| **Critical** | Now, quiet moment or not | Said before, and said again when it is done |

Two rules hold across all three and are worth stating because they are what stops "critical" becoming a habit.
**Even a critical fix goes to one puck first** — a bad image that bricks one puck is a dark corner, and the same
image on all five is a dead mesh, which is a worse outcome than the bug being fixed. The wait shrinks; it does
not vanish. And **the household's switch still wins**: a house that turned automatic updates off is nudged
harder and told why, not overruled. A maker who can overrule that switch does not really offer it.

### What it says while it is happening

The answer to the open decision above, which asked whether the panel says anything at all: **nothing for a
routine one, and for a critical one the words a restart already uses**, because it is the same event — thirty
seconds of a deaf mesh — and a household reading two different accounts of it learns that the panel guesses.
`restart.py`'s vocabulary, unchanged:

- **Keeps:** *The switches on the wall keep working.* Always true, and the first thing said. Multi-way in this
  house is switch to switch with the hub out of the path (`docs/brilliant.md`), so a puck rebooting costs the
  house its view of those switches and not the use of them.
- **Stops:** *Motion and the panel's view of those switches pause for about a minute.* Said because it is true,
  and because a household whose panel has stopped showing the hallway lights will otherwise assume the hallway
  lights are broken — the mistake `health.bridges()` already exists to prevent.
- **How long:** measured, not guessed. `restart.py` learns `restart_took` per rung from the house it is actually
  in; a puck's reboot is the same number wanted for the same reason.

### The case this section exists for: it cannot reach the puck

This is the interesting failure and the one a good design is judged on. A critical fix is published, the hub has
it, and one puck is unplugged, moved, on a socket somebody switched off at the wall, or out of range since the
Wi‑Fi changed. The fix cannot land, and **nothing in the mechanism above will ever make it land**, because the
recovery is a walk to a socket with a puck in your hand.

`health.bridges()` already says exactly this shape of thing, and its comment is the design rule verbatim:

> THE RECOVERY IS IN THE TEXT AND NOT IN A BUTTON, because it is a walk to a socket with a puck in your hand and
> there is no tap that performs it.

So a critical fix that has not reached every puck becomes a *Needs a look* line built the same way, with the
same three parts in the same order:

1. **The name a household has for it** — `bridge.room_of()`, already written: *The hallway bridge*. Never a chip
   id, and never "a puck". Where the hub cannot honestly name the room it says *A bridge*, and does not guess.
2. **The reassurance, first** — *Its switches still work on the wall.*
3. **What is actually missing, in effect** — *It is missing a fix for <the release's own sentence>.* The notes
   already exist (`releases/*.md`, `what:`); a puck fix writes its line in the same file and this reads it. No
   second notes system, and nothing that mentions firmware.
4. **The walk** — *Plug it into the hub for a minute and it will catch up.* In the text. The only button is the
   one `health.bridges()` already offers: agree the thing is gone for good.

### The counting is the feature

The failure that actually costs a household is not an update that fails loudly. It is **a house that believes
every puck has the fix when one does not.** So the house counts, out loud:

> *Two of your three bridges have the fix. The hallway one hasn't been heard from since Tuesday.*

And the line **stays** until the count is whole. It does not clear on a tap, it does not clear because somebody
read it, and it does not clear at midnight — the rule the rest of the panel already keeps: nothing vanishes
under a tap, and only the fact changing clears the line about the fact. A critical fix that reached three of
four pucks is not a finished job, and a panel that says nothing about the fourth is a panel that lied by
omission.

### Coming back, and saying so afterwards rather than during

A puck that takes the image and cannot get back on the network rolls itself back inside two minutes, by the
bootloader, with nobody watching. The panel should say **nothing while that is happening**: a fault reported at
3:01am and self-healed at 3:03am is a fault the household reads about over breakfast and walks to a hallway to
investigate, finding it fine. That is how a panel earns the reputation of crying wolf.

What is worth saying is the pattern. **A puck that rolled back twice has stopped being a puck that was unlucky**,
and that is a *Needs a look* line naming the room — the same escalation `restart.py` makes when the same rung
has been tried three times in an hour and has stopped being the answer.

### The morning after

The hub's own updates land overnight and are read the next morning on one dismissible card (`docs/updates.md`
piece 4). A puck fix belongs on the **same card**, in the same sentence about the house, and not on one of its
own. *What's new* is a thing a household reads; it is not a changelog per component, and a second card about a
part of the system they have never heard of is how the first card stops being read.

### What this adds to the mechanism above

Nothing structural. It needs `urgent` carried from the signed release to the puck manifest (the field
`docs/updates.md` piece 3 wrote down and did not build), each puck's running version compared against the
shipped one — which the hub already has, in `settings["bridges"][chip]["fw"]` and
`releases/bridge/esp32s3-ship.json` — and `health.py` to grow a second bridge line beside the one it has. The
detection half is buildable today, before one line of OTA exists, and is worth having on its own: a hub that can
say *the hallway bridge is behind, and here is what it is missing* is more useful than one that cannot, even
while the only cure is a cable.

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
- ~~**What the panel says while a puck is updating.**~~ **Decided, 19 September 2026** — see *When it cannot
  wait* above. Nothing for a routine one; a restart's own words for a critical one; and the only line that
  interrupts anybody is the one naming a puck the fix could not reach, because that is the only one a person can
  do anything about.

## What this does not change

`docs/updates.md` is untouched — this extends it to a second kind of thing in the house and borrows its key, its
manifest and its rules whole. The adoption flow in `brain/hub/bridge.py` is untouched: a bare board is still
flashed over a cable, and that remains the only way a puck gets its first image. What changes is that it stops
being the only way it ever gets another.
