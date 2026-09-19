# The puck's light: an instrument first, and then a nightlight

*Written 18 September 2026, from two things said the same day. One: a puck left on a USB wall charger overnight
already worked as a nightlight, by accident, and it was pleasant. Two, and it is the load-bearing one: the shipped
puck is meant to be **a product** — a small, plain relay object sitting out in the open in a living space — not an
ESP32 devkit on a shelf, and part of the job is that it is nice to look at. Its light is the only expressive
surface it has. The design is settled; what it asks of the hardware, and the questions that are genuinely open,
are at the foot and marked as such. **The whole build order is written** (18–19 September): the state, the
precedence, the NVS setting, the MQTT topics, the Home Assistant entity, the hub side, the question on the sheet,
the motion lift, and the Bridges section on This hub that step 5 turned out to need. Both firmware targets
compile, the brain's 964 tests and the panel's 415 pass, and every screen has been walked through in the real
panel against the mock. Nothing has run on a puck yet — there has been none on the cable — so every claim below
about how it *behaves on hardware* is still a claim.*

## What the light does today, and for how long

`brilliant/esp32-bridge/src/light.{h,cpp}` gives the puck one light and three things it can say — blinking amber
(looking), steady green (a switch answered *and* the broker is up), breathing red (three empty scans, too far).
`design/puck/Placing.dc.html` is the argument for it: both halves of setting a bridge up end with you unplugging
it and walking off with it in your hand, and the wall panel cannot follow you down a corridor. Nobody is taught
the colors. You stand there until it goes green.

That question is over about a minute after you plug it in. Then the object sits on a socket in a hallway or a
living room and glows at nobody until morning — an indicator light doing indicator-light duty for fourteen hours
in a room where somebody lives. The decision this document takes is what it does with that time.

Two constraints from the existing code, both of which shape everything below:

- **Green is a promise.** `lightRefresh()` in `main.cpp` recomputes it every pass and requires the mesh link
  *and* the broker, because BLE and Wi-Fi are separate radios and a socket can carry one without the other. A
  puck that is green while invisible to the hub would be a light contradicting the panel.
- **The light is written only on change.** The data line is electrically marginal (3.3 V logic into an LED on a
  5 V rail), so a fraction of frames are misread; rewriting a steady color at 25 Hz turned one dice roll into
  twenty-five a second, which is what made "steady" green flicker pale. Anything that fades is exposed to that
  fault. See `emitter-colors-are-not-screen-colors`.

## The decision

**Not "the bridge is also a lamp."** The light stays an instrument until it has finished being one, and a fault
takes it straight back. Four rows, and they are strictly ordered:

| | Situation | The light |
|---|---|---|
| 1 | Anything is wrong — no mesh, no broker, out of range | Amber or breathing red, exactly as today. Outranks everything below it |
| 2 | Still being placed | Steady green, until somebody says it is home |
| 3 | Settled, and the household said yes | A warm glow: dim, steady, unsaturated, and not one of the three |
| 4 | Settled, and they did not | Dark. This is what it does today and it stays the default |

"Settled" is an **event, not a timer**: `POST /bridge/placed` already exists (`brain/hub/api.py:1098`) and is
what the sheet sends when somebody taps *Leave it here*. A puck that has never been told it is home keeps its
instrument, which is right — an un-placed puck is still being carried around.

The board is `design/puck/Nightlight.dc.html`, sitting next to `Placing` on the canvas because they are the same
light and cannot be designed apart.

## Why it has to be allowed to stop

A glow that carries on while the bridge is down is furniture that lies, and nobody checks furniture. That is the
whole reason row one is absolute rather than polite.

And it is the feature, not the price. A nightlight that has turned amber is the most legible fault report this
system has ever had: read at 2am, with nothing to open and no notification to miss, by somebody who was only
walking past on their way to the kitchen.

## Why it does not outrank the radio

The real risk is not technical. It is that people begin choosing sockets for where a nightlight looks good rather
than where the mesh needs one, and the bridge quietly ends up in a bad spot.

Precedence settles this without a word of copy: move it somewhere thin and it stops being a nightlight and goes
back to breathing red. The placement instrument stays in charge of its own argument, and the person gets the
feedback in the only currency they were already reading.

## Where the control lives: it is a light in the house

