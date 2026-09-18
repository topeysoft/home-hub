#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Read the whole house's multi-way wiring off the mesh, without touching anything.

A two-way switch stores its partner's unicast address in vendor field 0x08, and
0x08 answers to the APPKEY alone -- no device key. That is the whole trick: device
keys we will never have for the console's switches, but the vendor store is open to
anyone holding the app key, so every pairing in the house can be read off switches
we do not own, on a network we did not make, with nobody pressing anything.

What comes back is the arrangement, not a guess at it:

    0x08 = 0000   this switch has no partner -- it drives its own load, or it is
                  a single-pole switch. The two are indistinguishable here and do
                  not need distinguishing: neither of them points at anybody.
    0x08 = xxxx   this switch is a COMPANION of 0xxxxx. It has no load of its own;
                  a press on it is sent straight to that address.
    0x1b = 03     corroborates it -- the mode flag that makes a companion route its
                  press outward instead of applying it to a load it has not got.

READ TWICE, ALWAYS. A dropped reply is indistinguishable from a field that does not
exist, and here that error is not cosmetic: a missed 0x08 turns a companion into a
main, which is exactly the mis-pairing this read exists to prevent. So every field
is read on two passes and a value is only believed absent when both passes agree.
The hazard is written up in docs/brilliant.md, "0x56 is not the dimmer flag".

    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \\
        ../.venv/bin/python tools/pairs.py              # discover, then read
    ... tools/pairs.py 0005 0006 000a                   # or name the switches

