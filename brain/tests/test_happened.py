# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run from brain/: .venv/bin/python -m unittest -v"""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from hub.happened import lasted, spans, overnight
from tests.apptest import ApiTest

TZ = ZoneInfo("America/Chicago")


def at(y, mo, d, h, mi=0) -> float:
    return datetime(y, mo, d, h, mi, tzinfo=TZ).timestamp()


class Spans(unittest.TestCase):
    """The one idea in the file: a finding is the DISTANCE between two rows, which a timeline cannot
    show. Everything the page says about a light being left on comes out of this function."""

    def row(self, ts, new, old):
        return {"ts": ts, "new": new, "old": old}

    def test_a_thing_still_on_runs_to_the_end_of_the_window(self):
        rows = [self.row(at(2026, 9, 20, 9), "on", "off")]
        self.assertEqual(spans(rows, "on", at(2026, 9, 20, 8), at(2026, 9, 20, 18), ("on",)),
                         [(at(2026, 9, 20, 9), at(2026, 9, 20, 18))])

    def test_a_thing_that_was_already_on_when_the_window_opened(self):
        """The oldest row in the window carries what it was BEFORE in `old`, so no second query is
        needed to know the state the window opened in."""
        rows = [self.row(at(2026, 9, 20, 11), "off", "on")]
        self.assertEqual(spans(rows, "off", at(2026, 9, 20, 8), at(2026, 9, 20, 18), ("on",)),
                         [(at(2026, 9, 20, 8), at(2026, 9, 20, 11))])

    def test_no_rows_at_all_means_it_was_that_way_the_whole_time(self):
        """The commonest case for a light left on for a week, and the one a log of transitions is
        worst at: there is nothing written down in the window to find."""
        self.assertEqual(spans([], "on", at(2026, 9, 20, 8), at(2026, 9, 20, 18), ("on",)),
                         [(at(2026, 9, 20, 8), at(2026, 9, 20, 18))])
        self.assertEqual(spans([], "off", at(2026, 9, 20, 8), at(2026, 9, 20, 18), ("on",)), [])

    def test_several_spans_come_back_newest_first(self):
        rows = [self.row(at(2026, 9, 20, 15), "on", "off"),
                self.row(at(2026, 9, 20, 12), "off", "on"),
                self.row(at(2026, 9, 20, 10), "on", "off")]
        self.assertEqual(spans(rows, "on", at(2026, 9, 20, 8), at(2026, 9, 20, 18), ("on",)),
                         [(at(2026, 9, 20, 15), at(2026, 9, 20, 18)),
                          (at(2026, 9, 20, 10), at(2026, 9, 20, 12))])

    def test_two_rows_in_the_same_second_cannot_invent_a_span(self):
        t = at(2026, 9, 20, 12)
        rows = [self.row(t, "on", "off"), self.row(t, "off", "on")]
        for a, b in spans(rows, "on", at(2026, 9, 20, 8), at(2026, 9, 20, 18), ("on",)):
            self.assertGreater(b, a)

    def test_a_lock_uses_the_same_walk(self):
        rows = [self.row(at(2026, 9, 20, 6, 40), "locked", "unlocked"),
                self.row(at(2026, 9, 19, 23, 3), "unlocked", "locked")]
        self.assertEqual(spans(rows, "locked", at(2026, 9, 19, 18), at(2026, 9, 20, 18), ("unlocked",)),
                         [(at(2026, 9, 19, 23, 3), at(2026, 9, 20, 6, 40))])


class Words(unittest.TestCase):
    def test_a_duration_is_never_a_number_somebody_has_to_convert(self):
        self.assertEqual(lasted(90), "2 minutes")
        self.assertEqual(lasted(60), "a minute")
        self.assertEqual(lasted(3600), "an hour")
        self.assertEqual(lasted(7 * 3600 + 600), "7 hours")
        self.assertEqual(lasted(26 * 3600), "a day")

    def test_overnight_is_the_whole_point_of_the_lock_line(self):
        self.assertTrue(overnight(at(2026, 9, 19, 23, 3), at(2026, 9, 20, 6, 40), TZ))
        self.assertFalse(overnight(at(2026, 9, 20, 9), at(2026, 9, 20, 18), TZ))

    def test_an_evening_that_stops_before_the_small_hours_is_not_overnight(self):
        self.assertFalse(overnight(at(2026, 9, 19, 19), at(2026, 9, 19, 22, 30), TZ))


