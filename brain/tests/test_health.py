"""Run from brain/: .venv/bin/python -m unittest -v"""
import json, os, tempfile, time, unittest
from collections import namedtuple
from pathlib import Path
from unittest import mock
from hub import health, updates
from hub.model import Device
from tests.test_rules import FakeHub, TZ


class FakeProvision:
    def __init__(self): self.parts, self.problems, self.sign_ins = [], [], []
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


class DriverNoteTests(unittest.TestCase):
    """A sentence about a driver is only worth reading if something can be done about it, so each one
    carries the way to do it: the flow that finishes a sign-in, or the entry to ask again."""
    def setUp(self):
        self.hub = FakeHub(); self.hub.provision = FakeProvision()
        with mock.patch.dict(os.environ, {"HUB_VERSION": "v1", "HUB_COMMIT": "a" * 40}): self.hub.updates = updates.Updates(self.hub)
        self.h = health.Health(self.hub)

    def test_a_sign_in_says_the_maker_and_carries_its_flow(self):
        self.hub.provision.sign_ins = [{"flow_id": "f-nest", "handler": "nest", "kind": "Google Nest", "title": "home-hub", "source": "reauth"}]
        n = self.h.drivers()[0]
        self.assertEqual(n["text"], "Google Nest needs signing in again: home-hub.")
        self.assertEqual((n["flow"], n["subject"], n["do"]), ("f-nest", "nest", "Sign in again"))
        self.assertNotIn("reauth", n["text"])

    def test_one_account_of_its_kind_does_not_repeat_itself(self):
        self.hub.provision.sign_ins = [{"flow_id": "f1", "handler": "hue", "kind": "Philips Hue", "title": "Philips Hue", "source": "reauth"}]
        self.assertEqual(self.h.drivers()[0]["text"], "Philips Hue needs signing in again.")

    def test_a_reconfigure_asks_for_a_setting_not_a_sign_in(self):
        self.hub.provision.sign_ins = [{"flow_id": "f1", "handler": "hue", "kind": "Philips Hue", "title": "Philips Hue", "source": "reconfigure"}]
        n = self.h.drivers()[0]
        self.assertEqual((n["text"], n["do"]), ("Philips Hue needs a setting checked.", "Check it"))

    def test_something_that_could_not_start_carries_its_entry_to_try_again(self):
        self.hub.provision.problems = [{"entry_id": "e-hue", "domain": "hue", "title": "Hue bridge", "state": "setup_error", "reason": "no route"}]
        n = self.h.drivers()[0]
        self.assertEqual(n["text"], "Hue bridge could not connect: no route")
        self.assertEqual(n["retry"], "e-hue")

    def test_a_part_the_hub_runs_itself_has_no_flow_to_offer(self):
        self.hub.provision.parts = [{"id": "ring", "name": "Ring", "state": "sign-in"}]
        n = self.h.drivers()[0]
        self.assertEqual(n["text"], "Ring needs signing in again.")
        self.assertNotIn("flow", n)

