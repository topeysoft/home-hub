#!/usr/bin/env python3
"""Log every mesh PDU the node gives us, decoded or not.

`explore.py` and `listen.py` only ever print messages they could decrypt at the
*application* layer, and they build the application nonce with our own address
hardcoded as the destination. So a message the switch publishes to a group
address, or under an AppKey we do not hold, or segmented with SZMIC=1, is
dropped in silence and looks exactly like "the switch sent nothing".

This tool never drops. For every PDU it prints the network-layer header --
src, dst, ctl, ttl, seq -- which needs the NetKey alone, and only then tries the
application layer, reporting *why* a decrypt failed rather than skipping it.

The distinction this buys:

  dst is not 0x0001      the firmware publishes somewhere we were not listening
  AID is not ours        it publishes under an AppKey the panel holds and we don't
  decrypt fails          our nonce/segmentation handling is wrong
  nothing at all         the switch really is silent, and now we know it

usage: rawlog.py [seconds]      (default 180)
"""
import asyncio
import sys
import time

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

SECONDS = _arg_int(180)

CTL_OPCODES = {0x00: "Segment Ack", 0x01: "Friend Poll", 0x02: "Friend Update",
               0x03: "Friend Request", 0x04: "Friend Offer", 0x05: "Friend Clear",
               0x06: "Friend Clear Confirm", 0x07: "Friend Subscription List Add",
               0x0A: "Heartbeat"}


def addr_kind(a):
    if a == 0x0000:
        return "unassigned"
    if a < 0x8000:
        return "unicast"
    if a < 0xC000:
        return "virtual"
    if a == 0xFFFF:
        return "all-nodes"
    return "group"


def opcode_of(p):
    if p[0] & 0x80 == 0:
        return p[0], 1
    if p[0] & 0xC0 == 0x80:
        return int.from_bytes(p[:2], "big"), 2
    return int.from_bytes(p[:3], "big"), 3


def name_opcode(op, n):
    if n == 3:
        cid = int.from_bytes(bytes([(op >> 8) & 0xFF, op & 0xFF]), "little")
        return f"VENDOR op 0x{(op >> 16) & 0x3F:02x} company 0x{cid:04x}"
    return {0x8204: "Generic OnOff Status", 0x8208: "Generic Level Status",
            0x0002: "Config Composition Data Status",
            0x8019: "Config Model Publication Status",
            0x803E: "Config Model App Status",
            0x0005: "Health Current Status", 0x0006: "Health Fault Status",
            }.get(op, f"opcode 0x{op:04x}")


class Reassembler:
    """Collect segmented upper-transport PDUs, keyed by (src, seqzero)."""

    def __init__(self):
        self.parts = {}

    def feed(self, m, t):
        hdr = int.from_bytes(t[1:4], "big")
        szmic = (hdr >> 23) & 1
        seqzero = (hdr >> 10) & 0x1FFF
        sego = (hdr >> 5) & 0x1F
        segn = hdr & 0x1F
        key = (m["src"], seqzero)
        slot = self.parts.setdefault(key, {})
        slot[sego] = t[4:]
        if len(slot) != segn + 1:
            return None, (szmic, seqzero, sego, segn, False)
        del self.parts[key]
        full = b"".join(slot[i] for i in sorted(slot))
        return full, (szmic, seqzero, sego, segn, True)


def try_app(key, nonce_type, szmic, seq, src, dst, iv, body, tag):
    nonce = bytes([nonce_type, 0x80 if szmic else 0x00]) \
        + seq.to_bytes(3, "big") + src.to_bytes(2, "big") \
        + dst.to_bytes(2, "big") + iv.to_bytes(4, "big")
    return mesh.ccm_decrypt(key, nonce, body, tag=tag)



async def send_segack(cli, mtu, net, netkey, iv, us, src, seqzero, segn):
    """Acknowledge a reassembled segmented message.

    Without this the node assumes the message was lost and retransmits it for
    as long as its timer allows, which both floods the log and means a genuinely
    segmented event -- the shape a PIR report with a payload would take -- is
    seen only as a repeating segment 0 that never completes.
    """
    block = (1 << (segn + 1)) - 1
    ack = bytes([0x00]) + ((seqzero << 2) & 0x7FFF).to_bytes(2, "big") \
        + block.to_bytes(4, "big")
    seq = mesh.next_seq(net)
    pdu = mesh.net_encrypt(netkey, iv, ctl=1, ttl=5, seq=seq, src=us, dst=src,
                           transport_pdu=ack)
    await O.send(cli, 0x00, pdu, mtu)


