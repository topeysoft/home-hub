# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the lights tell you (hub/signals.py, design/signal/). Run from brain/: .venv/bin/python -m unittest -v"""
import asyncio, json, time, unittest
from hub import rules, signals
from hub.model import Device, Room
from tests.test_rules import FakeHub


class FakeStrips:
    """hub.strip, as far as signals reach into it: which strips there are, which hardware each is, and
    what was said to them. `answers` decides whether a strip says it started what it was sent."""
    def __init__(self, hub):
        self.hub, self.strips, self.said, self.answers = hub, {}, [], True
    async def _device_for(self, sid): return self.strips.get(sid, {}).get("hw")
    async def _tell(self, sid, leaf, payload, retain=False):
        self.said.append((sid, leaf, json.loads(payload)))
        body = json.loads(payload)
        if self.answers and body.get("kind") != "stop": self.hub.signals.heard(sid, body["id"])
    def sent(self, kind=None): return [b for _, leaf, b in self.said if leaf == "signal/set" and (kind is None or b["kind"] == kind)]


def house():
    """A drive the family comes in through: a gate, motion on the drive, and a strip along it."""
    h = FakeHub()
    h.home.rooms["drive"] = Room("drive", "Driveway")
    gate = Device("binary_sensor.gate", "Gate", "drive", "contact", "off", seen=time.time())
    eyes = Device("binary_sensor.drive_motion", "Drive motion", "drive", "motion", "off", seen=time.time())
    strip = Device("light.strip_abc", "Driveway strip", "drive", "light", "off", hw="dev-abc")
    porch = Device("light.porch", "Porch light", "drive", "light", "off", attrs={"supported_color_modes": ["hs"]})
    white = Device("light.lamp", "Drive lamp", "drive", "light", "off", attrs={"supported_color_modes": ["color_temp"]})
    for d in (gate, eyes, strip, porch, white):
        h.home.rooms["drive"].devices.append(d); h.home.devices[d.id] = d
    h.entry = ["drive"]
    h.strip = FakeStrips(h)
    h.strip.strips = {"abc": {"online": True, "hw": "dev-abc"}}
    h.signals = signals.Signals(h)
    h.signals._dark = lambda: True
    return h, gate, eyes


def run(coro): return asyncio.run(coro)


async def settle():
    for _ in range(20): await asyncio.sleep(0)


class InOrOut(unittest.TestCase):
    def test_a_door_that_opens_with_nobody_by_it_is_somebody_coming_in(self):
        self.assertEqual(signals.in_or_out(1000.0, None), "arriving")
        self.assertEqual(signals.in_or_out(1000.0, 1000.0 - signals.WINDOW - 1), "arriving")

    def test_motion_by_it_first_is_somebody_going_out(self):
        self.assertEqual(signals.in_or_out(1000.0, 990.0), "leaving")


class ThePage(unittest.TestCase):
    def test_the_four_come_in_the_order_the_board_draws_them(self):
        h, *_ = house()
        page = run(h.signals.page())
        self.assertEqual([m["id"] for m in page["meanings"]], ["arriving", "leaving", "open", "done"])

    def test_without_a_way_in_arriving_says_how_to_get_one(self):
        h, *_ = house(); h.entry = []
        row = run(h.signals.page())["meanings"][0]
        self.assertFalse(row["available"])
        self.assertIn("Routines", row["hint"])

    def test_the_lights_it_names_are_the_ones_that_can_show_it(self):
        h, *_ = house()
        row = run(h.signals.page())["meanings"][0]
        self.assertTrue(row["available"])
        self.assertEqual(row["lights"], ["Driveway strip", "Porch light"])     # the white-only lamp cannot

    def test_nothing_in_a_house_reports_how_far_along_so_that_one_says_so(self):
        h, *_ = house()
        done = run(h.signals.page())["meanings"][3]
        self.assertFalse(done["available"])

    def test_all_four_start_off(self):
        h, *_ = house()
        self.assertFalse(any(m["on"] for m in run(h.signals.page())["meanings"]))


