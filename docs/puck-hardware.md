# The puck as a board: rev A, and what it is for

*Written 19 September 2026, from the decision to actually build one. `design/puck/Shape.dc.html` put four form
factors side by side and chose none of them, on the grounds that the connector is the reversible decision and the
shell is not. This is the board that lets that stay true: one PCB, a USB-C inlet, and several printed shells around
it. KiCad, JLCPCB with assembly, five pieces, FDM shells printed here. Nothing below has been fabricated. Every
number is a design intent until a board comes back and is measured.*

## Rev A is an instrument, not a product

Five boards is the right number because rev A's job is to answer questions that cannot be answered in CAD:

1. **Does the antenna hold?** The whole product is a radio that has to sit within about −80 dBm of a switch
   (`docs/brilliant.md`). A module in a printed shell on a hallway socket is a different antenna from a devkit on a
   desk, and no simulation anybody here can run will settle it.
2. **Does a printed shell diffuse three emitters into one glow?** `docs/puck-light.md` requires "an emitter the
   enclosure can diffuse". Whether 1.5 mm of white PLA at 9 mm standoff reads as a nightlight or as three dots is a
   thing you look at.
3. **Does cold-boot-to-verdict fit inside a person's patience?** `design/puck/Shape.dc.html` names this as the thing
   no drawing can show. It needs a board, a socket and somebody standing in a hallway.
4. **Which shell gets placed well?** Print three, live with each for a week.

So rev A is not a shrunk-down product. It is the cheapest object that can be wrong in a way somebody notices.

**The principle that follows from it: on rev A a footprint is free and a respin is three weeks.** Anything cheap and
plausibly useful gets a footprint, populated or not. The ambient light sensor and the expansion header below are both
there for exactly this reason, and neither has to survive into the product.

## What it does not resolve, and must not pretend to

`docs/brilliant.md` says the right shape for onboarding is "the hub flashing the puck over USB the way it already
adopts radio sticks". `docs/shipping.md` argues radios belong on the network rather than on a USB port, and lands on
"a hub with no USB at all, which is what a CM5 box or a mini PC wants to be". **Both cannot hold for a shipped
unit**, and the answer decides whether the hub seat is the onboarding story or whether `design/puck/Knock.dc.html`
is.

It does not block rev A: USB-C is the power inlet and the console whichever way that goes. It does mean nothing on
this board should be designed *only* to serve the hub seat.

## The parts, and why each one

### The module: ESP32-S3-WROOM-1, 16 MB, and the 16 is not negotiable

A pre-certified module, not a bare chip. For five pieces this is not a close call: the RF is characterized, the
antenna is tuned and matched, and the module carries modular approval — which is the line between a prototype and
an intentional-radiator test. Rolling an antenna needs a VNA and a chamber.

**S3 specifically**, for two reasons already load-bearing in the firmware: native USB gives CDC with no UART bridge,
which is the whole cable console in `src/config.h`; and the second core is what lets the light hold its own task
while the main loop stalls for seconds, which `src/light.h` depends on.

**16 MB of flash is a hard requirement, not a preference.** `partitions-ota.csv` maps `coredump` at `0xFF0000` +
`0x10000`, which lands exactly on 16 MB. An 8 MB module does not "fit more tightly" — the table is invalid, and the
failure mode is the one that file exists to prevent: *"Do not move nvs. Ever."* Order `-N16R8` or `-N16`.

One layout consequence worth knowing before pin assignment: **the `R8` suffix is octal PSRAM, and it consumes
GPIO35/36/37 inside the module.** Nothing here uses PSRAM, so plain `-N16` is the better part and frees three pins.
`-N16R8` is the more reliably stocked one. Check LCSC at order time and take `-N16` if it is there.


**The `-1U`, decided later on 19 September, once the board was laid out.** Same module, same 41 pins, same
16 MB — but a U.FL connector where the `-1` has a trace antenna. The trace antenna needs a board edge and a
48 × 41 mm keepout, and on a 50 mm disc that blocked a third of every LED ring radius permanently; it is what
forced four LEDs instead of three and every asymmetry in the first layout. With the `-1U` the module sits at the
board's center, a 2.4 GHz flex antenna adheres to the inside of the diffuser roof, and the ring goes all the way
round. Cost: one FPC antenna and a U.FL press at assembly. Modular certification later depends on using an
antenna from Espressif's approved list; for five units it does not matter, and it is written down here so it
is not discovered when it does. KiCad 10 ships the `-1U` footprint but not its symbol; the `-1` symbol is
pin-identical (checked pad for pad) and pairs with it.

