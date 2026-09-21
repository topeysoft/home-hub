# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run from brain/: .venv/bin/python -m unittest -v"""
import sqlite3, tempfile, unittest
from pathlib import Path

from hub.events import EventLog


class RecentTests(unittest.TestCase):
    def setUp(self):
        self.log = EventLog(":memory:")
        self.log.add("intent", "hall", "empty", "occupied", source="rule", detail={"rule": "hall-evening"})
        self.log.add("state", "light.hall", "off", "on")
        self.log.add("intent", "home", "occupied", "asleep", source="user")
        self.log.add("held", "den", "movie", "empty", source="rule")

    def tearDown(self): self.log.db.close()

    def test_one_subject(self):
        rows = self.log.recent(10, subject="hall")
        self.assertEqual([r["kind"] for r in rows], ["intent"])
        self.assertEqual(rows[0]["detail"], '{"rule": "hall-evening"}')

    def test_a_room_and_the_house_together_newest_first(self):
        rows = self.log.recent(10, subject=("hall", "home"), kinds=("intent", "held"))
        self.assertEqual([(r["subject"], r["new"]) for r in rows], [("home", "asleep"), ("hall", "occupied")])

    def test_kinds_filter_and_limit(self):
        rows = self.log.recent(1, kinds=("intent", "held"))
        self.assertEqual([r["kind"] for r in rows], ["held"])


if __name__ == "__main__":
    unittest.main()


