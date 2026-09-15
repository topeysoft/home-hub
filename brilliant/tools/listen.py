#!/usr/bin/env python3
"""Listen to everything a provisioned Brilliant switch reports, with timestamps.

Assumes explore.py has already bound the AppKey and pointed the models'
publish addresses at us. Does no configuration -- just connects and watches,
so you can run it while standing at the switch.

usage: listen.py [seconds]      (default 180)
"""
import asyncio
import sys
import time

from bleak import BleakClient, BleakScanner

import mesh
import onoff as O
from explore import describe, opcode_of, try_decrypt

SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 180


async def main():
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    print(f"target {key} ({node['name']!r}) -- connecting...")

    dev = await BleakScanner.find_device_by_address(node["ble_address"], timeout=30.0)
    if not dev:
        print("node not found (is it powered and in range?)")
        return

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        n = O.Node(cli, mtu, net, node)
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(n.netkey, n.iv, ctl=1, ttl=0, seq=seq, src=n.src,
                               dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                               nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu)
        await asyncio.sleep(0.4)

        print(f"\n{'=' * 58}")
        print(f"  LISTENING {SECONDS}s -- go interact with the switch")
        print(f"{'=' * 58}")
        print("  try, pausing ~3s between each so they separate:")
        print("    1. wave your hand in front of it        (PIR)")
        print("    2. single tap                           (on/off)")
        print("    3. double tap                           (scene)")
        print("    4. slide up/down the dimming groove     (level)")
        print("    5. then stand back and stay still ~20s  (motion clear)\n")

        t0 = time.time()
        seen, raw = {}, []
        end = asyncio.get_event_loop().time() + SECONDS
        while asyncio.get_event_loop().time() < end:
            try:
                typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=3)
            except asyncio.TimeoutError:
                continue
            if typ != 0x00:
                continue
            m = mesh.net_decrypt(n.netkey, n.iv, pdu)
            if not m:
                continue
            plain = try_decrypt(n, m)
            if not plain:
                continue
            op, olen = evt = opcode_of(plain)
            params = plain[olen:]
            tag = describe(op, olen)
            seen[tag] = seen.get(tag, 0) + 1
            raw.append((time.time() - t0, tag, params.hex()))
            print(f"  +{time.time() - t0:6.1f}s  [{m['src']:#06x}] {tag}: {params.hex()}")

        print(f"\n{'=' * 58}\n  SUMMARY")
        for k, v in sorted(seen.items(), key=lambda x: -x[1]):
            print(f"    {v:4d}  {k}")
        if not seen:
            print("    nothing received in the whole window")
        if raw:
            with open("events.log", "a") as f:
                for t, tag, hx in raw:
                    f.write(f"{t:.2f}\t{tag}\t{hx}\n")
            print(f"\n  {len(raw)} event(s) appended to ~/brilliant-mesh/events.log")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
