#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Command a live panel switch with the captured keys: prove we can control it.

We can read the panel's switches; this proves we can drive them too, over BLE
mesh, with no Brilliant app and no reset. It sends an acknowledged Generic OnOff
Set or Generic Level Set to a switch and prints the Status it reports back, so
you both see the light change and get confirmation on the wire.

    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \\
        python3 tools/panel_cmd.py <target_hex> on|off|dim:<0-100>

    panel_cmd.py 000a off
    panel_cmd.py 000a dim:20
    panel_cmd.py 000a on

Pin the proxy with PANEL_NODE=<ble-addr>.
"""
import asyncio
import os
import sys

os.environ.setdefault(
    "BRILLIANT_MESH_STORE",
    os.path.expanduser("~/.config/brilliant-mesh/panel-net.json"))

from bleak import BleakClient, BleakScanner

import mesh
import onoff as O

_tid = 0


def tid():
    global _tid
    _tid = (_tid + 1) & 0xFF
    return _tid


async def find_proxy(netkey):
    our = mesh.k3(netkey)
    pin = os.environ.get("PANEL_NODE")
    if pin:
        d = await BleakScanner.find_device_by_address(pin, timeout=20.0)
        if d:
            print(f"  pinned proxy {pin}"); return d
    print("  scanning for a panel proxy...")
    seen = await BleakScanner.discover(timeout=20.0, return_adv=True)
    cands = []
    for dev, adv in seen.values():
        for uuid, sd in (adv.service_data or {}).items():
            if uuid.lower().startswith("00001828") and len(sd) >= 9 \
                    and sd[0] == 0x00 and sd[1:9] == our:
                cands.append((dev, adv))
    if not cands:
        return None
    cands.sort(key=lambda x: -x[1].rssi)
    print(f"  proxy {cands[0][0].address} at {cands[0][1].rssi} dBm")
    return cands[0][0]


async def main():
    if len(sys.argv) < 3:
        print(__doc__); return
    target = int(sys.argv[1], 16)
    cmd = sys.argv[2].lower()

    net = mesh.load()
    netkey = bytes.fromhex(net["netkey"]); appkey = bytes.fromhex(net["appkey"])
    iv = net["iv_index"]; us = net.get("our_unicast", 0x1a); aid = mesh.k4(appkey)

    if cmd in ("on", "off"):
        access = bytes([0x82, 0x02, 1 if cmd == "on" else 0, tid()])
        want = 0x8204; label = f"OnOff {cmd}"
    elif cmd.startswith("dim:"):
        # Captured from the panel dimming via the app: Generic Level Set (0x8206)
        # with the level on a 0-1000 scale (NOT the SIG -32768..32767 mapping),
        # then TID + transition-time 0x05 + delay 0x00. That scale is why sending
        # a standard-mapped level did nothing -- it was off the switch's range.
        pct = max(0, min(100, int(cmd.split(":")[1])))
        lvl = int(pct / 100.0 * 1000) & 0xFFFF
        access = bytes([0x82, 0x06]) + lvl.to_bytes(2, "little") + bytes([tid(), 0x05, 0x00])
        want = 0x8208; label = f"Level {pct}% (raw {lvl}/1000)"
    elif cmd.startswith("vdim:"):
        # Vendor brightness write: c1 2008 12 04 <val LE 2> 00, on the 0-1000
        # scale (the switch's native dimming, which the triac actually follows).
        pct = max(0, min(100, int(cmd.split(":")[1])))
        val = int(pct / 100.0 * 1000)
        access = bytes([0xC1, 0x20, 0x08, 0x12, 0x04]) + val.to_bytes(2, "little") + bytes([0x00])
        want = None; label = f"VENDOR brightness {pct}% (raw {val})"
    elif cmd.startswith("vset:"):
        # vset:<field>:<hexvalue>  -> c1 2008 12 <field> <value bytes> 00
        _, fld, hexv = cmd.split(":")
        access = bytes([0xC1, 0x20, 0x08, 0x12, int(fld, 16)]) + bytes.fromhex(hexv) + bytes([0x00])
        want = None; label = f"VENDOR set field 0x{fld} = {hexv}"
    else:
        print("command must be on | off | dim:<0-100> | vdim:<0-100> | vset:<field>:<hex>"); return

    print(f"target 0x{target:04x}  ->  {label}")
    O.rx = asyncio.Queue()
    dev = await find_proxy(netkey)
    if not dev:
        print("no panel proxy found"); return

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(netkey, iv, ctl=1, ttl=0, seq=seq, src=us,
                               dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                               nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu)
        await asyncio.sleep(0.4)

        seq0 = mesh.next_seq(net)
        upper = mesh.app_encrypt_appkey(appkey, iv, seq0, us, target, access)
        lower = bytes([0x40 | aid]) + upper
        npdu = mesh.net_encrypt(netkey, iv, ctl=0, ttl=7, seq=seq0, src=us,
                                dst=target, transport_pdu=lower)
        await O.send(cli, 0x00, npdu, mtu)
        print(f"  sent. watching for the switch's Status reply...")

        end = asyncio.get_event_loop().time() + 8
        while asyncio.get_event_loop().time() < end:
            try:
                typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=2)
            except asyncio.TimeoutError:
                continue
            if typ != 0x00:
                continue
            m = mesh.net_decrypt(netkey, iv, pdu)
            if not m or m["src"] != target or m["ctl"] or (m["transport"][0] & 0x80):
                continue
            nonce = bytes([0x01, 0x00]) + m["seq"].to_bytes(3, "big") \
                + m["src"].to_bytes(2, "big") + m["dst"].to_bytes(2, "big") \
                + iv.to_bytes(4, "big")
            try:
                p = mesh.ccm_decrypt(appkey, nonce, m["transport"][1:], tag=4)
            except Exception:
                continue
            op = int.from_bytes(p[:2], "big")
            if op in (want, 0x8204, 0x8208):
                print(f"  <- STATUS from 0x{m['src']:04x}: {p.hex()}  "
                      f"(the switch acted -- control confirmed)")
                await cli.stop_notify(O.PROXY_OUT)
                return
        print("  no Status within 8s (the light may still have changed; "
              "watch it, and check range).")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
