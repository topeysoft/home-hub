#!/usr/bin/env python3
"""Which vendor fields actually accept a write?

We can read 55 fields and we know 0x12 writes one (proved on 0x04). Load type --
the dimmer-vs-switch choice Brilliant's panel makes at setup -- must live in a
*writable* field, so separating configuration from read-only status cuts the
search down without needing anybody to watch a lamp.

For each field: read it, write a deliberately different value, read again, then
put the original back. A field whose readback follows the write is config; one
that ignores it is status the firmware owns.

Nothing is left modified: every changed field is restored before moving on, and
the original values are saved to a file first in case a restore fails.

    writable.py                 try every known field
    writable.py 1b,1c,56        just these

usage: writable.py [comma-separated hex fields]
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
from snapshot import FIELDS, read_field

CID = 0x0820

# Fields that identify the device or that we have already characterised.
# Writing these buys nothing and a bad restore would be a nuisance.
SKIP = {0x0e,        # Device UUID
        0x0f,        # DFU firmware id
        0x47,        # device identifier
        0x13,        # analogue, drifts (temperature)
        0x1d}        # uptime counter


async def write_field(n, value_hex, field):
    """12 <field> <value> 00.

    The trailing byte matters. A status is `13 <field> <value> 00` and
    read_field strips that last byte, so writing back what it returned produces
    a short PDU that the node ignores without complaint -- which reads as "this
    field is not writable" for every field at once.
    """
    await n._tx(bytes([0xC1]) + CID.to_bytes(2, "little")
                + bytes([0x12, field]) + bytes.fromhex(value_hex) + b"\x00",
                use_appkey=True)
    await asyncio.sleep(0.35)


def perturb(hex_value):
    """A value certainly different from the current one, same width."""
    b = bytearray.fromhex(hex_value)
    if not b:
        return None
    b[0] = (b[0] + 1) & 0xFF
    return bytes(b).hex()


async def main():
    want = None
    if len(sys.argv) > 1:
        want = [int(x, 16) for x in sys.argv[1].split(",")]
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

        fields = [f for f in (want or FIELDS) if f not in SKIP]
        print(f"  reading {len(fields)} originals first...", end="", flush=True)
        original = {}
        for f in fields:
            original[f] = await read_field(n, cli, mtu, net, asm, f)
        path = f"originals-{int(time.time())}.json"
        with open(path, "w") as fh:
            json.dump({f"{k:02x}": v for k, v in original.items()}, fh, indent=2)
        print(f" saved {path}\n")

        writable, readonly, failed = [], [], []
        for f in fields:
            cur = original[f]
            if cur is None:
                failed.append(f)
                continue
            new = perturb(cur)
            await write_field(n, new, f)
            back = await read_field(n, cli, mtu, net, asm, f)
            if back == new:
                writable.append((f, cur, new))
                print(f"  0x{f:02x}  WRITABLE   {cur} -> {back}")
                await write_field(n, cur, f)          # restore
                again = await read_field(n, cli, mtu, net, asm, f)
                if again != cur:
                    print(f"        !! restore did not take: now {again}")
            elif back == cur:
                readonly.append(f)
            else:
                failed.append(f)
                print(f"  0x{f:02x}  odd: wrote {new}, read {back}")

        print("\n" + "=" * 60)
        print(f"  writable config : {len(writable)} -> "
              + ", ".join(f"0x{f:02x}" for f, _, _ in writable))
        print(f"  read-only status: {len(readonly)} -> "
              + ", ".join(f"0x{f:02x}" for f in readonly))
        if failed:
            print(f"  inconclusive    : "
                  + ", ".join(f"0x{f:02x}" for f in failed))
        print(f"\n  originals saved in {path}")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
