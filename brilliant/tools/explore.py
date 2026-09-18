#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Open up everything the Brilliant switch can tell us.

  1. bind our AppKey to the vendor model (0x0820 / 0x0001) and to OnOff + Level
  2. point each model's PUBLISH address at us, so the node reports events
     unprompted -- the same path motion used to take to the dead Control
  3. listen, and decode whatever arrives while you touch the switch / wave at it

usage: explore.py [listen_seconds]
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner

import ble
import mesh
import onoff as O

VENDOR_CID = 0x0820
VENDOR_MID = 0x0001

SIG_NAMES = {0x1000: "Generic OnOff Server", 0x1002: "Generic Level Server",
             0x0002: "Health Server"}

CFG_STATUS = {0x00: "Success", 0x01: "Invalid Address", 0x02: "Invalid Model",
              0x03: "Invalid AppKey Index", 0x04: "Invalid NetKey Index",
              0x05: "Insufficient Resources", 0x06: "Key Index Already Stored",
              0x07: "Invalid PublishParameters",
              0x08: "Not a Subscribe Model", 0x09: "Storage Failure",
              0x0A: "Feature Not Supported", 0x0B: "Cannot Update",
              0x0C: "Cannot Remove", 0x0D: "Cannot Bind",
              0x0E: "Temporarily Unable to Change State",
              0x0F: "Cannot Set", 0x10: "Unspecified Error",
              0x11: "Invalid Binding"}

def _arg_int(default):
    """argv[1] as an int, tolerating anything else.

    This module gets imported by other tools, which carry their own argv.
    Parsing it eagerly at import time made the import crash whenever the
    importing tool's first argument was not a number -- and the crash looked
    exactly like a probe that got no reply.
    """
    try:
        return int(sys.argv[1])
    except (IndexError, ValueError):
        return default


LISTEN = _arg_int(75)

segs = {}


def opcode_of(p):
    if p[0] & 0x80 == 0:
        return p[0], 1
    if p[0] & 0xC0 == 0x80:
        return int.from_bytes(p[:2], "big"), 2
    return int.from_bytes(p[:3], "big"), 3          # vendor, 3 octets


def describe(op, n):
    if n == 3:
        cid = int.from_bytes(bytes([op >> 8 & 0xFF, op & 0xFF]), "little")
        return f"VENDOR op 0x{(op >> 16) & 0x3F:02x} company 0x{cid:04x}"
    return {0x8204: "Generic OnOff Status", 0x8208: "Generic Level Status",
            0x0002: "Config Composition Data Status",
            0x8003: "Config AppKey Status", 0x803E: "Config Model App Status",
            0x8019: "Config Model Publication Status",
            0x0005: "Health Current Status",
            0x0006: "Health Fault Status"}.get(op, f"opcode 0x{op:04x}")


async def await_status(n, cli, mtu, want, label, timeout=12.0):
    """Read a Config status, reassembling segments and acking them."""
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        try:
            typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=3)
        except asyncio.TimeoutError:
            continue
        if typ != 0x00:
            continue
        m = mesh.net_decrypt(n.netkey, n.iv, pdu)
        if not m or m["src"] != n.dst:
            continue
        t = m["transport"]
        if t[0] & 0x80:                       # segmented -> ack it
            hdr = int.from_bytes(t[1:4], "big")
            seqzero, sego, segn = (hdr >> 10) & 0x1FFF, (hdr >> 5) & 0x1F, hdr & 0x1F
            store = segs.setdefault(seqzero, {})
            store[sego] = t[4:]
            if len(store) == segn + 1:
                block = 0
                for i in store:
                    block |= 1 << i
                ack = bytes([0x00]) + ((seqzero << 2) & 0x7FFF).to_bytes(2, "big") \
                    + block.to_bytes(4, "big")
                aseq = mesh.next_seq(n.net)
                apdu = mesh.net_encrypt(n.netkey, n.iv, ctl=1, ttl=5, seq=aseq,
                                        src=n.src, dst=n.dst, transport_pdu=ack)
                await O.send(cli, 0x00, apdu, mtu)
        plain = try_decrypt(n, m)
        if not plain:
            continue
        op, olen = opcode_of(plain)
        if op == want:
            return plain
        print(f"     (saw {describe(op, olen)})")
    return None


async def bind(n, cli, mtu, model, vendor=False):
    mid = (VENDOR_CID.to_bytes(2, "little") + VENDOR_MID.to_bytes(2, "little")
           if vendor else model.to_bytes(2, "little"))
    access = bytes([0x80, 0x3D]) + n.dst.to_bytes(2, "little") \
        + (0).to_bytes(2, "little") + mid
    label = "vendor 0x0820/0x0001" if vendor else SIG_NAMES.get(model, hex(model))
    print(f"  -> bind AppKey to {label}")
    await n._tx(access, use_appkey=False)
    r = await await_status(n, cli, mtu, 0x803E, "bind")
    if r:
        print(f"     status: {CFG_STATUS.get(r[2], hex(r[2]))}")
    else:
        print("     (no status)")
    return r


