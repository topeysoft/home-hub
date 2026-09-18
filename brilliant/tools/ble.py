# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finding a node, and saying out loud how well we can hear it.

A mesh proxy link is a plain GATT connection, and GATT does not degrade
gracefully: somewhere below about -80 dBm it stops completing rather than
getting slow. What you see then is a bare `asyncio.TimeoutError` out of
CoreBluetooth, which looks like a broken tool and is actually a wall in the way.

So every tool that connects goes through here, and here always prints the
signal it got before it hands the device over.
"""
import asyncio

from bleak import BleakScanner

PROV_SVC = "00001827-0000-1000-8000-00805f9b34fb"   # unprovisioned
PROXY_SVC = "00001828-0000-1000-8000-00805f9b34fb"  # provisioned

GOOD, WEAK = -70, -80


def _verdict(rssi):
    # CoreBluetooth reports 127 when it has no RSSI for the advertisement.
    # Treating that as a very strong signal is worse than saying nothing.
    if rssi is None or rssi >= 20:
        return "signal unknown (CoreBluetooth reported no RSSI)"
    if rssi >= GOOD:
        return "strong -- GATT will be fine"
    if rssi >= WEAK:
        return "usable, but expect retries"
    return "TOO WEAK -- GATT will time out; carry the laptop to the switch"


async def find_node(address, timeout=20.0):
    """Find a provisioned node by address. Returns the device, or None."""
    print(f"  scanning {timeout:.0f}s for {address}...")
    seen = await BleakScanner.discover(timeout=timeout, return_adv=True)
    hit = seen.get(address)
    if not hit:
        print(f"  not seen. It may be out of range, or another process may hold"
              f"\n  its one proxy connection. {len(seen)} other device(s) were visible.")
        return None
    dev, adv = hit
    print(f"  found at {adv.rssi} dBm -- {_verdict(adv.rssi)}")
    return dev


async def find_unprovisioned(timeout=20.0, strongest=True):
    """Find a claimable node. Picks the nearest, not merely the first seen.

    Uses a detection callback rather than discover(): on macOS discover() keeps
    only each device's latest advertisement, which for a Brilliant switch is as
    often its 0xFEE4 DFU beacon as its unprovisioned 0x1827 beacon, so the node
    that census.py plainly sees can be invisible to a discover() filter.
    """
    print(f"  scanning {timeout:.0f}s for unprovisioned nodes...")
    hits = {}

    def cb(dev, adv):
        uuids = [u.lower() for u in (adv.service_uuids or [])]
        has_sd = any(str(u).lower().startswith("00001827") for u in (adv.service_data or {}))
        if PROV_SVC in uuids or has_sd:
            hits[dev.address] = (dev, adv)

    scanner = BleakScanner(detection_callback=cb)
    await scanner.start()
    await asyncio.sleep(timeout)
    await scanner.stop()
    cands = list(hits.values())
    if not cands:
        print("  none advertising 0x1827.")
        return None
    cands.sort(key=lambda x: -x[1].rssi)
    for d, a in cands:
        print(f"    {a.rssi:>4} dBm  {d.address}  {d.name or ''!r}")
    dev, adv = cands[0] if strongest else cands[-1]
    print(f"  -> taking the nearest, {dev.address} at {adv.rssi} dBm"
          f" -- {_verdict(adv.rssi)}")
    return dev
