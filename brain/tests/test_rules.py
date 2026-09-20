# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
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
    def last_user(self): return max((r["ts"] for r in self.rows if r["source"] == "user"), default=0.0)
    def recent(self, limit=100, subject=None, kinds=None):
        rows = [r for r in reversed(self.rows) if (not subject or r["subject"] == subject) and (not kinds or r["kind"] in kinds)]
        return rows[:limit]
    def of(self, kind): return [r for r in self.rows if r["kind"] == kind]


class FakeSettings:
    """settings.json without the file. hub_id is made the same way the real one makes it."""
    def __init__(self): self.data = {}
    def get(self, key, default=None): return self.data.get(key, default)
    def set(self, **updates): self.data.update(updates)
    def hub_id(self):
        if not self.data.get("hub_id"): self.data["hub_id"] = "0123456789abcdef"
        return self.data["hub_id"]


class FakeBridges:
    """Just enough of hub.bridge for anything that asks the house about its bridges."""
    def __init__(self, quiet=()): self.gone = list(quiet)
    def quiet(self): return self.gone


class FakeHA:
    """Records the calls a device outcome makes. `fails` names a device that raises, for the test that a
    broken outcome does not take the rest of the rule down with it."""
    def __init__(self): self.calls, self.fails = [], set()
    async def call(self, domain, service, entity_id, **data):
        if entity_id in self.fails: raise RuntimeError(f"{entity_id} is not answering")
        self.calls.append((domain, service, entity_id, data))


class FakeHub:
    def __init__(self):
        self.tz, self.location, self.driver, self.entry = TZ, LOC, "ready", []
        self.home, self.log, self.sent = Home(), FakeLog(), []
        self.settings = FakeSettings()
        self.home.rooms = {"hall": Room("hall", "Hallway"), "den": Room("den", "Den")}
        self.motion = Device("binary_sensor.hall_motion", "Hall motion", "hall", "motion", "off")
        self.light = Device("light.hall", "Hall light", "hall", "light", "off")
        self.home.rooms["hall"].devices += [self.motion, self.light]
        self.home.devices = {d.id: d for d in self.home.rooms["hall"].devices}
        self.presence = Presence(self)
        self.ha = FakeHA()
        self.engine = rules.Engine(self)
        # The real Hub always has one (api.Hub.__init__), and health.notes() asks it which bridges
        # have gone quiet. A house with none answers with an empty list, which is this.
        self.bridge = FakeBridges()
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


