#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Measure how a Brilliant switch reports a person: how fast it notices, and how long it holds.

`walk_past.py` asked the wrong question of vendor field `0x0c` and got a null answer. It compared
thirty-second walks against sixty-second gaps, and `0x0c` never fell in sixty seconds, so every window
looked the same. Watched over a longer afternoon the field is plainly not static: `00` with the room
empty, `01` within a minute of somebody going in, `01` for a solid six minutes of somebody moving about,
and `00` again once they had been gone a while -- with the lamp never commanded once. That is occupancy
with a slow release, not a PIR trip, and the number that decides what can be built on it is the release
hold.

So this does not try to catch a transition by luck. It gives the field a long, genuinely empty stretch to
settle, one short visit, and then a long stretch to fall again, and it times both edges.

    python3 tools/presence_hold.py 0007

`0x13` is polled alongside as a control. It is the lamp, so it must stay flat -- if it moves, somebody
drove that light and the timings are not trustworthy. Nothing is written and no lamp is commanded.
"""
import asyncio
import os
import sys
import time

from bleak import BleakClient

import mesh
import onoff as O
from pairs import CID, Link
from vendor_store import find_proxy

PRESENCE = 0x0C
CONTROL = 0x13

EMPTY, PRESENT, RELEASE = 300, 30, 360
LEAD = 75
EVERY = 3.0          # seconds between presence reads: fine enough to time an edge, slow enough to be kind


def hhmm(t):
    return time.strftime("%H:%M:%S", time.localtime(t))


def mmss(s):
    return f"{int(s) // 60}m {int(s) % 60:02d}s"


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    target = int(sys.argv[1], 16)

    net = mesh.load()
    O.rx = asyncio.Queue()
    dev = None
    for attempt in range(1, 6):
        print(f"looking for a way into the mesh (try {attempt}) … ", end="", flush=True)
        try:
            dev = await find_proxy(bytes.fromhex(net["netkey"]))
        except Exception as e:
            print(f"scan failed ({e.__class__.__name__})")
            continue
        if dev:
            print("in.")
            break
        print("nothing answered.")
    if not dev:
        print("\nNo proxy answered in five scans. Move the Mac nearer any switch on this network.")
        return 1

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        link = Link(cli, net, mtu)
        seq = mesh.next_seq(net)
        await O.send(cli, 0x02, mesh.net_encrypt(link.netkey, link.iv, ctl=1, ttl=0, seq=seq,
                     src=link.us, dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                     nonce_type=0x03), mtu)
        await asyncio.sleep(0.4)

        t0 = time.time() + LEAD
        plan = [("empty", t0, t0 + EMPTY),
                ("present", t0 + EMPTY, t0 + EMPTY + PRESENT),
                ("release", t0 + EMPTY + PRESENT, t0 + EMPTY + PRESENT + RELEASE)]
        says = {"empty": "STAY OUT of the room entirely",
                "present": "GO IN and move about",
                "release": "LEAVE, and stay out"}

        print(f"\nswitch 0x{target:04x}, field 0x{PRESENCE:02x}. Nothing written, no lamp touched.\n")
        print("  The plan, by the clock:\n")
        for label, a, b in plan:
            print(f"    {hhmm(a)} - {hhmm(b)}   {says[label]}")
        print(f"\n  Ends {hhmm(plan[-1][2])}. Starts in {LEAD}s -- get out of the room now.\n")

        samples, control, misses = [], [], 0
        while time.time() < plan[-1][2]:
            now = time.time()
            if now < t0:
                await asyncio.sleep(1.0)
                continue
            try:
                v = await link.field(target, PRESENCE)
            except Exception:
                v = None
            if v is None:
                misses += 1
            else:
                samples.append((time.time(), v[:2]))
            if len(samples) % 10 == 0:
                try:
                    c = await link.field(target, CONTROL)
                    if c:
                        control.append((time.time(), c))
                except Exception:
                    pass
            label = next((l for l, a, b in plan if a <= time.time() <= b), "…")
            last = samples[-1][1] if samples else "--"
            print(f"\r  {hhmm(time.time())}  {label:8} 0x0c={last}  reads={len(samples)} missed={misses}   ",
                  end="", flush=True)
            await asyncio.sleep(EVERY)
        print("\n")

        dump = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"presence-{target:04x}-{int(time.time())}.csv")
        with open(dump, "w") as fh:
            fh.write("time,window,field,value\n")
            for t, v in samples:
                w = next((l for l, a, b in plan if a <= t <= b), "between")
                fh.write(f"{t:.3f},{w},0x0c,{v}\n")
            for t, v in control:
                w = next((l for l, a, b in plan if a <= t <= b), "between")
                fh.write(f"{t:.3f},{w},0x13,{v}\n")

        print("---- the timeline ----\n")
        prev = None
        for t, v in samples:
            if v != prev:
                w = next((l for l, a, b in plan if a <= t <= b), "between")
                print(f"  {hhmm(t)}  0x0c -> {v}     (during {w})")
                prev = v

        per = {}
        for label, a, b in plan:
            vals = [v for t, v in samples if a <= t <= b]
            per[label] = vals
            seen = sorted(set(vals)) or ["(no reads)"]
            print(f"\n  {label:8} {len(vals):3d} reads, values {seen}")

        _, pa, pb = plan[1]
        trip = next((t for t, v in samples if pa <= t and v == "01"), None)
        rel = None
        after = [(t, v) for t, v in samples if t > pb]
        for i, (t, v) in enumerate(after):
            if v == "00" and all(vv == "00" for _, vv in after[i:]):
                rel = t
                break

        print("\n---- verdict ----\n")
        # The control asks one question: did the LAMP come on? 0x13 is the load and it always wanders --
        # it ranged 5-9 across a run where nothing touched the light. An earlier version flagged "more
        # than one distinct value" and cried wolf on exactly that noise. A lit lamp is not a wobble of a
        # few counts, it is roughly +60, so that is what this looks for.
        cvals = [int(v[:2], 16) for _, v in control if v]
        cmoved = bool(cvals) and (max(cvals) - min(cvals)) > 20
        if not samples:
            print("  No reads got through at all. That is a link problem, not a result.\n")
        elif len(set(per["empty"] or ["?"])) == 1 and (per["empty"] or [""])[0] == "00" and trip:
            before = max([t for t, v in samples if t < trip and v == "00"], default=pa)
            print(f"  IT IS AN OCCUPANCY SIGNAL. 0x0c sat at 00 for {mmss(EMPTY)} of empty room, then went")
            print(f"  01 between {hhmm(before)} and {hhmm(trip)} -- so {mmss(before - pa)} to {mmss(trip - pa)}")
            print(f"  after you went in. The bracket is the honest number: reads drop on this link, and an")
            print(f"  edge is only ever known to lie between the read that missed it and the one that caught it.")
            if rel:
                print(f"  It fell back to 00 at {hhmm(rel)}, holding for {mmss(rel - pb)} after you left.")
                print(f"\n  So: build the bridge's sensor on 0x0c, publish it as OCCUPANCY rather than motion,")
                print(f"  and expect a ~{mmss(rel - pb)} tail. An `idle` rule needs a threshold well above that.")
            else:
                print(f"  It had NOT fallen back by the end of {mmss(RELEASE)}. The hold is longer than this")
                print(f"  run -- worth repeating with a longer release leg before anything depends on it.")
        elif trip is None:
            print("  It never went 01 while you were in the room. Either the visit missed the sensor's")
            print("  view, or 0x0c is not what the afternoon suggested. Worth one repeat before dropping it.\n")
        else:
            print(f"  MUDDLED. The empty leg was not clean: values {sorted(set(per['empty']))}. Either the")
            print("  room was not empty or the field was still falling from earlier. Repeat with a longer")
            print("  first leg.\n")
        if cmoved:
            print(f"\n  NOTE: the control 0x13 swung {min(cvals)}-{max(cvals)}, which is a lamp coming on, not")
            print("  its noise floor. Something drove that light during the run; treat the edges as suspect.")
        elif cvals:
            print(f"\n  Control clean: 0x13 stayed in {min(cvals)}-{max(cvals)}, its dark noise band. The lamp")
            print("  was never lit, so nothing above is an artifact of the light.")
        if misses:
            print(f"\n  {misses} reads went unanswered. Dropped reads are normal on this link; they only")
            print("  blur an edge by a few seconds, they do not invent one.")
        print(f"\n  raw samples in {os.path.basename(dump)}")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
