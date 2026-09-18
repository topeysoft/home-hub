#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Move a whole LIGHT off the console, pairing and all, in the right order.

Adopting one switch is `restore_switch.py`. A light with two or three switches is
not three runs of that: the companions store their partner's unicast in vendor
field `0x08`, and after a migration that address is WRONG -- it names a node on a
network the switch has just left. Rewriting it is the step that, if forgotten,
produces a switch which provisions cleanly, replays its config, verifies, and
does nothing at all when a finger touches it. That failure has happened here
twice and both times looked like a hardware fault.

So the ordering this enforces, which is the whole point of the tool:

    plan     READ THE PAIRING FIRST, while everything is still on the console.
             0x08 answers to the AppKey alone, so this needs nobody's device key
             and presses nothing. Once a switch is reset this is unrecoverable:
             the reset wipes 0x08, and the only record of which light a companion
             belonged to is gone with it.
    adopt    one switch at a time, on foot -- factory reset, then claim it. The
             plan remembers each switch's new address as it lands.
    finish   rewrite every companion's 0x08 to the main's NEW unicast, and
             0x1b = 03 so it announces at all. Readback confirms.

`0x1b` is the announce flag, NOT a role: a switch carrying 03 still drives
whatever lamp is wired to it (proven 17 Sep on our own stairway load). What 03
buys is the `0403` to the partner; a companion set to 00 is a plate wired to
nothing, which is exactly what a main's config replayed onto a companion does.

    # 1. everything still on the console. Names the light's shape and captures
    #    each switch's config for replay. Nothing is written.
    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/panel-net.json \\
        python3 migrate.py plan 0005 0006

    # 2. per switch, on foot: factory reset it, then
    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/mesh-net.json \\
        python3 migrate.py adopt plan-stairs.json 0006
    #    ...power cycle it (the load type is read only at boot)

    # 3. when every switch in the plan has landed
    BRILLIANT_MESH_STORE=~/.config/brilliant-mesh/mesh-net.json \\
        python3 migrate.py finish plan-stairs.json

