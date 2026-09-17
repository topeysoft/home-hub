#!/usr/bin/env python3
"""Read (and set) a node's model publication -- why a switch never reports itself.

Provisioning and binding are not enough to make a switch *announce* anything. A
model publishes only if it has a publish address, which is set separately by
Config Model Publication Set. Bind without publication and you get a node that
answers every Get and obeys every Set and volunteers nothing -- no tap, no
state change, no motion. That is a silent switch, and this is how you see it.

    publication.py 0004                 # show publish address per model
    publication.py 0004 --to 0xffff     # publish to all-nodes (what the console does)
    publication.py 0004 --to 0x0001     # publish at the provisioner instead

Config messages are DevKey-encrypted, so this works only on nodes we
provisioned ourselves (never on a switch still on the console's network).
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner

import mesh
import onoff as O
import rawlog
from onoff import Node

MODELS = [(0x1000, None, "Generic OnOff Server"),
          (0x1002, None, "Generic Level Server"),
          (0x0001, 0x0820, "vendor 0x0820/0x0001")]

CFG_STATUS = {0x00: "Success", 0x01: "Invalid Address", 0x02: "Invalid Model",
              0x03: "Invalid AppKey Index", 0x07: "Cannot Set",
              0x08: "Not a Subscribe Model", 0x0B: "Invalid Binding"}


def model_bytes(model, company):
    return (company.to_bytes(2, "little") + model.to_bytes(2, "little")
            if company is not None else model.to_bytes(2, "little"))


def show(label, r):
    if not r:
        print(f"  {label:<24} (no status)")
        return
    st = r[2]
    pub = int.from_bytes(r[5:7], "little")
    ttl = r[9] if len(r) > 9 else None
    note = "  <- SILENT: nothing is published" if pub == 0x0000 else ""
    print(f"  {label:<24} status {CFG_STATUS.get(st, hex(st)):<18} "
          f"publish addr 0x{pub:04x} ttl {ttl}{note}")


async def pub_status(n, asm, timeout=8.0):
    """Wait for Config Model Publication Status (0x8019) specifically.

    Not Node.status(): a switch that is already publishing floods the queue with
    its own vendor traffic, and a reader that returns the first thing it can
    decrypt will hand back a motion reading and call it a publication status.
    Config messages are DevKey-encrypted, so only the devkey is tried here.
    """
    end = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < end:
        try:
            typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=0.3)
        except asyncio.TimeoutError:
            continue
        if typ != 0x00:
            continue
        m = mesh.net_decrypt(n.netkey, n.iv, pdu)
        if not m or m["ctl"] or m["src"] != n.dst:
            continue
        t = m["transport"]
        if (t[0] >> 6) & 1:        # AppKey-encrypted: vendor/state traffic, not config
            continue
        # A Publication Status is 14-16 bytes plus its MIC, so it always arrives
        # SEGMENTED. Skipping segmented messages here is why this returned
        # "no status" for every model on a node that was answering perfectly.
        if t[0] & 0x80:
            body, (szmic, seqzero, sego, segn, done) = asm.feed(m, t)
            if not done:
                continue
            await rawlog.send_segack(n.cli, n.mtu, n.net, n.netkey, n.iv, n.src,
                                     m["src"], seqzero, segn)
            seq_use, tag = mesh.seq_auth(m["seq"], seqzero), (8 if szmic else 4)
        else:
            body, seq_use, tag, szmic = t[1:], m["seq"], 4, 0
        nonce = bytes([0x02, 0x80 if szmic else 0x00]) + seq_use.to_bytes(3, "big") \
            + m["src"].to_bytes(2, "big") + m["dst"].to_bytes(2, "big") + n.iv.to_bytes(4, "big")
        try:
            p = mesh.ccm_decrypt(n.devkey, nonce, body, tag=tag)
        except Exception:
            continue
        if len(p) >= 2 and int.from_bytes(p[:2], "big") == 0x8019:
            return p
    return None


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    target = f"0x{int(sys.argv[1], 16):04x}"
    dest = None
    if "--to" in sys.argv:
        dest = int(sys.argv[sys.argv.index("--to") + 1], 16)

    net = mesh.load()
    node = net["nodes"][target]
    O.rx = asyncio.Queue()
    print(f"node {target} on network {mesh.k3(bytes.fromhex(net['netkey'])).hex()}")
    dev = await BleakScanner.find_device_by_address(node["ble_address"], timeout=30.0)
    if not dev:
        print("  not reachable over GATT")
        return
    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(bytes.fromhex(net["netkey"]), net["iv_index"], ctl=1, ttl=0,
                               seq=seq, src=net["provisioner_addr"], dst=0,
                               transport_pdu=b"\x00\x01", nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu)
        await asyncio.sleep(0.4)
        n = Node(cli, mtu, net, node)
        asm = rawlog.Reassembler()

        for model, company, label in MODELS:
            mid = model_bytes(model, company)
            if dest is None:
                access = bytes([0x80, 0x18]) + n.dst.to_bytes(2, "little") + mid
            else:
                access = (bytes([0x03]) + n.dst.to_bytes(2, "little")
                          + dest.to_bytes(2, "little")
                          + (0).to_bytes(2, "little")   # appkey index 0, cred flag 0
                          + bytes([7])                  # TTL
                          + bytes([0])                  # period: none
                          + bytes([0])                  # retransmit
                          + mid)
            await n._tx(access, use_appkey=False)
            show(label, await pub_status(n, asm))
        try:
            await cli.stop_notify(O.PROXY_OUT)
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
