#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Control experiment: prove the node's publish path actually reaches us.

Every "the switch reported nothing" result in this project has so far turned out
to be a step we had not done -- no AppKey, no publish address. Before reading
silence during a hand touch as a fact about the firmware, prove that a
publication from this node, right now, over this connection, arrives.

An *unacknowledged* Generic OnOff Set produces no direct reply by definition, so
anything that comes back is a genuine model publication. If a Generic OnOff
Status arrives here, the publish path is live end to end, and silence while
somebody works the switch by hand means something.

usage: pubtest.py
"""
import asyncio
import sys
import time

from bleak import BleakClient

import ble
import mesh
import onoff as O

WINDOW = 8.0
_tid = 0


async def watch(n, seconds, label):
    """Drain everything that arrives, decoding it, for `seconds`."""
    got = []
    end = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < end:
        try:
            typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=1.5)
        except asyncio.TimeoutError:
            continue
        if typ != 0x00:
            continue
        m = mesh.net_decrypt(n.netkey, n.iv, pdu)
        if not m:
            continue
        t = m["transport"]
        if m["ctl"]:
            continue
        akf = (t[0] >> 6) & 1
        if t[0] & 0x80:
            print(f"    <- segmented from 0x{m['src']:04x} -> 0x{m['dst']:04x}")
            got.append(("segmented", None))
            continue
        for kk, nt in (((n.appkey, 0x01) if akf else (n.devkey, 0x02)),
                       (n.devkey, 0x02), (n.appkey, 0x01)):
            nonce = bytes([nt, 0x00]) + m["seq"].to_bytes(3, "big") \
                + m["src"].to_bytes(2, "big") + m["dst"].to_bytes(2, "big") \
                + n.iv.to_bytes(4, "big")
            try:
                plain = mesh.ccm_decrypt(kk, nonce, t[1:], tag=4)
            except Exception:
                continue
            op = int.from_bytes(plain[:2], "big")
            print(f"    <- 0x{m['src']:04x} -> 0x{m['dst']:04x}  "
                  f"opcode 0x{op:04x}  {plain.hex()}")
            got.append((op, plain))
            break
    return got


async def main():
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    print(f"target {key} ({node['name']!r})")
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
        print(f"connected, MTU {mtu}\n")

        published = []
        global _tid
        for on in (True, False, True):
            _tid = (_tid + 1) & 0xFF
            print(f"  -> Generic OnOff Set UNACKNOWLEDGED: "
                  f"{'ON' if on else 'OFF'}  (no direct reply is possible)")
            await n._tx(bytes([0x82, 0x03, 1 if on else 0, _tid]),
                        use_appkey=True)
            got = await watch(n, WINDOW, "after set")
            if not got:
                print("    <- nothing")
            published.extend(got)
            print()

        print("=" * 60)
        statuses = [p for op, p in published if op == 0x8204]
        if statuses:
            print(f"  PUBLISH PATH IS LIVE: {len(statuses)} Generic OnOff Status")
            print("  publication(s) arrived with no request to trigger them.")
            print("  So a silent switch during a hand touch is a real finding.")
        elif published:
            print("  Something arrived, but no Generic OnOff Status publication.")
            print("  Check the opcodes above before trusting any silence.")
        else:
            print("  NOTHING PUBLISHED. The model's publish address is set and")
            print("  the AppKey is bound, yet an unacknowledged Set produced no")
            print("  publication -- so this node's publish path is not working,")
            print("  and no 'the switch reports nothing' result can stand until")
            print("  it does. Re-check Config Model Publication Status.")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
