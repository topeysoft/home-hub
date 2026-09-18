# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
import asyncio, sys
sys.path.insert(0, "/private/tmp/claude-501/-Users-temi-dev-home-hub/4218b043-2dd5-498e-8d59-3e2222904350/scratchpad")
import onoff as O, mesh
from bleak import BleakClient, BleakScanner

async def ack_set(n, on, tid):
    a = bytes([0x82, 0x02, 1 if on else 0, tid])
    print(f"  -> Generic OnOff Set (acknowledged): {'ON' if on else 'OFF'}")
    await n._tx(a, use_appkey=True)
    end = asyncio.get_event_loop().time() + 8
    while asyncio.get_event_loop().time() < end:
        try: typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=3)
        except asyncio.TimeoutError: continue
        if typ != 0x00: continue
        m = mesh.net_decrypt(n.netkey, n.iv, pdu)
        if not m or m["src"] != n.dst or (m["transport"][0] & 0x80): continue
        nonce = b"\x01\x00" + m["seq"].to_bytes(3,"big") + m["src"].to_bytes(2,"big") \
              + n.src.to_bytes(2,"big") + n.iv.to_bytes(4,"big")
        try: p = mesh.ccm_decrypt(n.appkey, nonce, m["transport"][1:], tag=4)
        except Exception: continue
        if p[:2] == b"\x82\x04":
            print(f"  <- Generic OnOff STATUS: present={p[2]}  ({p.hex()})")
            return p[2]
    print("  (no status)"); return None

async def main():
    net = mesh.load(); key = list(net["nodes"])[0]; node = net["nodes"][key]
    O.rx = asyncio.Queue()
    dev = await BleakScanner.find_device_by_address(node["ble_address"], timeout=30.0)
    if not dev: print("not found"); return
    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli,"mtu_size",23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        n = O.Node(cli, mtu, net, node)
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(n.netkey,n.iv,ctl=1,ttl=0,seq=seq,src=n.src,dst=0,
                               transport_pdu=bytes([0x00,0x01]),nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu); await asyncio.sleep(0.4)
        print(f"node {key}, MTU {mtu}\n")
        r1 = await ack_set(n, True, 0x51);  await asyncio.sleep(1.5)
        r2 = await ack_set(n, False, 0x52); await asyncio.sleep(1.5)
        r3 = await ack_set(n, True, 0x53)
        print()
        if (r1, r2, r3) == (1, 0, 1):
            print("VERIFIED: node reports the exact state we commanded (on, off, on).")
        else:
            print(f"states reported: {r1}, {r2}, {r3}")
        await cli.stop_notify(O.PROXY_OUT)
asyncio.run(main())