# A trigger that is not about any one room, so a rule naming several rooms acts on all of them at once.
FANOUT = {"device": "binary_sensor.hall_motion", "state": "on"}


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

    def test_a_wait_is_seconds_on_the_two_triggers_that_take_one(self):
        good, errors = rules.validate({"rules": [
            rule("held", when={"device": "lock.front", "state": "unlocked", "for": 10800}, then={"notify": "still unlocked"}),
            rule("gone", room="home", when={"presence": "nobody", "for": 600}, then={"intent": "away"}),
            rule("typo", when={"device": "lock.front", "state": "unlocked", "for": True}, then={"notify": "no"}),
            rule("backwards", when={"device": "lock.front", "state": "unlocked", "for": -1}, then={"notify": "no"}),
        ]}, {"hall"})
        self.assertEqual([r["id"] for r in good], ["held", "gone"])
        # "for": true is a typo, not three seconds -- Python would otherwise read the bool as an int
        self.assertEqual(len(errors), 2)
        self.assertTrue(all("seconds" in e for e in errors))

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

    async def test_a_hand_beats_a_rule_that_names_a_light_directly(self):
        """The hold used to guard only an intent outcome, so a rule naming a device turned it straight back
        on at the next flicker of motion, seconds after somebody had switched it off by hand."""
        hub = FakeHub()
        use(hub, rule("lamp-on", then={"device": "light.hall", "action": "on"}))
        hub.home.rooms["hall"].hold_until = time.time() + 60
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.ha.calls, [])
        ev = hub.log.of("held")[0]
        self.assertEqual((ev["subject"], ev["new"]), ("light.hall", "on"))     # the light, not the room

    async def test_the_hold_that_counts_is_the_device_s_room_not_the_rule_s(self):
        """A rule filed under the hall may act on a lamp in the den. It is the den's hand that governs it."""
        hub = FakeHub()
        den_lamp = Device("light.den", "Den lamp", "den", "light", "off")
        hub.home.rooms["den"].devices.append(den_lamp); hub.home.devices[den_lamp.id] = den_lamp
        use(hub, rule("den-lamp", room="hall", then={"device": "light.den", "action": "on"}))
        hub.home.rooms["hall"].hold_until = time.time() + 60        # the rule's own room: not what matters
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.ha.calls, [("light", "turn_on", "light.den", {})])
        hub.ha.calls.clear()
        hub.home.rooms["den"].hold_until = time.time() + 60         # the device's room: this one does
        hub.motion.state = "off"; hub.engine.on_state(hub.motion, "on")
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.ha.calls, [])

    async def test_a_notify_is_never_held(self):
        """It changes no device, so there is nothing for a hand to disagree with."""
        hub = FakeHub()
        use(hub, rule("say", then={"notify": "Someone is in the hall"}))
        hub.home.rooms["hall"].hold_until = time.time() + 60
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(len(hub.log.of("notify")), 1)

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


    async def unlocked(self, hub):
        """A door that has just been unlocked, and the rule that minds how long it stays that way."""
        lock = Device("lock.front", "Front door", "hall", "lock", "locked")
        hub.home.rooms["hall"].devices.append(lock); hub.home.devices[lock.id] = lock
        use(hub, rule("left-unlocked", when={"device": lock.id, "state": "unlocked", "for": 10800},
                      then={"notify": "The front door has been unlocked for three hours."}))
        lock.state, lock.since = "unlocked", time.time()
        hub.engine.on_state(lock, "locked"); await self.settle()
        return lock

    async def test_a_device_that_waits_arms_rather_than_fires(self):
        hub = FakeHub()
        lock = await self.unlocked(hub)
        # the moment it unlocked is not the moment: "unlocked" and "unlocked for three hours" are
        # different rules, and the second one must not go off at the click of the first
        self.assertEqual(hub.log.of("notify"), [])
        t = datetime(2026, 9, 6, 12, 0, tzinfo=TZ)
        hub.engine.tick(t); hub.engine.tick(t + timedelta(seconds=1)); await self.settle()
        self.assertEqual(hub.log.of("notify"), [])
        lock.since = time.time() - 10800
        for s in range(2, 6): hub.engine.tick(t + timedelta(seconds=s))
        await self.settle()
        self.assertEqual(len(hub.log.of("notify")), 1)          # once, and not once a second after that
        self.assertEqual(hub.log.of("notify")[0]["detail"]["trigger"]["for"], 10800)

    async def test_locking_it_and_leaving_it_again_is_a_new_wait(self):
        hub = FakeHub()
        lock = await self.unlocked(hub)
        t = datetime(2026, 9, 6, 12, 0, tzinfo=TZ)
        lock.since = time.time() - 10800
        hub.engine.tick(t); hub.engine.tick(t + timedelta(seconds=1)); await self.settle()
        self.assertEqual(len(hub.log.of("notify")), 1)
        lock.state, lock.since = "locked", time.time()
        hub.engine.on_state(lock, "unlocked"); await self.settle()
        for s in range(2, 4): hub.engine.tick(t + timedelta(seconds=s))
        await self.settle()
        self.assertEqual(len(hub.log.of("notify")), 1)          # locked: nothing to say
        lock.state, lock.since = "unlocked", time.time() - 10800
        for s in range(4, 7): hub.engine.tick(t + timedelta(seconds=s))
        await self.settle()
        self.assertEqual(len(hub.log.of("notify")), 2)          # a second spell is a second sentence

    async def test_dry_run_knows_a_device_is_waiting(self):
        hub = FakeHub()
        lock = await self.unlocked(hub)
        lock.since = 1000.0
        out = hub.engine.dry_run("left-unlocked")
        self.assertEqual((out["would"], out["next"]), ("armed", 1000.0 + 10800))
        lock.state = "locked"                                   # nothing to wait for while it is shut
        self.assertEqual(hub.engine.dry_run("left-unlocked")["next"], None)



