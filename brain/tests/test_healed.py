# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run from brain/: .venv/bin/python -m unittest -v

The hub starting a part of itself again, as design/healed/ direction C says it: once, a span on What
happened and nothing anywhere else; the third time in a week, a job on Needs a look with Back up on it.
"""
import json, time
from datetime import UTC, datetime

from hub.healed import stamp
from tests.apptest import ApiTest


def docker(ts: float) -> str:
    """A time the way Docker writes FinishedAt: nine digits of fraction and a Z."""
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%S.123456789Z")


class Healed(ApiTest):
    def setUp(self):
        super().setUp()
        # The ceiling and kitchen lights are on Messages, the way a bridge's switches are.
        self.hub.provision.domains = {"entry-hw-ceiling": "mqtt", "entry-hw-kitchen": "mqtt"}

    def knock(self, minutes_ago=30, down_for=10, power=True, service="mosquitto"):
        """One line from the watchdog, as watchdog.sh writes it."""
        at = time.time() - minutes_ago * 60
        stopped = at - down_for * 60
        line = {"at": int(at), "boot": int(stopped + 20) if power else int(stopped - 86400),
                "parts": [{"service": service, "stopped": docker(stopped)}]}
        with open(self.data / "healed.jsonl", "a") as f: f.write(json.dumps(line) + "\n")

    def over(self):
        page = self.client.get("/happened").json()
        return [i for g in page["groups"] for i in g["items"] if i["subject"].startswith("healed:")]

    def notes(self):
        return [n for n in self.client.get("/health").json()["notes"] if n["kind"] == "healed"]

    def test_once_it_is_a_span_on_what_happened_naming_what_was_cut_off(self):
        self.knock()
        [row] = self.over()
        self.assertTrue(row["text"].startswith("The hub lost power at "), row["text"])
        self.assertIn("When it came back, Messages did not, so Ceiling light and Kitchen lights were cut off "
                      "until the hub started it again itself.", row["text"])
        self.assertEqual(row["acts"], [])
        self.assertIn(" – ", row["when"])

    def test_once_it_is_nowhere_else(self):
        """Not on Needs a look, so not on Home's band either: by the time anybody reads it, it is over."""
        self.knock()
        self.assertEqual(self.notes(), [])
        self.assertFalse((self.data / "healed.jsonl").exists(), "the host's file is taken into the diary")

    def test_a_part_that_stopped_while_the_hub_was_running_does_not_claim_a_power_cut(self):
        self.knock(power=False)
        [row] = self.over()
        self.assertTrue(row["text"].startswith("Messages stopped at "), row["text"])
        self.assertNotIn("power", row["text"])

    def test_the_third_time_in_a_week_it_is_a_job_with_a_backup_on_it(self):
        for days in (5, 3, 0):
            self.knock(minutes_ago=days * 1440 + 30)
        self.hub.healed.take()
        [n] = self.notes()
        self.assertEqual(n["text"], "The hub has lost power 3 times this week, and each time Messages did not start again by itself.")
        self.assertIn("memory card", n["more"])
        self.assertEqual(n["acts"], [{"do": "Back up", "act": "backup", "to": None}])

    def test_twice_is_still_news(self):
        self.knock(minutes_ago=2000); self.knock()
        self.assertEqual(self.notes(), [])

    def test_it_is_nobodys_change_to_the_house(self):
        self.knock(); self.hub.healed.take()
        rows = self.client.get("/happened/changes").json()["rows"]
        self.assertFalse([r for r in rows if "Messages" in r["text"]])

    def test_the_engine_takes_everything_with_it(self):
        self.knock(service="homeassistant")
        [row] = self.over()
        self.assertIn("the hub's engine did not, so everything in the house was cut off", row["text"])

    def test_a_half_written_file_does_not_take_the_page_down(self):
        (self.data / "healed.jsonl").write_text('{"at": 1, "parts": [{"serv')
        self.assertEqual(self.client.get("/happened").status_code, 200)
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_docker_times(self):
        self.assertAlmostEqual(stamp("2026-09-26T22:29:45.477055085Z"), 1790461785.477055, places=3)
        self.assertIsNone(stamp("0001-01-01T00:00:00Z"))
        self.assertIsNone(stamp(""))
