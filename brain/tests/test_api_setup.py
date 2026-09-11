"""First run: a hub out of its box, and the screens that bring the engine up.

Nobody doing this has read anything. Every step has to say what happened in words, and a step that
fails must leave the house somewhere a person can try again from.

Run from brain/: .venv/bin/python -m unittest -v
"""
import unittest
from unittest import mock

from hub import ha_setup
from tests.apptest import ApiTest


class StatusTests(ApiTest):
    ready = False

    def test_the_starting_screen_is_told_which_stage_the_engine_is_at(self):
        s = self.client.get("/setup/status").json()
        self.assertEqual(s["driver"], "down")
        self.assertFalse(s["setup_done"])
        self.assertIsNone(s["owner"])

    def test_status_carries_everything_the_setup_screens_draw_from(self):
        s = self.client.get("/setup/status").json()
        for key in ("driver", "reason", "setup_done", "owner", "home", "location", "rooms",
                    "devices", "drivers", "problems", "locked", "version", "update"):
            self.assertIn(key, s)


class OwnerTests(ApiTest):
    ready = False

    def test_a_fresh_engine_is_onboarded_without_anyone_seeing_it(self):
        self.hub.driver = "fresh"
        acct = {"username": "temi", "password": "p", "token": "T", "refresh": None}
        with mock.patch.object(ha_setup, "onboard", mock.AsyncMock(return_value=acct)):
            r = self.client.post("/setup/owner", json={"name": "Temi", "home": "Ash Street"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.hub.settings.get("ha")["token"], "T")
        self.assertEqual(self.hub.settings.get("home_name"), "Ash Street")

    def test_a_house_with_no_name_is_still_called_something(self):
        self.hub.driver = "ready"
        self.client.post("/setup/owner", json={"name": "Temi"})
        self.assertEqual(self.hub.settings.get("home_name"), "Home")

    def test_a_person_needs_a_name(self):
        r = self.client.post("/setup/owner", json={"name": "  "})
        self.assertEqual(r.status_code, 400)
        self.assertIn("name", r.json()["detail"])

    def test_when_the_engine_is_not_answering_the_screen_is_told_to_wait_rather_than_that_it_failed(self):
        self.hub.driver = "down"
        r = self.client.post("/setup/owner", json={"name": "Temi"})
        self.assertEqual(r.status_code, 503)

    def test_when_onboarding_breaks_halfway_the_words_come_from_the_engine(self):
        self.hub.driver = "fresh"
        with mock.patch.object(ha_setup, "onboard", mock.AsyncMock(side_effect=ha_setup.SetupError("could not create the owner"))):
            r = self.client.post("/setup/owner", json={"name": "Temi"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("could not create the owner", r.json()["detail"])


class SignInTests(ApiTest):
    ready = False

    def test_signing_in_to_an_engine_that_was_set_up_by_hand_keeps_the_token(self):
        with mock.patch.object(ha_setup, "sign_in", mock.AsyncMock(return_value={"username": "temi", "password": "p", "token": "T"})):
            r = self.client.post("/setup/login", json={"username": "temi", "password": "p"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.hub.settings.get("ha")["token"], "T")

    def test_a_wrong_password_says_so_and_changes_nothing(self):
        with mock.patch.object(ha_setup, "sign_in", mock.AsyncMock(side_effect=ha_setup.SetupError("That name and password did not work."))):
            r = self.client.post("/setup/login", json={"username": "temi", "password": "no"})
        self.assertEqual(r.status_code, 401)
        self.assertIsNone(self.hub.settings.get("ha"))

    def test_both_halves_are_needed_before_the_engine_is_troubled(self):
        for body in ({"username": "temi"}, {"password": "p"}, {}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post("/setup/login", json=body).status_code, 400)


class FinishingTests(ApiTest):
    def test_finishing_setup_is_remembered_so_the_hub_never_asks_again(self):
        self.assertEqual(self.client.post("/setup/done").status_code, 200)
        self.assertTrue(self.hub.settings.get("setup_done"))
        self.assertEqual(self.sent("status")[-1]["status"]["setup_done"], True)

    def test_the_advanced_door_hands_over_the_engines_own_sign_in(self):
        self.hub.settings.set(ha={"url": "http://ha:8123", "username": "temi", "password": "p", "token": "T"})
        a = self.client.get("/setup/advanced").json()
        self.assertEqual((a["username"], a["password"]), ("temi", "p"))
        self.assertNotIn("token", a)          # the Advanced door is a sign-in, not a key hand-over


class LocationTests(ApiTest):
    def test_a_place_is_kept_and_the_sky_is_told(self):
        with mock.patch.object(type(self.hub), "set_location", mock.AsyncMock(return_value=None)):
            r = self.client.post("/location", json={"name": "Chicago", "lat": 41.88, "lon": -87.63})
        self.assertEqual(r.status_code, 200)

    def test_coordinates_that_are_not_on_earth_are_refused(self):
        for place in ({"lat": 91, "lon": 0}, {"lat": 0, "lon": 181}, {"lat": -91, "lon": 0}):
            with self.subTest(place=place):
                r = self.client.post("/location", json=place)
                self.assertEqual(r.status_code, 400)
                self.assertIn("Earth", r.json()["detail"])

    def test_a_place_without_coordinates_is_refused(self):
        self.assertEqual(self.client.post("/location", json={"name": "Chicago"}).status_code, 400)


class UsernameTests(unittest.TestCase):
    def test_a_persons_name_becomes_something_the_engine_will_accept(self):
        self.assertEqual(ha_setup.username_for("Temi Adeyeri"), "temiadeyeri")
        # Letters the engine will not take are dropped, not transliterated: Zoë's name gives up its ë.
        self.assertEqual(ha_setup.username_for("Zoë O'Brien-Smith"), "zoobriensmith")
        self.assertEqual(ha_setup.username_for("温"), "owner")          # nothing usable left: it still has to be a name
        self.assertEqual(ha_setup.username_for(""), "owner")
        self.assertLessEqual(len(ha_setup.username_for("a" * 80)), 24)


class QrTests(ApiTest):
    def test_the_qr_code_is_svg_a_phone_camera_can_read_off_the_wall(self):
        r = self.client.get("/qr.svg", params={"text": "http://hub.local/"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/svg+xml")
        self.assertIn(b"<svg", r.content)

    def test_the_qr_route_will_not_encode_anything_but_an_address(self):
        for bad in ("javascript:alert(1)", "not a url", "http://" + "x" * 300):
            with self.subTest(text=bad):
                self.assertEqual(self.client.get("/qr.svg", params={"text": bad}).status_code, 400)


if __name__ == "__main__":
    unittest.main()
