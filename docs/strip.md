# A light strip: what is built, and what is still a claim

*Written 20 September 2026, from "what's the possibility of building an ESP32-controlled RGB/RGBW strip for
accent lighting". The answer turned out to be that two thirds of it already existed in this tree, and the
interesting part was not the electronics. The design is settled and drawn (`design/strip/`, `design/occasion/`);
the brain, the panel and the firmware are written and their suites pass. **Nothing in here has run against a
real strip.** Every claim below about how it behaves on hardware is a claim, and the honest list of what is
not built at all is at the foot, where it is meant to be read.*

## What it is, and what it is not

A light strip you buy in a box, tape behind a television or under a shelf, and plug into a socket nowhere near
the hub. Warm, on, any color, and then forgotten about. That is the whole of the first product.

**Following the picture on the television is a different product line and is not started.** It needs a box in
the AV path, HDCP licensing, and a household willing to let something sit between their sources and their
screen — see the foot of this document. The ambient strip does not wait for it.

## The shape, and why it is short

A strip is the first thing this house adopts that is neither a bridge nor already in a wall. It could have
needed a whole new flow. It does not: **four of its six beats are the arrival sheet the panel already ships**,
including the words. `design/strip/Spine.dc.html` is mostly a demonstration of that.

    knocking   it has power and is advertising. Nothing of the house's has moved
    working    wifi, then hub. Two steps, not the bridge's three -- the software is already on it
    order      which color comes out first
    length     how far it goes
    room       the ordinary room chips every new device gets
    ready      an ordinary light from here: the tile, the colors, the schedules, "everything off"

Two beats a bridge has fall away. There is no mesh, so no keys step. And there is no walk to find it a socket,
so the placing instrument — blinking amber, steady green, breathing red — has nothing to answer.

**It never goes to the hub on a cable.** It leaves the factory flashed and knocks over Bluetooth. That is
`design/puck/Knock.dc.html` direction A, which lost for a bridge on one line — *"it only works on a board that
already has firmware on it"* — and a product we ship is flashed. `docs/puck-hardware.md` left that question
open for the puck; it is answered here for this device class and not for that one.

## The two questions, and the one fact behind both

**Nothing can be read back off a strip.** The data line is write-only on every part in this family. So the
controller cannot discover how long the strip is and cannot discover which order it wants its colors in. Both
are shown, and the household names what it can see — the same move as pressing a switch to say which room it
is in.

**Which color comes out first.** Six orderings are in circulation; WS2812B is `grb` and is most of what anybody
owns. The strip is lit with the three bytes that would be red *if* it is what we guessed, and the household is
asked one yes/no. `brain/hub/strip.py` does that arithmetic and `strip/firmware/src/pixels.h` writes the bytes
out unmapped — putting them through the strip's mapping would be applying the very guess the question exists to
test, which is why the command is called `raw` and not `solid`.

> **One tap is a prior, not a proof.** The first question makes the *second* byte loud, so the channel somebody
> names is the one that byte drives — and that always leaves two orderings standing, never one. "Yes, red"
> leaves `grb` and `brg`, and we take `grb` on its odds. **The row on the light's own pane that asks again is
> therefore not a nicety; it is the other half of this shortcut, and the shortcut is not honest without it.**
> A test pins that the first answer always leaves a pair.

**The fourth answer is the interesting one.** A three-byte frame sent to a strip that carries a separate white
misaligns by a byte a pixel and comes out as a candy-stripe rather than one color. So "stripes of color"
answers *how many channels* with no vocabulary at all, and it needs no special case in the firmware — `raw3`
always strides three and the wire does the rest.

**How far it goes.** It fills from the plug end and somebody taps when the far end lights. A *traveling* light
was the first draft and cannot work: past the real end it is writing to pixels that do not exist, so it simply
vanishes and there is nothing left to tap. A fill stops changing at exactly that moment. **The firmware latches
the position when the stop arrives**, not when the hub gets round to reading a number back — a person's
reaction time is already the error that matters, and adding however busy the Wi-Fi is on top of it would make a
strip measure short on a busy evening and right on a quiet one.

## The light never reports a fault

This is the one place a strip is the opposite of the bridge puck, and it is worth writing down before somebody
copies the table out of `docs/puck-light.md`. A puck that glows while its bridge is down is furniture that
lies, so a fault outranks its light. A strip is behind somebody's television while they watch a film: turning
it amber because the broker blinked is the product breaking, not reporting. **It holds whatever it was asked
for, and the panel carries the fault.**

The same reasoning decides what happens when the Wi-Fi goes. It does **not** reopen a pairing window: a router
reboot would otherwise make every strip in the house start advertising at once, several times a year, with
nobody present and nobody told. It keeps its light, alternates between the two sets of credentials it holds,
and stays quiet. Coming back needs a deliberate act.

## Occasions, and what moves

Raised as "should we do effects — Christmas, festive periods". Three things were hiding under that word and
they belong in three different places (`design/occasion/`):

- **Ambient motion** — still, drifting, candlelight. A property of the light, on its own pane. Three, and there
  is no fourth: each is a way for the color the household already chose to *be*, and none of them takes that
  color away, which is what an effect does.
