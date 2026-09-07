"""Run from brain/: .venv/bin/python -m unittest -v"""
import asyncio, json, tempfile, unittest
from pathlib import Path
from hub import rules
from hub.model import Device
from tests.test_rules import FakeHub, use, rule


class EntryTests(unittest.IsolatedAsyncioTestCase):
    async def settle(self):
        for _ in range(3): await asyncio.sleep(0)

    def test_entry_is_a_valid_room_word(self):
        good, errors = rules.validate({"rules": [rule("w", room="entry", when={"presence": "somebody"}, then={"intent": "occupied"})]}, {"hall"})
        self.assertEqual((len(good), errors), (1, []))

    async def test_an_entry_rule_runs_in_each_chosen_room_and_nowhere_when_none(self):
        hub = FakeHub()
        use(hub, rule("welcome", room="entry", when={"presence": "somebody"}, then={"intent": "occupied"}))
        hub.presence.load([{"entity_id": "person.a", "state": "not_home", "attributes": {}}])
        hub.presence.on_state("person.a", {"entity_id": "person.a", "state": "home", "attributes": {}}); hub.engine.on_presence(); await self.settle()
        self.assertEqual(hub.log.of("intent"), [])                       # nobody chose an entry room yet
        hub.entry = ["hall", "den", "attic"]                                # attic is not a room: ignored
        hub.presence.on_state("person.a", {"entity_id": "person.a", "state": "not_home", "attributes": {}})
        hub.presence.on_state("person.a", {"entity_id": "person.a", "state": "home", "attributes": {}}); hub.engine.on_presence(); await self.settle()
        self.assertEqual(sorted(r["subject"] for r in hub.log.of("intent")), ["den", "hall"])
        self.assertEqual({r["detail"]["rule"] for r in hub.log.of("intent")}, {"welcome"})

    async def test_motion_in_an_entry_room_wakes_an_entry_rule(self):
        hub = FakeHub(); hub.entry = ["hall"]
        use(hub, rule("in", room="entry", when={"motion": "on"}, then={"intent": "occupied"}))
        hub.motion.state = "on"; hub.engine.on_state(hub.motion, "off"); await self.settle()
        self.assertEqual(hub.home.rooms["hall"].intent, "occupied")

    def test_dry_run_says_when_no_entry_room_is_chosen(self):
        hub = FakeHub()
        use(hub, rule("welcome", room="entry", when={"presence": "somebody"}, then={"intent": "occupied"}))
        out = hub.engine.dry_run("welcome")
        self.assertEqual((out["would"], out["note"]), ("wait", "no entry rooms chosen yet"))
        hub.entry = ["den"]
        self.assertEqual(hub.engine.dry_run("welcome")["rule"]["room"], "den")


class SeedTests(unittest.TestCase):
    def test_a_fresh_data_directory_starts_from_the_repo_copy(self):
        keep = (rules.RULES_PATH, rules.SEED)
        with tempfile.TemporaryDirectory() as d:
            rules.SEED, rules.RULES_PATH = Path(d) / "repo" / "rules.json", Path(d) / "data" / "rules.json"
            rules.SEED.parent.mkdir(); rules.SEED.write_text(json.dumps({"rules": [{"id": "x", "room": "home", "when": {"time": "22:00"}, "then": {"intent": "asleep"}}]}))
            hub = FakeHub(); hub.engine.load(force=True)
            self.assertTrue(rules.RULES_PATH.exists())
            self.assertEqual([r["id"] for r in hub.engine.rules], ["x"])
            rules.RULES_PATH.write_text(json.dumps({"rules": []})); hub.engine.load(force=True)
            self.assertEqual(hub.engine.rules, [])                        # the hub's own copy wins from then on
        rules.RULES_PATH, rules.SEED = keep


if __name__ == "__main__":
    unittest.main()
