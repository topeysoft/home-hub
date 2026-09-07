"""Run from brain/: .venv/bin/python -m unittest tests.test_model -v"""
import time, unittest
from hub.model import Home


def snap(state="cool", fan="off"):
    areas = [{"area_id": "living_room", "name": "Living Room"}]
    entities = [{"entity_id": "climate.nest", "device_id": "d1"}]
    devices = [{"id": "d1", "area_id": "living_room"}]
    states = [{"entity_id": "climate.nest", "state": state, "attributes": {"friendly_name": "Living Room", "temperature": 76, "current_temperature": 77, "hvac_modes": ["heat", "cool", "off"], "fan_mode": fan, "fan_modes": ["on", "off"], "hvac_action": "cooling", "supported_features": 411}}]
    return areas, devices, entities, states


class ApplianceTests(unittest.TestCase):
    def test_fridge_and_oven_readings_are_not_room_sensors(self):
        areas = [{"area_id": "kitchen", "name": "Kitchen"}, {"area_id": "bedroom", "name": "Bedroom"}]
        devices = [{"id": "fridge", "area_id": "kitchen", "name": "Refrigerator", "manufacturer": "Samsung", "model": "RF28"},
                   {"id": "range", "area_id": "kitchen", "name": "Range", "manufacturer": "Samsung"},
                   {"id": "aqara", "area_id": "bedroom", "name": "Temperature and humidity sensor", "manufacturer": "Aqara", "model": "WSDCGQ11LM"},
                   {"id": "nest", "area_id": "bedroom", "name": "Living Room", "manufacturer": "Google"}]
        entities = [{"entity_id": "sensor.kitchen_fridge_temperature", "device_id": "fridge"},
                    {"entity_id": "sensor.kitchen_second_cavity_temperature", "device_id": "range"},
                    {"entity_id": "sensor.mystery_temperature", "device_id": "fridge"},          # a bland name on an appliance device
                    {"entity_id": "sensor.bedroom_temperature", "device_id": "aqara"},
                    {"entity_id": "sensor.bedroom_humidity", "device_id": "aqara"},
                    {"entity_id": "sensor.living_room_temperature", "device_id": "nest"}]
        st = lambda eid, name, cls="temperature": {"entity_id": eid, "state": "70", "attributes": {"friendly_name": name, "device_class": cls, "unit_of_measurement": "°F"}}
        states = [st("sensor.kitchen_fridge_temperature", "Fridge temperature"), st("sensor.kitchen_second_cavity_temperature", "Second cavity temperature"),
                  st("sensor.mystery_temperature", "Temperature"), st("sensor.bedroom_temperature", "Temperature"),
                  st("sensor.bedroom_humidity", "Humidity", "humidity"), st("sensor.living_room_temperature", "Temperature")]
        home = Home().build(areas, devices, entities, states)
        self.assertEqual(sorted(home.devices), ["sensor.bedroom_humidity", "sensor.bedroom_temperature", "sensor.living_room_temperature"])
        self.assertEqual(home.devices["sensor.bedroom_temperature"].attrs, {"unit_of_measurement": "°F"})


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


class CameraLampTests(unittest.TestCase):
    """A Ring floodlight cam is one unit in HA with a camera entity and a light entity."""
    def snap(self, lamp="off"):
        areas = [{"area_id": "yard", "name": "Backyard"}]
        entities = [{"entity_id": "camera.yard", "device_id": "ring1"}, {"entity_id": "light.yard_light", "device_id": "ring1"},
                    {"entity_id": "camera.door", "device_id": "ring2"}, {"entity_id": "light.porch", "device_id": "hue1"}]
        devices = [{"id": "ring1", "area_id": "yard"}, {"id": "ring2", "area_id": "yard"}, {"id": "hue1", "area_id": "yard"}]
        states = [{"entity_id": "camera.yard", "state": "idle", "attributes": {"friendly_name": "Backyard Live view"}},
                  {"entity_id": "light.yard_light", "state": lamp, "attributes": {"friendly_name": "Backyard Light"}},
                  {"entity_id": "camera.door", "state": "idle", "attributes": {"friendly_name": "Doorbell"}},
                  {"entity_id": "light.porch", "state": "on", "attributes": {"friendly_name": "Porch"}}]
        return areas, devices, entities, states

    def test_the_camera_points_at_its_own_lamp_only(self):
        home = Home().build(*self.snap())
        self.assertEqual(home.devices["camera.yard"].attrs.get("light"), "light.yard_light")
        self.assertNotIn("light", home.devices["camera.door"].attrs, "a camera without a lamp gets none, not the nearest light")
        self.assertEqual(home.devices["light.yard_light"].capability, "light", "the lamp is still a light of its own in the room")

    def test_the_link_survives_a_state_change(self):
        home = Home().build(*self.snap())
        home.apply_state("camera.yard", {"state": "recording", "attributes": {"friendly_name": "Backyard Live view"}})
        self.assertEqual(home.devices["camera.yard"].attrs.get("light"), "light.yard_light")