class Direction(unittest.TestCase):
    def test_toward_the_house_runs_toward_whichever_end_is_the_house(self):
        h, *_ = house()
        t = {"strip": "abc"}
        h.settings.data["signals"] = {"ends": {"abc": "plug"}}
        self.assertEqual(h.signals._dir(t, "house"), (-1, None))
        self.assertEqual(h.signals._dir(t, "out"), (1, None))
        h.settings.data["signals"] = {"ends": {"abc": "far"}}
        self.assertEqual(h.signals._dir(t, "house"), (1, None))

    def test_a_strip_nobody_has_asked_runs_away_from_the_plug_and_says_it_guessed(self):
        h, *_ = house()
        d, note = h.signals._dir({"strip": "abc"}, "house")
        self.assertEqual(d, 1)
        self.assertIn("which end", note)


class ShowMeNow(unittest.TestCase):
    def test_every_light_says_how_it_answered(self):
        h, *_ = house()
        w = run(h.signals.try_("arriving", "now"))
        self.assertEqual(w["state"], "passed")
        by = {s["text"]: s for s in w["steps"]}
        self.assertEqual(by["Driveway strip showed the way in"]["state"], "ok")
        self.assertEqual(by["Porch light showed the way in"]["state"], "ok")
        self.assertEqual(by["Drive lamp showed the way in"]["state"], "skip")
        self.assertEqual(h.signals.last["arriving"]["line"], "everything answered")

    def test_what_the_strip_is_sent(self):
        h, *_ = house()
        run(h.signals.try_("arriving", "now"))
        body = h.strip.sent("way")[0]
        self.assertEqual(body["rgb"], list(signals.EMITTER["arriving"]))
        self.assertEqual((body["ms"], body["times"]), signals.TIMING["way"])
        self.assertIn(body["dir"], (1, -1))
        self.assertIn(("light", "turn_on", "light.porch", {"flash": "long"}), h.ha.calls)

    def test_a_strip_that_is_asked_and_never_answers_fails_and_says_so(self):
        h, *_ = house(); h.strip.answers = False
        signals.ACK_WAIT, was = 0.05, signals.ACK_WAIT
        try: w = run(h.signals.try_("arriving", "now"))
        finally: signals.ACK_WAIT = was
        self.assertEqual(w["state"], "failed")
        self.assertIn("did not answer", next(s for s in w["steps"] if s["key"] == "light:light.strip_abc")["sub"])

    def test_a_strip_that_is_away_is_not_sent_anything(self):
        h, *_ = house(); h.strip.strips["abc"]["online"] = False
        w = run(h.signals.try_("arriving", "now"))
        self.assertEqual(w["state"], "failed")
        self.assertEqual(h.strip.sent(), [])


class WaitForTheRealThing(unittest.TestCase):
    def test_a_gate_opening_with_nobody_by_it_passes_arriving(self):
        h, gate, _ = house()
        async def go():
            await h.signals.try_("arriving", "watch")
            gate.state = "on"; h.signals.on_state(gate, "off"); await settle()
            return h.signals.trying
        w = run(go())
        self.assertEqual(w["state"], "passed", w["steps"])
        self.assertEqual([s["key"] for s in w["steps"][:2]], ["heard", "decide"])
        self.assertIn("nobody moving by it", w["steps"][1]["sub"])

    def test_leaving_that_hears_arriving_names_the_sensor_that_did_not_see(self):
        h, gate, eyes = house()
        eyes.seen = time.time() - 3 * 86400
        async def go():
            await h.signals.try_("leaving", "watch")
            gate.state = "on"; h.signals.on_state(gate, "off"); await settle()
            return h.signals.trying
        w = run(go())
        self.assertEqual(w["state"], "failed")
        decide = next(s for s in w["steps"] if s["key"] == "decide")
        self.assertEqual(decide["state"], "no")
        self.assertIn("Drive motion was last heard from 3 days ago", decide["sub"])
        # and nothing was shown: the lights after a broken link are left waiting, not failed
        self.assertEqual(h.strip.sent(), [])
        self.assertEqual(next(s for s in w["steps"] if s["key"] == "light:light.strip_abc")["state"], "wait")

    def test_motion_then_the_gate_passes_leaving(self):
        h, gate, eyes = house()
        async def go():
            await h.signals.try_("leaving", "watch")
            h.home.rooms["drive"].motion_at = time.time() - 10
            gate.state = "on"; h.signals.on_state(gate, "off"); await settle()
            return h.signals.trying
        self.assertEqual(run(go())["state"], "passed")

    def test_a_watch_nothing_happens_to_names_what_it_was_listening_to(self):
        h, *_ = house()
        async def go():
            w = await h.signals.try_("arriving", "watch")
            w["ends"] = time.time() - 1
            await h.signals.tick()
            return w
        w = run(go())
        self.assertEqual(w["state"], "failed")
        self.assertIn("Gate (last heard just now)", w["steps"][0]["sub"])

    def test_a_room_that_cannot_see_motion_decides_nothing_and_says_why(self):
        h, gate, eyes = house()
        h.home.rooms["drive"].devices.remove(eyes)
        async def go():
            await h.signals.try_("arriving", "watch")
            gate.state = "on"; h.signals.on_state(gate, "off"); await settle()
            return h.signals.trying
        w = run(go())
        self.assertEqual(w["state"], "failed")
        self.assertIn("could not tell in from out", next(s for s in w["steps"] if s["key"] == "decide")["text"])