class TimerLatchTests(unittest.IsolatedAsyncioTestCase):
    """A timer trigger fires once per spell. What "once" is spent on is the subtle part, and `quiet` is what
    made it matter: a rule whose conditions were not ready yet must keep its turn."""

    async def settle(self):
        for _ in range(3): await asyncio.sleep(0)

    async def test_conditions_not_ready_yet_keeps_its_turn(self):
        hub = FakeHub()
        use(hub, rule("quiet-den", when={"idle": 600}, then={"intent": "empty"},
                      **{"if": [["device", "light.hall", "is", "off"]]}))
        hub.home.rooms["hall"].motion_at = time.time() - 900
        hub.light.state = "on"                                   # not ready
        t0 = datetime(2026, 9, 6, 22, 0, tzinfo=TZ)
        hub.engine.tick(t0); hub.engine.tick(t0 + timedelta(seconds=1)); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "unknown")
        hub.light.state = "off"                                  # ready now, same motion spell
        hub.engine.tick(t0 + timedelta(seconds=2)); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "empty")

    async def test_a_held_room_spends_the_turn_and_is_not_asked_again(self):
        """The other half. A hand on the room is a real answer, so asking every second would write the same
        held line to the log for as long as the hold lasts."""
        hub = FakeHub()
        use(hub, rule("quiet-den", when={"idle": 600}, then={"intent": "empty"}))
        hub.home.rooms["hall"].motion_at = time.time() - 900
        hub.home.rooms["hall"].hold_until = time.time() + 600
        t0 = datetime(2026, 9, 6, 22, 0, tzinfo=TZ)
        for n in range(1, 6): hub.engine.tick(t0 + timedelta(seconds=n))
        await self.settle()
        self.assertEqual(len(hub.log.of("held")), 1)


