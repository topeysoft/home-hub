"""Run from brain/: .venv/bin/python -m unittest -v"""
import asyncio, time, unittest
from datetime import datetime, timedelta
from hub import rules
from hub.presence import Presence
from tests.test_rules import FakeHub, FakeLog, use, rule, TZ


def st(eid, state, name=None):
    return {"entity_id": eid, "state": state, "attributes": {"friendly_name": name} if name else {}}


class AnswerTests(unittest.TestCase):
    def test_nothing_to_go_on(self):
        p = Presence(None); p.load([st("light.hall", "on")])
        self.assertIsNone(p.somebody); self.assertIsNone(p.since); self.assertIsNone(p.as_dict()["source"])

    def test_people_decide(self):
        p = Presence(None); p.load([st("person.a", "home", "Ada"), st("person.b", "not_home", "Ben")])
        self.assertTrue(p.somebody); self.assertEqual(p.as_dict()["source"], "people")
        self.assertTrue(p.on_state("person.a", st("person.a", "Work")))      # another zone counts as away
        self.assertFalse(p.somebody)
        self.assertFalse(p.on_state("person.b", st("person.b", "not_home")))  # no flip, no news

    def test_alarm_away_beats_a_lagging_phone(self):
        p = Presence(None); p.load([st("person.a", "home"), st("alarm_control_panel.ring", "armed_away")])
        self.assertFalse(p.somebody); self.assertEqual(p.as_dict()["source"], "alarm")
        p.on_state("alarm_control_panel.ring", st("alarm_control_panel.ring", "disarmed"))
        self.assertTrue(p.somebody)

    def test_alarm_alone_and_its_in_between_states(self):
        p = Presence(None); p.load([st("alarm_control_panel.ring", "disarmed")])
        self.assertTrue(p.somebody)
        self.assertFalse(p.on_state("alarm_control_panel.ring", st("alarm_control_panel.ring", "arming")))
        self.assertTrue(p.somebody)                                          # arming keeps the last answer
        self.assertTrue(p.on_state("alarm_control_panel.ring", st("alarm_control_panel.ring", "armed_away")))
        self.assertFalse(p.somebody)

    def test_since_only_moves_on_a_flip_and_seeds_from_the_log(self):
        p = Presence(None); p.load([st("person.a", "not_home")])
        t = p.since
        p.load([st("person.a", "not_home")])
        self.assertEqual(p.since, t)
        log = FakeLog(); log.add("presence", "home", "somebody", "nobody"); log.rows[0]["ts"] = 1000.0
        p.seed(log); self.assertEqual(p.since, 1000.0)
        log.rows[0]["new"] = "somebody"; p.since = t; p.seed(log); self.assertEqual(p.since, t)   # a stale answer is ignored

    def test_bad_for_is_refused(self):
        good, errors = rules.validate({"rules": [rule("x", room="home", when={"presence": "nobody", "for": -1}, then={"intent": "away"})]}, set())
        self.assertEqual(good, []); self.assertIn("for", errors[0])


class RuleTests(unittest.IsolatedAsyncioTestCase):
    async def settle(self):
        for _ in range(3): await asyncio.sleep(0)

    def leave(self, hub):
        """As the hub does it: the engine hears about presence only when the answer flips."""
        if hub.presence.on_state("person.a", st("person.a", "not_home")): hub.engine.on_presence()

    async def test_a_rule_with_no_wait_fires_on_the_flip(self):
        hub = FakeHub(); hub.presence.load([st("person.a", "home")])
        use(hub, rule("gone", room="home", when={"presence": "nobody"}, then={"intent": "away"}))
        self.leave(hub); await self.settle()
        ev = hub.log.of("intent")[0]
        self.assertEqual((ev["subject"], ev["new"], ev["detail"]["trigger"]), ("home", "away", {"presence": "nobody"}))
        self.leave(hub); await self.settle()                                  # no flip, no second firing
        self.assertEqual(len(hub.log.of("intent")), 1)

    async def test_a_rule_with_a_wait_fires_once_when_the_time_is_up(self):
        hub = FakeHub(); hub.presence.load([st("person.a", "home")])
        use(hub, rule("gone", room="home", when={"presence": "nobody", "for": 300}, then={"intent": "away"}))
        self.leave(hub); await self.settle()
        self.assertEqual(hub.log.of("intent"), [])                            # not yet
        t0 = datetime(2026, 9, 6, 20, 0, tzinfo=TZ)
        hub.engine.tick(t0); hub.engine.tick(t0 + timedelta(seconds=1)); await self.settle()
        self.assertEqual(hub.log.of("intent"), [])
        hub.presence.since = time.time() - 301
        hub.engine.tick(t0 + timedelta(seconds=2)); hub.engine.tick(t0 + timedelta(seconds=3)); await self.settle()
        self.assertEqual([r["new"] for r in hub.log.of("intent")], ["away"])
        self.assertEqual(hub.log.of("intent")[0]["detail"]["trigger"]["for"], 300)
        hub.presence.on_state("person.a", st("person.a", "home"))            # back, and no rule for that
        hub.engine.tick(t0 + timedelta(seconds=4)); await self.settle()
        self.assertEqual(len(hub.log.of("intent")), 1)

    async def test_presence_as_a_condition(self):
        hub = FakeHub(); hub.presence.load([st("person.a", "not_home")])
        use(hub, rule("intruder", when={"motion": "on"}, then={"intent": "guests"}, **{"if": [["presence", "is", "nobody"]]}))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.log.of("intent")[0]["detail"]["checked"], [["presence", "is", "nobody", "nobody", True]])

    async def test_dry_run(self):
        hub = FakeHub()
        use(hub, rule("gone", room="home", when={"presence": "nobody", "for": 300}, then={"intent": "away"}))
        self.assertEqual(hub.engine.dry_run("gone")["would"], "wait")         # nobody knows yet
        hub.presence.load([st("person.a", "home")])
        self.assertEqual((hub.engine.dry_run("gone")["would"], hub.engine.dry_run("gone")["next"]), ("wait", None))
        hub.presence.on_state("person.a", st("person.a", "not_home"))
        out = hub.engine.dry_run("gone")
        self.assertEqual(out["would"], "armed"); self.assertAlmostEqual(out["next"], hub.presence.since + 300)


if __name__ == "__main__":
    unittest.main()