class ForReal(unittest.TestCase):
    def test_off_shows_nothing(self):
        h, gate, _ = house()
        async def go():
            gate.state = "on"; h.signals.on_state(gate, "off"); await settle()
        run(go())
        self.assertEqual(h.strip.sent(), [])

    def test_on_after_dark_shows_it_once_and_not_again_straight_away(self):
        h, gate, _ = house()
        h.signals.set_on("arriving", True)
        async def go():
            for _ in range(2):
                gate.state = "on"; h.signals.on_state(gate, "off"); await settle()
                gate.state = "off"; h.signals.on_state(gate, "on"); await settle()
        run(go())
        self.assertEqual(len(h.strip.sent("way")), 1)

    def test_in_daylight_it_waits_for_dark(self):
        h, gate, _ = house()
        h.signals.set_on("arriving", True); h.signals._dark = lambda: False
        async def go():
            gate.state = "on"; h.signals.on_state(gate, "off"); await settle()
        run(go())
        self.assertEqual(h.strip.sent(), [])

    def test_a_phone_coming_home_is_arriving(self):
        h, *_ = house()
        h.signals.set_on("arriving", True)
        async def go():
            h.signals.on_people({"person.a": {"name": "Ada", "home": False}}, {"person.a": {"name": "Ada", "home": True}})
            await settle()
        run(go())
        self.assertEqual(len(h.strip.sent("way")), 1)

    def test_a_door_left_open_breathes_until_it_is_shut(self):
        h, gate, _ = house()
        h.signals.set_on("open", True)
        gate.state, gate.since = "on", time.time() - signals.OPEN_AFTER - 1
        async def go():
            await h.signals.tick(); await h.signals.tick()
            gate.state = "off"; h.signals.on_state(gate, "on"); await settle()
        run(go())
        self.assertEqual(len(h.strip.sent("call")), 1)
        self.assertEqual(len(h.strip.sent("stop")), 1)


class AHouseholdsOwn(unittest.TestCase):
    def rule(self, **then):
        return {"id": "drive-in", "name": "Show the way in", "room": "drive", "when": {"contact": "open"},
                "if": [["sun", "below", 0]], "then": [{"intent": "occupied"}, {"signal": "way", "toward": "house", **then}]}

    def test_a_signal_is_an_outcome_a_routine_may_have(self):
        good, errors = rules.validate({"rules": [self.rule()]}, {"drive"})
        self.assertEqual(errors, [])
        self.assertEqual(len(good), 1)

    def test_it_is_held_to_the_same_four(self):
        _, errors = rules.validate({"rules": [{**self.rule(), "then": {"signal": "rainbow"}}]}, {"drive"})
        self.assertTrue(errors)
        _, errors = rules.validate({"rules": [self.rule(rgb=[300, 0, 0])]}, {"drive"})
        self.assertTrue(errors)

    def test_trying_one_sets_its_conditions_aside_and_runs_only_its_signal(self):
        h, gate, _ = house()
        h.engine.rules = [self.rule()]
        h.engine.load = lambda force=False: None
        h.engine.check = lambda c, room, now: list(c) + [None, False]      # the sun is up
        async def go():
            await h.signals.try_("rule:drive-in", "watch")
            gate.state = "on"; h.engine.on_state(gate, "off"); await settle()
            return h.signals.trying
        w = run(go())
        self.assertEqual(w["state"], "passed", w["steps"])
        self.assertEqual(len(h.strip.sent("way")), 1)
        self.assertEqual(h.home.rooms["drive"].intent, "unknown")            # the room was not set at noon
        self.assertIn("set aside", next(s for s in w["steps"] if s["key"] == "decide")["text"])


if __name__ == "__main__":
    unittest.main()
