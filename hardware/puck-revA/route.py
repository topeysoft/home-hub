#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copper for puck-revA: the pours, the LED chain, and the stitching that ties them together.

SEPARATE from gen_pcb.py on purpose. gen_pcb.py owns placement and refuses to overwrite a board
that has copper in it; this adds the copper. Run it after gen_pcb.py and before touching the board
in KiCad:

    python3 gen_pcb.py --force && python3 route.py && python3 route.py --check

gen_pcb.py needs --force there because route.py has by then put copper on the board and the guard in
gen_pcb.py is doing its job. That guard is for YOUR hand routing, which no script should ever eat.

WHAT IT DOES, and what it deliberately leaves alone. The regular two-thirds of this board routes
better from a script than by hand, because the ring is eleven copies of one hop and the pours are
two polygons:

  * GND  -- a pour on B.Cu over the whole board, with a stitching via beside every GND pad.
  * VBUS -- a pour on B.Cu as an annulus through r=18.76, with a via down from every VDD pad. The
            ring sorts the rails for us: turned tangentially, every LED puts VDD and DIN on the
            OUTER flank at r=18.76 and VSS and DOUT on the inner one at r=15.59. (I had that
            backwards first and put the power pour straight over the ground pads -- measured off
            the placed board, not assumed, which is how it was caught.) Both pours share the back
            because the back is otherwise empty; VBUS takes priority and GND fills around it.
  * The chain -- eleven identical DOUT -> DIN hops, each two segments, by symmetry.

Everything where judgement beats symmetry is left for a person in the GUI: the USB pair, the 5 V
data line out of U3, I2C, and the module's own fan-out.

