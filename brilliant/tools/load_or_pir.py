#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settle what vendor field 0x13 is actually reading: the lamp, or you.

The measurement this repo quotes -- dark 1-3, lit 92-97 on `0x0005` -- was taken with a person at the
switch, flipping it by hand. That is a confound and it deserves to be named: somebody standing close
enough to press a wall switch has a finger in front of the PIR, so a rise at the moment the light comes
on could be the body rather than the load. Everything else on file argues for the load (the reading
collapses two seconds after switch-off, while the hand is still there; resting values scale with the
size of the load on switches nobody is near). But argument is not measurement.

So: drive the lamp over the mesh, from another room, and watch 0x13 through the bridge. Nobody is in
front of the sensor at any point, which is the whole design. Then the reading is unambiguous.

    python3 tools/load_or_pir.py <addr-hex> [broker-host]     e.g. load_or_pir.py 0005

Four windows, about seven minutes: dark baseline, lit, dark again, and a dim leg. The dim leg is not
decoration -- the bridge re-learns its motion floor on a Generic OnOff Status (main.cpp, the 0x8204
branch) but NOT on a Level Status, so if the baseline tracks brightness then dimming moves it with no
re-learn and motion latches on. That is a bridge bug this run either demonstrates or rules out.

Nothing here writes a vendor field or touches a switch's configuration. It turns one light on and off.

