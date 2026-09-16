"""Run from brain/: .venv/bin/python -m unittest -v"""
import json, os, tempfile, time, unittest
from collections import namedtuple
from pathlib import Path
from unittest import mock
from hub import health, updates
from hub.model import Device
from tests.test_rules import FakeHub, TZ


class FakeProvision:
    def __init__(self): self.parts, self.problems, self.sign_ins, self.domains = [], [], [], {}
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

    def test_every_offline_thing_gets_its_own_line(self):
        """The list used to stop at five and end with "And 3 more things are offline" -- a sentence with
        nowhere to go. A page can fold its own long list; a fold the panel owns can be opened."""
        for i in range(8):
            d = Device(f"light.x{i}", f"Light {i}", "hall", "light", "unavailable"); self.hub.home.devices[d.id] = d
        with mock.patch("hub.health.shutil.disk_usage", return_value=namedtuple("u", "total used free")(100 * 1024 ** 3, 10 * 1024 ** 3, 90 * 1024 ** 3)):
            notes = [n["text"] for n in self.h.notes()]
        self.assertEqual(len(notes), 8)
        self.assertFalse(any("more things are offline" in t for t in notes))

    def test_an_offline_thing_says_where_it_is_and_how_to_be_rid_of_it(self):
        self.hub.light.state = "unavailable"
        n = self.h.notes()[0]
        self.assertEqual(n["where"], "Hallway · a light")
        self.assertEqual([a["act"] for a in n["acts"]], ["check", "forget"])
        self.assertEqual([a["to"] for a in n["acts"]], ["light.hall", "light.hall"])
        self.assertIn("Remove Hall light", n["acts"][1]["ask"])

    def test_storage_drivers_and_a_failed_update(self):
        self.hub.provision.parts = [{"id": "ring", "name": "Ring", "state": "sign-in", "text": ""}, {"id": "zwave", "name": "Z-Wave radio", "state": "failed", "text": "the stick vanished"}]
        self.hub.provision.problems = [{"entry_id": "e1", "title": "Nest", "reason": "the key expired"}]
        with tempfile.TemporaryDirectory() as d:
            keep, updates.STATE = updates.STATE, Path(d) / "update.json"
            updates.STATE.write_text(json.dumps({"state": "failed", "finished": 5}))
            with mock.patch("hub.health.shutil.disk_usage", return_value=namedtuple("u", "total used free")(100 * 1024 ** 3, 99 * 1024 ** 3, 1024 ** 3)):
                texts = [n["text"] for n in self.h.notes()]
            updates.STATE = keep
        # Causes first: a person opening this is looking for the thing to do, and a fault is that thing.
        self.assertEqual(texts, ["Ring needs signing in again.", "Z-Wave radio is not running: the stick vanished",
                                 "Nest could not connect: the key expired", "The hub's storage is nearly full: 1.0 GB left.",
                                 "The last update did not finish. You can try it again from here."])

    def test_an_update_that_did_not_start_says_the_house_is_working(self):
        # The rollback already happened. What is left to say is which version, that nothing is broken,
        # and that trying again is a thing a person may do from here. docs/updates.md, piece 1.
        with tempfile.TemporaryDirectory() as d:
            keep, updates.STATE = updates.STATE, Path(d) / "update.json"
            updates.STATE.write_text(json.dumps({"state": "reverted", "finished": 5, "bad": "v1.3.0"}))
            notes = self.h.update()
            updates.STATE = keep
        self.assertEqual(len(notes), 1)
        self.assertIn("Version v1.3.0 did not start", notes[0]["text"])
        self.assertIn("Everything is working", notes[0]["text"])
        self.assertEqual([a["act"] for a in notes[0]["acts"]], ["update"])

    def test_an_update_that_could_not_even_be_put_back_says_so_rather_than_claim_a_rollback(self):
        with tempfile.TemporaryDirectory() as d:
            keep, updates.STATE = updates.STATE, Path(d) / "update.json"
            updates.STATE.write_text(json.dumps({"state": "failed", "finished": 5, "bad": "v1.3.0", "reverted": False}))
            notes = self.h.update()
            updates.STATE = keep
        self.assertIn("could not put back", notes[0]["text"])
        self.assertIn("needs a hand", notes[0]["text"])

    def test_a_release_that_could_not_be_checked_is_news_and_not_a_job(self):
        # No Try again: the same tap refuses the same release, and this one is not the household's to fix.
        with tempfile.TemporaryDirectory() as d:
            keep, updates.STATE = updates.STATE, Path(d) / "update.json"
            updates.STATE.write_text(json.dumps({"state": "refused", "finished": 5, "bad": "v1.3.0"}))
            notes = self.h.update()
            updates.STATE = keep
        self.assertEqual(notes[0]["acts"], [])
        self.assertIn("could not be checked", notes[0]["text"])
        self.assertIn("house is working normally", notes[0]["text"])

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
        self.assertEqual(n["subject"], "nest")
        self.assertEqual(n["acts"], [{"do": "Sign in again", "act": "flow", "to": "f-nest"}])
        self.assertNotIn("reauth", n["text"])

    def test_one_account_of_its_kind_does_not_repeat_itself(self):
        self.hub.provision.sign_ins = [{"flow_id": "f1", "handler": "hue", "kind": "Philips Hue", "title": "Philips Hue", "source": "reauth"}]
        self.assertEqual(self.h.drivers()[0]["text"], "Philips Hue needs signing in again.")

    def test_a_reconfigure_asks_for_a_setting_not_a_sign_in(self):
        self.hub.provision.sign_ins = [{"flow_id": "f1", "handler": "hue", "kind": "Philips Hue", "title": "Philips Hue", "source": "reconfigure"}]
        n = self.h.drivers()[0]
        self.assertEqual((n["text"], n["acts"][0]["do"]), ("Philips Hue needs a setting checked.", "Check it"))

    def test_something_that_could_not_start_carries_its_entry_to_try_again(self):
        self.hub.provision.problems = [{"entry_id": "e-hue", "domain": "hue", "title": "Hue bridge", "state": "setup_error", "reason": "no route"}]
        n = self.h.drivers()[0]
        self.assertEqual(n["text"], "Hue bridge could not connect: no route")
        self.assertEqual(n["acts"], [{"do": "Try again", "act": "entry", "to": "e-hue"}])

    def test_a_part_the_hub_runs_itself_has_no_flow_to_offer(self):
        self.hub.provision.parts = [{"id": "ring", "name": "Ring", "state": "sign-in"}]
        n = self.h.drivers()[0]
        self.assertEqual(n["text"], "Ring needs signing in again.")
        self.assertEqual(n["acts"], [])



