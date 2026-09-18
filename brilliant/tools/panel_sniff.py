#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Listen to the live Brilliant panel mesh with the captured netkey.

We provisioned an ESP32 into the panel's network and it handed over the netkey
(see docs/brilliant.md). That key decrypts the *network layer* of the whole
panel mesh: every PDU's source, destination and sequence. It does NOT decrypt
the application payload -- the PIR/tap *values* are under the panel's AppKey,
which we don't have yet -- but it answers the question that started all of this:
**do the switches transmit anything when somebody touches them, and to whom?**

This connects to any switch on the panel network (found by its network id, not a
stored address), sets the proxy filter to forward everything, and logs every PDU
by its network header. Control messages (heartbeats, friendship) decode fully;
access messages show source/dest/seq and are marked as held under an AppKey we
don't have.

    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \\
        python3 tools/panel_sniff.py [seconds]

Defaults the store to panel-net.json if you don't set it.

Stand at a wall switch while it runs: wave, tap, double-tap. A burst of access
messages from a switch's address to the panel means the switches DO report, and
the recorder (grab the AppKey too) is worth building. Silence across real
interaction means they don't -- and that is finally a sound negative, because the
whole panel network is now visible, not just one address.
"""
import asyncio
import os
import sys
import time

# default the store to the panel key unless the caller points elsewhere
os.environ.setdefault(
    "BRILLIANT_MESH_STORE",
    os.path.expanduser("~/.config/brilliant-mesh/panel-net.json"))

from bleak import BleakClient, BleakScanner

import mesh
import onoff as O
import rawlog

PROXY_SVC = "00001828-0000-1000-8000-00805f9b34fb"
SECONDS = rawlog._arg_int(180) if hasattr(rawlog, "_arg_int") else (
    int(sys.argv[1]) if len(sys.argv) > 1 else 180)


async def find_panel_proxy(our_netid, timeout=20.0):
    """Strongest node advertising 0x1828 whose service-data netid is the panel's."""
    print(f"  scanning {timeout:.0f}s for a switch on netid {our_netid.hex()}...")
    seen = await BleakScanner.discover(timeout=timeout, return_adv=True)
    cands = []
    for dev, adv in seen.values():
        for uuid, sd in (adv.service_data or {}).items():
            if uuid.lower().startswith("00001828") and len(sd) >= 9 and sd[0] == 0x00:
                if sd[1:9] == our_netid:
                    cands.append((dev, adv))
    if not cands:
        print("  no panel-network proxy in range.")
        return None
    cands.sort(key=lambda x: -x[1].rssi)
    for d, a in cands:
        print(f"    {a.rssi:>4} dBm  {d.address}")
    dev, adv = cands[0]
    print(f"  -> connecting to {dev.address} at {adv.rssi} dBm "
          f"(it relays for the whole mesh)")
    return dev


