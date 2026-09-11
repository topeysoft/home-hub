"""Run from brain/: .venv/bin/python -m unittest tests.test_comfort -v"""
import time, unittest
from unittest import mock
from hub import comfort
from hub.model import Home, Room, Device


class FakeHA:
    def __init__(self): self.calls = []
    async def call(self, domain, service, eid, **data): self.calls.append((service, eid, data))


class FakeClock:
    """Stands in for the time module inside comfort, so a test can run ten hours in a moment."""
    def __init__(self, now=None): self.now = float(now if now is not None else time.time())
    def time(self): return self.now
    def advance(self, seconds): self.now += seconds; return self.now


class FakeLog:
    def __init__(self, clock=None):
        self.clock, self.rows, self.stamped = clock or FakeClock(), [], []
    def add(self, kind, subject, old=None, new=None, source="device", detail=None):
        self.rows.append((kind, subject, old, new, source, detail))
        self.stamped.append({"ts": self.clock.time(), "kind": kind, "subject": subject, "old": old, "new": new,
                             "source": source, "detail": detail})
    def recent(self, limit=100, subject=None, kinds=None):
        rows = [r for r in self.stamped if (subject is None or r["subject"] == subject) and (not kinds or r["kind"] in kinds)]
        return list(reversed(rows))[:limit]


class FakeSettings:
    def __init__(self): self.data = {}
    def get(self, k, default=None): return self.data.get(k, default)
    def set(self, **kw): self.data.update(kw)


class FakeHub:
    def __init__(self, unit="°F"):
        self.clock = FakeClock()
        self.temp_unit, self.ha, self.log, self.settings, self.sent = unit, FakeHA(), FakeLog(self.clock), FakeSettings(), []
        self.home = Home()
        self.home.rooms = {"living_room": Room("living_room", "Living Room"), "bedroom": Room("bedroom", "Bedroom")}
        self.t = Device("climate.nest", "Living Room", "living_room", "climate", "cool",
                        {"temperature": 74.0, "current_temperature": 74.0, "min_temp": 50, "max_temp": 90, "hvac_modes": ["heat", "cool", "off"]})
        self.s = Device("sensor.bedroom_temp", "Bedroom temperature", "bedroom", "sensor.temperature", "77.0")
        self.home.rooms["living_room"].devices.append(self.t); self.home.rooms["bedroom"].devices.append(self.s)
        self.home.devices = {self.t.id: self.t, self.s.id: self.s}
    def _broadcast(self, msg): self.sent.append(msg)


class MathTests(unittest.TestCase):
    def test_setpoint_offsets_by_the_difference(self):
        # want 72 in the bedroom; bedroom reads 77, thermostat reads 74: ask the thermostat for 69
        self.assertEqual(comfort.setpoint_for(72, 77, 74, 1, 50, 90, 5), 69)
        self.assertEqual(comfort.setpoint_for(21, 19.3, 20.1, 0.5, 5, 35, 2.5), 22.0)
        self.assertEqual(comfort.setpoint_for(72, 90, 74, 1, 60, 90, 50), 61)     # a step inside the thermostat's floor
        self.assertEqual(comfort.setpoint_for(72, 40, 74, 1, 50, 90, 50), 89)     # and its ceiling
        self.assertEqual(comfort.in_unit(24.7, "°C", "°F"), 76.46)
        self.assertEqual(round(comfort.in_unit(77, "°F", "°C"), 1), 25.0)
        self.assertEqual(comfort.in_unit(21, "°C", "°C"), 21)
        self.assertEqual(comfort.in_unit(72, None, "°F"), 72)

    def test_a_correction_never_lands_further_than_the_bound_from_the_number_asked_for(self):
        # The rooms are 18° apart, which is the sensor's fault or the thermostat's, not something to chase.
        self.assertEqual(comfort.setpoint_for(72, 90, 74, 1, 50, 90, 5), 67)
        self.assertEqual(comfort.setpoint_for(72, 40, 74, 1, 50, 90, 5), 77)
        self.assertEqual(comfort.setpoint_for(21, 30, 20, 0.5, 5, 35, 2.5), 18.5)
        # the thermostat's own limits still win where they are tighter than the bound
        self.assertEqual(comfort.setpoint_for(72, 90, 74, 1, 70, 90, 5), 71)

    def test_a_sensor_in_celsius_is_read_in_the_house_unit(self):
        hub = FakeHub(); c = comfort.Comfort(hub)
        hub.s.state, hub.s.attrs = "25.0", {"unit_of_measurement": "°C"}
        self.assertEqual(c._reading(hub.s), 77.0)