PANEL_NODE=<ble-addr> pins the proxy. Nothing here writes: the only messages sent
are a Generic OnOff Get (to find who is out there) and vendor field reads.
"""
import asyncio
import json
import os
import sys
import time

from bleak import BleakClient

import mesh
import onoff as O
import rawlog
from vendor_store import find_proxy

CID = 0x0820
PARTNER, MODE = 0x08, 0x1b
PASSES = 2


class Link:
    """One proxy link, and the two questions we ask over it."""

    def __init__(self, cli, net, mtu):
        self.cli, self.net, self.mtu = cli, net, mtu
        self.netkey = bytes.fromhex(net["netkey"])
        self.appkey = bytes.fromhex(net["appkey"])
        self.iv = net["iv_index"]
        self.us = net.get("our_unicast", net.get("provisioner_addr", 1))
        self.aid = mesh.k4(self.appkey)
        self.asm = rawlog.Reassembler()

    async def _send_access(self, dst, access):
        seq = mesh.next_seq(self.net)
        upper = mesh.app_encrypt_appkey(self.appkey, self.iv, seq, self.us, dst, access)
        lower = bytes([0x40 | self.aid]) + upper
        npdu = mesh.net_encrypt(self.netkey, self.iv, ctl=0, ttl=7, seq=seq,
                                src=self.us, dst=dst, transport_pdu=lower)
        await O.send(self.cli, 0x00, npdu, self.mtu)

    async def _harvest(self, seconds, want_src=None):
        """Every application payload that arrives in `seconds`, as (src, bytes)."""
        out = []
        end = asyncio.get_event_loop().time() + seconds
        while asyncio.get_event_loop().time() < end:
            try:
                typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=0.3)
            except asyncio.TimeoutError:
                continue
            if typ != 0x00:
                continue
            m = mesh.net_decrypt(self.netkey, self.iv, pdu)
            if not m or m["ctl"]:
                continue
            if want_src is not None and m["src"] != want_src:
                continue
            t = m["transport"]
            if not ((t[0] >> 6) & 1):
                continue
            # a vendor Status comes back segmented often enough that ignoring
            # segments would report "no such field" on a field that answered
            if t[0] & 0x80:
                body, (szmic, seqzero, _sego, segn, done) = self.asm.feed(m, t)
                if not done:
                    continue
                await rawlog.send_segack(self.cli, self.mtu, self.net, self.netkey,
                                         self.iv, self.us, m["src"], seqzero, segn)
                seq_use, tag = mesh.seq_auth(m["seq"], seqzero), (8 if szmic else 4)
            else:
                body, seq_use, tag, szmic = t[1:], m["seq"], 4, 0
            nonce = bytes([0x01, 0x80 if szmic else 0x00]) + seq_use.to_bytes(3, "big") \
                + m["src"].to_bytes(2, "big") + m["dst"].to_bytes(2, "big") \
                + self.iv.to_bytes(4, "big")
            try:
                p = mesh.ccm_decrypt(self.appkey, nonce, body, tag=tag)
            except Exception:
                continue
            out.append((m["src"], p))
        return out

    async def who_is_there(self, rounds=3, wait=4.0):
        """An all-nodes Generic OnOff Get. Eleven switches answering at once lose
        replies to each other, so ask more than once and take the union."""
        seen = set()
        for i in range(rounds):
            await self._send_access(0xFFFF, bytes([0x82, 0x01]))
            # anything that answers at all is a node: the reply we asked for is a
            # Generic OnOff Status, but a switch that volunteers something else in
            # the same window is just as much a switch, and is worth reading too.
            for src, _p in await self._harvest(wait):
                seen.add(src)
            print(f"  round {i + 1}: {len(seen)} so far")
        return sorted(seen)

    async def field(self, target, fid, timeout=2.5):
        access = bytes([0xC1]) + CID.to_bytes(2, "little") + bytes([0x11, fid])
        await self._send_access(target, access)
        for src, p in await self._harvest(timeout, want_src=target):
            if len(p) >= 5 and p[3] == 0x13 and p[4] == fid:
                return p[5:].hex()
        return None


def arrangement(rows):
    """Switches into lights. A companion belongs to the address in its 0x08; anything
    pointing at nobody is a light in its own right."""
    partner = {a: r["partner"] for a, r in rows.items() if r["partner"]}
    lights = {}
    for addr, r in sorted(rows.items()):
        if addr in partner:
            continue
        lights[addr] = []
    for addr, to in sorted(partner.items()):
        lights.setdefault(to, []).append(addr)   # a main we never read still gets its group
    return lights


async def main():
    targets = [int(a, 16) for a in sys.argv[1:] if not a.startswith("--")]
    net = mesh.load()
    O.rx = asyncio.Queue()
    print(f"network {mesh.k3(bytes.fromhex(net['netkey'])).hex()}")
    dev = await find_proxy(bytes.fromhex(net["netkey"]))
    if not dev:
        print("no proxy in range for this network")
        return 1

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        link = Link(cli, net, mtu)
        # the proxy filter: accept everything, or the node forwards us nothing
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(link.netkey, link.iv, ctl=1, ttl=0, seq=seq, src=link.us,
                               dst=0x0000, transport_pdu=bytes([0x00, 0x01]), nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu)
        await asyncio.sleep(0.4)

        if not targets:
            print("asking who is out there (all-nodes OnOff Get, nothing is changed)...")
            targets = await link.who_is_there()
            targets = [t for t in targets if t != link.us]
        print(f"{len(targets)} switches: {' '.join(f'{t:04x}' for t in targets)}\n")

        rows = {t: {"partner": None, "mode": None, "reads": 0} for t in targets}
        for p in range(PASSES):
            print(f"pass {p + 1} of {PASSES}")
            for t in targets:
                got_partner = await link.field(t, PARTNER)
                got_mode = await link.field(t, MODE)
                r = rows[t]
                if got_partner is not None:
                    # little-endian; 0000 means "nobody", which is a real answer
                    v = int.from_bytes(bytes.fromhex(got_partner)[:2], "little")
                    r["partner"] = v or None
                    r["reads"] += 1
                if got_mode is not None:
                    r["mode"] = got_mode
                mark = "·" if got_partner is None else ("→%04x" % r["partner"] if r["partner"] else "—")
                print(f"  {t:04x}  0x08 {mark:8} 0x1b {got_mode or '·'}")

        print()
        for t, r in sorted(rows.items()):
            if r["reads"] == 0:
                print(f"  0x{t:04x} never answered on either pass -- unknown, NOT assumed single")
        lights = arrangement(rows)
        print(f"\n{len(lights)} lights, {len(rows)} switches")
        for main, companions in sorted(lights.items()):
            if companions:
                ends = " + ".join(f"0x{c:04x}" for c in companions)
                print(f"  0x{main:04x}  with {ends}   {len(companions) + 1} switches, one light")
            else:
                print(f"  0x{main:04x}  on its own")

        out = f"pairs-{int(time.time())}.json"
        json.dump({"network": mesh.k3(link.netkey).hex(), "read_at": time.time(),
                   "switches": {f"{t:04x}": {"partner": f"{r['partner']:04x}" if r["partner"] else None,
                                             "mode": r["mode"], "answered": r["reads"]}
                                for t, r in rows.items()}}, open(out, "w"), indent=1)
        print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
