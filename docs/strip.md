# A light strip: what is built, and what is still a claim

*Written 20 September 2026, from "what's the possibility of building an ESP32-controlled RGB/RGBW strip for
accent lighting". The answer turned out to be that two thirds of it already existed in this tree, and the
interesting part was not the electronics. The design is settled and drawn (`design/strip/`, `design/occasion/`);
the brain, the panel and the firmware are written and their suites pass. The firmware is a **Matter device**,
which was decided on 20 September before anything shipped and is the subject of its own section below.
**First bring-up was 20 September and the light driver is now proven on silicon** — see below for exactly how
much of it, which is less than all of it. The honest list of what is not built is at the foot, where it is
meant to be read.*

## Picking this up

*The rest of this document is how it got here, which is worth reading before changing any of it. This section
is where it stands, as of 22 September 2026.*

### Where each piece is

| | |
|---|---|
| **Design** | 27 boards in `design/strip/`, 3 in `design/door/`, 3 in `design/occasion/`, 5 in `design/ears/`. The last row of `design/strip/` is the press and the rung below it; `design/ears/` is how a hub reaches a strip it cannot hear, and it is drawn and unbuilt |
| **Firmware** | ESP-IDF + esp-matter, **commissionable over BLE, proven on an ESP32-S3** |
| **Brain** | both doors: knock → adopt → (press → rhythm | code) → set up. 71 tests. Our door carries the broker |
| **Panel** | the beats including the press, previewable with `?strip=knocking\|press\|rhythm\|working\|ready`; and the two rows a strip adds to its own light pane |
| **Suites** | brain 1137, panel 502, native firmware test, all green |

### What is proven on hardware, and what is not

**Proven:** the RMT driver, WS2812 timing, bit order, `grb` mapping agreeing with the brain, and Matter's BLE
commissioning advertisement — the board says `CHIPoBLE advertising started` and a laptop scan finds it at
−41 dBm carrying a valid commissionable payload.

**Also proven, and this page said otherwise until 20 September:** a commissioning has completed. Home Assistant
took the strip and reported manufacturer `TEST_VENDOR`, model `TEST_PRODUCT`, which is what item 6 is about. The
line here used to read *"never run: a completed commissioning, by anything"*, because this page was written from
item 3 three hours after item 6 had already recorded one. If two parts of this document disagree, date them
against the log before believing either.

**Also proven, 20 September: a phone has taken it.** Apple Home commissioned the strip from the code it now
prints at boot. **It took two fabric slots of the five, not one** — `VendorId 0x1349` (Apple Inc., the local
home hub) and `0x1384` (Apple Keychain, the iCloud admin) — which is worth knowing before promising a household
Apple, Google and Alexa at once, because that is four slots of five before our own hub asks for one.

**And Google Home too**, `VendorId 0x6006`, on a test vendor id and without refusing it — see 2b, which is the
item that claim belongs to. Apple made **two** fabrics on the first pairing (`0x1349` local home hub and
`0x1384` iCloud) and only `0x1384` on the second, so budget two and do not count on one.

**Also proven, 21 September: our own door, on the press.** On an ESP32-S3, with the hub's own client:
a session opened on the public password and was **refused the Wi-Fi** until the button was pressed; a
short press let it through and the Wi-Fi and the broker were handed over together; tapping *It has no
button I can reach* shut the door and reopened it 150 ms later with a freshly minted rhythm; and a wrong
rhythm was refused inside SRP6a. Item 23.

**Never run:** the broker has never been spoken to, neither the color question nor the fill has run outside a
unit test, and Alexa has not been tried. **And no strip has ever joined a real Wi-Fi through our door** —
the bench used a network name that does not exist, so `NETWORK_PROV_WIFI_CRED_SUCCESS` has never fired on
this firmware and the `ours` flag it writes has never been written.

### THE WHOLE THING WORKS, 21 September

**A strip now goes from a box to a light on the wall, in a real house, with no phone and no app.** Knock,
press the button, Wi-Fi and the broker in one session, "Is it red?", the fill, a room, and then a tile
you can switch on, dim and color — with a way back to both setup answers afterwards. Every beat of that
ran on an ESP32-S3 against a real hub and a real broker. Items 23 to 32 are what it cost, and **every
bug past the BLE session was the first time that line had ever run in a house**: the bench had a Wi-Fi
that did not exist, a fake home that was a list, and no broker.

### The next three things, in order

1. **The distance between a hub and a device. Drawn and decided on 22 September; not built.**
   `design/ears/` has five boards and the direction is **A, the bridge puck as an errand runner** — the
   hub hands it a job over MQTT, it does the GATT work, and **the SRP6a session stays end to end**, so
   the puck carries bytes it cannot read and the press gate stays on the strip. Item 33.
   **The first thing to find out is a bench question and nothing should be designed past it:** can the
   puck's ESP32 be a GATT central while it is already a mesh proxy client on the same radio? Nothing
   here has ever tried. Item 15's 13 dB is the same problem measured on a bench; `hardware/` has still
   never had the conversation.
2. **The partial-commissioning bug.** A Matter adopt reported failure on the wall and left a fabric
   behind, which silently bricks a strip until somebody knows the five-second hold exists. Item 24 is its
   cousin and is fixed; this one is not, and neither is the fact that **nothing on the wall ever says a
   strip is spent** — a strip that has completed setup advertises nothing at all, so it looks like a
   strip that is simply not there.
3. ~~**A button, reachable, on the outside of every product**~~ — **written down, 22 September**, in
   `hardware/README.md`, which is the page `hardware/` never had. Item 35. It also turned up the one
   thing to get right on the strip's product board, which does not exist yet: the firmware's
   `BUTTON_PIN` defaults to **0**, and GPIO0 is BOOT, a strapping pin, and the line the USB bridge's
   auto-reset pulls from DTR.

**And the decision that was waiting is taken:** the three setup commands are no longer retained, and
the strip retires a retained one rather than obeying it. Item 33. **It is written and it has not run on
a board** — no ESP32 was plugged into the machine that wrote it.

### Decided, and not to be reopened without a reason

- **Our ecosystem first; Matter is kept, dormant, and gates nothing** (21 September). The strip stays a Matter
  device because it is proven and costs ~3 KB, but certification is off the table indefinitely and nothing is
  designed around it. A household reaches the strip through our own door (`Ours`); Apple, Google and Alexa
  reach it through the hub's bridge (`docs/matter.md`), not through the strip's own Matter stack. So `CodeHub`
  is parked — the bridge opens commissioning windows, not the strip — and the fork stays as a fact of the
  firmware rather than a product promise. Selling a certified unit remains possible later because the
  partitions and the Matter lane are already there.
- **The proof of possession on our door is a press on the button** (21 September, `design/door/PressIt.dc.html`,
  item 23). Nothing printed, nothing to count, nothing derived from the chip — and it needs no light, so it is
  the same gesture on a sensor as on two metres of strip. The gate is on the strip and not on the hub.
  **`PopLight` is demoted rather than deleted:** it is the rung below, reached only by tapping *It has no
  button I can reach*, and it keeps a real SRP6a secret for a strip already mounted out of arm's reach.
  `PopWindow` may exist only behind a build flag for the bench, never in a release; `PopBox` was not chosen
  because its one argument — the label has to exist anyway — only holds if Matter ships first.
  `design/door/ShowMe.dc.html` is the rung the door canvas names for out-of-reach things and it stays drawn
  and unbuilt: for a strip it would move the gate onto the hub.

- **How a hub reaches a device it cannot hear: the bridge puck runs the errand** (22 September,
  `design/ears/`, direction A). Whatever hears the strip is a courier and nothing more: the hub opens the
  SRP6a session, the strip closes it, and the press gate stays on the strip. Build the hub's question as
  *who can hear this*, so `Anyone` — every powered thing of ours answering, and the hub asking the
  loudest — is only a longer list later rather than a second design. `InHand` (the wall over Web
  Bluetooth) stays drawn and unbuilt, the way `design/door/ShowMe.dc.html` is: it is the record of why
  the wall is not the radio, and its three preconditions are all false here today.
- **Nothing a strip is told is retained** (22 September, item 33). The device's own NVS is the memory.
- **ESP-IDF, not Arduino.** Arduino compiles Matter-over-BLE out on every target; a strip built that way cannot
  be set up by Apple or Google at all. Evidence both ways is in this document.
- **The partition table** (`partitions-matter.csv`), sized for Matter with the certification partitions laid
  down. An update cannot move slots, so this one could not wait.
- **The length question:** the fill at setup, the trim row afterwards. `design/strip/Later.dc.html`.
- **Occasions are a scene-bar chip, never a strip setting.** `design/occasion/`.
- **Two tiers:** it works anywhere, and better in a house with our hub. `design/strip/Tiers.dc.html`.

### Open, with boards to argue from

- **Where the setup code comes from** — `CodeBox` / `CodeMade` / `CodeTap`, and now `CodeHub`. `CodeBox` for
  the box, because `CodeMade` fails certification and `CodeTap` cannot stand alone; `CodeHub` for a house with
  our hub in it, where the strip mints a code for one window and the wall shows it. The two are not rivals — see
  item 1a. **Not urgent:** a development board's passcode is public and the brain fills it in, so nothing is
  blocked until real units are labeled.
- **How a strip finds our hub** — `ReachTold` / `ReachAsks` / `ReachNone`. Recommendation was `ReachAsks` for
  strips we commission, `ReachNone` as the fallback for strips somebody else did. **The forked row has largely
  overtaken this:** a strip that came through our own door is handed the broker during that handshake, and a
  strip somebody else set up is reached over mDNS afterwards (`Theirs`), which is better than `ReachNone`. What
  is left of the question is only the strip we can never reach at all. The three boards stay for the record.

### Traps that have already cost a day

- **Matter commissioning cannot be tested on the Mac.** Item `2-mac`. Read that before starting any container.
- **The Command Line Tools on that machine are broken** — no C headers in any SDK, and a corrupt default SDK.
  Every native build used `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer` to borrow Xcode's.
  `sudo xcode-select -s` fixes it properly.
