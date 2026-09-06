import tempfile, unittest
from pathlib import Path
from hub.lock import Lock, needs_code, TRIES
from hub.settings import Settings


class NeedsCode(unittest.TestCase):
    def test_driving_the_house_is_open(self):
        for m, p in [("POST", "/devices/light.kitchen/on"), ("POST", "/rooms/kitchen/intent/asleep"), ("POST", "/home/intent/away"),
                     ("GET", "/home"), ("GET", "/setup/status"), ("GET", "/events"), ("GET", "/rooms/kitchen/why"), ("GET", "/discovered"), ("GET", "/pair"),
                     ("POST", "/drafts"), ("GET", "/drafts"), ("GET", "/assistant"), ("POST", "/rooms/kitchen/explain")]:
            self.assertFalse(needs_code(m, p), p)

    def test_changing_the_house_is_locked(self):
        for m, p in [("POST", "/setup/pin"), ("POST", "/setup/done"), ("GET", "/setup/advanced"), ("POST", "/rooms"), ("DELETE", "/rooms/kitchen"),
                     ("POST", "/rooms/kitchen/rename"), ("POST", "/devices/light.kitchen/move"), ("POST", "/devices/light.kitchen/rename"),
                     ("POST", "/flows"), ("GET", "/flows/abc"), ("POST", "/credentials"), ("POST", "/location"), ("PUT", "/rules"), ("POST", "/pair"), ("DELETE", "/pair"),
                     ("POST", "/drafts/hall-late/approve"), ("DELETE", "/drafts/hall-late"), ("POST", "/assistant/key")]:
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
