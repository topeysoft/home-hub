# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Lifting a bridge's own light, with no puck, no mesh and nobody walking past.

What these hold is the behaviour somebody in a hallway at 2am would notice -- the glow comes up as
they arrive and goes down after they have gone -- and the four ways a naive version would be wrong:
lighting up every puck in the house, lifting a light that is off, doing it for a household that
never asked, and settling while somebody is still standing there.

And one that is not about behaviour at all: a lift must never go out as a brightness. That would be
two flash erases per walk-past for the life of the puck, and would drag the household's own setting
up and down in Home Assistant. The topic is the whole point, so a test names it.
"""
import asyncio, json, tempfile, unittest
from pathlib import Path

from hub.nightlight import Nightlight
from hub.settings import Settings


class FakeHA:
    def __init__(self): self.published = []
    async def call(self, domain, service, entity_id, **data):
        self.published.append((data["topic"], data["payload"]))


class FakeBridges:
    def __init__(self): self.pucks, self.rooms = {}, {}
    def room_of(self, chip): return self.rooms.get(chip)


class FakeHub:
    def __init__(self, tmp):
        self.ha, self.bridge = FakeHA(), FakeBridges()
        self.settings = Settings(Path(tmp) / "settings.json")


class Dev:
    def __init__(self, cap="motion", state="on", room="hall"):
        self.capability, self.state, self.room_id = cap, state, room


def run(coro): return asyncio.run(coro)


class Lifting(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hub = FakeHub(self.tmp)
        self.hub.bridge.pucks = {"c8ebba": {"online": True, "night": True}}
        self.hub.bridge.rooms = {"c8ebba": "hall"}
        self.hub.settings.set(bridges={"c8ebba": {"since": 1, "lift": True}})
        self.n = Nightlight(self.hub)
        self.n.hold = 0.05          # a whole swell and settle in a heartbeat

    def sent(self): return self.hub.ha.published

    async def walk_past(self, dev=None, settle=True):
        self.n.on_state(dev or Dev(), "off")
        await asyncio.sleep(0.01)                    # let the lift task run
        if settle: await asyncio.sleep(self.n.hold + 0.05)

    def test_somebody_walks_past_and_it_comes_up_then_goes_down(self):
        run(self.walk_past())
        self.assertEqual(self.sent(), [("mesh/bridge/c8ebba/night/lift/set", "255"),
                                       ("mesh/bridge/c8ebba/night/lift/set", "0")])

    def test_a_lift_is_never_sent_as_a_brightness(self):
        """It would cost two flash erases a walk-past, and move the household's own setting."""
        run(self.walk_past())
        self.assertEqual([t for t, _ in self.sent() if "brightness" in t], [])

    def test_still_there_holds_it_up_and_does_not_send_again(self):
        async def go():
            await self.walk_past(settle=False)
            for _ in range(3):                       # three more passes inside the hold
                await asyncio.sleep(self.n.hold / 2)
                await self.walk_past(settle=False)
            self.assertEqual(self.sent(), [("mesh/bridge/c8ebba/night/lift/set", "255")])
            await asyncio.sleep(self.n.hold + 0.05)
            self.assertEqual(self.sent()[-1], ("mesh/bridge/c8ebba/night/lift/set", "0"))
        run(go())

    def test_a_puck_in_another_room_is_not_woken_by_it(self):
        run(self.walk_past(Dev(room="kitchen")))
        self.assertEqual(self.sent(), [])

    def test_a_light_that_is_off_is_not_lifted_into_life(self):
        self.hub.bridge.pucks["c8ebba"]["night"] = False
        run(self.walk_past())
        self.assertEqual(self.sent(), [])

    def test_nobody_asked_for_this(self):
        self.hub.settings.set(bridges={"c8ebba": {"since": 1}})
        run(self.walk_past())
        self.assertEqual(self.sent(), [])

    def test_a_puck_that_is_not_there_is_not_talked_to(self):
        self.hub.bridge.pucks["c8ebba"]["online"] = False
        run(self.walk_past())
        self.assertEqual(self.sent(), [])

    def test_only_motion_arriving_counts(self):
        run(self.walk_past(Dev(state="off")))
        run(self.walk_past(Dev(cap="light")))
        self.assertEqual(self.sent(), [])

    def test_motion_that_was_already_on_is_not_an_arrival(self):
        async def go(): self.n.on_state(Dev(), "on"); await asyncio.sleep(0.01)
        run(go())
        self.assertEqual(self.sent(), [])


class TheSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.hub = FakeHub(self.tmp)
        self.hub.bridge.pucks = {"c8ebba": {"online": True, "night": True}}
        self.hub.bridge.rooms = {"c8ebba": "hall"}
        self.hub.settings.set(bridges={"c8ebba": {"since": 1}})
        self.n = Nightlight(self.hub)
        self.n.hold = 0.05

    def test_it_is_off_until_somebody_flips_it(self):
        self.assertFalse(self.n.wants("c8ebba"))

    def test_flipping_it_is_written_down_at_once(self):
        """Synchronously: a hub restarted a second later must still know."""
        self.assertTrue(self.n.on_command("c8ebba", "ON"))
        self.assertTrue(self.n.wants("c8ebba"))
        self.assertEqual(self.hub.settings.get("bridges")["c8ebba"]["since"], 1)   # and keeps the rest

    def test_a_bridge_the_hub_does_not_know_is_refused(self):
        self.assertFalse(self.n.on_command("ffffff", "ON"))

    def test_turning_it_off_while_it_is_up_puts_it_down_now(self):
        async def go():
            self.n.on_command("c8ebba", "ON")
            self.n.on_state(Dev(), "off")
            await asyncio.sleep(0.01)
            self.assertIn(("mesh/bridge/c8ebba/night/lift/set", "255"), self.hub.ha.published)
            self.n.on_command("c8ebba", "OFF")
            await asyncio.sleep(0.02)
            self.assertEqual(self.hub.ha.published[-1], ("mesh/bridge/c8ebba/night/lift/set", "0"))
        run(go())

    def test_it_lands_on_the_pucks_own_device(self):
        run(self.n.announce("c8ebba"))
        topic, payload = self.hub.ha.published[0]
        self.assertEqual(topic, "homeassistant/switch/mesh_bridge_c8ebba_motion/config")
        d = json.loads(payload)
        self.assertEqual(d["dev"]["ids"], ["mesh_bridge_c8ebba"])
        self.assertEqual(d["cmd_t"], "mesh/bridge/c8ebba/motion/set")
        self.assertEqual(self.hub.ha.published[-1], ("mesh/bridge/c8ebba/motion", "OFF"))


if __name__ == "__main__":
    unittest.main()
