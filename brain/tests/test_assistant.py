"""Run from brain/: .venv/bin/python -m unittest -v"""
import asyncio, json, tempfile, unittest
from pathlib import Path
from hub import rules
from hub.assistant import Assistant, AssistantError
from hub.settings import Settings
from tests.test_rules import FakeHub


class Reply:
    """What the SDK hands back, reduced to what the assistant reads."""
    def __init__(self, text, stop="end_turn"):
        self.stop_reason, self.content = stop, [type("T", (), {"type": "text", "text": text})()]


class FakeModel:
    """A scripted model: answers in order, remembers what it was asked."""
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []
        self.beta = type("B", (), {})(); self.beta.messages = self
    async def create(self, **kw):
        self.calls.append(kw); return self.replies.pop(0)


def ok(rule): return Reply(json.dumps({"ok": True, "reason": "", "rule_json": json.dumps(rule)}))
def no(reason): return Reply(json.dumps({"ok": False, "reason": reason, "rule_json": ""}))
RULE = {"id": "hall-late", "name": "Hallway light on after dark when someone walks through", "room": "hall",
        "when": {"motion": "on"}, "if": [["sun", "below", 0]], "then": {"intent": "occupied"}}


class AssistantTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); d = Path(self.dir.name)
        self._path, rules.RULES_PATH = rules.RULES_PATH, d / "rules.json"     # a real file, so save and load round-trip
        rules.RULES_PATH.write_text(json.dumps({"rules": [{**RULE, "id": "hall-evening"}], "drafts": []}))
        self.hub = FakeHub(); self.hub.settings, self.hub.env = Settings(d / "settings.json"), {}
        self.hub.engine.load(force=True)

    def tearDown(self):
        rules.RULES_PATH = self._path; self.dir.cleanup()

    def file(self): return json.loads(rules.RULES_PATH.read_text())

    def test_not_connected_until_there_is_a_key(self):
        a = Assistant(self.hub)
        self.assertFalse(a.status()["configured"])
        with self.assertRaises(AssistantError) as c: a.client()
        self.assertEqual(c.exception.status, 409)
        self.hub.env["ANTHROPIC_API_KEY"] = "sk-test"
        self.assertEqual((a.status()["configured"], a.status()["source"]), (True, "env"))
        self.hub.settings.set(assistant={"key": "sk-panel"})
        self.assertEqual(a.status()["source"], "panel")

    async def test_a_sentence_becomes_a_draft_nothing_runs(self):
        model = FakeModel(ok(RULE))
        a = Assistant(self.hub, client=model)
        d = await a.draft("  turn the hall light on after dark when someone walks through ")
        self.assertEqual((d["id"], d["by"], d["room"], d["enabled"]), ("hall-late", "assistant", "hall", True))
        self.assertEqual(d["said"], "turn the hall light on after dark when someone walks through")
        f = self.file()
        self.assertEqual([r["id"] for r in f["rules"]], ["hall-evening"])          # not a rule yet
        self.assertEqual([r["id"] for r in f["drafts"]], ["hall-late"])
        self.assertEqual([r["id"] for r in self.hub.engine.rules], ["hall-evening"])   # the evaluator never sees drafts
        self.assertEqual(self.hub.log.of("draft")[0]["source"], "assistant")
        self.assertIn('"type": "drafts"', self.hub.sent[-1])
        asked = model.calls[0]
        self.assertEqual(asked["model"], "claude-opus-5")
        self.assertIn("hall: Hallway", asked["messages"][0]["content"])          # it was told the rooms
        self.assertIn("binary_sensor.hall_motion", asked["messages"][0]["content"])
        self.assertIn("hall-evening", asked["messages"][0]["content"])           # and the ids already taken
        self.assertEqual(asked["output_config"]["format"]["type"], "json_schema")

    async def test_an_id_already_taken_gets_a_suffix(self):
        a = Assistant(self.hub, client=FakeModel(ok({**RULE, "id": "hall-evening"})))
        self.assertEqual((await a.draft("same again"))["id"], "hall-evening-2")

    async def test_a_refused_rule_gets_one_fix(self):
        bad = {**RULE, "room": "attic"}
        model = FakeModel(ok(bad), ok(RULE))
        d = await Assistant(self.hub, client=model).draft("hall light after dark")
        self.assertEqual(d["id"], "hall-late")
        self.assertIn("refused your previous rule", model.calls[1]["messages"][0]["content"])
        self.assertIn("attic", model.calls[1]["messages"][0]["content"])

    async def test_two_bad_rules_is_a_plain_error_and_no_draft(self):
        bad = {**RULE, "when": {"motion": "on", "idle": 5}}
        with self.assertRaises(AssistantError) as c: await Assistant(self.hub, client=FakeModel(ok(bad), ok(bad))).draft("something odd")
        self.assertEqual(c.exception.status, 422); self.assertEqual(self.file()["drafts"], [])

    async def test_the_model_may_say_it_cannot(self):
        with self.assertRaises(AssistantError) as c:
            await Assistant(self.hub, client=FakeModel(no("The porch has no light of its own here."))).draft("everything off except the porch")
        self.assertEqual((c.exception.status, str(c.exception)), (422, "The porch has no light of its own here."))

    async def test_a_refusal_stop_is_a_plain_error(self):
        with self.assertRaises(AssistantError): await Assistant(self.hub, client=FakeModel(Reply("", stop="refusal"))).draft("do a thing")

    async def test_approve_moves_it_and_discard_drops_it(self):
        a = Assistant(self.hub, client=FakeModel(ok(RULE), ok({**RULE, "id": "den-idle", "room": "den", "when": {"idle": 600}, "if": [], "then": {"intent": "empty"}})))
        await a.draft("one"); await a.draft("two")
        rule = a.approve("hall-late")
        self.assertIn("approved", rule)
        self.assertEqual([r["id"] for r in self.file()["rules"]], ["hall-evening", "hall-late"])
        self.assertEqual([r["id"] for r in self.hub.engine.rules], ["hall-evening", "hall-late"])   # now it runs
        a.discard("den-idle")
        self.assertEqual(self.file()["drafts"], [])
        with self.assertRaises(AssistantError): a.approve("den-idle")
        self.assertEqual([r["new"] for r in self.hub.log.of("draft")], ["proposed", "proposed", "approved", "discarded"])

    async def test_explain_reads_the_log_and_returns_prose(self):
        self.hub.log.add("intent", "hall", "unknown", "occupied", source="rule", detail={"rule": "hall-evening", "trigger": {"motion": "on"}})
        self.hub.log.add("state", "light.hall", "off", "on")
        model = FakeModel(Reply("The hallway lit up because someone walked through after dark."))
        out = await Assistant(self.hub, client=model).explain("hall", "why did the light come on?")
        self.assertTrue(out["answer"].startswith("The hallway"))
        asked = model.calls[0]["messages"][0]["content"]
        self.assertIn("Room: Hallway", asked); self.assertIn("Hall light off -> on", asked)
        self.assertIn(RULE["name"], asked)                                       # the rule's name, so the prose can use it
        self.assertEqual(model.calls[0]["output_config"], {"effort": "low"})
        with self.assertRaises(AssistantError): await Assistant(self.hub, client=model).explain("attic", None)


if __name__ == "__main__":
    unittest.main()