class TheDiaryCannotFailTheHouse(unittest.TestCase):
    """A line of the diary is not the thing it is about.

    19 Sep 2026: a bridge had its firmware written, its Wi-Fi configured and its keys handed over,
    and the panel said "That did not work. / database is locked" -- because the one INSERT saying
    so lost a race with something else holding the file. 75 places in the house call add(), most of
    them inside a `try` that belongs to something else entirely."""

    def test_add_never_raises_however_broken_the_database_is(self):
        log = EventLog(":memory:")
        log.db.close()                                  # the worst thing that can happen to it
        log.add("bridge", "c8ebba", None, "set up", source="user")   # and it is not the caller's problem

    def test_the_line_is_lost_and_nothing_else_is(self):
        with tempfile.TemporaryDirectory() as d:
            log = EventLog(Path(d) / "events.db")
            log.add("bridge", "c8ebba", None, "set up", source="user")
            self.assertEqual(len(log.recent(10)), 1)
            log.db.close()
            log.add("bridge", "c8ebba", None, "placed", source="user")   # goes nowhere, quietly
            log.db.close()

    def test_readers_do_not_block_the_writer(self):
        """WAL, so the assistant reading five thousand rows and the backup copying the file cannot
        shut an INSERT out. Under the rollback journal either of them could, for as long as it ran."""
        with tempfile.TemporaryDirectory() as d:
            log = EventLog(Path(d) / "events.db")
            self.assertEqual(log.db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            self.assertGreaterEqual(log.db.execute("PRAGMA busy_timeout").fetchone()[0], 30000)
            log.db.close()

    def test_a_database_the_hub_already_has_converts_on_the_next_start(self):
        """Every hub in the field has one of these in rollback mode with a year of rows in it. The
        switch happens when the brain next opens it, and nothing in it moves."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "events.db"
            old = sqlite3.connect(path)
            old.execute("CREATE TABLE events(ts REAL, kind TEXT, subject TEXT, old TEXT, new TEXT, source TEXT, detail TEXT)")
            old.execute("INSERT INTO events VALUES(1,?,?,NULL,?,?,NULL)", ("bridge", "c0e33a", "set up", "user"))
            old.commit()
            self.assertEqual(old.execute("PRAGMA journal_mode").fetchone()[0], "delete")
            old.close()

            log = EventLog(path)
            self.assertEqual(log.db.execute("PRAGMA journal_mode").fetchone()[0], "wal")
            log.add("bridge", "c8ebba", None, "set up", source="user")
            self.assertEqual([r["subject"] for r in log.recent(10)], ["c8ebba", "c0e33a"])   # and the year is still there
            log.db.close()

    def test_a_second_connection_writing_does_not_lose_the_line(self):
        """What a hub update looks like from here: two processes, one file, both writing."""
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "events.db"
            log = EventLog(path)
            other = sqlite3.connect(path, timeout=30)
            other.execute("BEGIN IMMEDIATE")            # the other brain, mid-write
            other.commit()                              # ...and done, as it would be in under 30s
            log.add("bridge", "c8ebba", None, "set up", source="user")
            self.assertEqual(log.recent(10)[0]["new"], "set up")
            other.close(); log.db.close()


class Keeping(unittest.TestCase):
    """20 Sep 2026: the log was unbounded. A hub that had run a year held a year of every motion
    sensor in the house in one file, on eMMC, and it rode every backup."""

    def setUp(self):
        self.log = EventLog(":memory:")
        self.now = 1_800_000_000.0

    def tearDown(self): self.log.db.close()

    def at(self, days_ago, kind, subject, new, old=None, source="device"):
        """A row aged on arrival; add() can only ever write `now`."""
        self.log.db.execute("INSERT INTO events(ts,kind,subject,old,new,source) VALUES(?,?,?,?,?,?)",
                            (self.now - days_ago * 86400, kind, subject, old, new, source))
        self.log.db.commit()

    def kinds(self):
        return sorted(r[0] for r in self.log.db.execute("SELECT kind FROM events").fetchall())

    def test_chatter_goes_after_a_month_and_house_news_does_not(self):
        self.at(40, "state", "light.hall", "on")
        self.at(35, "state", "light.hall", "on")     # the newer copy is the keeper; this pair is the sweep
        self.at(40, "home", "hallway", "Landing", source="user")
        self.log.prune(self.now)
        self.assertEqual(self.kinds(), ["home", "state"])
        self.assertEqual(self.log.db.execute("SELECT COUNT(*) FROM events WHERE kind='state'").fetchone()[0], 1)

    def test_house_news_goes_after_a_year(self):
        self.at(400, "home", "hallway", "Landing", source="user")
        self.at(400, "home", "kitchen", "Kitchen", source="user")
        self.log.prune(self.now)
        self.assertEqual(self.kinds(), [])

    def test_a_kind_nobody_listed_keeps_the_long_time(self):
        """A kind added next year is likelier to be house news than chatter, so the default is a year."""
        self.at(40, "somethingnew", "x", "y")
        self.log.prune(self.now)
        self.assertEqual(self.kinds(), ["somethingnew"])
        self.at(400, "somethingnew", "z", "y")
        self.log.prune(self.now)
        self.assertEqual(self.kinds(), ["somethingnew"])   # the 40-day one; the 400-day one went

    def test_the_newest_row_for_a_value_survives_any_age(self):
        """THE rule. health.py asks "how long has this been offline" and rules.seed asks "when did
        this room last see motion", and both are last_by_subject -- which must answer the same after
        a prune as before it, or a device that went quiet in March starts claiming it went quiet today."""
        self.at(300, "state", "light.hall", "unavailable")      # went quiet ten months ago
        self.at(299, "state", "binary_sensor.kitchen", "on")    # and a floor that has not moved since
        before = self.log.last_by_subject("state", "unavailable")
        self.log.prune(self.now)
        self.assertEqual(self.log.last_by_subject("state", "unavailable"), before)
        self.assertEqual(self.log.last_by_subject("state", "on"),
                         {"binary_sensor.kitchen": self.now - 299 * 86400})

    def test_it_keeps_the_newest_of_each_value_and_not_merely_the_newest_row(self):
        """A light that went quiet and came back has 'on' as its newest row. Keeping only that would
        drop the 'unavailable' the health page reads -- so the rule is per (kind, subject, new)."""
        self.at(200, "state", "light.hall", "unavailable")
        self.at(199, "state", "light.hall", "on")
        self.log.prune(self.now)
        self.assertEqual(sorted(r[0] for r in self.log.db.execute("SELECT new FROM events")), ["on", "unavailable"])

    def test_the_old_copies_go_and_one_stays(self):
        for d in (200, 150, 100, 40):
            self.at(d, "state", "light.hall", "on")
        self.log.prune(self.now)
        rows = self.log.db.execute("SELECT ts FROM events").fetchall()
        self.assertEqual([r[0] for r in rows], [self.now - 40 * 86400])

    def test_the_cap_takes_the_oldest_and_still_spares_the_keepers(self):
        import hub.events as ev
        was, ev.CAP = ev.CAP, 5
        try:
            self.at(300, "state", "light.old", "unavailable")      # a keeper, and the oldest row there is
            for i in range(20): self.at(1, "state", f"light.{i}", "on")
            self.log.prune(self.now)
            left = self.log.db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            self.assertLessEqual(left, 21)                          # every row is a keeper, so the cap cannot bite
            self.assertIn("light.old", [r[0] for r in self.log.db.execute("SELECT subject FROM events")])
        finally: ev.CAP = was

    def test_pruning_a_broken_database_is_not_the_callers_problem(self):
        self.log.db.close()
        self.assertEqual(self.log.prune(self.now), 0)


class WhoAsked(unittest.TestCase):
    """`source` says what sort of thing acted; `who` says which one, and only for a person."""

    def setUp(self): self.log = EventLog(":memory:")
    def tearDown(self): self.log.db.close()

    def test_a_person_is_named_from_the_request(self):
        from hub.events import asked_by
        t = asked_by.set("Temi's iPhone")
        try: self.log.add("home", "hallway", None, "Landing", source="user")
        finally: asked_by.reset(t)
        self.assertEqual(self.log.recent(1)[0]["who"], "Temi's iPhone")

    def test_a_rule_is_not_named_however_it_was_started(self):
        """A task spawned mid-request inherits the request's context and outlives it. Attributing its
        writes to whoever last tapped something would put a name to work they did not do."""
        from hub.events import asked_by
        t = asked_by.set("Temi's iPhone")
        try:
            self.log.add("intent", "hall", None, "occupied", source="rule")
            self.log.add("state", "light.hall", "off", "on", source="device")
            self.log.add("home", "registry", None, "rebuilt", source="system")
        finally: asked_by.reset(t)
        self.assertEqual([r["who"] for r in self.log.recent(9)], [None, None, None])

    def test_a_caller_that_knows_better_than_the_request_wins(self):
        self.log.add("home", "update", None, "installed", source="user", who="the hub, overnight")
        self.assertEqual(self.log.recent(1)[0]["who"], "the hub, overnight")

    def test_a_house_with_no_code_says_nothing_rather_than_guessing(self):
        self.log.add("home", "hallway", None, "Landing", source="user")   # nothing set it: no code, no phones
        self.assertIsNone(self.log.recent(1)[0]["who"])

    def test_the_column_arrives_on_a_database_that_predates_it(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "events.db"
            old = sqlite3.connect(path)
            old.execute("CREATE TABLE events(ts REAL, kind TEXT, subject TEXT, old TEXT, new TEXT, source TEXT, detail TEXT)")
            old.execute("INSERT INTO events VALUES(1,'home','hallway',NULL,'Landing','user',NULL)")
            old.commit(); old.close()

            log = EventLog(path)
            log.add("home", "kitchen", None, "Scullery", source="user", who="Temi's iPhone")
            rows = log.recent(10)
            self.assertEqual([r["who"] for r in rows], ["Temi's iPhone", None])   # and the old row is honest
            log.db.close()


class AWindow(unittest.TestCase):
    """Without a range the only way to reach yesterday was to pull thousands of rows and drop most."""

    def setUp(self):
        self.log = EventLog(":memory:")
        self.now = 1_800_000_000.0
        for hours, new in ((30, "out"), (20, "back"), (2, "out")):
            self.log.db.execute("INSERT INTO events(ts,kind,subject,new,source) VALUES(?,?,?,?,?)",
                                (self.now - hours * 3600, "presence", "home", new, "device"))
        self.log.db.commit()

    def tearDown(self): self.log.db.close()

    def test_since_and_until_cut_the_window(self):
        rows = self.log.recent(10, since=self.now - 24 * 3600, until=self.now - 10 * 3600)
        self.assertEqual([r["new"] for r in rows], ["back"])

    def test_since_alone_is_everything_after_it(self):
        rows = self.log.recent(10, since=self.now - 24 * 3600)
        self.assertEqual([r["new"] for r in rows], ["out", "back"])
