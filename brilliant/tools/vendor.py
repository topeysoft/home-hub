#!/usr/bin/env python3
"""Probe the Brilliant vendor model 0x0820/0x0001 with parameters.

The earlier sweep sent all 64 opcodes with an EMPTY payload and concluded that
no vendor opcode does anything. That conclusion is weaker than it looks: a
handler that length-checks its payload drops a zero-length message before it
ever dispatches, silently, every time. And we now know the model takes commands
-- Brilliant's panel writes a load type (dimmer vs switch) to the switch at
setup, which is not any SIG state and can only travel this way.

So: sweep again, with payloads, and log every reply with the network header
intact so an answer to the wrong address or under the wrong key still shows up.

A vendor access PDU is a 3-octet opcode: 0b11xxxxxx then the Company ID little
endian, then parameters.

    vendor.py                 opcodes 0xC0-0xFF, payloads: none, 00, 01
    vendor.py c0 c8           just that range
    vendor.py --payloads 00,01,02,ff

The node is expendable: it is ours, and anything a probe manages to break is
undone by a factory reset and provision.py.
"""
import asyncio
import sys

from bleak import BleakClient

import ble
import mesh
import onoff as O
import rawlog

CID = 0x0820


def parse_args(argv):
    payloads = [b"", b"\x00", b"\x01"]
    lo, hi = 0xC0, 0xFF
    wait = 0.45
    rest = []
    i = 0
    while i < len(argv):
        if argv[i] == "--wait":
            wait = float(argv[i + 1])
            i += 2
            continue
        if argv[i] == "--payloads":
            payloads = [bytes.fromhex(p) if p else b""
                        for p in argv[i + 1].split(",")]
            i += 2
            continue
        rest.append(argv[i])
        i += 1
    if len(rest) == 2:
        lo, hi = int(rest[0], 16), int(rest[1], 16)
    return lo, hi, payloads, wait


async def drain(n, cli, mtu, net, seconds, asm):
    """Collect what arrives, reassembling and acknowledging segmented replies.

    The vendor model answers some requests with a message too long for one PDU.
    Without reassembly those show only as repeating segment 0, and without a
    SegAck the node retransmits them into the next probe's window -- which is
    what made a clean request/response look like several opcodes answering.
    """
    out = []
    end = asyncio.get_event_loop().time() + seconds
    while asyncio.get_event_loop().time() < end:
        try:
            typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=0.4)
        except asyncio.TimeoutError:
            continue
        if typ != 0x00:
            continue
        m = mesh.net_decrypt(n.netkey, n.iv, pdu)
        if not m or m["ctl"]:
            continue
        t = m["transport"]
        now = asyncio.get_event_loop().time()
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
            out.append((m, "decoded", plain.hex(), now))
            break
        else:
            out.append((m, "undecodable", body.hex(), now))
    return out


async def main():
    lo, hi, payloads, wait = parse_args(sys.argv[1:])
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    print(f"target {key} ({node['name']!r})")
    print(f"opcodes 0x{lo:02x}-0x{hi:02x}, {len(payloads)} payload(s), "
          f"{wait}s reply window\n")

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
        await O.ensure_bound(n, net, node)

        asm = rawlog.Reassembler()
        hits = []
        total = (hi - lo + 1) * len(payloads)
        done = 0
        for op in range(lo, hi + 1):
            for pl in payloads:
                done += 1
                access = bytes([op]) + CID.to_bytes(2, "little") + pl
                # Drain anything still in flight so a late reply is never
                # credited to the next opcode -- that misattribution is what
                # made the first pass look like several opcodes answering.
                await drain(n, cli, mtu, net, 0.15, asm)
                t0 = asyncio.get_event_loop().time()
                await n._tx(access, use_appkey=True)
                got = await drain(n, cli, mtu, net, wait, asm)
                if got:
                    for m, kind, hx, at in got:
                        dt = at - t0   # when it ARRIVED, not when the window shut
                        line = (f"  0x{op:02x} payload {pl.hex() or '(none)':>6} "
                                f"-> +{dt * 1000:.0f}ms REPLY from "
                                f"0x{m['src']:04x} to 0x{m['dst']:04x} "
                                f"[{kind}] {hx}")
                        print(line)
                        hits.append(line)
                if done % 32 == 0:
                    print(f"  ... {done}/{total}")

        print("\n" + "=" * 60)
        if hits:
            print(f"  {len(hits)} reply/replies -- these opcodes do something:")
            for h in hits:
                print(h)
        else:
            print("  No opcode in this range answered with any payload tried.")
            print("  That rules out short payloads; it does not rule out the")
            print("  model, which we know takes a load-type write from the panel.")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
