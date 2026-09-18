# The puck's light: an instrument first, and then a nightlight

*Written 18 September 2026, from two things said the same day. One: a puck left on a USB wall charger overnight
already worked as a nightlight, by accident, and it was pleasant. Two, and it is the load-bearing one: the shipped
puck is meant to be **a product** — a small, plain relay object sitting out in the open in a living space — not an
ESP32 devkit on a shelf, and part of the job is that it is nice to look at. Its light is the only expressive
surface it has. Nothing in this document is built. The design is settled; what it asks of the hardware, and the
questions that are genuinely open, are at the foot and marked as such.*

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

None of these are blockers for building the *software* — the precedence, the entity and the question can all be
built and tested on the desk pucks today. They are what the hardware has to be for the feature to be worth
shipping.

## The build order

1. **Firmware, the state.** A fourth `Light::Night` in `light.{h,cpp}`, warm and unsaturated, static; the
   precedence table in `lightRefresh()`; a `settled` flag and a `night` setting (on/off + brightness) in
   `BridgeConfig`, in NVS, so it survives a reboot with the hub down.
2. **Firmware, the entity.** `mesh/bridge/<chip>/nightlight` (retained) and `.../nightlight/set`, plus an HA
   discovery payload making the puck's own device a `light` with brightness. Nothing else changes about the
   contract.
3. **Hub.** `brain/hub/bridge.py` marks settled on `POST /bridge/placed` and carries the household's answer
   through to the puck. No new endpoint if the answer rides the existing one.
4. **Panel.** The one question in `BridgeSheet.vue` at `ready`; after that it is an ordinary light on its room's
   tile, with no special-casing.
5. **Motion**, as a brain rule over `0x13` from the switch beside it. Optional, and last, because it is the only
   part that can be wrong in a way that wakes somebody up.
6. **Hardware.** The three requirements above into the product board spec, alongside the enclosure's diffusing
   face.

Steps 1–4 are the feature. Step 5 is the one that makes people like it.

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
