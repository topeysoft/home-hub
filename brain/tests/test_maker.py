"""Run from brain/: .venv/bin/python -m unittest -v. Who made a device, from the driver's device registry to the panel."""
import unittest
from hub.model import Home


def snap():
    areas = [{"area_id": "living", "name": "Living room"}]
    devices = [{"id": "hue1", "area_id": "living", "name": "Hue color lamp", "manufacturer": "Signify Netherlands B.V.", "model": "LCA001"},
               {"id": "plug1", "area_id": "living", "name": "Smart plug"}]                       # a maker the registry does not know
    entities = [{"entity_id": "light.floor_lamp", "device_id": "hue1"},
                {"entity_id": "switch.desk_plug", "device_id": "plug1"},
                {"entity_id": "light.orphan", "device_id": None}]                               # no hardware at all: a group, a template
    st = lambda eid, name: {"entity_id": eid, "state": "on", "attributes": {"friendly_name": name}}
    states = [st("light.floor_lamp", "Floor lamp"), st("switch.desk_plug", "Desk plug"), st("light.orphan", "All lamps")]
    return areas, devices, entities, states


class MakerTests(unittest.TestCase):
    def setUp(self): self.home = Home().build(*snap())

    def test_the_registry_manufacturer_reaches_the_device(self):
        self.assertEqual(self.home.devices["light.floor_lamp"].maker, "Signify Netherlands B.V.")

    def test_no_manufacturer_means_none_not_empty(self):
        """A tile shows a maker chip only when there is a name; an empty string would draw an empty chip."""
        self.assertIsNone(self.home.devices["switch.desk_plug"].maker)
        self.assertIsNone(self.home.devices["light.orphan"].maker)

    def test_it_is_in_what_the_panel_receives(self):
        devs = {d["id"]: d for r in self.home.to_dict()["rooms"] for d in r["devices"]}
        self.assertEqual(devs["light.floor_lamp"]["maker"], "Signify Netherlands B.V.")
        self.assertIn("maker", devs["switch.desk_plug"])   # present and null, so an old panel and a new one read the same shape


if __name__ == "__main__":
    unittest.main()
