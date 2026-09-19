#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""puck-revA.kicad_pcb: the board outline, the holes, and the placements the enclosure depends on.

Nets and parts come from gen_sch.PARTS, so the board and the schematic cannot disagree about what is
on them. Routing is not attempted and never will be here -- this exists so the geometry the shell
needs is in the file rather than in somebody's head, and so the ratsnest is right when you open it.

WHAT IS FIXED HERE, and must not be nudged without changing enclosure/puck.scad to match:

  * BOARD is 50 mm. The 54.8 mm in puck.scad is the SHELL; board_d there is 50.
  * U1's antenna end sits flush with the board edge at 180 deg, pointing away from the connector,
    because a USB cube and its cable are the nearest metal this object ever has. The footprint
    carries Espressif's own keepout zone, so placing it correctly brings the keepout with it.
  * J1's mouth sits at the board edge at 0 deg, under the enclosure's notch.
  * THREE M2 holes at r=21 on {24, 144, 264}: a 42 mm bolt circle, not the 40 mm first drawn.
    At 40 mm no equilateral trio clears the LEDs, the module and the connector at once. This is the
    circle every shell shares -- enclosure/puck.scad must agree, and then it is frozen.
  * FOUR LEDs at r=17, not three. See below -- this is the one thing here that contradicts the docs.

WHY FOUR LEDS. docs/puck-hardware.md says three, and three does not fit. The module is 18x25.5 and
lies across the board from the 180 deg edge; the connector occupies the 0 deg edge. Between them they
block every ring angle in (129,231) and (328,32), and an equilateral triple always lands one LED in
one of those -- proven by exhaustive search over every angle AND every ring radius that keeps the
emitters 8-10 mm off the diffuser. Growing the ring to r>=19 does admit a symmetric quad, but then
the radial standoff falls to 6.4 mm and the rim hotspots, so that cure is worse than the disease.

