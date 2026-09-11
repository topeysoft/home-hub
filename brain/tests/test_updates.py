"""Which build this is, whether there is a newer one, and how the panel is told.

Two channels. A hub in someone's house follows releases: nothing reaches it until somebody tags it.
A hub being worked on follows main, commit by commit. The important case in both is the third
answer — "cannot tell" — because a panel that says "up to date" when it does not know is a lie
somebody acts on.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json, os, tempfile, unittest
from pathlib import Path
from unittest import mock

from hub import updates
from tests.test_rules import FakeHub


class UpdateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); d = Path(self.dir.name)
        self.keep = (updates.REQUEST, updates.STATE)
        updates.REQUEST, updates.STATE = d / "update.request", d / "update.json"
        self.hub = FakeHub()
        self.hub.status = lambda: {"update": self.hub.updates.summary()}

    def tearDown(self):
        updates.REQUEST, updates.STATE = self.keep; self.dir.cleanup()

    def make(self, version="v1.2.0", commit="a" * 40, channel="release"):
        with mock.patch.dict(os.environ, {"HUB_VERSION": version, "HUB_COMMIT": commit, "HUB_CHANNEL": channel}):
            self.hub.updates = updates.Updates(self.hub)
        return self.hub.updates

    @staticmethod
    def release(version="v1.3.0", title="Quieter mornings"):
        return lambda: {"version": version, "sha": "b" * 40, "when": "2026-09-11T20:00:00Z", "title": title}


class ChannelTests(UpdateTest):
    def test_a_hub_follows_releases_unless_it_was_told_otherwise(self):
        self.assertEqual(self.make(channel="release").channel, "release")
        with mock.patch.dict(os.environ, {"HUB_VERSION": "v1", "HUB_COMMIT": "a"}, clear=True):
            self.assertEqual(updates.Updates(self.hub).channel, "release")

    def test_a_hub_being_worked_on_can_follow_main_instead(self):
        self.assertEqual(self.make(channel="main").channel, "main")
        self.assertEqual(self.make(channel="MAIN").channel, "main")

    def test_a_channel_nobody_has_heard_of_falls_back_to_releases(self):
        self.assertEqual(self.make(channel="nightly").channel, "release")

    def test_the_panel_is_told_which_channel_it_is_on(self):
        self.assertEqual(self.make(channel="main").summary()["channel"], "main")


class ReleaseChannelTests(UpdateTest):
    async def test_a_newer_release_is_offered_with_the_words_from_the_release_itself(self):
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.0", "Quieter mornings")
        out = await u.check()
        self.assertTrue(out["available"])
        self.assertEqual(out["latest"]["title"], "Quieter mornings")
        self.assertIn('"type": "status"', self.hub.sent[-1])

    async def test_the_release_this_hub_is_already_on_is_not_offered_again(self):
        u = self.make(version="v1.3.0")
        u.fetch = self.release("v1.3.0")
        self.assertFalse((await u.check())["available"])

    async def test_the_v_is_not_what_makes_two_releases_different(self):
        # git carries the tag as v1.3.0 and the image is tagged 1.3.0. They are one release.
        u = self.make(version="1.3.0")
        u.fetch = self.release("v1.3.0")
        self.assertFalse((await u.check())["available"])

    async def test_a_hub_running_a_build_that_is_not_a_release_cannot_be_told_it_is_behind(self):
        # Following releases while running main-1a2b3c4 is a question with no honest answer.
        for version in ("dev", "main-1a2b3c4", ""):
            with self.subTest(version=version):
                u = self.make(version=version)
                u.fetch = self.release("v1.3.0")
                self.assertIsNone((await u.check())["available"])

    async def test_a_hub_that_has_not_managed_to_ask_yet_says_it_does_not_know(self):
        u = self.make()
        self.assertIsNone(u.available)

    async def test_moving_to_a_release_is_a_file_for_the_host_and_a_line_in_the_log(self):
        u = self.make(version="v1.2.0")
        u.latest = self.release("v1.3.0")()
        out = u.request()
        self.assertTrue(out["requested"])
        parked = json.loads(updates.REQUEST.read_text())
        self.assertEqual((parked["from"], parked["to"], parked["channel"]), ("v1.2.0", "v1.3.0", "release"))
        self.assertEqual(self.hub.log.rows[-1]["new"], "v1.3.0")


class MainChannelTests(UpdateTest):
    @staticmethod
    def commit(sha="b" * 40, title="feat: something"):
        return lambda: {"version": f"main-{sha[:7]}", "sha": sha, "when": "2026-09-11T20:00:00Z", "title": title}

    async def test_main_moved_on_and_the_panel_is_told_once(self):
        u = self.make(version="main-aaaaaaa", channel="main")
        u.fetch = self.commit()
        out = await u.check()
        self.assertTrue(out["available"])
        self.assertEqual(out["latest"]["title"], "feat: something")
        sent = len(self.hub.sent)
        await u.check()                                            # no change, no chatter
        self.assertEqual(len(self.hub.sent), sent)

    async def test_the_same_commit_means_up_to_date(self):
        u = self.make(commit="a" * 40, channel="main")
        u.fetch = self.commit("a" * 40)
        self.assertFalse((await u.check())["available"])

    async def test_a_release_tag_is_not_what_this_channel_compares(self):
        # On main it is the commit that decides, so a hub built from a tagged commit is still current.
        u = self.make(version="v1.2.0", commit="a" * 40, channel="main")
        u.fetch = self.commit("a" * 40)
        self.assertFalse((await u.check())["available"])

    async def test_a_build_that_does_not_know_its_own_commit_cannot_tell(self):
        u = self.make(commit="", channel="main")
        u.fetch = self.commit()
        self.assertIsNone((await u.check())["available"])


class WhenGitHubIsUnreachableTests(UpdateTest):
    async def test_the_last_good_answer_stands_and_the_reason_is_kept_not_raised(self):
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.0")
        self.assertTrue((await u.check())["available"])

        def boom(): raise OSError("no internet")
        u.fetch = boom
        out = await u.check()
        self.assertTrue(out["available"])                          # still true: nothing has changed, we just cannot re-ask
        self.assertIn("no internet", out["error"])

    async def test_asking_again_and_succeeding_clears_the_complaint(self):
        u = self.make(version="v1.2.0")
        def boom(): raise OSError("no internet")
        u.fetch = boom
        self.assertIsNotNone((await u.check())["error"])
        u.fetch = self.release("v1.3.0")
        self.assertIsNone((await u.check())["error"])


class HostReportTests(UpdateTest):
    def test_what_the_host_wrote_about_the_last_attempt_reaches_the_panel(self):
        u = self.make()
        updates.STATE.write_text(json.dumps({"state": "running", "started": 1}))
        self.assertEqual(u.summary()["state"]["state"], "running")

    def test_a_state_file_that_got_mangled_does_not_take_the_panel_down(self):
        u = self.make()
        updates.STATE.write_text("{half a file")
        self.assertIsNone(u.summary()["state"])


if __name__ == "__main__":
    unittest.main()
