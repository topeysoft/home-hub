"""The door: what a code changes about who may do what, and how a phone gets in.

The rule the whole product rests on is that driving the house never needs the code and changing it
always does. These tests state that as a contract so a new route cannot quietly land on the wrong side.

Run from brain/: .venv/bin/python -m unittest -v
"""
import unittest

from hub.lock import needs_code
from hub.phones import COOKIE, open_to_strangers
from tests.apptest import ApiTest


class OpenHouseTests(ApiTest):
    def test_with_no_code_set_the_house_is_open_on_the_wifi_the_way_it_starts(self):
        self.assertFalse(self.hub.lock.locked)
        self.assertEqual(self.client.post("/devices/light.kitchen/on").status_code, 200)
        self.assertEqual(self.client.post("/rooms", json={"name": "Study"}).status_code, 200)
        self.assertTrue(self.client.get("/phones/me").json()["paired"])   # nothing to be paired to yet


class LockedHouseTests(ApiTest):
    def setUp(self):
        super().setUp()
        self.code = self.lock_the_house("4821")

    def admit(self):
        """A phone that belongs to the house, as its cookie."""
        phone, token = self.hub.phones.with_code("Temi's phone")
        self.client.cookies.set(COOKIE, token)
        return phone

    # ---- who gets in at all ----
    def test_a_phone_the_house_does_not_know_is_turned_away(self):
        r = self.client.get("/home")
        self.assertEqual((r.status_code, r.json()["detail"]), (401, "phone"))

    def test_the_join_screen_still_loads_for_a_phone_that_is_not_in_yet(self):
        r = self.client.get("/phones/me")
        self.assertEqual(r.status_code, 200)
        self.assertEqual((r.json()["locked"], r.json()["paired"]), (True, False))

    def test_a_known_phone_may_drive_the_house_without_ever_typing_the_code(self):
        self.admit()
        self.assertEqual(self.client.post("/devices/light.kitchen/on").status_code, 200)
        self.assertEqual(self.client.post("/rooms/living/intent/movie").status_code, 200)
        self.assertEqual(self.client.get("/home").status_code, 200)

    # ---- what still needs the code ----
    def test_changing_the_house_needs_the_code_even_from_a_phone_that_belongs_to_it(self):
        self.admit()
        r = self.client.post("/rooms", json={"name": "Study"})
        self.assertEqual((r.status_code, r.json()["detail"]), (401, "code"))
        ok = self.client.post("/rooms", json={"name": "Study"}, headers={"x-hub-code": self.code})
        self.assertEqual(ok.status_code, 200)

    def test_the_engines_own_sign_in_is_behind_the_code(self):
        self.admit()
        self.assertEqual(self.client.get("/setup/advanced").status_code, 401)
        self.assertEqual(self.client.get("/setup/advanced", headers={"x-hub-code": self.code}).status_code, 200)

    def test_the_archive_carries_the_houses_keys_so_it_is_behind_the_code(self):
        self.admit()
        self.assertEqual(self.client.get("/backup").status_code, 401)

    # ---- guessing ----
    def test_five_wrong_codes_from_one_address_buys_a_wait(self):
        self.admit()
        for _ in range(5):
            self.assertEqual(self.client.post("/rooms", json={"name": "x"}, headers={"x-hub-code": "0000"}).status_code, 401)
        r = self.client.post("/rooms", json={"name": "x"}, headers={"x-hub-code": self.code})
        self.assertEqual(r.status_code, 429)               # even the right code waits the minute out
        self.assertIn("Wait", r.json()["detail"])


