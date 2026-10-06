# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
import tempfile, unittest
from pathlib import Path
from hub.lock import Lock, needs_code, TRIES
from hub.settings import Settings


class SurvivesARestart(unittest.TestCase):
    """The wait after five wrong codes is on disk, and it is on disk because of the restart button.

    While the count lived only in the process, anybody who could make the brain start again got five
    fresh guesses. That used to mean somebody at the plug; it now means one tap on a phone, so the
    brute force would be the feature. docs/restart.md, piece 9."""
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.path = Path(self.dir.name) / "settings.json"
        lock = Lock(Settings(self.path))
        lock.set("2468")
        for _ in range(TRIES): lock.check("1111", "10.0.0.9")
        self.assertGreater(lock.waiting("10.0.0.9"), 0)

    def test_the_wait_is_still_there_on_the_way_back_up(self):
        again = Lock(Settings(self.path))
        self.assertGreater(again.waiting("10.0.0.9"), 0)
        self.assertFalse(again.check("2468", "10.0.0.9"))      # even the right code waits the minute out

    def test_and_it_is_only_the_address_that_was_guessing(self):
        again = Lock(Settings(self.path))
        self.assertEqual(again.waiting("10.0.0.20"), 0)
        self.assertTrue(again.check("2468", "10.0.0.20"))


class NeedsCode(unittest.TestCase):
    def test_driving_the_house_is_open(self):
        for m, p in [("POST", "/devices/light.kitchen/on"), ("POST", "/rooms/kitchen/intent/asleep"), ("POST", "/home/intent/away"),
                     ("GET", "/home"), ("GET", "/setup/status"), ("GET", "/events"), ("GET", "/rooms/kitchen/why"), ("GET", "/discovered"), ("GET", "/pair"),
                     ("POST", "/drafts"), ("GET", "/drafts"), ("GET", "/assistant"), ("POST", "/rooms/kitchen/explain"), ("GET", "/update"), ("POST", "/update/check"), ("POST", "/drafts/suggest"), ("GET", "/strip"), ("GET", "/strip/list")]:
            self.assertFalse(needs_code(m, p), p)

    def test_changing_the_house_is_locked(self):
        for m, p in [("POST", "/setup/pin"), ("POST", "/setup/done"), ("GET", "/setup/advanced"), ("POST", "/rooms"), ("DELETE", "/rooms/kitchen"),
                     ("POST", "/rooms/kitchen/rename"), ("POST", "/devices/light.kitchen/move"), ("POST", "/devices/light.kitchen/rename"),
                     ("POST", "/flows"), ("GET", "/flows/abc"), ("POST", "/credentials"), ("POST", "/location"), ("POST", "/home/entry"), ("PUT", "/rules"), ("POST", "/pair"), ("DELETE", "/pair"),
                     ("POST", "/drafts/hall-late/approve"), ("DELETE", "/drafts/hall-late"), ("POST", "/assistant/key"), ("POST", "/update"), ("GET", "/backup"), ("POST", "/restore"),
                     ("DELETE", "/devices/light.kitchen"), ("DELETE", "/strip/c8ebba")]:
            self.assertTrue(needs_code(m, p), p)


class LockTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.lock = Lock(Settings(Path(self.dir.name) / "settings.json"))

    def tearDown(self): self.dir.cleanup()

    def test_no_code_means_open(self):
        self.assertFalse(self.lock.locked)
        self.assertTrue(self.lock.check(None))

    def test_set_check_clear(self):
        self.lock.set("2468")
        self.assertTrue(self.lock.locked)
        self.assertTrue(self.lock.check("2468", "a"))
        self.assertFalse(self.lock.check("1111", "a"))
        self.assertFalse(self.lock.check(None, "a"))
        self.assertNotIn("2468", (Path(self.dir.name) / "settings.json").read_text())   # never stored in the clear
        self.lock.set("")
        self.assertFalse(self.lock.locked)

    def test_shape(self):
        for bad in ("123", "123456789", "12ab", "abcd"):
            with self.assertRaises(ValueError): self.lock.set(bad)

    def test_too_many_tries_waits(self):
        self.lock.set("2468")
        for _ in range(TRIES): self.lock.check("0000", "guest")
        self.assertGreater(self.lock.waiting("guest"), 0)
        self.assertFalse(self.lock.check("2468", "guest"))     # even the right code waits
        self.assertTrue(self.lock.check("2468", "owner"))      # another address is unaffected


if __name__ == "__main__":
    unittest.main()
