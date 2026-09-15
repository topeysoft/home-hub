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

    # ---- a key is not the same thing as a way in ----
    def guest(self):
        """A phone let in at the wall, with the code in hand: the case the code alone never covered."""
        ask = self.client.post("/phones/ask", json={"name": "Guest"}).json()
        wall, wall_token = self.hub.phones.from_setup()
        self.hub.phones.allow(ask["id"], "day")
        _, phone, token = self.hub.phones.claim(ask["id"])
        return phone, token, wall, wall_token

    def test_a_phone_let_in_at_the_wall_cannot_let_anybody_else_in(self):
        """The hole the code could not close, because the code is one secret the whole house shares.

        A phone let in for the afternoon, once somebody reads the code out in a kitchen, could admit
        anyone. It holds the code here and is still refused: what it may do turns on how it got in."""
        phone, token, _, _ = self.guest()
        self.client.cookies.set(COOKIE, token)
        nxt = self.client.post("/phones/ask", json={"name": "Somebody else"}).json()
        r = self.client.post(f"/phones/asks/{nxt['id']}/allow", json={"span": "keep"}, headers={"x-hub-code": self.code})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.hub.phones.claim(nxt["id"])[0], "waiting")     # and nothing was issued
        # nor may it wave the knock away on the wall's behalf
        self.assertEqual(self.client.delete(f"/phones/asks/{nxt['id']}", headers={"x-hub-code": self.code}).status_code, 403)

    def test_a_phone_let_in_at_the_wall_is_shown_itself_and_no_knocks(self):
        phone, token, _, _ = self.guest()
        self.client.cookies.set(COOKIE, token)
        self.client.post("/phones/ask", json={"name": "Somebody else"})
        seen = self.client.get("/phones").json()
        self.assertEqual([p["name"] for p in seen["phones"]], ["Guest"])
        self.assertEqual(seen["asks"], [])

    def test_a_guest_may_leave_but_not_evict(self):
        """Leaving is the button on its own row; taking somebody else out is a key."""
        phone, token, wall, _ = self.guest()
        self.client.cookies.set(COOKIE, token)
        self.assertEqual(self.client.delete(f"/phones/{wall['id']}", headers={"x-hub-code": self.code}).status_code, 403)
        self.assertIsNotNone(self.hub.phones.get(wall["id"]))
        self.assertEqual(self.client.delete(f"/phones/{phone['id']}", headers={"x-hub-code": self.code}).status_code, 200)
        self.assertIsNone(self.hub.phones.get(phone["id"]))

    def test_a_guest_cannot_talk_its_own_way_out_of_the_house(self):
        phone, token, _, _ = self.guest()
        self.client.cookies.set(COOKIE, token)
        r = self.client.post(f"/phones/{phone['id']}/remote", json={"remote": True}, headers={"x-hub-code": self.code})
        self.assertEqual(r.status_code, 403)
        self.assertFalse(self.hub.phones.get(phone["id"])["remote"])

    def test_the_wall_that_set_the_house_up_may_still_do_all_of_it(self):
        """The guard is not a wall that cannot answer its own door."""
        phone, _, wall, wall_token = self.guest()
        self.client.cookies.set(COOKIE, wall_token)
        nxt = self.client.post("/phones/ask", json={"name": "Somebody else"}).json()
        self.assertEqual(self.client.post(f"/phones/asks/{nxt['id']}/allow", json={"span": "keep"}, headers={"x-hub-code": self.code}).status_code, 200)
        self.assertEqual(self.client.delete(f"/phones/{phone['id']}", headers={"x-hub-code": self.code}).status_code, 200)
        self.assertEqual(len(self.client.get("/phones").json()["phones"]), 2)

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


class AwayTagTests(ApiTest):
    """Step 1 of docs/away.md piece 2: the brain knows which door a request came in at, and nothing more.

    The gate that refuses a home-only phone is step 2. Until it lands, an away request is served exactly
    as a home one, and the tests below say so on purpose: they are what step 2 has to change.
    """

    def test_off_the_wifi_a_request_is_at_home(self):
        self.assertFalse(self.client.get("/phones/me").json()["away"])

    def test_in_through_the_relay_the_house_can_tell(self):
        r = self.client.get("/phones/me", headers={"X-Hub-Via": "relay"})
        self.assertTrue(r.json()["away"])

    def test_the_tag_is_set_on_a_locked_house_too(self):
        self.lock_the_house("4821")
        self.assertTrue(self.client.get("/phones/me", headers={"X-Hub-Via": "relay"}).json()["away"])


