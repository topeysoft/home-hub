#!/usr/bin/env python3
"""Why won't it dim? Ask the node instead of guessing.

On/off works and this switch demonstrably dimmed on Brilliant's own network, so
the load is dimmable and the failure is on our side. `onoff.py` dims with
*unacknowledged* Generic Level Set, which by definition tells us nothing: if the
model is unbound, unimplemented, or the value is out of range, the node stays
silent and we cannot tell those apart.

Everything here is acknowledged, so each step either produces a Status or a
conspicuous silence:

  1. is Generic Level Server (0x1002) actually bound to our AppKey?
  2. does a Level Get come back at all?          -- is the model alive?
  3. does an acknowledged Level Set come back?   -- does it accept values?
  4. if not, is dimming behind Light Lightness instead?

usage: dim.py
"""
import asyncio
import sys

from bleak import BleakClient

import ble
import mesh
import onoff as O

LEVELS = (100, 75, 50, 25)
_tid = 0


def tid():
    global _tid
    _tid = (_tid + 1) & 0xFF
    return _tid


def pct_to_level(pct):
    return int(-32768 + (pct / 100.0) * 65535)


def level_to_pct(lvl):
    return (lvl + 32768) * 100 // 65535


async def ack(n, access, want, label, timeout=8.0):
    await n._tx(access, use_appkey=True)
    return await n.status(want, label, timeout=timeout)


async def main():
    O.rx = asyncio.Queue()
    net = mesh.load()
    key = list(net["nodes"])[0]
    node = net["nodes"][key]
    print(f"target {key} ({node['name']!r})")

    dev = await ble.find_node(node["ble_address"])
    if not dev:
        return

    async with BleakClient(dev, timeout=30.0) as cli:
        mtu = getattr(cli, "mtu_size", 23) or 23
        await cli.start_notify(O.PROXY_OUT, O.on_notify)
        n = O.Node(cli, mtu, net, node)
        seq = mesh.next_seq(net)
        cfg = mesh.net_encrypt(n.netkey, n.iv, ctl=1, ttl=0, seq=seq, src=n.src,
                               dst=0x0000, transport_pdu=bytes([0x00, 0x01]),
                               nonce_type=0x03)
        await O.send(cli, 0x02, cfg, mtu)
        await asyncio.sleep(0.4)
        print(f"connected, MTU {mtu}\n")

        await O.ensure_bound(n, net, node)

        print("--- 1. is Generic Level Server bound? ---")
        r = await n.bind(0x1002)
        st = r[2] if r and len(r) > 2 else None
        bound = st == 0x00 or st == 0x06      # 0x06: already stored
        print(f"    -> {'bound' if bound else 'NOT BOUND'} "
              f"(status {'0x%02x' % st if st is not None else 'no reply'})\n")

        print("--- 2. turn the light on, acknowledged ---")
        on = await ack(n, bytes([0x82, 0x02, 1, tid()]), 0x8204, "OnOff")
        print(f"    -> {'OnOff Server answers' if on else 'NO ANSWER'}\n")
        await asyncio.sleep(1.0)

        print("--- 3. does the Level Server answer a Get? ---")
        g = await ack(n, bytes([0x82, 0x05]), 0x8208, "Level Get")
        if g:
            lvl = int.from_bytes(g[2:4], "little", signed=True)
            print(f"    -> present level {lvl} ({level_to_pct(lvl)}%)\n")
        else:
            print("    -> NO ANSWER: the Level Server is not responding\n")

        print("--- 4. acknowledged Level Sets ---")
        results = []
        for pct in LEVELS:
            lvl = pct_to_level(pct)
            access = bytes([0x82, 0x06]) + (lvl & 0xFFFF).to_bytes(2, "little") \
                + bytes([tid()])
            print(f"  -> Generic Level Set (ack): {pct}% (level {lvl})")
            r = await ack(n, access, 0x8208, f"Level {pct}%")
            if r:
                got = int.from_bytes(r[2:4], "little", signed=True)
                print(f"     <- present {got} ({level_to_pct(got)}%)")
                results.append((pct, got))
            else:
                print("     <- no Status")
                results.append((pct, None))
            await asyncio.sleep(1.5)

        answered = [g for _, g in results if g is not None]
        print("\n--- 5. if Level is a dead end, is it Light Lightness? ---")
        ll = None
        if not answered:
            await n.bind(0x1300)          # Light Lightness Server, if present
            val = 0xC000
            access = bytes([0x82, 0x4C]) + val.to_bytes(2, "little") \
                + bytes([tid()])
            print(f"  -> Light Lightness Set (ack): 0x{val:04x}")
            ll = await ack(n, access, 0x824E, "Light Lightness")
            print(f"     <- {'ANSWERED -- dimming lives here' if ll else 'no Status'}")
        else:
            print("  skipped: the Level Server is answering.")

        print("\n" + "=" * 60)
        if not bound:
            print("  Generic Level Server would not bind. Commands to it are")
            print("  dropped before they reach any handler -- that alone")
            print("  explains the missing dimming.")
        elif not answered:
            print("  Bound, but silent to both Get and acknowledged Set.")
            print("  The model is declared in the composition data and not")
            print("  implemented behind it, or dimming is not on this model.")
            if ll:
                print("  Light Lightness DID answer -- drive dimming from there.")
            else:
                print("  Re-run compo.py and check what element 0 really lists;")
                print("  if Level is the only dimming model and it is a stub,")
                print("  the vendor model is where Brilliant put dimming.")
        elif len(set(answered)) == 1:
            print(f"  The node accepts Level Sets but reports the same value")
            print(f"  ({answered[0]}) every time -- it is acknowledging without")
            print("  acting. Dimming is not wired to Generic Level here.")
        else:
            print("  The Level Server tracks what we set:")
            for pct, got in results:
                print(f"    asked {pct:>3}%  ->  reported "
                      f"{level_to_pct(got)}%" if got is not None
                      else f"    asked {pct:>3}%  ->  no answer")
            print("  If the bulb still did not visibly change, the mesh side is")
            print("  correct and the gap is the load or the switch's bulb-type")
            print("  setting, which Brilliant's panel configured.")
        await cli.stop_notify(O.PROXY_OUT)


if __name__ == "__main__":
    asyncio.run(main())
