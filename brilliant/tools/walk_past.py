#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Find out whether a Brilliant switch can see a person at all.

The inverse of `load_or_pir.py`. That one drove the lamp with nobody in the room and settled what
vendor field `0x13` reads: the load, not a body. This one leaves the lamp completely alone and moves
a *person* instead, on a schedule, so that anything which changes can only be the person.

Why it polls the list it polls. The dead Control panels poll their switches constantly, and the list
they ask for is `03 04 05 06 0c 1a 4b 51 55 56` -- it does not contain `0x13`. So whatever Brilliant's
own system reacts to when somebody walks up to a switch is in that list, or it arrives unsolicited, or
it is not on the switch at all and their motion lives in the panel. All three are answers, and this
tool separates them: `0x13` is polled too, as a control that should stay flat while the lamp is untouched.

Why the schedule is wall clock. Nobody can read a terminal while walking past a bedroom switch, so the
tool prints the whole plan in clock time before it starts and you follow it from a phone or a watch. The
windows are long and the cue is coarse on purpose -- a walk-past is seconds long and the windows are
tens of seconds, so being a little early or late costs nothing.

    python3 tools/walk_past.py 0007            # the switch to stand in front of

Three cycles of: stay away, then walk past repeatedly. Nothing is written to any switch and no lamp is
commanded at any point -- if the light changes while this runs, something else in the house did it and
the run is spoiled.

PANEL_NODE=<ble-addr> pins which node is used as the way in, as with the other tools.
"""
import asyncio
import os
import sys
import time
from collections import defaultdict

from bleak import BleakClient

import mesh
import onoff as O
from pairs import CID, Link
from vendor_store import find_proxy

# The panel's own poll list, plus 0x13 as a control. If a field here moves for a person and not for a
# lamp, that is the motion signal this house has been missing.
FIELDS = [0x03, 0x04, 0x05, 0x06, 0x0C, 0x1A, 0x4B, 0x51, 0x55, 0x56, 0x13]
CONTROL = 0x13

AWAY, WALK, CYCLES = 60, 30, 3
LEAD = 75          # long enough to read the plan and walk out of the room before it starts


def hhmm(t):
    return time.strftime("%H:%M:%S", time.localtime(t))


class Watch:
    """One proxy link. Records two streams that have to be kept apart: what arrived unsolicited, and
    what came back because we asked. Brilliant's panels never poll `0x13`, so the unsolicited stream is
    where their motion most likely lives, and conflating the two would hide exactly that."""

    def __init__(self, link, target):
        self.link, self.target = link, target
        self.samples = []       # (t, field, value_hex, asked) -- asked=False means it arrived on its own
        self.other = []         # (t, src, payload_hex) -- anything from another address, kept for context

    def note(self, t, payloads, asked_field=None):
        for src, p in payloads:
            if len(p) >= 5 and p[3] == 0x13:
                field, val = p[4], p[5:].hex()
                if src == self.target:
                    self.samples.append((t, field, val, asked_field == field))
                    continue
            if src != self.target:
                self.other.append((t, src, p.hex()))
            else:
                self.samples.append((t, None, p.hex(), False))

    async def listen(self, seconds):
        """Harvest in short chunks so arrivals carry a timestamp worth having."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            got = await self.link._harvest(0.5)
            if got:
                self.note(time.time(), got)

    async def sweep(self):
        """One pass over the poll list. A field that only answers a Get is invisible to the passive
        stream, which is why this runs at all -- but it is slow, so the passive listen carries the
        transients and this carries the slow state."""
        for f in FIELDS:
            access = bytes([0xC1]) + CID.to_bytes(2, "little") + bytes([0x11, f])
            await self.link._send_access(self.target, access)
            got = await self.link._harvest(0.6, want_src=self.target)
            self.note(time.time(), got, asked_field=f)


