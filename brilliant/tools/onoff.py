#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bind an AppKey and drive a provisioned Brilliant switch with stock SIG models.

  Config AppKey Add      -> node learns our AppKey
  Config Model App Bind  -> bind it to Generic OnOff Server (0x1000) and Level (0x1002)
  Generic OnOff Set      -> turn the actual light on and off
  Generic Level Set      -> dim it

usage: onoff.py [blink|on|off|dim <0-100>]
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner

import mesh

PROXY_SVC = "00001828-0000-1000-8000-00805f9b34fb"
PROXY_IN = "00002add-0000-1000-8000-00805f9b34fb"
PROXY_OUT = "00002ade-0000-1000-8000-00805f9b34fb"
PDU_NETWORK, PDU_PROXY_CFG = 0x00, 0x02

rx = None
_buf = bytearray()
_tid = 0


def on_notify(_, data: bytearray):
    global _buf
    sar, typ = (data[0] & 0xC0) >> 6, data[0] & 0x3F
    p = bytes(data[1:])
    if sar == 0b00:
        rx.put_nowait((typ, p))
    elif sar == 0b01:
        _buf = bytearray(p)
    elif sar == 0b10:
        _buf += p
    else:
        _buf += p
        rx.put_nowait((typ, bytes(_buf)))


async def send(cli, typ, pdu, mtu):
    room = mtu - 3 - 1
    if len(pdu) <= room:
        await cli.write_gatt_char(PROXY_IN, bytes([typ]) + pdu, response=False)
        return
    chunks = [pdu[i:i + room] for i in range(0, len(pdu), room)]
    for i, c in enumerate(chunks):
        sar = 0b01 if i == 0 else (0b11 if i == len(chunks) - 1 else 0b10)
        await cli.write_gatt_char(PROXY_IN, bytes([(sar << 6) | typ]) + c,
                                  response=False)
        await asyncio.sleep(0.02)


