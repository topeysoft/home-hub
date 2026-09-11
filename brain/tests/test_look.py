"""Run from brain/: .venv/bin/python -m unittest -v. How the panel looks, kept by the house rather than by the screen."""
import json, tempfile, unittest
from pathlib import Path
from hub.api import Hub, LOOK
from hub.settings import Settings


class FakeHub:
    """Just enough Hub to exercise set_look: a settings file and a broadcast."""

    set_look = Hub.set_look

    def __init__(self, path):
        self.settings = Settings(path)
        self.look = {**LOOK, **(self.settings.get("look") or {})}
        self.sent = []

    def _broadcast(self, msg): self.sent.append(json.loads(msg))

    def ambient(self): return {"location": None, "weather": None, "look": self.look}


class LookTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "settings.json"
        self.hub = FakeHub(self.path)

    def tearDown(self): self.dir.cleanup()

    def test_defaults_before_anyone_chooses(self):
        """A house nobody has touched still has an answer, so a new screen is right first time."""
        self.assertEqual(self.hub.look, LOOK)
        self.assertEqual(self.hub.look["layout"], "stack")   # the arrangement the panel has always had

    def test_setting_one_key_leaves_the_other(self):
        self.hub.set_look({"tone": "pastel"})
        self.assertEqual(self.hub.look, {"tone": "pastel", "layout": "stack"})
        self.hub.set_look({"layout": "rail"})
        self.assertEqual(self.hub.look, {"tone": "pastel", "layout": "rail"})

    def test_unknown_keys_are_dropped(self):
        """An older or newer screen cannot teach the house a setting it does not have."""
        self.hub.set_look({"tone": "cool", "wallpaper": "kittens"})
        self.assertEqual(self.hub.look, {"tone": "cool", "layout": "stack"})
        self.assertNotIn("wallpaper", self.hub.settings.get("look"))

    def test_every_screen_is_told(self):
        """One house, one answer: the change goes out so the other panels follow without a reload."""
        self.hub.set_look({"layout": "rail"})
        self.assertEqual(len(self.hub.sent), 1)
        self.assertEqual(self.hub.sent[0]["type"], "ambient")
        self.assertEqual(self.hub.sent[0]["ambient"]["look"]["layout"], "rail")

    def test_it_survives_a_restart(self):
        self.hub.set_look({"tone": "warm", "layout": "rail"})
        again = FakeHub(self.path)
        self.assertEqual(again.look, {"tone": "warm", "layout": "rail"})


if __name__ == "__main__":
    unittest.main()