def values_in(samples, field, start, end):
    return [v for t, f, v, _ in samples if f == field and start <= t <= end]


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    target = int(sys.argv[1], 16)

    net = mesh.load()
    O.rx = asyncio.Queue()
    # Whether a proxy answers is luck on the margin: three scans from the same spot gave a node at
    # -68 dBm, a timeout, and nothing at all. A single miss is not "out of range", and aborting on one
    # would waste a walk the person has already made. Any node on the network will do -- the mesh
    # relays the last hop -- so this keeps asking.
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
        print("\nNo proxy answered in five scans. The Mac is too far from this network -- move it nearer\n"
              "any switch on it (the mesh relays the rest of the way) and run this again.")
        return 1

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        link = Link(cli, net, mtu)
        w = Watch(link, target)

        # The same secure-network beacon the other tools send, so the proxy starts relaying to us.
        seq = mesh.next_seq(net)
        await O.send(cli, 0x02, mesh.net_encrypt(link.netkey, link.iv, ctl=1, ttl=0, seq=seq,
                     src=link.us, dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                     nonce_type=0x03), mtu)
        await asyncio.sleep(0.4)

        print(f"\nswitch 0x{target:04x}. Nothing will be written and no lamp will be touched.\n")
        start = time.time() + LEAD
        plan = []
        t = start
        for c in range(CYCLES):
            plan.append(("away", t, t + AWAY)); t += AWAY
            plan.append(("walk", t, t + WALK)); t += WALK

        print("  The plan, by the clock. Follow it from your phone:\n")
        for label, a, b in plan:
            what = "STAY AWAY from the switch" if label == "away" else "WALK PAST IT, back and forth"
            print(f"    {hhmm(a)} - {hhmm(b)}   {what}")
        print(f"\n  Ends {hhmm(t)}. First window opens in {LEAD}s -- leave the room now.\n")

        while time.time() < start:
            await w.listen(1.0)

        windows = []
        for label, a, b in plan:
            print(f"  {hhmm(time.time())}  {label.upper():5}", end="", flush=True)
            while time.time() < b:
                await w.sweep()
                left = b - time.time()
                if left > 0:
                    await w.listen(min(2.0, left))
            windows.append((label, a, b))
            print("  done")

        print("\n---- what moved, and when ----\n")
        moved, control_moved = [], []
        for f in FIELDS:
            away_v, walk_v = set(), set()
            for label, a, b in windows:
                (walk_v if label == "walk" else away_v).update(values_in(w.samples, f, a, b))
            if not away_v and not walk_v:
                print(f"  0x{f:02x}  no answer at all")
                continue
            only_walk = walk_v - away_v
            tag = ""
            if only_walk:
                if f == CONTROL:
                    tag = "   <-- CONTROL MOVED: the lamp did not stay still"
                    control_moved.append(sorted(only_walk))
                else:
                    tag = "   <-- MOVED FOR A PERSON"
                    moved.append((f, sorted(only_walk)))
            print(f"  0x{f:02x}  away={sorted(away_v)}  walk={sorted(walk_v)}{tag}")

        # Everything the switch sent on its own, INCLUDING payloads that are not vendor-field
        # statuses. An earlier version of this tool reported only `13 <field> <value>` replies and
        # silently dropped the rest, which would have thrown away a PIR that reports over a SIG
        # sensor model or any other opcode -- the exact thing this run exists to find.
        unsolicited = [(t, f, v) for t, f, v, asked in w.samples if not asked]
        byfield = defaultdict(lambda: defaultdict(int))
        for t, f, v in unsolicited:
            when = next((lab for lab, a, b in windows if a <= t <= b), "between")
            byfield[f][when] += 1
        print(f"\n  unsolicited from 0x{target:04x}: {len(unsolicited)}, by what it was and when")
        for f in sorted(byfield, key=lambda x: (x is None, x)):
            name = "NOT a vendor status -- raw payload" if f is None else f"field 0x{f:02x}"
            counts = "  ".join(f"{k}={v}" for k, v in sorted(byfield[f].items()))
            print(f"    {name:38} {counts}")
        odd = [(t, v) for t, f, v in unsolicited if f is None]
        if odd:
            print(f"\n  the {len(odd)} non-vendor-status payloads, which is where a real sensor may hide:")
            for t, v in odd[:25]:
                when = next((lab for lab, a, b in windows if a <= t <= b), "between")
                print(f"    {hhmm(t)}  {v}   during {when}")

        dump = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"walk-{target:04x}-{int(time.time())}.csv")
        with open(dump, "w") as fh:
            fh.write("time,window,field,value,asked\n")
            for t, f, v, asked in w.samples:
                when = next((lab for lab, a, b in windows if a <= t <= b), "between")
                fh.write(f"{t:.3f},{when},{'' if f is None else f'0x{f:02x}'},{v},{int(asked)}\n")
        print(f"\n  raw samples written to {os.path.basename(dump)} -- a walk is expensive, so no run\n"
              f"  should ever have to be repeated just to ask the data a different question.")

        print("\n---- verdict ----\n")
        if moved:
            for f, vals in moved:
                print(f"  FIELD 0x{f:02x} TRACKS A PERSON. It took {vals} while somebody walked past and never")
                print(f"  while the room was empty, with the lamp untouched throughout. That is the motion")
                print(f"  signal -- build the bridge's binary_sensor on this, not on 0x13.\n")
        else:
            print("  NOTHING ON THIS SWITCH SAW YOU. No polled field and nothing unsolicited distinguished")
            print("  three walk-pasts from three empty windows. Either these switches have no PIR and")
            print("  Brilliant's motion lives in the Control panel, or it is behind a field the panel's")
            print("  poll list does not name. Check the faceplate for a sensor lens before spending")
            print("  another session on vendor fields.\n")
        if control_moved:
            print("  NOTE: the control field 0x13 moved too, which means the lamp was not actually left")
            print("  alone. Something else in the house drove it -- a rule, the app, or somebody at a")
            print("  switch. Anything above is suspect. Do it again.\n")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
