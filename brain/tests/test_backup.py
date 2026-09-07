"""Run from brain/: .venv/bin/python -m unittest -v"""
import json, os, sqlite3, tarfile, tempfile, unittest
from pathlib import Path
from unittest import mock
from hub import backup, updates
from hub.settings import Settings
from tests.test_rules import FakeHub


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); d = Path(self.dir.name)
        self.keep = (backup.DATA, backup.DRIVER, backup.REQUEST, backup.STATE, backup.ARCHIVE)
        backup.DATA, backup.DRIVER = d / "data", d / "driver"
        backup.REQUEST, backup.STATE, backup.ARCHIVE = backup.DATA / "restore.request", backup.DATA / "restore.json", backup.DATA / "restore.tar.gz"
        backup.DATA.mkdir(); (backup.DATA / "rules.json").write_text("{}"); (backup.DATA / "update.json").write_text("{}")
        db = sqlite3.connect(backup.DATA / "events.db"); db.execute("create table t(x)"); db.execute("insert into t values (1)"); db.commit(); db.close()
        for rel, text in [(".env", "TZ=UTC\nHUB_IP=1.2.3.4\n"), ("homeassistant/.storage/core.config", "{}"), ("homeassistant/configuration.yaml", ""),
                          ("homeassistant/home-assistant_v2.db", "big"), ("homeassistant/home-assistant.log", "noise"), ("homeassistant/deps/x/y", "pip"),
                          ("zigbee2mqtt/configuration.yaml", "key"), ("zigbee2mqtt/log/2026/a.log", "noise"), ("ring-mqtt/ring-state.json", "{}")]:
            p = backup.DRIVER / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
        self.hub = FakeHub(); self.hub.settings = Settings(d / "settings.json"); self.hub.settings.set(home_name="Main Palace", owner={"name": "Temi"})
        with mock.patch.dict(os.environ, {"HUB_VERSION": "v1", "HUB_COMMIT": "a" * 40}): self.hub.updates = updates.Updates(self.hub)
        (backup.DATA / "settings.json").write_text(json.dumps(self.hub.settings.data))
        self.b = backup.Backup(self.hub)

    def tearDown(self):
        backup.DATA, backup.DRIVER, backup.REQUEST, backup.STATE, backup.ARCHIVE = self.keep; self.dir.cleanup()

    def test_the_archive_holds_the_right_things_and_not_the_rest(self):
        out = self.b.make()
        self.assertTrue(out.name.startswith("home-hub-main-palace-") and out.name.endswith(".tar.gz"))
        with tarfile.open(out) as tar:
            names = set(tar.getnames())
            manifest = json.loads(tar.extractfile("manifest.json").read())
        self.assertLessEqual({"manifest.json", "data/settings.json", "data/events.db", "data/rules.json", "driver/.env",
                              "driver/homeassistant/.storage/core.config", "driver/homeassistant/configuration.yaml",
                              "driver/zigbee2mqtt/configuration.yaml", "driver/ring-mqtt/ring-state.json"}, names)
        for gone in ("data/update.json", "driver/homeassistant/home-assistant_v2.db", "driver/homeassistant/home-assistant.log",
                     "driver/homeassistant/deps/x/y", "driver/zigbee2mqtt/log/2026/a.log"):
            self.assertNotIn(gone, names, gone)
        self.assertEqual((manifest["home"], manifest["owner"], manifest["version"]), ("Main Palace", "Temi", "v1"))
        self.assertIn("events.db", manifest["data"]); self.assertIn("homeassistant", manifest["driver"])
        self.assertEqual(self.hub.log.rows[-1]["subject"], "backup")

    def test_receive_parks_a_real_archive_and_refuses_junk(self):
        body = self.b.make().read_bytes()
        out = self.b.receive(body)
        self.assertEqual(out["manifest"]["home"], "Main Palace")
        self.assertTrue(backup.ARCHIVE.exists() and backup.REQUEST.exists())
        self.assertEqual(json.loads(backup.REQUEST.read_text())["manifest"]["owner"], "Temi")
        with self.assertRaises(ValueError): self.b.receive(b"not a tarball, not even close, but long enough to get past the size check")
        with self.assertRaises(ValueError): self.b.receive(b"")

    def test_paths_that_escape_are_refused(self):
        import io
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name in ("manifest.json", "data/../../etc/passwd"):
                ti = tarfile.TarInfo(name); ti.size = 2; tar.addfile(ti, io.BytesIO(b"{}"))
        with self.assertRaises(ValueError): self.b.receive(buf.getvalue())


if __name__ == "__main__":
    unittest.main()