### The antenna, and the rule that replaced the keepout

With the `-1` the rule was a keepout: the antenna end overhanging the board edge, no copper beneath, nothing
metal within 15 mm, and the whole thing pointed away from the connector. Getting that wrong did not produce a
board that worked slightly worse — it produced FAR breathing red in rooms where a devkit was fine.

With the `-1U` the antenna is a flex on the inside of the diffuser roof, centered over the module, and the rule
becomes simpler: **nothing metal above the board.** The roof is plastic. The screws sit 12 mm below it and the
magnets further still. The LEDs are 9 mm below and 17 mm off-axis. If a later variant ever puts anything metal
in the roof — a button cap, a badge, a heat spreader — that is the moment to think about this again. Rev A's
placement of the flex is an assembly step and therefore a variable; the first five boards are how it gets
measured.

### The light: SK6812-RGBW, eleven of them, chained — and why not a ring at the rim

The change that most improves the actual light is still the part choice: `emitter-colors-are-not-screen-colors`
says a pastel emitter reads as white, which is the problem stated from the other side, at the one moment the
design genuinely wants white. **SK6812-RGBW carries a dedicated warm-white die** instead of faking white by mixing
R+G+B. Row three of the precedence table gets a real warm white, and rows one and two keep R/G/B free and fully
saturated for the instrument — exactly the inversion `docs/puck-light.md` describes.

**Eleven, chained DOUT→DIN on one data line, on a Ø34 ring at 30° spacing.** Eleven rather than twelve because
the twelfth slot is where the USB-C is. This was three, then four, then briefly twenty-one at the rim; the
history is in the commits and the reason it landed here is worth keeping:

- Three could not be placed at all with the `-1` module across the board. Four could, asymmetrically. Both of
  those constraints dissolved with the `-1U`, and the ring became placeable in full for the first time.
- **A ring of light at the rim was considered and rejected on aesthetics.** Twenty-one small LEDs 3.9 mm inside
  the wall would read as a *light ring* — an Echo-Dot signifier, a gadget with a status band — and would bead
  visibly at the base of the band where the wall is only 4.6 mm from the emitters. Every board and doc here
  describes something else: *warm, and still*; a *small, plain relay object*; not *a hard point source you can
  see the die in*. That is an object that **glows evenly from within**, and you get it with fewer LEDs further
  from the wall, not more LEDs closer to it.
- At Ø34 the emitters are 9.0 mm from the roof and 8.4 mm from the wall — deliberately close to equal, so the
  glow is the same from the top and from the side of a body whose orientation nobody can predict — and at
  8.9 mm pitch eleven dice blur into one.

Each LED gets its own 100 nF just inside it on Ø28.6, which is the datasheet's recommendation and costs nothing
as a JLC basic part.

**Current, so nobody is surprised.** Eleven × four dice × ~15 mA is ~0.66 A with every die at full, on top of the
module's ~0.3 A Wi-Fi bursts — right at a 1 A cube's limit. The nightlight runs the W die alone at ~110/255,
about 70 mA, and the three instrument states are single colors. Firmware caps the total; the cube does not get
to find out.

Availability is the risk: WS2812B is the fallback and shares the land pattern.

### The data line, actually driven

`docs/puck-light.md` requirement 2. The part wants V<sub>IH</sub> of 0.7 × V<sub>DD</sub>, so **3.5 V against a 5 V
supply, and 3.3 V logic is out of spec by 200 mV**. That marginality is not a theory — it is the documented cause of
the pale-green flicker, and the reason the light is written only on change.

A **74AHCT1G125** (single gate, SOT-23-5) has TTL input thresholds and swings its output to 5 V. One part, a few
cents, and the workaround stops being a workaround: fades become safe to write, and a sunset ramp or a motion swell
becomes an ordinary thing to do. Keep write-on-change anyway; it costs nothing.

A ~300 Ω series resistor between the buffer and the first DIN, and 100 nF at each LED. Standard, and it damps the
ringing that makes long-ish data lines unreliable.

### Power

5 V in from VBUS, 3.3 V to the module.

- **USB-C receptacle, 16-pin, USB 2.0 only.** CC1 and CC2 each to ground through their own 5.1 kΩ. Leaving these off
  is the single most common way a first board arrives dead: a C-to-C cable will deliver no power at all, and an
  A-to-C cable will, so it looks intermittent rather than broken.
