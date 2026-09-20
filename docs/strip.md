# A light strip: what is built, and what is still a claim

*Written 20 September 2026, from "what's the possibility of building an ESP32-controlled RGB/RGBW strip for
accent lighting". The answer turned out to be that two thirds of it already existed in this tree, and the
interesting part was not the electronics. The design is settled and drawn (`design/strip/`, `design/occasion/`);
the brain, the panel and the firmware are written and their suites pass. The firmware is a **Matter device**,
which was decided on 20 September before anything shipped and is the subject of its own section below.
**First bring-up was 20 September and the light driver is now proven on silicon** — see below for exactly how
much of it, which is less than all of it. The honest list of what is not built is at the foot, where it is
meant to be read.*

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

    knocking   it has power and is advertising itself as commissionable. Nothing of the house's has moved
    working    onto the Wi-Fi, then found. Two steps, not the bridge's three -- the software is already on it
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

The same reasoning decides what happens when the Wi-Fi goes. It does **not** reopen a commissioning window: a
router reboot would otherwise make every strip in the house advertise itself at once, several times a year,
with nobody present and nobody told. It keeps its light and stays quiet. **Since Matter came in, retrying the
Wi-Fi is `esp-matter`'s job rather than ours** — the hand-rolled ring of two credentials went with the
hand-rolled provisioning, which is one fewer thing of ours to be wrong. Coming back needs a deliberate act.

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
| `strip/firmware/` | pixels, RMT, Matter commissioning and an Enhanced Color Light, MQTT for the instruments |
| `strip/firmware/test_pixels_native.cpp` | all six orderings, checked against the brain's arithmetic |

Brain 1090 tests, panel 490, `vue-tsc -p tsconfig.app.json` clean, `lint:css` no errors. `pio run` succeeds for
`esp32s3` and `esp32dev` from one source.

**The part and why.** The S3 is the default: BLE 5.0 with better coexistence — which matters because this
streams frames *and* holds a recovery channel — a more mature secure boot and flash encryption, native USB
that takes the UART bridge chip off the board, and it is the same part as the puck so one toolchain covers
both. A classic ESP32 does everything in the ambient product perfectly well and is a fine thing to prototype
on; it is simply the oldest part in the family to start a multi-year product on.

## Matter, and why it was done before anything shipped

**A strip we make is a Matter device in its own right.** Commission it with any hub — Apple Home, Google Home,
Alexa, SmartThings — and it is a color light: on, off, dim, any color, any warmth, in whatever app the
household already has. Nothing of ours needs to be in the house.

That is worth having on its own. It is not why it was done now.

**It was meant to replace something that was wrong**, and on this framework it does not. The first firmware
provisioned itself over a hand-rolled BLE characteristic, which sent the household's Wi-Fi password over an
unauthenticated link. Matter's own commissioning is PASE with SPAKE2+ and then CASE, so adopting it was meant
to close that hole and buy four ecosystems in the same move.

> **CHIPoBLE IS COMPILED OUT OF THE ARDUINO FRAMEWORK.** `CONFIG_ENABLE_CHIPOBLE is not set` in the
> precompiled libraries for **every** target — esp32, c3, c6 and s3. So a device built this way can never
> advertise itself for BLE commissioning: it has to be **on the Wi-Fi already**, and the commissioner finds it
> by mDNS. That is why every Arduino Matter example hardcodes `WiFi.begin(ssid, pass)` — not laziness, a
> requirement. Found on 20 September by scanning for the advertisement and not finding it, after the stack
> itself reported `fabrics 0, commissioning window OPEN`.

So Matter gets us the ecosystems and **does not, here, get us secure provisioning**. Something still has to put
the strip on the Wi-Fi first. The answer is `WiFiProv`, which ships in the same core: BLE transport, protocomm
`SECURITY_1` (X25519 then AES-CTR, with a proof of possession), which is the handshake that was wanted in the
first place. It is not written yet.

### The two numbers that made it urgent

|  | flash |
|---|---|
| the bespoke-BLE firmware | 942,869 bytes |
| the same firmware as a Matter device | **1,759,998 bytes** |

`min_spiffs.csv`, which it was on, has 1,966,080-byte app slots. Matter would have fitted at **89.5 % with
nothing left to grow into**, and that table has no `esp_secure_cert` or `fctry` partitions at all — so a
*certified* unit, which needs a per-device attestation certificate written at manufacture, could not have
existed on it.

**A partition table is the one thing an update cannot change.** An update writes the other app slot and flips
`otadata`; it cannot move the slots. A unit shipped on the old table could never have become a Matter device,
and the household would have had to send it back. `partitions-matter.csv` gives 3.75 MB a slot on an 8 MB part
and lays down the two certification partitions now, while they cost nothing.

The bridge puck already learned the shallow version of this: it shipped once on `huge_app.csv`, which has one
app slot, so it could never be updated remotely at all.

### What Matter cannot say

The Enhanced Color Light cluster is on/off, level, hue, saturation and color temperature — **one color for the
whole fitting.** It has no concept of a pixel. So:

| | |
|---|---|
| the ambient product | entirely Matter. Any hub, no code of ours |
| the order and fill questions | ours, over MQTT |
| spatial occasions, following a picture | ours, and always will be |

That is the same split Hue and Nanoleaf run, and it is not a compromise. **A strip with no broker in its NVS
simply does not do the second half and is none the worse for it** — which is exactly the strip somebody buys
in a shop.

### What it cost

The core had to move from Arduino 2.0.17 to 3.2.1 (the pioarduino build, which `brilliant/esp32-bridge`
already reaches for when it wants a C6), because the Arduino wrapper for `esp-matter` arrived in 3.x. That
rewrote the RMT driver against the new API and deleted NimBLE entirely — Matter owns the Bluetooth radio now,
and a second BLE stack in the image was both wasted flash and a second thing that could hold the radio.

