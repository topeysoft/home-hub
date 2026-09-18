#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read a switch's whole vendor store (every field that answers) to a JSON file.

Works on either network: point BRILLIANT_MESH_STORE at the panel keys to read
a panel-configured dimmer, or at mesh-net.json to read one of ours. The proxy
is any node advertising that network's id (pin one with PANEL_NODE=<ble-addr>).

    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \\
        python3 tools/vendor_store.py 000a /tmp/panel-000a.json
    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/mesh-net.json \\
        python3 tools/vendor_store.py 0003 /tmp/ours-0003.json
    python3 tools/vendor_store.py --diff /tmp/panel-000a.json /tmp/ours-0003.json

The point of two files is the diff: a switch the panel set up as a dimmer with
motion, against one that was factory reset, differ exactly in the fields the
panel wrote. --all sweeps every field id 0x00-0xff instead of the known list.
"""
import asyncio
import json
import os
import sys
import time

from bleak import BleakClient, BleakScanner

import mesh
import onoff as O
import rawlog
from snapshot import FIELDS

CID = 0x0820


def diff(a_path, b_path):
    a, b = json.load(open(a_path)), json.load(open(b_path))
    fa, fb = a["fields"], b["fields"]
    print(f"{'field':5}  {os.path.basename(a_path):28}  {os.path.basename(b_path)}")
    same = 0
    for k in sorted(set(fa) | set(fb)):
        va, vb = fa.get(k), fb.get(k)
        if va == vb:
            same += 1
            continue
        print(f"0x{k}   {str(va):28}  {vb}")
    print(f"\n{same} fields identical, {len(set(fa) | set(fb)) - same} differ")


async def find_proxy(netkey):
    our = mesh.k3(netkey)
    pin = os.environ.get("PANEL_NODE")
    if pin:
        d = await BleakScanner.find_device_by_address(pin, timeout=20.0)
        if d:
            print(f"  pinned proxy {pin}")
            return d
    print(f"  scanning 12s for a proxy on {our.hex()}...")
    # A detection callback, not discover(): on macOS discover() keeps only each
    # device's latest advertisement, which is as often the FWID beacon as the
    # proxy beacon, and the network id lives only in the latter.
    cands = {}

    def cb(dev, adv):
        for uuid, sd in (adv.service_data or {}).items():
            if uuid.lower().startswith("00001828") and len(sd) >= 9 and sd[0] == 0x00 \
                    and sd[1:9] == our:
                cands[dev.address] = (dev, adv)

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    await asyncio.sleep(12)
    await scanner.stop()
    cands = list(cands.values())
    if not cands:
        return None
    cands.sort(key=lambda x: -x[1].rssi)
    print(f"  proxy {cands[0][0].address} at {cands[0][1].rssi} dBm")
    return cands[0][0]


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--diff" in sys.argv:
        diff(args[0], args[1])
        return
    target = int(args[0], 16)
    out_path = args[1] if len(args) > 1 else f"store-{target:04x}-{int(time.time())}.json"
    fields = list(range(256)) if "--all" in sys.argv else FIELDS

    net = mesh.load()
    netkey = bytes.fromhex(net["netkey"])
    appkey = bytes.fromhex(net["appkey"])
    iv = net["iv_index"]
    us = net.get("our_unicast", net.get("provisioner_addr", 1))
    aid = mesh.k4(appkey)
    print(f"target 0x{target:04x} on network {mesh.k3(netkey).hex()}, {len(fields)} fields, from 0x{us:04x}")

    O.rx = asyncio.Queue()
    dev = await find_proxy(netkey)
    if not dev:
        print("no proxy found for this network")
        return
    asm = rawlog.Reassembler()
    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(netkey, iv, ctl=1, ttl=0, seq=seq, src=us, dst=0x0000,
                               transport_pdu=bytes([0x00, 0x01]), nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu)
        await asyncio.sleep(0.4)

        async def get(field):
            access = bytes([0xC1]) + CID.to_bytes(2, "little") + bytes([0x11, field])
            seq0 = mesh.next_seq(net)
            upper = mesh.app_encrypt_appkey(appkey, iv, seq0, us, target, access)
            lower = bytes([0x40 | aid]) + upper
            npdu = mesh.net_encrypt(netkey, iv, ctl=0, ttl=7, seq=seq0, src=us, dst=target,
                                    transport_pdu=lower)
            await O.send(cli, 0x00, npdu, mtu)

        async def reply(field, timeout):
            end = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < end:
                try:
                    typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=0.3)
                except asyncio.TimeoutError:
                    continue
                if typ != 0x00:
                    continue
                m = mesh.net_decrypt(netkey, iv, pdu)
                if not m or m["ctl"] or m["src"] != target:
                    continue
                t = m["transport"]
                if not ((t[0] >> 6) & 1):
                    continue
                if t[0] & 0x80:
                    body, (szmic, seqzero, sego, segn, done) = asm.feed(m, t)
                    if not done:
                        continue
                    await rawlog.send_segack(cli, mtu, net, netkey, iv, us, m["src"], seqzero, segn)
                    seq_use, tag = mesh.seq_auth(m["seq"], seqzero), (8 if szmic else 4)
                else:
                    body, seq_use, tag, szmic = t[1:], m["seq"], 4, 0
                nonce = bytes([0x01, 0x80 if szmic else 0x00]) + seq_use.to_bytes(3, "big") \
                    + m["src"].to_bytes(2, "big") + m["dst"].to_bytes(2, "big") + iv.to_bytes(4, "big")
                try:
                    p = mesh.ccm_decrypt(appkey, nonce, body, tag=tag)
                except Exception:
                    continue
                if len(p) >= 5 and p[3] == 0x13 and p[4] == field:
                    return p[5:].hex()
            return None

        result = {}
        t0 = time.time()

        def save():
            json.dump({"target": f"{target:04x}", "network": mesh.k3(netkey).hex(), "read_at": time.time(),
                       "fields": result}, open(out_path, "w"), indent=1)

        try:
            for f in fields:
                if not cli.is_connected:
                    print("\n  proxy dropped the link; saving what was read")
                    break
                val = None
                for attempt in range(2):
                    await get(f)
                    val = await reply(f, 0.8)
                    if val is not None:
                        break
                if val is not None:
                    result[f"{f:02x}"] = val
                    save()
                print(f"\r  {f:02x}: {val if val is not None else '-':24} ({len(result)} answered)", end="", flush=True)
        except Exception as e:
            print(f"\n  link error: {e}; saving what was read")
        print(f"\n  {len(result)} fields answered in {time.time() - t0:.0f}s")
        try:
            await cli.stop_notify(O.PROXY_OUT)
        except Exception:
            pass
    save()
    print(f"  saved {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
