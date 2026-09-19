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