Reworking the RMT driver caught a real bug on the way past. The first version built symbols eight bytes at a
time and called `rmtWrite` per block; the gap between two of those calls is whatever the scheduler feels like,
and a gap over about 50 µs is precisely what a WS2812 reads as *end of frame*. It would have looked correct at
30 pixels and torn at 300.


---

## What is not built, and what is not safe yet

Everything under this line is honest. None of it is done.

**1. NOT closed after all — the Wi-Fi password still has no safe way across.** This was written down as closed
when Matter came in, and hardware says otherwise: CHIPoBLE is compiled out of the Arduino framework on every
target, so Matter cannot carry the credentials and something else must. `WiFiProv` with BLE and protocomm
`SECURITY_1` is in the same core and is the intended answer; nothing is built. **Until it is, a strip can only
be put on the Wi-Fi by a method that does not exist yet, which is also why nothing can be commissioned.**

**1a. But nobody can commission it yet.** A commissionable Matter device advertises its discriminator; it does
**not** advertise its passcode, and commissioning cannot happen without one. So the hub cannot silently adopt a
strip the way `design/puck/Knock.dc.html` argues for — **that board's proudest claim, that the identity check is
the object and never a number, is now in tension with the standard.** Options, none chosen: put the code in the
box like every other Matter device and accept that our own panel is no better than anyone else's; derive
passcodes at manufacture from something the hub can look up, which makes every unit we sell commissionable by
anybody holding our algorithm; or an NFC tag the phone reads. **This is an artboard conversation before it is a
code one, and it has not been had.**

**2. The hub cannot actually drive the firmware.** `Radio.join()` raises. The firmware is commissionable; the
brain has no commissioning client and does not talk to `matter-server` at all yet. So the two halves have never
spoken. `Radio.scan()` still matches on our own name prefix rather than the Matter commissionable service, for
the reason in 1a.

**2a. Nothing decides how a strip learns our broker.** After commissioning it is on the house Wi-Fi and knows
nothing about us; `mhost` in its NVS is blank, so it is a plain Matter light and the color and length questions
never get asked. Handing those details over needs either a route on the hub or a custom Matter cluster, and
neither is designed. **This is the seam between "a Matter light anybody can buy" and "a light our hub set up
properly", and it is currently an empty string.**

**2b. Certification, which is what "just works" actually costs.** Everything above runs on a *test* vendor id.
Apple and Google will commission such a device with an "uncertified accessory" warning; it cannot be sold.
Shipping needs CSA membership and a real Vendor ID (the Adopter tier is roughly $7k a year — verify before
planning around it), a Device Attestation Certificate provisioned into `esp_secure_cert` on **every unit** at
manufacture, and certification testing per product at an authorized lab. The partitions are laid down for it.
Nothing else is.

**3. Some of it has run on hardware now, and this is exactly how much.** An ESP32-S3 on 20 September lit a
WS2812 through red, green, blue and white in order, then held the waiting glow. That settles the RMT driver,
the WS2812 timing, MSB-first bit order, the one-write-per-frame frame shape, and `Order::bytes` agreeing with
the brain about `grb` — a real strip lights, in the right colors, from this code.

Everything past that light is still a claim. Nothing has been commissioned, no ecosystem has seen it, the
broker has never been spoken to, and neither the color question nor the fill has run outside a unit test.

**Three bugs came out of that one evening, and none of them could have been found any other way.** The waiting
glow was drawn and then wiped a fraction of a second later, when Matter synced its light's off state through
our own callback — indistinguishable from never lighting. The frame buffer was claimed for the longest strip
anybody could attach, 60% of free heap, where it would have failed or starved Matter later. And the glow was
lit with the panel's own accent copied out of the palette, which came out **white**, which is precisely what
`AGENTS.md` says a pastel does on an emitter and why it says never to do it. That one cost an evening of pin
swapping, because an identity light that is white and an identity light that is broken look identical on a
bench.

**And one non-bug worth recording**: the first dead strip was a power problem, not a pin. The driver had been
right the whole time, which is what the self-test (`-e esp32s3-selftest`, no wiring, fifteen seconds) exists to
establish before anybody starts swapping pins.

**4. `esp32c3` is unverified** — the RISC-V toolchain on the machine this was written on is the wrong
architecture and would not run. The environment is in `platformio.ini` and has never been built.

**5. The strip is not placed in a room properly.** `Strips.put()` calls `hub.strip_placed()` behind an
`AttributeError` guard, and there is no such method. The room is recorded on a retained topic and the light
appears through Home Assistant discovery; making it a first-class device the brain has placed is not done.

**6. The pane rows are half built, and the join is now known but unproven.** Asking either question again
is done: `Strips.revisit()`, `GET /strip/list`, `POST /strip/revisit`, and the sheet says a different sentence
for a question asked a second time. What is missing is the **entry point** — the two rows on the light's own
pane that `design/strip/Later.dc.html` draws — which needs the panel to know that a given light *is* one of
our strips.

The first commissioning answered what that join cannot be. Home Assistant reported **manufacturer
`TEST_VENDOR`, model `TEST_PRODUCT`** — esp-matter's defaults for a test vendor id, identical on every device
anybody builds this way, so neither field distinguishes one of our strips from another or from somebody else's
weekend project. Real vendor and product names arrive with a real Vendor ID and not before (see 2b).

So the join is the **serial number**, which we can set without buying anything: the firmware now stores the
chip there at boot, which is the same id the strip publishes all its MQTT topics under. **Unproven** — it is
stored after the Basic Information cluster has already been built, so the first boot after a flash still
reports the default and the one after it should be right. Nobody has looked yet.

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
