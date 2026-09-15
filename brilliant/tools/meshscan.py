#!/usr/bin/env python3
"""Classify nearby BLE devices as SIG Bluetooth Mesh or proprietary.

Decisive test for the Brilliant BHS120US dimmers (Nordic nRF52832):
  0x1827 Mesh Provisioning  -> unprovisioned SIG mesh node, ANY provisioner can claim it
  0x1828 Mesh Proxy         -> provisioned SIG mesh node, standard stack
  neither, vendor UUID only -> proprietary mesh
"""
import asyncio
import sys
from collections import defaultdict

from bleak import BleakScanner

MESH_PROV = "00001827"
MESH_PROXY = "00001828"
SECONDS = int(sys.argv[1]) if len(sys.argv) > 1 else 20

seen = {}


def note(dev, ad):
    uuids = [u.lower() for u in (ad.service_uuids or [])]
    kind = "-"
    if any(u.startswith(MESH_PROV) for u in uuids):
        kind = "SIG MESH: UNPROVISIONED (provisionable!)"
    elif any(u.startswith(MESH_PROXY) for u in uuids):
        kind = "SIG MESH: provisioned node (GATT proxy)"
    elif uuids:
        kind = "other/vendor GATT"
    prev = seen.get(dev.address)
    if prev is None or (kind != "-" and prev["kind"] == "-"):
        seen[dev.address] = {
            "name": ad.local_name or dev.name or "",
            "rssi": ad.rssi,
            "uuids": uuids,
            "mfr": dict(ad.manufacturer_data or {}),
            "kind": kind,
        }


async def main():
    print(f"scanning {SECONDS}s for BLE mesh beacons...\n")
    scanner = BleakScanner(detection_callback=note)
    await scanner.start()
    await asyncio.sleep(SECONDS)
    await scanner.stop()

    if not seen:
        print("nothing seen. On macOS grant Bluetooth permission to your terminal:")
        print("  System Settings > Privacy & Security > Bluetooth")
        return

    buckets = defaultdict(list)
    for addr, d in seen.items():
        buckets[d["kind"]].append((addr, d))

    for kind in sorted(buckets, key=lambda k: (k == "-", k)):
        print(f"=== {kind} ===")
        for addr, d in sorted(buckets[kind], key=lambda x: -x[1]["rssi"]):
            print(f"  {addr}  {d['rssi']:>4} dBm  {d['name']!r}")
            if d["uuids"]:
                print(f"      uuids: {', '.join(d['uuids'])}")
            for cid, data in d["mfr"].items():
                print(f"      mfr 0x{cid:04x}: {data.hex()}")
        print()

    hits = [k for k in buckets if k.startswith("SIG MESH")]
    print("VERDICT:", "; ".join(hits) if hits else
          "no SIG mesh beacons -> proprietary mesh, or nodes not beaconing")


asyncio.run(main())
