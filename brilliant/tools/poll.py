#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Poll vendor fields fast and print every change, with timestamps.

Field 0x13 moves when somebody works the switch by hand and stays put when
nobody does -- so the switch tracks local input after all, and it is readable.
A before/after diff proves that much but cannot say *which* gesture moved it.
Polling one field quickly turns the counter into an event stream, so a wave, a
tap and a double-tap can be told apart by when the number jumps.

    poll.py                 poll field 0x13 for 120s
    poll.py 90 13,19,27     poll several fields (slower per cycle)

usage: poll.py [seconds] [comma-separated hex fields]
"""
import asyncio
import sys
import time

from bleak import BleakClient

import ble
import mesh
import onoff as O
import rawlog
from snapshot import read_field


def parse_args(argv):
    secs = 120
    fields = [0x13]
    if len(argv) > 0:
        try:
            secs = int(argv[0])
        except ValueError:
            pass
    if len(argv) > 1:
        fields = [int(x, 16) for x in argv[1].split(",")]
    return secs, fields


async def main():
    secs, fields = parse_args(sys.argv[1:])
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    print(f"target {key} ({node['name']!r})")
    print(f"polling {[f'0x{f:02x}' for f in fields]} for {secs}s")

    dev = await ble.find_node(node["ble_address"])
    if not dev:
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
        asm = rawlog.Reassembler()

        print("\n" + "=" * 64)
        print("  Do these ONE AT A TIME, leaving ~8s of stillness between,")
        print("  so each shows up as its own jump:")
        print("    1. wave your hand in front of it, then stand back")
        print("    2. single tap")
        print("    3. double tap")
        print("    4. slide the dimmer groove")
        print("    5. then stay completely still and away from it")
        print("=" * 64 + "\n")

        last = {}
        t0 = time.time()
        end = asyncio.get_event_loop().time() + secs
        while asyncio.get_event_loop().time() < end:
            for f in fields:
                v = await read_field(n, cli, mtu, net, asm, f, timeout=0.9)
                if v is None:
                    continue
                if f in last and v != last[f]:
                    try:
                        a = int.from_bytes(bytes.fromhex(last[f]), "little")
                        b = int.from_bytes(bytes.fromhex(v), "little")
                        delta = f"  (+{b - a})" if b > a else f"  ({b - a})"
                    except Exception:
                        delta = ""
                    print(f"  +{time.time() - t0:6.1f}s  field 0x{f:02x}: "
                          f"{last[f]} -> {v}{delta}")
                last[f] = v

        print(f"\n  final: " + ", ".join(
            f"0x{f:02x}={last.get(f)}" for f in fields))
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
