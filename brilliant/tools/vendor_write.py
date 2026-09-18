#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Write one vendor field to a switch, over a proxy, and read it back.

`setfields.py` writes over a DIRECT BLE connection to the switch itself, which
means the laptop has to be in radio range of that particular switch and nothing
else may be holding its one GATT link. Neither is true often enough. This writes
the same field through whatever node on the network answers as a proxy, so the
mesh does the last hop -- the same route `pairs.py` reads over.

    write   C1 2008 12 <field> <value LE> 00   ->  C1 2008 13 <field> <value> 00

**The trailing 00 on a write is load-bearing**; without it the write is accepted
on the wire and silently dropped. So is the vendor model's AppKey binding, which
a switch we adopted already has.

It always prints the value BEFORE it writes, so there is a restore value in the
log even when nobody thought to save one, and reads back after to show what took.
A field read only at boot (the load type, and on the evidence `0x1b`) will read
back as written and still not be live until the switch is power cycled -- the
readback is not the proof, the behavior is.

    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/mesh-net.json \\
        python3 vendor_write.py 0006 1b 03
    ... vendor_write.py 0006 1b          # read only, no write

PANEL_NODE=<ble-addr> pins which node is used as the way in.
"""
import asyncio
import sys

from bleak import BleakClient

import mesh
import onoff as O
from pairs import CID, Link
from vendor_store import find_proxy


async def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    target = int(sys.argv[1], 16)
    field = int(sys.argv[2], 16)
    value = bytes.fromhex(sys.argv[3]) if len(sys.argv) > 3 else None

    net = mesh.load()
    O.rx = asyncio.Queue()
    dev = await find_proxy(bytes.fromhex(net["netkey"]))
    if not dev:
        print("no proxy in range for this network")
        return 1

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        link = Link(cli, net, mtu)
        seq = mesh.next_seq(net)
        await O.send(cli, 0x02, mesh.net_encrypt(link.netkey, link.iv, ctl=1, ttl=0, seq=seq,
                     src=link.us, dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                     nonce_type=0x03), mtu)
        await asyncio.sleep(0.4)

        # twice, because a dropped read looks exactly like a field that is not there
        raw = await link.field(target, field) or await link.field(target, field)
        # A Status is `13 <field> <value> 00`, so the reply carries a trailing byte that is
        # NOT part of the value. Echoing it back as a restore value writes one byte too many
        # and the switch drops the write in silence -- which cost a restore on a live light.
        before = raw[:-2] if raw and len(raw) > 2 else raw
        print(f"  0x{target:04x} field 0x{field:02x} BEFORE = {before}   (raw reply {raw})")
        if value is None:
            return 0
        if before is None:
            print("  refusing to write a field that did not answer a read -- no restore value")
            return 1

        access = bytes([0xC1]) + CID.to_bytes(2, "little") + bytes([0x12, field]) + value + b"\x00"
        await link._send_access(target, access)
        await asyncio.sleep(1.0)
        raw_after = await link.field(target, field) or await link.field(target, field)
        after = raw_after[:-2] if raw_after and len(raw_after) > 2 else raw_after
        print(f"  0x{target:04x} field 0x{field:02x} AFTER  = {after}   (raw reply {raw_after})")
        print(f"\n  to put it back:  vendor_write.py {target:04x} {field:02x} {before}")
        if after is None:
            print("  (readback failed -- that is a dropped reply, not proof the write failed)")
        elif after != value.hex():
            print("  WRITE DID NOT TAKE. Check the vendor model is bound to our AppKey.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
