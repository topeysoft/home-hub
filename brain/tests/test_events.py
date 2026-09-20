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
