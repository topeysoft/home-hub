#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""puck-revA.kicad_sch from the netlist in this file, which is the netlist in README.md.

The README is the argument and this is the machine-readable copy of it; run this after changing
either, so the two cannot drift -- the same deal design/puck/make-index.py has with canvas.json.

WHAT THIS PRODUCES, and what it deliberately does not. Every pin gets a short stub and a global
label carrying its net name. Connectivity is therefore by NAME, not by wire routing: no crossings,
no junctions, nothing that can be subtly wrong in a way that looks right. It is not a hand-drafted
schematic and is not trying to be one -- rearranging symbols in Eeschema cannot break the netlist,
which is the property worth having while the design is still moving.

Verify with:
    kicad-cli sch erc --output erc.rpt puck-revA.kicad_sch
    kicad-cli sch export netlist --output puck-revA.net puck-revA.kicad_sch
and then check the exported nets against NETS below -- gen_sch.py --check does exactly that.
"""
import argparse, math, pathlib, re, sys, uuid

SYMDIR = pathlib.Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols")
HERE = pathlib.Path(__file__).parent
PROJECT = "puck-revA"

# ---- the design ------------------------------------------------------------------------------
#
# ref: (library, symbol, value, footprint, {pin number: net})
# Pin numbers, never pin names: names differ between a symbol and the part it inherits from, and a
# name that silently matches the wrong pin is exactly the fault this file exists to make impossible.

PARTS = {
 # The -1U: the same module with a U.FL where the -1 has a trace antenna, so the antenna becomes a
 # flex stuck inside the shell and the module no longer has to sit at a board edge. KiCad 10 ships
 # the -1U footprint but not its symbol; the -1 symbol is pin-identical (checked pad for pad).
 "U1": ("RF_Module", "ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1U-N16",
        "RF_Module:ESP32-S3-WROOM-1U", {
        "1":"GND", "40":"GND", "41":"GND", "2":"+3V3", "3":"EN", "27":"IO0",
        "4":"USER_BTN", "12":"SDA", "17":"SCL",
        "9":"EXP_C", "10":"EXP_A", "11":"EXP_B",
        "13":"USB_DM", "14":"USB_DP",
        "31":"LED_DATA_3V3", "36":"UART0_RX", "37":"UART0_TX"}),

 "U2": ("Regulator_Linear", "AP2112K-3.3", "AP2112K-3.3", "Package_TO_SOT_SMD:SOT-23-5",
        {"1":"VBUS", "2":"GND", "3":"VBUS", "5":"+3V3"}),          # EN tied on: always up

 "U3": ("74xGxx", "74AHCT1G125", "74AHCT1G125", "Package_TO_SOT_SMD:SOT-23-5",
        {"1":"GND", "2":"LED_DATA_3V3", "3":"GND", "4":"LED_DATA_5V", "5":"VBUS"}),  # pin1 OE low

 "U4": ("Power_Protection", "USBLC6-2SC6", "USBLC6-2SC6", "Package_TO_SOT_SMD:SOT-23-6",
        {"1":"USB_DM", "6":"USB_DM", "3":"USB_DP", "4":"USB_DP", "2":"GND", "5":"VBUS"}),

 "U5": ("Sensor_Optical", "LTR-303ALS-01", "ambient light, DNP", "OptoDevice:Lite-On_LTR-303ALS-01",
        {"1":"+3V3", "3":"GND", "4":"SCL", "6":"SDA"}),

 "J1": ("Connector", "USB_C_Receptacle_USB2.0_16P", "USB-C 16P",
        "Connector_USB:USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal",
        {"A1":"GND","A12":"GND","B1":"GND","B12":"GND","SH":"GND",
         "A4":"VBUS","A9":"VBUS","B4":"VBUS","B9":"VBUS",
         "A5":"CC1","B5":"CC2","A6":"USB_DP","B6":"USB_DP","A7":"USB_DM","B7":"USB_DM"}),

 "J2": ("Connector_Generic", "Conn_01x04", "UART", "Connector_PinHeader_1.27mm:PinHeader_1x04_P1.27mm_Vertical",
        {"1":"GND", "2":"UART0_TX", "3":"UART0_RX", "4":"+3V3"}),
 "J3": ("Connector_Generic", "Conn_01x06", "EXP (DNP on the product)",
        "Connector_PinHeader_1.27mm:PinHeader_1x06_P1.27mm_Vertical",
        {"1":"+3V3", "2":"VBUS", "3":"GND", "4":"EXP_A", "5":"EXP_B", "6":"EXP_C"}),

 # LEDs: generated below, N_LEDS of them in a chain. See gen_pcb.py for the ring.

 # KMR2 side-actuated, 4.2 x 2.8 x 1.4: the SKQG it replaces is 5.7 mm deep and fits nowhere once the
 # ring is on the board. Its SH pad is a mechanical ground tab the SW_Push symbol has no pin for; it is
 # left floating, which the datasheet allows.
 "SW1": ("Switch","SW_Push","BOOT","Button_Switch_SMD:SW_Push_1P1T-SH_NO_CK_KMR2xxG",   {"1":"IO0","2":"GND"}),
 "SW2": ("Switch","SW_Push","RESET","Button_Switch_SMD:SW_Push_1P1T-SH_NO_CK_KMR2xxG",  {"1":"EN","2":"GND"}),
 "SW3": ("Switch","SW_Push","USER","Button_Switch_SMD:SW_Push_1P1T-SH_NO_CK_KMR2xxG",   {"1":"USER_BTN","2":"GND"}),

 "R1": ("Device","R","5k1","Resistor_SMD:R_0603_1608Metric", {"1":"CC1","2":"GND"}),
 "R2": ("Device","R","5k1","Resistor_SMD:R_0603_1608Metric", {"1":"CC2","2":"GND"}),
 "R3": ("Device","R","10k","Resistor_SMD:R_0603_1608Metric", {"1":"+3V3","2":"EN"}),
 "R4": ("Device","R","300", "Resistor_SMD:R_0603_1608Metric", {"1":"LED_DATA_5V","2":"LED_D1_IN"}),
 "R5": ("Device","R","4k7","Resistor_SMD:R_0603_1608Metric", {"1":"+3V3","2":"SDA"}),
 "R6": ("Device","R","4k7","Resistor_SMD:R_0603_1608Metric", {"1":"+3V3","2":"SCL"}),

 "C1": ("Device","C","22u","Capacitor_SMD:C_0805_2012Metric", {"1":"VBUS","2":"GND"}),
 "C2": ("Device","C","10u","Capacitor_SMD:C_0603_1608Metric", {"1":"+3V3","2":"GND"}),
 "C3": ("Device","C","100n","Capacitor_SMD:C_0603_1608Metric",{"1":"+3V3","2":"GND"}),
 "C7": ("Device","C","1u",  "Capacitor_SMD:C_0603_1608Metric",{"1":"EN","2":"GND"}),

 # VBUS and GND arrive on a connector, whose pins are passive, so nothing on the sheet tells ERC
 # they are powered. These say so.
 "#FLG1": ("power","PWR_FLAG","","", {"1":"VBUS"}),
 "#FLG2": ("power","PWR_FLAG","","", {"1":"GND"}),
}

# The ring: 11 SK6812-RGBW 5050 on r=17 at 30 deg spacing, one chain, one 100 nF each. Eleven
# rather than twelve because the twelfth would sit in the USB-C, and it is at r=17 rather than the
# rim because the object is meant to GLOW, not to wear a light ring: ~9 mm from emitter to roof
# and to wall blurs eleven dice into one warm body. gen_pcb.py fixes the angles.
#
# Current, so nobody is surprised: 11 x 4 dice x ~15 mA is ~0.66 A at full white on every die, on
# top of the module's ~0.3 A Wi-Fi bursts -- right at a 1 A cube's limit. The nightlight runs the W
# die alone at ~110/255 (~70 mA) and the instrument states are single colours; firmware caps the
# total rather than the cube browning out.
N_LEDS = 11
for _i in range(1, N_LEDS + 1):
    _nets = {"1": "VBUS", "3": "GND", "4": "LED_D1_IN" if _i == 1 else f"LED_D{_i-1}_OUT"}
    if _i < N_LEDS: _nets["2"] = f"LED_D{_i}_OUT"          # the last DOUT is left open
    PARTS[f"D{_i}"] = ("LED", "WS2812B", "SK6812-RGBW",
                       "LED_SMD:LED_SK6812_PLCC4_5.0x5.0mm_P3.2mm", _nets)

# Decoupling: FOUR 100 nF around the ring, not one per LED, and this is a decision rather than a
# saving. There is nowhere on a single-sided 50 mm board for eleven of them. Inboard of the ring is
# out -- the module's courtyard corners reach r=14.02 and the ring's inner edge is 14.25. Outboard
# is where the switches and headers live. And the ring's own gaps are 2.0 mm wide against an 0603
# courtyard of 3.0 mm, so "between the LEDs" does not fit either; all three were tried and measured.
#
# Four is defensible on its own terms: one per ~3 LEDs is ordinary practice for a ring this size,
# the chain's peak is ~0.66 A across 34 mm of ring, C1's 22 uF sits on the same rail, and the board
# gets a solid GND pour. If the first five boards show LED noise, the fix is a cap on the BACK under
# each LED with two vias -- electrically better than anything on this side, at the cost of the
# second-side assembly that docs/puck-hardware.md deliberately avoided.
for _i in range(1, 5):
    PARTS[f"C{100 + _i}"] = ("Device", "C", "100n", "Capacitor_SMD:C_0603_1608Metric",
                             {"1": "VBUS", "2": "GND"})

# ---- reading the installed libraries ----------------------------------------------------------

def sexp_block(text, header):
    i = text.index(header)
    d = 0
    for k in range(i, len(text)):
        if text[k] == "(": d += 1
        elif text[k] == ")":
            d -= 1
            if d == 0: return text[i:k + 1]
    raise ValueError(header)

_libcache = {}
def lib_text(lib):
    if lib not in _libcache:
        p = SYMDIR / f"{lib}.kicad_sym"
        if not p.exists(): sys.exit(f"no such symbol library: {p}")
        _libcache[lib] = p.read_text()
    return _libcache[lib]

def raw_symbol(lib, name):
    return sexp_block(lib_text(lib), f'\t(symbol "{name}"')

def resolved(lib, name):
    """The block that actually carries the pins. KiCad symbols inherit, and a derived symbol holds
    properties only -- its parent holds the geometry. Guessing this wrong yields a symbol with no
    pins and a netlist with no nets, which is how this was caught."""
    blk = raw_symbol(lib, name)
    m = re.search(r'\(extends "([^"]+)"', blk)
    return raw_symbol(lib, m.group(1)) if m else blk

PIN_RE = re.compile(r'\(pin (\w+) \w+\s*\(at ([-\d.]+) ([-\d.]+) (\d+)\)(?:.|\n)*?'
                    r'\(name "([^"]*)"(?:.|\n)*?\(number "([^"]*)"')

def pins_of(lib, name):
    out = {}
    for etype, x, y, a, nm, num in PIN_RE.findall(resolved(lib, name)):
        out[num] = (float(x), float(y), int(a), nm)
    return out

# ---- geometry ---------------------------------------------------------------------------------
#
# Library symbols are drawn Y-up; a schematic sheet is Y-down. A pin's (at) is its CONNECTION point
# and its angle points from there back into the body, so a stub leaves in the opposite direction.

STUB = 7.62   # long enough that a label clears its neighbour's symbol body

def pin_xy(ox, oy, px, py):        return (ox + px, oy - py)
def stub_xy(ox, oy, px, py, a):
    return (ox + px - STUB * math.cos(math.radians(a)),
            oy - py + STUB * math.sin(math.radians(a)))
def label_angle(a):                return (a + 180) % 360

def uid(): return str(uuid.uuid4())
def mm(v):  return f"{v:.2f}"

# ---- emit -------------------------------------------------------------------------------------

def build():
    used, placed, wires, labels, nocon = {}, [], [], [], []

    # every symbol's footprint on the sheet, so the grid can leave room for the big ones
    extents = {}
    for ref, (lib, name, *_rest) in PARTS.items():
        ps = pins_of(lib, name)
        if not ps: sys.exit(f"{ref}: {lib}:{name} resolved to zero pins")
        xs = [p[0] for p in ps.values()]; ys = [p[1] for p in ps.values()]
        extents[ref] = (max(xs) - min(xs) + 58, max(ys) - min(ys) + 42)

    # Shelf packing, tallest first, on a 2.54 grid. Placement is cosmetic -- the netlist is in the
    # labels -- so this only has to avoid overlap.
    order = sorted(PARTS, key=lambda r: -extents[r][1])
    x, y, row_h, PAGE_W = 40.0, 45.0, 0.0, 545.0
    pos = {}
    for ref in order:
        w, h = extents[ref]
        if x + w > PAGE_W: x, y, row_h = 40.0, y + row_h + 14, 0.0
        pos[ref] = (round((x + w / 2) / 2.54) * 2.54, round((y + h / 2) / 2.54) * 2.54)
        x += w + 14; row_h = max(row_h, h)

    for ref, (lib, name, value, fp, netmap) in PARTS.items():
        used[f"{lib}:{name}"] = (lib, name)
        ox, oy = pos[ref]
        ps = pins_of(lib, name)
        for num in netmap:
            if num not in ps: sys.exit(f"{ref}: {lib}:{name} has no pin {num}")
        show_ref = not ref.startswith("#")
        props = [("Reference", ref, not show_ref), ("Value", value, False),
                 ("Footprint", fp, True), ("Datasheet", "", True), ("Description", "", True)]
        body = [f'\t\t(property "{k}" "{v}"\n\t\t\t(at {mm(ox)} {mm(oy - 12)} 0)\n'
                f'\t\t\t(effects\n\t\t\t\t(font (size 1.27 1.27))'
                + ('\n\t\t\t\t(hide yes)' if hide else '') + '\n\t\t\t)\n\t\t)'
                for k, v, hide in props]
        pinrefs = "".join(f'\t\t(pin "{n}"\n\t\t\t(uuid "{uid()}")\n\t\t)\n' for n in ps)
        placed.append(
            f'\t(symbol\n\t\t(lib_id "{lib}:{name}")\n\t\t(at {mm(ox)} {mm(oy)} 0)\n\t\t(unit 1)\n'
            f'\t\t(exclude_from_sim no)\n\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n'
            f'\t\t(uuid "{uid()}")\n' + "\n".join(body) + "\n" + pinrefs +
            f'\t\t(instances\n\t\t\t(project "{PROJECT}"\n\t\t\t\t(path "/{SHEET_UUID}"\n'
            f'\t\t\t\t\t(reference "{ref}")\n\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)')

        for num, net in netmap.items():
            px, py, a, _ = ps[num]
            p0 = pin_xy(ox, oy, px, py); p1 = stub_xy(ox, oy, px, py, a)
            wires.append(f'\t(wire\n\t\t(pts\n\t\t\t(xy {mm(p0[0])} {mm(p0[1])}) '
                         f'(xy {mm(p1[0])} {mm(p1[1])})\n\t\t)\n'
                         f'\t\t(stroke (width 0) (type default))\n\t\t(uuid "{uid()}")\n\t)')
            labels.append(
                f'\t(global_label "{net}"\n\t\t(shape passive)\n'
                f'\t\t(at {mm(p1[0])} {mm(p1[1])} {label_angle(a)})\n\t\t(fields_autoplaced yes)\n'
                f'\t\t(effects\n\t\t\t(font (size 1.27 1.27))\n\t\t\t(justify left)\n\t\t)\n'
                f'\t\t(uuid "{uid()}")\n\t)')

        # Everything deliberately left open says so. Without these, ERC drowns in 28 warnings and
        # a genuinely forgotten pin hides among them -- which is the only thing ERC is for.
        for num, (px, py, _a, _nm) in ps.items():
            if num in netmap: continue
            q = pin_xy(ox, oy, px, py)
            nocon.append(f'\t(no_connect\n\t\t(at {mm(q[0])} {mm(q[1])})\n\t\t(uuid "{uid()}")\n\t)')

    libs = []
    for key, (lib, name) in sorted(used.items()):
        libs.append(embed(key, lib, name))
    return placed, wires, labels, libs, nocon


def embed(key, lib, name):
    """A self-contained symbol definition for lib_symbols.

    A derived symbol holds properties and an (extends) and NO geometry, so embedding it as-is gives
    KiCad a symbol with no pins. Rather than splice the parent's innards into the child -- which is
    where this first went wrong, and produced a file that would not parse at all -- take the PARENT
    wholesale and rename it, inner unit sub-symbols included. Same pins, same graphics, right name."""
    blk = raw_symbol(lib, name)
    m = re.search(r'\(extends "([^"]+)"', blk)
    if not m:
        return blk.replace(f'(symbol "{name}"', f'(symbol "{key}"', 1)
    parent = m.group(1)
    out = raw_symbol(lib, parent)
    out = out.replace(f'(symbol "{parent}_', f'(symbol "{name}_')       # unit sub-symbols first
    out = out.replace(f'\t(symbol "{parent}"', f'\t(symbol "{key}"', 1)
    # The parent supplies geometry and NOTHING ELSE. Its properties describe the parent -- taking
    # them wholesale made the embedded AP2112K-3.3 claim to be an AP2204K-1.5, a 150 mA part rather
    # than a 600 mA one, which is a wrong Value on its way to a BOM. Overlay the child's.
    for pname, ptext in top_properties(blk).items():
        out = replace_property(out, pname, ptext)
    return out


def top_properties(block):
    """Direct-child (property ...) forms of a symbol, by name."""
    out, depth, start = {}, 0, None
    for i, ch in enumerate(block):
        if ch == "(":
            if depth == 1 and block.startswith("(property ", i): start = i
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 1 and start is not None:
                frag = block[start:i + 1]
                out[re.match(r'\(property "([^"]+)"', frag).group(1)] = frag
                start = None
    return out


def replace_property(block, pname, ptext):
    cur = top_properties(block).get(pname)
    return block.replace(cur, ptext, 1) if cur else block


SHEET_UUID = uid()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", metavar="NETLIST", help="compare an exported .net against PARTS")
    a = ap.parse_args()
    if a.check: return check(a.check)
    placed, wires, labels, libs, nocon = build()
    out = (f'(kicad_sch\n\t(version 20231120)\n\t(generator "gen_sch.py")\n'
           f'\t(generator_version "8.0")\n\t(uuid "{SHEET_UUID}")\n\t(paper "A2")\n'
           f'\t(title_block\n\t\t(title "Puck rev A")\n\t\t(rev "A")\n'
           f'\t\t(comment 1 "Generated by gen_sch.py from PARTS. Connectivity is by global label, not by wire routing: move symbols freely, but edit nets in gen_sch.py and regenerate.")\n\t)\n'
           f'\t(lib_symbols\n' + "\n".join(libs) + "\n\t)\n"
           + "\n".join(wires) + "\n" + "\n".join(nocon) + "\n"
           + "\n".join(labels) + "\n" + "\n".join(placed) + "\n)\n")
    d = 0
    for ch in out:
        if ch == "(": d += 1
        elif ch == ")": d -= 1
    assert d == 0, f"unbalanced s-expression: {d}"
    p = HERE / f"{PROJECT}.kicad_sch"
    p.write_text(out)
    nets = {}
    for ref, (_l, _n, _v, _f, nm) in PARTS.items():
        for pin, net in nm.items(): nets.setdefault(net, []).append(f"{ref}.{pin}")
    print(f"{p.name}: {len(PARTS)} symbols, {len(nets)} nets, "
          f"{sum(len(v) for v in nets.values())} pins, {len(nocon)} no-connects")

def check(netfile):
    """Every net in PARTS must appear in the exported netlist with exactly the same pins."""
    txt = pathlib.Path(netfile).read_text()
    got = {}
    for m in re.finditer(r'\(net\s+\(code "\d+"\)\s+\(name "([^"]+)"\)((?:.|\n)*?)\n\t\t\)', txt):
        name = m.group(1).lstrip("/")
        got[name] = {f'{r}.{p}' for r, p in re.findall(r'\(node\s+\(ref "([^"]+)"\)\s+\(pin "([^"]+)"\)', m.group(2))}
    want = {}
    for ref, (_l, _n, _v, _f, nm) in PARTS.items():
        if ref.startswith("#"): continue   # power symbols are not components; KiCad omits them
        for pin, net in nm.items(): want.setdefault(net, set()).add(f"{ref}.{pin}")
    bad = 0
    for net, pins in sorted(want.items()):
        g = got.get(net)
        if g is None:
            print(f"  MISSING net {net}"); bad += 1
        elif g != pins:
            print(f"  {net}: extra={sorted(g-pins)} missing={sorted(pins-g)}"); bad += 1
    print(f"{'FAIL' if bad else 'OK'}: {len(want)} nets checked, {bad} wrong")
    return 1 if bad else 0

if __name__ == "__main__":
    sys.exit(main() or 0)
