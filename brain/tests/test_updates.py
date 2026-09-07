"""Run from brain/: .venv/bin/python -m unittest -v"""
import json, os, tempfile, unittest
from pathlib import Path
from unittest import mock
from hub import updates
from tests.test_rules import FakeHub


class UpdateTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); d = Path(self.dir.name)
        self.keep = (updates.REQUEST, updates.STATE)
        updates.REQUEST, updates.STATE = d / "update.request", d / "update.json"
        self.hub = FakeHub()
        self.hub.status = lambda: {"update": self.hub.updates.summary()}

    def tearDown(self):
        updates.REQUEST, updates.STATE = self.keep; self.dir.cleanup()

    def make(self, version="v1.2.0", commit="a" * 40):
        with mock.patch.dict(os.environ, {"HUB_VERSION": version, "HUB_COMMIT": commit}):
            self.hub.updates = updates.Updates(self.hub)
        return self.hub.updates

    def test_a_dev_build_cannot_tell(self):
        with mock.patch.dict(os.environ, {"HUB_VERSION": "", "HUB_COMMIT": ""}, clear=False):
            u = updates.Updates(self.hub)
        self.assertEqual((u.version, u.available), ("dev", None))

    async def test_main_moved_on_and_the_panel_is_told(self):
        u = self.make()
        u.fetch = lambda: {"sha": "b" * 40, "when": "2026-09-06T20:00:00Z", "title": "feat: something"}
        out = await u.check()
        self.assertTrue(out["available"]); self.assertEqual(out["latest"]["title"], "feat: something")
        self.assertIn('"type": "status"', self.hub.sent[-1])
        sent = len(self.hub.sent)
        await u.check()                                            # no change, no chatter
        self.assertEqual(len(self.hub.sent), sent)

    async def test_same_commit_means_up_to_date_and_errors_are_kept_not_raised(self):
        u = self.make()
        u.fetch = lambda: {"sha": "a" * 40, "when": "", "title": ""}
        self.assertFalse((await u.check())["available"])
        def boom(): raise OSError("no internet")
        u.fetch = boom
        out = await u.check()
        self.assertFalse(out["available"]); self.assertIn("no internet", out["error"])   # the last good answer stands

    def test_a_request_is_a_file_for_the_host_and_a_line_in_the_log(self):
        u = self.make(); u.latest = {"sha": "b" * 40, "when": "", "title": ""}
        out = u.request()
        self.assertTrue(out["requested"]); self.assertTrue(updates.REQUEST.exists())
        self.assertEqual(json.loads(updates.REQUEST.read_text())["to"], "b" * 40)
        self.assertEqual(self.hub.log.rows[-1]["subject"], "update")
        updates.STATE.write_text(json.dumps({"state": "running", "started": 1}))
        self.assertEqual(u.summary()["state"]["state"], "running")


if __name__ == "__main__":
    unittest.main()