- **Two PlatformIO cores are installed** and fight over the build directory; builds fail and then succeed
  unchanged. Irrelevant now the firmware is ESP-IDF, but it will confuse anybody touching `brilliant/`.
- **A failed setup used to leave a strip that could never be set up again.** Item 24, and the brain
  described it with the wrong sentence for an hour because the exception had no message.
- **The build cache keeps a `-D` from a session nobody remembers**, so read the `pin N` in the boot line
  before believing anything about the light. Item 21.
- **`network_prov_mgr_deinit()` from the `NETWORK_PROV_END` handler deadlocks silently** and takes the
  housekeeping loop with it. Item 22, and it was in the shipped code before the press was.
- **Two things a protocomm transport must do that no header says.** Both cost an evening on
  21 September and both look like "failed to initialise session" at the client. **One:** SECURITY_2
  refuses every message until `protocomm_open_session` has been called for that connection —
  *"Invalid session ID:1(expected -1)"* — and the reference transport does it from the GAP connect
  event, which CHIP owns, so ours opens it on the first write instead and closes it on
  `kCHIPoBLEConnectionClosed`. **Two:** NimBLE serves a long read as several callbacks with rising
  offsets, so an answer freed after the first read is an answer cut off at the MTU. SRP's public key
  is about 400 bytes, so the handshake broke every time and the log's last word was *"Using salt and
  verifier to generate public key..."*. Keep each answer until the next write to that characteristic.
- **A 31-byte scan response makes the strip vanish from scanners — the whole advertisement, Matter's
  included.** The spec allows 31 and CHIP accepts 31; at 31 nothing found the board, at 30 everything did,
  name included. `prov.cpp` caps at 30 on purpose. Also: Espressif's provisioning app finds devices by name
  prefix (`PROV_`) and shows nothing without one, which is the only reason a name is in the scan response.
- **`pdMS_TO_TICKS` of anything under one tick is zero, and `vTaskDelay(0)` does not sleep.** The tick here is
  100 Hz, so the housekeeping loop's `pdMS_TO_TICKS(5)` was 0 ticks; `vTaskDelay(0)` yields only to tasks at
  the same priority or above and never to the idle task at 0. The loop was a busy spin that starved IDLE0 and
  tripped the task watchdog every five seconds — found on 20 September only because an uncommissioned board was
  left running long enough to print it twice, and invisible on a commissioned one in the same session. Fixed to
  10 ms. Any delay under 10 ms in this firmware silently means *do not sleep at all*.
- **`idf.py -D<anything> build` re-runs CHIP's GN build, and GN needs esp-matter's own environment.** Sourcing
  `esp-idf/export.sh` alone is enough for an ordinary rebuild and not enough for a reconfigure; the failure is
  `Unable to load "/build_overrides/pigweed_environment.gni"`, which names pigweed and has nothing to do with
  whatever you passed on the command line. Source `esp-matter/export.sh` too.
- **`SELFTEST` is a CMake cache variable, so it stays on until it is explicitly cleared** — `idf.py -DSELFTEST=`
  with an empty value, because `-DSELFTEST=0` still satisfies the `#ifdef`. A build dir configured for the
  bring-up self test keeps self-testing forever, and until 20 September the test left `strip.count` at 1
  afterwards, so the board lit exactly one LED however long the strip really was. On a board somebody has just
  paired that reads as a broken strip rather than as a self test that forgot to put something back.
- **The error text on the wall lied four times in a row** during bring-up, each time naming a confident wrong
  cause. If a strip screen tells you what is wrong, verify it before acting on it, and see item 11.

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
the strip on the Wi-Fi first, and that is now `WiFiProv` from the same core: BLE transport, protocomm
`SECURITY_1` — X25519 to agree a key, then AES-CTR, with a per-device random proof of possession so being in
radio range is not enough. The handshake that was wanted in the first design conversation, before Matter looked
like it would do the job for us.

**Built and seen on air, 20 September**: `hub-strip-58422e` at −45 dBm carrying the protocomm service. It
advertises under the same name `Radio.scan()` in the brain was already written to look for, so that half needs
no change. Matter is started only once there is an address, because with CHIPoBLE gone it is found over mDNS
and mDNS needs a network.

**Two costs, both real.** Bluedroid takes the image from 1.77 MB to **2.38 MB**, which does not fit
`min_spiffs.csv` at all — the partition decision made before any of this was known turns out to have been the
one that mattered. And free heap at boot falls from 129 KB to **66 KB**, with a 28 KB frame buffer still to
come; `FREE_BTDM` hands the Bluetooth memory back once provisioning is done, and nothing has yet watched it do
so under load.

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


## Scoped: leaving Arduino for ESP-IDF

*Scoped 20 September, not started. The question it answers is not "is Arduino nice" — it is that **on the
Arduino framework a strip cannot be set up by Apple Home or Google Home at all.* Without CHIPoBLE they cannot
provision Wi-Fi, so a strip bought by a household with no hub of ours does not work, and no amount of work on
our side fixes it: it is a compile-time flag in somebody else's precompiled binary. That is the promise this
whole product line started from.*

### What the move buys

Matter does the Wi-Fi **and** the commissioning, in one encrypted flow, over BLE. Which means these all go
away rather than getting ported: `WiFiProv`, the proof of possession and the question of how anybody learns it,
the two-key Wi-Fi ring, and most of `Radio` in the brain — because the hub would commission a strip through
`matter-server`, which the house already runs (`docs/matter.md`), exactly like any other Matter device.

It also puts secure boot, flash encryption and per-unit DAC provisioning within reach. Those are IDF-level and
are what the `esp_secure_cert` and `fctry` partitions were laid down for.

### What the move actually touches

| | |
|---|---|
| `src/pixels.h`, `test_pixels_native.cpp` | **nothing.** 351 lines, already framework-free, and that was the point of writing them that way |
| `partitions-matter.csv` | nothing |
| the brain, the panel, every board in `design/` | nothing |
| `src/pixels.cpp` | the RMT layer, about 40 lines, from `esp32-hal-rmt.h` to IDF's `driver/rmt_tx.h` |
| `src/main.cpp` | the rewrite, and it **shrinks** |