- **Occasions** — Christmas, Halloween, a birthday. **A chip in the scene bar, not a setting on the strip.**
  Put it on the strip and somebody has to walk to every strip and set each one while the color-capable bulbs
  never join in. Put it in the bar and one tap does the house, with the strip rendering it best because it is
  the only thing with pixels. Two rules came out of drawing it: a light that cannot do color *says so in the
  room* rather than being skipped in silence, and **an occasion turns nothing on that was not already on.**
- **The zoo** — strobe, meteor, fire, rainbow cycle. No.

**None of this is built.** The boards are drawn and argued; there is no code.

## What is built, and what was verified

| | |
|---|---|
| `brain/hub/strip.py` | the machine, radio behind an interface so it tests without hardware |
| `brain/tests/test_strip.py` | 24 tests, one pinning the six beats to the board |
| `brain/hub/api.py` | nine routes, adopt gated by the code like `/bridge/adopt` |
| `app/src/StripSheet.vue`, `StripArt.vue` | the sheet, in `BridgeSheet`'s shell and words |
| `strip/firmware/` | pixels, RMT, BLE knock, the two-key ring, MQTT, HA discovery |
| `strip/firmware/test_pixels_native.cpp` | all six orderings, checked against the brain's arithmetic |

Brain 1090 tests, panel 490, `vue-tsc -p tsconfig.app.json` clean, `lint:css` no errors. `pio run` succeeds for
`esp32s3` and `esp32dev` from one source.

**The part and why.** The S3 is the default: BLE 5.0 with better coexistence — which matters because this
streams frames *and* holds a recovery channel — a more mature secure boot and flash encryption, native USB
that takes the UART bridge chip off the board, and it is the same part as the puck so one toolchain covers
both. A classic ESP32 does everything in the ambient product perfectly well and is a fine thing to prototype
on; it is simply the oldest part in the family to start a multi-year product on.

---

## What is not built, and what is not safe yet

Everything under this line is honest. None of it is done.

**1. The Wi-Fi password crosses Bluetooth without a handshake. This is the one that must be fixed before
anything ships.** The firmware's provisioning is a single write characteristic taking `key=value` lines, which
is readable and works and is *not* secure: the household's PSK goes over an unauthenticated BLE link, and
anything in radio range during setup can read it. The intended fix is ESP-IDF's `wifi_provisioning` with the
BLE transport and **security2 (SRP6a)** — the crypto is done, it is maintained, and the hub side is Python, so
`brain/hub/bridge.py`'s sibling gains a transport rather than a subsystem. The friction is that security2 wants
a proof-of-possession, and the canonical answer is a code printed on the device, which is the number on a
screen that `design/puck/Knock.dc.html` is proud of not having. The intended resolution is the first-boot
window plus the blink confirmation as the proof for the normal path, with a printed code as the recovery and
hardened option — **and that residual risk has not been accepted by anybody yet; it is written here so it can
be.** Until this is done, treat provisioning as a bench convenience.

**2. The hub cannot actually drive the firmware.** `Radio.join()` raises. The firmware advertises and accepts
writes; the brain's `bleak` client for it is not written. So the two halves have never spoken.

**3. Nothing has run on hardware at all.** Not one LED has been lit by this code.

**4. `esp32c3` is unverified** — the RISC-V toolchain on the machine this was written on is the wrong
architecture and would not run. The environment is in `platformio.ini` and has never been built.

**5. The strip is not placed in a room properly.** `Strips.put()` calls `hub.strip_placed()` behind an
`AttributeError` guard, and there is no such method. The room is recorded on a retained topic and the light
appears through Home Assistant discovery; making it a first-class device the brain has placed is not done.

**6. The pane rows are not built.** `design/strip/Later.dc.html` draws them — *Ends here* and *The colors look
wrong* — and item 1 of the color question depends on the second one existing. Drawn, not written.

**7. No updates story.** `docs/puck-updates.md` is about pucks. A strip in a living room has the same problem
and none of the answer.

**8. Occasions and movement.** Drawn in `design/occasion/`, no code.

**9. The hardware is a devkit.** The product board needs, at minimum: a level shifter (**not optional** — a
fill writes every frame, so the bridge puck's write-on-change workaround does not survive here), power
injection and a real 5 V supply sized for the run, a button for recovery and factory reset, and an antenna that
works taped behind a 65-inch television, which is a metal plane. `hardware/puck-revA/` has the shape of this
conversation for the puck; none of it has been had for a strip.

**10. Following the television picture.** Not started, and deliberately a separate product line. The only
universal method puts a box in the HDMI path, which needs an HDCP adopter agreement and HDMI Forum adoption —
real annual cost before a unit ships — and inserts the product into the most quality-sensitive signal path in
the house, which is how these things get returned. The camera route avoids all of that and costs a camera
pointed into a living room. **The cheap next step is neither: a capture stick and HyperHDR on a bench,
to find out whether it feels like the screen extended or like a gimmick, before any of it is paid for.**
