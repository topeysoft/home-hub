# Nightfall, into the panel

The canvas is at https://claude.ai/code/artifact/060753bd-648a-419a-8973-2badb9f3decb —
three artboards, and every number below is already in
[`Main.dc.html`](Main.dc.html) as working code rather than as a description of
code. When something here is vague, read the artboard: it is the spec.

The direction is a **face**, not a rewrite. A face decides what the panel is
made of; it does not decide what is on it. Everything the panel already knows —
the sky, the tone system, the layouts, the device drawings, the signals — stays
exactly where it is, and Nightfall is one more thing a house can be set to.

## Where this is

All six slices have landed, each as its own commit: `git log --oneline a2cdf1a..HEAD`.
Glass is a face a house can be set to, its material is derived from the sky, the
field carries the blooms, the rail has its focal plane, the pane has its measured
timings, and there is a floor under the whole thing.

One thing is still owed and cannot be paid from here: **the Pi.** `npm run cost`
is the instrument -- point it at a real hub with `BASE=` and it prints what a
rail swipe costs in frames, under each face, on that host. Everything else about
slice 6 is measured; that number is not, and guessing it would be worse than
saying so.

Two things were found under slice 5 rather than written by it, and both are
their own commits before it:

- **There was no frost in the built panel at all.** `panel.css` wrote
  `-webkit-backdrop-filter` by hand next to every standard `backdrop-filter`,
  and the CSS minifier reads that pair as proof the prefixed one covers every
  target: 19 of the file's 23 declarations came out of the build prefixed only.
  Chrome 153 has removed the `-webkit-` alias. So the cards, the rail, both
  panes and the whole of glass had been flat in every build for as long as that
  browser has been current, while the source plainly said blur and every unit
  test passed. The fix is to stop writing the prefix; the build adds it, and
  correctly emits both. `e2e/face.spec.ts` is the guard, and it has to be an
  e2e -- nothing that reads the stylesheet can see this, because the stylesheet
  was right.
- **The pane's close button was thirty pixels off the left of the screen.**
  `[data-face='glass'] .back` declared `position: relative` for the rim's
  containing block, which beats a plain `.opened-close`, so the button fell back
  into the flow and `right: 30px` took it the other way. A wall panel has no
  keyboard, so the veil was the only way out. The containing block belongs to
  the surface, not the face.

Run it: `cd app && npm run build && npm run mock`, then
`localhost:8399/?face=glass&layout=rail&nav=top`, or pick **Glass** under *This
house -> How it looks*. `&at=12:30&wx=sunny` is noon, `&face=paper` is the
before. Every change is scoped under `[data-face='glass']`, so paper is
untouched and that is the thing to check first if something looks wrong.

**One decision is still open, and slice 5 has now run into it twice.** A face
was defined as what the panel is MADE OF, not what is on it — so the material
and the motion have landed on the panel's own arrangement, and the screen still
does not look much like the artboard. It leads with a serif greeting, a next-up
line and the attention strip, so the row starts two thirds down; the weather is
a cloud in the header corner rather than a tall lozenge hung off-card; the type
is Instrument rather than Plus Jakarta; cards are 22px where the artboard is 28.
Those are arrangement, type and radius, and none of them belong to a face.

Closing that gap means a LAYOUT — a third beside stack and rail, in the shape
`layout.ts` already describes — not more face. It is a real piece of work and
nobody has asked for it yet. Slice 5 was worth doing either way, and was: a new
layout would reuse the pane rather than replace it. But the one line of the
slice that could not be done is arrangement — *the row you came from is still
there, dimmed, above the pane* — and the reason is that on this arrangement the
row is not where the pane stops short of. The pane is right; there is nothing
above it to leave uncovered.

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

