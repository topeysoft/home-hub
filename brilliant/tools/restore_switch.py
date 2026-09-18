#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Move a Brilliant switch off the console onto our own network, dimming intact.

Tonight's recipe, made repeatable. A factory reset strips the dimmer/motion
setup the Control panel wrote, and that setup is NOT restored by provisioning
alone: it lives in the vendor store, and the firmware reads the load type only
at boot. So the order is capture, reset, adopt, power-cycle.

    # 1. while the switch is still on the console's network
    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \\
        python3 tools/vendor_store.py 000a ~/.config/brilliant-mesh/store-000a.json

    # 2. factory reset it by hand: pull the Safety Disconnect, push it back,
    #    hold the touch plate ~10s until the LED blinks

    # 3. claim it onto our network and write its own config back
    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/mesh-net.json \\
        python3 tools/restore_switch.py adopt ~/.config/brilliant-mesh/store-000a.json

    # 4. power-cycle the switch again (the load type is read at boot)

    # 5. prove it dims
    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/mesh-net.json \\
        python3 tools/restore_switch.py verify 0005

Two things in step 3 are easy to miss and both produce a switch that looks
broken in a way that is nothing to do with the load:

  - without binding the VENDOR model 0x0820/0x0001 to our AppKey, every config
    write is silently dropped and the switch looks like it refuses configuring;
  - without Config Model Publication Set, the switch announces NOTHING -- no
    tap, no state change, no motion -- while still answering Gets and obeying
    Sets. `ensure_bound` now does both; `publication.py` shows and repairs it.