ONE THING TO KNOW. `kicad-cli pcb drc` does not fill zones, so it cannot see a pour and will report
every pour-connected pad as unconnected -- measured, not assumed. That is why --check exists: it
works out connectivity itself, counting a pad as joined to a pour when it sits inside the polygon on
a layer the pour is on. Open the board in KiCad and press B to fill, and its own DRC will agree.
"""
import argparse, math, pathlib, re, sys, uuid

HERE = pathlib.Path(__file__).parent
BOARD = HERE / "puck-revA.kicad_pcb"
CX = CY = 100.0
TRACK_W, VIA_D, VIA_DRILL = 0.25, 0.6, 0.3

def uid(): return str(uuid.uuid4())
def f(v): return f"{v:.4f}".rstrip("0").rstrip(".")

def blocks(text, tag):
    for m in re.finditer(r'\(' + tag + r'[\s\n]', text):
        i = m.start(); d = 0
        for k in range(i, len(text)):
            if text[k] == '(': d += 1
            elif text[k] == ')':
                d -= 1
                if d == 0: yield text[i:k + 1], i, k + 1; break

def pads(text):
    """Every pad as (ref, num, x, y, net, layers) in board coordinates."""
    out = []
    for b, _i, _j in blocks(text, "footprint"):
        ref = re.search(r'\(property "Reference" "([^"]*)"', b).group(1)
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+)(?: ([-\d.]+))?\)', b)
        ox, oy, rot = float(at.group(1)), float(at.group(2)), float(at.group(3) or 0)
        a = math.radians(rot)
        for pb, _pi, _pj in blocks(b, "pad"):
            num = re.match(r'\(pad "([^"]*)"', pb).group(1)
            nm = re.search(r'\(net (\d+) "([^"]*)"\)', pb)
            pat = re.search(r'\(at ([-\d.]+) ([-\d.]+)', pb)
            px, py = float(pat.group(1)), float(pat.group(2))
            lay = re.search(r'\(layers ([^)]*)\)', pb)
            out.append((ref, num,
                        ox + px * math.cos(a) + py * math.sin(a),
                        oy - px * math.sin(a) + py * math.cos(a),
                        nm.group(2) if nm else "", lay.group(1) if lay else ""))
    return out

def netids(text):
    return {m.group(2): int(m.group(1)) for m in re.finditer(r'\(net (\d+) "([^"]*)"\)', text)}

def seg(x0, y0, x1, y1, net, layer="F.Cu", w=TRACK_W):
    return (f'\t(segment\n\t\t(start {f(x0)} {f(y0)})\n\t\t(end {f(x1)} {f(y1)})\n'
            f'\t\t(width {w})\n\t\t(layer "{layer}")\n\t\t(net {net})\n\t\t(uuid "{uid()}")\n\t)')

def via(x, y, net):
    return (f'\t(via\n\t\t(at {f(x)} {f(y)})\n\t\t(size {VIA_D})\n\t\t(drill {VIA_DRILL})\n'
            f'\t\t(layers "F.Cu" "B.Cu")\n\t\t(net {net})\n\t\t(uuid "{uid()}")\n\t)')

def seg_dist(a, b, c, d):
    """Closest approach between two segments. Crossing tests alone left nine clearance errors:
    tracks that never meet but run 0.1 mm apart are just as dead on a board."""
    def pt_seg(p, q, r):
        vx, vy = r[0] - q[0], r[1] - q[1]
        L = vx * vx + vy * vy
        t = 0.0 if L == 0 else max(0.0, min(1.0, ((p[0] - q[0]) * vx + (p[1] - q[1]) * vy) / L))
        return math.hypot(p[0] - (q[0] + t * vx), p[1] - (q[1] + t * vy))
    if crosses(a, b, c, d): return 0.0
    return min(pt_seg(a, c, d), pt_seg(b, c, d), pt_seg(c, a, b), pt_seg(d, a, b))


def crosses(a, b, c, d):
    """Do segments ab and cd properly intersect? Stub tracks that cross a chain hop are nine DRC
    errors that no amount of via-placement care prevents, because the fault is the track, not the via."""
    def o(p, q, r):
        v = (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else 2)
    o1, o2, o3, o4 = o(a, b, c), o(a, b, d), o(c, d, a), o(c, d, b)
    return o1 != o2 and o3 != o4


def zone(net, name, layer, poly, clearance=0.3, priority=0):
    pts = "".join(f"\n\t\t\t\t(xy {f(x)} {f(y)})" for x, y in poly)
    return (f'\t(zone\n\t\t(net {net})\n\t\t(net_name "{name}")\n\t\t(layers "{layer}")\n'
            f'\t\t(uuid "{uid()}")\n\t\t(priority {priority})\n\t\t(hatch edge 0.5)\n\t\t(connect_pads\n\t\t\t(clearance {clearance})\n\t\t)\n'
            f'\t\t(min_thickness 0.2)\n\t\t(filled_areas_thickness no)\n'
            f'\t\t(fill\n\t\t\t(thermal_gap 0.4)\n\t\t\t(thermal_bridge_width 0.4)\n\t\t)\n'
            f'\t\t(polygon\n\t\t\t(pts{pts}\n\t\t\t)\n\t\t)\n\t)')

def disc(r, n=180):
    return [(CX + r * math.cos(math.radians(a * 360 / n)), CY + r * math.sin(math.radians(a * 360 / n)))
            for a in range(n)]

def slit_annulus(r_in, r_out, slit_deg=1.2, n=180):
    """An annulus as one simple polygon: out along the slit, round the outside, back in, round the
    inside. KiCad zones take a single outline, so a ring has to be cut somewhere."""
    a0, a1 = slit_deg / 2, 360 - slit_deg / 2
    outer = [a0 + (a1 - a0) * k / n for k in range(n + 1)]
    return ([(CX + r_out * math.cos(math.radians(a)), CY + r_out * math.sin(math.radians(a))) for a in outer] +
            [(CX + r_in * math.cos(math.radians(a)), CY + r_in * math.sin(math.radians(a))) for a in reversed(outer)])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="report connectivity instead of routing")
    args = ap.parse_args()
    t = BOARD.read_text()
    if args.check: return check(t)
    if any(True for _ in blocks(t, "segment")):
        sys.exit("board already has copper; re-run gen_pcb.py first to start clean")

    nid, P = netids(t), pads(t)
    art = []

    # --- the pours ---------------------------------------------------------------------------
    # GND on BOTH layers. That is the whole trick and it took me far too long to reach it: a pour on
    # the component side connects every surface-mount GND pad directly, with no via and no stub, and
    # KiCad clears it around foreign nets on its own. Stitching ~40 GND pads by hand-rolled geometry
    # instead cost shorts, mask bridges and crossing tracks in every arrangement I tried -- I was
    # writing a bad autorouter to solve a problem a pour does not have.
    art.append(zone(nid["GND"], "GND", "F.Cu", disc(24.4), priority=0))
    art.append(zone(nid["GND"], "GND", "B.Cu", disc(24.4), priority=0))
    # VBUS takes the back as a ring through r=18.76, where the LEDs put their VDD pads.
    art.append(zone(nid["VBUS"], "VBUS", "B.Cu", slit_annulus(17.5, 20.1), priority=1))

    byref = {}
    for ref, num, x, y, net, _lay in P: byref.setdefault(ref, {})[num] = (x, y, net)
    n_leds = sum(1 for r in byref if re.fullmatch(r"D\d+", r))

    # --- the LED chain, on the front -----------------------------------------------------------
    # Every hop is identical: DOUT at r=15.59 on one flank to the next DIN at r=18.76 on the other,
    # with the corner at r=13.6, inboard of both, so no run crosses a neighbour's pads.
    hops = 0
    laid = []
    for i in range(1, n_leds):
        a, b = byref[f"D{i}"]["2"], byref[f"D{i+1}"]["4"]
        net = nid[a[2]]
        # THREE segments, not two. A straight dogleg from DOUT out to the next DIN cuts clean across
        # the intervening VSS pad -- twenty DRC hits on one pad of D9 alone. So: drop radially to
        # r=13.6, which is inboard of every pad on the ring and outboard of the module's own pads,
        # travel round at that radius, and climb back out at the far end.
        ra = math.atan2(a[1] - CY, a[0] - CX)
        rb = math.atan2(b[1] - CY, b[0] - CX)
        p1 = (CX + 13.6 * math.cos(ra), CY + 13.6 * math.sin(ra))
        p2 = (CX + 13.6 * math.cos(rb), CY + 13.6 * math.sin(rb))
        for (s0, s1) in (((a[0], a[1]), p1), (p1, p2), (p2, (b[0], b[1]))):
            art.append(seg(s0[0], s0[1], s1[0], s1[1], net)); laid.append((s0, s1))
        hops += 1

    # --- VBUS down to its ring -----------------------------------------------------------------
    # Only the pads that sit ON the ring get a via here, offset along it rather than across it --
    # the ring is 2.6 mm wide and any radial offset big enough to clear a pad leaves it. Everything
    # else on VBUS is named below and left for a person.
    taken = [(x, y, 1.45) for _r, _n, x, y, _net, _l in P]
    counts = {"VBUS": 0}
    missed = []
    for ref, num, x, y, net, lay in P:
        if net != "VBUS" or "F.Cu" not in lay: continue
        d = math.hypot(x - CX, y - CY) or 1
        tx, ty = -(y - CY) / d, (x - CX) / d
        for k in (2.0, -2.0, 2.4, -2.4, 2.9, -2.9):
            vx, vy = x + tx * k, y + ty * k
            if not (17.9 <= math.hypot(vx - CX, vy - CY) <= 19.7): continue
            if any(math.hypot(vx - px, vy - py) < keep for px, py, keep in taken): continue
            if any(seg_dist((x, y), (vx, vy), p0, p1) < 0.45 for p0, p1 in laid): continue
            art.append(seg(x, y, vx, vy, nid[net]))
            art.append(via(vx, vy, nid[net])); taken.append((vx, vy, 0.95))
            laid.append(((x, y), (vx, vy))); counts["VBUS"] += 1
            break
        else:
            missed.append(f"{ref}.{num}")

    BOARD.write_text(t[:t.rindex(")")] + "\n".join(art) + "\n)\n")
    print(f"routed: 3 pours (GND both sides, VBUS ring on the back), {hops} chain hops, "
          f"{counts['VBUS']} VBUS vias")
    if missed: print(f"  left for a person ({len(missed)} VBUS pads): {', '.join(missed)}")

def check(t):
    """Connectivity worked out here rather than asked of KiCad, because `kicad-cli pcb drc` does not
    fill zones and so cannot see a pour.

    A proper graph, not pad-to-segment matching: nodes are pads, track endpoints and vias; a segment
    joins its own two ends; coincident nodes join; and a pour joins everything of its net that lies
    inside it on a layer it covers. The first version of this unioned only pads that touched the
    same segment, so a two-segment dogleg -- which is every hop in the chain -- read as unconnected.
    """
    nid, P = netids(t), pads(t)
    zones = []
    for b, _i, _j in blocks(t, "zone"):
        name = re.search(r'\(net_name "([^"]*)"\)', b).group(1)
        lay = re.search(r'\(layers "([^"]+)"\)', b) or re.search(r'\(layer "([^"]+)"\)', b)
        pts = [(float(x), float(y)) for x, y in re.findall(r'\(xy ([-\d.]+) ([-\d.]+)\)', b)]
        zones.append((name, lay.group(1), pts))
    segs, vias = [], []
    for b, _i, _j in blocks(t, "segment"):
        st = re.search(r'\(start ([-\d.]+) ([-\d.]+)\)', b); en = re.search(r'\(end ([-\d.]+) ([-\d.]+)\)', b)
        segs.append((int(re.search(r'\(net (\d+)\)', b).group(1)),
                     float(st.group(1)), float(st.group(2)), float(en.group(1)), float(en.group(2))))
    for b, _i, _j in blocks(t, "via"):
        at = re.search(r'\(at ([-\d.]+) ([-\d.]+)\)', b)
        vias.append((int(re.search(r'\(net (\d+)\)', b).group(1)), float(at.group(1)), float(at.group(2))))

    def inside(pt, poly):
        x, y = pt; c = False; n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]; x1, y1 = poly[(i + 1) % n]
            if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0 + 1e-12) + x0: c = not c
        return c

    bypad = {}
    for ref, num, x, y, net, lay in P:
        if net: bypad.setdefault(net, []).append((f"{ref}.{num}", x, y, lay))

    print(f"{'net':14s} {'pads':>5s} {'islands':>8s}   what is left")
    done = 0
    for net in sorted(bypad, key=lambda k: -len(bypad[k])):
        nn = nid.get(net)
        nodes = [(x, y, lay) for _n, x, y, lay in bypad[net]]
        npads = len(nodes)
        for sn, x0, y0, x1, y1 in segs:
            if sn == nn: nodes += [(x0, y0, "*"), (x1, y1, "*")]
        for vn, vx, vy in vias:
            if vn == nn: nodes.append((vx, vy, "*"))
        parent = list(range(len(nodes)))
        def find(i):
            while parent[i] != i: parent[i] = parent[parent[i]]; i = parent[i]
            return i
        def union(i, j): parent[find(i)] = find(j)
        base = npads
        for sn, x0, y0, x1, y1 in segs:                 # a segment joins its own two ends
            if sn != nn: continue
            union(base, base + 1); base += 2
        for i in range(len(nodes)):                     # coincident nodes are the same point
            for j in range(i + 1, len(nodes)):
                if math.hypot(nodes[i][0] - nodes[j][0], nodes[i][1] - nodes[j][1]) < 0.35: union(i, j)
        for zname, zlay, poly in zones:                 # a pour joins what sits in it
            if zname != net: continue
            inz = [k for k, (x, y, lay) in enumerate(nodes)
                   if inside((x, y), poly) and (lay == "*" or zlay in lay or "*.Cu" in lay)]
            for k in inz[1:]: union(inz[0], k)
        islands = len({find(k) for k in range(npads)})
        if islands == 1: done += 1
        print(f"{net:14s} {npads:5d} {islands:8d}   {'' if islands == 1 else 'not routed'}")
    print(f"\n{done}/{len(bypad)} nets fully connected")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