async def publish_to_us(n, cli, mtu, model, vendor=False):
    mid = (VENDOR_CID.to_bytes(2, "little") + VENDOR_MID.to_bytes(2, "little")
           if vendor else model.to_bytes(2, "little"))
    access = (bytes([0x03])
              + n.dst.to_bytes(2, "little")       # element
              + n.src.to_bytes(2, "little")       # publish address = us
              + (0).to_bytes(2, "little")         # appkey idx 0, cred flag 0
              + bytes([7])                        # TTL
              + bytes([0])                        # period: none
              + bytes([0])                        # retransmit
              + mid)
    label = "vendor 0x0820/0x0001" if vendor else SIG_NAMES.get(model, hex(model))
    print(f"  -> publish {label} -> 0x{n.src:04x} (us)")
    await n._tx(access, use_appkey=False)
    r = await await_status(n, cli, mtu, 0x8019, "publication")
    if r:
        pub = int.from_bytes(r[5:7], "little")
        print(f"     status: {CFG_STATUS.get(r[2], hex(r[2]))}  "
              f"publish addr now 0x{pub:04x}")
    else:
        print("     (no status)")
    return r


def try_decrypt(n, m):
    """Return plaintext access PDU, or None."""
    t = m["transport"]
    if t[0] & 0x80:                                 # segmented
        hdr = int.from_bytes(t[1:4], "big")
        szmic, seqzero = (hdr >> 23) & 1, (hdr >> 10) & 0x1FFF
        sego, segn = (hdr >> 5) & 0x1F, hdr & 0x1F
        segs.setdefault(seqzero, {})[sego] = t[4:]
        if len(segs[seqzero]) != segn + 1:
            return None
        full = b"".join(segs[seqzero][i] for i in sorted(segs[seqzero]))
        sa = mesh.seq_auth(m["seq"], seqzero)
        del segs[seqzero]
        akf = (t[0] >> 6) & 1
        tag = 8 if szmic else 4
        body, seq_use = full, sa
    else:
        akf = (t[0] >> 6) & 1
        body, seq_use, tag = t[1:], m["seq"], 4

    # The application nonce takes the message's REAL destination and the
    # ASZMIC bit. Hardcoding our own address here silently discarded anything
    # the node published to a group address; ignoring ASZMIC discarded every
    # segmented message carrying a 64-bit MIC. Both look like "it sent nothing".
    aszmic = 0x80 if (tag == 8) else 0x00
    for key, kind in (((n.appkey, "app") if akf else (n.devkey, "dev")),
                      (n.devkey, "dev"), (n.appkey, "app")):
        nt = bytes([0x01 if kind == "app" else 0x02, aszmic])
        nonce = nt + seq_use.to_bytes(3, "big") + m["src"].to_bytes(2, "big") \
            + m["dst"].to_bytes(2, "big") + n.iv.to_bytes(4, "big")
        try:
            return mesh.ccm_decrypt(key, nonce, body, tag=tag)
        except Exception:
            continue
    return None


async def main():
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    print(f"target {key} ({node['name']!r})\n")

    dev = await ble.find_node(node["ble_address"])
    if not dev:
        print("node not found")
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
        print(f"connected, MTU {mtu}\n--- binding ---")

        # Without this every bind below answers Invalid AppKey Index.
        await O.ensure_bound(n, net, node)

        await bind(n, cli, mtu, VENDOR_MID, vendor=True)
        await bind(n, cli, mtu, 0x0002)
        print("\n--- publication ---")
        await publish_to_us(n, cli, mtu, VENDOR_MID, vendor=True)
        await publish_to_us(n, cli, mtu, 0x1000)
        await publish_to_us(n, cli, mtu, 0x1002)
        await publish_to_us(n, cli, mtu, 0x0002)

        print(f"\n=== LISTENING {LISTEN}s ===")
        print("  >> WAVE AT THE SWITCH (PIR), TAP IT, DOUBLE-TAP IT,")
        print("  >> AND SLIDE YOUR FINGER ON THE DIMMER GROOVE <<\n")

        end = asyncio.get_event_loop().time() + LISTEN
        seen = {}
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
                # Never swallow this: a PDU we decrypted at the network layer
                # but not at the application layer is a real event we cannot
                # read, which is a different fact from silence.
                tag = f"UNDECODED -> 0x{m['dst']:04x}"
                seen[tag] = seen.get(tag, 0) + 1
                print(f"  [{m['src']:#06x}] {tag}: {m['transport'].hex()}")
                continue
            op, olen = opcode_of(plain)
            params = plain[olen:]
            tag = describe(op, olen)
            seen[tag] = seen.get(tag, 0) + 1
            print(f"  [{m['src']:#06x}] {tag}: {params.hex()}")

        print("\n=== SUMMARY ===")
        for k, v in sorted(seen.items(), key=lambda x: -x[1]):
            print(f"  {v:4d}  {k}")
        if not seen:
            print("  nothing received")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
