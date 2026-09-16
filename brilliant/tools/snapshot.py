#!/usr/bin/env python3
"""Read every vendor field, twice, and diff -- to find the state that moves.

We can now read the switch's whole configuration/state store over the vendor
model. That turns the original question inside out. Rather than guessing which
field means "motion" or "load type", read all of them, have somebody work the
switch by hand, read them all again, and see what moved. Whatever changes is
state that tracks physical reality, by definition.

Counters that tick on their own (uptime, a config-change count) will show up
too; run it once with no interaction to learn which those are.

    snapshot.py                 read, pause for a hand touch, read, diff
    snapshot.py --pause 45      longer window
    snapshot.py --quiet         no prompt: measures only free-running drift

usage: snapshot.py [--pause N] [--quiet]
"""
import asyncio
import json
import sys
import time

from bleak import BleakClient

import ble
import mesh
import onoff as O
import rawlog

CID = 0x0820

# Discovered by sweeping 11 00 .. 11 ff; only these answer.
FIELDS = [0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x0b, 0x0c, 0x0d, 0x0e, 0x0f,
          0x11, 0x13, 0x19, 0x1a, 0x1b, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x24,
          0x25, 0x26, 0x27, 0x28, 0x2d, 0x2e, 0x2f, 0x31, 0x32, 0x40, 0x41,
          0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49, 0x4a, 0x4b, 0x4c,
          0x4d, 0x4e, 0x4f, 0x50, 0x51, 0x52, 0x53, 0x54, 0x55, 0x56, 0x57]


def parse_args(argv):
    pause, quiet = 30, False
    i = 0
    while i < len(argv):
        if argv[i] == "--pause":
            pause = int(argv[i + 1]); i += 2; continue
        if argv[i] == "--quiet":
            quiet = True; i += 1; continue
        i += 1
    return pause, quiet


async def read_field(n, cli, mtu, net, asm, field, timeout=1.2):
    """11 <field> -> 13 <field> <value> 00. Returns the value bytes."""
    await n._tx(bytes([0xC1]) + CID.to_bytes(2, "little")
                + bytes([0x11, field]), use_appkey=True)
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        try:
            typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=0.3)
        except asyncio.TimeoutError:
            continue
        if typ != 0x00:
            continue
        m = mesh.net_decrypt(n.netkey, n.iv, pdu)
        if not m or m["ctl"]:
            continue
        t = m["transport"]
        akf = (t[0] >> 6) & 1
        if t[0] & 0x80:
            body, (szmic, seqzero, sego, segn, done) = asm.feed(m, t)
            if not done:
                continue
            await rawlog.send_segack(cli, mtu, net, n.netkey, n.iv, n.src,
                                     m["src"], seqzero, segn)
            seq_use = mesh.seq_auth(m["seq"], seqzero)
            tag = 8 if szmic else 4
        else:
            body, seq_use, tag, szmic = t[1:], m["seq"], 4, 0
        for kk, nt in (((n.appkey, 0x01) if akf else (n.devkey, 0x02)),
                       (n.devkey, 0x02), (n.appkey, 0x01)):
            nonce = bytes([nt, 0x80 if szmic else 0x00]) \
                + seq_use.to_bytes(3, "big") + m["src"].to_bytes(2, "big") \
                + m["dst"].to_bytes(2, "big") + n.iv.to_bytes(4, "big")
            try:
                plain = mesh.ccm_decrypt(kk, nonce, body, tag=tag)
            except Exception:
                continue
            # c1 <cid lo> <cid hi> 13 <field> <value...> 00
            if len(plain) >= 5 and plain[3] == 0x13 and plain[4] == field:
                return plain[5:-1].hex()
            break
    return None


async def snap(n, cli, mtu, net, asm, label):
    print(f"  reading {len(FIELDS)} fields ({label})...", end="", flush=True)
    out = {}
    for f in FIELDS:
        out[f"{f:02x}"] = await read_field(n, cli, mtu, net, asm, f)
    missing = sum(1 for v in out.values() if v is None)
    print(f" done ({len(out) - missing}/{len(out)} answered)")
    return out


def diff(a, b):
    rows = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            rows.append((k, a.get(k), b.get(k)))
    return rows


async def main():
    pause, quiet = parse_args(sys.argv[1:])
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
        asm = rawlog.Reassembler()

        before = await snap(n, cli, mtu, net, asm, "before")

        if quiet:
            print(f"\n  QUIET: no interaction. Waiting {pause}s to learn which")
            print("  fields move on their own.\n")
        else:
            print(f"\n  >> NOW, for the next {pause}s, work the switch by hand:")
            print("  >>   wave at it, tap it, double-tap it, slide the groove.\n")
        for i in range(pause, 0, -10):
            print(f"     {i}s...")
            await asyncio.sleep(min(10, i))

        after = await snap(n, cli, mtu, net, asm, "after")

        stamp = int(time.time())
        path = f"snapshot-{stamp}.json"
        with open(path, "w") as f:
            json.dump({"before": before, "after": after}, f, indent=2)

        rows = diff(before, after)
        print("\n" + "=" * 64)
        if not rows:
            print("  Nothing changed in any of the 55 fields.")
        else:
            print(f"  {len(rows)} field(s) changed:")
            for k, x, y in rows:
                print(f"    field 0x{k}:  {x}  ->  {y}")
            if quiet:
                print("\n  These move on their own -- ignore them in the next run.")
            else:
                print("\n  Cross-check against a --quiet run: anything not in that")
                print("  list is state that responded to your hands.")
        print(f"\n  saved {path}")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
