"""Run from brain/: .venv/bin/python -m unittest -v"""
import asyncio, time, unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from hub import rules, sun
from hub.intents import RoomState
from hub.model import Home, Room, Device
from hub.presence import Presence

TZ = ZoneInfo("America/Chicago")
LOC = {"name": "Home", "lat": 41.88, "lon": -87.63}


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, kind, subject, old=None, new=None, source="device", detail=None):
        self.rows.append({"ts": time.time(), "kind": kind, "subject": subject, "old": old, "new": new, "source": source, "detail": detail})
    def last_by_subject(self, kind, new): return {}
    def recent(self, limit=100, subject=None, kinds=None):
        rows = [r for r in reversed(self.rows) if (not subject or r["subject"] == subject) and (not kinds or r["kind"] in kinds)]
        return rows[:limit]
    def of(self, kind): return [r for r in self.rows if r["kind"] == kind]


class FakeHub:
    def __init__(self):
        self.tz, self.location, self.driver = TZ, LOC, "ready"
        self.home, self.log, self.sent = Home(), FakeLog(), []
        self.home.rooms = {"hall": Room("hall", "Hallway"), "den": Room("den", "Den")}
        self.motion = Device("binary_sensor.hall_motion", "Hall motion", "hall", "motion", "off")
        self.light = Device("light.hall", "Hall light", "hall", "light", "off")
        self.home.rooms["hall"].devices += [self.motion, self.light]
        self.home.devices = {d.id: d for d in self.home.rooms["hall"].devices}
        self.presence = Presence(self)
        self.engine = rules.Engine(self)
    def _broadcast(self, msg): self.sent.append(msg)
    async def set_intent(self, room, state, source="user", detail=None, depth=0):
        room.intent = state.value; room.set_by = f"rule:{detail['rule']}"
        self.log.add("intent", room.id, None, state.value, source=source, detail=detail)
        self.engine.on_intent(room.id, state, depth)
    async def set_home_intent(self, state, source="user", detail=None, depth=0):
        self.home.intent = state.value
        self.log.add("intent", "home", None, state.value, source=source, detail=detail)
        self.engine.on_intent("home", state, depth)


def use(hub, *rs):
    hub.engine.rules, hub.engine.errors = rules.validate({"rules": list(rs)}, set(hub.home.rooms))
    hub.engine._mtime = -1                      # pretend the file is loaded so load() does not read disk
    hub.engine.load = lambda force=False: None
    assert not hub.engine.errors, hub.engine.errors


def rule(id, room="hall", when=None, then=None, **kw):
    return {"id": id, "room": room, "when": when or {"motion": "on"}, "then": then or {"intent": "occupied"}, **kw}


class SunTests(unittest.TestCase):
    def test_noon_is_up_and_midnight_is_down(self):
        noon = datetime(2026, 9, 6, 12, 30, tzinfo=TZ)
        self.assertGreater(sun.elevation(noon, LOC["lat"], LOC["lon"]), 45)
        self.assertLess(sun.elevation(noon + timedelta(hours=12), LOC["lat"], LOC["lon"]), -30)

    def test_september_crossings_in_chicago(self):
        rise, set_ = sun.crossings(datetime(2026, 9, 6, tzinfo=TZ), LOC["lat"], LOC["lon"])
        self.assertEqual((rise.hour, set_.hour), (6, 19))          # about 6:20 and 19:15 CDT


class ValidateTests(unittest.TestCase):
    def test_good_and_bad_rows(self):
        good, errors = rules.validate({"rules": [
            rule("ok"),
            rule("ok2", when={"idle": 60}, then={"intent": "empty"}),
            rule("no-room", room="attic"),
            rule("two-triggers", when={"motion": "on", "idle": 5}),
            rule("bad-state", then={"intent": "party"}),
            rule("home-motion", room="home"),
            rule("ok3", room="home", when={"time": "22:30"}, then={"intent": "asleep"}),
            {"id": "ok", "room": "hall", "when": {"motion": "on"}, "then": {"intent": "occupied"}},
        ]}, {"hall"})
        self.assertEqual([r["id"] for r in good], ["ok", "ok2", "ok3"])
        self.assertEqual(len(errors), 5)
        self.assertIn("duplicate", errors[-1])

    def test_compare(self):
        self.assertTrue(rules._compare("between", "23:10", ["22:00", "06:00"]))
        self.assertFalse(rules._compare("between", "12:00", ["22:00", "06:00"]))
        self.assertTrue(rules._compare("below", -3.2, 0))
        self.assertTrue(rules._compare("in", "sat", ["sat", "sun"]))
        self.assertFalse(rules._compare("above", "dark", 5))