- **USBLC6-2SC6** across D+/D−. Cheap, usually a JLC basic part.
- **AP2112K-3.3** or equivalent, 600 mA. Espressif wants a regulator that can take the Wi-Fi TX transient.
- 22 µF bulk on VBUS, 10 µF plus 100 nF at the module's 3V3 pin, close.

**Thermals, stated accurately:** the LDO drops 1.7 V, so it burns about 0.17 W at the ~100 mA this thing idles at
with BLE and Wi-Fi up, with brief peaks near 0.85 W on a TX burst. That is fine inside a sealed body. A buck would
be more efficient and is not worth changing one more thing for on rev A.

The LEDs run from 5 V directly, not from the 3.3 V rail.

### Buttons, the header, and the sensor that might not be populated

- **BOOT** on GPIO0 and **RESET** on EN. Both needed while prototyping even though USB-CDC handles normal flashing,
  because the time you need them is when USB-CDC is what is broken.
- **One user button**, on a free GPIO with the internal pull-up. This is `docs/puck-light.md`'s open question —
  *"does the object want a button?"* — turned into something you can find out. A tap for "dark until morning" is the
  obvious gesture, and adoption and factory reset may want it anyway.

  The three switches are C&K KMR2 side-actuated tacts (4.2 × 2.8 × 1.4 mm), not the 5.7 mm-deep SKQG first
  specified: once the ring was on the board there was nowhere the bigger part would go. The user button sits at
  the board edge at 180° — the front of the shelf variant, where a person would tap — and is reached through a
  **printed plunger** dropped into the shell's button hole, because a side switch at the board edge sits 2.4 mm
  behind the base wall and a fingertip cannot get there. `enclosure/puck.scad` prints the plunger
  (`show = "plunger"`). BOOT and RESET are the same part and are reached with the shell off.
- **A 4-pin UART header**: GND, GPIO43 (TX), GPIO44 (RX), 3V3. Native USB is not a debug path when native USB is the
  fault.
- **A 6-pad expansion header** at the board edge, inside the shell: 3V3, 5 V, GND and three spare GPIOs, one pair of
  which can serve as a UART or an I2C bus. This is the honest version of "a footprint is free" — it is what lets an
  LD2410 or an AM312 be tried on a bench for a week without committing the shell, the orientation or the power
  budget. **Rev A populates it. The product does not, and the shell has no opening for it** — an exposed header on an
  object in somebody's hallway is a support liability and a tamper surface, and nothing the product does needs it.
- **An ambient light sensor footprint**, unpopulated if you like. The brain can schedule the nightlight over MQTT and
  that is the design — but a sensor is the difference between an object that is correct and one that works when the
  hub is down, and on rev A the footprint is free.

**Pins to keep clear:** GPIO19/20 are USB D−/D+. GPIO26–32 are the SPI flash. GPIO33–37 go to PSRAM on an `R8` part.
GPIO0, 3, 45 and 46 are strapping pins and want nothing that can hold them at boot.

## Why there is no motion sensor in it

Asked and settled on 19 September. The puck does not get a PIR or an mmWave presence module, and the reasons are
about the object rather than about the part.

**Orientation is unknowable.** `design/puck/Shape.dc.html` establishes that a wall-plugged object's rotation is
decided by the outlet it lands in, which is already why the light is a rim and not a face. A PIR needs a lens aimed
at a volume and mmWave needs a boresight. Neither has a rim-shaped answer.

**It would break "one board, several shells."** The light sensor is fine because it sits behind a diffuser that
already exists and needs no aperture of its own. A motion sensor needs a window and a lens, which makes the shell a
second variable in the one experiment rev A exists to run.

**It adds a placement criterion with nothing to report it.** `docs/puck-light.md` already handles the risk that
people choose sockets for where a nightlight looks good rather than where the mesh needs one: a thin spot stops
being a nightlight and goes back to breathing red. That mechanism protects the mesh and nothing else. Nothing would
tell anybody that the PIR is pointed at a wall.

**And presence sensors are tuned things.** Per-gate sensitivity, distance gates, hold times — and 70–100 mA
continuously for an LD2410-class part, roughly doubling this board's idle. `product-direction-out-of-the-box` says
the panel must never send anyone to Home Assistant's UI, and this is the most tuning-hungry device class there is.