class ThePage(ApiTest):
    """Against a real house: the Ceiling light is on, the Front door is locked (apptest.house())."""

    def aged(self, kind, subject, new, hours_ago, old=None, source="device", who=None):
        import time
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.db.execute(
            "INSERT INTO events(ts,kind,subject,old,new,source,who) VALUES(?,?,?,?,?,?,?)",
            (time.time() - hours_ago * 3600, kind, subject, old, new, source, who))
        api.hub.log.db.commit()

    def test_a_light_on_all_day_leads_and_carries_the_only_button(self):
        self.aged("state", "light.ceiling", "on", 10, old="off")
        self.aged("presence", "home", "nobody", 11)
        self.aged("presence", "home", "somebody", 0.2)
        page = self.client.get("/happened").json()
        still = next(g for g in page["groups"] if g["id"] == "still")
        self.assertEqual(still["label"], "Still on")
        row = still["items"][0]
        self.assertIn("Ceiling light has been on for 10 hours", row["text"])
        self.assertEqual(row["acts"], [{"do": "Turn off", "act": "device", "to": "light.ceiling", "arg": "off"}])

    def test_what_is_over_carries_no_buttons(self):
        """A door that locked itself at 6:40am is not a job, and offering an act against it would be
        offering to do something that has already happened."""
        self.aged("presence", "home", "nobody", 20)
        self.aged("state", "lock.front", "unlocked", 14, old="locked")
        self.aged("state", "lock.front", "locked", 7, old="unlocked")
        page = self.client.get("/happened").json()
        over = next(g for g in page["groups"] if g["id"] == "over")
        row = next(i for i in over["items"] if i["subject"] == "lock.front")
        self.assertIn("was unlocked for 7 hours", row["text"])
        self.assertIn("It is locked now.", row["text"])
        self.assertEqual(row["acts"], [])

    def test_something_on_for_ten_minutes_is_not_news(self):
        self.aged("state", "light.kitchen", "on", 0.15, old="off")
        page = self.client.get("/happened").json()
        subjects = [i["subject"] for g in page["groups"] for i in g["items"]]
        self.assertNotIn("light.kitchen", subjects)

    def test_the_heading_is_named_by_the_brain_and_not_the_panel(self):
        """'Still on' over a door that is still unlocked would be a lie the panel could not know it
        was telling, so this file names the group from what is actually in it."""
        self.aged("presence", "home", "nobody", 12)
        self.aged("state", "light.ceiling", "on", 10, old="off")
        self.aged("state", "lock.front", "unlocked", 9, old="locked")
        api = __import__("hub.api", fromlist=["api"])
        api.hub.home.devices["lock.front"].state = "unlocked"
        page = self.client.get("/happened").json()
        still = next(g for g in page["groups"] if g["id"] == "still")
        self.assertEqual(still["label"], "Still on, and still unlocked")

    def test_a_door_sensor_is_offered_the_room_because_nothing_shuts_it_over_the_network(self):
        api = __import__("hub.api", fromlist=["api"])
        d = api.hub.home.devices["binary_sensor.kitchen_motion"]
        d.capability = "contact"; d.state = "on"
        self.aged("state", d.id, "on", 5, old="off")
        page = self.client.get("/happened").json()
        row = next(i for g in page["groups"] for i in g["items"] if i["subject"] == d.id)
        self.assertEqual(row["acts"], [{"do": "Show me", "act": "room", "to": "kitchen"}])

    def test_the_lede_says_when_the_house_was_empty(self):
        self.aged("presence", "home", "nobody", 9)
        self.aged("presence", "home", "somebody", 0.1)
        self.assertRegex(self.client.get("/happened").json()["lede"], r"^You were out from .+ until .+\.$")

    def test_a_house_with_nobody_set_up_does_not_invent_a_window(self):
        """Nothing is claimed that cannot be known: with no presence rows there is no way to know when
        anybody left, so the page says how far back it looked instead of guessing."""
        self.assertEqual(self.client.get("/happened").json()["lede"],
                         "Here is what the house has been doing since yesterday.")

    def test_a_phone_that_joined_is_on_the_page(self):
        self.aged("phone", "p1", "joined", 40, source="user")
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.db.execute("UPDATE events SET detail=? WHERE subject='p1'", ('{"name": "Ada\'s iPad"}',))
        api.hub.log.db.commit()
        page = self.client.get("/happened").json()
        people = next(g for g in page["groups"] if g["id"] == "people")
        self.assertEqual(people["items"][0]["text"], "Ada's iPad joined the house.")