class Node:
    def __init__(self, cli, mtu, net, node):
        self.cli, self.mtu, self.net = cli, mtu, net
        self.dst = node["unicast"]
        self.devkey = bytes.fromhex(node["devkey"])
        self.netkey = bytes.fromhex(net["netkey"])
        self.appkey = bytes.fromhex(net["appkey"])
        self.src = net["provisioner_addr"]
        self.iv = net["iv_index"]
        self.aid = mesh.k4(self.appkey)

    async def _tx(self, access, use_appkey):
        seq0 = mesh.next_seq(self.net)
        if use_appkey:
            upper = mesh.app_encrypt_appkey(self.appkey, self.iv, seq0, self.src,
                                            self.dst, access)
            akf_aid = 0x40 | (self.aid & 0x3F)
        else:
            upper = mesh.app_encrypt_devkey(self.devkey, self.iv, seq0, self.src,
                                            self.dst, access)
            akf_aid = 0x00

        if len(upper) <= 15:
            lower = bytes([akf_aid]) + upper
            npdu = mesh.net_encrypt(self.netkey, self.iv, ctl=0, ttl=5, seq=seq0,
                                    src=self.src, dst=self.dst, transport_pdu=lower)
            await send(self.cli, PDU_NETWORK, npdu, self.mtu)
            return

        # segmented access: 12 bytes of upper transport per segment
        parts = [upper[i:i + 12] for i in range(0, len(upper), 12)]
        segn = len(parts) - 1
        seqzero = seq0 & 0x1FFF
        print(f"     (segmenting into {segn + 1} parts, seqzero {seqzero})")
        for i, part in enumerate(parts):
            seq = seq0 if i == 0 else mesh.next_seq(self.net)
            hdr = (seqzero << 10) | (i << 5) | segn      # SZMIC=0
            lower = bytes([0x80 | akf_aid]) + hdr.to_bytes(3, "big") + part
            npdu = mesh.net_encrypt(self.netkey, self.iv, ctl=0, ttl=5, seq=seq,
                                    src=self.src, dst=self.dst,
                                    transport_pdu=lower)
            await send(self.cli, PDU_NETWORK, npdu, self.mtu)
            await asyncio.sleep(0.08)

    async def _segack(self, seqzero, segn):
        """Acknowledge a reassembled message so the node stops retransmitting."""
        block = (1 << (segn + 1)) - 1
        ack = bytes([0x00]) + ((seqzero << 2) & 0x7FFF).to_bytes(2, "big") \
            + block.to_bytes(4, "big")
        pdu = mesh.net_encrypt(self.netkey, self.iv, ctl=1, ttl=5,
                               seq=mesh.next_seq(self.net), src=self.src,
                               dst=self.dst, transport_pdu=ack)
        await send(self.cli, PDU_NETWORK, pdu, self.mtu)

    async def status(self, want_opcode, label, timeout=10.0):
        """Wait for one specific status opcode.

        Two things this must get right, both of which bit once. A status longer
        than 15 bytes -- Config Model Publication Status, for one -- arrives
        SEGMENTED, so it has to be reassembled or it looks like no reply at all.
        And a node that is already publishing floods this queue with its own
        traffic, so returning the first thing that decrypts hands back a motion
        reading and calls it a bind status: match the opcode that was asked for.
        """
        parts = {}
        end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end:
            try:
                typ, pdu = await asyncio.wait_for(rx.get(), timeout=3)
            except asyncio.TimeoutError:
                continue
            if typ != PDU_NETWORK:
                continue
            m = mesh.net_decrypt(self.netkey, self.iv, pdu)
            if not m or m["ctl"] or m["src"] != self.dst:
                continue
            t = m["transport"]
            akf = (t[0] >> 6) & 1
            if t[0] & 0x80:
                hdr = int.from_bytes(t[1:4], "big")
                szmic = (hdr >> 23) & 1
                seqzero = (hdr >> 10) & 0x1FFF
                sego, segn = (hdr >> 5) & 0x1F, hdr & 0x1F
                parts.setdefault(seqzero, {})[sego] = t[4:]
                if len(parts[seqzero]) != segn + 1:
                    continue
                body = b"".join(parts[seqzero][i] for i in sorted(parts[seqzero]))
                del parts[seqzero]
                await self._segack(seqzero, segn)
                seq_use, tag = mesh.seq_auth(m["seq"], seqzero), (8 if szmic else 4)
            else:
                body, seq_use, tag, szmic = t[1:], m["seq"], 4, 0
            # The nonce takes the message's real destination, not our own
            # address; see tools/test_nonce.py for why that distinction bites.
            for key, nt in (((self.appkey, 0x01) if akf
                             else (self.devkey, 0x02)),
                            (self.devkey, 0x02), (self.appkey, 0x01)):
                nonce = bytes([nt, 0x80 if szmic else 0x00]) + seq_use.to_bytes(3, "big") \
                    + m["src"].to_bytes(2, "big") + m["dst"].to_bytes(2, "big") \
                    + self.iv.to_bytes(4, "big")
                try:
                    plain = mesh.ccm_decrypt(key, nonce, body, tag=tag)
                except Exception:
                    continue
                op = plain[0] if plain[0] < 0x80 else int.from_bytes(plain[:2], "big")
                if op != want_opcode:
                    break            # someone else's traffic, keep waiting
                print(f"  <- {label} status: opcode 0x{op:04x} {plain.hex()}")
                return plain
        print(f"  (no {label} status within {timeout}s)")
        return None

    async def appkey_add(self):
        access = bytes([0x00]) + mesh.pack_key_indexes(0, 0) + self.appkey
        print("  -> Config AppKey Add")
        await self._tx(access, use_appkey=False)
        return await self.status(0x8003, "AppKey Add")

    async def bind(self, model_id, company=None):
        # SIG model: 2-byte model id. Vendor model: company id (LE) + model id (LE).
        mid = (company.to_bytes(2, "little") + model_id.to_bytes(2, "little")
               if company is not None else model_id.to_bytes(2, "little"))
        access = (bytes([0x80, 0x3D])
                  + self.dst.to_bytes(2, "little")
                  + (0).to_bytes(2, "little")
                  + mid)
        label = f"0x{company:04x}/0x{model_id:04x}" if company is not None else f"0x{model_id:04x}"
        print(f"  -> Config Model App Bind (model {label})")
        await self._tx(access, use_appkey=False)
        return await self.status(0x803E, "Model App Bind")

    async def publish(self, model_id, dest, company=None):
        """Config Model Publication Set. The Status comes back SEGMENTED."""
        mid = (company.to_bytes(2, "little") + model_id.to_bytes(2, "little")
               if company is not None else model_id.to_bytes(2, "little"))
        access = (bytes([0x03])
                  + self.dst.to_bytes(2, "little")
                  + dest.to_bytes(2, "little")
                  + (0).to_bytes(2, "little")   # appkey index 0, cred flag 0
                  + bytes([7])                  # TTL
                  + bytes([0])                  # period: none
                  + bytes([0])                  # retransmit
                  + mid)
        label = f"0x{company:04x}/0x{model_id:04x}" if company is not None else f"0x{model_id:04x}"
        print(f"  -> Config Model Publication Set ({label} -> 0x{dest:04x})")
        await self._tx(access, use_appkey=False)
        return await self.status(0x8019, "Model Publication")

    async def onoff(self, on):
        global _tid
        _tid = (_tid + 1) & 0xFF
        access = bytes([0x82, 0x03, 1 if on else 0, _tid])  # Set Unacknowledged
        print(f"  -> Generic OnOff Set: {'ON' if on else 'OFF'}")
        await self._tx(access, use_appkey=True)

    async def level(self, pct):
        global _tid
        _tid = (_tid + 1) & 0xFF
        lvl = int(-32768 + (pct / 100.0) * 65535)
        access = bytes([0x82, 0x09]) + (lvl & 0xFFFF).to_bytes(2, "little") \
            + bytes([_tid])
        print(f"  -> Generic Level Set: {pct}% (level {lvl})")
        await self._tx(access, use_appkey=True)


