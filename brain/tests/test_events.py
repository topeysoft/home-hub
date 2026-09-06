"""Run from brain/: .venv/bin/python -m unittest -v"""
import unittest
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
