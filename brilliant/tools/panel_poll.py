#!/usr/bin/env python3
"""Poll a live panel switch's vendor fields and print what changes -- to find PIR.

We hold the panel's netkey + appkey, and we watched the panel itself read this
list of vendor fields from a switch:

    01 07 08 0f 19 1c 28 2d 2e 2f 40 41 42

One of them is almost certainly motion. This connects to a panel proxy, then
repeatedly sends vendor GET (c1 2008 11 <field>) addressed to the target switch,
decodes the 0x13 status replies with the appkey, and prints any field whose
value changes -- with a timestamp, so you can line it up with walking past the
sensor and then leaving.

    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \\
        python3 tools/panel_poll.py [target_hex] [seconds]

target defaults to 0x000a (the switch seen reporting taps/dims). Pin the proxy
node with PANEL_NODE=<ble-addr> to avoid weak-node roulette.
"""
import asyncio
import os
import sys
import time

os.environ.setdefault(
    "BRILLIANT_MESH_STORE",
    os.path.expanduser("~/.config/brilliant-mesh/panel-net.json"))

from bleak import BleakClient, BleakScanner

import mesh
import onoff as O
import rawlog

CID = 0x0820
FIELDS = [0x01, 0x07, 0x08, 0x0f, 0x13, 0x19, 0x1c, 0x28,
          0x2d, 0x2e, 0x2f, 0x40, 0x41, 0x42]
# Focus on specific fields with POLL_FIELDS=13,28 (faster sampling, clearer signal)
_pf = os.environ.get("POLL_FIELDS")
if _pf:
    FIELDS = [int(x, 16) for x in _pf.split(",")]

TARGET = int(sys.argv[1], 16) if len(sys.argv) > 1 else 0x000a
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 150


async def find_proxy(netkey):
    our = mesh.k3(netkey)
    pin = os.environ.get("PANEL_NODE")
    if pin:
        d = await BleakScanner.find_device_by_address(pin, timeout=20.0)
        if d:
            print(f"  pinned proxy {pin}")
            return d
    print("  scanning 20s for a panel proxy...")
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
    net = mesh.load()
    netkey = bytes.fromhex(net["netkey"]); appkey = bytes.fromhex(net["appkey"])
    iv = net["iv_index"]; us = net.get("our_unicast", 0x1a)
    aid = mesh.k4(appkey)
    print(f"target switch 0x{TARGET:04x}   fields {[hex(f) for f in FIELDS]}")
    print(f"appkey AID 0x{aid:02x}, IV {iv}\n")

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
        print("=" * 60)
        print("  Walk PAST the switch a few times, then step well away and")
        print("  stay still ~15s. Watching which field moves.")
        print("=" * 60 + "\n")

        async def get(field):
            access = bytes([0xC1]) + CID.to_bytes(2, "little") + bytes([0x11, field])
            seq0 = mesh.next_seq(net)
            upper = mesh.app_encrypt_appkey(appkey, iv, seq0, us, TARGET, access)
            lower = bytes([0x40 | aid]) + upper
            npdu = mesh.net_encrypt(netkey, iv, ctl=0, ttl=7, seq=seq0, src=us,
                                    dst=TARGET, transport_pdu=lower)
            await O.send(cli, 0x00, npdu, mtu)

        def decode(field, m):
            t = m["transport"]
            if t[0] & 0x80:
                return None
            akf = (t[0] >> 6) & 1
            if not akf:
                return None
            nonce = bytes([0x01, 0x00]) + m["seq"].to_bytes(3, "big") \
                + m["src"].to_bytes(2, "big") + m["dst"].to_bytes(2, "big") \
                + iv.to_bytes(4, "big")
            try:
                p = mesh.ccm_decrypt(appkey, nonce, t[1:], tag=4)
            except Exception:
                return None
            # c1 2008 13 <field> <value...>
            if len(p) >= 5 and p[3] == 0x13:
                return p[4], p[5:].hex()
            return None

        last = {}
        t0 = time.time()
        end = asyncio.get_event_loop().time() + SECONDS
        while asyncio.get_event_loop().time() < end:
            for f in FIELDS:
                await get(f)
                # brief drain for the reply
                try:
                    while True:
                        typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=0.25)
                        if typ != 0x00:
                            continue
                        m = mesh.net_decrypt(netkey, iv, pdu)
                        if not m or m["src"] != TARGET:
                            continue
                        r = decode(f, m)
                        if not r:
                            continue
                        fld, val = r
                        changed = fld in last and last[fld] != val
                        if changed or (len(FIELDS) == 1):
                            arrow = f"{last.get(fld,'?')} -> {val}" if changed else val
                            print(f"  +{time.time()-t0:6.1f}s  0x{fld:02x}: {arrow}")
                        last[fld] = val
                except asyncio.TimeoutError:
                    pass

        print("\n  final field values:")
        for f in sorted(last):
            print(f"    0x{f:02x} = {last[f]}")
        if not last:
            print("    no replies -- switch may be out of relay range, or the")
            print("    target address is wrong. Try a target seen in panel_sniff.")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
