# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A phone moving to the house's own name (design/away/, C): the one-time code minted at home, the token on the
other side for the same phone, the token working as a header and on a websocket, and the one other origin the hub
answers across names. Every route the move touches is tried from outside too, because that is where it is used."""
import json, time
from unittest import mock

from starlette.websockets import WebSocketDisconnect

from hub.phones import COOKIE
from tests.apptest import ApiTest

AWAY = {"X-Hub-Via": "relay"}
ORIGIN = "https://maple-court.elyir.app"
APP = "https://houses.elyir.app"


class Base(ApiTest):
    def setUp(self):
        super().setUp()
        self.lock_the_house("4821")
        self.phone, self.token = self.hub.phones.with_code("Temi's phone")
        self.client.cookies.set(COOKIE, self.token)
        (self.data / "address.json").write_text(json.dumps({"house": "maple-court", "secret": "s" * 43, "zone": "elyir.app", "want": "on"}))

    def move(self, **headers):
        return self.client.post("/phones/move", headers=headers)


class Moving(Base):
    def test_a_phone_of_the_house_gets_a_code_at_home_and_is_sent_into_the_app(self):
        r = self.move()
        self.assertEqual(r.status_code, 200)
        code = r.json()["code"]
        # design/houses/, MoveToApp: into the one app, the house and the code in the fragment, never the query
        self.assertEqual(r.json()["url"], f"{APP}/add#h=maple-court&c={code}")

    def test_the_code_is_one_a_person_can_read_off_one_screen_and_type_on_another(self):
        code = self.move().json()["code"]
        self.assertEqual(len(code), 8)
        self.assertTrue(set(code) <= set("ABCDEFGHJKMNPQRSTUVWXYZ23456789"), code)       # no 0/O, no 1/I/L
        typed = f"{code[:4].lower()} - {code[4:].lower()}"
        self.assertEqual(self.client.post("/phones/move/claim", json={"code": typed}).status_code, 200)

    def test_ten_wrong_codes_stop_the_claims_for_a_while_from_anywhere(self):
        code = self.move().json()["code"]
        for _ in range(10):
            self.assertEqual(self.client.post("/phones/move/claim", json={"code": "AAAAAAAA"}, headers=AWAY).status_code, 410)
        self.assertEqual(self.client.post("/phones/move/claim", json={"code": code}).status_code, 429)   # even the right one, for now
        with mock.patch("hub.phones.time.time", return_value=time.time() + 601):
            code = self.move().json()["code"]
            self.assertEqual(self.client.post("/phones/move/claim", json={"code": code}).status_code, 200)

    def test_never_from_outside_and_never_before_the_house_has_an_address(self):
        self.hub.phones.set_remote(self.phone["id"], True)
        self.assertEqual(self.move(**AWAY).status_code, 403)
        (self.data / "address.json").unlink()
        self.assertEqual(self.move().status_code, 409)

    def test_the_claim_is_the_same_phone_with_a_new_token_and_the_old_one_still_works(self):
        code = self.move().json()["code"]
        self.client.cookies.clear()
        got = self.client.post("/phones/move/claim", json={"code": code})
        self.assertEqual(got.status_code, 200)
        new = got.json()["token"]
        self.assertNotEqual(new, self.token)
        self.assertEqual(got.json()["phone"]["id"], self.phone["id"])
        self.assertEqual(self.hub.phones.identify(new)["id"], self.phone["id"])
        self.assertEqual(self.hub.phones.identify(self.token)["id"], self.phone["id"])     # the old icon still opens
        self.assertTrue(self.hub.phones._public(self.hub.phones.get(self.phone["id"]))["moved"])

    def test_a_code_works_once_and_not_after_ten_minutes(self):
        code = self.move().json()["code"]
        self.assertEqual(self.client.post("/phones/move/claim", json={"code": code}).status_code, 200)
        self.assertEqual(self.client.post("/phones/move/claim", json={"code": code}).status_code, 410)
        code = self.move().json()["code"]
        with mock.patch("hub.phones.time.time", return_value=time.time() + 601):
            self.assertEqual(self.client.post("/phones/move/claim", json={"code": code}).status_code, 410)
        self.assertEqual(self.client.post("/phones/move/claim", json={"code": "guess"}).status_code, 410)

    def test_the_claim_can_be_made_from_outside_and_the_token_still_obeys_the_door(self):
        code = self.move().json()["code"]
        self.client.cookies.clear()
        got = self.client.post("/phones/move/claim", json={"code": code}, headers=AWAY)
        self.assertEqual(got.status_code, 200)
        bearer = {"Authorization": f"Bearer {got.json()['token']}", **AWAY}
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/home", headers=bearer).status_code, 403)       # not let out yet
        self.hub.phones.set_remote(self.phone["id"], True)
        self.assertEqual(self.client.get("/home", headers=bearer).status_code, 200)


class Token(Base):
    def test_the_token_works_as_a_header_exactly_as_the_cookie_does(self):
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/home").status_code, 401)
        self.assertEqual(self.client.get("/home", headers={"Authorization": f"Bearer {self.token}"}).status_code, 200)
        self.assertEqual(self.client.get("/home", headers={"Authorization": "Bearer guess"}).status_code, 401)

    def test_and_on_a_websocket_as_a_subprotocol_never_in_the_url(self):
        self.client.cookies.clear()
        with self.client.websocket_connect("/stream", subprotocols=["hub", self.token]) as ws:
            self.assertEqual(ws.accepted_subprotocol, "hub")
            self.assertEqual(json.loads(ws.receive_text())["type"], "status")
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect("/stream", subprotocols=["hub", "guess"]) as ws:
                ws.receive_text()
        self.assertEqual(caught.exception.code, 4401)

    def test_from_outside_the_websocket_still_needs_the_phone_let_out(self):
        self.client.cookies.clear()
        with self.assertRaises(WebSocketDisconnect) as caught:
            with self.client.websocket_connect("/stream", subprotocols=["hub", self.token], headers=AWAY) as ws:
                ws.receive_text()
        self.assertEqual(caught.exception.code, 4403)

    def test_a_phone_of_the_house_is_told_the_name_at_home(self):
        env = self.data / ".env"
        env.write_text("HUB_LAN_NAME=192-168-86-53.maple-court.home.elyir.app\n")
        with mock.patch.dict("os.environ", {"HUB_DRIVER": str(self.data)}):
            me = self.client.get("/phones/me").json()
            self.assertEqual(me["lan"], "192-168-86-53.maple-court.home.elyir.app")
            self.assertEqual(me["address"], ORIGIN)
            self.client.cookies.clear()
            self.assertIsNone(self.client.get("/phones/me").json()["lan"])                   # a stranger is told nothing


class AcrossNames(Base):
    def preflight(self, origin, pna=True):
        h = {"Origin": origin, "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "authorization"}
        if pna: h["Access-Control-Request-Private-Network"] = "true"
        return self.client.options("/home", headers=h)

    def test_the_houses_own_name_may_call_the_hub_at_home(self):
        r = self.preflight(ORIGIN)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(r.headers["access-control-allow-origin"], ORIGIN)
        self.assertEqual(r.headers["access-control-allow-private-network"], "true")
        self.assertIn("Authorization", r.headers["access-control-allow-headers"])
        got = self.client.get("/home", headers={"Origin": ORIGIN, "Authorization": f"Bearer {self.token}"})
        self.assertEqual(got.headers["access-control-allow-origin"], ORIGIN)

    def test_a_refusal_is_readable_too(self):
        self.client.cookies.clear()
        r = self.client.get("/home", headers={"Origin": ORIGIN})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.headers["access-control-allow-origin"], ORIGIN)

    def test_no_other_site_is_answered(self):
        for origin in ("https://evil.example", "https://other.elyir.app", "http://maple-court.elyir.app", "null"):
            r = self.preflight(origin)
            self.assertNotIn("access-control-allow-origin", r.headers, origin)
            got = self.client.get("/home", headers={"Origin": origin})
            self.assertNotIn("access-control-allow-origin", got.headers, origin)

    def test_nothing_is_answered_across_names_before_the_house_has_an_address(self):
        (self.data / "address.json").unlink()
        self.assertNotIn("access-control-allow-origin", self.preflight(ORIGIN).headers)
        self.assertNotIn("access-control-allow-origin", self.preflight(APP).headers)

    def test_a_phone_claimed_by_the_app_is_in_it_and_one_moved_only_to_the_name_is_not(self):
        code = self.move().json()["code"]
        self.client.post("/phones/move/claim", json={"code": code}, headers={"Origin": ORIGIN})
        self.assertFalse(self.client.get("/phones/me").json()["phone"]["in_app"])
        code = self.move().json()["code"]
        self.client.post("/phones/move/claim", json={"code": code}, headers={"Origin": APP})
        self.assertTrue(self.client.get("/phones/me").json()["phone"]["in_app"])

    def test_the_app_every_house_lives_in_may_call_it_too(self):
        r = self.preflight(APP)
        self.assertEqual(r.headers["access-control-allow-origin"], APP)
        claim = self.client.options("/phones/move/claim", headers={"Origin": APP, "Access-Control-Request-Method": "POST",
                                                                   "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(claim.status_code, 204)


class Framing(Base):
    """Who may show the panel inside a page of their own (found 3 October: until then, anybody)."""
    def test_only_the_house_and_the_app_may_frame_the_panel(self):
        csp = self.client.get("/alive").headers["content-security-policy"]
        self.assertEqual(csp, f"frame-ancestors 'self' {APP} {ORIGIN}")

    def test_a_house_with_no_address_frames_only_itself(self):
        (self.data / "address.json").unlink()
        self.assertEqual(self.client.get("/alive").headers["content-security-policy"], "frame-ancestors 'self'")


class SocketOrigins(Base):
    """A websocket's page is the one check it has: no CORS. Found 3 October, when nothing looked at it."""
    def connect(self, origin=None):
        headers = {"Origin": origin} if origin else {}
        with self.client.websocket_connect("/stream", subprotocols=["hub", self.token], headers=headers) as ws:
            return json.loads(ws.receive_text())["type"]

    def test_the_page_itself_the_houses_names_and_the_app_are_let_in(self):
        self.client.cookies.clear()
        for origin in (None, "http://testserver", ORIGIN, APP, "http://localhost:5173"):
            self.assertEqual(self.connect(origin), "status", origin)

    def test_another_site_is_refused_even_holding_a_token(self):
        self.client.cookies.clear()
        for origin in ("https://evil.example", "https://other.elyir.app", "null"):
            with self.assertRaises(WebSocketDisconnect) as caught:
                self.connect(origin)
            self.assertEqual(caught.exception.code, 4403, origin)