**1. `face` exists and does nothing.** *(landed)*  `FACES` in `layout.ts` (`paper` — what
the panel is today — and `glass`), an `isFace()` guard, the row in `LookPage`,
the field on `ambient.look`, and the same round-trip through the brain the
other three take. Done when picking it changes a `data-face` attribute on the
shell and nothing else moves.

**2. The material.** *(landed)*  `toneVars` gains the glass block when `face === 'glass'`,
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

**3. The field.** *(landed)*  `Sky.vue` already paints the ramp and the veil. Under `glass`
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

**4. The rail.** *(landed)*  The biggest slice, and the one with the idea in it. `rail`
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

Landed, and it needed almost no new machinery: the rail already drives its edges
from `animation-timeline: view(inline)`, so glass only swaps which keyframes
those two animations run. Paper softens both ends even-handedly; glass does not,
because a focal plane is not even-handed. The lag is `transform` rather than
`translate` because `translate` belongs to the arrival, and those two have
always deliberately stayed off each other's properties.

The weather recedes without being in the rail to know it should — it stays put,
blurs, and drops the reading. That is what the row's own `data-at-start` is now
kept true for on every browser rather than only the ones without scroll-driven
animations.

The lag is a share of the card, not a count of pixels: the row runs from a 248px
glance column to a 372px media card, so a fixed number overlaps the wide ones
barely and the narrow ones twice as much. 45% of the card, less the row's 18px
gap, puts coverage at 50 -> 99 -> 130px through the exit.

One thing that does NOT fix, and it is worth knowing before someone tries again:
the overlap is a during-the-swipe effect, not a resting one. The row snaps to
card boundaries, so once it settles nothing is mid-exit and the receded card
sits entirely behind its neighbour. The reference rests mid-card, which is why
the stack stands still in the drawing. Making it persist at rest means changing
where the rail stops, which is a decision about the rail rather than the face.

The velocity blur is **not** in. It is a second blur on top of one the file
already warns re-rasterises every frame of a swipe, and adding that cost before
slice 6 has measured the first one is backwards. It waits for a number.

**5. The pane.** *(landed)*  `Opened.vue` already rose; it needed the measured timings.
400ms up on `cubic-bezier(.12,.78,.24,1)`, 300ms down on
`cubic-bezier(.4,0,.6,1)`, the object inside travelling further and still
settling at 700ms, the bottom bar leaving 60ms *before* the pane starts and
coming back 180ms after it has gone. The pane stops short of the top bar so the
row you came from is still there, dimmed, above it -- that is what makes it a
drawer rather than a new screen. The room dims; it does not blur.

Landed in three commits, because the timings could not be looked at until the
pane was made of something.

*The room dims; it does not blur* turned out to have a second reason underneath
the stated one. A pane over an already-blurred room is a dark sheet over mush --
the blur the pane is MADE of has nothing left to work on -- and the dim cannot
be a `filter` either, because a filter on `.stage` forms a backdrop root and
silently kills `backdrop-filter` on every card beneath it. It is the same trap
as the rail's blur, which goes on each card and never on the row. So the room
stays where it is and `--glass-scrim` takes it down: the air from under the
pane, deepening as the day does, because a dark room is already most of the way
to being out of the way and a bright one is not.

*A pane is measured against the room, not the sky.* Both panes were still
wearing paper's fixed near-black, invisible while the room behind them was mush
and, once it was not, exactly the hole punched in the daylight `tone.ts` exists
to prevent: at noon the room read L .49 and the pane .13. A card under glass
holds its distance from the sky; a pane does not, because by the time you are
looking at one the sky is not what is behind it. `--pane` is written as what it
does to the scrimmed room -- each stop says how far it lifts what is behind it,
and the painted lightness falls out of that and the stop's own alpha.