class LoopTests(unittest.IsolatedAsyncioTestCase):
    async def test_choosing_a_sensor_moves_the_thermostat_and_shows_on_the_card(self):
        hub = FakeHub(); c = comfort.Comfort(hub)
        await c.set_sensor(hub.t, "sensor.bedroom_temp")
        self.assertEqual(hub.ha.calls, [("set_temperature", "climate.nest", {"temperature": 71.0})])   # wanted 74 at a room 3° warmer
        self.assertEqual(hub.settings.data["comfort"], {"climate.nest": {"sensor": "sensor.bedroom_temp", "wanted": 74.0}})
        self.assertEqual((hub.t.attrs["sense_from"], hub.t.attrs["sense_name"], hub.t.attrs["sense_temp"], hub.t.attrs["wanted"]),
                         ("sensor.bedroom_temp", "Bedroom", 77.0, 74.0))
        self.assertEqual(hub.log.rows[-1][4], "comfort")

    async def test_wanting_a_number_and_settling(self):
        hub = FakeHub(); c = comfort.Comfort(hub)
        await c.set_sensor(hub.t, "sensor.bedroom_temp"); hub.ha.calls.clear()
        await c.want(hub.t, 70)
        self.assertEqual(hub.ha.calls, [("set_temperature", "climate.nest", {"temperature": 67.0})])
        hub.ha.calls.clear()
        hub.s.state = "76.0"; await c.on_state(hub.s)                 # too soon after the last move: wait for the room
        self.assertEqual(hub.ha.calls, [])
        c._acted["climate.nest"] = time.time() - 1000
        hub.t.attrs["temperature"] = 67.0; await c.on_state(hub.s)
        self.assertEqual(hub.ha.calls, [("set_temperature", "climate.nest", {"temperature": 68.0})])

    async def test_leaves_the_thermostat_alone_when_it_should(self):
        hub = FakeHub(); c = comfort.Comfort(hub)
        await c.set_sensor(hub.t, "sensor.bedroom_temp"); hub.ha.calls.clear(); c._acted.clear()
        hub.t.state = "heat_cool"; await c.check("climate.nest")        # auto keeps its own range
        hub.t.state = "off"; await c.check("climate.nest")
        hub.t.state = "cool"; hub.s.state = "unavailable"; await c.check("climate.nest")   # a dead sensor is not trusted
        hub.s.state = "77.0"; hub.t.attrs["temperature"] = 71.0; await c.check("climate.nest")   # already where it should be
        self.assertEqual(hub.ha.calls, [])
        await c.set_sensor(hub.t, None)
        self.assertNotIn("sense_from", hub.t.attrs)
        self.assertEqual(hub.settings.data["comfort"], {})

    async def test_rejects_things_that_are_not_temperature_sensors(self):
        hub = FakeHub(); c = comfort.Comfort(hub)
        with self.assertRaises(ValueError): await c.set_sensor(hub.t, "climate.nest")


