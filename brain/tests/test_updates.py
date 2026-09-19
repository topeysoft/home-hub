# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which build this is, whether there is a newer one, and how the panel is told.

Two channels. A hub in someone's house follows releases: nothing reaches it until somebody tags it.
A hub being worked on follows main, commit by commit. The important case in both is the third
answer — "cannot tell" — because a panel that says "up to date" when it does not know is a lie
somebody acts on.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json, os, tempfile, time, unittest
from pathlib import Path
from unittest import mock

from hub import updates
from tests.test_rules import FakeHub


class UpdateTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); d = Path(self.dir.name)
        self.keep = (updates.REQUEST, updates.STATE)
        self.keep_channel, self.keep_progress = updates.CHANNEL, updates.PROGRESS
        updates.REQUEST, updates.STATE = d / "update.request", d / "update.json"
        updates.CHANNEL = d / "channel.json"
        updates.PROGRESS = d / "update.progress"
        self.hub = FakeHub()
        self.hub.status = lambda: {"update": self.hub.updates.summary()}

    def tearDown(self):
        updates.REQUEST, updates.STATE = self.keep
        updates.CHANNEL, updates.PROGRESS = self.keep_channel, self.keep_progress
        self.dir.cleanup()

    def make(self, version="v1.2.0", commit="a" * 40, channel="release", verified=""):
        with mock.patch.dict(os.environ, {"HUB_VERSION": version, "HUB_COMMIT": commit, "HUB_CHANNEL": channel,
                                          "HUB_VERIFIED": verified}):
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


class RolledBackTests(UpdateTest):
    """A version the host installed, could not bring back up, and put back. docs/updates.md, piece 1."""

    def reverted(self, bad="v1.3.0", state="reverted"):
        updates.STATE.write_text(json.dumps({"state": state, "started": 1, "finished": 2, "bad": bad}))

    async def offered(self, u):
        out = await u.check()
        return out["available"], out["offer"]

    async def test_a_version_that_was_put_back_is_not_raised_again_on_its_own(self):
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.0")
        self.assertEqual(await self.offered(u), (True, True))
        self.reverted("v1.3.0")
        # It is still true that a newer build exists; what changes is whether the hub pushes it.
        self.assertEqual(await self.offered(u), (True, False))
        self.assertEqual(u.summary()["rejected"], "1.3.0")

    async def test_the_v_does_not_make_it_a_different_version_here_either(self):
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.0")
        self.reverted("1.3.0")                                     # the host named it without the v
        self.assertEqual(await self.offered(u), (True, False))

    async def test_the_release_after_the_one_that_failed_is_offered_normally(self):
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.1")
        self.reverted("v1.3.0")
        self.assertEqual(await self.offered(u), (True, True))

    async def test_a_person_can_still_ask_for_it_from_this_hub(self):
        # The nudge is what stops; the button is not. Trying it twice is often what fixes it.
        u = self.make(version="v1.2.0")
        u.latest = self.release("v1.3.0")()
        self.reverted("v1.3.0")
        self.assertTrue(u.request()["requested"])
        self.assertEqual(json.loads(updates.REQUEST.read_text())["to"], "v1.3.0")

    async def test_an_update_that_could_not_even_be_put_back_is_refused_the_same_way(self):
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.0")
        self.reverted("v1.3.0", state="failed")
        self.assertEqual(await self.offered(u), (True, False))

    async def test_a_release_the_host_would_not_vouch_for_is_not_offered_either(self):
        # Nothing was installed and nothing is broken; what stops is the hub raising it. docs/updates.md, piece 2.
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.0")
        self.reverted("v1.3.0", state="refused")
        self.assertEqual(await self.offered(u), (True, False))
        self.assertEqual(u.summary()["rejected"], "1.3.0")

    async def test_an_ordinary_failure_with_no_version_named_holds_nothing_back(self):
        # The installer stopped before anything moved: there is no bad version, so nothing is refused.
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.0")
        updates.STATE.write_text(json.dumps({"state": "failed", "started": 1, "finished": 2}))
        self.assertEqual(await self.offered(u), (True, True))

    async def test_the_fix_for_a_rejected_release_is_raised_the_moment_it_exists(self):
        """What the panel is told about is `offer` moving, not `available`.

        After a rollback both are already settled -- there is a newer build (true) and the hub is not
        pushing it (false) -- so the release that comes along to fix it moves only the second one. A
        hub that watched `available` would sit on the fix in silence, because from its point of view
        nothing changed. The rollback itself needs no broadcast: putting the old image back restarts
        the brain, so every panel reconnects and asks.
        """
        u = self.make(version="v1.2.0")
        u.fetch = self.release("v1.3.0")
        self.reverted("v1.3.0")
        await u.check()
        sent = len(self.hub.sent)
        u.fetch = self.release("v1.3.1")
        out = await u.check()
        self.assertEqual((out["available"], out["offer"]), (True, True))
        self.assertGreater(len(self.hub.sent), sent)


