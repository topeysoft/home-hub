# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turning it off and on again: the ladder, the gate on it, and the two things it must never become.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json, time, unittest
from unittest import mock

from hub import restart as restart_mod, updates as updates_mod
from hub.lock import needs_code
from hub.phones import COOKIE
from tests.apptest import ApiTest


class WhatItCosts(unittest.TestCase):
    def test_asking_is_open_and_doing_is_not(self):
        """A sheet that demanded the code before it would say what the button does is a sheet nobody reads."""
        self.assertFalse(needs_code("GET", "/restart"))
        self.assertTrue(needs_code("POST", "/restart"))


class Restarting(ApiTest):
    def setUp(self):
        super().setUp()
        self.code = self.lock_the_house()
        self.head = {"x-hub-code": self.code}
        # The wall: the screen that set the house up, and the one every test below taps unless it says otherwise.
        _, token = self.hub.phones.from_setup()
        self.client.cookies.set(COOKIE, token)
        self.went = mock.patch.object(restart_mod.Restart, "quit")   # nothing in a test raises SIGTERM at itself
        self.quit = self.went.start(); self.addCleanup(self.went.stop)

    # ---- the sheet ----
    def test_the_sheet_says_what_keeps_working_first(self):
        s = self.client.get("/restart").json()
        self.assertEqual(s["rung"], "hub")
        self.assertEqual(s["keeps"], "Lights and switches keep working.")
        self.assertIn("seconds", s["how_long"])
        self.assertIsNone(s["blocked"])
        self.assertTrue(s["may"])

    def test_what_stops_is_only_said_where_it_is_true(self):
        """A sentence true of some house is how a panel earns the reputation of exaggerating."""
        self.assertNotIn("Apple Home, Google Home and Alexa say “no response” until it's back.",
                         self.client.get("/restart").json()["stops"])
        self.hub.share.set(on=True)
        self.assertIn("Apple Home, Google Home and Alexa say “no response” until it's back.",
                      self.client.get("/restart").json()["stops"])

    def test_a_pairing_in_flight_is_named_before_it_is_lost(self):
        self.hub.pair.session = {"kind": "zigbee", "state": "listening", "text": "", "device": None, "needs": None, "until": None}
        self.assertIn("The house is waiting for a new device to pair; you'll need to start that again.",
                      self.client.get("/restart").json()["flight"])

    def test_a_deeper_rung_costs_more_and_says_so(self):
        s = self.client.get("/restart", params={"rung": "machine"}).json()
        self.assertEqual(s["yes"], "Restart the little computer")
        self.assertIn("Everything the hub talks to goes quiet until it's back — lights, sensors and the radios.", s["stops"])

    # ---- the doing ----
    def test_the_hub_rung_goes_by_itself_and_needs_no_host(self):
        r = self.client.post("/restart", json={"rung": "hub"}, headers=self.head)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["rung"], "hub")
        self.quit.assert_called_once()
        self.assertFalse(restart_mod.REQUEST.exists())         # nothing was asked of the host
        self.assertEqual(json.loads(restart_mod.STATE.read_text())["rung"], "hub")

    def test_a_deeper_rung_asks_the_host_for_a_word_and_never_a_command(self):
        r = self.client.post("/restart", json={"rung": "everything"}, headers=self.head)
        self.assertEqual(r.status_code, 200)
        self.quit.assert_not_called()
        asked = json.loads(restart_mod.REQUEST.read_text())
        self.assertEqual(asked["rung"], "everything")
        self.assertEqual(set(asked) - {"at"}, {"rung"})         # a rung, and nothing else to act on

    def test_a_rung_the_hub_does_not_know_is_refused(self):
        r = self.client.post("/restart", json={"rung": "; reboot"}, headers=self.head)
        self.assertEqual(r.status_code, 409)
        self.assertFalse(restart_mod.REQUEST.exists())

    def test_who_asked_is_written_down(self):
        self.client.post("/restart", json={"rung": "hub"}, headers=self.head)
        e = self.hub.log.recent(limit=5, subject="restart")[0]
        self.assertEqual((e["old"], e["new"], e["source"]), ("hub", "asked", "user"))
        self.assertEqual(json.loads(e["detail"])["who"], "This wall")   # the phone row names itself; "the wall" is only the fallback

    # ---- and what it must not become ----
    def test_it_will_not_happen_during_an_update(self):
        """The panel hides the button too; this is what answers a phone whose page is an hour old."""
        updates_mod.STATE.write_text(json.dumps({"state": "running"}))
        self.assertIn("installing an update", self.client.get("/restart").json()["blocked"])
        r = self.client.post("/restart", json={"rung": "hub"}, headers=self.head)
        self.assertEqual(r.status_code, 409)
        self.quit.assert_not_called()

    def test_one_at_a_time(self):
        self.client.post("/restart", json={"rung": "hub"}, headers=self.head)
        r = self.client.post("/restart", json={"rung": "hub"}, headers=self.head)
        self.assertEqual(r.status_code, 409)
        self.assertIn("already restarting", r.json()["detail"])
        self.quit.assert_called_once()

    def test_a_restart_that_never_came_back_stops_standing_in_the_way(self):
        """The alternative is a house that can never be restarted again."""
        restart_mod.STATE.write_text(json.dumps({"rung": "hub", "at": time.time() - restart_mod.IN_FLIGHT - 1}))
        self.assertEqual(self.client.post("/restart", json={"rung": "hub"}, headers=self.head).status_code, 200)

    def test_it_still_needs_the_code(self):
        self.assertEqual(self.client.post("/restart", json={"rung": "hub"}).status_code, 401)
        self.quit.assert_not_called()

    def test_a_phone_let_in_at_the_wall_holds_the_code_and_still_cannot(self):
        """The code is one secret the whole house shares. A guest runs the house; it does not take it down."""
        ask = self.client.post("/phones/ask", json={"name": "Guest"}).json()
        self.hub.phones.from_setup()
        self.hub.phones.allow(ask["id"], "day")
        _, _, token = self.hub.phones.claim(ask["id"])
        self.client.cookies.set(COOKIE, token)
        self.assertFalse(self.client.get("/restart").json()["may"])      # and the sheet says so rather than lying
        r = self.client.post("/restart", json={"rung": "hub"}, headers=self.head)
        self.assertEqual(r.status_code, 403)
        self.quit.assert_not_called()

    def test_a_hub_with_no_code_locks_nothing(self):
        self.hub.lock.set("")
        self.client.cookies.clear()
        self.assertEqual(self.client.post("/restart", json={"rung": "hub"}).status_code, 200)

    # ---- the ladder revealing itself ----
    def test_after_three_in_an_hour_the_same_rung_stops_being_the_answer(self):
        for _ in range(3): self.hub.log.add("home", "restart", "hub", "asked", source="user")
        s = self.client.get("/restart").json()
        self.assertEqual(s["harder"], "everything")
        self.assertIn("restarting isn't fixing", s["weary"])

    def test_coming_back_learns_how_long_this_hub_actually_takes(self):
        """A hub on a tired card that takes ninety seconds should say ninety seconds, not the figure
        that was true on the maker's desk."""
        restart_mod.STATE.write_text(json.dumps({"rung": "hub", "at": time.time() - 92, "who": "the wall"}))
        again = restart_mod.Restart(self.hub)
        self.assertEqual(again.seconds("hub"), 92)
        self.assertEqual(again.ask("hub")["how_long"], "about 2 minutes")
        self.assertFalse(restart_mod.STATE.exists())            # read once, and not counted twice
        e = self.hub.log.recent(limit=5, subject="restart")[0]
        self.assertEqual((e["old"], e["new"]), ("hub", "back"))

    def test_a_hub_that_was_pulled_out_of_the_wall_learns_nothing(self):
        """It did not restart. It stopped, and there is nothing on the floor to read."""
        self.assertEqual(restart_mod.Restart(self.hub).seconds("hub"), restart_mod.USUALLY["hub"])