The lifts are small, and it took measuring to find out how small. Lifted a
card's distance, at noon the pane is a pale blue sheet with grey type on it: the
muted ink came off the screen at 2.0:1 against paper's 4.4:1 at the same hour.
Which is the other half -- the surface moved, so the ink has to move with it,
the same as on a card. `--pane-ink-2` and `--pane-muted` hold a ratio against
the pane's own foot rather than a colour, and never drop below what paper gives,
so after dark nothing changes at all. Measured back off the screen at noon:
6.1:1 and 4.7:1.

*The timings* needed a real instant to count from, twice, and neither existed.
`shown` cannot flip until the pane has painted once at `translateY(100%)`, two
frames after the bar starts leaving, so the pane's delay is 28ms and those two
frames are the rest of the 60. And the way back used to be counted from
`Opened.vue`'s unmount timeout, which is a `setTimeout` on the same main thread
that is painting a 300ms fall through a 30px blur and runs about 70ms late; a
`closing` flag goes on at the instant the fall begins instead. It is a separate
fact from `!shown` and has to be, because for two frames at the start a pane is
also not shown and CSS cannot tell those apart.

Measured off the transitions' own clocks rather than by sampling frames -- at
1280x800 a frame runs about 25ms while a pane is being painted, which is coarser
than the gaps involved. Bar at 0, veil at 25, pane at 51, landed at 480, the
object still going until 760. The test asserts the ORDER, because that is what
breaks silently and the numbers are load-dependent.

One part of the slice did not land and could not: **the row you came from is not
still there above the pane.** The pane stops short of the top bar as specified --
176px at 1280x800 -- but this panel's home leads with a serif greeting, a
next-up line and the attention strip, so the row does not begin until y 340 and
the pane covers all of it. On the canvas the row starts at the top and the pane
takes its lower two thirds. That is the arrangement, not the face, and it is the
open decision below.

**6. Reduced motion, and the floor.** *(landed, except the Pi)*  All eight moves collapse to
opacity, the field stops drifting, the rail jumps. Then the question this whole
port exists to answer: a Pi 5 at 1280×800, painting `backdrop-filter` on every
card with an animated `filter` on five of them at once. If it will not hold, the
honest answer is that the blur is sized to the host the way everything else is,
and `glass` degrades to a flat tint on the floor rather than the whole face
being abandoned.

*Reduced motion* was almost already true, and checked in a browser rather than
assumed: the blanket block near the top of `panel.css` leaves no animation, no
filter and no transition anywhere under either face, and `Sky.vue` draws its
scene once instead of starting a loop. One thing was a step too far. The rail
did not arm its arrival at all, so the row appeared between two frames, where
the canvas asks for a 180ms fade -- a fade is not vestibular motion, a pop is
only abrupt. The rail now arms it either way and the stylesheet decides what
arriving means, which is the point: a move and its reduced form drifting apart
is what happens when that decision lives in two files. The travel has to be
cancelled explicitly, because `translate` is a plain property and the blanket
block does nothing to it -- otherwise every card sits 696px right for one
painted frame, which is the move this is supposed to remove.

*The floor,* and the measurement reframes it. **Both faces paint the same 13
frosted surfaces** at 1280x800. Paper has always put `--frost` on every tile;
glass adds none. The whole difference is the radius -- 26px against 18 -- plus a
saturate, and on the rail an animated 5px blur where paper animates 6. So the
risk was never whether a host can blur. It is how wide, and that is one number:
`--glass-blur`, with `--pane-blur` beside it.

What `npm run cost` measures at 1280x800 with software rasterisation, which is
the nearest thing to a weak GPU available without one: a 650ms rail swipe holds
every frame under paper and drops about a quarter of them under glass,
repeatably. A radius bill, not a face bill.

The floor itself is built regardless, because there is one state the face could
not survive: a host with no `backdrop-filter` at all. An unblurred glass card is
.34 of a colour over the open sky and hardly a card -- the face would not
degrade, it would vanish. `--glass-flat` and `--pane-flat` are not a second
palette; each stop is the colour its translucent twin composites TO, so the rim,
the sweep and the shadow are all still drawn and only the depth is gone.
`data-flat` carries it rather than `@supports`, for two reasons: a feature query
cannot be switched on to look at, and this is a state the panel will spend its
whole life never being in, so nobody would ever see it -- `?flat=1` does. And
the switch has a second job waiting, because a host that CAN blur but not fast
enough wants exactly the same answer, and that is a measurement rather than a
feature query.