class QuietTests(unittest.IsolatedAsyncioTestCase):
    """`quiet`: how long every room named has been still. The condition a whole-floor off needs and the one
    thing the vocabulary could not say -- `for` lives on triggers, so a list of ["device", ..., "not", "on"]
    conditions could only ever describe the instant, never the duration."""

    async def settle(self):
        for _ in range(3): await asyncio.sleep(0)

    def test_it_validates_and_a_bad_one_does_not(self):
        rooms = {"hall", "den"}
        good, errors = rules.validate({"rules": [
            rule("own-room", **{"if": [["quiet", "above", 600]]}),
            rule("one-room", **{"if": [["quiet", "den", "above", 600]]}),
            rule("both", **{"if": [["quiet", ["hall", "den"], "above", 1200]]}),
            rule("attic", **{"if": [["quiet", ["hall", "attic"], "above", 600]]}),
            rule("wrong-op", **{"if": [["quiet", "is", 600]]}),
            rule("not-seconds", **{"if": [["quiet", "above", "ages"]]}),
            rule("negative", **{"if": [["quiet", "above", -1]]}),
        ]}, rooms)
        self.assertEqual([r["id"] for r in good], ["own-room", "one-room", "both"])
        self.assertIn("unknown room 'attic'", errors[0])
        self.assertIn("above or below", errors[1])
        self.assertIn("quiet is seconds", errors[2])
        self.assertIn("quiet is seconds", errors[3])

    def test_the_least_quiet_room_governs(self):
        hub = FakeHub()
        use(hub, rule("upstairs", **{"if": [["quiet", ["hall", "den"], "above", 600]]}))
        now = time.time()
        hub.home.rooms["hall"].motion_at = now - 3000
        hub.home.rooms["den"].motion_at = now - 60          # somebody is still in the den
        out = hub.engine.dry_run("upstairs")
        self.assertAlmostEqual(out["checked"][0][-2], 60, delta=2)
        self.assertFalse(out["checked"][0][-1])
        hub.home.rooms["den"].motion_at = now - 900         # now both have been still a while
        self.assertTrue(hub.engine.dry_run("upstairs")["checked"][0][-1])

    def test_with_no_rooms_named_it_means_the_rule_s_own(self):
        hub = FakeHub()
        use(hub, rule("here", **{"if": [["quiet", "above", 600]]}))
        hub.home.rooms["hall"].motion_at = time.time() - 900
        hub.home.rooms["den"].motion_at = time.time() - 1     # a busy den is not this rule's business
        self.assertTrue(hub.engine.dry_run("here")["checked"][0][-1])

    def test_a_room_the_house_cannot_speak_for_fails_closed(self):
        """No motion sensor, or none seen since the hub came up. Unknown never passes, so the failure lands
        on leaving lights ON rather than putting a house dark around somebody it could not see."""
        hub = FakeHub()
        use(hub, rule("upstairs", **{"if": [["quiet", ["hall", "den"], "above", 600]]}))
        hub.home.rooms["hall"].motion_at = time.time() - 3000
        hub.home.rooms["den"].motion_at = None
        out = hub.engine.dry_run("upstairs")
        self.assertIsNone(out["checked"][0][-2])
        self.assertFalse(out["checked"][0][-1])
        self.assertEqual(out["would"], "wait")

    async def test_a_whole_floor_goes_off_only_when_every_room_is_still(self):
        hub = FakeHub()
        use(hub, rule("upstairs-off", room=["hall", "den"], when={"idle": 600},
                      then={"intent": "empty"}, **{"if": [["quiet", ["hall", "den"], "above", 600]]}))
        now, t0 = time.time(), datetime(2026, 9, 6, 22, 0, tzinfo=TZ)
        hub.home.rooms["hall"].motion_at = now - 900
        hub.home.rooms["den"].motion_at = now - 30           # still someone in the den
        hub.engine.tick(t0); hub.engine.tick(t0 + timedelta(seconds=1)); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "unknown")
        hub.home.rooms["den"].motion_at = now - 900          # the den has gone still too
        hub.engine.tick(t0 + timedelta(seconds=2)); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "empty")
        self.assertEqual(hub.home.rooms["den"].intent, "empty")