Do not build a nightlight feature. The puck already publishes Home Assistant MQTT discovery for every switch it
can hear (`main.cpp:303`) and already owns `mesh/bridge/<chip>/*`. One more discovery payload makes **the puck
itself** a light — brightness included — and then everything a nightlight needs already exists in the house:
schedules, "good night", all-off, the room tile it appears on. None of it has to be invented and none of it has
to live in firmware, which is the point: firmware holds one setting in NVS and the precedence, and nothing that
needs to know what time it is.

The free win: these pucks sit next to switches that already report motion on vendor field `0x13`. A rule that
lifts the glow from a floor-marker to something you can walk by when the switch beside it sees someone, then
lets it settle, is a brain rule over data that already works.

## The one question, and where it is asked

Once, at the `placing → ready` step of `app/src/BridgeSheet.vue` — the only moment anybody is standing in front
of the object in the place it is going to live:

> **Leave its light on?** It will glow warm through the night, and go straight back to telling you if something
> goes wrong.  — *Leave it on* / *No, dark*

Afterwards it is the device's own tile, like any other light. Never a settings page. This follows
`product-direction-out-of-the-box`: the panel must never send anyone to Home Assistant's UI.

## Color, and the rule that inverts here

`emitter-colors-are-not-screen-colors` says indicator colors want the off-channels at or near zero, because a
pastel emitter reads as white. **The nightlight is the one place that inverts**: it is illuminating a floor, not
signaling, so it wants to be warm and *unsaturated* — the thing a saturated indicator must never be.

That also keeps it from colliding with the instrument. Blinking amber and a steady warm white are not confusable
at a glance, and the two steady states never coexist: once the puck is settled, green has done its job and row
three has the light.

## What it asks of the product board

Three requirements, each the fix for something the devkit got wrong, and all three are cheap on a board we design
rather than buy:

1. **The LED lit however the thing is plugged in.** On the AYWHP/YD-ESP32-S3 clone the WS2812's 5 V rail is fed
   only through the UART-side USB port; through the native port the chip runs and the light is dead. On a devkit
   that is a gotcha. On a product it is a returned unit.
2. **A data line that is actually driven** — a 3.3 V-logic part, or a level shifter. This retires the
   write-on-change workaround as a *workaround*: fades stop being the pale-green flicker bug, and a slow sunset
   ramp or a motion swell becomes safe to write. (Keep write-on-change anyway; it costs nothing.)
3. **An emitter the enclosure can diffuse**, and probably more than one pixel. A single WS2812 behind a pinhole
   is a maker's nightlight — a hard point source you can see the die in. This is an argument for the enclosure
   having a diffusing face, which is a thing it wants for its own sake.

`docs/puck-hardware.md` (rev A) takes all three of these as requirements and answers them: a level shifter for
2, three emitters behind a printed diffuser for 3, and it carries the button from the open questions below as a
footprint. Whether 1.5 mm of white PLA reads as one glow or as three dots is its open question, and it is the
same question as this document's default brightness — both want an eye in a dark hallway rather than a build.

None of these are blockers for building the *software* — the precedence, the entity and the question can all be
built and tested on the desk pucks today. They are what the hardware has to be for the feature to be worth
shipping.

## The build order

1. ~~**Firmware, the state.**~~ **Written, not yet run on hardware (18 September).** `Light::Night` in
   `light.{h,cpp}` painting `WARM` (255/140/45, roughly 2000 K) scaled by `lightNightLevel()`, static between
   transitions and simply dark on a board with only a plain LED. The precedence table is `lightRefresh()` in
   `main.cpp` and lives in that one function. `settled`, `night` and `nightLevel` are in `BridgeConfig`, loaded
   in `loadRing()` (NVS only, no compiled fallback) and written by `configSetNight()` / `configSetSettled()`,
   which write through to both `cfg` and NVS and skip unchanged values — a brightness slider dragged across a
   room would otherwise cost a few hundred erases. Two new cable commands, `set night <0|1> <0-255>` and
   `set settled <0|1>`, take effect **without** an `apply`, because somebody changing the brightness on a cable
   wants to see it change. `status` gains `night=unplaced|on|off`, and `LIGHTS[]` in `bridgeStatusLine()` was
   masked `& 3` — a fifth state does not fit in two bits, and that mask is the one trap in this step.
   `esp32s3-ship` and `esp32dev` (the `#else` path, no RGB) both compile.