class JoiningTests(ApiTest):
    def setUp(self):
        super().setUp()
        self.code = self.lock_the_house("4821")

    def test_the_code_typed_on_the_phone_itself_puts_it_in_and_sets_its_cookie(self):
        r = self.client.post("/phones/code", json={"code": self.code, "name": "Temi's phone"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(COOKIE, r.cookies)
        self.assertEqual(self.client.get("/home").status_code, 200)     # the cookie carries on

    def test_the_cookie_is_not_readable_by_the_page_and_is_not_marked_secure_over_plain_http(self):
        r = self.client.post("/phones/code", json={"code": self.code, "name": "Temi's phone"})
        set_cookie = r.headers["set-cookie"]
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=lax", set_cookie)
        self.assertNotIn("Secure", set_cookie)

    def test_the_cookie_is_marked_secure_when_the_front_door_was_https(self):
        r = self.client.post("/phones/code", json={"code": self.code}, headers={"x-forwarded-proto": "https"})
        self.assertIn("Secure", r.headers["set-cookie"])

    def test_a_wrong_code_on_the_phone_lets_nobody_in(self):
        r = self.client.post("/phones/code", json={"code": "0000"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.hub.phones.data, [])

    def test_a_phone_asks_and_waits_until_a_paired_screen_answers(self):
        ask = self.client.post("/phones/ask", json={"name": "Guest"}).json()
        self.assertEqual(self.client.get(f"/phones/claim/{ask['id']}").json()["state"], "waiting")

        wall = self.client                                              # the screen that allows it is already in
        phone, token = self.hub.phones.with_code("Wall")
        wall.cookies.set(COOKIE, token)
        allowed = wall.post(f"/phones/asks/{ask['id']}/allow", json={"span": "day"}, headers={"x-hub-code": self.code})
        self.assertEqual(allowed.status_code, 200)

        claim = self.client.get(f"/phones/claim/{ask['id']}")
        self.assertEqual(claim.json()["state"], "allowed")
        self.assertIn(COOKIE, claim.cookies)

    def test_a_token_is_handed_over_once_and_a_second_claim_finds_nothing(self):
        ask = self.client.post("/phones/ask", json={"name": "Guest"}).json()
        self.hub.phones.allow(ask["id"], "keep")
        self.assertEqual(self.client.get(f"/phones/claim/{ask['id']}").json()["state"], "allowed")
        self.assertEqual(self.client.get(f"/phones/claim/{ask['id']}").json()["state"], "gone")

    def test_letting_a_phone_in_is_a_change_so_it_needs_the_code(self):
        ask = self.client.post("/phones/ask", json={"name": "Guest"}).json()
        phone, token = self.hub.phones.with_code("Wall")
        self.client.cookies.set(COOKIE, token)
        self.assertEqual(self.client.post(f"/phones/asks/{ask['id']}/allow", json={}).status_code, 401)

    def test_removing_a_phone_puts_it_out_at_once(self):
        joined = self.client.post("/phones/code", json={"code": self.code, "name": "Temi's phone"}).json()
        self.assertEqual(self.client.get("/home").status_code, 200)
        self.hub.phones.remove(joined["phone"]["id"])
        self.assertEqual(self.client.get("/home").status_code, 401)

    def test_a_guest_starts_home_only(self):
        ask = self.client.post("/phones/ask", json={"name": "Guest"}).json()
        p = self.hub.phones.allow(ask["id"], "day")
        self.assertFalse(p["remote"])
        self.assertIsNotNone(p["expires"])

    def test_asking_to_join_a_house_with_no_code_says_there_is_nothing_to_join(self):
        self.hub.lock.set("")
        self.assertEqual(self.client.post("/phones/ask", json={"name": "Guest"}).status_code, 409)


class SettingTheCodeTests(ApiTest):
    def test_the_screen_that_sets_the_first_code_becomes_the_houses_first_phone(self):
        r = self.client.post("/setup/pin", json={"pin": "4821"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(COOKIE, r.cookies)                                # it is inside, not locked out of what it just secured
        self.assertEqual(len(self.hub.phones.data), 1)
        self.assertEqual(self.hub.phones.data[0]["how"], "setup")

    def test_a_code_that_is_not_four_to_eight_digits_is_refused(self):
        for bad in ("12", "abcd", "1234567890"):
            with self.subTest(pin=bad):
                self.assertEqual(self.client.post("/setup/pin", json={"pin": bad}).status_code, 400)
        self.assertFalse(self.hub.lock.locked)

    def test_changing_a_code_needs_the_old_one(self):
        self.client.post("/setup/pin", json={"pin": "4821"})
        self.assertEqual(self.client.post("/setup/pin", json={"pin": "9999"}).status_code, 401)
        self.assertEqual(self.client.post("/setup/pin", json={"pin": "9999"}, headers={"x-hub-code": "4821"}).status_code, 200)
        self.assertTrue(self.hub.lock.check("9999"))


class WhichSideOfTheDoorTests(unittest.TestCase):
    """The two tables the middleware reads. They are pure, so they are checked directly and exhaustively."""

    def test_driving_the_house_never_needs_the_code(self):
        for method, path in [("POST", "/devices/light.kitchen/on"), ("POST", "/devices/climate.nest/set"),
                             ("POST", "/rooms/living/intent/movie"), ("POST", "/home/intent/asleep"),
                             ("POST", "/say"), ("GET", "/home"), ("GET", "/events"), ("POST", "/drafts/suggest")]:
            with self.subTest(path=path):
                self.assertFalse(needs_code(method, path))

    def test_changing_the_house_always_does(self):
        for method, path in [("POST", "/rooms"), ("POST", "/rooms/living/rename"), ("DELETE", "/rooms/living"),
                             ("POST", "/devices/light.ceiling/move"), ("POST", "/devices/light.ceiling/rename"),
                             ("POST", "/location"), ("POST", "/home/entry"), ("GET", "/setup/advanced"),
                             ("POST", "/setup/pin"), ("POST", "/flows"), ("POST", "/credentials"),
                             ("POST", "/assistant/key"), ("GET", "/backup"), ("POST", "/restore"),
                             ("POST", "/pair"), ("DELETE", "/phones/abc"), ("POST", "/update")]:
            with self.subTest(path=path):
                self.assertTrue(needs_code(method, path))

    def test_the_panel_itself_loads_before_a_phone_belongs_to_the_house(self):
        for path in ("/", "/index.html", "/assets/index-abc123.js", "/assets/index-abc123.css",
                     "/manifest.webmanifest", "/sw.js", "/favicon.svg", "/phones/me", "/phones/ask",
                     "/phones/code", "/phones/claim/abc", "/sounds/rain.mp3", "/qr.svg"):
            with self.subTest(path=path):
                self.assertTrue(open_to_strangers("GET", path))

    def test_the_house_itself_is_not_open_to_strangers(self):
        for path in ("/home", "/events", "/devices/light.kitchen/on", "/phones", "/setup/advanced", "/backup", "/suggestions"):
            with self.subTest(path=path):
                self.assertFalse(open_to_strangers("GET", path))


if __name__ == "__main__":
    unittest.main()
