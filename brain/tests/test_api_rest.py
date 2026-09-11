"""The rest of the surface the panel talks to: rules, the log a room's story is told from, sounds,
health, updates, restore, and the stream every screen holds open.

Run from brain/: .venv/bin/python -m unittest -v
"""
import io, json, tarfile, time, unittest

from starlette.websockets import WebSocketDisconnect

from hub.phones import COOKIE
from tests.apptest import ApiTest


class RulesTests(ApiTest):
    def test_rules_are_returned_with_whether_they_are_usable(self):
        d = self.client.get("/rules").json()
        self.assertIn("rules", d)
        self.assertIn("valid", d)

    def test_a_rule_that_cannot_run_is_refused_with_reasons_and_the_old_ones_keep_running(self):
        before = self.client.get("/rules").json()["rules"]
        r = self.client.put("/rules", json={"rules": [{"id": "bad", "room": "nowhere", "when": {"motion": "on"}, "then": {"intent": "occupied"}}]})
        self.assertEqual(r.status_code, 422)
        self.assertEqual(self.client.get("/rules").json()["rules"], before)

    def test_a_good_rule_is_kept(self):
        r = self.client.put("/rules", json={"rules": [{"id": "kitchen-motion", "room": "kitchen", "when": {"motion": "on"}, "then": {"intent": "occupied"}}]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["id"] for x in r.json()["rules"]], ["kitchen-motion"])

    def test_a_rule_can_be_switched_off_without_being_deleted(self):
        self.client.put("/rules", json={"rules": [{"id": "kitchen-motion", "room": "kitchen", "when": {"motion": "on"}, "then": {"intent": "occupied"}}]})
        r = self.client.post("/rules/kitchen-motion/enable", json={"enabled": False})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()["enabled"])
        self.assertEqual([x["id"] for x in self.client.get("/rules").json()["rules"]], ["kitchen-motion"])

    def test_switching_a_rule_that_is_not_there_is_a_404(self):
        self.assertEqual(self.client.post("/rules/nope/enable", json={"enabled": False}).status_code, 404)


class WhyTests(ApiTest):
    def test_a_rooms_story_carries_the_house_wide_taps_as_well_as_its_own(self):
        self.hub.log.add("intent", "kitchen", None, "occupied", source="rule", detail={"rule": "kitchen-motion"})
        self.hub.log.add("intent", "home", None, "asleep", source="user")
        self.hub.log.add("intent", "living", None, "movie", source="user")     # another room: not this one's story
        subjects = [row["subject"] for row in self.client.get("/rooms/kitchen/why").json()]
        self.assertEqual(sorted(subjects), ["home", "kitchen"])

    def test_the_house_has_a_story_of_its_own(self):
        self.hub.log.add("intent", "home", None, "asleep", source="user")
        self.assertEqual(self.client.get("/rooms/home/why").status_code, 200)

    def test_a_room_that_is_not_there_has_no_story(self):
        self.assertEqual(self.client.get("/rooms/attic/why").status_code, 404)

    def test_the_log_is_newest_first_so_the_panel_reads_top_down(self):
        for i in range(3):
            self.hub.log.add("intent", "kitchen", None, f"s{i}", source="user"); time.sleep(0.002)
        self.assertEqual([r["new"] for r in self.client.get("/events", params={"subject": "kitchen"}).json()], ["s2", "s1", "s0"])


class IntentTests(ApiTest):
    def test_setting_a_room_to_asleep_turns_its_lights_off_and_locks_what_it_can(self):
        r = self.client.post("/rooms/living/intent/asleep")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.ha.called("light", "turn_off", "light.ceiling"))
        self.assertEqual(self.hub.home.rooms["living"].intent, "asleep")

    def test_a_state_the_house_does_not_have_a_word_for_is_refused(self):
        self.assertEqual(self.client.post("/rooms/living/intent/dancing").status_code, 422)

    def test_an_unknown_room_is_a_404(self):
        self.assertEqual(self.client.post("/rooms/attic/intent/asleep").status_code, 404)

    def test_a_house_wide_tap_reaches_every_room(self):
        r = self.client.post("/home/intent/away")
        self.assertEqual(r.status_code, 200)
        off = {c[2] for c in self.ha.called("light", "turn_off")}
        self.assertEqual(off, {"light.ceiling", "light.kitchen", "light.new_lamp"})