2. ~~**Firmware, the entity.**~~ **Written, not yet run on hardware (19 September).** The puck's own HA device
   `mesh_bridge_<chip>` gains a **Nightlight** (`light`, with brightness, `bri_scl` 255) alongside the proxy
   sensor it already had. Retained state on `mesh/bridge/<chip>/night` and `.../night/brightness`, commands on
   `.../night/set` and `.../night/brightness/set`, and `.../settled` + `.../settled/set` for step 3 to use.
   Discovery, the subscriptions and the retained publishes all happen in the existing on-connect block, so a
   broker restart restores the lot. Two decisions worth keeping:

   - **The entity reports the SETTING, not the LED.** They differ whenever the puck is unwell or unplaced,
     because precedence puts a fault above the nightlight. Reporting the LED would show the nightlight as "off"
     the moment a puck lost its broker — an invitation for an automation to turn it back "on" and for the
     household to wonder why nothing happens. What the LED is *actually* doing is a third entity, a diagnostic
     `sensor` on `mesh/bridge/<chip>/light` carrying `looking|heard|night|off`.
   - **Brightness zero is an off.** HA can send a brightness of 0, which would otherwise leave a nightlight that
     is on and invisible — a state nobody can explain. It turns it off and keeps the old level, so turning it
     back on restores the brightness rather than coming up black.

   That diagnostic sensor also answers one of the open questions below — how you ask a settled puck whether it
   is well once green has stopped being the answer — at least for anyone looking at the house rather than at the
   object. The 2am version of that question is still open.
3. ~~**Hub.**~~ **Written and tested (19 September).** `POST /bridge/placed` grew an optional body —
   `{"night": bool, "level": 0-255}` — so the answer rides the existing endpoint and a panel that does not ask
   the question still places a bridge. `Bridges.placed()` then sends the two halves **differently, and that
   difference is the whole of it**:

   - **`settled/set` is retained.** It is the hub's to own, it never changes after placement, and until the puck
     has it the light stays an instrument. Retaining it means a puck that was offline at that exact moment — or
     wiped and flashed again in the same corner — picks it up on its next connect. Replaying it is harmless
     because it is idempotent, and `forget()` now clears it along with `night`, `night/brightness` and `light`,
     which is what stops a bridge that was sent away coming back believing it is still placed.
   - **`night/set` is not retained, and is said exactly once.** From the instant they answer, the setting is the
     household's: the puck holds it in NVS and Home Assistant owns it. A retained placement answer would
     silently overrule somebody turning the nightlight off in February the next time the puck rebooted — a
     failure that would be invisible and maddening, and not retaining is the entire fix.

   A puck that is offline at that moment therefore keeps its green and loses only the nightlight, which is the
   right way round: the instrument survives, the decoration does not. Publishing failures are suppressed rather
   than raised — the broker is not why somebody tapped the button, and a sheet stuck on a step the person has
   already finished is worse than a bridge with no glow.
4. ~~**Panel.**~~ **Built and walked through (19 September).** The question sits between "Leave it here" and the
   brain being told, because the answer travels *with* that message. `BridgeSheet.vue` gains exactly one local
   step, `asking` — and it must stay the only one: nothing about the bridge is decided there, the job is still
   `placing`, and walking away from the question leaves it exactly where it was, to come back on the next poll.
   That is also the answer to "what if nobody answers": nothing is lost and nothing is assumed.
   `placedBridge(night?)` leaves the field out entirely rather than sending `false` when the question was never
   asked — a bridge placed without an answer is not the same as one whose household said no, and only the brain
   should decide what to do with the difference. `BridgeArt` gains a fourth light, `warm`, its four states now a
   lookup rather than a ternary per attribute. Three e2e cases hold it: the question is asked and nothing is sent
   until it is answered, both answers place the bridge, and walking away places nothing.