async def main():
    net = mesh.load()
    netkey = bytes.fromhex(net["netkey"])
    iv = net["iv_index"]
    us = net.get("our_unicast", net.get("provisioner_addr", 1))
    our_netid = mesh.k3(netkey)
    appkey = bytes.fromhex(net["appkey"]) if net.get("appkey") else None
    our_aid = mesh.k4(appkey) if appkey else None
    print(f"panel netkey network-id {our_netid.hex()}   IV index {iv}   "
          f"our addr 0x{us:04x}")
    print("panel appkey: " + (f"AID 0x{our_aid:02x} (loaded -- will decode values)"
                              if appkey else "NOT loaded (network layer only)") + "\n")

    O.rx = asyncio.Queue()

    pin = os.environ.get("PANEL_NODE")   # pin a known-good BLE address if set

    print("=" * 64)
    print(f"  PANEL SNIFF, {SECONDS}s -- go stand at a wall switch and")
    print("  wave / tap / double-tap it. Any switch, it all relays here.")
    print("  (reconnects on its own if a node drops us)")
    print("=" * 64 + "\n")

    asm = rawlog.Reassembler()
    counts, sources = {}, {}
    t0 = time.time()
    budget_end = t0 + SECONDS

    async def open_filter(cli, mtu):
        # Reject-list (0x01), no entries = forward everything. A well-behaved
        # proxy answers with a Filter Status; some are lax and honor it silently.
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(netkey, iv, ctl=1, ttl=0, seq=seq, src=us,
                               dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                               nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu)

    while time.time() < budget_end:
        dev = None
        if pin:
            from bleak import BleakScanner as _BS
            dev = await _BS.find_device_by_address(pin, timeout=20.0)
            if dev:
                print(f"  pinned node {pin} found")
        if not dev:
            dev = await find_panel_proxy(our_netid)
        if not dev:
            await asyncio.sleep(2)
            continue
        try:
            cli = BleakClient(dev, timeout=30.0)
            await cli.connect()
        except Exception as e:
            print(f"  (connect failed: {e}; retrying)")
            continue
        mtu = getattr(cli, "mtu_size", 23) or 23
        try:
            await cli.start_notify(O.PROXY_OUT, O.on_notify)
        except Exception as e:
            print(f"  (subscribe failed: {e}; retrying)")
            try: await cli.disconnect()
            except Exception: pass
            continue
        await open_filter(cli, mtu)
        last_filter = time.time()
        print(f"  connected to {dev.address}; filter opened, listening\n")

        while time.time() < budget_end and cli.is_connected:
            # re-assert the filter periodically in case the proxy expired it
            if time.time() - last_filter > 20:
                try: await open_filter(cli, mtu)
                except Exception: pass
                last_filter = time.time()
            try:
                typ, pdu = await asyncio.wait_for(O.rx.get(), timeout=3)
            except asyncio.TimeoutError:
                continue
            ts = f"+{time.time() - t0:6.1f}s"
            if typ == 0x01:
                counts["secure network beacon"] = counts.get("secure network beacon", 0) + 1
                continue
            if typ == 0x03:
                # proxy configuration status (e.g. Filter Status)
                print(f"  {ts}  <- proxy config status: {pdu.hex()}")
                counts["filter status"] = counts.get("filter status", 0) + 1
                continue
            if typ != 0x00:
                continue
            m = mesh.net_decrypt(netkey, iv, pdu)
            if not m:
                nid = pdu[0] & 0x7F
                tag = f"other network (NID 0x{nid:02x})"
                counts[tag] = counts.get(tag, 0) + 1
                continue

            t = m["transport"]
            src, dst = m["src"], m["dst"]
            sources[src] = sources.get(src, 0) + 1
            head = (f"  {ts}  0x{src:04x} -> 0x{dst:04x} "
                    f"({rawlog.addr_kind(dst)}) seq {m['seq']}")

            if m["ctl"]:
                op = t[0] & 0x7F
                nm = rawlog.CTL_OPCODES.get(op, f"control 0x{op:02x}")
                print(f"{head}  CTL {nm}")
                counts[nm] = counts.get(nm, 0) + 1
                continue

            akf, aid = (t[0] >> 6) & 1, t[0] & 0x3F
            if t[0] & 0x80:
                body, (szmic, seqzero, sego, segn, done) = asm.feed(m, t)
                if not done:
                    continue
                await rawlog.send_segack(cli, mtu, net, netkey, iv, us,
                                         src, seqzero, segn)
                seq_use = mesh.seq_auth(m["seq"], seqzero)
                tag = 8 if szmic else 4
            else:
                body, seq_use, tag, szmic = t[1:], m["seq"], 4, 0

            # Decode with the captured panel AppKey.
            plain = None
            if akf and appkey is not None:
                nonce = bytes([0x01, 0x80 if szmic else 0x00]) \
                    + seq_use.to_bytes(3, "big") + src.to_bytes(2, "big") \
                    + dst.to_bytes(2, "big") + iv.to_bytes(4, "big")
                try:
                    plain = mesh.ccm_decrypt(appkey, nonce, body, tag=tag)
                except Exception:
                    plain = None
            if plain is not None:
                op, olen = rawlog.opcode_of(plain)
                nm = rawlog.name_opcode(op, olen)
                params = plain[olen:]
                print(f"{head}  {nm}: {params.hex()}")
                counts[nm] = counts.get(nm, 0) + 1
            else:
                why = "AID not ours" if (akf and aid != our_aid) else \
                      ("devkey msg" if not akf else "decrypt failed")
                print(f"{head}  access AKF{akf} AID0x{aid:02x} ({why}): {body.hex()}")
                counts["undecoded access"] = counts.get("undecoded access", 0) + 1

        try:
            await cli.stop_notify(O.PROXY_OUT)
        except Exception:
            pass
        try:
            await cli.disconnect()
        except Exception:
            pass
        if time.time() < budget_end:
            print("  (node dropped us; reconnecting)")

    print("\n" + "=" * 64 + "\n  SUMMARY")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"    {v:5d}  {k}")
    if sources:
        print("\n  addresses heard from:")
        for a, v in sorted(sources.items(), key=lambda x: -x[1]):
            print(f"    0x{a:04x}: {v}")
    got_mesh = any(k not in ("secure network beacon",) for k in counts)
    if not got_mesh:
        print("\n  Only beacons -- no mesh PDUs. The netkey is proven (the beacon")
        print("  authenticates under it), but the proxy forwarded no traffic:")
        print("  either the network was idle (nobody interacting) or the filter")
        print("  was not honored. Re-run WHILE working a switch by hand.")


if __name__ == "__main__":
    asyncio.run(main())