class SafetyTests(unittest.IsolatedAsyncioTestCase):
    """What stops the loop running away with the equipment. A thermostat hangs where the air blows, so its own
    reading answers a correction long before a sensor two rooms away does; correcting on the raw difference
    between the two feeds back on itself, and the setpoint chases the reading it just moved."""

    async def test_the_setpoint_does_not_walk_away_from_the_number_asked_for(self):
        hub = FakeHub(); c = comfort.Comfort(hub); clock = hub.clock
        hub.t.attrs.update(temperature=72.0, current_temperature=74.0)
        hub.s.state, hub.s.seen = "76.0", clock.time()
        with mock.patch.object(comfort, "time", clock):
            await c.set_sensor(hub.t, "sensor.bedroom_temp")
            await c.want(hub.t, 72.0)
            moves = [clock.time()]
            for _ in range(600):                     # ten hours, taking a look once a minute
                clock.advance(60)
                # the house answers: the thermostat's own room follows the setpoint fast, the far room hardly at all
                cooling = hub.t.attrs["current_temperature"] > hub.t.attrs["temperature"]
                hub.t.attrs["current_temperature"] += -0.4 if cooling else 0.3
                hub.s.state = str(round(float(hub.s.state) + (-0.05 if cooling else 0.04), 2))
                hub.s.seen = clock.time()
                before = len(hub.ha.calls)
                await c.check("climate.nest")
                if len(hub.ha.calls) > before:
                    moves.append(clock.time())
                    hub.t.attrs["temperature"] = hub.ha.calls[-1][2]["temperature"]   # HA echoes the new setpoint back
                self.assertLessEqual(abs(hub.t.attrs["temperature"] - 72.0), comfort.MAX_OFFSET_F,
                                     f"the setpoint walked to {hub.t.attrs['temperature']} chasing its own correction")
        self.assertGreater(len(moves), 1, "the loop should still be correcting, just not running away")
        gaps = [b - a for a, b in zip(moves, moves[1:])]
        self.assertTrue(all(g >= comfort.SETTLE for g in gaps), f"a compressor was given {min(gaps)}s of rest")
        self.assertGreaterEqual(comfort.SETTLE, 300, "a compressor needs five minutes between starts")

    async def test_a_sensor_that_has_stopped_reporting_is_dropped(self):
        hub = FakeHub(); c = comfort.Comfort(hub); clock = hub.clock
        with mock.patch.object(comfort, "time", clock):
            await c.set_sensor(hub.t, "sensor.bedroom_temp")
            hub.ha.calls.clear()
            clock.advance(comfort.STALE + comfort.SETTLE)       # its battery died an hour ago; the number is a fossil
            hub.t.attrs["current_temperature"] = 80.0
            await c.check("climate.nest")
            self.assertEqual(hub.ha.calls, [], "a reading that old must not steer a thermostat")
            self.assertEqual(hub.log.rows[-1][3], "on its own sensor")
            await c.check("climate.nest")
            self.assertEqual(len([r for r in hub.log.rows if r[3] == "on its own sensor"]), 1, "said once, not every tick")
            hub.s.seen = clock.time()                            # it comes back
            await c.check("climate.nest")
            self.assertEqual(len(hub.ha.calls), 1)
            self.assertEqual(hub.log.rows[-1][3], str(77.0))

    async def test_a_restart_does_not_shorten_a_compressors_rest(self):
        hub = FakeHub(); c = comfort.Comfort(hub); clock = hub.clock
        with mock.patch.object(comfort, "time", clock):
            await c.set_sensor(hub.t, "sensor.bedroom_temp")
            self.assertEqual(len(hub.ha.calls), 1)
            clock.advance(60)
            again = comfort.Comfort(hub); again.load()           # the hub restarted a minute later
            hub.ha.calls.clear(); hub.t.attrs["current_temperature"] = 80.0
            await again.check("climate.nest")
            self.assertEqual(hub.ha.calls, [], "the wait is remembered across a restart, not started again")
            clock.advance(comfort.SETTLE)
            await again.check("climate.nest")
            self.assertEqual(len(hub.ha.calls), 1)
