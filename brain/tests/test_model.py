"""Run from brain/: .venv/bin/python -m unittest tests.test_model -v"""
import time, unittest
from hub.model import Home


def snap(state="cool", fan="off"):
    areas = [{"area_id": "living_room", "name": "Living Room"}]
    entities = [{"entity_id": "climate.nest", "device_id": "d1"}]
    devices = [{"id": "d1", "area_id": "living_room"}]
    states = [{"entity_id": "climate.nest", "state": state, "attributes": {"friendly_name": "Living Room", "temperature": 76, "current_temperature": 77, "hvac_modes": ["heat", "cool", "off"], "fan_mode": fan, "fan_modes": ["on", "off"], "hvac_action": "cooling", "supported_features": 411}}]
    return areas, devices, entities, states


class ExtrasTests(unittest.TestCase):
    def test_a_fan_timer_rides_along_with_the_attrs(self):
        home = Home().build(*snap())
        d = home.devices["climate.nest"]
        self.assertEqual(d.capability, "climate")
        self.assertEqual((d.attrs["fan_mode"], d.attrs["fan_modes"], d.attrs["hvac_action"]), ("off", ["on", "off"], "cooling"))
        self.assertNotIn("supported_features", d.attrs)
        home.extras["climate.nest"] = {"fan_until": 123.0}
        home.apply_state("climate.nest", snap(fan="on")[3][0])
        self.assertEqual((d.attrs["fan_mode"], d.attrs["fan_until"]), ("on", 123.0))
        home.build(*snap(fan="on"))                                  # a rebuild keeps what the brain knows
        self.assertEqual(home.devices["climate.nest"].attrs["fan_until"], 123.0)
        home.extras["climate.nest"] = {"fan_until": time.time() + 600}
        home.apply_state("climate.nest", snap(fan="off")[3][0])     # the thermostat has not caught up yet
        self.assertEqual(home.devices["climate.nest"].attrs["fan_mode"], "on")
        home.extras.pop("climate.nest")
        d = home.devices["climate.nest"]                             # the rebuild made a new device object
        home.apply_state("climate.nest", snap()[3][0])
        self.assertNotIn("fan_until", d.attrs)
