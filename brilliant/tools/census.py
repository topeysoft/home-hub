#!/usr/bin/env python3
"""Census of Brilliant switches, sorted by signal and grouped by network.

Tells you at a glance which switches are still captive to the dead Brilliant
panels (and so need a factory reset before they can be claimed), which are
already ours, and which are sitting unprovisioned waiting to be provisioned.

usage: census.py [seconds]
"""
import asyncio
import sys

from bleak import BleakScanner

import mesh

# The network the dead Brilliant Control panels provisioned. Anything still
# advertising this needs a factory reset before it can be claimed.
OLD_BRILLIANT_NET = bytes.fromhex("3deef9825e444955")

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 30
found = {}


def main():
    net = mesh.load()
    ours = mesh.k3(bytes.fromhex(net["netkey"]))

    def cb(dev, ad):
        for uuid, sd in (ad.service_data or {}).items():
            u = uuid.lower()
            if u.startswith("00001827"):
                found[dev.address] = ("UNPROVISIONED - claim it", ad.rssi, "-")
            elif u.startswith("00001828") and len(sd) >= 9 and sd[0] == 0x00:
                nid = sd[1:9]
                if nid == ours:
                    label = "ours"
                elif nid == OLD_BRILLIANT_NET:
                    label = "old Brilliant net - reset it"
                else:
                    label = "unknown network"
                found[dev.address] = (label, ad.rssi, nid.hex())

    async def run():
        s = BleakScanner(detection_callback=cb)
        await s.start()
        await asyncio.sleep(SECS)
        await s.stop()

    asyncio.run(run())

    print(f"our network id: {ours.hex()}   ({SECS}s scan)\n")
    if not found:
        print("  no mesh nodes seen")
        return
    for addr, (label, rssi, nid) in sorted(found.items(), key=lambda x: -x[1][1]):
        print(f"  {rssi:>4} dBm  {label:28s} netid={nid}  {addr}")
    mine = sum(1 for v in found.values() if v[0] == "ours")
    print(f"\n  {mine} ours, {len(found) - mine} still to claim")


if __name__ == "__main__":
    main()