class SeveralRoomsTests(unittest.IsolatedAsyncioTestCase):
    """`room` as a list: one rule, several rooms. The alternative is three copies of a rule that drift apart,
    which is what this replaces."""

    async def settle(self):
        for _ in range(3): await asyncio.sleep(0)

    def test_a_list_of_rooms_validates_and_a_bad_one_does_not(self):
        rooms = {"hall", "den"}
        good, errors = rules.validate({"rules": [
            rule("both", room=["hall", "den"]),
            rule("nowhere", room=["hall", "attic"]),
            rule("empty", room=[]),
            rule("twice", room=["hall", "hall"]),
            rule("nested", room=["hall", "home"]),
            rule("entry-nested", room=["hall", "entry"]),
        ]}, rooms)
        self.assertEqual([r["id"] for r in good], ["both"])
        self.assertEqual(len(errors), 5)
        self.assertIn("unknown room 'attic'", errors[0])
        self.assertIn("cannot be empty", errors[1])
        self.assertIn("same room twice", errors[2])
        self.assertIn("'home' cannot go in a list", errors[3])
        self.assertIn("'entry' cannot go in a list", errors[4])

    def test_a_trigger_that_needs_a_room_still_refuses_home(self):
        _, errors = rules.validate({"rules": [rule("bad", room="home", when={"motion": "on"})]}, {"hall"})
        self.assertIn("motion needs a room, not home", errors[0])

    async def test_one_rule_acts_on_every_room_it_names(self):
        hub = FakeHub()
        use(hub, rule("path", room=["hall", "den"], when={"device": "binary_sensor.hall_motion", "state": "on"},
                      then={"intent": "occupied"}))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "occupied")
        self.assertEqual(hub.home.rooms["den"].intent, "occupied")

    async def test_a_room_scoped_trigger_means_each_room_on_its_own_signal(self):
        """The distinction a list has to be read with. `motion`, `contact` and `idle` are about the room they
        happen in, so ["hall", "den"] is two independent behaviours -- hall motion lights the hall -- exactly
        as "entry" already means. Only a room-independent trigger (device, time, sun, presence, intent) fans
        one signal out across the rooms. Getting this backwards is the obvious way to misread the feature."""
        hub = FakeHub()
        den_motion = Device("binary_sensor.den_motion", "Den motion", "den", "motion", "off")
        hub.home.rooms["den"].devices.append(den_motion); hub.home.devices[den_motion.id] = den_motion
        use(hub, rule("walk-by", room=["hall", "den"], when={"motion": "on"}, then={"intent": "occupied"}))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "occupied")
        self.assertEqual(hub.home.rooms["den"].intent, "unknown")       # the den has its own sensor to wait for
        den_motion.state = "on"; hub.engine.on_state(den_motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["den"].intent, "occupied")

    async def test_shadowed_in_one_room_still_acts_in_the_other(self):
        """`taken` is per room, so a rule losing the hall to an earlier one keeps the den. The alternative --
        dropping the whole rule -- would make a multi-room rule silently all-or-nothing on a collision."""
        hub = FakeHub()
        use(hub, rule("hall-first", room="hall", when=FANOUT, then={"intent": "guests"}),
                 rule("path", room=["hall", "den"], when=FANOUT, then={"intent": "occupied"}))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "guests")
        self.assertEqual(hub.home.rooms["den"].intent, "occupied")
        self.assertEqual(hub.log.of("shadowed")[0]["subject"], "hall")

    async def test_a_hand_in_one_room_does_not_hold_the_other(self):
        hub = FakeHub()
        use(hub, rule("path", room=["hall", "den"], when=FANOUT, then={"intent": "occupied"}))
        hub.home.rooms["hall"].hold_until = time.time() + 60
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "unknown")
        self.assertEqual(hub.home.rooms["den"].intent, "occupied")

    def test_dry_run_speaks_for_the_first_room(self):
        hub = FakeHub()
        use(hub, rule("path", room=["den", "hall"], then={"intent": "occupied"}))
        self.assertEqual(hub.engine.dry_run("path")["rule"]["room"], "den")


