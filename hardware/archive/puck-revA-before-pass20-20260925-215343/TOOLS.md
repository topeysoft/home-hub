# The tooling around this board

Three scripts, and the reason each exists.

## `./drc.sh` — DRC with the zones filled

**Use this, never bare `kicad-cli pcb drc`.** kicad-cli does not fill zones, so on a board with
pours it reports pour-connected pads as unconnected, pour-fed vias as dangling, and everything
inside an unfilled pour as *shorted* to it. Reasoning about which complaints were "really"
artifacts is how ten genuine shorts got reported here as a false alarm; the GUI's DRC said
otherwise. `drc.sh` fills the zones with KiCad's own `ZONE_FILLER` (through `kicad_check.py`, run
under KiCad's bundled Python), writes the filled board to a temp file, and runs DRC on that. The
numbers then match the GUI. The board on disk is never modified.

## `./autoroute.sh` — KiCadRoutingTools

A Rust-accelerated A* router that works on `.kicad_pcb` directly — no Specctra round trip.
Installed at `~/Documents/KiCad/10.0/3rdparty/KiCadRoutingTools`, MIT, and also available in
KiCad's Plugin and Content Manager if you want the GUI (Tools → External Plugins).

It took the board from **51 disconnected pads to 4** in under a second, with zero rule escalations.
What it leaves is the USB pair, which should be hand-routed anyway.

**The flags matter.** Left alone it relaxes the project's design rules to get a route in — on the
first run here it rewrote min hole 0.3 → 0.15 mm and min via 0.45 → 0.25 mm, under JLC's standard
process, and told us plainly that it had. `--escalation off` and `--no-fix-drc-settings` hold the
floor; the geometry is pinned explicitly.

### Driving it yourself, in KiCad

The plugin is installed. **PCB Editor → Tools → External Plugins → KiCadRoutingTools.**

**Select the nets you want in the PCB editor first** — the plugin pre-checks whatever is selected
when it opens, on the Route, Fanout, Planes and Differential tabs. Otherwise pick them from the
Route tab's list, which filters by name and by component.

**The one setting that matters more than the rest: `Escalation`, on the Route tab.** It defaults to
`fab`, which means *"to finish a net, go below the board's own minimums, down to the fab tier
floor."* That is how the first run here produced 0.15 mm holes and 0.25 mm vias against a project
that declares 0.3 and 0.45. Set it to:

- **`off`** — never narrow; a net that will not fit is reported as failed. What `autoroute.sh` uses.
- **`board`** — may narrow to the Board Setup minimums, i.e. what KiCad's DRC accepts.

It discloses every narrowing either way, but only if you read the log. Set it to `off` and the
question does not arise.

Take track width, clearance and via size **from the net class** rather than typing them: this
project's `Default` is 0.25 mm at 0.15, `Power` is 0.5 at 0.2, and those already match the fab.

Two Route-tab features worth knowing for a board this tight:

- **Guide corridor** — draw a polyline on a User layer (say `User.1`), tick *Follow User-layer guide
  path*, and the selected nets follow it. This is the lever for the USB pair if you want it routed
  rather than hand-drawn.
- **Keepout** — draw closed polygons on another User layer (`User.2`), tick *Keep out of User-layer
  polygon(s)*. Useful over the antenna area if anything is ever added above the board.

The other tabs: **Differential** (pair gap, turning radius, polarity fix, GND vias),
**Fanout** (BGA/QFN escape — nothing here needs it), **Planes** (creates pours; this board already
has its own, so leave it alone), **Log** (read this — it is where the narrowing is disclosed).

Settings persist between sessions.

### Or from the command line

```sh
RT=~/Documents/KiCad/10.0/3rdparty/KiCadRoutingTools

python3 $RT/py_router/route.py in.kicad_pcb out.kicad_pcb --nets "*" \
    --escalation off --no-fix-drc-settings \
    --track-width 0.25 --clearance 0.15 --via-size 0.6 --via-drill 0.3

python3 $RT/py_router/route_diff.py in.kicad_pcb -o out.kicad_pcb --nets "USB_D*"
python3 $RT/py_router/check_connected.py out.kicad_pcb     # what is still open
python3 $RT/py_router/check_drc.py out.kicad_pcb           # its own DRC view
```

`--nets` takes globs (`"LED_D*"`) and `--component U1` limits to one part. `./autoroute.sh` is just
the first of these with the flags already right.

**Whatever you route, verify with `./drc.sh`**, not with the tool's own check and not with bare
kicad-cli.

## FreeRouting

Also installed, at `~/Documents/KiCad/10.0/3rdparty/freerouting/freerouting.jar`. **Version 2.1.0,
not the current 2.4.1** — 2.4.1 is compiled for Java 25 and this machine has Java 21, so it will not
start. 2.1.0 runs.

It needs the Specctra round trip, which `pcbnew`'s Python API can drive headlessly
(`ExportSpecctraDSN` / `ImportSpecctraSES`, both verified working here). It is the older, more
widely used option; KiCadRoutingTools did the job without the round trip, so FreeRouting is the
fallback rather than the default.

## What is NOT set up

**ProtoFlow**, from the same search. It is a commercial third-party desktop tool and I have not
verified what it is, who ships it, or what it does with a board file. Nothing here depends on it.
