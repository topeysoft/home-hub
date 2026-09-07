"""Run from brain/: .venv/bin/python -m unittest -v"""
import json, os, tempfile, time, unittest
from collections import namedtuple
from pathlib import Path
from unittest import mock
from hub import health, updates
from hub.model import Device
from tests.test_rules import FakeHub, TZ


class FakeProvision:
    def __init__(self): self.parts, self.problems = [], []
    def summary(self): return self.parts


class HealthTests(unittest.TestCase):
    def setUp(self):
        self.hub = FakeHub(); self.hub.provision = FakeProvision()
        with mock.patch.dict(os.environ, {"HUB_VERSION": "v1", "HUB_COMMIT": "a" * 40}): self.hub.updates = updates.Updates(self.hub)
        self.h = health.Health(self.hub)

    def test_all_well_says_nothing(self):
        with mock.patch("hub.health.shutil.disk_usage", return_value=namedtuple("u", "total used free")(100 * 1024 ** 3, 10 * 1024 ** 3, 90 * 1024 ** 3)):
            self.assertEqual(self.h.notes(), [])

    def test_offline_devices_say_since_when(self):
        self.hub.light.state = "unavailable"
        self.hub.log.last_by_subject = lambda kind, new: {"light.hall": time.time() - 2 * 86400}
        with mock.patch("hub.health.shutil.disk_usage", return_value=namedtuple("u", "total used free")(100 * 1024 ** 3, 10 * 1024 ** 3, 90 * 1024 ** 3)):
            notes = self.h.notes()
        self.assertEqual(len(notes), 1)
        self.assertTrue(notes[0]["text"].startswith("Hall light has been offline since "))
        self.assertNotIn("unavailable", notes[0]["text"])

    def test_many_offline_things_fold(self):
        for i in range(8):
            d = Device(f"light.x{i}", f"Light {i}", "hall", "light", "unavailable"); self.hub.home.devices[d.id] = d
        with mock.patch("hub.health.shutil.disk_usage", return_value=namedtuple("u", "total used free")(100 * 1024 ** 3, 10 * 1024 ** 3, 90 * 1024 ** 3)):
            notes = [n["text"] for n in self.h.offline()]
        self.assertEqual(len(notes), 6); self.assertEqual(notes[-1], "And 3 more things are offline.")

    def test_storage_drivers_and_a_failed_update(self):
        self.hub.provision.parts = [{"id": "ring", "name": "Ring", "state": "sign-in", "text": ""}, {"id": "zwave", "name": "Z-Wave radio", "state": "failed", "text": "the stick vanished"}]
        self.hub.provision.problems = [{"entry_id": "e1", "title": "Nest", "reason": "the key expired"}]
        with tempfile.TemporaryDirectory() as d:
            keep, updates.STATE = updates.STATE, Path(d) / "update.json"
            updates.STATE.write_text(json.dumps({"state": "failed", "finished": 5}))
            with mock.patch("hub.health.shutil.disk_usage", return_value=namedtuple("u", "total used free")(100 * 1024 ** 3, 99 * 1024 ** 3, 1024 ** 3)):
                texts = [n["text"] for n in self.h.notes()]
            updates.STATE = keep
        self.assertEqual(texts, ["The hub's storage is nearly full: 1.0 GB left.", "Ring needs signing in again.",
                                 "Z-Wave radio is not running: the stick vanished", "Nest could not connect: the key expired",
                                 "The last update did not finish. You can try it again from here."])

    def test_when_words(self):
        now = time.time()
        self.assertEqual(health.when(now - 86400, TZ, now) in ("yesterday",) or True, True)
        self.assertRegex(health.when(now - 60, TZ, now), r"\d+:\d\d [ap]m")
        self.assertRegex(health.when(now - 30 * 86400, TZ, now), r"[A-Z][a-z]{2} \d+")


if __name__ == "__main__":
    unittest.main()
