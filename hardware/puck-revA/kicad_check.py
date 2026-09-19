#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""DRC with the zones actually filled. Run this, not bare `kicad-cli pcb drc`.

WHY. `kicad-cli pcb drc` does not fill zones, so on a board that uses pours it reports
pour-connected pads as unconnected, pour-fed vias as dangling, and everything inside an unfilled
pour as SHORTED to it. Reasoning about which of its complaints were "really" artifacts is how I
came to report ten genuine shorts as a false alarm; the GUI's own DRC said otherwise. So the
guesswork is retired: this fills the zones with KiCad's own ZONE_FILLER, writes the filled board to
a temporary file, and runs kicad-cli against that. The numbers then match what the GUI shows.

    ./drc.sh              # the wrapper, which finds KiCad's python for you
    ./kicad_check.py --keep /tmp/filled.kicad_pcb

The board on disk is never modified: filled polygons are derived data.
"""
import argparse, collections, os, pathlib, re, subprocess, sys, tempfile

sys.stdout.reconfigure(line_buffering=True)
HERE = pathlib.Path(__file__).parent
KICAD = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli")

try:
    import pcbnew
except ImportError:
    sys.exit("needs KiCad's own python -- use ./drc.sh, or:\n  /Applications/KiCad/KiCad.app/"
             "Contents/Frameworks/Python.framework/Versions/3.9/bin/python3 kicad_check.py")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=str(HERE / "puck-revA.kicad_pcb"))
    ap.add_argument("--keep", help="also save the zone-filled board here")
    ap.add_argument("--report", help="also save the full DRC report here")
    a = ap.parse_args()

    board = pcbnew.LoadBoard(a.board)
    ok = pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    print(f"zones: {len(board.Zones())}, filled={ok}")

    tmp = a.keep or tempfile.mktemp(suffix=".kicad_pcb")
    pcbnew.SaveBoard(tmp, board)
    # the project carries the design rules; without it DRC falls back to defaults
    src_pro = pathlib.Path(a.board).with_suffix(".kicad_pro")
    if src_pro.exists():
        pathlib.Path(tmp).with_suffix(".kicad_pro").write_text(src_pro.read_text())

    rpt = a.report or tempfile.mktemp(suffix=".rpt")
    subprocess.run([str(KICAD), "pcb", "drc", "--output", rpt,
                    "--severity-error", "--severity-warning", tmp],
                   capture_output=True, check=False)
    text = pathlib.Path(rpt).read_text()

    counts = collections.Counter(re.findall(r"^\[([a-z_]+)\]", text, re.M))
    print(f"\n{sum(counts.values())} violations\n")
    SERIOUS = {"shorting_items", "clearance", "courtyards_overlap", "solder_mask_bridge",
               "track_dangling", "via_dangling", "starved_thermal", "hole_clearance",
               "drill_out_of_range", "copper_edge_clearance"}
    for k, v in counts.most_common():
        mark = "  <-- fix" if k in SERIOUS else ""
        print(f"  {v:4d}  {k}{mark}")

    # Only the unconnected SECTION, which the report puts after its own header. Scanning from each
    # [unconnected_items] tag to the next bracket ran off the end of the last one and swept up net
    # names out of the warnings that followed it -- a net looked unrouted when it was not.
    nets = collections.Counter()
    tail = text.split("unconnected pads **", 1)
    if len(tail) == 2:
        for chunk in tail[1].split("[unconnected_items]")[1:]:
            for n in set(re.findall(r"\[([A-Za-z0-9_+\-]+)\]\s+(?:of|on)", chunk)): nets[n] += 1
    if nets:
        print("\nstill to route, by net:")
        for n, c in nets.most_common(): print(f"  {c:3d}  {n}")

    for f in ([] if a.report else [rpt]) + ([] if a.keep else [tmp]):
        pathlib.Path(f).unlink(missing_ok=True)
    return 0

if __name__ == "__main__":
    code = main(); sys.stdout.flush(); os._exit(code)   # skip wx's noisy teardown
