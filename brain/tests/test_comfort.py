"""Run from brain/: .venv/bin/python -m unittest tests.test_comfort -v"""
import time, unittest
from hub import comfort
from hub.model import Home, Room, Device


class FakeHA:
    def __init__(self): self.calls = []
    async def call(self, domain, service, eid, **data): self.calls.append((service, eid, data))


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, kind, subject, old=None, new=None, source="device", detail=None): self.rows.append((kind, subject, old, new, source, detail))


class FakeSettings:
    def __init__(self): self.data = {}
    def get(self, k, default=None): return self.data.get(k, default)
    def set(self, **kw): self.data.update(kw)


class FakeHub:
    def __init__(self, unit="°F"):
        self.temp_unit, self.ha, self.log, self.settings, self.sent = unit, FakeHA(), FakeLog(), FakeSettings(), []
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
        self.assertEqual(comfort.setpoint_for(72, 77, 74, 1, 50, 90), 69)
        self.assertEqual(comfort.setpoint_for(21, 19.3, 20.1, 0.5, 5, 35), 22.0)
        self.assertEqual(comfort.setpoint_for(72, 90, 74, 1, 60, 90), 61)     # a step inside the thermostat's floor
        self.assertEqual(comfort.setpoint_for(72, 40, 74, 1, 50, 90), 89)     # and its ceiling
        self.assertEqual(comfort.in_unit(24.7, "°C", "°F"), 76.46)
        self.assertEqual(round(comfort.in_unit(77, "°F", "°C"), 1), 25.0)
        self.assertEqual(comfort.in_unit(21, "°C", "°C"), 21)
        self.assertEqual(comfort.in_unit(72, None, "°F"), 72)

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
