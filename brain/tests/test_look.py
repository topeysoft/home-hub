# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
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
        self.assertEqual(self.hub.look["feel"], "calm")      # the one thing a person actually picks
        self.assertEqual(self.hub.look["layout"], "auto")    # and the one the screen answers for itself

    def test_setting_one_key_leaves_the_others(self):
        self.hub.set_look({"tone": "pastel"})
        self.assertEqual(self.hub.look, {"feel": "calm", "tone": "pastel", "face": "paper", "layout": "auto", "nav": "auto"})
        self.hub.set_look({"layout": "rail"})
        self.assertEqual(self.hub.look["layout"], "rail")
        self.assertEqual(self.hub.look["tone"], "pastel")

    def test_a_feel_is_kept(self):
        """The Look page writes one feel and what it resolves to, in a single call."""
        self.hub.set_look({"feel": "nightfall", "face": "glass", "tone": "follow", "layout": "auto", "nav": "auto"})
        self.assertEqual(self.hub.look, {"feel": "nightfall", "face": "glass", "tone": "follow", "layout": "auto", "nav": "auto"})

    def test_a_face_is_kept(self):
        """It was not in the vocabulary, so every Glass a panel ever sent was dropped on the floor:
        the screen showed it optimistically and the house handed back paper."""
        self.hub.set_look({"face": "glass"})
        self.assertEqual(self.hub.look["face"], "glass")
        self.assertEqual(self.hub.settings.get("look")["face"], "glass")

    def test_unknown_keys_are_dropped(self):
        """An older or newer screen cannot teach the house a setting it does not have."""
        self.hub.set_look({"tone": "cool", "wallpaper": "kittens"})
        self.assertEqual(self.hub.look["tone"], "cool")
        self.assertNotIn("wallpaper", self.hub.look)
        self.assertNotIn("wallpaper", self.hub.settings.get("look"))

    def test_every_screen_is_told(self):
        """One house, one answer: the change goes out so the other panels follow without a reload."""
        self.hub.set_look({"layout": "rail"})
        self.assertEqual(len(self.hub.sent), 1)
        self.assertEqual(self.hub.sent[0]["type"], "ambient")
        self.assertEqual(self.hub.sent[0]["ambient"]["look"]["layout"], "rail")

    def test_it_survives_a_restart(self):
        self.hub.set_look({"feel": "daylight", "tone": "warm", "face": "glass", "layout": "rail", "nav": "top"})
        again = FakeHub(self.path)
        self.assertEqual(again.look, {"feel": "daylight", "tone": "warm", "face": "glass", "layout": "rail", "nav": "top"})

    def test_a_house_from_before_feels_keeps_what_it_chose(self):
        """The arrangement went automatic, and "auto" is the new default -- but a house that had
        already been told Rail and Top said so explicitly, and nothing may quietly overrule that."""
        self.settings_before = Settings(self.path)
        self.settings_before.set(look={"tone": "warm", "layout": "rail", "nav": "top"})
        again = FakeHub(self.path)
        self.assertEqual(again.look["layout"], "rail")
        self.assertEqual(again.look["nav"], "top")
        self.assertEqual(again.look["tone"], "warm")
        self.assertEqual(again.look["feel"], "calm")   # somewhere real to fall back to; the panel calls it adjusted


if __name__ == "__main__":
    unittest.main()
