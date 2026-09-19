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
 "U1": ("RF_Module", "ESP32-S3-WROOM-1", "ESP32-S3-WROOM-1-N16",
        "RF_Module:ESP32-S2-WROOM", {
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

 "U5": ("Sensor_Optical", "LTR-303ALS-01", "ambient light, DNP", "",
        {"1":"+3V3", "3":"GND", "4":"SCL", "6":"SDA"}),

 "J1": ("Connector", "USB_C_Receptacle_USB2.0_16P", "USB-C 16P", "",
        {"A1":"GND","A12":"GND","B1":"GND","B12":"GND","SH":"GND",
         "A4":"VBUS","A9":"VBUS","B4":"VBUS","B9":"VBUS",
         "A5":"CC1","B5":"CC2","A6":"USB_DP","B6":"USB_DP","A7":"USB_DM","B7":"USB_DM"}),

 "J2": ("Connector_Generic", "Conn_01x04", "UART", "",
        {"1":"GND", "2":"UART0_TX", "3":"UART0_RX", "4":"+3V3"}),
 "J3": ("Connector_Generic", "Conn_01x06", "EXP (DNP on the product)", "",
        {"1":"+3V3", "2":"VBUS", "3":"GND", "4":"EXP_A", "5":"EXP_B", "6":"EXP_C"}),

 "D1": ("LED","WS2812B","SK6812-RGBW","LED:LED_SK6812_PLCC6_5.0x5.0mm",
        {"1":"VBUS","3":"GND","4":"LED_D1_IN","2":"LED_D1_OUT"}),
 "D2": ("LED","WS2812B","SK6812-RGBW","LED:LED_SK6812_PLCC6_5.0x5.0mm",
        {"1":"VBUS","3":"GND","4":"LED_D1_OUT","2":"LED_D2_OUT"}),
 "D3": ("LED","WS2812B","SK6812-RGBW","LED:LED_SK6812_PLCC6_5.0x5.0mm",
        {"1":"VBUS","3":"GND","4":"LED_D2_OUT"}),                 # DOUT left open

 "SW1": ("Switch","SW_Push","BOOT","",   {"1":"IO0","2":"GND"}),
 "SW2": ("Switch","SW_Push","RESET","",  {"1":"EN","2":"GND"}),
 "SW3": ("Switch","SW_Push","USER","",   {"1":"USER_BTN","2":"GND"}),

 "R1": ("Device","R","5k1","Resistor_SMD:R_0603_1608Metric", {"1":"CC1","2":"GND"}),
 "R2": ("Device","R","5k1","Resistor_SMD:R_0603_1608Metric", {"1":"CC2","2":"GND"}),
 "R3": ("Device","R","10k","Resistor_SMD:R_0603_1608Metric", {"1":"+3V3","2":"EN"}),
 "R4": ("Device","R","300", "Resistor_SMD:R_0603_1608Metric", {"1":"LED_DATA_5V","2":"LED_D1_IN"}),
 "R5": ("Device","R","4k7","Resistor_SMD:R_0603_1608Metric", {"1":"+3V3","2":"SDA"}),
 "R6": ("Device","R","4k7","Resistor_SMD:R_0603_1608Metric", {"1":"+3V3","2":"SCL"}),

 "C1": ("Device","C","22u","Capacitor_SMD:C_0805_2012Metric", {"1":"VBUS","2":"GND"}),
 "C2": ("Device","C","10u","Capacitor_SMD:C_0603_1608Metric", {"1":"+3V3","2":"GND"}),
 "C3": ("Device","C","100n","Capacitor_SMD:C_0603_1608Metric",{"1":"+3V3","2":"GND"}),
 "C4": ("Device","C","100n","Capacitor_SMD:C_0603_1608Metric",{"1":"VBUS","2":"GND"}),
 "C5": ("Device","C","100n","Capacitor_SMD:C_0603_1608Metric",{"1":"VBUS","2":"GND"}),
 "C6": ("Device","C","100n","Capacitor_SMD:C_0603_1608Metric",{"1":"VBUS","2":"GND"}),
 "C7": ("Device","C","1u",  "Capacitor_SMD:C_0603_1608Metric",{"1":"EN","2":"GND"}),

 # VBUS and GND arrive on a connector, whose pins are passive, so nothing on the sheet tells ERC
 # they are powered. These say so.
 "#FLG1": ("power","PWR_FLAG","","", {"1":"VBUS"}),
 "#FLG2": ("power","PWR_FLAG","","", {"1":"GND"}),
}

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
    if m:
        parent = m.group(1)
        blk = raw_symbol(lib, parent)
        blk = blk.replace(f'(symbol "{parent}_', f'(symbol "{name}_')   # unit sub-symbols first
        blk = blk.replace(f'\t(symbol "{parent}"', f'\t(symbol "{key}"', 1)
    else:
        blk = blk.replace(f'(symbol "{name}"', f'(symbol "{key}"', 1)
    return blk


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