Before running: get out of the room, and take the pets. A rule that lights the same room will fight
this -- check the routines page, or run it on a switch no rule names.
"""
import os
import statistics
import sys
import time

import paho.mqtt.client as mqtt

ADDR = (sys.argv[1] if len(sys.argv) > 1 else "0005").lower().removeprefix("0x").zfill(4)
HOST = sys.argv[2] if len(sys.argv) > 2 else "192.168.86.42"
BASE = os.environ.get("MQTT_BASE", "mesh")
HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, "..", "..", "driver-layer", ".env")

SETTLE = 15         # seconds to let the level settle after a command before a window starts
DARK, LIT, DIM = 60, 180, 60
MOVED = 4           # counts: the bridge's own MOTION_ON_ABOVE, so the verdict speaks its language


def creds():
    u, p = os.environ.get("MQTT_USER"), os.environ.get("MQTT_PASSWORD")
    if u and p:
        return u, p
    if os.path.exists(ENV):
        kv = dict(l.rstrip("\n").split("=", 1) for l in open(ENV) if "=" in l and not l.startswith("#"))
        return kv.get("MQTT_USER", "hub"), kv.get("MQTT_PASSWORD", "")
    return "hub", ""


class Run:
    """One connection, one switch. Samples are (monotonic, value); `motion` is what the BRIDGE decided,
    which is a separate question from what the field did and is reported separately."""

    def __init__(self):
        self.net = None                 # learned from a retained topic: never hardcode this house's netid
        self.levels, self.motion, self.windows = [], [], []
        self.c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"load-or-pir-{os.getpid()}")
        u, p = creds()
        self.c.username_pw_set(u, p)
        self.c.on_message = self.on_msg
        self.c.on_connect = lambda cl, *_: cl.subscribe(f"{BASE}/#")
        try:
            self.c.connect(HOST, 1883, 30)
            # A background network thread, not loop() in the callers' waits. paho's loop() reads ONE
            # packet per call, and this mesh publishes motion_level for every switch it can hear every
            # 250 ms -- so a 0.5 s loop() drains two messages a second out of a stream of dozens. The
            # retained backlog never finished arriving (the netid was never learned, on a house where
            # the topic is plainly there), and a run that got past that would have sampled further and
            # further behind the lamp it was driving. The windows must be wall-clock honest or the
            # verdict is meaningless.
            self.c.loop_start()
        except OSError as e:
            sys.exit(f"cannot reach the broker at {HOST}:1883 ({e}). Pass the host as the second "
                     f"argument, and check MQTT_USER / MQTT_PASSWORD or driver-layer/.env.")

    def on_msg(self, _c, _u, m):
        parts = m.topic.split("/")
        if len(parts) < 4 or parts[0] != BASE or parts[1] == "bridge" or parts[2] != ADDR:
            return
        self.net = parts[1]
        val = m.payload.decode("utf-8", "replace")
        leaf = "/".join(parts[3:])
        if leaf == "motion_level" and val.lstrip("-").isdigit():
            self.levels.append((time.monotonic(), int(val)))
        elif leaf == "motion":
            self.motion.append((time.monotonic(), val))

    def send(self, payload):
        self.c.publish(f"{BASE}/{self.net}/{ADDR}/set", payload)

    def wait(self, secs, label):
        end = time.monotonic() + secs
        while time.monotonic() < end:
            time.sleep(0.5)
            left = int(end - time.monotonic())
            print(f"\r  {label}: {left:3d}s   level {self.levels[-1][1] if self.levels else '?':>5}"
                  f"   motion {self.motion[-1][1] if self.motion else '?':<4}", end="", flush=True)
        print()

    def window(self, secs, label):
        """Record a window. Returns (label, start, end, [(t, value)]) -- timestamped, because attributing a
        false motion report to the leg that caused it is half of what this run is for. Starts now, so
        callers settle first."""
        start = time.monotonic()
        self.wait(secs, label)
        end = time.monotonic()
        w = (label, start, end, [(t, v) for t, v in self.levels if start <= t <= end])
        self.windows.append(w)
        return w


def vals(w, first=None, last=None):
    """The values in a window, optionally only its first or last `n` seconds."""
    _, start, end, xs = w
    if first is not None:
        xs = [(t, v) for t, v in xs if t - start <= first]
    if last is not None:
        xs = [(t, v) for t, v in xs if end - t <= last]
    return [v for _, v in xs]


def med(xs, default=None):
    return statistics.median(xs) if xs else default


def main():
    r = Run()
    print(f"connecting to {HOST} … ", end="", flush=True)
    for _ in range(20):                      # retained topics arrive at once; we only need the netid
        time.sleep(0.5)
        if r.net:
            break
    if not r.net:
        sys.exit(f"\nnothing retained for switch {ADDR} under {BASE}/+/{ADDR}/. "
                 f"Is the bridge up, and is that the right address? `bridge_watch.py {HOST}` will say.")
    print(f"net {r.net[:4]}…, switch {ADDR}")

    print("\nLeave the room now. Nothing should walk past this switch until the run ends (~7 min).")
    for n in range(20, 0, -1):
        time.sleep(0.5)
        print(f"\r  starting in {n:2d}s …", end="", flush=True)
    print("\n")

    quiet_from = time.monotonic()        # the room is empty from here on: any motion report after it is false

    r.send("off")
    r.wait(SETTLE, "settling dark")
    w_dark0 = r.window(DARK, "dark baseline")

    r.send("on")
    r.wait(SETTLE, "settling lit")
    w_lit = r.window(LIT, "lit, empty room")

    r.send("off")
    r.wait(SETTLE, "settling dark")
    w_dark1 = r.window(DARK, "dark again")

    r.send("on")
    r.wait(5, "lamp on for the dim leg")   # two commands back to back race on one proxy link
    r.send("dim:20")
    r.wait(SETTLE, "settling at 20%")
    w_lo = r.window(DIM, "dim 20%")
    r.send("dim:100")
    r.wait(SETTLE, "settling at 100%")
    w_hi = r.window(DIM, "dim 100%")
    r.send("off")

    print("\n---- what the field did, with nobody in the room ----")
    for label, _, _, xs in r.windows:
        v = [x for _, x in xs]
        if v:
            print(f"  {label:18} n={len(v):3d}   {min(v):5d} - {max(v):<5d}  median {med(v):6.1f}")
        else:
            print(f"  {label:18} no samples   (0x13 never changed in that window)")

    d0 = med(vals(w_dark0))
    if d0 is None or not vals(w_lit):
        sys.exit("\nNot enough samples to say anything. motion_level publishes only on change, so a switch "
                 "whose 0x13 is stuck (the flat 32 a factory reset leaves) produces exactly this. Confirm "
                 "with `bridge_watch.py` that the field moves at all on this switch.")

    peak = max(vals(w_lit, first=30)) - d0      # the switch-on transient
    tail = med(vals(w_lit, last=60)) - d0       # two-plus minutes in, still lit, still empty
    back = (med(vals(w_dark1)) or d0) - d0
    lo, hi = med(vals(w_lo, last=40)), med(vals(w_hi, last=40))
    print(f"\n  at switch-on: {peak:+.1f} counts over dark.  two minutes later, still lit: {tail:+.1f}."
          f"  back in the dark: {back:+.1f}.")

    print("\n---- verdict ----")
    if tail >= MOVED:
        print(f"  IT IS THE LOAD. 0x13 held {tail:+.1f} counts above dark after two minutes lit, in an empty")
        print(f"  room, and fell back to {back:+.1f} when the lamp went off. Nobody was near the sensor at any")
        print("  point, so a finger in front of the PIR cannot explain it. The load-detector reading stands,")
        print("  and so does the feedback-loop worry: this baseline is what a walk-past has to rise above.")
        if lo is not None and hi is not None and abs(hi - lo) >= MOVED:
            print(f"\n  AND IT TRACKS BRIGHTNESS: 20% sits at {lo:.1f}, 100% at {hi:.1f} ({hi - lo:+.1f}). The")
            print("  baseline moves with the dim level, not just with on/off -- which the bridge does not re-learn.")
    elif peak >= MOVED:
        print(f"  A TRANSIENT, NOT A PLATEAU. 0x13 jumped {peak:+.1f} as the lamp came on, then settled back to")
        print(f"  {tail:+.1f} within the lit window with the light still on. That is an inrush or a warm-up, not a")
        print("  standing load signal -- so the baseline is safe a minute in, and only the switch-on moment")
        print("  needs suppressing. Narrower fix than the one I was expecting.")
    else:
        print(f"  IT WAS YOU. 0x13 did not move ({peak:+.1f} at switch-on, {tail:+.1f} after) when the lamp came")
        print("  on with nobody present. The 92-97 in docs/brilliant.md was the body in front of the sensor.")
        print("  0x13 is a PIR, the load-detector reading is wrong, and the feedback loop goes with it --")
        print("  but so does the silent probe: migrate.py cannot tell which switch has the lamp this way.")

    print("\n---- what the BRIDGE made of it (a separate question) ----")
    false_on = [t for t, v in r.motion if t >= quiet_from and v == "ON"]
    if not false_on:
        print("  No motion reported in an empty room. The floor re-learn at main.cpp:680 held throughout.")
    else:
        print(f"  It reported motion {len(false_on)}x with nobody there. Each one would light a room, restamp")
        print("  motion_at, and hold an `idle` rule off for as long as it lasts.")
        for t in false_on:
            where = next((lb for lb, a, b, _ in r.windows if a <= t <= b), "between windows (settling)")
            print(f"    +{t - quiet_from:6.1f}s   during: {where}")
        if any(w_lo[1] <= t <= w_hi[2] for t in false_on):
            print("\n  At least one landed in a dim leg. A Level Status does not re-learn the floor (only the")
            print("  0x8204 branch does), so a brightness change is the case that latches. That is the bug.")

    r.c.loop_stop()
    r.c.disconnect()


if __name__ == "__main__":
    main()