Underneath all of it: a presence sensor wants to be placed deliberately and aimed. The puck's position is chosen by
the mesh and its orientation by an outlet. They are opposite objects, and combining them makes both worse.

**The gap this leaves, and where it actually gets closed.** Every switch already carries a PIR on field `0x13`, and
it survives migration — the seven fields plus a power cycle restore `0x48`/`0x4f`, and unsolicited reporting with
them (`docs/brilliant.md`). What it does badly is documented in the same place: the baseline jumps about fiftyfold
when the load comes on (1.8 dark, 92.0 lit, measured on `0x0005`), so the bridge re-learns its floor after every
transition and is blind for roughly two seconds each time. **That is a bridge problem, not a sensor problem.** The
bridge knows when it commanded the load itself, so it can hold the prior motion state across a known local on/off
instead of re-learning blind. Smaller than a sensor, and it improves every switch in the house rather than one
socket.

What stays missing either way is stillness — PIR never sees somebody sitting still and reading. If that turns out to
matter, it is a separate object that gets to be mounted and aimed properly, not a second job for this one.

## What JLCPCB assembly constrains

- **Single-sided assembly**, everything on top, LEDs included — the shell diffuses from above. Halves the cost and
  removes a whole class of process risk.
- **0402 passives are fine** for their process; 0603 if you expect to rework anything by hand. Given five boards and
  a soldering iron in the room, 0603 is the kinder choice and the size difference does not matter on a 50 mm disc.
- **Extended parts carry a per-part setup fee.** The module, the LEDs and the level shifter will all be extended;
  budget for a handful of those on top of the boards.
- 2-layer, 1.6 mm, and a round outline of roughly 50 mm so a 55 mm shell has wall to be made of.
- **Three M2 mounting holes on a 44.8 mm bolt circle at {45°, 165°, 285°}, identical in every shell.** Outside
  the ring, 7.4 mm from the nearest LED, and their heads land below the opaque base rim so they cast no shadow
  on the glow. Solved against the real board by `hardware/puck-revA/gen_pcb.py` rather than chosen. Frozen.

## The enclosure: FDM is an advantage here, not a compromise

Printed white or natural PLA at 1.2–2 mm is a genuinely good diffuser. This is one of the few places where FDM beats
a machined part outright rather than approximating one.

Two things decide whether it reads as a product or as a maker's nightlight:

- **8–10 mm from emitter to diffusing surface.** Closer and you see three distinct hotspots through the wall, which
  is the pinhole problem `docs/puck-light.md` warns about, moved outward by a few millimeters.
- **Print the diffusing face so layer lines do not stripe the glow.** Enough solid perimeters, and the face oriented
  so the lines run with the form rather than across the lit area.

PLA over PETG: better diffusion, stiffer, easier snap fits, and nothing in this object gets near its glass
transition. Snap-fit lid, M2 self-tappers into printed bosses. Nothing metal near the antenna.

Then print the short-tail body, the dock body and the shelf body around identical boards, and let a house settle the
argument that `Shape.dc.html` deliberately left open.

## The build order

1. **KiCad project**, schematic first: module, USB-C with its CC resistors, LDO, level shifter, three LEDs, two
   buttons, the header, the sensor footprint. Symbols and footprints checked against the real datasheets, not
   against memory.
2. **Layout**, antenna keepout first and everything else arranged around it. Board outline and the M2 bolt circle
   frozen at the end of this step, because the shells depend on them.
3. **A shell around the frozen outline**, printed and fitted to nothing — just to confirm the board drops in, the
   USB-C is reachable and the buttons land where fingers go.
4. **Order five**, assembled.
5. **Bring-up in order**: 3.3 V rail before anything, then USB enumeration, then flash the existing `esp32s3-ship`
   image with `-DBRIDGE_RGB_PIN=38`, then the light, then a BLE scan next to a real switch with `tools/bridge_watch.py`
   open.
6. **The four questions**, in a house, with the three shells.

## Open

- **C6 instead of S3, later.** `docs/matter.md` exists and Thread needs 802.15.4, which the S3 does not have. Not
  rev A — single core is the wrong shape for a firmware whose main loop stalls — but the question should be asked
  before anything is tooled.
- **Whether the light sensor gets populated**, which is really the question of how much the object should do with
  the hub down.
- **The button's gesture**, which is what rev A is for.
- **Whether the hub seat survives `docs/shipping.md`**, above. It changes rev B's connector, not rev A's.

