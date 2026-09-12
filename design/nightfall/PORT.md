# Nightfall, into the panel

The canvas is at https://claude.ai/code/artifact/060753bd-648a-419a-8973-2badb9f3decb —
three artboards, and every number below is already in
[`Main.dc.html`](Main.dc.html) as working code rather than as a description of
code. When something here is vague, read the artboard: it is the spec.

The direction is a **face**, not a rewrite. A face decides what the panel is
made of; it does not decide what is on it. Everything the panel already knows —
the sky, the tone system, the layouts, the device drawings, the signals — stays
exactly where it is, and Nightfall is one more thing a house can be set to.

## The seam

`toneVars(elevation, condition, tone)` in [`tone.ts`](../../app/src/tone.ts)
already turns *what the sky is doing* into *the custom properties the panel
paints with*, and the shell binds the result as a style so every card inherits
it. That is the whole hook. Nightfall adds properties to that object; it does
not add a second way of colouring anything.

`LookPage.vue` already picks a tone, a layout and a nav, and each is a short
table with an `is*()` guard and a test that every entry has a name and a line
saying who it is for. A face is a fourth table of exactly that shape.

## Slices, in an order where each one lands on its own

Each of these is meant to be committed and looked at before the next one
starts. Nothing below needs the slice after it to be worth having.

**1. `face` exists and does nothing.** `FACES` in `layout.ts` (`paper` — what
the panel is today — and `glass`), an `isFace()` guard, the row in `LookPage`,
the field on `ambient.look`, and the same round-trip through the brain the
other three take. Done when picking it changes a `data-face` attribute on the
shell and nothing else moves.

**2. The material.** `toneVars` gains the glass block when `face === 'glass'`,
derived from the `ground(el, condition)` it already computes:

| property        | value                                                      |
| --------------- | ---------------------------------------------------------- |
| `--glass`       | three-stop 148deg, `oklch(ground.L + .10 … / .34 → .12)`     |
| `--rim`         | 158deg, catch `.74 → .40`, shadow `.02 → .20`, as `bright` runs `0 → 1` |
| `--inner`       | `inset 0 -46px 56px -48px` the sky's top band, darkened      |
| `--drop`        | tightens and lightens as the day lightens                    |
| `--sweep`       | `.15 → .07`                                                 |
| `--glass-sat`   | `1.7 → 1.15`                                                |

where `bright = clamp((ground.L - .18) / .34)`. The rim swapping ends is the
part that matters: on a dark field you see the catch along the top, at noon the
shadow under the foot, which is what glass does. `panel.css` reads these instead
of its literals under `[data-face="glass"]`; the existing warm tokens are left
alone. `tone.test.ts` is where this is held honest — the glass L has to track
`ground.L` at every hour and the rim has to invert past `bright` .5.

**3. The field.** `Sky.vue` already paints the ramp and the veil. Under `glass`
it also lays the four blooms on at low alpha — character, not lightness. The
lightness must stay the sky's own, because `ground()` is what every card is
measured against and a field painted darker than `ground` makes every distance
in the system a lie. That was the one real mistake of the daylight pass; do not
repeat it.

Landed, with one thing found. This panel's sky is a painted scene — a ramp, a
horizon, rolling ground under it, stars, drifting cloud — where the face was
drawn against an abstract field. Blooms laid on a scene read as a tint rather
than as the field, which is why the difference between paper and glass is
quieter in the app than it is on the canvas. Whether glass wants the landscape
suppressed, or wants these carried inside the canvas rather than over it, is a
design call nobody has made.

**4. The rail.** The biggest slice, and the one with the idea in it. `rail`
layout already sweeps; what it does not have is a focal plane. Depth is one
idea, not three — further back is blurrier, dimmer **and** slower:

- the cards travel 1:1, the card just passed gives back a third of the travel
  so the one in focus overtakes and covers it, and the sky gives back nearly
  all of it
- what has gone past goes to `blur(5px)` at `.6`; the sky to `blur(5px)` at
  `.8`, and the readout hung in front of it fades out entirely
- on top, small: `blur(2.5px)`, 150ms in and 500ms off, so even the cards that
  end sharp are soft in the middle of the move

**The blur goes on each card, never on the rail.** A `filter` on an ancestor
forms a backdrop root, which silently kills `backdrop-filter` on everything
beneath it, and the glass goes flat mid-swipe. Same reason the wake's
`animation-fill-mode` is `backwards` and not `both`.

**5. The pane.** `Opened.vue` already rises; it needs the measured timings.
400ms up on `cubic-bezier(.12,.78,.24,1)`, 300ms down on
`cubic-bezier(.4,0,.6,1)`, the object inside travelling further and still
settling at 700ms, the bottom bar leaving 60ms *before* the pane starts and
coming back 180ms after it has gone. The pane stops short of the top bar so the
row you came from is still there, dimmed, above it — that is what makes it a
drawer rather than a new screen. The room dims; it does not blur.

**6. Reduced motion, and the floor.** All eight moves collapse to opacity, the
field stops drifting, the rail jumps. Then the question this whole port exists
to answer: a Pi 5 at 1280×800, painting `backdrop-filter` on every card with an
animated `filter` on five of them at once. If it will not hold, the honest
answer is that the blur is sized to the host the way everything else is, and
`glass` degrades to a flat tint on the floor rather than the whole face being
abandoned.

## What is still open

The direction survives the day — the Sky chip on the canvas is the proof, and
the material sheet computes the argument: the band a card sits on runs L .140 at
night to L .492 at noon and nothing inverts across it. But at clear noon this is
a bright blue panel, and the indigo, the inner glow and the orb are an evening
identity. Whether that wants a distinct day face or just this one tracking
lightness is a design decision nobody has made yet, and it does not block
anything above.

The other unbuilt thing is a screen that is not a rail. A room fits on the
screen, so [`Room.dc.html`](../Room.dc.html) argues it is a ranked grid rather
than something you sweep — and rail-plus-pane is the spine of this direction.
Whether it has an answer there is genuinely unknown.
