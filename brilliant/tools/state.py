#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read the switch's state without changing it, before and after a hand touch.

This exists because nothing else in `tools/` can read state without writing it.
`verify.py` uses an *acknowledged* Generic OnOff Set, which applies a value and
then reports the value it just applied -- so it can only ever tell you what you
commanded. Concluding from it that "local touch never updates the model" is
circular; the Set overwrote the evidence.

Generic OnOff Get (0x8201) and Generic Level Get (0x8205) are read-only. If the
switch does track its own physical state, this is what shows it.

    python3 tools/state.py

It reads, waits for you to work the switch by hand, then reads again.
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner

import ble
import mesh
import onoff as O

def _arg_int(default):
    """argv[1] as an int, tolerating anything else.

    These modules get imported by other tools, which carry their own argv.
    Parsing it eagerly at import time made `import rawlog` crash whenever the
    importing tool's first argument was not a number -- and the crash looked
    exactly like a probe that got no reply.
    """
    try:
        return int(sys.argv[1])
    except (IndexError, ValueError):
        return default

PAUSE = _arg_int(20)


async def get(n, opcode, want, label, timeout=10.0):
    """Send a read-only Get and return the decrypted Status access PDU."""
    await n._tx(opcode, use_appkey=True)
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        try:
            typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=3)
        except asyncio.TimeoutError:
            continue
        if typ != 0x00:
            continue
        m = mesh.net_decrypt(n.netkey, n.iv, pdu)
        if not m or m["src"] != n.dst or m["ctl"] or (m["transport"][0] & 0x80):
            continue
        t = m["transport"]
        nonce = b"\x01\x00" + m["seq"].to_bytes(3, "big") \
            + m["src"].to_bytes(2, "big") + m["dst"].to_bytes(2, "big") \
            + n.iv.to_bytes(4, "big")
        try:
            plain = mesh.ccm_decrypt(n.appkey, nonce, t[1:], tag=4)
        except Exception:
            continue
        if int.from_bytes(plain[:2], "big") == want:
            return plain
    print(f"  (no {label} Status within {timeout}s)")
    return None


async def read_both(n, when):
    print(f"\n--- {when} ---")
    s = await get(n, bytes([0x82, 0x01]), 0x8204, "Generic OnOff")
    onoff = None
    if s:
        onoff = s[2]
        tgt = f", target {s[3]}" if len(s) > 3 else ""
        print(f"  OnOff : present {onoff}{tgt}   ({s.hex()})")
    lv = await get(n, bytes([0x82, 0x05]), 0x8208, "Generic Level")
    level = None
    if lv:
        level = int.from_bytes(lv[2:4], "little", signed=True)
        print(f"  Level : {level}  ({(level + 32768) * 100 // 65535}%)"
              f"   ({lv.hex()})")
    return onoff, level


async def main():
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    print(f"target {key} ({node['name']!r}) -- connecting...")

    dev = await ble.find_node(node["ble_address"])
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

        if not node.get("bound"):
            print("\n  This node has no AppKey yet, so a Generic OnOff Get is")
            print("  undecryptable at the node and will go unanswered -- which")
            print("  would look exactly like a switch that ignores the mesh.")
            print("  Adding it now rather than reporting a false negative.")
            await O.ensure_bound(n, net, node)

        before = await read_both(n, "BEFORE (nothing has been commanded)")

        print(f"\n  >> Now change the light BY HAND: tap the switch, and slide")
        print(f"  >> the dimmer groove to a clearly different brightness.")
        for i in range(PAUSE, 0, -5):
            print(f"     {i}s...")
            await asyncio.sleep(5)

        after = await read_both(n, "AFTER (still nothing commanded)")

        print("\n" + "=" * 58)
        if before == (None, None) or after == (None, None):
            print("  Inconclusive -- a Get went unanswered.")
            print("  Check the bind statuses above: if they say Invalid AppKey")
            print("  Index, the node never received AppKey 0 and this says")
            print("  nothing about whether it tracks its own state.")
        elif before != after:
            print("  The model DOES track the physical switch.")
            print(f"  {before} -> {after}")
            print("  So state is readable by polling, and the earlier")
            print("  'local touch bypasses the mesh' finding was an artefact")
            print("  of reading with an acknowledged Set.")
        else:
            print("  Unchanged across a hand operation -- the model really does")
            print("  ignore local touch. Optimistic state is the only option")
            print("  short of new firmware.")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