class EngineTests(unittest.IsolatedAsyncioTestCase):
    async def settle(self):
        for _ in range(3): await asyncio.sleep(0)

    async def test_motion_sets_the_room_and_says_why(self):
        hub = FakeHub()
        use(hub, rule("hall-any", when={"motion": "on"}, then={"intent": "occupied"}, **{"if": [["intent", "not", "asleep"]]}))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "occupied")
        ev = hub.log.of("intent")[0]
        self.assertEqual(ev["source"], "rule")
        self.assertEqual(ev["detail"]["rule"], "hall-any")
        self.assertEqual(ev["detail"]["checked"], [["intent", "not", "asleep", "unknown", True]])
        self.assertIsNotNone(hub.home.rooms["hall"].motion_at)

    async def test_conditions_fail_quietly(self):
        hub = FakeHub()
        use(hub, rule("night-only", **{"if": [["sun", "below", -90]]}))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "unknown")
        self.assertEqual(hub.log.rows, [])

    async def test_a_hand_beats_a_rule(self):
        hub = FakeHub()
        use(hub, rule("hall-any"))
        hub.home.rooms["hall"].hold_until = time.time() + 60; hub.home.rooms["hall"].set_by = "user"
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "unknown")
        self.assertEqual(hub.log.of("held")[0]["detail"]["rule"], "hall-any")

    async def test_first_rule_wins_the_room(self):
        hub = FakeHub()
        use(hub, rule("first", then={"intent": "occupied"}), rule("second", then={"intent": "guests"}))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "occupied")
        self.assertEqual(hub.log.of("shadowed")[0]["detail"]["rule"], "second")

    async def test_idle_fires_once_per_motion(self):
        hub = FakeHub()
        use(hub, rule("quiet", when={"idle": 600}, then={"intent": "empty"}))
        room = hub.home.rooms["hall"]; room.motion_at = time.time() - 601
        t0 = datetime(2026, 9, 6, 20, 0, tzinfo=TZ)
        hub.engine.tick(t0); hub.engine.tick(t0 + timedelta(seconds=1)); await self.settle()
        hub.engine.tick(t0 + timedelta(seconds=2)); await self.settle()
        self.assertEqual([r["new"] for r in hub.log.of("intent")], ["empty"])
        room.motion_at = time.time() - 700
        hub.engine.tick(t0 + timedelta(seconds=3)); await self.settle()
        self.assertEqual(len(hub.log.of("intent")), 2)

    async def test_time_and_sun_fire_exactly_once(self):
        hub = FakeHub()
        use(hub, rule("bedtime", room="home", when={"time": "22:30"}, then={"intent": "asleep"}),
                 rule("dusk", room="hall", when={"sun": "set", "offset": 600}, then={"intent": "occupied"}))
        t = datetime(2026, 9, 6, 22, 29, 59, tzinfo=TZ)
        for s in range(3): hub.engine.tick(t + timedelta(seconds=s))
        await self.settle()
        self.assertEqual([r["subject"] for r in hub.log.of("intent")], ["home"])
        _, sunset = sun.crossings(datetime(2026, 9, 6, tzinfo=TZ), LOC["lat"], LOC["lon"])
        t = sunset + timedelta(seconds=600) - timedelta(seconds=1)
        hub.engine._last_tick = t - timedelta(seconds=1)
        hub.engine.tick(t); hub.engine.tick(t + timedelta(seconds=2)); await self.settle()
        self.assertEqual(hub.log.of("intent")[-1]["detail"]["trigger"]["sun"], "set")

    async def test_clock_jumps_do_not_replay_the_day(self):
        hub = FakeHub()
        use(hub, rule("bedtime", room="home", when={"time": "22:30"}, then={"intent": "asleep"}))
        hub.engine.tick(datetime(2026, 9, 6, 8, 0, tzinfo=TZ))
        hub.engine.tick(datetime(2026, 9, 6, 23, 0, tzinfo=TZ)); await self.settle()
        self.assertEqual(hub.log.rows, [])

    async def test_intent_rules_run_once_and_never_chain(self):
        hub = FakeHub()
        use(hub, rule("follow", room="den", when={"intent": "asleep", "in": "hall"}, then={"intent": "asleep"}),
                 rule("loop", room="hall", when={"intent": "asleep", "in": "den"}, then={"intent": "guests"}))
        await hub.set_intent(hub.home.rooms["hall"], RoomState.asleep, source="user", detail={"rule": None})
        await self.settle(); await self.settle()
        self.assertEqual(hub.home.rooms["den"].intent, "asleep")
        self.assertEqual(hub.home.rooms["hall"].intent, "asleep")   # "loop" never ran

    async def test_dry_run_reports_without_acting(self):
        hub = FakeHub()
        use(hub, rule("night", **{"if": [["sun", "below", 0], ["weekday", "in", ["sat", "sun"]]]}))
        out = hub.engine.dry_run("night")
        self.assertIn(out["would"], ("fire", "wait"))
        self.assertEqual([c[0] for c in out["checked"]], ["sun", "weekday"])
        self.assertEqual(hub.log.rows, [])
        self.assertIsNone(hub.engine.dry_run("nope"))

    async def test_dry_run_knows_timers(self):
        hub = FakeHub()
        use(hub, rule("quiet", when={"idle": 600}, then={"intent": "empty"}),
                 rule("bedtime", room="home", when={"time": "22:30"}, then={"intent": "asleep"}),
                 rule("dusk", when={"sun": "set"}), rule("off", enabled=False))
        self.assertEqual((hub.engine.dry_run("quiet")["would"], hub.engine.dry_run("quiet")["next"]), ("wait", None))
        hub.home.rooms["hall"].motion_at = 1000.0
        self.assertEqual((hub.engine.dry_run("quiet")["would"], hub.engine.dry_run("quiet")["next"]), ("armed", 1600.0))
        bed = hub.engine.dry_run("bedtime")
        self.assertEqual(bed["would"], "armed"); self.assertGreater(bed["next"], time.time())
        self.assertEqual(hub.engine.dry_run("dusk")["would"], "armed")
        self.assertEqual(hub.engine.dry_run("off")["would"], "off")


if __name__ == "__main__":
    unittest.main()
