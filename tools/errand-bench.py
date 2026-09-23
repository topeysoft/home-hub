#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Adopt a strip through a puck, over the errand protocol the bridge ships.

A BENCH DRIVER for brilliant/esp32-bridge/src/errand.{h,cpp}. It drives `strip_door.adopt()` -- the
real one -- with a transport that speaks the shipped format to a puck, and takes the strip's address
from what the puck's EAR reported (src/ear.h), exactly as the hub will: no scan, a sighting seconds
old, and the address type that goes with it (docs/strip.md items 42 and 43). What it proves is the
firmware half: that the format, the ids, the base64 and the ring all work on the air. The brain's half
speaks the same format through Home Assistant rather than paho, and is tested against it separately.

    brain/.venv/bin/python -u tools/errand-bench.py --puck 08388e \\
        --ssid VirusBroadcast --pass '...' --broker 192.168.86.53 --password '...'

`--base bench` by default, because the bench puck talks on its own base on purpose: nothing it says
may land where a house is reading.
"""
import argparse
import asyncio
import base64
import os
import secrets
import sys
import time

# Both paths, explicitly: strip_door adds brain/vendor itself, and ordering is not a contract.
_BRAIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'brain')
sys.path.insert(0, _BRAIN)
sys.path.insert(1, os.path.join(_BRAIN, 'vendor'))

from esp_prov.transport.transport import Transport
from hub import strip_door
from hub.ears import Ears


class Errand(Transport):
    """protocomm over somebody else's radio, in the words errand.h defines.

    Holds no key, does no crypto: every byte it carries was made by `adopt()` above it and is
    unwrapped by the strip below it. That is the property the whole direction rests on."""

    def __init__(self, client, base, timeout=20.0):
        self.client, self.base, self.timeout = client, base, timeout
        self.loop = asyncio.get_running_loop()
        self.id = secrets.token_hex(4)
        self.n = 0
        self.waiting = {}                 # n -> future, and "open" -> future
        self.can_ring = False
        self.rung = asyncio.Event()
        self.rings = self.exchanges = self.out_bytes = self.in_bytes = 0
        self.slowest = 0.0
        self.closed = None

    def ask(self, line):
        self.client.publish(f'{self.base}/errand/ask', line, qos=0)

    def on_tell(self, line: str):
        """From paho's thread: hand each answer to the loop rather than touching a future here."""
        words = line.split(' ')
        if len(words) < 2 or words[1] != self.id:
            return                        # somebody else's errand, or an old one of ours
        verb = words[0]
        if verb == 'open':
            self._settle('open', ('open', words[2] if len(words) > 2 else 'quiet'))
        elif verb == 'ok' and len(words) >= 3:
            self._settle(words[2], ('ok', words[3] if len(words) > 3 else ''))
        elif verb == 'fail' and len(words) >= 4:
            self._settle('open' if words[2] == '-' else words[2], ('fail', words[3]))
        elif verb == 'ring':
            self.rings += 1
            print('  -- the strip rang')
            self.loop.call_soon_threadsafe(self.rung.set)
        elif verb == 'closed':
            self.closed = words[2] if len(words) > 2 else '?'
            print(f'  -- the puck closed the errand: {self.closed}')

    def _settle(self, key, value):
        fut = self.waiting.pop(key, None)
        if fut:
            self.loop.call_soon_threadsafe(lambda: fut.done() or fut.set_result(value))

    async def open(self, addr, kind):
        fut = self.loop.create_future()
        self.waiting['open'] = fut
        self.ask(f'open {self.id} {addr} {kind}')
        verb, said = await asyncio.wait_for(fut, 30)
        if verb != 'open':
            raise RuntimeError(f'the puck could not open the errand: {said}')
        self.can_ring = said == 'ring'
        return said

    async def send_data(self, ep_name, data):
        self.n += 1
        n = str(self.n)
        body = data.encode('latin-1')
        fut = self.loop.create_future()
        self.waiting[n] = fut
        started = time.monotonic()
        self.ask(f'send {self.id} {n} 0x{strip_door.ENDPOINTS[ep_name]:04x} '
                 f'{base64.b64encode(body).decode()}')
        try:
            verb, said = await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            self.waiting.pop(n, None)
            raise RuntimeError(f'the puck did not answer for {ep_name} within {self.timeout}s')
        took = time.monotonic() - started
        if verb != 'ok':
            print(f'  {ep_name:<13} {len(body):>4} out  refused: {said}')
            raise RuntimeError(f'{ep_name}: {said}')
        reply = base64.b64decode(said) if said else b''
        self.slowest = max(self.slowest, took)
        self.exchanges += 1
        self.out_bytes += len(body)
        self.in_bytes += len(reply)
        print(f'  {ep_name:<13} {len(body):>4} out  {len(reply):>4} back  {took * 1000:>6.0f} ms')
        return reply.decode('latin-1')

    async def send_session_data(self, data):
        return await self.send_data('prov-session', data)

    async def send_config_data(self, data):
        return await self.send_data('prov-config', data)

    async def listen_for_ring(self) -> bool:
        return self.can_ring

    async def wait_for_ring(self):
        await self.rung.wait()
        self.rung.clear()

    async def disconnect(self):
        pass


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--puck', required=True, help='the puck chip id, six hex digits')
    ap.add_argument('--ssid', required=True)
    ap.add_argument('--pass', dest='passphrase', required=True)
    ap.add_argument('--broker', default='hub.local')
    ap.add_argument('--user', default=os.environ.get('MQTT_USER', 'hub'))
    ap.add_argument('--password', default=os.environ.get('MQTT_PASSWORD', ''))
    ap.add_argument('--base', default='bench', help="the puck's MQTT base; bench, not mesh")
    ap.add_argument('--press-wait', type=float, default=120.0)
    args = ap.parse_args()

    import paho.mqtt.client as mqtt
    base = f'{args.base}/bridge/{args.puck}'
    ears = Ears()
    box = {}
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if args.password:
        client.username_pw_set(args.user, args.password)

    def on_connect(c, u, flags, rc, props=None):
        c.subscribe(f'{base}/errand/tell')
        c.subscribe(f'{base}/heard')

    def on_message(c, u, msg):
        text = msg.payload.decode('utf-8', 'replace')
        if msg.topic.endswith('/heard'):
            ears.from_puck(args.puck, text)       # the hub's own table, fed as the hub feeds it
        elif (t := box.get('t')) is not None:
            t.on_tell(text)

    client.on_connect, client.on_message = on_connect, on_message
    client.connect(args.broker, 1883, 30)
    client.loop_start()

    # THE ADDRESS COMES FROM THE EAR, the way it will in a house: wait for the puck to report a strip
    # of ours, and take the loudest one it has heard.
    print(f'waiting for {args.puck} to hear a strip knocking...')
    addr = kind = None
    for _ in range(60):
        heard = [(a, h) for a in list(ears._heard) for h in ears.who_can_hear(a) if h['ear'] == args.puck]
        if heard:
            addr, h = max(heard, key=lambda ah: ah[1]['rssi'])
            kind = h['type']
            print(f'  heard {addr} ({kind}) at {h["rssi"]} dBm')
            break
        await asyncio.sleep(1)
    if not addr:
        print('the puck heard no strip knocking')
        client.loop_stop()
        return

    where = {'mhost': args.broker, 'base': 'strip'}
    if args.user:
        where['muser'] = args.user
    if args.password:
        where['mpass'] = args.password

    transport = Errand(client, base)
    box['t'] = transport
    started = time.monotonic()
    try:
        said = await transport.open(addr.lower(), kind)
        print(f'  errand {transport.id} open, and the strip {"can ring" if said == "ring" else "cannot ring"}')
        outcome = await strip_door.adopt(
            addr, args.ssid, args.passphrase, hub=where,
            on_pressed=lambda: print('  -- the strip says it was pressed'),
            press_wait=args.press_wait, transport=transport)
        print(f'\n{outcome.upper()} in {time.monotonic() - started:.1f}s')
    except strip_door.NotPressed:
        print('\nNOBODY PRESSED IT. Not a radio failure: the errand held the whole time.')
    except Exception as e:                                        # noqa: BLE001 -- a bench report
        print(f'\nFAILED after {time.monotonic() - started:.1f}s: {type(e).__name__}: {e}')
    finally:
        print(f'{transport.exchanges} exchanges through the puck '
              f'({"it rang " + str(transport.rings) + " time(s)" if transport.can_ring else "no ring"}), '
              f'{transport.out_bytes} bytes out, {transport.in_bytes} back, '
              f'slowest {transport.slowest * 1000:.0f} ms')
        transport.ask(f'close {transport.id}')
        await asyncio.sleep(1.5)
        client.loop_stop()


if __name__ == '__main__':
    asyncio.run(main())