class WhoChangedWhat(ApiTest):
    def test_it_needs_the_code(self):
        self.client.post("/setup/pin", json={"pin": "4321"})
        self.assertEqual(self.client.get("/happened/changes").status_code, 401)
        r = self.client.get("/happened/changes", headers={"x-hub-code": "4321"})
        self.assertEqual(r.status_code, 200)

    def test_a_rename_reads_as_a_sentence_with_a_person_in_front_of_it(self):
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.add("home", "light.ceiling", "Ceiling light", "Reading lamp", source="user", who="Temi's iPhone")
        rows = self.client.get("/happened/changes").json()["rows"]
        self.assertEqual((rows[0]["who"], rows[0]["text"]), ("Temi's iPhone", "renamed Ceiling light to Reading lamp."))
        self.assertTrue(rows[0]["named"])

    def test_the_house_acting_on_its_own_says_so_rather_than_naming_anybody(self):
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.add("home", "update", "0.8.1", "installed", source="hub")
        rows = self.client.get("/happened/changes").json()["rows"]
        self.assertEqual((rows[0]["who"], rows[0]["text"]), ("The hub", "installed 0.8.1."))
        self.assertFalse(rows[0]["named"])

    def test_a_change_with_no_phone_behind_it_is_someone_at_the_wall(self):
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.add("home", "room", None, "Landing", source="user")
        rows = self.client.get("/happened/changes").json()["rows"]
        self.assertEqual((rows[0]["who"], rows[0]["text"]), ("Someone at the wall", "added the room Landing."))

    def test_turning_a_light_on_is_not_a_change_to_the_house(self):
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.add("action", "light.ceiling", None, "off", source="user", who="Temi's iPhone")
        api.hub.log.add("state", "light.ceiling", "on", "off", source="device")
        self.assertEqual(self.client.get("/happened/changes").json()["rows"], [])

    def test_a_phone_let_in_for_the_weekend_says_so(self):
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.add("phone", "p2", None, "joined", source="user", who="The wall",
                        detail={"name": "Sam's phone", "how": "wall", "span": "weekend"})
        rows = self.client.get("/happened/changes").json()["rows"]
        self.assertEqual(rows[0]["text"], "let Sam's phone into the house for the weekend.")

    def test_before_the_code_nothing_can_be_named_and_the_page_says_so(self):
        api = __import__("hub.api", fromlist=["api"])
        self.client.post("/setup/pin", json={"pin": "4321"})
        page = self.client.get("/happened/changes", headers={"x-hub-code": "4321"}).json()
        self.assertIsNotNone(page["coded_since"])
        self.assertIsNotNone(page["coded_when"])

    def test_an_unlocked_house_claims_no_date(self):
        self.assertIsNone(self.client.get("/happened/changes").json()["coded_since"])


if __name__ == "__main__":
    unittest.main()