class SeveralOutcomesTests(unittest.IsolatedAsyncioTestCase):
    """`then` as a list: one rule, several things done in the order they are written."""

    async def settle(self):
        for _ in range(4): await asyncio.sleep(0)

    def test_a_list_of_outcomes_validates_and_a_bad_one_does_not(self):
        good, errors = rules.validate({"rules": [
            rule("many", then=[{"intent": "occupied"}, {"device": "light.hall", "action": "on"}, {"notify": "hello"}]),
            {**rule("none"), "then": []},                  # `then or default` in rule() would hide an empty list
            rule("two-in-one", then=[{"intent": "occupied", "notify": "both"}]),
            rule("not-an-object", then=["occupied"]),
            rule("no-action", then=[{"device": "light.hall"}]),
        ]}, {"hall"})
        self.assertEqual([r["id"] for r in good], ["many"])
        self.assertIn("cannot be empty", errors[0])
        self.assertIn("exactly one of", errors[1])
        self.assertIn("an outcome is an object", errors[2])
        self.assertIn("needs an action", errors[3])

    async def test_every_outcome_runs_in_order(self):
        hub = FakeHub()
        use(hub, rule("arrive", then=[{"intent": "occupied"},
                                      {"device": "light.hall", "action": "off"},
                                      {"notify": "You're home"}]))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "occupied")
        self.assertEqual(hub.ha.calls, [("light", "turn_off", "light.hall", {})])
        self.assertEqual(hub.log.of("notify")[0]["new"], "You're home")
        self.assertEqual([r["kind"] for r in hub.log.rows], ["intent", "action", "notify"])

    async def test_one_broken_outcome_does_not_lose_the_others(self):
        hub = FakeHub()
        hub.ha.fails.add("light.hall")
        use(hub, rule("arrive", then=[{"device": "light.hall", "action": "on"}, {"notify": "still said"}]))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(len(hub.log.of("failed")), 1)
        self.assertEqual(hub.log.of("notify")[0]["new"], "still said")

    async def test_a_held_room_stops_the_whole_rule_not_just_its_intent(self):
        """An outcome list is one thought. If a hand has held the room, a rule that would set it must not
        still go and turn the lights on -- that is the half-applied state a hold exists to prevent."""
        hub = FakeHub()
        use(hub, rule("arrive", then=[{"intent": "occupied"}, {"device": "light.hall", "action": "on"}]))
        hub.home.rooms["hall"].hold_until = time.time() + 60
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "unknown")
        self.assertEqual(hub.ha.calls, [])
        self.assertEqual(hub.log.of("held")[0]["detail"]["rule"], "arrive")

    async def test_an_absolute_outcome_runs_once_however_many_rooms(self):
        """Only `intent` varies by room. A device outcome names an absolute id and a notify is one sentence,
        so running them once per named room would turn a light on twice and say the same thing twice."""
        hub = FakeHub()
        use(hub, rule("path", room=["hall", "den"], when=FANOUT,
                      then=[{"intent": "occupied"}, {"device": "light.hall", "action": "on"}, {"notify": "Mind the step"}]))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "occupied")     # the intent reaches both rooms
        self.assertEqual(hub.home.rooms["den"].intent, "occupied")
        self.assertEqual(hub.ha.calls, [("light", "turn_on", "light.hall", {})])
        self.assertEqual(len(hub.log.of("notify")), 1)

    async def test_a_timer_trigger_says_it_once_across_all_its_rooms(self):
        """`tick` evaluates a multi-room timer rule one room at a time -- each room carries its own idle
        clock -- so the once-per-rule guard has to span the whole wake-up, not one batch. Without that, a
        rule saying "everything off upstairs, and tell me" tells you once per room."""
        hub = FakeHub()
        use(hub, rule("upstairs-off", room=["hall", "den"], when={"idle": 600},
                      then=[{"intent": "empty"}, {"notify": "Upstairs is off"}]))
        now, t0 = time.time(), datetime(2026, 9, 6, 23, 0, tzinfo=TZ)
        hub.home.rooms["hall"].motion_at = hub.home.rooms["den"].motion_at = now - 900
        hub.engine.tick(t0); hub.engine.tick(t0 + timedelta(seconds=1)); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "empty")
        self.assertEqual(hub.home.rooms["den"].intent, "empty")
        self.assertEqual(len(hub.log.of("notify")), 1)

    async def test_a_rule_with_nothing_left_to_do_in_a_room_is_not_fired(self):
        """All-absolute outcomes over two rooms: the first room does the work, the second has nothing."""
        hub = FakeHub()
        use(hub, rule("ping", room=["hall", "den"], when=FANOUT, then=[{"notify": "once"}]))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual([e["subject"] for e in hub.log.of("notify")], ["hall"])

    def test_dry_run_knows_a_list_can_be_held(self):
        hub = FakeHub()
        use(hub, rule("arrive", then=[{"notify": "hi"}, {"intent": "occupied"}]))
        hub.home.rooms["hall"].hold_until = time.time() + 60
        self.assertEqual(hub.engine.dry_run("arrive")["would"], "held")



if __name__ == "__main__":
    unittest.main()
