"""The hub's own memory, and what belongs in it.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json, os, tempfile, unittest
from pathlib import Path
from unittest import mock

from hub.settings import Settings, env_file


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.path = self.dir / "settings.json"

    def test_a_hub_that_has_never_been_set_up_starts_empty_rather_than_failing(self):
        self.assertEqual(Settings(self.path).get("owner"), None)
        self.assertEqual(Settings(self.path).get("owner", "nobody"), "nobody")

    def test_what_is_written_is_there_on_the_next_start(self):
        Settings(self.path).set(home_name="Ash Street", setup_done=True)
        again = Settings(self.path)
        self.assertEqual(again.get("home_name"), "Ash Street")
        self.assertTrue(again.get("setup_done"))

    def test_writing_one_key_leaves_the_others_alone(self):
        s = Settings(self.path)
        s.set(home_name="Ash Street")
        s.set(setup_done=True)
        self.assertEqual(Settings(self.path).get("home_name"), "Ash Street")

    def test_a_settings_file_that_got_mangled_does_not_stop_the_hub_booting(self):
        # A hub that will not start because a JSON file lost a brace is a hub someone has to plug a
        # keyboard into. It comes up empty instead, and setup asks again.
        self.path.write_text("{not json")
        self.assertEqual(Settings(self.path).data, {})

    def test_the_file_is_replaced_whole_so_a_power_cut_mid_write_cannot_halve_it(self):
        s = Settings(self.path)
        s.set(home_name="Ash Street")
        self.assertFalse(self.path.with_suffix(".tmp").exists())   # the temp file was moved into place, not left behind
        self.assertEqual(json.loads(self.path.read_text())["home_name"], "Ash Street")

    def test_the_directory_is_made_if_the_data_volume_is_brand_new(self):
        deep = self.dir / "nowhere" / "yet" / "settings.json"
        Settings(deep).set(home_name="Ash Street")
        self.assertTrue(deep.exists())


class EnvFileTests(unittest.TestCase):
    def test_the_developers_way_in_is_read_from_the_process(self):
        with mock.patch.dict(os.environ, {"HA_URL": "http://ha:8123", "HOME_LAT": "41.88", "PATH": "/bin"}):
            env = env_file()
        self.assertEqual(env["HA_URL"], "http://ha:8123")
        self.assertEqual(env["HOME_LAT"], "41.88")
        self.assertNotIn("PATH", env)          # only the hub's own names, not the whole environment


if __name__ == "__main__":
    unittest.main()
