#!/usr/bin/env python3
"""Read Composition Data Page 0 from a node we provisioned.

Connects to the node's Mesh Proxy service, opens the proxy filter (a fresh
connection defaults to an empty allow-list and would drop our reply), then
sends Config Composition Data Get (0x8008) encrypted with the node's DevKey.
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner

import mesh

PROXY_SVC = "00001828-0000-1000-8000-00805f9b34fb"
PROXY_IN = "00002add-0000-1000-8000-00805f9b34fb"
PROXY_OUT = "00002ade-0000-1000-8000-00805f9b34fb"

PDU_NETWORK, PDU_PROXY_CFG = 0x00, 0x02

FEATURES = {0: "Relay", 1: "Proxy", 2: "Friend", 3: "Low Power"}

# a few SIG model ids worth naming
MODELS = {
    0x0000: "Configuration Server", 0x0001: "Configuration Client",
    0x0002: "Health Server", 0x0003: "Health Client",
    0x1000: "Generic OnOff Server", 0x1001: "Generic OnOff Client",
    0x1002: "Generic Level Server", 0x1003: "Generic Level Client",
    0x1004: "Generic Default Transition Time Server",
    0x1006: "Generic Power OnOff Server", 0x1007: "Generic Power OnOff Setup Server",
    0x1008: "Generic Power OnOff Client",
    0x1300: "Light Lightness Server", 0x1301: "Light Lightness Setup Server",
    0x1302: "Light Lightness Client",
    0x1303: "Light CTL Server", 0x1306: "Light HSL Server",
    0x1100: "Sensor Server", 0x1101: "Sensor Setup Server",
    0x1102: "Sensor Client",
}

rx = None
_buf = bytearray()


def on_notify(_, data: bytearray):
    global _buf
    sar, typ = (data[0] & 0xC0) >> 6, data[0] & 0x3F
    payload = bytes(data[1:])
    if sar == 0b00:
        rx.put_nowait((typ, payload))
    elif sar == 0b01:
        _buf = bytearray(payload)
    elif sar == 0b10:
        _buf += payload
    else:
        _buf += payload
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


def parse_composition(d):
    cid, pid, vid, crpl, feat = (int.from_bytes(d[i:i + 2], "little")
                                 for i in (0, 2, 4, 6, 8))
    print(f"  Company ID (CID) : 0x{cid:04x}")
    print(f"  Product ID (PID) : 0x{pid:04x}")
    print(f"  Version ID (VID) : 0x{vid:04x}")
    print(f"  RPL capacity     : {crpl}")
    on = [n for b, n in FEATURES.items() if feat & (1 << b)]
    print(f"  Features         : 0x{feat:04x}  {', '.join(on) or 'none'}")
    i, el = 10, 0
    while i + 4 <= len(d):
        loc = int.from_bytes(d[i:i + 2], "little")
        nums, numv = d[i + 2], d[i + 3]
        i += 4
        print(f"\n  Element {el} (location 0x{loc:04x}): "
              f"{nums} SIG model(s), {numv} vendor model(s)")
        for _ in range(nums):
            mid = int.from_bytes(d[i:i + 2], "little"); i += 2
            print(f"    SIG    0x{mid:04x}  {MODELS.get(mid, '(unknown SIG model)')}")
        for _ in range(numv):
            cvid = int.from_bytes(d[i:i + 2], "little")
            mid = int.from_bytes(d[i + 2:i + 4], "little"); i += 4
            print(f"    VENDOR company 0x{cvid:04x} model 0x{mid:04x}  <-- proprietary")
        el += 1


async def main():
    global rx
    rx = asyncio.Queue()
    net = mesh.load()
    if not net["nodes"]:
        print("no provisioned nodes in store; run provision.py first")
        return
    key = sys.argv[1] if len(sys.argv) > 1 else list(net["nodes"])[0]
    node = net["nodes"][key]
    dst = node["unicast"]
    devkey = bytes.fromhex(node["devkey"])
    netkey = bytes.fromhex(net["netkey"])
    src = net["provisioner_addr"]
    iv = net["iv_index"]
    our_netid = mesh.k3(netkey).hex()
    print(f"target {key} ({node['name']!r}) devkey {node['devkey'][:8]}...")
    print(f"our network id {our_netid}\n")

    print("finding the node as a mesh proxy...")
    dev = await BleakScanner.find_device_by_address(node["ble_address"], timeout=30.0)
    if not dev:
        dev = await BleakScanner.find_device_by_filter(
            lambda d, ad: PROXY_SVC in [u.lower() for u in (ad.service_uuids or [])]
            and d.address == node["ble_address"], timeout=30.0)
    if not dev:
        print("node not found as proxy")
        return

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        print(f"connected, MTU {mtu}")
        await cli.start_notify(PROXY_OUT, on_notify)

        # Proxy config: Set Filter Type = 0x01 (deny-list) so nothing is filtered out
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(netkey, iv, ctl=1, ttl=0, seq=seq, src=src,
                               dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                               nonce_type=0x03)
        await send(cli, PDU_PROXY_CFG, cfg, mtu)
        print("  -> proxy filter set to deny-list (accept everything)")
        await asyncio.sleep(0.5)

        # Config Composition Data Get, page 0, device-key encrypted
        seq = mesh.next_seq(net)
        access = bytes([0x80, 0x08, 0x00])
        upper = mesh.app_encrypt_devkey(devkey, iv, seq, src, dst, access)
        lower = bytes([0x00]) + upper          # unsegmented access, AKF=0 AID=0
        npdu = mesh.net_encrypt(netkey, iv, ctl=0, ttl=5, seq=seq, src=src,
                                dst=dst, transport_pdu=lower)
        await send(cli, PDU_NETWORK, npdu, mtu)
        print("  -> Config Composition Data Get (page 0)\n")

        segs, meta = {}, {}
        deadline = asyncio.get_event_loop().time() + 40
        while asyncio.get_event_loop().time() < deadline:
            try:
                typ, pdu = await asyncio.wait_for(rx.get(), timeout=5)
            except asyncio.TimeoutError:
                continue
            if typ != PDU_NETWORK:
                continue
            msg = mesh.net_decrypt(netkey, iv, pdu)
            if not msg or msg["src"] != dst:
                continue
            t = msg["transport"]

            if not (t[0] & 0x80):                      # unsegmented access
                try:
                    plain = mesh.app_decrypt_devkey(devkey, iv, msg["seq"],
                                                    msg["src"], src, t[1:])
                except Exception:
                    continue
                print(f"  unsegmented access: {plain.hex()}")
                continue

            # segmented access message
            hdr = int.from_bytes(t[1:4], "big")
            szmic = (hdr >> 23) & 1
            seqzero = (hdr >> 10) & 0x1FFF
            sego = (hdr >> 5) & 0x1F
            segn = hdr & 0x1F
            if sego not in segs:
                print(f"  <- segment {sego}/{segn}")
            segs[sego] = t[4:]
            meta.update(szmic=szmic, seqzero=seqzero, segn=segn,
                        seq=msg["seq"])

            if len(segs) == segn + 1:
                # acknowledge so the node stops retransmitting
                block = 0
                for i in segs:
                    block |= (1 << i)
                ack = bytes([0x00]) + ((seqzero << 2) & 0x7FFF).to_bytes(2, "big") \
                    + block.to_bytes(4, "big")
                aseq = mesh.next_seq(net)
                apdu = mesh.net_encrypt(netkey, iv, ctl=1, ttl=5, seq=aseq,
                                        src=src, dst=dst, transport_pdu=ack)
                await send(cli, PDU_NETWORK, apdu, mtu)
                print(f"  -> SegAck (block 0x{block:08x})")

                full = b"".join(segs[i] for i in sorted(segs))
                sa = mesh.seq_auth(meta["seq"], seqzero)
                try:
                    plain = mesh.app_decrypt_devkey(
                        devkey, iv, sa, dst, src, full,
                        tag=8 if szmic else 4)
                except Exception as e:
                    print(f"  !! upper transport decrypt failed: {e}")
                    segs.clear()
                    continue
                if plain[0] == 0x02:
                    print("\n=== Composition Data Page 0 ===")
                    parse_composition(plain[2:])
                    await cli.stop_notify(PROXY_OUT)
                    return
                print(f"  access message opcode 0x{plain[0]:02x}: {plain.hex()}")
                segs.clear()
        print("no Composition Data Status received")
        await cli.stop_notify(PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