async def main():
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    netkey = bytes.fromhex(net["netkey"])
    appkey = bytes.fromhex(net["appkey"])
    devkey = bytes.fromhex(node["devkey"])
    us = net["provisioner_addr"]
    iv = net["iv_index"]
    our_aid = mesh.k4(appkey)
    our_nid, _, _ = mesh.k2(netkey, b"\x00")

    print(f"target {key} ({node['name']!r})")
    print(f"our NID 0x{our_nid:02x}   our AID 0x{our_aid:02x}   "
          f"our address 0x{us:04x}\n")

    dev = await ble.find_node(node["ble_address"])
    if not dev:
        print("node not found (is it powered and in range?)")
        return

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)

        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(netkey, iv, ctl=1, ttl=0, seq=seq, src=us,
                               dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                               nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu)
        await asyncio.sleep(0.4)

        print("=" * 64)
        print(f"  RAW LOG, {SECONDS}s -- every PDU, decoded or not")
        print("=" * 64)
        print("  pause ~3s between each so they separate in the log:")
        print("    1. wave your hand in front of it        (PIR)")
        print("    2. single tap                           (on/off)")
        print("    3. double tap                           (scene)")
        print("    4. slide up/down the dimming groove     (level)")
        print("    5. stand back and stay still ~20s       (motion clear)\n")

        asm = Reassembler()
        t0 = time.time()
        counts = {}
        end = asyncio.get_event_loop().time() + SECONDS
        while asyncio.get_event_loop().time() < end:
            try:
                typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=3)
            except asyncio.TimeoutError:
                continue
            ts = f"+{time.time() - t0:6.1f}s"

            if typ != 0x00:
                kind = {0x01: "mesh beacon", 0x02: "proxy config",
                        0x03: "provisioning"}.get(typ, f"proxy type 0x{typ:02x}")
                print(f"  {ts}  [{kind}] {pdu.hex()}")
                counts[kind] = counts.get(kind, 0) + 1
                continue

            m = mesh.net_decrypt(netkey, iv, pdu)
            if not m:
                nid = pdu[0] & 0x7F
                tag = f"foreign network NID 0x{nid:02x}"
                print(f"  {ts}  [{tag}] {len(pdu)}B {pdu.hex()}")
                counts[tag] = counts.get(tag, 0) + 1
                continue

            t = m["transport"]
            head = (f"  {ts}  src 0x{m['src']:04x} -> dst 0x{m['dst']:04x} "
                    f"({addr_kind(m['dst'])}) ttl {m['ttl']} seq {m['seq']}")

            if m["ctl"]:
                op = t[0] & 0x7F
                nm = CTL_OPCODES.get(op, f"control opcode 0x{op:02x}")
                print(f"{head}  CTL {nm}: {t[1:].hex()}")
                counts[nm] = counts.get(nm, 0) + 1
                continue

            akf, aid = (t[0] >> 6) & 1, t[0] & 0x3F
            if t[0] & 0x80:
                body, (szmic, seqzero, sego, segn, done) = asm.feed(m, t)
                if not done:
                    print(f"{head}  segment {sego}/{segn} (seqzero {seqzero})")
                    continue
                await send_segack(cli, mtu, net, netkey, iv, us, m["src"],
                                  seqzero, segn)
                seq_use = mesh.seq_auth(m["seq"], seqzero)
                tag_len = 8 if szmic else 4
                extra = f" [reassembled {segn + 1} segs, szmic {szmic}]"
            else:
                body, seq_use, tag_len, szmic = t[1:], m["seq"], 4, 0
                extra = ""

            keyinfo = (f"AKF {akf} AID 0x{aid:02x}"
                       + ("" if not akf else
                          " (ours)" if aid == our_aid else " <-- NOT OUR APPKEY"))

            plain = None
            for k, nt in (((appkey, 0x01) if akf else (devkey, 0x02)),
                          (devkey, 0x02), (appkey, 0x01)):
                try:
                    plain = try_app(k, nt, szmic, seq_use, m["src"], m["dst"],
                                    iv, body, tag_len)
                    break
                except Exception:
                    continue

            if plain is None:
                note = "undecryptable"
                if akf and aid != our_aid:
                    note += " -- held under an AppKey we do not have"
                elif addr_kind(m["dst"]) == "virtual":
                    note += " -- virtual address, needs the Label UUID as AAD"
                print(f"{head}  {keyinfo}{extra}  {note}: {body.hex()}")
                counts[note.split(' --')[0]] = counts.get(note.split(' --')[0], 0) + 1
                continue

            op, olen = opcode_of(plain)
            nm = name_opcode(op, olen)
            print(f"{head}  {keyinfo}{extra}  {nm}: {plain[olen:].hex()}")
            counts[nm] = counts.get(nm, 0) + 1

        print("\n" + "=" * 64 + "\n  SUMMARY")
        for k, v in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"    {v:4d}  {k}")
        if not counts:
            print("    nothing arrived at all -- not even a heartbeat.")
            print("    That is now a real negative: the network layer was open")
            print("    the whole time and every PDU would have been printed.")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
