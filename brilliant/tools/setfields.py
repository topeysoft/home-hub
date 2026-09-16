#!/usr/bin/env python3
"""Write a batch of vendor fields, keeping a restore file.

For bisecting a behaviour to a field: write half the candidates, see whether
the switch changes, restore, narrow. Originals go to a JSON file first, and
`restore.py <file>` puts them back.

    setfields.py 1b=01 56=01 0c=00          field=value, hex
    setfields.py --restore originals-*.json  put a saved set back

usage: setfields.py FIELD=HEX [...]  |  setfields.py --restore FILE
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
from snapshot import read_field
from writable import write_field


async def session():
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    print(f"target {key} ({node['name']!r})")
    dev = await ble.find_node(node["ble_address"])
    if not dev:
        return None
    cli = BleakClient(dev, timeout=30.0)
    await cli.connect()
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
    return cli, mtu, net, n, rawlog.Reassembler()


async def apply(sess, pairs, label):
    cli, mtu, net, n, asm = sess
    ok = True
    for f, v in pairs:
        await write_field(n, v, f)
        back = await read_field(n, cli, mtu, net, asm, f)
        mark = "ok" if back == v else f"!! read back {back}"
        ok &= back == v
        print(f"  {label} 0x{f:02x} = {v}   {mark}")
    return ok


async def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return
    sess = await session()
    if not sess:
        return
    cli, mtu, net, n, asm = sess
    try:
        if argv[0] == "--restore":
            saved = json.load(open(argv[1]))
            pairs = [(int(k, 16), v) for k, v in saved.items()]
            ok = await apply(sess, pairs, "restore")
            print("\n  restored" if ok else "\n  !! some restores did not take")
            return
        pairs = []
        for a in argv:
            f, v = a.split("=")
            pairs.append((int(f, 16), v.lower()))
        originals = {}
        for f, _ in pairs:
            originals[f"{f:02x}"] = await read_field(n, cli, mtu, net, asm, f)
        path = f"originals-{int(time.time())}.json"
        json.dump(originals, open(path, "w"), indent=2)
        print(f"  originals -> {path}")
        for f, v in pairs:
            cur = originals[f"{f:02x}"]
            if cur is not None and len(cur) != len(v):
                print(f"  !! 0x{f:02x}: current {cur} is {len(cur) // 2} byte(s), "
                      f"you gave {len(v) // 2}; sending anyway")
        ok = await apply(sess, pairs, "set")
        print(f"\n  {'all writes took' if ok else 'SOME WRITES DID NOT TAKE'}"
              f"\n  restore with:  setfields.py --restore {path}")
    finally:
        try:
            await cli.stop_notify(O.PROXY_OUT)
            await cli.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
