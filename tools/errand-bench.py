#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adopt a strip through a puck, to find out whether the session really does stay end to end.

A BENCH INSTRUMENT. `design/ears/` chose direction A -- a hub that cannot hear a strip hands the job
to a bridge puck that can -- and the claim the whole direction rests on is that the puck is only a
corridor: the SRP6a session is opened here and closed at the strip, so the courier carries bytes it
cannot read, and the press gate stays on the thing itself. docs/strip.md item 38 proved the radio
will hold the second link. It did not prove this, because no handshake had ever gone through one.

So this drives `strip_door.adopt()` -- THE REAL ONE, not a copy of it -- with a transport that
publishes each protocomm request to a puck over MQTT and waits for the answer to come back. If the
adoption completes, the claim is measured rather than argued: every byte of the session was made
here, carried by something that never had the key, and unwrapped at the strip.

The wire format below is the shortest thing that answers the question and IS NOT A PROPOSAL. What
ships gets drawn first, per AGENTS.md section 1.

    brain/.venv/bin/python tools/errand-bench.py --puck 08388e \
        --ssid VirusBroadcast --pass '...' --broker 192.168.86.53

The puck finds the door itself unless `--strip <addr>` hands it one -- a sighting from the puck's
passive ear (docs/strip.md item 42), which is what the shipped errand will carry. The address holds
for the whole boot; what failed here once was opening a random address as a public one.
"""
import argparse
import asyncio
import os
import sys
import time

# BOTH PATHS, EXPLICITLY. strip_door adds brain/vendor itself, so this used to work by importing it
# first -- and then a tidy-up sorted the imports and `esp_prov` was gone. Ordering is not a contract.
_BRAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'brain')
sys.path.insert(0, _BRAIN)
sys.path.insert(1, os.path.join(_BRAIN, 'vendor'))

from esp_prov.transport.transport import Transport
from hub import strip_door

# The endpoint order the puck's DOOR_EP knows. An index rather than a name because the puck must not
# have to parse anything: it is told where to put the bytes, not what they are.
EP_INDEX = {'prov-session': 0, 'prov-config': 1, 'proto-ver': 2, 'hub': 3, 'press': 4}


class Errand(Transport):
    """protocomm over somebody else's radio.

    Every method here is the same shape as `strip_door._Bleak`: hand the bytes to the endpoint and
    give back what came out. The difference is two MQTT hops in the middle, and nothing else -- in
    particular this class holds no key, does no crypto, and could not tell a handshake from a
    shopping list. That is the property being tested.
    """

    def __init__(self, client, base, timeout=20.0):
        self.client = client
        self.base = base
        self.timeout = timeout
        self.seq = 0
        self.waiting = {}
        self.loop = asyncio.get_running_loop()
        self.exchanges = 0
        self.out_bytes = 0
        self.in_bytes = 0
        self.slowest = 0.0
        self.can_ring = False
        self.rung = asyncio.Event()
        self.rings = 0

    def on_ring(self):
        """From paho's thread, like on_rx."""
        self.rings += 1
        print('  -- the strip rang')
        self.loop.call_soon_threadsafe(self.rung.set)

    async def listen_for_ring(self) -> bool:
        return self.can_ring

    async def wait_for_ring(self):
        await self.rung.wait()
        self.rung.clear()

    def on_rx(self, payload: bytes):
        """Called from paho's thread, so it hands the answer back across to ours rather than
        touching a future directly -- an asyncio future is not thread-safe and a handshake is
        exactly the place a lost wakeup would look like a radio fault."""
        if len(payload) < 2:
            return
        fut = self.waiting.pop(payload[0], None)
        if fut and not fut.done():
            self.loop.call_soon_threadsafe(fut.set_result, (payload[1], payload[2:]))

    async def send_data(self, ep_name, data):
        self.seq = (self.seq + 1) % 256
        seq = self.seq
        body = data.encode('latin-1')
        fut = self.loop.create_future()
        self.waiting[seq] = fut
        started = time.monotonic()
        self.client.publish(f'{self.base}/errand/tx', bytes([seq, EP_INDEX[ep_name]]) + body, qos=0)
        try:
            ok, reply = await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            self.waiting.pop(seq, None)
            raise RuntimeError(f'the puck did not answer for {ep_name} within {self.timeout}s')
        took = time.monotonic() - started
        self.slowest = max(self.slowest, took)
        self.exchanges += 1
        self.out_bytes += len(body)
        self.in_bytes += len(reply)
        print(f'  {ep_name:<13} {len(body):>4} out  {len(reply):>4} back  {took * 1000:>6.0f} ms'
              f'{"" if ok else "   <- the strip refused it"}')
        if not ok:
            raise RuntimeError(f'the strip refused a write on {ep_name}')
        return reply.decode('latin-1')

    async def send_session_data(self, data):
        return await self.send_data('prov-session', data)

    async def send_config_data(self, data):
        return await self.send_data('prov-config', data)

    async def disconnect(self):
        pass


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--puck', required=True, help='the bench puck chip id, six hex digits')
    ap.add_argument('--strip', default='', help='a warm BLE address; by default the puck finds the door')
    ap.add_argument('--ssid', required=True)
    ap.add_argument('--pass', dest='passphrase', required=True)
    ap.add_argument('--broker', default='hub.local')
    ap.add_argument('--user', default=os.environ.get('MQTT_USER', 'hub'))
    ap.add_argument('--password', default=os.environ.get('MQTT_PASSWORD', ''))
    ap.add_argument('--base', default='bench', help='the puck MQTT base; bench, not mesh')
    ap.add_argument('--press-wait', type=float, default=120.0)
    args = ap.parse_args()

    import paho.mqtt.client as mqtt
    base = f'{args.base}/bridge/{args.puck}'
    transport_box = {}

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if args.password:
        client.username_pw_set(args.user, args.password)

    opened = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_connect(c, u, flags, rc, props=None):
        c.subscribe(f'{base}/errand/rx')
        c.subscribe(f'{base}/errand/ring')
        c.subscribe(f'{base}/errand')

    def on_message(c, u, msg):
        if msg.topic.endswith('/errand'):
            said = msg.payload.decode('utf-8', 'replace')
            print(f'  puck: {said}')
            if 'session open' in said:
                t = transport_box.get('t')
                if t is not None:
                    t.can_ring = 'can ring' in said
                loop.call_soon_threadsafe(opened.set)
            return
        if msg.topic.endswith('/errand/ring'):
            t = transport_box.get('t')
            if t is not None:
                t.on_ring()
            return
        t = transport_box.get('t')
        if t is not None:
            t.on_rx(msg.payload)

    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(args.broker, 1883, 30)
    client.loop_start()

    # The same four keys brain/hub/strip.py:460 hands a strip, so the last step of the
    # adoption is the real one rather than a shape that only exists in this script.
    where = {'mhost': args.broker, 'base': 'strip'}
    if args.user:
        where['muser'] = args.user
    if args.password:
        where['mpass'] = args.password

    transport = Errand(client, base)
    transport_box['t'] = transport

    # No address by default: the puck finds the door itself. With one, it is opened as a RANDOM
    # address, which a strip's is -- see "open" in errand_bench.h.
    print(f'asking {args.puck} to open a link{" to " + args.strip if args.strip else ""}...')
    client.publish(f'{base}/errand/set', f'open {args.strip}'.strip())
    try:
        await asyncio.wait_for(opened.wait(), 120)
    except asyncio.TimeoutError:
        print('the puck never got a link open; nothing to drive')
        client.loop_stop()
        return

    started = time.monotonic()
    try:
        outcome = await strip_door.adopt(
            args.strip or '(the puck found it)', args.ssid, args.passphrase,
            hub=where,
            on_pressed=lambda: print('  -- the strip says it was pressed'),
            press_wait=args.press_wait,
            transport=transport,
        )
        print(f'\n{outcome.upper()} in {time.monotonic() - started:.1f}s')
    except strip_door.NotPressed:
        print('\nNOBODY PRESSED IT. Not a radio failure: the session held the whole time.')
    except Exception as e:                                        # noqa: BLE001 -- a bench report
        print(f'\nFAILED after {time.monotonic() - started:.1f}s: {type(e).__name__}: {e}')
    finally:
        print(f'{transport.exchanges} exchanges through the puck '
              f'({"it could ring, and rang " + str(transport.rings) + " time(s)" if transport.can_ring else "it could not ring"}), '
              f'{transport.out_bytes} bytes out, {transport.in_bytes} back, '
              f'slowest {transport.slowest * 1000:.0f} ms')
        client.publish(f'{base}/errand/set', 'close')
        await asyncio.sleep(1)
        client.loop_stop()


if __name__ == '__main__':
    asyncio.run(main())