"""
import asyncio
import json
import sys

from bleak import BleakClient, BleakScanner

import ble
import mesh
import onoff as O
import rawlog
from onoff import Node, ensure_bound
from snapshot import read_field
from writable import write_field

# The load-type / reporting configuration, in the order the console writes it.
# Identity (0x0e UUID, 0x47 device id), counters (0x0b, 0x1d) and live readings
# (0x13 motion, 0x0c on/off notice) are deliberately not replayed.
CONFIG_FIELDS = ["1a", "1b", "48", "4f", "56", "03", "07", "4c", "4d", "52"]


def wanted(store):
    """Config field -> value bytes, from a vendor_store.py capture."""
    fields = store["fields"]
    out = []
    for f in CONFIG_FIELDS:
        v = fields.get(f)
        if not v:
            continue
        # captures carry the natural width plus the reply's trailing 00; the
        # write appends its own trailing 00, so strip one here.
        v = v[:-2] if len(v) > 2 and v.endswith("00") else v
        out.append((f, v))
    return out


async def open_proxy(cli, net, mtu):
    seq = mesh.next_seq(net)
    cfg = mesh.net_encrypt(bytes.fromhex(net["netkey"]), net["iv_index"], ctl=1, ttl=0,
                           seq=seq, src=net["provisioner_addr"], dst=0,
                           transport_pdu=b"\x00\x01", nonce_type=0x03)
    await O.send(cli, 0x02, cfg, mtu)
    await asyncio.sleep(0.4)


async def adopt(store_path):
    store = json.load(open(store_path))
    cfg = wanted(store)
    print(f"config captured from 0x{store['target']} on network {store['network'][:8]}...")
    print(f"  {len(cfg)} field(s) to replay: {', '.join('0x' + f for f, _ in cfg)}\n")

    net = mesh.load()
    print(f"our network {mesh.k3(bytes.fromhex(net['netkey'])).hex()}")
    dev = await ble.find_unprovisioned()
    if not dev:
        print("\nNo unprovisioned switch in range. Factory reset it first:")
        print("  pull the Safety Disconnect, push it back, hold the touch plate")
        print("  ~10s until the LED goes out and blinks.")
        return

    # provision.py owns the provisioning handshake; run it rather than fork it.
    import provision
    await provision.main()

    net = mesh.load()
    addr = max(net["nodes"], key=lambda k: net["nodes"][k]["unicast"])
    node = net["nodes"][addr]
    print(f"\nconfiguring {addr}")
    node["bound"] = False          # bind again: the vendor model is new in ensure_bound
    mesh.save(net)

    O.rx = asyncio.Queue()
    dev = await BleakScanner.find_device_by_address(node["ble_address"], timeout=30.0)
    if not dev:
        print("  provisioned, but the node is not answering GATT -- rerun `adopt` to configure")
        return
    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        await open_proxy(cli, net, mtu)
        n = Node(cli, mtu, net, node)
        await ensure_bound(n, net, node)

        asm = rawlog.Reassembler()
        bad = 0
        for field, val in cfg:
            await write_field(n, val, int(field, 16))
            back = await read_field(n, cli, mtu, net, asm, int(field, 16))
            ok = back is not None and back.startswith(val)
            bad += 0 if ok else 1
            print(f"  0x{field} = {val:<8} read back {back}  {'ok' if ok else 'NOT SET'}")
        try:
            await cli.stop_notify(O.PROXY_OUT)
        except Exception:
            pass

    if bad:
        print(f"\n{bad} field(s) did not stick. If they all failed, the vendor model")
        print("0x0820/0x0001 is not bound to our AppKey -- rerun and watch the bind lines.")
        return
    print(f"\n{addr} adopted and configured.")
    print("NOW POWER-CYCLE THE SWITCH (the load type is only read at boot),")
    print(f"then: restore_switch.py verify {addr.replace('0x', '')}")


async def verify(addr_hex):
    net = mesh.load()
    addr = f"0x{int(addr_hex, 16):04x}"
    node = net["nodes"][addr]
    O.rx = asyncio.Queue()
    dev = await BleakScanner.find_device_by_address(node["ble_address"], timeout=30.0)
    if not dev:
        print("node not answering GATT")
        return
    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        await open_proxy(cli, net, mtu)
        n = Node(cli, mtu, net, node)
        await n.onoff(True)
        await asyncio.sleep(1.5)
        print("WATCH THE LAMP:")
        ramped = 0
        for i, pct in enumerate((30, 100, 10, 100), start=1):
            lvl = pct * 10
            await n._tx(bytes([0x82, 0x06]) + lvl.to_bytes(2, "little")
                        + bytes([i, 0x05, 0x00]), use_appkey=True)
            got = await status_level(n, 2.0)
            print(f"  {pct:>3}% -> {got}")
            if got and "present=" in got:
                ramped += 1
            await asyncio.sleep(3.0)
        try:
            await cli.stop_notify(O.PROXY_OUT)
        except Exception:
            pass
    print(f"\n{ramped}/4 acknowledged with a Level Status.")
    print("Dimming works if the lamp visibly followed. If the level is echoed but the")
    print("lamp never changes, the switch is still in on/off mode: power-cycle it.")


async def status_level(n, secs):
    end = asyncio.get_event_loop().time() + secs
    while asyncio.get_event_loop().time() < end:
        try:
            typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=0.3)
        except asyncio.TimeoutError:
            continue
        if typ != 0:
            continue
        m = mesh.net_decrypt(n.netkey, n.iv, pdu)
        if not m or m["ctl"] or m["src"] != n.dst:
            continue
        t = m["transport"]
        if t[0] & 0x80 or not ((t[0] >> 6) & 1):
            continue
        nonce = bytes([1, 0]) + m["seq"].to_bytes(3, "big") + m["src"].to_bytes(2, "big") \
            + m["dst"].to_bytes(2, "big") + n.iv.to_bytes(4, "big")
        try:
            p = mesh.ccm_decrypt(n.appkey, nonce, t[1:], tag=4)
        except Exception:
            continue
        if int.from_bytes(p[:2], "big") == 0x8208:
            return f"Level Status present={int.from_bytes(p[2:4], 'little')}"
    return "(no reply)"


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "adopt":
        asyncio.run(adopt(sys.argv[2]))
    elif cmd == "verify":
        asyncio.run(verify(sys.argv[2]))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
