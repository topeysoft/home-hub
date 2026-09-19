#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""puck-revA.kicad_pcb: the board outline, the holes, and the placements the enclosure depends on.

Nets and parts come from gen_sch.PARTS, so the board and the schematic cannot disagree about what is
on them. Routing is not attempted and never will be here -- this exists so the geometry the shell
needs is in the file rather than in somebody's head, and so the ratsnest is right when you open it.

WHAT IS FIXED HERE, and must not be nudged without changing enclosure/puck.scad to match:

  * BOARD is 50 mm. The 54.8 mm in puck.scad is the SHELL; board_d there is 50.
  * U1 sits at the CENTRE. It is the -1U: a U.FL instead of a trace antenna, so the antenna is a
    flex adhered inside the diffuser roof and nothing about the module wants a board edge. That
    one change is what made the ring placeable at all -- the -1's edge antenna and its keepout
    blocked a third of every ring radius, permanently, and forced every asymmetry before this.
  * J1's mouth sits at the board edge at 0 deg, under the enclosure's notch.
  * THE RING: N_LEDS SK6812-RGBW on r=17 at 30 deg spacing, 30..330, with the twelfth slot empty
    because it is where the connector is. r=17 and not the rim ON PURPOSE: this object glows, it
    does not wear a light ring, and ~9 mm from emitter to roof AND to wall is what blurs eleven
    dice into one warm body. The four 100 nF are packed with the other passives; see gen_sch.py for why four.
  * THREE M2 holes at r=22.4 on {45, 165, 285}, OUTSIDE the ring and 7.4 mm from the nearest LED.
    The screw heads land at z 7.2-9, below the opaque base rim at 11.2, so they cast no shadow on
    the visible band. This is the circle every shell shares. Freeze it.