class FromAway(Restarting):
    """The rung that can strand somebody. Allowed, because the household that most needs it is the one
    furthest from the socket -- and told, because nobody is there to reach the plug."""
    def setUp(self):
        super().setUp()
        p = self.hub.phones.data[0]
        p["remote"] = True                                    # somebody at the wall let this phone out
        self.hub.phones._save()
        self.away = {**self.head, "x-hub-via": "relay"}

    def test_the_machine_asks_once_more_and_then_allows_it(self):
        r = self.client.post("/restart", json={"rung": "machine"}, headers=self.away)
        self.assertEqual(r.status_code, 409)
        self.assertIn("Nobody is home to unplug it", r.json()["detail"])
        self.assertFalse(restart_mod.REQUEST.exists())
        r = self.client.post("/restart", json={"rung": "machine", "understood": True}, headers=self.away)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(json.loads(restart_mod.REQUEST.read_text())["rung"], "machine")

    def test_the_shallower_rungs_are_not_nagged_about(self):
        self.assertEqual(self.client.post("/restart", json={"rung": "hub"}, headers=self.away).status_code, 200)

    def test_an_away_phone_is_told_it_loses_the_house(self):
        self.assertIn("This phone loses the house until it's back.",
                      self.client.get("/restart", headers={"x-hub-via": "relay"}).json()["stops"])