class AwayGateTests(ApiTest):
    """Step 2 of docs/away.md piece 2: from outside the house, only a phone the house has let out.

    The rule underneath is that being let into the house and being let out of it are two decisions. A phone
    that belongs here still does nothing from away until somebody at the wall promotes it.
    """
    AWAY = {"X-Hub-Via": "relay"}

    def setUp(self):
        super().setUp()
        self.lock_the_house("4821")

    def admit(self, remote=False):
        phone, token = self.hub.phones.with_code("Temi's phone")
        if remote: self.hub.phones.set_remote(phone["id"], True)
        self.client.cookies.set(COOKIE, token)
        return phone

    # ---- who the door opens for ----
    def test_a_phone_the_house_has_let_out_drives_it_from_away(self):
        self.admit(remote=True)
        self.assertEqual(self.client.post("/devices/light.kitchen/on", headers=self.AWAY).status_code, 200)

    def test_the_same_phone_at_home_only_does_not(self):
        self.admit()
        r = self.client.post("/devices/light.kitchen/on", headers=self.AWAY)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"], "remote")
        self.assertIn("works at home", r.json()["message"])

    def test_and_the_same_phone_at_home_still_does(self):
        """The gate is about the door, not the phone: nothing changes on the Wi-Fi."""
        self.admit()
        self.assertEqual(self.client.post("/devices/light.kitchen/on").status_code, 200)

    def test_a_stranger_out_there_is_told_nothing_it_could_act_on(self):
        r = self.client.post("/devices/light.kitchen/on", headers=self.AWAY)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"], "away")

    # ---- the way in is not out there ----
    def test_the_join_routes_are_refused_from_away(self):
        for m, path in [("POST", "/phones/ask"), ("POST", "/phones/code"), ("GET", "/phones/claim/abc")]:
            with self.subTest(path=path):
                self.assertEqual(self.client.request(m, path, json={}, headers=self.AWAY).status_code, 403)

    def test_not_even_to_a_phone_the_house_has_let_out(self):
        """A phone joins the house from inside it, where somebody can see who is asking."""
        self.admit(remote=True)
        r = self.client.post("/phones/ask", json={"name": "A phone"}, headers=self.AWAY)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"], "at-home")

    def test_the_join_routes_still_work_on_the_wifi(self):
        self.assertEqual(self.client.post("/phones/ask", json={"name": "A phone"}).status_code, 200)

    # ---- what a refused phone can still load ----
    def test_the_app_itself_loads_so_it_can_say_why(self):
        for path in ("/index.html", "/assets/index-abc.js", "/phones/me"):
            with self.subTest(path=path):
                self.assertNotEqual(self.client.get(path, headers=self.AWAY).status_code, 403)

    def test_from_away_the_house_gives_no_name_to_anyone_it_has_not_let_out(self):
        self.admit()
        me = self.client.get("/phones/me", headers=self.AWAY).json()
        self.assertTrue(me["away"]); self.assertFalse(me["paired"])
        self.assertEqual(me["home"], "the house")
        self.assertIsNone(me["phone"])

    def test_a_phone_it_has_let_out_sees_the_house_as_itself(self):
        phone = self.admit(remote=True)
        me = self.client.get("/phones/me", headers=self.AWAY).json()
        self.assertTrue(me["away"]); self.assertTrue(me["paired"])
        self.assertEqual(me["phone"]["id"], phone["id"])

    # ---- a house with no code has no door to the outside ----
    def test_a_house_with_no_code_lets_nobody_in_from_away(self):
        self.hub.lock.set("")                                # back to how a hub starts
        self.assertFalse(self.hub.lock.locked)
        self.assertEqual(self.client.post("/devices/light.kitchen/on").status_code, 200)          # the Wi-Fi is open as ever
        self.assertEqual(self.client.post("/devices/light.kitchen/on", headers=self.AWAY).status_code, 403)

    # ---- letting a phone out is a change to the house ----
    def test_the_switch_needs_the_code(self):
        phone = self.admit()
        for m, path in [("POST", f"/phones/{phone['id']}/remote")]:
            self.assertTrue(needs_code(m, path))


if __name__ == "__main__":
    unittest.main()