PANEL_NODE=<ble-addr> pins the way in, on either network.
"""
import asyncio
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from bleak import BleakClient

import mesh
import onoff as O
from pairs import CID, Link, PASSES
from vendor_store import find_proxy

HERE = Path(__file__).parent


async def _link(net):
    """A proxy link on whichever network the store points at."""
    O.rx = asyncio.Queue()          # onoff's notify callback drops everything without it
    dev = await find_proxy(bytes.fromhex(net["netkey"]))
    if not dev:
        return None, None
    cli = BleakClient(dev, timeout=30.0)
    await cli.connect()
    mtu = getattr(cli, "mtu_size", 23) or 23
    await cli.start_notify(O.PROXY_OUT, O.on_notify)
    link = Link(cli, net, mtu)
    seq = mesh.next_seq(net)
    await O.send(cli, 0x02, mesh.net_encrypt(link.netkey, link.iv, ctl=1, ttl=0, seq=seq,
                 src=link.us, dst=0x0000, transport_pdu=b"\x00\x01", nonce_type=0x03), mtu)
    await asyncio.sleep(0.4)
    return cli, link


def _value(raw):
    """A read reply is `<value> 00`; the trailing byte is not part of the value.
    Echoing it back into a write sends one byte too many and the switch drops it
    in silence -- which cost two restore attempts on a live light."""
    return raw[:-2] if raw and len(raw) > 2 else raw


async def plan(addrs, out_path):
    net = mesh.load()
    cli, link = await _link(net)
    if not link:
        print("no proxy in range for the console's network")
        return 1
    rows = {}
    try:
        for p in range(PASSES):                      # a dropped read looks exactly
            for a in addrs:                          # like a field that is not there,
                partner = _value(await link.field(a, 0x08))   # and here that error turns a
                mode = _value(await link.field(a, 0x1b))      # companion into a light
                r = rows.setdefault(a, {"partner": None, "mode": None, "answered": 0})
                if partner is not None:
                    v = int.from_bytes(bytes.fromhex(partner)[:2], "little")
                    r["partner"], r["answered"] = (v or None), r["answered"] + 1
                if mode is not None:
                    r["mode"] = mode
            print(f"  pass {p + 1}: " + "  ".join(
                f"{a:04x}->{(rows[a]['partner'] or 0):04x}" for a in addrs))
    finally:
        await cli.disconnect()

    silent = [a for a in addrs if rows[a]["answered"] == 0]
    if silent:
        print("\n  these answered nothing on either pass: " +
              " ".join(f"0x{a:04x}" for a in silent))
        print("  they are UNKNOWN, not unpaired. Move the proxy closer and re-run;")
        print("  adopting on this plan would lose a pairing that cannot be read back.")
        return 1

    companions = [a for a in addrs if rows[a]["partner"]]
    mains = [a for a in addrs if not rows[a]["partner"]]
    if len(mains) != 1:
        print(f"\n  expected exactly one switch with no partner, found {len(mains)}: " +
              " ".join(f"0x{m:04x}" for m in mains))
        print("  a light has one switch the lamp is wired to. If these are two lights,")
        print("  plan them separately; if one is missing, it was not in the address list.")
        return 1
    main = mains[0]
    stray = [c for c in companions if rows[c]["partner"] != main]
    if stray:
        print("\n  these name a partner outside this plan: " +
              " ".join(f"0x{c:04x}->0x{rows[c]['partner']:04x}" for c in stray))
        print("  most likely their partner is the CONSOLE, which is not a switch and")
        print("  cannot be migrated. Decide what light they belong to before moving them.")
        return 1

    print(f"\n  one light: 0x{main:04x} has the lamp, "
          f"{len(companions)} companion(s) {' '.join(f'0x{c:04x}' for c in companions)}")

    caps = {}
    for a in addrs:                                   # the replay material, read while
        f = str(HERE / f"capture-{a:04x}.json")       # it still exists to be read
        print(f"\n  capturing 0x{a:04x} -> {f}")
        r = subprocess.run([sys.executable, str(HERE / "vendor_store.py"), f"{a:04x}", f],
                           env={**os.environ}, capture_output=True, text=True)
        tail = [l for l in r.stdout.splitlines() if "answered in" in l]
        print("   ", tail[-1].strip() if tail else "(capture produced no summary -- check it)")
        caps[a] = f

    json.dump({"created": time.time(), "network": mesh.k3(bytes.fromhex(net["netkey"])).hex(),
               "main": {"old": f"{main:04x}", "capture": caps[main], "new": None},
               "companions": [{"old": f"{c:04x}", "capture": caps[c], "new": None,
                               "was_partner": f"{rows[c]['partner']:04x}"} for c in companions]},
              open(out_path, "w"), indent=1)
    print(f"\n  plan written to {out_path}")
    print("  next: factory reset a switch, then `migrate.py adopt " + out_path + " <its old address>`")
    return 0


async def adopt_one(plan_path, old_hex):
    p = json.load(open(plan_path))
    every = [p["main"]] + p["companions"]
    row = next((e for e in every if e["old"].lower() == old_hex.lower()), None)
    if not row:
        print(f"0x{old_hex} is not in this plan. It holds: " +
              " ".join(e["old"] for e in every))
        return 1
    if row["new"]:
        print(f"0x{old_hex} is already adopted as 0x{row['new']}.")
        return 0

    import restore_switch
    await restore_switch.adopt(row["capture"])

    net = mesh.load()                       # restore_switch gives the new node the
    new = max(net["nodes"].values(), key=lambda n: n["unicast"])["unicast"]   # highest unicast
    row["new"] = f"{new:04x}"
    json.dump(p, open(plan_path, "w"), indent=1)
    print(f"\n  0x{old_hex} is now 0x{new:04x} on our network.")
    print("  POWER CYCLE IT NOW -- the load type is read only at boot.")
    left = [e["old"] for e in every if not e["new"]]
    print("  still to move: " + (" ".join(left) if left else "none -- run `finish`"))
    return 0


async def finish(plan_path):
    p = json.load(open(plan_path))
    if not p["main"]["new"]:
        print("the switch with the lamp has not been adopted yet; do that first.")
        return 1
    left = [c["old"] for c in p["companions"] if not c["new"]]
    if left:
        print("not every switch has landed yet: " + " ".join(left))
        return 1
    main_new = int(p["main"]["new"], 16)

    net = mesh.load()
    cli, link = await _link(net)
    if not link:
        print("no proxy in range for our network")
        return 1
    bad = []
    try:
        for c in p["companions"]:
            tgt = int(c["new"], 16)
            for field, value in ((0x08, main_new.to_bytes(2, "little").hex()), (0x1b, "03")):
                access = (bytes([0xC1]) + CID.to_bytes(2, "little")
                          + bytes([0x12, field]) + bytes.fromhex(value) + b"\x00")
                await link._send_access(tgt, access)
                await asyncio.sleep(0.8)
                got = _value(await link.field(tgt, field) or await link.field(tgt, field))
                ok = got == value
                print(f"  0x{tgt:04x} field 0x{field:02x} = {got} {'ok' if ok else 'NOT WRITTEN'}")
                if not ok:
                    bad.append((tgt, field, got))
    finally:
        await cli.disconnect()

    if bad:
        print("\n  some writes did not take. A readback of None is a dropped reply and")
        print("  worth retrying; a readback of the OLD value is a write the switch refused")
        print("  -- check the vendor model is bound to our AppKey (restore_switch does it).")
        return 1
    print(f"\n  every companion now points at 0x{main_new:04x}.")
    print("  Go and press one of them. The proof is the LAMP moving, and on the wire it is")
    print(f"  0x{main_new:04x} broadcasting Generic OnOff Status to 0xffff -- watch with")
    print("  `panel_sniff.py`. Do not look for the companion's 0403: it is a directed")
    print("  unicast and may never reach whatever is listening.")
    return 0


def main():
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        return 2
    if a[0] == "plan" and len(a) >= 2:
        addrs = [int(x, 16) for x in a[1:]]
        return asyncio.run(plan(addrs, str(HERE / f"plan-{a[1]}.json")))
    if a[0] == "adopt" and len(a) == 3:
        return asyncio.run(adopt_one(a[1], a[2]))
    if a[0] == "finish" and len(a) == 2:
        return asyncio.run(finish(a[1]))
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main() or 0)