if __name__ == "__main__":
    unittest.main()


class HoldAndRolloutTests(UpdateTest):
    """What the maker is saying about releases right now. docs/updates.md, piece 5."""

    def channel(self, **doc):
        updates.CHANNEL.parent.mkdir(parents=True, exist_ok=True)
        updates.CHANNEL.write_text(json.dumps({"schema": 1, "made": "2026-09-16T00:00:00Z"} | doc))

    def waiting(self, version="v1.3.0"):
        u = self.make(version="v1.2.0", verified="1")
        u.latest = self.release(version)()
        return u

    # ---- a hold ----
    def test_a_held_release_is_not_offered_installed_or_tappable(self):
        u = self.waiting()
        self.assertTrue(u.offer)
        self.channel(hold=["v1.3.0"])
        self.assertTrue(u.available)                       # it still exists; that has not changed
        self.assertFalse(u.offer)
        self.assertTrue(u.summary()["held"])
        with self.assertRaises(ValueError): u.request()    # the panel gets a sentence, not a restart

    def test_the_v_is_not_what_makes_two_versions_different_here_either(self):
        u = self.waiting()
        self.channel(hold=["1.3.0"])
        self.assertTrue(u.held())

    def test_a_hold_on_some_other_release_changes_nothing(self):
        u = self.waiting()
        self.channel(hold=["v1.2.9", "v1.4.0"])
        self.assertTrue(u.offer)
        self.assertFalse(u.summary()["held"])

    def test_no_channel_file_means_nothing_is_held(self):
        # The direction this is allowed to fail in: the alternative hands anybody who can block a
        # network the power to freeze every hub on the version it is on.
        u = self.waiting()
        self.assertFalse(u.held())
        self.assertTrue(u.offer)

    def test_a_channel_file_that_got_mangled_does_not_take_the_panel_down(self):
        u = self.waiting()
        updates.CHANNEL.parent.mkdir(parents=True, exist_ok=True)
        updates.CHANNEL.write_text("{half a file")
        self.assertEqual(u.channel_says(), {})
        self.assertTrue(u.offer)

    # ---- and a rollout ----
    def test_a_release_only_part_way_out_reaches_some_houses_and_not_others(self):
        seen = []
        for n in range(40):
            self.hub.settings.data["hub_id"] = f"hub{n}"
            u = self.waiting()
            self.channel(rollout={"v1.3.0": 0.25})
            seen.append(u.reached_us())
        self.assertTrue(any(seen))
        self.assertTrue(any(not x for x in seen))
        self.assertLess(sum(seen), 30)                     # a quarter, give or take, and nothing like all

    def test_all_the_way_out_reaches_everybody(self):
        for n in range(10):
            self.hub.settings.data["hub_id"] = f"hub{n}"
            u = self.waiting()
            self.channel(rollout={"v1.3.0": 1})
            self.assertTrue(u.reached_us())

    def test_the_same_houses_are_not_first_every_time(self):
        """The version is mixed into the hash on purpose. Hashing the id alone would make one
        unlucky tenth of houses the guinea pigs for every release this hub ever ships."""
        self.hub.settings.data["hub_id"] = "a-particular-house"
        first = []
        for n in range(3, 40):
            v = f"v1.{n}.0"
            u = self.waiting(v)
            self.channel(rollout={v: 0.25})
            first.append(u.reached_us())
        self.assertTrue(any(first))
        self.assertTrue(any(not x for x in first))

    def test_a_share_nobody_can_read_is_not_a_hold(self):
        u = self.waiting()
        self.channel(rollout={"v1.3.0": "a quarter"})
        self.assertTrue(u.reached_us())

    def test_a_rollout_slows_the_hub_down_and_never_a_person(self):
        """Somebody standing at the wall with Install in front of them has decided. Being in the
        second nine tenths is a reason for the hub to wait and not a reason to refuse them."""
        self.hub.settings.data["hub_id"] = "not-in-the-first-tenth"
        u = self.waiting()
        self.channel(rollout={"v1.3.0": 0.0})
        self.assertFalse(u.reached_us())
        self.assertTrue(u.offer)                           # still offered, and the button still works
        self.assertTrue(u.request()["requested"])


