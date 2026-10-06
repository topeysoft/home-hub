# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run from brain/: .venv/bin/python -m unittest -v. The house's one language.

Not what the panel's own words are in -- those are English. What everything the house did NOT
write is asked for in: Home Assistant's names for every integration and every form label, the
place search, the dates and the voice. See hub.set_language and app/src/lang.ts.
"""
import json, tempfile, unittest
from pathlib import Path
from hub.api import Hub
from hub.settings import Settings


class FakeOnboarding:
    """Onboarding keeps every integration's form labels by handler, in the language they were
    fetched in. set_language has to drop them or the Add screen goes on speaking the old one."""

    def __init__(self):
        self._strings = {"hue": {"title": "Philips Hue"}}
        self._names = {"hue": "Philips Hue"}


class FakeHub:
    """Just enough Hub to exercise set_language: a settings file, a broadcast, a strings cache."""

    set_language = Hub.set_language

    def __init__(self, path):
        self.settings = Settings(path)
        self.language = self.settings.get("language") or "en"
        self.onboarding = FakeOnboarding()
        self.sent = []

    def _broadcast(self, msg): self.sent.append(json.loads(msg))

    def status(self): return {"language": self.language}


class LanguageTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "settings.json"
        self.hub = FakeHub(self.path)

    def tearDown(self): self.dir.cleanup()

    def test_a_house_nobody_has_told_is_english(self):
        """The hub ships in English and says so, rather than leaving the field empty for every
        caller to guess at. hub.language is never None."""
        self.assertEqual(self.hub.language, "en")

    def test_it_is_remembered(self):
        self.hub.set_language("fr")
        self.assertEqual(self.hub.language, "fr")
        self.assertEqual(Settings(self.path).get("language"), "fr")
        self.assertEqual(FakeHub(self.path).language, "fr")   # and it survives the brain restarting

    def test_a_region_is_kept_and_the_language_is_lowercased(self):
        """"pt-BR" is a different answer from "pt" and both are worth keeping, but "EN" and "en"
        are not two languages -- a browser that shouts is still asking for English."""
        self.assertEqual(self.hub.set_language("pt-BR"), "pt-BR")
        self.assertEqual(self.hub.set_language("EN"), "en")
        self.assertEqual(self.hub.set_language("zh-Hans"), "zh-Hans")

    def test_nonsense_is_refused_rather_than_stored(self):
        """The panel sends whatever the browser reports, so this takes anything. A tag it cannot
        make sense of leaves the house in the language it was already in."""
        self.hub.set_language("de")
        for bad in ("", "  ", "english please", "e", "xx_YY", "../../etc", "<script>"):
            with self.assertRaises(ValueError, msg=bad): self.hub.set_language(bad)
        self.assertEqual(self.hub.language, "de")

    def test_the_form_labels_cached_in_the_old_language_are_dropped(self):
        """The whole point of the setting. Onboarding caches HA's translated strings per handler;
        without this the Add screen would go on saying the old language's words until the brain
        restarted, which is the kind of bug somebody reports as "it only half worked"."""
        self.assertTrue(self.hub.onboarding._strings)
        self.hub.set_language("nl")
        self.assertEqual(self.hub.onboarding._strings, {})
        self.assertEqual(self.hub.onboarding._names, {})

    def test_every_screen_is_told_at_once(self):
        """One house, one language: a phone and the wall must not disagree about what the
        thermostat's maker is called, so the change goes out on the socket rather than waiting
        for each screen to ask again."""
        self.hub.set_language("it")
        self.assertEqual([m["type"] for m in self.hub.sent], ["status"])
        self.assertEqual(self.hub.sent[0]["status"]["language"], "it")


if __name__ == "__main__":
    unittest.main()
