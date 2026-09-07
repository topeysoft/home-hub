"""Names and rooms for things under New devices. Run from brain/: .venv/bin/python -m unittest -v"""
import json, unittest
from hub.suggest import Suggestions, clean_name
from hub.model import Device, Room
from tests.test_rules import FakeHub


class Assistant:
    def __init__(self, configured, reply=None): self.configured, self.reply, self.calls = configured, reply, []
    def status(self): return {"configured": self.configured}
    async def _ask(self, system, user, schema=None, **kw): self.calls.append(user); return json.dumps(self.reply)


class Hub(FakeHub):
    def __init__(self, configured=False, reply=None):
        super().__init__()
        self.home.rooms["kitchen"] = Room("kitchen", "Kitchen"); self.home.rooms["kids"] = Room("kids", "Kids' room"); self.home.rooms["unassigned"] = Room("unassigned", "New devices")
        self.home.hardware = {"hw1": {"name": "Kitchen Hue bridge lamp", "manufacturer": "Signify", "model": "LCA001"}, "hw2": {"name": "lumi.sensor_motion.aq2", "manufacturer": "LUMI", "model": "RTCGQ11LM"}}
        for d in (Device("light.hue_color_lamp_1", "Hue color lamp 1", "unassigned", "light", "off", hw="hw1"),
                  Device("binary_sensor.lumi_motion", "lumi.sensor_motion.aq2 Occupancy", "unassigned", "motion", "off", hw="hw2"),
                  Device("sensor.lumi_lux", "lumi.sensor_motion.aq2 Illuminance", "unassigned", "sensor.illuminance", "12", hw="hw2"),
                  Device("switch.kids_room_plug", "TP-LINK Kasa HS103 Kids Room Plug", "unassigned", "switch", "on"),
                  Device("light.hall_2", "Hallway lamp", "unassigned", "light", "off")):
            self.home.rooms["unassigned"].devices.append(d); self.home.devices[d.id] = d
        self.assistant = Assistant(configured, reply)


class Names(unittest.TestCase):
    def test_maker_and_model_words_come_out(self):
        self.assertEqual(clean_name("TP-LINK Kasa KL125 Bulb", "light"), "Light")
        self.assertEqual(clean_name("Zooz ZEN32 Scene Controller", "switch"), "Plug")
        self.assertEqual(clean_name("Kitchen Hue Color Lamp", "light", "Kitchen"), "Kitchen lamp")
        self.assertEqual(clean_name("Living Room TV", "media"), "Living room TV")
        self.assertEqual(clean_name("Front door", "lock"), "Front door")
        self.assertEqual(clean_name("lumi.sensor_motion.aq2 Occupancy", "motion"), "Sensor motion occupancy")

    def test_a_name_that_is_only_the_room_gets_a_kind(self):
        self.assertEqual(clean_name("Kitchen", "light", "Kitchen"), "Kitchen light")


class House(unittest.IsolatedAsyncioTestCase):
    async def test_rooms_come_from_names_and_hardware(self):
        hub = Hub()
        out = await hub.suggest.all() if hasattr(hub, "suggest") else await Suggestions(hub).all()
        by = {i["id"]: i for i in out["items"]}
        self.assertEqual(by["light.hue_color_lamp_1"]["room"], "kitchen")            # the hardware is called "Kitchen Hue bridge lamp"
        self.assertEqual(by["switch.kids_room_plug"]["room"], "kids")               # "Kids Room" matches Kids' room
        self.assertEqual(by["switch.kids_room_plug"]["name"], "Kids room plug")
        self.assertEqual(by["light.hall_2"]["room"], "hall")                         # "Hallway" is the room's own name
        self.assertNotIn("room", by.get("binary_sensor.lumi_motion", {}).get("room", "x") or "x")   # nothing places the motion sensor
        self.assertEqual(by["binary_sensor.lumi_motion"]["room"], "")
        self.assertFalse(out["assistant"])
        self.assertEqual(hub.home.devices["light.hue_color_lamp_1"].room_id, "unassigned")   # nothing moved

    async def test_the_assistant_fills_in_what_the_house_could_not(self):
        reply = {"items": [{"id": "binary_sensor.lumi_motion", "name": "Hallway motion", "room": "hall", "why": "the same unit as the light level sensor by the hall"},
                           {"id": "sensor.lumi_lux", "name": "Hallway light level", "room": "attic", "why": "guess"},
                           {"id": "light.hue_color_lamp_1", "name": "Should not apply", "room": "den", "why": "not asked"}]}
        hub = Hub(configured=True, reply=reply)
        out = await Suggestions(hub).all()
        by = {i["id"]: i for i in out["items"]}
        self.assertTrue(out["assistant"])
        self.assertEqual((by["binary_sensor.lumi_motion"]["room"], by["binary_sensor.lumi_motion"]["name"], by["binary_sensor.lumi_motion"]["source"]), ("hall", "Hallway motion", "assistant"))
        self.assertEqual(by["sensor.lumi_lux"]["room"], "")                          # an unknown room is dropped, the name kept
        self.assertEqual(by["sensor.lumi_lux"]["name"], "Hallway light level")
        self.assertEqual(by["light.hue_color_lamp_1"]["room"], "kitchen")            # the house had placed it; only unplaced things were asked about
        asked = hub.assistant.calls[0]
        self.assertIn("binary_sensor.lumi_motion", asked); self.assertNotIn("light.hue_color_lamp_1", asked)
        self.assertIn("kitchen: Kitchen", asked)


if __name__ == "__main__":
    unittest.main()