## What is still open

The direction survives the day — the Sky chip on the canvas is the proof, and
the material sheet computes the argument: the band a card sits on runs L .140 at
night to L .492 at noon and nothing inverts across it. But at clear noon this is
a bright blue panel, and the indigo, the inner glow and the orb are an evening
identity. Whether that wants a distinct day face or just this one tracking
lightness is a design decision nobody has made yet, and it does not block
anything above.

Slice 5 put a number on one corner of that. A pane at noon cannot be both lit
glass and carry paper's greys: to give the muted ink paper's 4.4:1 it would have
to come down to a near-black sheet, which is the hole punched in the daylight
all over again. The pane carries its own ink instead, which is the house's own
rule and holds — but it is worth knowing that the day question is not only about
identity. It has a legibility floor under it, and that floor is what decides how
light a pane is allowed to be.

The other unbuilt thing is a screen that is not a rail. A room fits on the
screen, so [`Room.dc.html`](../Room.dc.html) argues it is a ranked grid rather
than something you sweep — and rail-plus-pane is the spine of this direction.
Whether it has an answer there is genuinely unknown.

With all six slices in, what is left is not really port work any more. The Pi
number is a half-hour on the right machine, and `npm run cost` is already
pointed at it. Everything else on this page is a design decision: whether the
day wants a face of its own, whether the sky should suppress its landscape under
glass, whether Home should have a third layout, and whether a room is a rail at
all. The face itself is finished, and every one of those can be answered without
touching it.

The `data-flat` switch is the one seam left half-used. It is wired to the
question a browser can answer -- can this host paint a backdrop-filter -- and
waiting on the one only a measurement can: can it paint one fast enough. If the
Pi says no, that is where the answer goes, and the step before a flat tint is a
smaller `--glass-blur` rather than no glass at all.

## How this work has been going, for whoever picks it up

Small slices, each committed and looked at before the next one starts. The
panel is checked by driving the real thing at 1280x800 against `mock/brain.mjs`
and reading computed styles, not by trusting that the CSS says what it means --
the rail's 56px lag was confirmed by measuring an exiting card at x -294 under
glass against -350 under paper. Slice 5 needed two instruments past that, and
both are worth keeping. For colour, screenshot a clip of the pane and read the
pixels back, because a composite of a gradient over a blurred backdrop is not
anywhere in the computed styles -- that is where 2.0:1 came from, and nothing
else would have found it. For timing, listen for `transitionstart` and
`transitionend` rather than sampling frames: a frame runs about 25ms while a
pane is being painted, which is coarser than the gaps being measured, and a
sampled trace put the bar and the pane at the same instant when they are 51ms
apart. And for cost, `npm run cost` -- a scripted rail swipe with the gaps
between presented frames written down, which is the only one of the three meant
to be run somewhere other than here. `npx vitest run`, `npx playwright test`,
`npx vue-tsc --noEmit -p tsconfig.app.json` and `npx eslint` all pass; the hold
gesture spec flakes under load and passes in isolation.

Findings get written down rather than tuned away. The blooms read as a tint
because the panel's sky is a painted scene and the face was drawn against an
abstract field -- that is in slice 3 as a question, not fixed by raising an
alpha until it looked right. The same goes for the last 9ms of the pane's 60ms
lead: it is one frame, chasing it moved the measurement the wrong way, and the
comment in `panel.css` says so instead of pretending to 60.

And check the built panel, not the dev server. The frost bug above only exists
after minification, so `npm run dev` shows a face that `npm run build` does
not.