class NightlyTests(UpdateTest):
    """The hub installing an update by itself, in the small hours. docs/updates.md, piece 3."""

    def ready(self, **kw):
        """A hub that can verify, with an update waiting for it."""
        u = self.make(version="v1.2.0", verified="1", **kw)
        u.latest = self.release("v1.3.0")()
        return u

    @staticmethod
    def at(hour, minute, day=17):
        from datetime import datetime
        from tests.test_rules import TZ
        return datetime(2026, 9, day, hour, minute, tzinfo=TZ).timestamp()

    def tonight(self, u, past=1):
        """`past` minutes after this hub's own minute of the window."""
        m = u.minute_of_the_night() + past
        return self.at(updates.WINDOW[0] + m // 60, m % 60)

    # ---- whether it is on at all ----
    def test_a_hub_that_cannot_check_what_it_installs_waits_to_be_asked(self):
        # Updating by itself from something nothing verifies is the supply-chain problem with the
        # person taken out of it. No keys on the host, no updating in the night.
        self.assertFalse(self.make(verified="").auto)

    def test_a_hub_that_can_check_installs_on_its_own(self):
        self.assertTrue(self.make(verified="1").auto)

    def test_the_household_outranks_both(self):
        u = self.make(verified="1")
        u.set_auto(False)
        self.assertFalse(u.auto)
        self.assertEqual(self.hub.log.rows[-1]["new"], "automatic off")
        u.set_auto(True)
        self.assertTrue(u.auto)
        # ...and it stays said, on a hub that could not check either way
        v = self.make(verified="")
        self.assertTrue(v.auto)

    # ---- when ----
    def test_not_in_the_evening_and_not_over_breakfast(self):
        u = self.ready()
        for hour, minute in ((21, 30), (0, 30), (5, 30), (12, 0)):
            with self.subTest(at=f"{hour}:{minute:02d}"):
                self.assertFalse(u.due(self.at(hour, minute)))

    def test_not_before_this_hub_s_own_minute_comes_round(self):
        u = self.ready()
        self.assertFalse(u.due(self.tonight(u, past=-1)))
        self.assertTrue(u.due(self.tonight(u, past=0)))

    def test_a_release_that_has_not_reached_this_house_yet_is_not_installed_in_the_night(self):
        u = self.ready()
        self.hub.settings.data["hub_id"] = "not-in-the-first-tenth"
        updates.CHANNEL.write_text(json.dumps({"rollout": {"v1.3.0": 0.0}}))
        self.assertFalse(u.due(self.tonight(u)))

    def test_a_hub_busy_at_its_own_minute_tries_again_later_the_same_night(self):
        # Rather than waiting a whole day, which is a day spent on the version that had the bug.
        u = self.ready()
        self.assertTrue(u.due(self.tonight(u, past=30)))

    def test_two_hubs_do_not_move_in_the_same_minute(self):
        # Ten thousand houses waking at two o'clock exactly would take a bad release together.
        seen = set()
        for hub_id in ("aaa", "bbb", "ccc", "ddd", "eee", "fff"):
            self.hub.settings.data["hub_id"] = hub_id
            seen.add(self.make(verified="1").minute_of_the_night())
        self.assertGreater(len(seen), 3)
        self.assertTrue(all(0 <= m < 180 for m in seen))

    def test_the_same_hub_uses_the_same_minute_every_night(self):
        # A household that notices the hub restarts at twenty past two is not wrong tomorrow.
        u = self.ready()
        self.assertEqual(u.minute_of_the_night(), self.make(verified="1").minute_of_the_night())

    # ---- and whether the house is asleep, which is not the same as the hour ----
    def test_somebody_is_still_up(self):
        u = self.ready()
        now = self.tonight(u)
        u.hub.log.last_user = lambda: now - 60
        self.assertFalse(u.due(now))
        u.hub.log.last_user = lambda: now - updates.QUIET - 60
        self.assertTrue(u.due(now))

    # ---- and what it will not walk into ----
    def test_nothing_to_install_is_not_a_reason_to_restart_the_house(self):
        u = self.make(version="v1.3.0", verified="1")
        u.latest = self.release("v1.3.0")()
        self.assertFalse(u.due(self.tonight(u)))

    def test_a_version_that_was_put_back_is_never_installed_unasked(self):
        u = self.ready()
        updates.STATE.write_text(json.dumps({"state": "reverted", "bad": "v1.3.0"}))
        self.assertFalse(u.due(self.tonight(u)))

    def test_it_does_not_walk_in_on_an_update_already_running(self):
        u = self.ready()
        updates.STATE.write_text(json.dumps({"state": "running", "started": 1}))
        self.assertFalse(u.due(self.tonight(u)))
        updates.STATE.unlink()
        u.request()                                                # somebody tapped a moment ago
        self.assertFalse(u.due(self.tonight(u)))

    def test_one_go_a_night(self):
        """An update that fails for a reason nothing here can see would otherwise run every five
        minutes until morning, restarting the house each time.

        The clock is patched rather than passed in: `due` takes a moment for the tests' benefit but
        `request` records the real one, and the two only mean anything together.
        """
        u = self.ready()
        now = self.tonight(u)
        with mock.patch("hub.updates.time.time", return_value=now):
            self.assertTrue(u.due())
            u.request(source="hub")
            updates.REQUEST.unlink()                               # the host has taken it
        with mock.patch("hub.updates.time.time", return_value=now + 600):
            self.assertFalse(u.due())                              # same night, an hour later: no
        with mock.patch("hub.updates.time.time", return_value=now + 86400):
            self.assertTrue(u.due())                               # the next night, same minute: yes

    def test_the_log_says_the_hub_did_it_and_not_somebody_in_the_house(self):
        u = self.ready()
        u.request(source="hub")
        self.assertEqual(self.hub.log.rows[-1]["source"], "hub")
        self.assertEqual(self.hub.log.rows[-1]["new"], "v1.3.0")


class OpeningThisHubTests(UpdateTest):
    """Opening This hub is the check: it asks GitHub now, unless the hub asked a few minutes ago."""
    def setUp(self):
        super().setUp()
        self.u = self.make(version="v1.2.0"); self.asked = 0
        def fetch():
            self.asked += 1; return self.release("v1.3.0")()
        self.u.fetch = fetch
        self.now = 1_000_000.0

    async def test_opening_the_page_asks(self):
        with mock.patch("hub.updates.time.time", return_value=self.now):
            self.assertTrue((await self.u.check_now())["available"])
        self.assertEqual(self.asked, 1)

    async def test_opening_it_again_a_minute_later_does_not_ask_twice(self):
        with mock.patch("hub.updates.time.time", return_value=self.now): await self.u.check_now()
        with mock.patch("hub.updates.time.time", return_value=self.now + 60): out = await self.u.check_now()
        self.assertEqual(self.asked, 1)
        self.assertTrue(out["available"])          # the answer from a minute ago, not nothing
        self.assertEqual(out["checked"], self.now)

    async def test_and_asks_again_once_the_few_minutes_are_up(self):
        with mock.patch("hub.updates.time.time", return_value=self.now): await self.u.check_now()
        with mock.patch("hub.updates.time.time", return_value=self.now + updates.RECHECK + 1): await self.u.check_now()
        self.assertEqual(self.asked, 2)

    async def test_a_failed_look_counts_as_a_look(self):
        def fetch():
            self.asked += 1; raise OSError("no internet")
        self.u.fetch = fetch
        with mock.patch("hub.updates.time.time", return_value=self.now): out = await self.u.check_now()
        self.assertIsNotNone(out["error"])
        with mock.patch("hub.updates.time.time", return_value=self.now + 60): await self.u.check_now()
        self.assertEqual(self.asked, 1)


class ProgressTests(UpdateTest):
    """Where the host has got to, while it is getting there.

    The point of the file is that the brain is ALIVE for nearly all of an update -- the code, the
    signature and the pull all happen with it running -- so the panel can say what is happening
    instead of throwing a blackout over a house that is merely downloading something.
    """
    def phases(self, *lines):
        updates.PROGRESS.write_text("".join(json.dumps(x) + "\n" for x in lines))

    def asked(self):
        updates.REQUEST.write_text(json.dumps({"at": 1, "to": "v1.3.0"}))

    def test_nothing_is_happening_and_the_panel_is_told_nothing(self):
        self.assertIsNone(self.make().progress())

    def test_the_second_between_the_tap_and_the_host_waking_up_still_says_something(self):
        """A tap that shows nothing for two seconds is a tap that feels like it missed."""
        self.asked()
        p = self.make().progress()
        self.assertEqual(p["phase"], "checking")
        self.assertFalse(p["dark"])
        self.assertEqual((p["step"], p["steps"]), (1, 5))

    def test_the_last_line_is_where_we_are_and_the_words_are_the_brain_s(self):
        self.asked()
        self.phases({"phase": "fetching", "at": 10}, {"phase": "downloading", "at": 20})
        p = self.make().progress()
        self.assertEqual(p["phase"], "downloading")
        self.assertEqual(p["says"], "Downloading it.")
        self.assertFalse(p["dark"])                       # the house still works; no overlay earned

    def test_a_phase_nobody_has_heard_of_is_dropped_on_the_floor(self):
        """The host names a phase from a fixed list and never a sentence. Anything that can write
        into the data volume could otherwise put words of its own on somebody's wall."""
        self.asked()
        self.phases({"phase": "downloading", "at": 10},
                    {"phase": "Your hub is infected. Call this number.", "at": 20})
        self.assertEqual(self.make().progress()["phase"], "downloading")

    def test_a_line_the_host_was_part_way_through_writing_does_not_take_the_panel_down(self):
        self.asked()
        updates.PROGRESS.write_text('{"phase": "fetching", "at": 10}\n{"phase": "downl')
        self.assertEqual(self.make().progress()["phase"], "fetching")

    def test_the_stretch_the_brain_is_not_there_for_says_so(self):
        for phase in ("restarting", "putting_back"):
            with self.subTest(phase=phase):
                self.asked(); self.phases({"phase": phase, "at": 10})
                self.assertTrue(self.make().progress()["dark"])

    def test_what_is_actually_moving_becomes_what_a_household_would_notice(self):
        """The sentence docs/updates.md has been promising since its first draft: said only when it
        is what is about to happen, which is the whole difference from assuming it."""
        self.asked()
        self.phases({"phase": "restarting", "at": 10, "moving": ["brain", "homeassistant"]})
        p = self.make().progress()
        self.assertEqual(p["moving"], ["brain", "homeassistant"])
        self.assertIn("For about a minute the wall switches still work but the app doesn’t.", p["notices"])

    def test_only_the_brain_moving_is_a_blink_and_earns_no_warning(self):
        self.asked()
        self.phases({"phase": "restarting", "at": 10, "moving": ["brain"]})
        self.assertEqual(self.make().progress()["notices"], [])

    def test_what_is_moving_is_remembered_after_the_line_that_carried_it(self):
        self.asked()
        self.phases({"phase": "downloading", "at": 10, "moving": ["homeassistant"]},
                    {"phase": "restarting", "at": 20})
        self.assertEqual(self.make().progress()["moving"], ["homeassistant"])

    def test_asking_again_clears_the_last_run_s_timeline(self):
        """Last time's phases are not this time's, and the panel starts reading the moment the
        request file exists."""
        self.phases({"phase": "proving", "at": 10})
        u = self.make()
        u.latest = {"version": "v1.3.0", "sha": "b" * 40}
        u.request()
        self.assertEqual(u.progress()["phase"], "checking")


class LearningTests(UpdateTest):
    """A hub that takes four minutes should say four minutes, not the figure from the maker's desk."""
    def ran(self, total=300, dark=50, state="done", ago=0.0, phases=True):
        """A finished run on the disk, `ago` seconds back. Relative to now on purpose: whether the
        receipt is still news is part of what is being tested."""
        fin = time.time() - ago
        updates.STATE.write_text(json.dumps({"state": state, "started": fin - total, "finished": fin}))
        marks = (("restarting", fin - dark), ("proving", fin)) if phases else ()
        updates.PROGRESS.write_text("".join(json.dumps({"phase": p, "at": at}) + "\n" for p, at in marks))

    def test_a_careful_guess_until_this_hub_has_measured_its_own(self):
        u = self.make()
        self.assertEqual(u.seconds(), updates.USUALLY["total"])
        self.assertEqual(u.seconds(dark=True), updates.USUALLY["dark"])

    def test_the_build_that_came_back_learns_both_figures_off_the_disk(self):
        self.ran()
        u = self.make()
        self.assertEqual(u.seconds(), 300)             # the whole run
        self.assertEqual(u.seconds(dark=True), 50)     # ...of which the wall was away for this much

    def test_it_is_learned_once_and_not_again_on_every_start(self):
        self.ran()
        self.make()
        before = len(self.hub.log.rows)
        self.make()
        self.assertEqual(len(self.hub.log.rows), before)

    def test_the_morning_receipt_says_the_house_did_it_and_how_long_it_took(self):
        """"What's new" says what changed. This is the line that says nobody in the house had to."""
        self.hub.log.add("home", "update", "v1.2.0", "v1.3.0", source="hub")
        self.ran()
        self.make()
        said = self.hub.log.rows[-1]
        self.assertEqual((said["new"], said["source"]), ("installed", "hub"))
        self.assertEqual(said["detail"]["took"], 300)
        self.assertEqual(said["detail"]["dark"], 50)

    def test_a_run_that_did_not_finish_teaches_nothing(self):
        for state in ("running", "failed", "reverted", "refused"):
            with self.subTest(state=state):
                self.hub.settings.data.pop("update_took", None)
                self.ran(state=state)
                self.assertEqual(self.make().seconds(), updates.USUALLY["total"])

    def test_a_figure_nobody_should_quote_is_not_learned(self):
        """Somebody's hub sat on a broken network for three hours. That is not what the next one costs."""
        self.ran(total=updates.TOOK + 60, phases=False)
        self.assertEqual(self.make().seconds(), updates.USUALLY["total"])

    def test_a_run_with_no_phases_written_still_learns_the_total(self):
        """An older host, or one whose progress file did not survive. Half an answer beats none."""
        self.ran(phases=False)
        u = self.make()
        self.assertEqual(u.seconds(), 300)
        self.assertEqual(u.seconds(dark=True), updates.USUALLY["dark"])


class TheSheetTests(UpdateTest):
    """What installing this would cost, in this house, right now -- and why anybody would want it."""
    def ready(self, **kw):
        u = self.make(**kw)
        u.latest = {"version": "v1.3.0", "sha": "b" * 40, "when": "", "title": "Quieter mornings",
                    "what": ["Speakers remember how loud you had them.", "The kitchen comes up faster."]}
        return u

    def test_it_names_the_version_and_says_why_in_the_release_s_own_words(self):
        s = self.ready().ask()
        self.assertEqual(s["title"], "Install v1.3.0?")
        self.assertIn("Speakers remember how loud you had them.", s["what"])

    def test_the_download_is_not_a_blackout_and_the_sheet_says_so(self):
        """The one thing an update may say more generously than a restart: for most of the wait the
        house is entirely usable, and a panel that implies otherwise is exaggerating."""
        s = self.ready().ask()
        self.assertIn("keep working", s["keeps"])
        self.assertLess(s["dark_seconds"], s["seconds"])

    def test_the_figures_are_this_house_s_once_it_has_any(self):
        self.hub.settings.set(update_took={"at": 1, "total": 480, "dark": 40})
        s = self.ready().ask()
        self.assertEqual((s["seconds"], s["dark_seconds"]), (480, 40))
        self.assertEqual(s["how_long"], "about 8 minutes")
        self.assertEqual(s["dark_how_long"], "about 40 seconds")

    def test_a_phone_that_is_not_in_the_house_is_told_what_it_is_risking(self):
        self.assertIsNone(self.ready().ask()["warn"])
        self.assertIn("Nobody is home", self.ready().ask(away=True)["warn"])

    def test_a_held_release_is_blocked_with_the_reason_rather_than_a_tap_that_goes_nowhere(self):
        u = self.ready()
        updates.CHANNEL.write_text(json.dumps({"made": 1, "hold": ["1.3.0"]}))
        self.assertIn("paused by the people who make the hub", u.ask()["blocked"])
        with self.assertRaises(ValueError): u.request()

    def test_one_at_a_time(self):
        u = self.ready()
        updates.STATE.write_text(json.dumps({"state": "running", "started": 1}))
        self.assertEqual(u.ask()["blocked"], "This hub is already installing an update.")
        with self.assertRaises(ValueError): u.request()


class TheDoorTests(unittest.TestCase):
    def test_asking_is_open_and_doing_is_not(self):
        """The same shape as /restart's, for the same reason: a sheet that demanded the code before
        it would say what the button does is a sheet nobody reads."""
        from hub.lock import needs_code
        self.assertFalse(needs_code("GET", "/update/ask"))
        self.assertTrue(needs_code("POST", "/update"))


class LearnsAfterTheFactTests(UpdateTest):
    """The host marks a run finished AFTER the brain it installed is already up.

    `update.sh` proves the house came back before it writes `done`, and the proof includes a settle --
    so the new brain has been running this code for a good minute by the time the run it came from is
    marked finished. Learning only at startup means a hub files every update's figures at the NEXT
    restart, which on a working house is days later. Found on a real hub, whose settings.json had no
    update_took in it at all a minute after a successful update.
    """
    def setUp(self):
        super().setUp()
        updates.STATE.write_text(json.dumps({"state": "running", "started": time.time() - 60}))

    def finished(self, ago=0.0):
        fin = time.time() - ago
        updates.STATE.write_text(json.dumps({"state": "done", "started": fin - 300, "finished": fin}))
        updates.PROGRESS.write_text("".join(json.dumps({"phase": p, "at": at}) + "\n"
                                            for p, at in (("restarting", fin - 50), ("proving", fin))))

    def test_a_brain_that_started_before_the_run_was_marked_done_still_learns(self):
        u = self.make()                                   # comes up while the host is still proving
        self.assertEqual(u.seconds(), updates.USUALLY["total"])
        self.finished()                                   # ...and the host finishes a minute later
        u._learn()                                        # which is what the tick is for
        self.assertEqual(u.seconds(), 300)
        self.assertEqual(u.seconds(dark=True), 50)

    def test_and_files_the_receipt_once_however_many_ticks_go_by(self):
        u = self.make()
        self.finished()
        for _ in range(5): u._learn()
        self.assertEqual(sum(1 for r in self.hub.log.rows if r["new"] == "installed"), 1)

    def test_a_run_that_finished_last_week_is_worth_keeping_and_not_worth_announcing(self):
        """A hub switched off for a week. The figures still stand; a line under Recent saying the
        house updated itself just now would be the one entry there that did not happen when it says."""
        self.finished(ago=updates.STALE + 60)
        u = self.make()
        self.assertEqual(u.seconds(), 300)                             # kept
        self.assertFalse([r for r in self.hub.log.rows if r["new"] == "installed"])   # not announced
