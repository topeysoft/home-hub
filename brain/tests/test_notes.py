"""Release notes: the parser, what a hub shows, and when it stops showing it.

The point of the whole piece is one sentence somebody reads on a wall, so these tests are mostly
about what does NOT get shown -- an empty build, a version already read, a hub that has only ever
run the version it is on.

Run from brain/: .venv/bin/python -m pytest tests/test_notes.py
"""
import os, tempfile, unittest
from pathlib import Path
from unittest import mock

from hub import notes, updates
from tests.test_rules import FakeHub

GOOD = """## What's new

- Speakers remember how loud you had them.
- The kitchen comes up on the wall faster after the hub restarts.

## Details

Longer, for whoever goes looking.
"""


class NotesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.d = Path(self.dir.name)
        self.keep = notes.NOTES; notes.NOTES = self.d
        self.keep_state = (updates.REQUEST, updates.STATE)
        updates.REQUEST, updates.STATE = self.d / "update.request", self.d / "update.json"
        self.hub = FakeHub()
        self.hub.status = lambda: {"update": self.hub.updates.summary()}

    def tearDown(self):
        notes.NOTES = self.keep
        updates.REQUEST, updates.STATE = self.keep_state
        self.dir.cleanup()

    def write(self, version, text=GOOD): (self.d / f"{version}.md").write_text(text)

    def make(self, version="v1.3.0"):
        with mock.patch.dict(os.environ, {"HUB_VERSION": version, "HUB_COMMIT": "a" * 40, "HUB_CHANNEL": "release"}):
            self.hub.updates = updates.Updates(self.hub)
        return self.hub.updates


class ParsingTests(NotesTest):
    def test_the_two_sections(self):
        n = notes.parse(GOOD)
        self.assertEqual(len(n["what"]), 2)
        self.assertTrue(n["what"][0].startswith("Speakers remember"))
        self.assertEqual(n["details"], "Longer, for whoever goes looking.")

    def test_a_file_with_only_what_has_no_details_and_does_not_mind(self):
        self.assertEqual(notes.parse("## What's new\n\n- One thing.\n"), {"what": ["One thing."], "details": ""})

    def test_prose_outside_a_heading_is_not_mistaken_for_a_line(self):
        self.assertEqual(notes.parse("Some preamble nobody asked for.\n\n## What's new\n\n- One thing.\n")["what"],
                         ["One thing."])

    def test_asterisks_are_bullets_too(self):
        self.assertEqual(notes.parse("## What's new\n\n* One thing.\n")["what"], ["One thing."])

    def test_nothing_at_all(self):
        self.assertEqual(notes.parse(""), {"what": [], "details": ""})

    def test_the_v_is_not_what_makes_two_releases_different(self):
        self.write("1.3.0")
        self.assertIsNotNone(notes.read("v1.3.0"))
        self.assertIsNotNone(notes.read("1.3.0"))

    def test_a_build_with_no_notes_is_not_an_error(self):
        self.assertIsNone(notes.read("9.9.9"))
        self.assertIsNone(notes.read(""))
        self.assertIsNone(notes.read("dev"))


class HistoryTests(NotesTest):
    def test_newest_first_by_version_and_not_by_name(self):
        for v in ("0.9.0", "0.10.0", "0.2.1"): self.write(v)
        self.assertEqual([r["version"] for r in notes.history()], ["0.10.0", "0.9.0", "0.2.1"])

    def test_the_readme_in_that_folder_is_not_a_release(self):
        self.write("0.3.0"); (self.d / "README.md").write_text("how to write these")
        self.assertEqual([r["version"] for r in notes.history()], ["0.3.0"])

    def test_no_folder_at_all_is_an_empty_history_and_not_a_crash(self):
        notes.NOTES = self.d / "nowhere"
        self.assertEqual(notes.history(), [])


class WhatTheWallShowsTests(NotesTest):
    def test_a_hub_that_has_only_ever_run_this_version_has_nothing_to_announce(self):
        # Somebody who has just plugged one in is being set up, not caught up.
        self.write("1.3.0")
        u = self.make("v1.3.0")
        self.assertIsNone(u.whats_new)
        self.assertEqual(self.hub.settings.get("notes_seen"), "v1.3.0")

    def test_the_version_it_updated_to_is_announced_once(self):
        self.write("1.3.0")
        self.hub.settings.set(notes_seen="v1.2.0")              # what it was on last night
        u = self.make("v1.3.0")
        self.assertEqual(len(u.whats_new["what"]), 2)
        self.assertEqual(u.summary()["whats_new"]["version"], "1.3.0")
        u.read_notes()
        self.assertIsNone(u.whats_new)
        self.assertIsNone(u.summary()["whats_new"])

    def test_a_release_that_shipped_without_notes_says_nothing_rather_than_an_empty_card(self):
        self.hub.settings.set(notes_seen="v1.2.0")
        self.assertIsNone(self.make("v1.3.0").whats_new)

    def test_a_notes_file_with_only_details_is_not_a_card_either(self):
        self.write("1.3.0", "## Details\n\nNothing a household needs.\n")
        self.hub.settings.set(notes_seen="v1.2.0")
        u = self.make("v1.3.0")
        self.assertIsNone(u.whats_new)
        self.assertEqual(u.notes()["details"], "Nothing a household needs.")   # still readable on This hub


class WhatIsWaitingTests(NotesTest):
    def test_the_release_being_offered_carries_its_own_words_and_not_a_commit_subject(self):
        u = self.make("v1.2.0")
        body = "## What's new\n\n- Speakers remember how loud you had them.\n"
        with mock.patch.object(updates, "_get", return_value={"tag_name": "v1.3.0", "name": "Quieter mornings",
                                                              "published_at": "2026-09-16T00:00:00Z", "body": body}):
            latest = u.fetch()
        self.assertEqual(latest["what"], ["Speakers remember how loud you had them."])

    def test_a_release_whose_body_is_a_changelog_is_simply_empty_here(self):
        # It describes and never decides, so the worst an unparseable body does is say nothing.
        u = self.make("v1.2.0")
        with mock.patch.object(updates, "_get", return_value={"tag_name": "v1.3.0", "body": "* abc1234 feat: thing"}):
            self.assertEqual(u.fetch()["what"], [])


if __name__ == "__main__":
    unittest.main()