5. ~~**Motion.**~~ **Built and tested (19 September), with one thing still owed — see below.**
   `brain/hub/nightlight.py`: motion arriving in a bridge's room swells its glow to something you can walk by,
   and it settles once the room has been quiet. Three decisions, each of which was nearly made the other way:

   - **Not two rules in `rules.json`.** The engine can express it — `motion on → device on with brightness`,
     then `idle 60 → device on with brightness` — and it was nearly built that way. But two rules can be
     half-approved, half-edited and half-deleted, and every one of those halves leaves a bedroom corridor at
     full brightness until somebody works out why. A swell and its settle are one behaviour and belong to one
     object that cannot be taken apart.
   - **A lift is not a brightness.** It goes out on a new firmware topic, `night/lift/set`, which moves the
     light and touches neither NVS nor the retained state. As an ordinary brightness this would be two flash
     erases per walk-past for the life of the puck, and it would drag the household's own setting up and down
     in Home Assistant, where what they set is supposed to be what it says. It also means **the puck settles
     itself**: a lift is forgotten on reboot, so a brain that dies mid-swell cannot leave a light bright all
     night. `0` means "back to what they chose", which the puck holds and the brain deliberately does not.
   - **Off until a person turns it on.** This is the part that can be wrong in a way that wakes somebody, so
     nothing enables it but a deliberate act. Four things must all be true before a lift goes out: the puck is
     online, its nightlight is on, the household asked for this, and the motion is in that puck's room.

   The switch is published by the brain rather than the puck — the motion sensors, the rooms and the timer are
   all brain-side, and a flag the firmware would only store and never read is a flag in the wrong place — but it
   rides the puck's topics, so it lands on the puck's own device beside its Nightlight. 14 tests; 954 brain
   tests green.
6. **Hardware.** The three requirements above into the product board spec, alongside the enclosure's diffusing
   face.

Steps 1–4 are the feature. Step 5 is the one that makes people like it.

6. **This hub gets a Bridges section (19 September)** — not in the original build order, and the thing step 5
   turned out to need. Step 5's switch existed only as a Home Assistant entity, which
   `product-direction-out-of-the-box` forbids, and there was nowhere on the panel to put it: **a puck surfaced
   only when something was wrong with it** — a note when it went quiet, a line here when it was a version
   behind — so the one place a household could act on one was a problem report. That is the wrong shape for an
   object that mostly just works.

   `GET /bridge/list` and `POST /bridge/light` in the brain (`Bridges.each()` and `Bridges.light()`), a Bridges
   section on `HubPage.vue` listing every bridge by the room it serves, and `BridgeCard.vue` for one of them:
   whether it is working, the nightlight, how bright it rests, brighten-as-you-pass, its software, and forget.
   Three decisions worth keeping:

   - **Three brightnesses, not a slider.** This panel has no sliders anywhere: brightness is a gesture on the
     thing itself. The nightlight *is* a light in the house, so anyone wanting a level between Dim, Soft and
     Bright has its own tile. What belongs on this card is the handful of decisions about the *bridge*.
   - **A puck the hub has never heard from gets no switches drawn.** `night` comes back `null` rather than
     `false`, and the card says "not heard from yet" — a switch showing "off" for something that has not
     answered is a small lie that costs somebody an evening.
   - **Turning a nightlight down is driving the house, not changing it**, so `/bridge/light` is open like
     `/devices/…/on` rather than gated behind the settings code (`hub/lock.py`'s own line).

   10 brain tests and 3 e2e cases; `/bridge/light` sends one field at a time, so a tap changes what it says and
   nothing else.

**What steps 1 to 4 still owe:** a puck on a cable. `set settled 1` then `set night 1 <level>` should put a settled,
healthy puck into a warm glow; pulling the broker should take it straight back to amber; a reboot should come
back glowing without the hub. None of that has been watched happen, and the default brightness (110) was chosen
on a screen, which `emitter-colours-are-not-screen-colours` is a standing warning about.

## Open

- **A fault at 3am: honest or kind?** Row one says breathing red, at full instrument brightness, in a bedroom
  corridor. The honest answer and the liveable one may differ, and "dim the fault overnight" is a promise-weakening
  change that should be argued, not slipped in.
- **How do you ask a settled puck "are you well?"** Green is gone once row three has the light. Candidates: the
  panel (which knows anyway), a brief green on boot, or `POST /bridge/blink`, which already exists.
- **Is the color the household's choice, or ours?** Recommendation: brightness yes, color no — a warm white we
  pick. Color choice invites a blue nightlight, which is the one thing a nightlight should not be.
- **One pixel or three**, and whether the enclosure's face is edge-lit or front-lit. An industrial design
  question, not a firmware one, but the answer changes the LED count on the board.
- **Does the object want a button?** A tap to make it dark until morning is the obvious physical gesture, and it
  is also a second job for a button that adoption and reset may want anyway.