Counted from the real file, `main.cpp` uses: `Matter` (23 call sites, and the real work — the Arduino wrapper
becomes esp-matter's own `node`/`endpoint`/`attribute` API), `Preferences` (16, → `nvs_flash`, mechanical),
`String` (10, → `std::string`), `millis` and `delay` (12, → `esp_timer` and `vTaskDelay`), `PubSubClient` (7, →
`esp_mqtt_client`, which is in IDF), `Serial` (5, → `ESP_LOGI`, and one console instead of two, which was its
own bug), `gpio` (3). **`WiFi` and `WiFiProv` (7) are deletions, not ports.**

### What it costs

**esp-matter's README recommends ESP-IDF v6.0.2.** The install on this machine is v5.4.1, so this is a second
IDF, not a reuse — a couple of gigabytes with toolchains, plus esp-matter itself, which vendors connectedhomeip
as a submodule. Expect a long first fetch and a first build measured in tens of minutes; CHIP is enormous.
Incremental builds afterwards are ordinary.

The daily cost is slower builds and losing the fifteen-second self-test loop that has already earned its keep
twice.

### The risk that was named, and what actually happened

The named risk was the version matrix between esp-matter, connectedhomeip and IDF. **It did not materialize.**
IDF v6.0.2 installed clean, esp-matter cloned, its submodules and connectedhomeip's resolved on the first try.

**And the premise is confirmed from the source rather than inferred.** `connectedhomeip/config/esp32/components/chip/Kconfig`:

    config ENABLE_CHIPOBLE
        bool "Enable CHIP-over-BLE (CHIPoBLE) Support"
        default y
        depends on BT_ENABLED

On esp-matter it is **on by default**. The Arduino framework turns it off — which cost 600 KB of `WiFiProv` to
put back a worse version of the same capability. So the move buys exactly what was scoped.

### What stopped it, and it is this machine rather than Matter

Three install attempts died, each further along, and none of it was esp-matter's:

1. **The Command Line Tools SDKs are broken.** `MacOSX27.0.sdk` — the default, the one `xcrun` returns — has a
   malformed `libSystem.tbd` carrying an unknown `arm64e.x1` architecture, and `xcrun` cannot read its version.
   Worse, **none of the CLT SDKs contain C headers at all**: `usr/include` is empty. Every native compile on
   this machine fails, which is not a Matter problem and had already cost an hour earlier in the day on the
   native pixel test, worked around with `-isysroot` and not written down.
2. **Rosetta 2 is not functional.** No x86_64 binary can run: CHIP's `zap-cli` is x86_64, and so is the
   PlatformIO RISC-V toolchain that failed identically hours earlier and was written off as "a toolchain
   problem" without finding the cause.

Xcode is installed and **its** SDK is intact, so `DEVELOPER_DIR` gets past the first. The second needs
`softwareupdate --install-rosetta`. Both want an administrator and are the machine owner's to run.

### And then it was proven on the board

Rosetta installed, the install completed, and esp-matter's own `light` example built and ran on the same
ESP32-S3 that had spent the evening refusing to pair. Its config, the thing the whole trip was for:

    CONFIG_BT_ENABLED=y
    CONFIG_ENABLE_CHIPOBLE=y

Its own log, with no Wi-Fi configured at all:

    chip[DL]: CHIPoBLE advertising started
    chip[DIS]: Advertise commission parameter vendorID=65521 productID=32768 discriminator=3840/15

And a scan from the laptop, the same scan that found 59 devices and none of ours on the Arduino build, now
finds it at **-35 dBm** carrying service `fff6` = `00000ff1ff008000` — a commissionable payload with vendor
0xFFF1, the test vendor id, which is what an uncertified device should say.

**The same question asked of both builds, on one board, with one scanner: Arduino advertises nothing, ESP-IDF
advertises properly.** That is the decision made on evidence rather than on a config file.

**And it is smaller.** `light.bin` is **1.5 MB** with BLE commissioning built in, against 1.76 MB for the
Arduino Matter build that could not commission at all and 2.38 MB once `WiFiProv` was bolted on to work around
it. Moving to ESP-IDF gives back about 880 KB *and* does more.

---

## What is not built, and what is not safe yet

Everything under this line is honest. None of it is done.

**0. A correction, because this document said something too strong.** It claimed the hub never handles a
household's Wi-Fi password again. It does — **once**, to `matter-server`, via Home Assistant's
`matter/set_wifi_credentials`, because a Matter controller cannot commission a device onto a network it has not
been told about. The controller then delivers it to the device inside the commissioning session. That is a
different thing from what was removed, which put it on an unauthenticated BLE link anything in range could
read, but it is not *nothing*, and the tidier sentence was wrong. Found by reading Home Assistant's own API
rather than by reasoning about it, which is how it should have been settled the first time.

**1. Half closed.** Matter was written down here as having closed this and had not: CHIPoBLE is compiled out of
the Arduino framework on every target, so Matter never carries the credentials. `WiFiProv` with BLE and
protocomm `SECURITY_1` now does, and is on air. **What is still open is not the handshake but the proof of
possession**: it is random per device, printed on the serial console, and nothing decides how a household or
the hub comes to know it. That is the same question Matter's own passcode asks, and it is 1a.

**1a. Nobody can commission it yet, and the design for that is now settled.** A commissionable Matter device
advertises its discriminator; it does **not** advertise its passcode, and commissioning cannot happen without
one. So the hub cannot silently adopt a strip the way `design/puck/Knock.dc.html` argues for — that board's
proudest claim, that the identity check is the object and never a number, was in tension with the standard.
The artboard conversation has now been had: `design/strip/` gained a row on 20 September (`Both`, `Ours`,
`Theirs`, `CodeHub`) in which Matter is one door rather than the only one, and the identity check survives on
our own door where the standard does not reach.

**The passcode question underneath it is answered, and the answer is not the one the board first drew.** The
question was whether a certified device may hand its factory passcode to a vendor channel. It cannot, and not
because a rule forbids it — **it does not have one.** A production device stores only the SPAKE2+ verifier:
`ESP32FactoryDataProvider::GetSetupPasscode` returns `CHIP_ERROR_NOT_IMPLEMENTED`, connectedhomeip's own header
says that using the verifier rather than the passcode *"safeguards the passcode from ever leaking"*, and
Espressif's production guide says the verifier is installed *"and not the actual passcode"*. Deriving passcodes
at manufacture stays rejected for the reason it always was: one algorithm loose and every unit we have sold is
open.

**What works instead is smaller than the thing it replaces.** The strip mints a passcode when it is asked,
derives the verifier on the chip, and opens an enhanced commissioning window with it — which is what Espressif
recommends for a device whose onboarding payload can be displayed, and it ships the code:
`examples/light_switch`'s `dynamic_commissionable_data_provider` is a DRBG draw, the disallowed-passcode check
and `Spake2pVerifier::Generate`. `CommissioningWindowManager::OpenEnhancedCommissioningWindow` takes the
verifier directly and needs neither a fabric nor a Matter administrator, so the hub does not have to be one and
`matter-server` stays off this path. Three things come with it and none is a blocker: an enhanced window never
advertises over Bluetooth, so the other app must be on the house Wi-Fi; the label's own code does not work while
the window is open, because the fresh verifier has replaced it; and fifteen minutes is the specification's
ceiling on a window rather than a number we chose. **None of it is written yet.**

**2. The hub can now hand a strip to the commissioner, and that is all it can do.** `Radio` speaks Matter:
it scans for the commissionable advertisement and decodes it (checked against a real device — an S3 running
our firmware advertises `00000ff1ff008000`, and its own log agrees the discriminator is 3840 and the vendor
0xFFF1), and hands a code to `matter/commission` through Home Assistant's websocket, which reaches
`matter-server` the house already runs. It carries no credentials of its own and must never be given a route
that does.

**Setup now stops at commissioned, and that is honest rather than a regression.** Everything after it — the
color question, the fill, a room — is addressed by the strip's *chip* over the broker, and a Matter
advertisement does not carry one. It used to pass in tests because a fake handed over an id nothing real would
have. A strip that reaches `ready` is a working Matter light in whatever app commissioned it; it is our extra
half that is missing, not its own.

**2-mac. COMMISSIONING CANNOT BE TESTED ON THE MAC, and an evening went into finding that out.** The strip
advertises, the brain asks correctly, and it fails — because `matter-server` needs host networking, mDNS and
IPv6 on the LAN, and `driver-layer/docker-compose.mac.yml` says in its own first line that Docker Desktop on
macOS has none of them. That file has no `matter-server` service at all; the container that was started came
from the Pi compose, where `network_mode: host` means something. On the Mac it binds a loopback Home Assistant
cannot reach from its bridge network, and every address refuses.

So the remaining ways to exercise commissioning are: **on the Pi**, where the driver layer is real; or **from a
phone** — Apple Home or Google Home commission over the phone's own Bluetooth and do not need any of this,
which is also the path a household buying one strip would use. The hub path waits for the Pi.

**A related thing worth deciding rather than discovering.** Adding the Matter integration to Home Assistant by
hand breaks `product-direction-out-of-the-box` — no household should have to open that UI. The hub already
drives config flows for the weather integration (`api.py`, `/api/config/config_entries/flow`), so it can do the
same for Matter with the url from the compose file. Not built, and it should be, because otherwise every house
needs somebody to do this by hand exactly once and nobody will remember.

**2a. ANSWERED AND BUILT, 21 September.** The strip is handed the broker inside the session that carried
the Wi-Fi, on a `hub` endpoint of our own: `network_prov_mgr_endpoint_create("hub")` takes `0xFF53 + 1`,
which is exactly the first characteristic `prov::reserve()` keeps spare, and the payload is lines of
`key=value` for the four things `find_hub()` reads. Not protobuf: the schema is ours at both ends, there are
four keys, and the hub-side client has to be hand-written anyway. A key the strip does not keep is refused
out loud rather than dropped, so a mismatch between the halves shows up on a bench. Seen in the table as
`1775ff54 name="hub"`. **Not yet driven by a client** — `esp_prov --custom_data` speaks its own
`custom-data` endpoint wrapped in a protobuf, so proving this needs the hub's own client, which is next
anyway.

*What it replaced, for the record:* **Nothing decides how a strip learns our broker.** After commissioning it is on the house Wi-Fi and knows
nothing about us; `mhost` in its NVS is blank, so it is a plain Matter light and the color and length questions
never get asked. Handing those details over needs either a route on the hub or a custom Matter cluster, and
neither is designed. **This is the seam between "a Matter light anybody can buy" and "a light our hub set up
properly", and it is currently an empty string.**

**2b. Certification, which is what "just works" actually costs.** Everything above runs on a *test* vendor id.
Apple and Google will commission such a device with an "uncertified accessory" warning — *the warning is the
part nobody here has written down having seen, so treat it as expected rather than observed* — and it cannot
be sold.
**Both have now done it** — Apple Home on 20 September and Google Home the same day, `VendorId 0x6006` sitting
in the fabric table beside Apple's. So the sentence above is confirmed in the half that matters and the
temptation to read it the other way should be resisted: **nothing refused the strip, and it still cannot be
sold.** What certification buys is not commissionability but the right to ship — a real Vendor ID instead of
reporting itself as `TEST_VENDOR`, a listing in the compliance ledger, the logo, and a certificate in the unit.
An artboard here had said Google refuses such a device. It does not, and that was invented rather than observed.
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

**35. The claim our door rests on is written down, and the puck already keeps it.** 22 September.
Item 23 ended with *"a button, reachable, on the outside of every product is now a hardware claim
this rests on. It is free to decide now and impossible later, and `hardware/` has never had the
conversation."* It has had it now: `hardware/README.md` is a short page of the claims every board we
make has to satisfy, with the button as the only one so far and the test written so it can be
checked rather than argued — from outside the assembled shell, with a fingertip, no tools, in the
state the product ships in, before it is placed, and **never on a strapping pin**.

**The puck passes, and it passes by accident rather than by intent**, which is the part worth
knowing. `SW3` sits on GPIO4 with the internal pull-up — module pin 4, `pinfunction "IO4_4"` in
`puck-revA.net` — a side-actuated tact at the board edge at 180°, the face a person would tap,
reached through a 3.6 mm hole cut through both the base wall and the skirt with a printed plunger
whose head stops it falling in. All of that was laid out on 19 September to answer
`docs/puck-light.md`'s question *"does the object want a button?"*, two days before the press became
the proof of possession. The board was right for a reason that has since been replaced by a better
one. `docs/puck-hardware.md` no longer calls it an open question.

**And the strip's board, which does not exist yet, has one thing to get right.** `BUTTON_PIN` in the
firmware defaults to **0** — BOOT on every devkit, a strapping pin, and the same line the USB
bridge's auto-reset pulls from DTR. On the bench that is a feature and it is how the press has been
tested with nobody in the room (item 23). On a product it means a finger on the adoption button at
power-up can drop the chip into download mode. It is a `#ifndef`, so the board defines it; nothing
anywhere said it had to until now.

**34. A knock takes the whole screen, up to a hundred and eight seconds late, and the panel already
had a politer way of saying it.** Reported 22 September after a night of setting strips up: powering a
strip on is not always a moment anybody asked to be interrupted in, and when the sheet did arrive it was
about two minutes behind, which read as the strip and the hub failing to talk to each other.

**THE TWO MINUTES IS ARITHMETIC AND NOTHING IS BROKEN.** Up to 20 s asleep between scans
(`watch(every=20.0)`); then `scan_ours(8)` and `scan(6)`, and a third scan at 14 s when Matter's door
answered and ours did not; then up to 60 s before the wall asks, because `store.ts:698` polls `/strip`
once a minute while nothing is live. **20 + 28 + 60 = 108 seconds**, worst case, and the last sixty of
them are one number in the panel.

**And instant is not available.** A strip is a passive advertiser; hearing one the moment it powers on
means scanning without stopping, and `watch()`'s own comment says why that is not free — the hub is the
Bluetooth end of every other device in the house. **So the delay and the interruption are one problem:**
an interruption nobody asked for has to be instant or it reads as a fault, and this one cannot be.

**THE PANEL SHIPS THE POLITE ANSWER ALREADY AND DOES NOT USE IT FOR A KNOCK.** A thing noticed on the
network becomes *"Found 2 new things nearby"* — one line in the band (`Attention.vue`) and an 8px lamp
dot on the `+` door in the bar (`panel.css` `.topbar-add.attention`), tap to open Add. A knock is drawn
the instant `store.strip.state !== 'none'` with nothing gating it (`App.vue:325`). Three shipped ways of
saying the same thing; two of them quiet, and the knock uses the third.

**Decided, `design/knock/`, five boards: C with A.** The knock is a line and a dot everywhere except on
Add, where it fills the page. The line is its own for an hour, then folds in with anything else waiting
and goes when the thing stops knocking; the dot stays, so the house stops talking without forgetting.
*Not mine* keeps the meaning `_dismissed` already gives it. **And `Look` is the one to build first:** Add
scans while it is open, which is the only moment spending the radio is free, and that is what lets
`watch(every=20.0)` be quietened. The two changes pay for each other.

**A correction worth keeping:** the first drawing of these boards gave the panel a tab row reading
Home / Rooms / This house / Add. There is no Add tab and there must not be one — the tabs are three
(the time of day, Rooms, Cameras) and Add is its own round door in the bar, beside This house.

**BUILT, 22 September**, and four things turned up in the building that the boards could not have.

**The band lost a line the moment a strip knocked.** The first `waitingBand()` returned one line, so
a house with something waiting on the network stopped being told about it as soon as a strip was
plugged in. It returns a list now. **Nothing but opening the panel and reading the band would have
shown this** — every test passed, and the types were right.

**The conversation opened underneath the page that opened it.** A sheet sits at z-index 35 and This
house at 40, which is correct everywhere else and wrong here, because Add *is* This house. Raised to
45 for this one sheet only, in `StripSheet.vue`'s own scoped block, so no other screen's stacking
moves. **`BridgeSheet.vue` has the same latent pair and is untouched** — a bridge knocking while Add
is open would draw under it too.

**And one Escape closed both of them**, so putting the strip down also threw the household out of
Add. `StripSheet` takes the key on the capture phase now and stops it there.

**The mock brain answers `{"ok":true}` to every POST it does not know**, and `keepLooking` was
assigning the answer straight into `store.strip` — which wiped the knock the instant Add opened. It
takes the answer only when it has a `state`. A hub older than `/strip/looking` answers 404, and the
page then says nothing rather than claiming to listen: **`store.looking` is only true once the hub
has said so**, because a page that says it is listening when nothing is is a comfortable lie.

**What the boards asked for and did not get:** `design/knock/Look.dc.html` drew a progress bar under
*Listening for anything new*. A scan here has no end — it runs until the page goes — and a bar that
cannot say how far along it is is a picture of progress rather than progress, which is the argument
`StripSheet.vue` already makes about its own single step. The board lost the bar rather than the
code gaining one.

**The numbers, as built:** `LOOK_EVERY` 60 s in the background, down from 20 — three times fewer
scans all day. `LOOK_HOLD` 12 s, refreshed every 5 s while Add is open, so the loop runs back to
back there and lapses by itself if the wall goes to rest. The panel's idle poll of `/strip` went
from 60 s to 30, and to 2 s while Add is open. Suites: brain 1143, panel 516, 194 e2e, all green.

**33. The distance is drawn and the courier is chosen; and the retain is gone, in two halves.**
22 September, and neither half has run on a board — nothing was plugged into this machine.

**`design/ears/`, five boards.** `Today` (one radio, and it is in the garage), `Errand` (A — the bridge
puck runs the errand), `Anyone` (B — every powered thing of ours is an ear and the hub asks the loudest),
`InHand` (C — the wall over Web Bluetooth) and `Deaf`, the failure all three end at. **A was chosen**, and
the case for each is in `design/ears/canvas.json` beside its board. Two things the boards settled that the
prose had not: *B is not a rival* — build A's question as "who can hear this" and B is a longer list later
— and *C is dead here for three reasons rather than one*: Web Bluetooth needs a secure context and the
wall gets plain `http://` on the LAN, it needs the API and the wall is an Android **WebView** rather than
Chrome, and it needs a person standing at the glass because the gesture *is* the permission model.

**And `Deaf` found a screen nobody had noticed was missing.** A house whose hub has no Bluetooth at all
is not a failure to report — nothing ever knocks, so there is nothing to report on. Today that house is a
wall that stays empty while a strip advertises in the next room for forty-eight hours. That sentence
belongs in **Add**, before anything is tried, and it is not built.

**The retain: `count/set`, `order/set` and `room/set` are published without it now.** The strip writes all
three into its own NVS, so the retained copy was a second source of truth that is replayed at every
reconnect and wins silently when it is stale — item 31's `count/set 1` from a bench test, and a board
that believed it was one pixel long. Pinned by two tests that fail with the flag put back.

**THE OBVIOUS WAY TO CLEAR WHAT IS ALREADY ON THE BROKER IS A TRAP, AND IT IS WORSE THAN THE BUG.** An
empty retained payload is how a retained topic is deleted — and to the firmware that has been shipping,
an empty `count/set` is `atoi("") == 0`, so the brain sweeping the broker clean would tell every strip in
every house that it is zero pixels long. **So the clear is on the device, not in the brain:** a command
whose answer is already in NVS is never taken from a retained message, and the strip publishes the empty
payload itself to retire it. Only firmware that has this line ever sends one. `e->retain` off the MQTT
event is what tells the two apart, and the broker delivers our own clear back with the flag off and no
payload, which the same line drops.

**What is not proven:** that the firmware half does what it says on silicon. It compiles (`0x1a3910`,
56% free) and no board was attached. The thing to watch for is the log line
*a retained count/set was waiting on the broker; retiring it* on a board that has one, the real count
surviving it, and `mosquitto_sub -t 'strip/+/count/set' -v` coming back empty afterwards.

**32. The three things a household found in the first run that reached the end.** Reported 21 September,
all three real, and the first two are one bug.

**The fill measured the wire against the length it already believed.** `fill.tick(now, strip.count)` —
and the fill IS the instrument that discovers `strip.count`. So a strip that came to believe it was one
pixel long filled one pixel, for ever: the "start over" ran and lit nothing anybody could see, because
only that one pixel was being written, and the length question could not be answered a second time.
**There was no way back to the truth from inside the panel.** It fills the whole wire now and latches
the real count on stop — writing 600 is free, the surplus falls off the end, which is why 300 is the
assumed length in the first place. Proven on a board deliberately told it was one pixel long: it filled
past 240 and latched 247.

**A late `fill` message dragged the job back to the measuring.** The strip publishes its progress as it
goes and the last of those lands *after* somebody has said "that's the whole of it" — and `_on_mqtt`
set the state to `length` whatever beat the job had moved on to. From the wall: you are asked for a
room, you tap one, you are told there is no light waiting for a room, and you are back watching the
fill. Three times in a row, which is exactly how often a late message lands. It only follows the fill
while the fill is what is on screen.

**And choosing a room never did anything.** `put()` called `self.hub.strip_placed(...)` — **a method no
hub has ever had** — inside a `try/except AttributeError: pass`. So the wall said "It's in", the light
stayed wherever Home Assistant first put it, and the household went and did it again by hand. It asks
the device registry now, and keeps asking for twenty seconds, because discovery is a moment behind the
room chip.

**And the other half of the first one is now built.** `design/strip/Later.dc.html` was drawn and chosen
on 20 September and the row was never made: the brain had `/strip/revisit` and the panel had
`revisitStrip()`, and **nothing called it**. So a household whose strip measured wrong had no way to say
so, which is exactly what came back. `LightPane.vue` carries the two rows now, at the foot, each one the
setup question it came from and nothing else — the length in metres, because strips are bought by the
metre, and the red question again for a strip that was replaced by a different make.

**How the pane knows the light it is drawing is a strip:** `/strip/list` now carries `device`, the
house's own id for the hardware, which every device the panel draws already has. Resolved from the
device registry by the same lookup that puts a strip in its room, cached when found and never cached
when missing — discovery is a moment behind everything else, and remembering that a thing did not exist
is how a panel comes to be permanently sure of a wrong answer.

**What is deliberately absent is the board's loudest argument**, and a test holds it: no effects, no
segments, no zones. A strip with a hundred named animations is a maker's toy; this is an accent light a
household should be able to forget about.

**31. A strip that is set up is still not a light anybody can switch on — until now.** Everything before
this item is setup, and setup is not the product. The household's own on/off, brightness and color
arrived over **Matter and nowhere else**, and a strip taken through our own door never joins a Matter
fabric (item 16). So a strip that had been through the whole flow sat on the broker answering questions
about itself and could not be turned on from the wall it had just been set up on.

The panel draws whatever the house has, so the whole of "control it" is **be a light the house has**:
one retained announcement on `homeassistant/light/strip_<chip>/config`, one command topic, one state
topic — which is what the bridge puck already does for a switch. Availability follows the same `status`
topic the last will already writes, so an unplugged strip goes unavailable rather than stale.

**Proven end to end on an ESP32-S3 against a real house, 21 September:** a fresh board through the
whole flow, `announced as a light the house can switch on`, and then

    -> strip/2e4258/light/set {"state":"ON","brightness":200,"color":{"r":255,"g":60,"b":0}}
    <- strip/2e4258/light     {"state":"ON","brightness":200,"color_mode":"rgb","color":{...}}

**AND A TRAP FOUND IN THE SAME BREATH: a retained command is replayed for ever.** `count/set`,
`order/set` and `room/set` are all published retained, so a strip relearns them when it reconnects. A
**stale** one is then a second source of truth that silently wins: this board was carrying
`count/set 1` from a bench test weeks of debugging ago, so it believed it was one pixel long, and
switching it on lit exactly one LED — which looks precisely like a broken strip and nothing anywhere
says why.

**The strip already keeps all three in its own NVS**, so the retain is redundant as well as dangerous,
and the honest fix is probably to stop retaining commands and let the device remember. That is a change
to how a strip is told things and it is **not made here**; it is written down so the next person does
not spend an evening on a light that works perfectly and shows one pixel.

**30. "Where is it?" answered 500 to everything, in any real house.** The first beat past the fill, and
the first one nobody had ever reached. `_rooms()` iterated `home.rooms` — **which is a dict of
`id -> Room`**, so it walked the keys and asked a string for `string["id"]`. Everywhere else in the
brain says `.rooms.values()`.

**It took the whole sheet down, not just that request.** `_rooms()` is called from `status()`, which is
what `GET /strip` returns, which is the poll the panel lives on — so once the job reached `room` every
request raised and the wall could not even draw what had gone wrong. The toast said *internal server
error*, which is the only honest thing it could say.

**No test caught it because the fake house is a list**, and a list of room objects is exactly the shape
this code was written against. The suite now uses a dict, which is what a house is. `unassigned` is also
a real room in that dict and is never somewhere to put a thing; every other caller skips it and this one
now does too.

**29. A strip set up through our own door never went to the broker until it was next switched off and
on.** This is the one that failed all evening, and it is the last mile of item 2a.

`find_hub()` was called from exactly two places: at boot, and on Matter's `kCommissioningComplete`.
**Our own door is neither.** So a strip taken through our door was handed the Wi-Fi and the broker in
one session, stored both, joined the house — and then sat there with a perfectly good broker it had
never been told to go to. The hub waited sixty seconds for a hello that could not come and reported
*"It joined your Wi-Fi but never reached the hub"*, which was true in the most misleading way
available. It reached the hub on the **next power cycle**, every time, which is what kept making the
retained topics look like a strip that had worked.

There is a third moment now, and it covers every path including ours: **an address on the house's
network.** `IP_EVENT_STA_GOT_IP` fires on the first join and again after a router reboot, and
`find_hub()` is safe to call from all three because only the first one that can answer does anything.

**And the first version of that hook did nothing at all, silently.** It was registered ahead of
`esp_matter::start()` on the reasoning that Matter is what brings the Wi-Fi up — but the default event
loop does not exist that early, `esp_event_handler_register` returns `ESP_ERR_INVALID_STATE`, and
**nothing says so**: the address arrived, the default handler printed it, and ours was never called.
It built clean and read correctly. The loop is created here if nobody has made one, and the return is
read. `find_hub()` also says why it is declining now — three silent returns and a strip that has joined
the house and gone quiet look identical from a serial console.

**Proven end to end on an ESP32-S3 against a real house and a real broker, 21 September:** factory
reset, knock, press, Wi-Fi and **four** broker details (it was two — item 26), `looking for the hub at
hub.local` in the same session, and `strip/52e204/status online`. No reboot. **That is the first time
our own door has ever completed.**

**28. The button stopped working after a successful setup, and a strip with a dead housekeeping loop
looks exactly like a strip that is fine.** Reported from a real house on 21 September as *"holding BOOT
does nothing until I press RESET first"*, which is the only symptom this has.

`tend_the_door()` calls `network_prov_mgr_deinit()` once the door has shut for good — and that line runs
**only after a session has actually completed**, so it never ran on a bench whose Wi-Fi was a name that
does not exist, and ran every time in a house. It is also the exact call item 22 is about: it takes the
manager's own lock, and the manager's cleanup timer holds that lock while it tells us the door has shut.

**What that costs is not the manager, it is the loop.** Everything a person can do to this thing with
their hands is read from `housekeeping()`: the short press that lets the hub in, the five-second hold
that forgets the house, the fill, the instrument, and `tend_the_door()` itself. The strip goes on
glowing, advertising and answering Matter with all of it gone.

**Two rules out of it, and they are both general:**

- **The button must never be behind anything that can block.** It is the way out of every other mistake
  in this firmware. The deinit now runs on a task of its own, where the worst a block costs is the
  manager's memory.
- **The loop that reads the hands is under the task watchdog.** A block is now a panic with a stack
  trace, which is a bad day somebody can read, instead of a strip that has quietly gone deaf.

**27. Two strips knocking, and the hub talked to the wrong one.** Our door's scan returned strips in
the order they happened to advertise; Matter's side has sorted by signal since it was written. So a
household standing over one strip, pressing its button, could be waited out by a hub holding a session
open with a different strip in another room — and then told *"that strip is a long way from the hub"*,
which was perfectly accurate about the wrong strip. `look()` sorts within each door now. **Our door
still wins over Matter's however faint it is** — it is the only one that can ask the two questions and
hand over the broker — but which strip at our door is now the nearest one.

**And the sentence the panel says while this happens cannot be made true by the panel.** `_label()`
returns "A light strip" on the reasoning that "it is two meters of light and it is the only one lit",
which is false the moment a second one is knocking. The brain now logs how many are, and at what
signal; what the wall should SAY when there are two is a screen and wants a board.

**The thing that made it hard to see:** a strip that has completed setup once **advertises nothing at
all** — our door is shut by the `ours` flag and Matter's window is closed at boot (item 16). So a strip
carried over to the hub and set up already is not "a strip near the hub that failed", it is not there,
and the only strip in earshot is whichever other one is still knocking somewhere else. Nothing on the
wall says a strip is spent; the five-second hold is the only way back and nobody is told it exists.
**That belongs with the partial-commissioning bug at the top of the open list.**

**Also learned, and it is a rule rather than a bug:** a scan filtered to the thing you are looking for
cannot tell "it is not there" from "the radio is dead". Item 18 is exactly that failure and it still
caught me: a filtered scan from the hub returned nothing twice and read as range, and the unfiltered
one returned **29 devices**. Scan for everything first, then filter.

**26. Every strip ever set up through our own door was handed a broker it could not log in to, and
then asked a question on a topic nothing subscribes to.** Two bugs in a row, both on the last mile,
and between them our door has never once completed. Found on a real hub on 21 September, with the
strip a foot from the Pi — so the distance was not it, and item 25's new sentence would have been
wrong too.

**One: the credentials were never sent.** `_where_we_are()` read a `broker` key in the settings that
**nothing in this hub has ever written**, so every strip was handed the literal name `"hub"` and no
user and no password. The strip joined the house, resolved the hub and reached the broker:

    I (1543) strip: already set up, through our own door
    I (5083) esp_netif_handlers: sta ip: 192.168.86.70
    W (5913) mqtt_client: Connection refused, not authorized

The tell was in plain sight on the bench all day and read as a success: *"the hub said where it is:
**2 details taken**, 0 refused"* — mhost and base, and never muser or mpass. A puck is told the same
four things and works, because `bridge.py` reads them out of the environment. There is one
`Bridges.broker()` now and both halves call it: **two descriptions of one broker is how one of them
comes to be wrong.**

**Two: the hub had nothing to call the strip.** `id` is `None` for a strip at our door — a Matter
advertisement carries a discriminator, not an id of ours — and the next line asked
`_ask(j["id"], "hello", ...)`, which publishes to **`strip/None/hello`**. Nothing has ever subscribed
to that. It could not have worked at any distance, and it had been there since the day our door was
written. The strip announces itself retained as `strip/<chip>/status` the moment it connects, so the
hub now waits for the one that was not there before rather than asking for a name it does not have;
one job at a time is what makes that unambiguous.

**And both failures wore item 25's sentence.** *"It joined your Wi-Fi but never found the hub. Try it
nearer the router"* — for a strip that had joined the Wi-Fi, found the hub, and been turned away at
the door. **Three times in one evening a true-sounding sentence sent somebody to check a thing that
was not wrong**, which is the actual lesson of items 24, 25 and 26 together: a message about the
household's house should be built from what the hub OBSERVED, not from where in the code the failure
happened to surface.

**And the fix for the second one was wrong on its first try, in a way only a real broker shows.** It
waited for an id that **was not there before** — but the broker keeps what a strip said last, retained,
and the brain reads all of it the moment it subscribes to `strip/#`. So a strip that has *ever*
connected is already in that dict before the session starts, marked offline, and can never be "new"
again. Which is precisely a strip somebody has just factory reset and is standing over. It waits for a
strip to come **online** that was not online before, which is the fact it actually needs.

**And that fix was wrong too, for a third reason, which is the one worth keeping.** Watching whether a
strip is *online* cannot work here: **a strip that goes away never says so.** The broker says it for it,
from the last will, and only once the keepalive has run out. A factory reset, a reboot, a knock and a
press all happen well inside that window — so the hub is still holding `status: online` from the
connection that has already died, the strip is excluded as "already here", and the household is standing
over it reading that it never reached the hub. **A message arriving is a fact with a time on it; a
retained "online" is only a guess about now.** The hub watches for the hello and keeps the state check
as a second chance, because the two fail in different weather.

**The exact fix is still not this.** The strip should say who it is **inside the session**, on the `hub`
endpoint it already answers on — no broker state, no races, no window. That is a firmware change and it
is the right one; everything above is the hub inferring an identity it could simply have been told.

**The broker is the instrument that settled it**, and it was three commands away the whole evening:

    strip/52e204/count  300
    strip/52e204/order  grb
    strip/52e204/status offline

That is a strip that reached the broker, said what it was, and later dropped — while the wall was
saying it never reached the hub. `mosquitto_sub -t "strip/#" -v` inside the `mosquitto` container, with
the brain's own `MQTT_USER`/`MQTT_PASSWORD`, is the check to run before believing anything about this
step.

**25. A strip too far from the hub failed four different ways and never once said "too far".** The
whole of 21 September's evening on a real hub, in one log:

    16:29  something that might be ours is at Matter's door; asking ours again
    16:33  commissioning failed (Commission with code failed for node 2.)
    16:35  our own door did not open (BleakDeviceNotFoundError: Device with address ... was not found)
    16:40  a twenty-second scan from the hub: nothing at either door, at all

Nothing was wrong with the code. The strip was on a desk at the other end of the house and the hub
could not hear it. Each attempt failed in whatever way the radio happened to fail that minute — the
setup code refused, a device that answered a scan not connectable a moment later, our scan response
arriving when the advertisement did not (item 19) — and **every one of those sentences sent somebody
to check a thing that was not wrong.** The worst of them was on the wall: *"The strip did not take the
code. Check it, and that the strip is still lit."*

**The hub knew all along.** `scan_ours()` and `scan()` both return an RSSI and the job threw it away.
It is kept now, and `_fail()` replaces whatever the radio said with the distance whenever the strip was
under **−60 dBm** when it knocked — measured, not guessed: item 15 has a session establishing first try
at −51 and the link dying three to five seconds in at −64, every time. Below that, the distance *is* the
reason, and giving two reasons is the household checking both.

**And the sentence is the product's own model of the order**, which `design/door/` had to correct once
already: a thing is unboxed, plugged in, **set up**, and *then* placed. So the wall says *set it up in
the same room as the hub, then put it where you want it* — which is what somebody should have been told
at 16:29.

**What this does not do is close item 15.** Telling a household their strip is too far is honest, and it
is still a strip they cannot use where they want it. The 13 dB is a product problem and `hardware/` has
still never had the conversation.

**24. A strip that took credentials and never joined could not open its door again, ever.** Found on a
real hub on 21 September, minutes after the press shipped, and it read on the wall as *"The hub could not
finish setting it up"* with nothing anywhere saying why.

**The path, and any household can walk it.** Setup hands over a Wi-Fi name and password. The strip stores
them and tries to join. The join fails — a typo, the 5 GHz band, a network that has since moved — so
`NETWORK_PROV_WIFI_CRED_SUCCESS` never fires and the `ours` flag is never written. At the next boot CHIP is
already connecting with those stored credentials, and `network_prov_mgr_start_provisioning` cannot set an
empty config over a connecting STA: **`ESP_ERR_WIFI_STATE`**, and the door never opens again. The strip goes
on advertising for ever and cannot be taken by anybody, at either rung, until somebody knows the five-second
hold exists.

**The fix is where the knowledge is.** Inside `FabricCount() == 0 && !ours` the strip has never finished
setup with *anybody*, so anything stored is from an attempt that failed and is only in the way:
`esp_wifi_restore()` and one restart. Guarded by a `wificlr` flag in NVS so a restore that does not take
cannot become a reboot loop in somebody's living room, and the flag is cleared the moment a door opens
normally. Proven on the bench twice over — brick it, watch it clear itself in one reboot, brick it again,
watch it clear itself again.

**And the brain was describing it wrong.** `hub.strip` logged `our own door did not open ()` — an exception
whose `str()` is the empty string, which is what a BLE connect timeout is on BlueZ. The wall's sentence was
picked by matching on that message, so every timeout fell through to *"Unplug it and try again"* instead of
*"try again a little nearer the hub"*. It matches on `type(e).__name__` as well now, and the log line names
the type. **A log line that reads `()` is a log line that told nobody anything**, and this one had been
printing for an hour.

**This is a cousin of the partial-commissioning bug** at the top of the open list: both are a setup that
reported failure and left something behind that silently bricks the strip.

**23. The proof of possession is a press, and PopLight is demoted rather than deleted.** Chosen
21 September from `design/door/PressIt.dc.html`; the spec for the strip is `design/strip/Press.dc.html`
and `design/strip/ReachRhythm.dc.html`. The rhythm shipped that morning as what *everybody* got, a real
SRP6a session completed against it, and then somebody used it and said counting four groups of flashes
is a chore — and then the thing that actually settled it, which is that **a proof made of light only
works on something two metres long.** A puck has one LED. A sensor has none. Our door is not a strip
feature, so an answer that needs a strip is not an answer for it.

**THE GATE IS ON THE STRIP.** This is the whole of what the press buys and it is four lines in
`chr_access`: anything in radio range may open a session, walk the GATT table and ask the strip its
version, and it gets exactly as far as `prov-config`, which is refused until `press()` has been called.
It is deliberately not the hub's to release — a gate the hub releases is a gate whoever spoke first
releases, which is the unauthenticated link this firmware was rewritten to remove. Proven on the bench:
a session on the public password, `config_set_config`, refused.

**What it does not buy, written down rather than implied:** there is no keyspace any more. Somebody in
radio range at the exact moment of the press, racing the household's own hub, is the residual risk, and
it is the trade every push-button pairing has ever made. The window is 120 seconds and single-use.

**The password is fixed and public** (`press`), so the SRP6a handshake on this rung proves nothing and
is not meant to; it is the encrypted channel the rest of the conversation needs. A refusal returns
`BLE_ATT_ERR_INSUFFICIENT_AUTHOR` and not `..._AUTHEN`: 0x05 and 0x0f both mean *encrypt the link and
come back*, so a central takes them as an invitation to pair. CoreBluetooth reports both as
"Insufficient Encryption" whatever we send, having tried; BlueZ does not.

**And the rung below is reached one way only** — the household tapping *It has no button I can reach*,
which is `/strip/reach`. The hub asks the strip for a rhythm on the `press` endpoint, the strip shuts
its door and opens it again with a verifier made from four freshly minted counts, and the wall shows
the four steppers exactly as before. A verifier cannot be swapped inside a live session, which is why
it is a shut and not a switch. Forcing that downgrade buys an attacker nothing: they still cannot see
the flashes. `design/door/ShowMe.dc.html` is what the door canvas names for this rung and it stays
drawn and unbuilt, because for a strip it would move the gate off the strip and onto the hub.

All four paths run on an ESP32-S3 on 21 September: no press → refused; press → Wi-Fi and the broker in
one session; *no button I can reach* → door shut and reopened with a rhythm 150 ms later; wrong rhythm
→ refused inside SRP6a. The button is GPIO 0, which is also what the auto-reset circuit pulls from DTR,
so the press can be made from the bench with no finger in the room.

**A button, reachable, on the outside of every product** is now a hardware claim this rests on. It is
free to decide now and impossible later, and `hardware/` has never had the conversation.

**22. Calling `network_prov_mgr_deinit()` from the `NETWORK_PROV_END` handler deadlocks the task it is
on, and nothing says so.** The header does not; the source does, in a comment. `prov_stop_and_notify()`
runs on the esp_timer task with the manager's own `prov_ctx_lock` **already held**, and the last thing
it does is call the app's event callback with `NETWORK_PROV_END`. `deinit()` takes that same lock, and
it is not recursive, so it never returns.

**Nothing is logged and nothing looks wrong.** The strip stays lit and keeps advertising. What is gone
is the esp_timer task, and then the next task that asks the manager for anything — which was the whole
housekeeping loop, the button with it, one line after asking to open a door a rung lower. It was found
only by holding BOOT for five seconds and getting no factory reset, which is the one thing that proves
that loop is dead.

**It was in the shipped code before any of this**, on the ordinary completion path, where it had never
been noticed because nothing afterwards needed a timer. The deinit now happens in `tend_the_door()`,
from the housekeeping task, which holds nothing.

**Three smaller ones from the same evening**, all in `prov.cpp` and all invisible until hardware:

- **`network_prov_mgr_stop_provisioning()` is asynchronous** — it arms a cleanup timer and returns. A
  flag cleared when the stop *lands* is a flag that asks for the same stop eighteen times in a fifth of
  a second, because the housekeeping loop runs every 10 ms. Clear it where it is set.
- **A stop does not raise `NETWORK_PROV_END`** — only a deinit does. Waiting for it after a stop is
  waiting for something that never comes, and the strip sat in silence with nothing open at either
  rung. The thing to watch is `gPc`, which our own `prov_stop` clears.
- **`network_prov_mgr_endpoint_create()` hands out the next id each time it is called.** Asking again
  on a second opening asks for 0xFF56 and 0xFF57, which no characteristic was reserved for. A stop
  leaves the manager initialised and IDLE with its endpoints intact, so the reopen is a
  `start_provisioning` and nothing else. Relatedly, the endpoint names were `strdup`ed and freed in
  `prov_stop` while the scheme config went on pointing at them — fine for a door that opens once, a
  use-after-free for one that opens twice. They are `std::string` now.

**And the endpoint count in the log is the only sign a handler has nowhere to live.**
`network_prov_mgr_endpoint_register()` at `NETWORK_PROV_START` without a matching
`endpoint_create()` before the start succeeds, silently, and the characteristic simply does not exist.
The `press` endpoint shipped that way for one boot and the only evidence was
`our door is open, 6 endpoints` where it should have said 7.

**21. The build cache keeps a `-D` from a session nobody remembers.** `idf.py -DDATA_PIN=48 build` puts
`DATA_PIN:UNINITIALIZED=48` in `build/CMakeCache.txt` and every later `idf.py build` uses it — so a
strip wired to GPIO 5 was being driven on GPIO 48, the devkit's own LED, and the boot line said so all
along: `0.3.0 chip 2e4258 pin 48 300 lights`. **Read that line before believing anything about the
light.** It is the same class of thing as the stale brain in `AGENTS.md` §2: a green from the wrong
instrument.

**20. A log that shouts loses the message it was kept for.** `be_patient_with_everyone()` walked
three connection handles on every pass of the housekeeping loop — every 10 ms — whether or not
anything was connected, and NimBLE logs `GAP conn_find: connection not found` for each miss. Three
hundred lines a second, a core spent on nothing, and a console in which the thing you were actually
looking for could not be found. It was discovered on 21 September only because somebody was reading
the log for a different reason.

It is now gated on the door being open and rate-limited to four times a second, which is forty times
less often and still far inside the window that matters — the link it exists to catch dies a second
or more after it forms. 6,000 lines in twenty seconds became 213. **`ble_gap_conn_active()` is not
the check to use:** it reports an in-progress *connect* procedure, which a peripheral never has, so
it is false even with a link up.

**19. The two doors are not equally easy to see, and the harder one is ours.** Matter's identity is
in the **advertisement**; ours is in the **scan response**, because Matter's payload had already
filled the advertisement and 31 bytes will not hold both (item 12). A scan response only arrives if
the scanner asked for one and the answer got back, so at the far end of a room the advertisement
lands and the scan response sometimes does not — and the same strip appears at Matter's door alone.

Seen on 21 September, on a real hub, minutes after the D-Bus mount made scanning work at all: the
household was asked for a setup code and the commissioner answered
`matter/commission: Node 1 does not exist`, for a strip that had a perfectly good door of ours open
the whole time. Nothing on the screen could have told them.

`look()` now asks our door a second time, for longer, when nothing turned up there and something at
Matter's door might be ours — a retry rather than a guess, since treating a test vendor id as proof
of anything is what item 6 already ruled out. And an address that answers at both doors is one strip,
so ours wins. **It is a mitigation and not a cure:** a scan response is simply less likely to arrive
than an advertisement, and the real answer is either extended advertising, where we would get an
advertising set of our own, or accepting that the last few decibels belong to Matter's door.

**18. The brain could not do Bluetooth at all on a real hub, and nothing said so.** Found on
21 September with a strip knocking a metre from the hub and the panel showing nothing. The brain runs
in a container with `network_mode: host`, which gives it the network and **not the system bus** — and
BlueZ is reached over D-Bus, not through a device node, so `/dev:/dev` does nothing for it. The
container had `bleak` installed and raised on every scan. Both doors went quiet at once: ours and
Matter's use the same radio, so the failure looked like "no strips anywhere" rather than like a
missing mount.

Proven by running the same published image twice on the hub: without `/run/dbus` a scan sees nothing,
with it the scan sees 28 devices. The fix is one line in `driver-layer/docker-compose.yml`.

**Two things this leaves.** The scan failure is caught and logged and the screen says nothing, which
is how it hid — `look()` swallows the exception so one door failing cannot take the other down, and
the cost is that both failing is silent. And a hub that has been updated will not have the mount until
its compose is updated too, so this is a thing to check on any hub that says it can see no strips.

**17. Two days of knocking, and CHIP's own way of doing it does not compile.** Item 14 is decided:
`design/strip/KnockTwoDays.dc.html`, a strip nobody has taken keeps knocking for 48 hours and then stops
in a way that reads as stopped. The board said this was one line of configuration and **it is not**.
`CONFIG_ENABLE_BLE_EXT_ANNOUNCEMENT` lifts `CHIP_DISCOVERY_TIMEOUT_SECS` from a 900-second ceiling to
172,800 — and it will not build: it is `default n`, nobody compiles that path, and CHIP's own
`BLEManagerImpl.cpp:288` drops a nodiscard `CHIP_ERROR` under `-Werror`. Turning it on means patching
vendored connectedhomeip, which lives outside this repository, so the fix would not be one anybody else
could reproduce.

So the window is reopened from our own code instead, in `prov::keep_knocking()`, with a 48-hour budget
measured from the moment the door opened. When the budget runs out the rhythm stops and the strip holds
a drained version of the same glow rather than going dark — **going dark is what a broken strip does**,
and the rule this whole panel runs on is that what was asking stays put and says it is no longer asking.
A power cycle starts the two days again. The board has been corrected rather than left standing: B lost
the cheapness that was most of its case and is still the right answer, because what was chosen was the
behavior, not the line of configuration.

**16. "Has anybody taken this strip?" is not a question the fabric table can answer, and two boots'
worth of bugs came out of assuming it was.** A strip adopted through our own door never joins a Matter
fabric, so `FabricCount()` is 0 for the rest of its life. Both fixed on 21 September, and both were
invisible on the first boot:

- **It reopened our door at every boot.** The condition for knocking was only "no fabric", so an adopted
  strip flashed its rhythm again and tried to start provisioning — by which time CHIP owns the Wi-Fi
  driver, so it failed with `ESP_ERR_WIFI_STATE`, *"sta is connecting, cannot set config"*. The wall
  would have said the strip was waiting while nothing was listening. The answer is an `ours` flag in NVS,
  written when a session completes, and it is the "first session to complete takes it" rule from
  `Both.dc.html` made real.
- **Matter reopened its own door.** CHIP opens a commissioning window by itself whenever there are no
  fabrics, so an adopted strip went back to advertising as commissionable at every boot and anybody in
  radio range could have put it into their app. An adopted strip now closes that window at boot and
  reserves no GATT service of its own, and a scan finds nothing at all.

**And a trap that kills the device rather than misbehaving:** `CloseCommissioningWindow()` from
`network_provisioning`'s task aborts. CHIP notices, calls it *"Chip stack locking error ... unsafe/racy"*,
and `chipDie`s into a reboot loop. Anything touching the stack from another task goes through
`PlatformMgr().ScheduleWork`.

**14. Our door is discoverable only while Matter's window is open, and nobody decided that.** Our scan
response rides on CHIP's advertisement, and CHIP caps a commissioning window at fifteen minutes
(`MaxCommissioningTimeout`, spec 5.4.2.3). When it shuts, the strip goes off air for *both* doors while
`network_prov_mgr` still believes it is listening — seen on 21 September, when a strip left waiting was
invisible to a scan and came back on a power cycle. A household that plugs a strip in and comes back
twenty minutes later finds nothing. This is not the case `docs/strip.md` already rules on: that one is a
*commissioned* strip re-advertising after a router reboot, which must never happen. This is a strip that
has never been set up at all, still sitting in its box's worth of nothing, and it should probably keep
knocking. **Not decided, and it wants an artboard** — for ever is a household-visible promise, and so is
giving up.

**15. The hub is the client, and it works.** `brain/hub/strip_door.py` plus `brain/vendor/esp_prov`
(Apache-2.0, vendored because the IDF dropped it at v6). On 21 September it found a strip by service
UUID, proved the rhythm, handed over the Wi-Fi and then the broker, in one session and with no phone:

    found: [{'name': 'PROV_52e20', 'rssi': -22}]
    prov: credentials for 'VirusBroadcast' arrived through our door
    prov: the hub said where it is: 2 details taken, 0 refused

Two things of ours sit on top of Espressif's: finding a strip by the service UUID rather than a name,
and the `hub` step. Espressif's own `Transport_BLE` could not be used unchanged for two reasons, both
assumptions that do not hold here — it finds a device by advertised *name*, and our scan response has
barely room for one; and it derives characteristic UUIDs by masking the endpoint id against the service
UUID, which is a no-op for the all-`ff` service it assumes and mangles ours. **Run on the Pi on 21 September, and the client is proven: at −51 dBm an SRP6a session establishes
first try, over BlueZ, with no workaround of any kind.** What was read as a client bug is link margin.
Everything below is what that cost to find out, and it matters because the margin is a product problem
rather than a bench one.

| from the Pi | result |
|---|---|
| −51 dBm | session ESTABLISHED, first attempt |
| −64 dBm | connection dies 3–5 s in, NimBLE reason `0x208`, every attempt |
| −25 dBm (a Mac) | completes |

**Thirteen decibels is the whole difference, and a real strip will not be at −51.** It is taped behind a
television — a metal plane — and the hub is in another room. So this is not solved, it is only understood:
a household at the wrong end of that gap sees a strip that will not set up, having done nothing wrong.
The likely fix is still the one below, and it is now worth doing rather than worth investigating.

**The original finding, kept because it is the diagnosis:** What works over BlueZ, with no
workaround of any kind: the vendored modules import on Linux and Python 3.13, discovery by service UUID
finds the strip repeatedly, and one connection walked 14 characteristics. **What does not work is
keeping the link up.** A connection establishes and then dies three to five seconds in with NimBLE
reason `0x208` — a supervision timeout — every time a session is attempted, at about −64 dBm. The same
code against the same strip at −25 dBm on a Mac completes.

**Two software levers were tried on 21 September and neither closed the gap.** Both are kept because
both are right on their own terms, and neither is the answer:

- **The strip now stays on fast advertising while it is knocking.** CHIP drops from a 25 ms interval to
  500 ms after thirty seconds, which is right for a device somebody is standing over and wrong for one a
  household walks away from. At the far table the Pi found the strip in seconds at 25 ms and **could not
  find it at all in twenty seconds** at 500 ms, so this one was worth having whatever else is true. It is
  a nudge on a timer, because CHIP raises no event when it drops to slow — the first version hung off
  `kCHIPoBLEAdvertisingChange` and silently never ran.
- **The strip now asks every new link for a 30–50 ms interval and a ten-second supervision timeout.**
  NimBLE accepts the request (`asked link 1 to be patient: ok`) and the link still dies about a second
  later. It has to be polled from the housekeeping loop: `kCHIPoBLEConnectionEstablished` is raised when
  a client subscribes to CHIPoBLE, not when the GAP link comes up, and the link was dying during service
  discovery seconds before that. CHIP owns the GAP event handler and we are not forking it.

**So the remaining gap looks like RF rather than software**, which is where it should have been suspected
once the parameter request was accepted and changed nothing. The devkit's antenna, the S3 holding up
Wi-Fi on the same radio, and thirteen decibels. Next places to look, none tried: the coexistence
balance, the antenna on a real board rather than a devkit, and whether the strip should stop scanning
Wi-Fi while a provisioning link is up. **Close range is unaffected and was re-checked after both
changes: −23 dBm, session established.**

The original diagnosis, kept because it is still true and still not the whole story: **CHIP never
negotiates connection parameters at all**
— there is no `ble_gap_update_params` anywhere in its NimBLE `BLEManagerImpl` — so the link runs on
whatever BlueZ proposes, and the strip is holding up Wi-Fi on the same radio while it answers. Software
coexistence is already on (`CONFIG_ESP_COEX_SW_COEXIST_ENABLE`). The fix is probably for the strip to ask
for a longer supervision timeout when a link comes up, which means a GAP hook in a connection CHIP owns.
Moving the strip next to the Pi separated range from parameters in one minute, which is what the table
above is.

A scratch copy for continuing this lives at `~/strip-door-test` on the hub, with its own venv; nothing
was installed into `/opt/home-hub`.

**And the BLE address rotates.** Two scans minutes apart returned `F3:EE:DA:BB:CD:5A` and then
`CC:57:3B:B4:71:80` for the same strip, so the hub must never cache an address — the service UUID and
the name are the identity, which is what `find()` already returns.

**13. How the second door actually gets built, read out of the source rather than guessed.** Three facts, and
together they decide the shape:

- **`protocomm_ble` cannot be used, and that is not negotiable.** `protocomm_nimble.c` stands up its own host
  inside `simple_ble_start()`: `nimble_port_init()`, `nimble_port_freertos_init(nimble_host_task)` and its own
  `ble_gatts_add_svcs`. CHIP has already done all three. Two NimBLE hosts is not a thing.
- **Protocomm's core is transport-neutral, and it is the part worth having.** `protocomm_new`,
  `protocomm_add_endpoint`, `protocomm_set_security`, and the one that matters:
  `protocomm_req_handle(pc, ep_name, session_id, inbuf, inlen, &outbuf, &outlen)`. `protocomm_security2` —
  SRP6a — ships beside it. **The half we must not hand-roll comes for free**, which is the whole reason to
  reach for protocomm at all rather than invent a handshake again.
- **The transport is a shim, and a small one.** `protocomm_nimble`'s GATT callback resolves an endpoint from a
  16-bit discriminator carried at byte 12 of each 128-bit characteristic UUID, calls `protocomm_req_handle`,
  and stashes the response for the read that follows. That is about a hundred lines of its eleven hundred, and
  it is the only part we write — against `ConfigureExtraServices`, which item 12 proved. Everything
  `protocomm_ble` does about advertising is dropped: CHIP owns the advertisement and we ride the scan response.

**And there is a seam for exactly this, which makes the shim smaller again.** `wifi_provisioning` is no longer
a core component in v6.0.2; it has become the managed component `espressif/network_provisioning`, and its
manager takes a **pluggable transport**:

    typedef struct network_prov_scheme {
        esp_err_t (*prov_start)(protocomm_t *pc, void *config);
        esp_err_t (*prov_stop)(protocomm_t *pc);
        void *(*new_config)(void);
        void (*delete_config)(void *config);
        esp_err_t (*set_config_service)(void *config, const char *service_name, const char *service_key);
        esp_err_t (*set_config_endpoint)(void *config, const char *endpoint_name, uint16_t uuid);
        wifi_mode_t wifi_mode;
    } network_prov_scheme_t;

So we supply a scheme instead of reimplementing a transport, and the manager hands us the whole flow: its
endpoints and their protobuf schemas, the SEC2 wiring, applying the credentials, and compatibility with a
client that already speaks all of it. **One constraint falls out of the timing and it shapes the code:**
`ConfigureExtraServices` refuses once CHIP's stack has started, and `prov_start` runs long after it. So the
characteristic table is registered at boot with the endpoint UUIDs known ahead of time, and the scheme's
`prov_start` only attaches the protocomm instance to characteristics that already exist.

**Built and proven on the board, 20 September.** `main/prov.cpp` is the scheme; `reserve()` runs before
`esp_matter::start()`. A scan and a GATT walk from this laptop, on an uncommissioned strip:

    ADVERTISEMENT  rssi -36
      service data { 0000fff6 } = ['00000ff1ff008000']      <- Matter, in the advertisement
      service uuids ['1775244d-6b43-439b-877c-060f2d9bed07'] <- ours, in the scan response

    GATT TABLE
      service 1775244d-6b43-439b-877c-060f2d9bed07   <-- ours
          chr 1775ff4f … 1775ff55  [write,read]  name=""     (seven of them)
      service 0000fff6-0000-1000-8000-00805f9b34fb  <-- Matter
          chr 18ee2ef5-…-9d11 [write]   chr 18ee2ef5-…-9d12 [read,indicate]

Two services in one table on one radio, which is what the whole forked row rests on. The empty names are the
design working rather than a fault: the manager has not been started, so the live table is empty and the
`0x2901` descriptors have nothing to say yet. The service costs 2,984 bytes of heap against 113 KB free.

**A trap for whoever writes the hub's half: CoreBluetooth will not enumerate this device.** macOS refuses
descriptor discovery on characteristics it reserves — *"the specified UUID is not allowed for this
operation"* — and bleak discovers descriptors for every characteristic during connect, so one refusal loses
the entire table. The walk above needed that call monkeypatched to tolerate it. Since the client reads the
`0x2901` descriptors to find its endpoints, **the vendored `esp_prov` has to be tested on the Pi over BlueZ,
not on a Mac**, and a Mac failing to provision a strip will not be a bug in the strip.

**Keep protocomm's UUID convention and its endpoint names** (`prov-session`, `prov-config`), so a client that
already exists can drive it. **`esp_prov` is not in ESP-IDF v6.0.2** — no `tools/esp_prov`, nothing under
esp-matter — so the first end-to-end proof of a SECURITY_2 session wants Espressif's provisioning app on a
phone. **The app is a bench instrument and is never part of the product**: it is a second app, and somebody
else's, which `product-direction-out-of-the-box` rules out twice over. In the shipped thing the *hub* is the
client, which is the whole of what `Ours` draws.

**The client the hub needs already exists and does not have to be written.** `tools/esp_prov` is still in
ESP-IDF **v5.4.1**, which is also installed here: 22 files, about 1,950 lines, Apache-2.0, with
`security/security2.py` doing SRP6a and a `bleak` BLE transport that works over BlueZ on the Pi. Apache-2.0
into AGPL-3.0-or-later is compatible one way, so it is vendored with attribution rather than reimplemented.
One change is needed and item 12 already named it: `ble_cli.py` discovers by device name, and there is no room
for a name in our scan response, so it has to match on the service UUID.

**12. BLE coexistence is answered, on the desk, and it corrected a board.** The forked design in
`design/strip/` rests on the strip offering our own provisioning service and Matter's at the same time. Read out
of `connectedhomeip` rather than reasoned about:

- **The GATT half is first-class and supported.** `BLEManagerImpl::ConfigureExtraServices(std::vector<ble_gatt_svc_def> &, bool afterMatterSvc)`
  merges application services into the same NimBLE host as `CHIPoBLEGATTSvc`. **There is no second stack and no
  second `nimble_port_init`**, which was the thing that could have killed the design. It has to be called before
  the stack starts — it returns `CHIP_ERROR_INCORRECT_STATE` once `mGattSvcs` is non-empty. esp-matter's own FAQ
  documents the surrounding story and points at `blemesh_bridge`.
- **The advertising half needed the scan response, and it is now proven on air.** `Both.dc.html` originally
  said *one advertisement carrying two services*, which this firmware cannot do: without
  `CONFIG_BT_NIMBLE_EXT_ADV`, CHIP calls `ble_gap_adv_start` — the single legacy advertising set — and 31 bytes
  will not hold Matter's `0xFFF6` service data and a 128-bit vendor UUID. `ConfigureScanResponseData` buys a
  second 31 bytes, and on **20 September a scanner saw both from one board**:

      svc data   {'0000fff6-0000-1000-8000-00805f9b34fb': '00000ff1ff008000'}
      svc uuids  ['21436587-09ba-dcfe-0001-020304050607']

  One address, −25 dBm, Matter's commissionable payload in the advertisement and a vendor service UUID in the
  scan response beside it. The UUID takes **18 of the 31 bytes and leaves 13**, which is not enough for the
  16-character device name the old `WiFiProv` design advertised — so the UUID is the identifier now and the
  brain's `Radio.scan()` has to match on that rather than on a name. Extended advertising, where Matter holds
  `kMatterAdvInstance = 0` and we take another instance, stays available and is not needed.
- **Measured, 20 September: the whole second door costs 228 bytes of heap and 1,232 of flash** — the GATT
  service and the scan response together, free internal DRAM 114,544 → 114,316 with the largest free block
  unmoved. A second GATT service alone, without the scan response, was 232 bytes. Registered through
  `ConfigureExtraServices` as one 128-bit service with four read/write characteristics, which is roughly the
  shape protocomm exposes, on an uncommissioned board with Matter up and CHIPoBLE advertising. Both calls
  returned `Success` and advertising was unaffected. **Against 114 KB free, the heap half of the coexistence
  question is not a question.** The spike was removed once it had answered; the numbers are the record.
- **`CONFIG_USE_BLE_ONLY_FOR_COMMISSIONING=y` can stay.** Our own door has no use for BLE once the strip is on
  the Wi-Fi — `Theirs` hands over via mDNS after that, and an enhanced commissioning window never advertises
  over Bluetooth at all — so the Bluetooth memory still goes back.

**Every heap and image figure this document used to quote was from a build that no longer exists** — 1.77 MB,
2.38 MB, 129 KB and 66 KB are all Arduino plus Bluedroid plus `WiFiProv`. Measured on the real thing on
20 September, an ESP32-S3 running this firmware, free internal DRAM:

| | free | largest block |
|---|---|---|
| at boot | 258,532 | 196,608 |
| before `esp_matter::start` | 246,532 | 196,608 |
| **after Matter, two fabrics** | **112,616** | 65,536 |

**Low water 95,312**, and that is the number with the say in it: there is a dip during Matter's startup that
the steady-state figure hides. So NimBLE and Matter together cost about 134 KB and leave **112 KB**, not the
66 KB that had been written down and repeated onto a board — the old figure was pessimistic by 46 KB, because it
was measuring Bluedroid. The image is 1,636,976 bytes, 58% of the app slot free.

*(An earlier version of this table read 114,020 free and 112,480 low water. Those were measured on a build with
`SELFTEST` left on in the CMake cache, which is a different binary and a six-second slower boot. The figures
above are the ordinary build.)*

**And there is no frame buffer still to come.** That phrase came from the same build. The pixel buffer is
`uint8_t buf[PX_MOST * 4]` — 2,400 bytes, static, already in `.bss` and already counted above — and the RMT
channel streams from `mem_block_symbols = 64` rather than holding a frame. Nothing large is waiting to be
allocated, which is the headroom a second GATT service has to fit into.

**11. The error text needs a pass with one rule: do not guess.** Four screens in a row during bring-up named a
confident wrong cause — Matter cannot do it, then check your code, then check your strip, then check your
Wi-Fi — while the real faults were a missing argument, a missing container, a missing integration and a
platform that cannot do mDNS. Each sentence was written to sound reassuring about a failure nobody had
diagnosed. On a wall panel that is worse than useless: a household cannot tell a guess from a diagnosis and
will go and do what it says. The honest default is to say the hub does not know and name where to look.