class HealthTests(ApiTest):
    def test_health_is_empty_good_news_or_sentences_a_person_can_read(self):
        notes = self.client.get("/health").json()["notes"]
        self.assertIsInstance(notes, list)
        for n in notes: self.assertIn("text", n)

    def test_a_starting_hub_reports_nothing_rather_than_complaining_about_a_house_it_has_not_read(self):
        self.hub.driver = "connecting"
        self.assertEqual(self.client.get("/health").json()["notes"], [])


class SoundsTests(ApiTest):
    def test_the_catalogue_says_what_can_be_played_and_what_is_playing(self):
        d = self.client.get("/sounds").json()
        self.assertIn("sounds", d)
        self.assertIn("playing", d)


class UpdateTests(ApiTest):
    def test_asking_for_an_update_parks_a_file_for_the_host_and_runs_nothing_here(self):
        r = self.client.post("/update")
        self.assertEqual(r.status_code, 200)
        self.assertTrue((self.data / "update.request").exists())

    def test_the_panel_can_read_which_build_this_is(self):
        self.assertIn("version", self.client.get("/update").json())


class RestoreTests(ApiTest):
    def archive(self, names=("manifest.json",), manifest=b'{"version": "v1"}'):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for n in names:
                data = manifest if n == "manifest.json" else b"x" * 100
                info = tarfile.TarInfo(n); info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def test_a_backup_is_parked_for_the_host_and_nothing_is_unpacked_here(self):
        r = self.client.post("/restore", content=self.archive())
        self.assertEqual(r.status_code, 200)
        self.assertTrue((self.data / "restore.tar.gz").exists())
        self.assertTrue((self.data / "restore.request").exists())

    def test_an_archive_that_would_write_outside_the_data_volume_is_refused(self):
        for names in (("manifest.json", "../../etc/passwd"), ("manifest.json", "/etc/passwd")):
            with self.subTest(names=names):
                r = self.client.post("/restore", content=self.archive(names))
                self.assertEqual(r.status_code, 400)
                self.assertFalse((self.data / "restore.tar.gz").exists())

    def test_something_that_is_not_a_backup_at_all_is_refused(self):
        for body in (b"", b"hello", b"\x1f\x8b" + b"x" * 200):
            with self.subTest(body=body[:8]):
                self.assertEqual(self.client.post("/restore", content=body).status_code, 400)

    def test_an_archive_with_no_manifest_is_refused(self):
        self.assertEqual(self.client.post("/restore", content=self.archive(("settings.json",))).status_code, 400)


class StreamTests(ApiTest):
    def test_a_screen_that_connects_is_told_the_status_at_once(self):
        with self.client.websocket_connect("/stream") as ws:
            first = json.loads(ws.receive_text())
        self.assertEqual(first["type"], "status")
        self.assertEqual(first["status"]["driver"], "ready")

    def test_a_phone_the_house_does_not_know_is_not_let_onto_the_stream(self):
        self.lock_the_house("4821")
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect("/stream") as ws:
                ws.receive_text()
        self.assertEqual(caught.exception.code, 4401)      # the join screen is the way in, and the panel knows that code

    def test_a_phone_that_belongs_to_the_house_is(self):
        self.lock_the_house("4821")
        _, token = self.hub.phones.with_code("Temi's phone")
        self.client.cookies.set(COOKIE, token)
        with self.client.websocket_connect("/stream") as ws:
            self.assertEqual(json.loads(ws.receive_text())["type"], "status")


class PresenceTests(ApiTest):
    def test_who_is_home_is_answerable_even_before_anyone_has_been_seen(self):
        d = self.client.get("/presence").json()
        for key in ("somebody", "since", "source"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