"""
import argparse, math, pathlib, re, sys, uuid
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from gen_sch import PARTS, PROJECT, N_LEDS

# Footprints whose F.CrtYd is not a courtyard but a keepout, and so must be packed by body+pads.
# Empty now: the -1U's courtyard is a courtyard. The -1's was Espressif's antenna keepout, 48 x 41
# mm, which is how this mechanism came to exist -- see courtyard_wh.
BODY_BOX = set()

FPDIR = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
HERE = pathlib.Path(__file__).parent
CX = CY = 100.0
BOARD_R = 25.0
BOLT_R, BOLT_ANGLES = 22.4, [45, 165, 285]
LED_R = 17.0
LED_ANGLES = [30 * (i + 1) for i in range(N_LEDS)]          # 30..330; 0 is the connector
LED_ORDER = [f"D{i}" for i in range(1, N_LEDS + 1)]

def polar(theta, r):
    """Board angle -> sheet xy, using the enclosure's convention: angles run counter-clockwise as
    seen from the component side, which is how puck.scad is drawn and how you look at the thing."""
    return (CX + r * math.cos(math.radians(theta)), CY - r * math.sin(math.radians(theta)))

FIXED = {
    "U1": (CX, CY, 0),                            # centre: nothing about a U.FL wants an edge
    "J1": (CX + (BOARD_R - 3.67), CY, 90),       # mouth at the 0 deg edge
}
# LED rotation is th+270, not th: that lays the 5050's SHORT axis radially (courtyard out to 19.75,
# not 20.45, which is the difference between the outer ring fitting and J2's pin 4 shorting to an LED
# pad), and it points each DOUT (local -X) at the next LED around the ring instead of the previous.
for n, (ref, th) in enumerate(zip(LED_ORDER, LED_ANGLES), 1):
    x, y = polar(th, LED_R); FIXED[ref] = (x, y, (th + 270) % 360)



# The rest of the big parts go on an outer ring, packed along two arcs from their REAL courtyard
# widths with a 0.4 mm gap -- hand-estimated half-angles overlapped the headers, measured ones do
# not. The outer band is under the diffuser's skirt, which starts 1.6 mm above the board: the 4.3 mm
# headers must stay inside r=23.15, so they ride a smaller radius than the 1.4 mm switches and the
# SOT-23s. The user button is pinned at 180, the front of the shelf variant, where you would tap it,
# with its actuator (local +Y) pointing out through the wall. Passives are left to the packer: it
# only ever failed on big parts, and where a 0603 lands is a routing convenience, not a decision.
# The outer ring, assigned by CIRCUIT rather than packed by index. The first version packed parts
# in list order and put the USB ESD diode 39 mm from the connector it protects and the 22 uF bulk
# 43 mm from the regulator it feeds -- both useless there, and no amount of routing fixes it. What
# is adjacent here is adjacent for a reason:
#
#   R1 R2 U4 hug J1     CC pulldowns and the ESD clamp belong at the port, not near it
#   C1 sits on U2       input bulk, on the regulator's own VIN
#   U3 sits near D1     the level shifter's 5 V output runs straight into the chain's first LED
#
# Holes at 45/165/285 and J1 spanning 346..14 are the fixed obstacles; everything below is checked
# against them and against its neighbours at generation time.
OUTER = {
    "R2": 337.0, "R1": 22.0,                     # CC pulldowns, either side of J1
    "U3": 60.0,                                  # level shifter -> D1 at 30 deg
    "U2": 78.0, "C1": 90.0,                      # regulator and its input bulk
    "J2": 105.0, "J3": 122.0,                    # UART, then EXP
    "SW1": 141.0, "SW3": 180.0, "SW2": 210.0,    # BOOT, USER (front), RST
    "U5": 234.0,                                 # ambient light, DNP
}
OUTER_R = {"J2": 21.6, "J3": 21.6}            # 4.3 mm tall: inside the skirt; the rest ride at 22.2

# Inboard, at r=12, each near what it serves. U1's 3V3 pin is at ~157 deg, its EN at ~150.
INNER_R = 12.0

# U4 is pinned, not preferred. It is the ESD clamp and it only does its job at the port: the outer
# ring pushed it past the mounting hole at 45 deg to 21 mm away, which is a diode that protects
# nothing. There is no LED at 0 deg -- that slot is the connector -- so it sits in the ring itself,
# directly inboard of J1 and 7 mm from it, with the D+/D- pair running straight out to the pads.
PINNED_POLAR = {"U4": (14.2, 0.0)}
INNER_PREF = {"C3": 157, "C2": 78, "R3": 145, "C7": 133, "R4": 45, "R5": 300, "R6": 312}

# SILKSCREEN. Function labels beat reference designators: BOOT is what you need to read, SW1 is what
# you look up. The switches and headers get a deliberate label on the free annulus between the
# module and the LED ring -- the one place with room for text -- each on the same radial line as the
# part it names, which is what makes it unambiguous nine millimetres away.
#
# And EVERY Value is hidden. "SK6812-RGBW" eleven times around the ring, plus AP2112K-3.3,
# 74AHCT1G125, USBLC6-2SC6 and a part number long enough to run off the board, was almost the whole
# silkscreen and none of the information -- values live in the BOM and the schematic.
SILK_LABEL = {"SW1": "BOOT", "SW2": "RST", "SW3": "USR", "J2": "UART", "J3": "EXP"}
SILK_R = 13.3
SILK_SIZE = 1.2

# LED and passive reference designators move to F.Fab, where assembly documentation expects them.
# D1..D11 and C101..C104 auto-placed around a 34 mm ring collide with each other and with the
# labels above, and none of them is something a person reads off a silkscreen. The parts you DO
# hunt for by eye -- switches, headers, connector, ICs, mounting holes -- keep theirs.
FAB_REF_PREFIX = ("D", "C", "R")

def tangential(fp, th):
    """Rotation that lays a part's long axis along the ring at angle th. A footprint's local +X ends
    up at board angle rot, and its local +Y at rot+270."""
    w, h = courtyard_wh(fp)
    return (th + 90) % 360 if w >= h else (th + 180) % 360

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


def courtyard_center(fp):
    """Where the courtyard's centre sits relative to the footprint origin, in local mm.

    Pin-header footprints are anchored at pin 1, not at the part's centre: a 1x06 at 1.27 mm runs
    6.35 mm to one side of its origin. Placing the ORIGIN on the ring put the header's end there and
    its body across the neighbour, and DRC called J2's pin a short, which it was."""
    layer = "F.Fab" if fp in BODY_BOX else "F.CrtYd"
    t = mod_text(fp); pts = []
    for tag in ("fp_line", "fp_poly", "fp_rect", "fp_circle"):
        for b, _i, _j in sexp(t, tag):
            if f'"{layer}"' not in b: continue
            pts += [(float(x), float(y)) for x, y in
                    re.findall(r'\((?:start|end|xy|center) ([-\d.]+) ([-\d.]+)\)', b)]
    if not pts: return (0.0, 0.0)
    xs = [q[0] for q in pts]; ys = [q[1] for q in pts]
    return ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)


def origin_for(fp, cx, cy, rot):
    """The footprint origin that puts its courtyard CENTRE at screen (cx, cy) under rotation rot.
    Screen y runs down and KiCad turns footprints counter-clockwise as displayed, so a local vector
    (x, y) lands at (x cos a + y sin a, -x sin a + y cos a)."""
    ox, oy = courtyard_center(fp); a = math.radians(rot)
    return (cx - (ox * math.cos(a) + oy * math.sin(a)), cy - (-ox * math.sin(a) + oy * math.cos(a)))


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