class TheDoorsHint(ApiTest):
    """The one line under the door is what makes somebody open it, so the brain writes it too."""

    def aged(self, kind, subject, new, hours_ago, old=None):
        import time
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.db.execute("INSERT INTO events(ts,kind,subject,old,new,source) VALUES(?,?,?,?,?,?)",
                               (time.time() - hours_ago * 3600, kind, subject, old, new, "device"))
        api.hub.log.db.commit()

    def test_it_counts_what_is_still_on(self):
        self.aged("state", "light.ceiling", "on", 9, old="off")
        self.assertEqual(self.client.get("/happened").json()["hint"], "1 thing still on")

    def test_it_falls_back_to_what_is_over(self):
        api = __import__("hub.api", fromlist=["api"])
        api.hub.home.devices["light.ceiling"].state = "off"      # the house ships with it on
        self.aged("state", "lock.front", "unlocked", 14, old="locked")
        self.aged("state", "lock.front", "locked", 7, old="unlocked")
        self.assertEqual(self.client.get("/happened").json()["hint"], "1 thing while you were out")

    def test_a_quiet_house_says_so_rather_than_nothing(self):
        api = __import__("hub.api", fromlist=["api"])
        api.hub.home.devices["light.ceiling"].state = "off"
        self.assertEqual(self.client.get("/happened").json()["hint"], "Nothing to catch up on")


class TheArrangement(ApiTest):
    """What design/happened/Main.dc.html drew, pinned so it cannot drift.

    The picture is the spec (AGENTS.md section 1). The ranking IS the design here -- it is the whole
    difference between this page and design/happened/Sections.dc.html, which is the same facts flat
    and was rejected for reading as a report you have to finish before you know if anything wants you.
    """

    def aged(self, kind, subject, new, hours_ago, old=None, source="device"):
        import time
        api = __import__("hub.api", fromlist=["api"])
        api.hub.log.db.execute("INSERT INTO events(ts,kind,subject,old,new,source) VALUES(?,?,?,?,?,?)",
                               (time.time() - hours_ago * 3600, kind, subject, old, new, source))
        api.hub.log.db.commit()

    def a_full_house(self):
        api = __import__("hub.api", fromlist=["api"])
        self.aged("presence", "home", "nobody", 12)
        self.aged("presence", "home", "somebody", 0.2)
        self.aged("state", "light.ceiling", "on", 10, old="off")       # still on, the longer of the two
        api.hub.home.devices["light.kitchen"].state = "on"
        self.aged("state", "light.kitchen", "on", 6, old="off")        # still on, the shorter
        self.aged("state", "lock.front", "unlocked", 11, old="locked")  # over
        self.aged("state", "lock.front", "locked", 4, old="unlocked")
        self.aged("phone", "p1", "joined", 30, source="user")
        return self.client.get("/happened").json()

    def test_the_groups_come_in_the_order_the_board_drew_them(self):
        self.assertEqual([g["id"] for g in self.a_full_house()["groups"]], ["still", "over", "people"])

    def test_only_what_is_still_true_carries_a_button(self):
        """A door that locked itself four hours ago is not a job. A button against it would offer to
        do something that has already happened, which is the rule the whole ranking rests on."""
        page = self.a_full_house()
        for g in page["groups"]:
            for i in g["items"]:
                if g["id"] == "still": self.assertTrue(i["acts"], i["text"])
                else: self.assertEqual(i["acts"], [], i["text"])

    def test_the_longest_standing_finding_leads(self):
        still = next(g for g in self.a_full_house()["groups"] if g["id"] == "still")
        self.assertEqual([i["subject"] for i in still["items"]], ["light.ceiling", "light.kitchen"])
        self.assertGreater(still["items"][0]["seconds"], still["items"][1]["seconds"])

    def test_an_empty_group_is_left_out_rather_than_drawn_empty(self):
        """A heading with nothing under it teaches somebody to stop reading the headings."""
        api = __import__("hub.api", fromlist=["api"])
        api.hub.home.devices["light.ceiling"].state = "off"
        self.assertEqual(self.client.get("/happened").json()["groups"], [])
