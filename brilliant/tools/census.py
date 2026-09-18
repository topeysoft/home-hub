#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
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

# The Brilliant-provisioned network. This was labeled "the dead panels' network"
# until we found that one panel is alive -- dead screen, working radio -- and the
# mobile app still drives the switches on it. So these are very likely LIVE nodes
# in a mesh somebody still uses, and they are also the nodes whose PIR and tap
# traffic we want to decrypt. Resetting one evicts it from that mesh and breaks
# the working setup, so this is no longer a "reset it" recommendation.
BRILLIANT_NET = bytes.fromhex("3deef9825e444955")

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
                elif nid == BRILLIANT_NET:
                    label = "Brilliant net - LIVE, do not reset"
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
    free = sum(1 for v in found.values() if v[0].startswith("UNPROVISIONED"))
    live = sum(1 for v in found.values() if v[0].startswith("Brilliant net"))
    print(f"\n  {mine} ours, {free} unprovisioned and claimable, "
          f"{live} on the Brilliant network")
    if live:
        print("\n  The Brilliant-network nodes are reachable by the surviving panel"
              "\n  and the mobile app. Do not factory-reset one to claim it unless"
              "\n  you mean to take it off that mesh for good.")


if __name__ == "__main__":
    main()