def routing_count(text):
    """Top-level segments, arcs, vias and zones -- i.e. hand routing.

    Depth has to be tracked properly. Substring counting caught the keepout zone inside U1's own
    footprint, and indentation is no help either because footprint bodies are spliced in at their
    original depth. Only the nesting level says what is routing and what is part of a part.
    """
    n = depth = 0; i = 0
    while i < len(text):
        c = text[i]
        if c == '"':                                  # skip strings; they contain brackets
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
        elif c == "(":
            depth += 1
            if depth == 2:
                tag = re.match(r"\(([a-z_]+)", text[i:])
                if tag and tag.group(1) in ("segment", "arc", "via", "zone"): n += 1
        elif c == ")":
            depth -= 1
        i += 1
    return n


def uid(): return str(uuid.uuid4())
def mm(v): return f"{v:.4f}".rstrip("0").rstrip(".")

def top_properties(block, level=0):
    """Direct-child (property ...) forms, by name.

    `level` is the nesting depth they sit at: 0 for a footprint's spliced-out CONTENTS, 1 for a
    whole (footprint ...) or (symbol ...) block. Getting it wrong finds nothing and hides nothing,
    silently, which is exactly what it did.
    """
    out, depth, start = {}, 0, None
    for i, ch in enumerate(block):
        if ch == "(":
            if depth == level and block.startswith("(property ", i): start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == level and start is not None:
                frag = block[start:i + 1]
                out[re.match(r'\(property "([^"]+)"', frag).group(1)] = frag
                start = None
    return out


def hide_property(block, name):
    """Add (hide yes) to one property's effects, leaving the text itself in the file so the value is
    still there for the BOM and one click away in the GUI."""
    cur = top_properties(block).get(name)
    if not cur or "(hide yes)" in cur: return block
    if "(effects" in cur:
        i = cur.index("(effects"); d = 0
        for k in range(i, len(cur)):
            if cur[k] == "(": d += 1
            elif cur[k] == ")":
                d -= 1
                if d == 0:
                    new = cur[:k] + "\n\t\t\t(hide yes)\n\t\t" + cur[k:]
                    return block.replace(cur, new, 1)
    return block.replace(cur, cur[:cur.rindex(")")] + "\n\t\t(effects\n\t\t\t(hide yes)\n\t\t)\n\t)", 1)


def move_property(block, name, layer):
    cur = top_properties(block).get(name)
    if not cur: return block
    if "(layer " in cur:
        return block.replace(cur, re.sub(r'\(layer "[^"]+"\)', f'(layer "{layer}")', cur, count=1), 1)
    return block.replace(cur, cur[:cur.rindex(")")] + f'\n\t\t(layer "{layer}")\n\t)', 1)