async def ensure_bound(n, net, node):
    """Add AppKey 0 to the node and bind the stock models, once.

    Provisioning hands over the NetKey and a DevKey and nothing else. Until a
    Config AppKey Add lands, the node holds no application key, so every bind
    answers `Invalid AppKey Index`, every publication set is refused, and every
    Get we send under the AppKey is undecryptable at the node and simply goes
    unanswered. That failure reads exactly like a switch that ignores the mesh,
    which is why this is no longer left to whoever runs the tools in the right
    order.
    """
    if node.get("bound"):
        return False
    print("  node has no AppKey yet -- adding and binding")
    await n.appkey_add()
    ok = True
    for mid, name, company in ((0x1000, "Generic OnOff Server", None),
                               (0x1002, "Generic Level Server", None),
                               (0x0001, "vendor 0x0820/0x0001", 0x0820)):
        r = await n.bind(mid, company)
        # Config Model App Status: opcode(2) status(1) ...
        st = r[2] if r and len(r) > 2 else None
        if st == 0x00:
            print(f"     {name}: bound")
        else:
            ok = False
            print(f"     {name}: NOT BOUND (status "
                  f"{'0x%02x' % st if st is not None else 'no reply'}) -- "
                  f"commands to this model will be ignored")
    # Binding alone makes a SILENT switch. A model publishes only if it has a
    # publish address, which Config Model Publication Set carries and which
    # nothing above touches -- so a node bound but not published answers every
    # Get, obeys every Set, and never announces a thing: no tap, no state
    # change, no motion. 0xffff is what the console itself uses (a panel switch
    # broadcasts its own touch to all-nodes), and it means any puck on the
    # network hears the switch without depending on which address is listening.
    for mid, name, company in ((0x1000, "Generic OnOff Server", None),
                               (0x1002, "Generic Level Server", None),
                               (0x0001, "vendor 0x0820/0x0001", 0x0820)):
        r = await n.publish(mid, 0xFFFF, company)
        st = r[2] if r and len(r) > 2 else None
        if st == 0x00:
            print(f"     {name}: publishes to 0xffff")
        else:
            ok = False
            print(f"     {name}: PUBLICATION NOT SET (status "
                  f"{'0x%02x' % st if st is not None else 'no reply'}) -- "
                  f"this switch will never announce itself")

    node["bound"] = ok
    mesh.save(net)
    print()
    return True


async def main():
    global rx
    rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    cmd = sys.argv[1] if len(sys.argv) > 1 else "blink"

    print(f"target {key} ({node['name']!r})")
    dev = await BleakScanner.find_device_by_address(node["ble_address"], timeout=30.0)
    if not dev:
        print("node not found")
        return

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        print(f"connected, MTU {mtu}\n")
        await cli.start_notify(PROXY_OUT, on_notify)

        n = Node(cli, mtu, net, node)
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(n.netkey, n.iv, ctl=1, ttl=0, seq=seq, src=n.src,
                               dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                               nonce_type=0x03)
        await send(cli, PDU_PROXY_CFG, cfg, mtu)
        await asyncio.sleep(0.4)

        await ensure_bound(n, net, node)

        if cmd == "blink":
            print("WATCH THE LIGHT:")
            for i in range(3):
                await n.onoff(True)
                await asyncio.sleep(1.5)
                await n.onoff(False)
                await asyncio.sleep(1.5)
            await n.onoff(True)
            await asyncio.sleep(1.0)
            print("\n  now dimming...")
            for pct in (75, 50, 25, 60, 100):
                await n.level(pct)
                await asyncio.sleep(1.2)
        elif cmd == "on":
            await n.onoff(True)
        elif cmd == "off":
            await n.onoff(False)
        elif cmd == "dim":
            await n.level(int(sys.argv[2]))
        await asyncio.sleep(1.0)
        await cli.stop_notify(PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