Four at {43, 128, 232, 317} keeps r=17 and therefore the 8.4 mm radial standoff, and spreads them
with a smallest gap of 85 deg where 90 would be perfect. The two wider gaps fall at 0 and 180: the
connector notch, which is already a hole in the glow, and the antenna side.
"""
import argparse, math, pathlib, re, sys, uuid
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_sch import PARTS, PROJECT

# Footprints whose F.CrtYd is not a courtyard but a keepout, and so must be packed by body+pads.
BODY_BOX = {"RF_Module:ESP32-S3-WROOM-1"}

FPDIR = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
HERE = pathlib.Path(__file__).parent
CX = CY = 100.0
BOARD_R = 25.0
BOLT_R, BOLT_ANGLES = 21.0, [24, 144, 264]
LED_R,  LED_ANGLES  = 17.0, [43, 128, 232, 317]
LED_ORDER = ["D1", "D2", "D3", "D4"]

def polar(theta, r):
    """Board angle -> sheet xy, using the enclosure's convention: angles run counter-clockwise as
    seen from the component side, which is how puck.scad is drawn and how you look at the thing."""
    return (CX + r * math.cos(math.radians(theta)), CY - r * math.sin(math.radians(theta)))

FIXED = {
    "U1": (CX - (BOARD_R - 12.75), CY, 90),      # antenna end flush with the 180 deg edge
    "J1": (CX + (BOARD_R - 3.67), CY, 90),       # mouth at the 0 deg edge
}
for ref, th in zip(LED_ORDER, LED_ANGLES):
    x, y = polar(th, LED_R)
    FIXED[ref] = (x, y, th)

def sexp(text, tag, start=0):
    for m in re.finditer(r'\(' + tag + r'[\s\n]', text[start:]):
        i = start + m.start(); d = 0
        for k in range(i, len(text)):
            if text[k] == '(': d += 1
            elif text[k] == ')':
                d -= 1
                if d == 0:
                    yield text[i:k + 1], i, k + 1
                    break

def mod_text(fp):
    lib, name = fp.split(":", 1)
    p = FPDIR / f"{lib}.pretty" / f"{name}.kicad_mod"
    if not p.exists(): sys.exit(f"no such footprint: {p}")
    return p.read_text()

def courtyard_wh(fp):
    """The physical extent of a part: its pads union its F.Fab body.

    NOT the courtyard. On ESP32-S3-WROOM-1 the F.CrtYd *is* Espressif's antenna keepout -- 48 x 41 mm
    -- and using it as a collision box sterilises a 50 mm board completely, which is how this was
    found. The keepout still matters, but on this board its on-board part lies under the module
    itself (the antenna is at the edge and the zone runs outward into free air), so the body is the
    right thing to pack against.
    """
    # The courtyard is the right packing box for everything whose courtyard is a courtyard.
    layer = "F.Fab" if fp in BODY_BOX else "F.CrtYd"
    t = mod_text(fp); pts = []
    for tag in ("fp_line", "fp_poly", "fp_rect", "fp_circle"):
        for b, _i, _j in sexp(t, tag):
            if f'"{layer}"' not in b: continue
            pts += [(float(x), float(y)) for x, y in
                    re.findall(r'\((?:start|end|xy|center) ([-\d.]+) ([-\d.]+)\)', b)]
    for m in re.finditer(r'\(pad "[^"]+"[\s\S]{0,240}?\(at ([-\d.]+) ([-\d.]+)[^)]*\)'
                         r'[\s\S]{0,80}?\(size ([-\d.]+) ([-\d.]+)\)', t):
        x, y, w, h = (float(g) for g in m.groups())
        pts += [(x - w / 2, y - h / 2), (x + w / 2, y + h / 2)]
    if not pts: pts = [(0, 0)]
    xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
    return (max(xs) - min(xs), max(ys) - min(ys))


def rot_wh(wh, rot):
    w, h = wh; a = math.radians(rot)
    return (abs(w * math.cos(a)) + abs(h * math.sin(a)),
            abs(w * math.sin(a)) + abs(h * math.cos(a)))


def courtyard_r(fp):
    t = mod_text(fp); pts = []
    for tag in ("fp_line", "fp_poly", "fp_rect", "fp_circle"):
        for b, _i, _j in sexp(t, tag):
            if '"F.CrtYd"' not in b: continue
            pts += [(float(x), float(y)) for x, y in
                    re.findall(r'\((?:start|end|xy|center) ([-\d.]+) ([-\d.]+)\)', b)]
    if not pts:
        pts = [(float(m.group(1)), float(m.group(2)))
               for m in re.finditer(r'\(pad "[^"]+"[\s\S]{0,200}?\(at ([-\d.]+) ([-\d.]+)', t)] or [(0, 0)]
        pts = [(p[0], p[1]) for p in pts]
    return max(math.hypot(*p) for p in pts)

def uid(): return str(uuid.uuid4())
def mm(v): return f"{v:.4f}".rstrip("0").rstrip(".")

def board_footprint(ref, fp, value, x, y, rot, netmap, nets):
    t = mod_text(fp)
    body, i, j = next(sexp(t, "footprint"))
    inner = body[body.index('"', body.index('"') + 1) + 1: body.rindex(")")]
    # drop the standalone-file preamble; a board footprint does not carry them
    for tag in ("version", "generator", "generator_version"):
        for b, a, c in list(sexp(inner, tag)):
            inner = inner[:a] + inner[c:]; break
    # pads get their net; a pad with no net in PARTS is intentionally floating
    out, last = [], 0
    for b, a, c in list(sexp(inner, "pad")):
        m = re.match(r'\(pad "([^"]*)"', b)          # mounting holes carry unnamed NPTH pads
        net = netmap.get(m.group(1)) if m else None
        # A board file stores pad ORIENTATION absolutely while pad POSITION stays footprint-local,
        # so a rotated footprint needs its own rotation added to every pad. Leaving it out put U1's
        # 1.5 mm-wide pads on a 1.27 mm pitch and DRC called them shorted, which they were.
        if rot:
            def turn(mm_):
                a = float(mm_.group(3) or 0) + rot
                return f'(at {mm_.group(1)} {mm_.group(2)} {a % 360:g})'
            b = re.sub(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', turn, b, count=1)
        if net is not None:
            b = b[:b.rindex(")")] + f'\n\t\t(net {nets[net]} "{net}")\n\t)'
        out.append(inner[last:a] + b); last = c
    inner = "".join(out) + inner[last:]
    # references and values, so the board reads like the schematic
    inner = re.sub(r'(\(property "Reference" )"[^"]*"', r'\1"' + ref + '"', inner, count=1)
    inner = re.sub(r'(\(property "Value" )"[^"]*"', r'\1"' + value.replace('"', "'") + '"', inner, count=1)
    return (f'\t(footprint "{fp}"\n\t\t(layer "F.Cu")\n\t\t(uuid "{uid()}")\n'
            f'\t\t(at {mm(x)} {mm(y)} {mm(rot)})\n' + inner + "\n\t)")

LAYERS = """\t(layers
\t\t(0 "F.Cu" signal)
\t\t(31 "B.Cu" signal)
\t\t(32 "B.Adhes" user "B.Adhesive")
\t\t(33 "F.Adhes" user "F.Adhesive")
\t\t(34 "B.Paste" user)
\t\t(35 "F.Paste" user)
\t\t(36 "B.SilkS" user "B.Silkscreen")
\t\t(37 "F.SilkS" user "F.Silkscreen")
\t\t(38 "B.Mask" user)
\t\t(39 "F.Mask" user)
\t\t(40 "Dwgs.User" user "User.Drawings")
\t\t(41 "Cmts.User" user "User.Comments")
\t\t(42 "Eco1.User" user "User.Eco1")
\t\t(43 "Eco2.User" user "User.Eco2")
\t\t(44 "Edge.Cuts" user)
\t\t(45 "Margin" user)
\t\t(46 "B.CrtYd" user "B.Courtyard")
\t\t(47 "F.CrtYd" user "F.Courtyard")
\t\t(48 "B.Fab" user)
\t\t(49 "F.Fab" user)
\t)"""

def main():
    real = {r: v for r, v in PARTS.items() if not r.startswith("#")}
    nets = {"": 0}
    for _r, (_l, _n, _v, _f, nm) in sorted(real.items()):
        for net in nm.values(): nets.setdefault(net, len(nets))

    size = {r: courtyard_wh(v[3]) for r, v in real.items() if v[3]}
    for r, v in real.items():
        if not v[3]: sys.exit(f"{r} has no footprint; assign one in gen_sch.PARTS")

    def fits(x, y, w, h):
        """Whole courtyard inside the board, with a little edge margin."""
        return all(math.hypot(x + sx * w / 2 - CX, y + sy * h / 2 - CY) <= BOARD_R - 0.4
                   for sx in (-1, 1) for sy in (-1, 1))

    placed, boxes = dict(FIXED), []
    for ref, (x, y, rot) in FIXED.items():
        w, h = rot_wh(size[ref], rot); boxes.append((x, y, w, h))
    for th in BOLT_ANGLES:
        x, y = polar(th, BOLT_R); boxes.append((x, y, 4.4, 4.4))

    def clear(x, y, w, h):
        return not any(abs(x - bx) < (w + bw) / 2 + 0.9 and abs(y - by) < (h + bh) / 2 + 0.9
                       for bx, by, bw, bh in boxes)

    rest = sorted((r for r in real if r not in placed), key=lambda r: -max(size[r]))
    grid = [(CX + i * 0.5, CY + j * 0.5) for i in range(-50, 51) for j in range(-50, 51)]
    grid.sort(key=lambda q: -(q[0] - CX))          # fill the free +X half first
    for ref in rest:
        for rot in (0, 90):
            w, h = rot_wh(size[ref], rot)
            hit = next(((x, y) for (x, y) in grid if fits(x, y, w, h) and clear(x, y, w, h)), None)
            if hit:
                placed[ref] = (hit[0], hit[1], rot); boxes.append((hit[0], hit[1], w, h)); break
        else:
            sys.exit(f"nowhere to put {ref} ({size[ref][0]:.1f}x{size[ref][1]:.1f} mm); board too full")

    fps = [board_footprint(ref, real[ref][3], real[ref][2], *placed[ref], real[ref][4], nets)
           for ref in sorted(real)]
    for n, th in enumerate(BOLT_ANGLES):
        x, y = polar(th, BOLT_R)
        fps.append(board_footprint(f"H{n+1}", "MountingHole:MountingHole_2.2mm_M2", "M2",
                                   x, y, 0, {}, nets))

    edge = (f'\t(gr_circle\n\t\t(center {mm(CX)} {mm(CY)})\n\t\t(end {mm(CX + BOARD_R)} {mm(CY)})\n'
            f'\t\t(stroke (width 0.1) (type default))\n\t\t(fill none)\n\t\t(layer "Edge.Cuts")\n'
            f'\t\t(uuid "{uid()}")\n\t)')
    netdefs = "\n".join(f'\t(net {i} "{n}")' for n, i in sorted(nets.items(), key=lambda kv: kv[1]))
    out = (f'(kicad_pcb\n\t(version 20240108)\n\t(generator "gen_pcb.py")\n'
           f'\t(generator_version "8.0")\n'
           f'\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n\t(paper "A4")\n'
           + LAYERS + "\n\t(setup\n\t\t(pad_to_mask_clearance 0)\n\t)\n"
           + netdefs + "\n" + "\n".join(fps) + "\n" + edge + "\n)\n")
    d = sum(1 if c == "(" else -1 if c == ")" else 0 for c in out)
    assert d == 0, f"unbalanced s-expression: {d}"
    p = HERE / f"{PROJECT}.kicad_pcb"
    # Routing is hand work and this generator would erase it without noticing. Once the board has
    # tracks or vias in it, regenerating is almost certainly a mistake -- say so and stop.
    if p.exists() and not FORCE:
        old = p.read_text()
        laid = old.count("(segment") + old.count("(via") + old.count("(zone")
        if laid:
            sys.exit(f"{p.name} already has {laid} tracks/vias/zones in it -- regenerating would "
                     f"throw that away.\n  Re-run with --force if you really mean to start over, "
                     f"or edit the board in KiCad from here.")
    p.write_text(out)
    print(f"{p.name}: {len(real)} parts + {len(BOLT_ANGLES)} holes, {len(nets) - 1} nets, "
          f"board {BOARD_R * 2:.1f} mm")
    print(f"  U1 antenna edge at x={mm(CX - BOARD_R)} (180 deg), J1 mouth at x={mm(CX + BOARD_R)} (0 deg)")
    print(f"  LEDs r={LED_R} at {LED_ANGLES}; M2 r={BOLT_R} at {BOLT_ANGLES}")

FORCE = False

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="overwrite a board that already has routing in it")
    FORCE = ap.parse_args().force
    main()