def silk_text(label, th, r=SILK_R, size=SILK_SIZE):
    """A label on the free annulus, turned to read along it (and flipped on the left-hand side so it
    never reads upside down)."""
    x, y = polar(th, r)
    ang = (th + 90) % 360
    if 90 < ang < 270: ang = (ang + 180) % 360
    return (f'\t(gr_text "{label}"\n\t\t(at {mm(x)} {mm(y)} {mm(ang)})\n\t\t(layer "F.SilkS")\n'
            f'\t\t(uuid "{uid()}")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size {size} {size})\n'
            f'\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)')


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
    inner = hide_property(inner, "Value")
    if ref[:1] in FAB_REF_PREFIX and ref[1:2].isdigit():
        inner = move_property(inner, "Reference", "F.Fab")
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

    # Preferred angles say what should be NEAR what; this makes them fit. Parts are laid out in
    # angular order from just past the connector, each pushed to the first place it clears its
    # neighbour and the mounting holes. Hand-picked angles alone gave seven shorts and ten mask
    # bridges -- the grouping was right and the arithmetic was not.
    for ref, (r, th) in PINNED_POLAR.items():
        x, y = polar(th, r); FIXED[ref] = (x, y, tangential(real[ref][3], th))

    span = {ref: math.degrees((max(courtyard_wh(real[ref][3])) / 2 + 0.7) / OUTER_R.get(ref, 22.2))
            for ref in OUTER}
    j1_half = math.degrees((max(courtyard_wh(real["J1"][3])) / 2 + 0.7) / 21.6)
    blocked = [(a - 5.9, a + 5.9) for a in BOLT_ANGLES] + [(360 - j1_half, 360 + j1_half)]
    def hits(a0, a1):
        return any(a0 < hi and a1 > lo for lo, hi in blocked) or \
               any(a0 < hi - 360 and a1 > lo - 360 for lo, hi in blocked)
    cursor = j1_half
    for ref in sorted(OUTER, key=lambda r: (OUTER[r] - j1_half) % 360):
        th = max(OUTER[ref], cursor + span[ref])
        while hits(th - span[ref], th + span[ref]):
            th += 0.5
        assert th + span[ref] < 360 - j1_half, f"{ref} runs past the connector at {th:.1f} deg"
        r = OUTER_R.get(ref, 22.2)
        x, y = polar(th, r); FIXED[ref] = (x, y, tangential(real[ref][3], th))
        cursor = th + span[ref]
    # Inboard, the annulus is not an annulus. The module's courtyard reaches r=10.1 off its flat
    # faces but 14.0 at its corners, and the LED ring's inner edge is 14.25 -- so there is room near
    # 0/90/180/270 and none at all diagonally. Preferences here say what each part wants to be near;
    # this walks outward from that angle to the first slot that actually clears.
    mhx, mhy = [v / 2 for v in courtyard_wh(real["U1"][3])]
    inner_boxes = []
    for ref, pref in INNER_PREF.items():
        w, h = courtyard_wh(real[ref][3])
        hw, hh = max(w, h) / 2 + 0.3, min(w, h) / 2 + 0.3
        for d in [0] + [s_ * k for k in range(1, 120) for s_ in (1, -1)]:
            th = (pref + d) % 360
            for r in (INNER_R, INNER_R + 0.6, INNER_R + 1.1):
                x, y = polar(th, r)
                # hw, not hh: a tangential part's long axis still reaches toward the module on the
                # diagonals, and checking only the short side let four resistors clip its courtyard.
                if abs(x - CX) - hw < mhx and abs(y - CY) - hw < mhy: continue   # into the module
                if r + hh > 14.25 - 0.3: continue                                # into the LED ring
                if any(math.hypot(x - bx, y - by) < hw + bw for bx, by, bw in inner_boxes): continue
                FIXED[ref] = (x, y, (th + 90) % 360); inner_boxes.append((x, y, hw)); break
            else:
                continue
            break
        else:
            sys.exit(f"nowhere inboard for {ref}")

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

    labels = []
    for ref, text in SILK_LABEL.items():
        px, py, _r = placed[ref]
        labels.append(silk_text(text, math.degrees(math.atan2(-(py - CY), px - CX)) % 360))

    edge = (f'\t(gr_circle\n\t\t(center {mm(CX)} {mm(CY)})\n\t\t(end {mm(CX + BOARD_R)} {mm(CY)})\n'
            f'\t\t(stroke (width 0.1) (type default))\n\t\t(fill none)\n\t\t(layer "Edge.Cuts")\n'
            f'\t\t(uuid "{uid()}")\n\t)')
    netdefs = "\n".join(f'\t(net {i} "{n}")' for n, i in sorted(nets.items(), key=lambda kv: kv[1]))
    out = (f'(kicad_pcb\n\t(version 20240108)\n\t(generator "gen_pcb.py")\n'
           f'\t(generator_version "8.0")\n'
           f'\t(general\n\t\t(thickness 1.6)\n\t\t(legacy_teardrops no)\n\t)\n\t(paper "A4")\n'
           + LAYERS + "\n\t(setup\n\t\t(pad_to_mask_clearance 0)\n\t)\n"
           + netdefs + "\n" + "\n".join(fps) + "\n" + "\n".join(labels) + "\n" + edge + "\n)\n")
    d = sum(1 if c == "(" else -1 if c == ")" else 0 for c in out)
    assert d == 0, f"unbalanced s-expression: {d}"
    p = HERE / f"{PROJECT}.kicad_pcb"
    # Routing is hand work and this generator would erase it without noticing. Once the board has
    # tracks or vias in it, regenerating is almost certainly a mistake -- say so and stop.
    if p.exists() and not FORCE:
        old = p.read_text()
        laid = routing_count(old)
        if laid:
            sys.exit(f"{p.name} already has {laid} tracks/vias/zones in it -- regenerating would "
                     f"throw that away.\n  Re-run with --force if you really mean to start over, "
                     f"or edit the board in KiCad from here.")
    p.write_text(out)
    print(f"{p.name}: {len(real)} parts + {len(BOLT_ANGLES)} holes, {len(nets) - 1} nets, "
          f"board {BOARD_R * 2:.1f} mm")
    print(f"  U1 at the centre; J1 mouth at x={mm(CX + BOARD_R)} (0 deg); user button at 180 deg")
    print(f"  LEDs r={LED_R} at {LED_ANGLES}; M2 r={BOLT_R} at {BOLT_ANGLES}")

FORCE = False

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--force", action="store_true",
                    help="overwrite a board that already has routing in it")
    FORCE = ap.parse_args().force
    main()
