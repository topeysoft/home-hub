# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The house's own address: offered only when it can be paid for, claimed once, its secret kept here and
never shown, and outside turned on and off through a file the host checks again (host/away.sh)."""
import json, os, unittest
from pathlib import Path
from unittest import mock

from hub.address import Unreachable, first_guess
from hub.lock import needs_code
from tests.apptest import ApiTest

SECRET = "s" * 43
TOKEN = "a" * 64


class Service:
    """The registration service, as far as the hub can tell: what relay/service/app.py answers."""
    def __init__(self, offer=None):
        self.houses: dict[str, str] = {}
        self.carried: set[str] = set()
        self.offer = offer or {"open": True, "price": "$3 a month", "pay": "https://pay.example/jordan"}
        self.calls = []

    def __call__(self, method, path, body=None, secret=None, timeout=8.0):
        self.calls.append((method, path))
        if path == "/offer": return 200, self.offer
        if path.startswith("/names/"):
            name = path.split("/")[2].split("?")[0]
            return 200, ({"name": name, "free": False, "why": "taken", "suggestions": ["jordans-house", "jordan-cedar", "jordan-lee"]}
                         if name in self.houses else {"name": name, "free": True, "address": f"{name}.elyir.app"})
        if path == "/houses" and method == "POST":
            name = body["name"]
            if name in self.houses: return 409, {"detail": {"why": "taken", "suggestions": ["jordans-house"]}}
            self.houses[name] = SECRET
            return 201, {"name": name, "address": f"{name}.elyir.app", "secret": SECRET, "carried": False,
                         "relay": {"addr": "relay.elyir.app", "token": TOKEN}}
        if path.startswith("/houses/"):
            name = path.split("/")[2]
            if self.houses.get(name) != secret: return 404, {"detail": "No house by that name holds that key."}
            if method == "DELETE": del self.houses[name]; return 204, None
            return 200, {"name": name, "carried": name in self.carried, "held_until": None, "entitled_until": 1.9e9 if name in self.carried else None,
                         "relay": {"addr": "relay.elyir.app", "token": TOKEN}}
        return 404, None


class Guess(unittest.TestCase):
    def test_the_field_starts_from_what_the_house_was_called(self):
        self.assertEqual(first_guess("Jordan's house"), "jordan")
        self.assertEqual(first_guess("Maple Court"), "maple-court")
        self.assertEqual(first_guess("The Lee Home"), "lee")
        self.assertEqual(first_guess(None), "home-hub")
        self.assertEqual(first_guess("House"), "home-hub")


class Addressing(ApiTest):
    def setUp(self):
        super().setUp()
        self.service = Service()
        self.hub.address.fetch = self.service
        self.hub.settings.set(home_name="Jordan's house", owner={"name": "Jordan Lee"})
        self.hub.location = {"name": "Cedar Falls, IA", "lat": 42.5, "lon": -92.4}

    def test_nothing_is_offered_until_the_service_says_it_can_be_paid_for(self):
        self.service.offer = {"open": False, "price": None, "pay": None}
        seen = self.client.get("/address").json()
        self.assertFalse(seen["offer"]["open"]); self.assertIsNone(seen["house"])
        self.assertEqual(seen["guess"], "jordan")

    def test_a_service_that_is_down_offers_nothing_and_breaks_nothing(self):
        self.hub.address.fetch = mock.Mock(side_effect=Unreachable("down"))
        self.assertFalse(self.client.get("/address").json()["offer"]["open"])
        self.assertEqual(self.client.get("/address/names/jordan").status_code, 503)

    def test_the_makers_own_hub_is_offered_it_by_hand(self):
        self.service.offer = {"open": False, "price": None, "pay": None}
        with mock.patch.dict(os.environ, {"HUB_AWAY_OFFER": "on"}):
            self.assertEqual(self.client.get("/address").json()["offer"], {"open": True, "price": None, "pay": None, "by_hand": True})

    def test_looking_sends_the_town_and_the_surname_as_hints(self):
        self.client.get("/address/names/jordan")
        path = self.service.calls[-1][1]
        self.assertIn("also=Cedar+Falls", path); self.assertIn("also=Lee", path)

    def test_claiming_keeps_the_secret_here_and_never_shows_it(self):
        out = self.client.post("/address", json={"name": "jordan"})
        self.assertEqual(out.status_code, 200)
        self.assertEqual(out.json()["address"], "jordan.elyir.app")
        self.assertNotIn(SECRET, json.dumps(out.json()))
        self.assertNotIn(SECRET, json.dumps(self.client.get("/address").json()))
        kept = json.loads((self.data / "address.json").read_text())
        self.assertEqual(kept["secret"], SECRET)
        self.assertEqual(oct((self.data / "address.json").stat().st_mode & 0o777), "0o600")

    def test_claiming_asks_the_host_to_turn_outside_on_with_values_it_can_check(self):
        self.client.post("/address", json={"name": "jordan"})
        self.assertEqual(json.loads((self.data / "away.request").read_text())["want"], "on")
        values = (self.data / "away.env").read_text()
        self.assertEqual(values, f"HUB_AWAY_HOUSE=jordan\nHUB_RELAY_SECRET={SECRET}\nHUB_RELAY_TOKEN={TOKEN}\nHUB_RELAY_ADDR=relay.elyir.app\nHUB_AWAY_ZONE=elyir.app\n")

    def test_a_taken_address_answers_with_somewhere_else(self):
        self.service.houses["jordan"] = "someone else's"
        out = self.client.post("/address", json={"name": "jordan"})
        self.assertEqual(out.status_code, 409); self.assertEqual(out.json()["detail"]["why"], "taken")
        self.assertFalse((self.data / "away.request").exists())

    def test_a_house_has_one_address(self):
        self.client.post("/address", json={"name": "jordan"})
        self.assertEqual(self.client.post("/address", json={"name": "palace"}).status_code, 422)

    def test_what_the_panel_shows_once_the_house_is_carried(self):
        self.client.post("/address", json={"name": "jordan"})
        self.assertFalse(self.client.get("/address").json()["carried"])
        self.service.carried.add("jordan"); self.hub.address._status = None
        (self.data / "away.json").write_text(json.dumps({"on": True, "house": "jordan"}))
        (self.data / "away.request").unlink()
        seen = self.client.get("/address").json()
        self.assertTrue(seen["carried"]); self.assertTrue(seen["on"]); self.assertFalse(seen["waiting"])

    def test_off_and_on_keep_the_address(self):
        self.client.post("/address", json={"name": "jordan"})
        self.assertEqual(self.client.post("/address/off").json()["want"], "off")
        self.assertEqual(json.loads((self.data / "away.request").read_text())["want"], "off")
        self.assertEqual(self.client.get("/address").json()["house"], "jordan")
        self.assertEqual(self.client.post("/address/on").json()["want"], "on")
        self.assertEqual(self.client.post("/address/sideways").status_code, 404)

    def test_giving_it_back_takes_the_secret_out_of_everything(self):
        self.client.post("/address", json={"name": "jordan"})
        self.client.delete("/address")
        self.assertNotIn("jordan", self.service.houses)
        self.assertFalse((self.data / "address.json").exists())
        self.assertEqual((self.data / "away.env").read_text(), "")
        self.assertEqual(json.loads((self.data / "away.request").read_text())["want"], "forget")

    def test_an_answer_that_does_not_look_right_never_reaches_the_host(self):
        def odd(method, path, body=None, secret=None, timeout=8.0):
            if path == "/houses": return 201, {"name": "jordan", "address": "jordan.elyir.app", "secret": "bad secret; rm -rf /", "relay": {"addr": "relay.elyir.app", "token": TOKEN}}
            return self.service(method, path, body, secret, timeout)
        self.hub.address.fetch = odd
        self.client.post("/address", json={"name": "jordan"})
        self.assertFalse((self.data / "away.request").exists())
        self.assertFalse((self.data / "away.env").exists())

    def test_it_is_behind_the_code_and_the_keys(self):
        for m, p in (("POST", "/address"), ("POST", "/address/on"), ("POST", "/address/off"), ("DELETE", "/address")):
            self.assertTrue(needs_code(m, p), (m, p))
        self.assertFalse(needs_code("GET", "/address"))
        self.assertFalse(needs_code("GET", "/address/names/jordan"))

    def test_the_house_is_backed_up_with_its_address(self):
        from hub import backup
        self.assertIn("address.json", backup.DATA_FILES)


class Paths(unittest.TestCase):
    def test_the_host_watches_the_file_this_writes(self):
        unit = (Path(__file__).resolve().parents[2] / "driver-layer" / "host" / "home-hub-away.path").read_text()
        self.assertIn("brain-data/away.request", unit)
