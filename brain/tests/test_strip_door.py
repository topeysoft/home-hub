# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Waiting for a finger, without a strip.

The press is the long part of taking a strip, and on a bridge puck every ask is an MQTT hop, a GATT
write, a GATT read and an MQTT hop back -- so how often the hub asks is the whole cost of an errand
(design/ears/Job.dc.html). A strip that can ring is asked once, then again when it rings
(design/ears/Tell.dc.html). These pin that, and the two things it must not break: a strip too old to
ring is still asked the old way, and "I cannot reach the button" still answers at once.
"""
import asyncio, time, unittest

import hub.strip_door as door


class Clear:
    """A session whose crypto is the identity, because what is under test is how often we ask."""
    def encrypt_data(self, b: bytes) -> bytes: return b
    def decrypt_data(self, b: bytes) -> bytes: return b


class Strip:
    """The press endpoint and nothing else: 'waiting' until somebody presses it, then 'pressed'."""
    def __init__(self, rings: bool):
        self.rings = rings
        self.pressed = False
        self.asks = []
        self._rung = asyncio.Event()

    def press(self):
        self.pressed = True
        if self.rings:
            self._rung.set()

    async def send_data(self, ep, data):
        assert ep == 'press'
        self.asks.append(data)
        if data == 'rhythm':
            return 'ok'
        return 'pressed' if self.pressed else 'waiting'

    async def listen_for_ring(self) -> bool:
        return self.rings

    async def wait_for_ring(self):
        await self._rung.wait()
        self._rung.clear()


def run(coro): return asyncio.run(coro)


class TheWait(unittest.TestCase):

    def test_a_strip_that_rings_is_asked_twice_and_not_a_hundred_and_seventy_times(self):
        """The reason the row in design/ears/ exists. Pressed a second and a half in -- two old-style
        polls' worth, so a hub that ignored the ring would have asked four times -- with the backstop
        at its real ten seconds: one ask to learn it is waiting, and one after the ring."""
        async def go():
            strip = Strip(rings=True)
            asyncio.get_running_loop().call_later(1.5, strip.press)
            started = time.monotonic()
            said = await door._wait_for_the_press(strip, Clear(), None, None, 120.0)
            return said, strip.asks, time.monotonic() - started
        said, asks, took = run(go())
        self.assertEqual(said, 'pressed')
        self.assertEqual(asks, ['?', '?'])
        self.assertLess(took, 2.5, 'the ring should cut the ten-second poll short')

    def test_a_strip_too_old_to_ring_is_still_asked_the_old_way(self):
        """The fallback. Nothing tells the two strips apart but how often they are asked."""
        saved = door.PRESS_POLL
        door.PRESS_POLL = 0.05
        try:
            async def go():
                strip = Strip(rings=False)
                asyncio.get_running_loop().call_later(0.3, strip.press)
                said = await door._wait_for_the_press(strip, Clear(), None, None, 120.0)
                return said, len(strip.asks)
            said, asks = run(go())
        finally:
            door.PRESS_POLL = saved
        self.assertEqual(said, 'pressed')
        self.assertGreater(asks, 3, 'an old strip is polled, so it is asked many times')

    def test_cannot_reach_it_answers_at_once_even_while_waiting_ten_seconds_for_a_ring(self):
        """The one the long poll could have broken. The household taps the rung below, and the wall
        must move on then -- not when the backstop poll next comes round."""
        async def go():
            strip = Strip(rings=True)
            out = asyncio.Event()
            asyncio.get_running_loop().call_later(0.2, out.set)
            started = time.monotonic()
            said = await door._wait_for_the_press(strip, Clear(), None, out, 120.0)
            return said, strip.asks, time.monotonic() - started
        said, asks, took = run(go())
        self.assertEqual(said, 'rhythm')
        self.assertEqual(asks[-1], 'rhythm')
        self.assertLess(took, 1.0)

    def test_nobody_pressing_it_still_ends_in_not_pressed_on_time(self):
        """A lost ring must never become a wait with no end: the backstop is capped by what is left."""
        saved = door.RING_POLL
        door.RING_POLL = 10.0
        try:
            async def go():
                strip = Strip(rings=True)
                started = time.monotonic()
                with self.assertRaises(door.NotPressed):
                    await door._wait_for_the_press(strip, Clear(), None, None, 0.4)
                return time.monotonic() - started
            took = run(go())
        finally:
            door.RING_POLL = saved
        self.assertLess(took, 1.5, 'the wait must end when the window does, not a poll later')


if __name__ == '__main__':
    unittest.main()