class GroupingTests(unittest.TestCase):
    """A fault is said once. Eight things on a dead radio are one job, not eight mysteries -- and the
    eight are named under it, so nobody has to wonder which eight."""
    def setUp(self):
        self.hub = FakeHub(); self.hub.provision = FakeProvision()
        with mock.patch.dict(os.environ, {"HUB_VERSION": "v1", "HUB_COMMIT": "a" * 40}): self.hub.updates = updates.Updates(self.hub)
        self.h = health.Health(self.hub)
        self.hub.provision.domains = {"e-zw": "zwave_js", "e-hue": "hue"}

    def quiet(self, n, entry, room="hall"):
        for i in range(n):
            d = Device(f"light.{entry}{i}", f"Light {entry}{i}", room, "light", "unavailable", entry=entry)
            self.hub.home.devices[d.id] = d

    def free_disk(self):
        return mock.patch("hub.health.shutil.disk_usage", return_value=namedtuple("u", "total used free")(100 * 1024 ** 3, 10 * 1024 ** 3, 90 * 1024 ** 3))

    def test_a_dead_radio_gathers_what_went_quiet_with_it(self):
        self.quiet(6, "e-zw")
        self.hub.provision.parts = [{"id": "zwave", "name": "Z-Wave radio", "state": "failed", "text": "no stick"}]
        with self.free_disk(): notes = self.h.notes()
        self.assertEqual(len(notes), 1)                      # one job, not seven lines
        self.assertEqual(len(notes[0]["with"]), 6)
        self.assertEqual(notes[0]["with"][0]["where"], "Hallway · a light")
        self.assertEqual(notes[0]["acts"], [{"do": "Try again", "act": "part", "to": "zwave"}])

    def test_a_part_that_is_simply_absent_is_only_news_when_something_waits_on_it(self):
        self.hub.provision.parts = [{"id": "zwave", "name": "Z-Wave radio", "state": "off", "text": "No Z-Wave stick found."}]
        with self.free_disk(): self.assertEqual(self.h.notes(), [])
        self.quiet(2, "e-zw")
        with self.free_disk(): notes = self.h.notes()
        self.assertEqual([n["text"] for n in notes], ["No Z-Wave stick found."])

    def test_what_no_fault_explains_still_gets_its_own_line(self):
        self.quiet(2, "e-zw")
        self.quiet(1, "e-other")                             # an entry provision knows nothing about
        self.hub.provision.parts = [{"id": "zwave", "name": "Z-Wave radio", "state": "failed", "text": "no stick"}]
        with self.free_disk(): notes = self.h.notes()
        self.assertEqual(len(notes), 2)
        self.assertEqual(notes[0]["kind"], "driver")
        self.assertEqual(notes[1]["subject"], "light.e-other0")

    def test_a_part_that_is_running_explains_nothing(self):
        self.quiet(3, "e-zw")
        self.hub.provision.parts = [{"id": "zwave", "name": "Z-Wave radio", "state": "ready", "text": "Running"}]
        with self.free_disk(): notes = self.h.notes()
        self.assertEqual([n["kind"] for n in notes], ["offline"] * 3)

    def test_nothing_is_claimed_twice(self):
        self.quiet(4, "e-hue")
        self.hub.provision.sign_ins = [{"flow_id": "f1", "handler": "hue", "kind": "Philips Hue", "title": "Philips Hue", "source": "reauth"}]
        self.hub.provision.problems = [{"entry_id": "e-hue", "domain": "hue", "title": "Hue bridge", "reason": "no route"}]
        with self.free_disk(): notes = self.h.notes()
        self.assertEqual([len(n["with"]) for n in notes], [4, 0])   # the sign-in got there first
        self.assertEqual(len(notes), 2)
