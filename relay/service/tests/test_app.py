# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The service over HTTP: what a hub can ask, and the door only frps may use."""
import tempfile, unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import CLAIMS_PER_DAY, WRONG_INVITES_PER_DAY, make, nearby_origins, seed_own_names
from registry import DAY, TICKET_REACH, Payers, Registry, sign_ticket


class Service(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.t = 1_790_000_000.0
        self.r = Registry(Path(self.dir.name) / "houses.db", now=lambda: self.t)
        # TestClient's own address is "testclient"; frps is loopback, so the plugin tests use one of each.
        self.c = TestClient(make(self.r, now=lambda: self.t))
        self.local = TestClient(make(self.r, now=lambda: self.t), client=("127.0.0.1", 50000))

    def tearDown(self):
        self.r.db.close(); self.dir.cleanup()

    def test_a_hub_looks_claims_and_checks_on_its_name(self):
        self.assertTrue(self.c.get("/names/jordan").json()["free"])
        made = self.c.post("/houses", json={"name": "jordan"})
        self.assertEqual(made.status_code, 201)
        secret = made.json()["secret"]
        self.assertFalse(made.json()["carried"])
        self.assertEqual(self.c.get("/names/jordan", params={"also": ["Cedar"]}).json()["suggestions"][:2], ["jordans-house", "jordan-house"])
        seen = self.c.get("/houses/jordan", headers={"Authorization": f"Bearer {secret}"})
        self.assertEqual(seen.status_code, 200); self.assertEqual(seen.json()["address"], "jordan.elyir.app")
        self.assertNotIn("secret", seen.json())

    def test_a_claim_says_how_to_reach_the_relay_so_nobody_types_it(self):
        c = TestClient(make(self.r, now=lambda: self.t, relay={"addr": "relay.elyir.app", "token": "shared"}))
        made = c.post("/houses", json={"name": "jordan"}).json()
        self.assertEqual(made["relay"], {"addr": "relay.elyir.app", "token": "shared"})
        seen = c.get("/houses/jordan", headers={"Authorization": f"Bearer {made['secret']}"}).json()
        self.assertEqual(seen["relay"]["addr"], "relay.elyir.app")

    def test_the_offer_is_closed_until_somebody_opens_it(self):
        self.assertEqual(self.c.get("/offer").json(), {"open": False, "price": None, "pay": None})
        opened = TestClient(make(self.r, offer={"open": True, "price": "$3 a month", "pay": "https://pay.example/x"}))
        self.assertTrue(opened.get("/offer").json()["open"])

    def test_a_taken_name_answers_with_somewhere_else_to_go(self):
        self.c.post("/houses", json={"name": "jordan"})
        again = self.c.post("/houses", json={"name": "jordan"})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"]["why"], "taken")
        self.assertEqual(len(again.json()["detail"]["suggestions"]), 3)

    def test_a_name_that_cannot_be_is_said_in_words(self):
        bad = self.c.post("/houses", json={"name": "-nope"})
        self.assertEqual(bad.status_code, 422); self.assertIn("dash", bad.json()["detail"])

    def test_only_the_house_that_claimed_a_name_can_see_or_release_it(self):
        secret = self.c.post("/houses", json={"name": "jordan"}).json()["secret"]
        for wrong in ({}, {"Authorization": "Bearer guess"}, {"Authorization": "Bearer "}):
            self.assertEqual(self.c.get("/houses/jordan", headers=wrong).status_code, 404, wrong)
        self.assertEqual(self.c.get("/houses/jordan", headers={"Authorization": f"Bearer {secret}"}).status_code, 200)
        self.assertEqual(self.c.delete("/houses/jordan", headers={"Authorization": "Bearer guess"}).status_code, 404)
        self.assertEqual(self.c.delete("/houses/jordan", headers={"Authorization": f"Bearer {secret}"}).status_code, 204)
        self.assertTrue(self.c.get("/names/jordan").json()["free"])

    def test_one_address_cannot_claim_names_all_day(self):
        for i in range(CLAIMS_PER_DAY): self.assertEqual(self.c.post("/houses", json={"name": f"house{i}"}).status_code, 201)
        self.assertEqual(self.c.post("/houses", json={"name": "one-more"}).status_code, 429)
        self.t += DAY + 1
        self.assertEqual(self.c.post("/houses", json={"name": "one-more"}).status_code, 201)

    def test_frps_is_told_yes_or_no(self):
        secret = self.c.post("/houses", json={"name": "jordan"}).json()["secret"]
        ask = {"version": "0.1.0", "op": "Login", "content": {"user": "jordan", "metas": {"house": "jordan", "secret": secret}}}
        self.assertEqual(self.local.post("/frps", json=ask).json(), {"reject": True, "reject_reason": "this house is not carried by this relay"})
        self.r.grant("jordan", self.t + 30 * DAY)
        self.assertEqual(self.local.post("/frps", json=ask).json(), {"reject": False, "unchange": True})

    def test_the_relays_door_is_not_open_to_anyone_else(self):
        ask = {"op": "Login", "content": {}}
        self.assertEqual(self.c.post("/frps", json=ask).status_code, 404)                       # not from this box
        self.assertEqual(self.local.post("/frps", json=ask, headers={"X-Forwarded-For": "203.0.113.9"}).status_code, 404)   # came through Caddy

    def test_an_invite_at_the_claim_or_after_it(self):
        made = self.c.post("/houses", json={"name": "desk", "invite": self.r.invite(self.t + 365 * DAY)})
        self.assertEqual(made.status_code, 201); self.assertTrue(made.json()["carried"])
        later = self.c.post("/houses", json={"name": "shop"}).json()
        self.assertFalse(later["carried"])
        key = {"Authorization": f"Bearer {later['secret']}"}
        got = self.c.post("/houses/shop/invite", json={"code": self.r.invite(self.t + 365 * DAY)}, headers=key)
        self.assertEqual(got.status_code, 200); self.assertTrue(got.json()["carried"])
        self.assertTrue(self.c.get("/houses/shop", headers=key).json()["carried"])

    def test_a_bad_code_says_why_and_takes_no_name(self):
        bad = self.c.post("/houses", json={"name": "desk", "invite": "AAAA-BBBB-CCCC"})
        self.assertEqual(bad.status_code, 403)
        self.assertEqual(bad.json()["detail"]["why"], "invite"); self.assertIn("typo", bad.json()["detail"]["message"])
        self.assertTrue(self.c.get("/names/desk").json()["free"])

    def test_only_the_holder_brings_an_invite_and_guessing_stops(self):
        secret = self.c.post("/houses", json={"name": "desk"}).json()["secret"]
        code = self.r.invite(self.t + 365 * DAY)
        self.assertEqual(self.c.post("/houses/desk/invite", json={"code": code}, headers={"Authorization": "Bearer nope"}).status_code, 404)
        self.assertIsNone(self.r.invite_problem(code))
        key = {"Authorization": f"Bearer {secret}"}
        for _ in range(WRONG_INVITES_PER_DAY):
            self.assertEqual(self.c.post("/houses/desk/invite", json={"code": "AAAA-BBBB-CCCC"}, headers=key).status_code, 403)
        self.assertEqual(self.c.post("/houses/desk/invite", json={"code": code}, headers=key).status_code, 429)
        self.t += DAY + 1
        self.assertEqual(self.c.post("/houses/desk/invite", json={"code": code}, headers=key).status_code, 404)   # its day was up: let go
        self.assertIsNone(self.r.invite_problem(code))

    def test_a_paid_plan_elsewhere_carries_a_house_that_brings_its_ticket(self):
        """Bench Cloud signs "carry atlas until then"; the printer brings it with its own secret."""
        keyfile = Path(self.dir.name) / "payers"
        keyfile.write_text("# payer key\nbench s3cret\n")
        c = TestClient(make(self.r, now=lambda: self.t, payers=Payers(keyfile)))
        secret = c.post("/houses", json={"name": "atlas"}).json()["secret"]
        me = {"Authorization": f"Bearer {secret}"}
        good = lambda **k: sign_ticket(**{"key": "s3cret", "payer": "bench", "name": "atlas", "until": self.t + 30 * DAY,
                                          "expires": self.t + 3600, "house": "h_1", **k})
        carried = c.post("/houses/atlas/carry", json={"ticket": good()}, headers=me)
        self.assertEqual(carried.status_code, 200)
        self.assertTrue(carried.json()["carried"]); self.assertEqual(carried.json()["entitled_until"], self.t + 30 * DAY)
        self.assertIsNone(self.c.get("/houses/atlas", headers=me).json()["held_until"])
        # a ticket only works with the name's own secret, for that name, signed by a known payer, in time
        self.assertEqual(c.post("/houses/atlas/carry", json={"ticket": good()}).status_code, 404)
        for bad, why in ((good(name="juno"), "another name"), (good(key="guess"), "signed"), (good(expires=self.t - 1), "ran out"),
                         (good(payer="someone"), "signed"), ("nonsense", "isn't a ticket")):
            r = c.post("/houses/atlas/carry", json={"ticket": bad}, headers=me)
            self.assertEqual(r.status_code, 403); self.assertIn(why, r.json()["detail"]["message"])
        # never further than TICKET_REACH, and never shortening a longer grant
        c.post("/houses/atlas/carry", json={"ticket": good(until=self.t + 400 * DAY)}, headers=me)
        self.assertEqual(self.r.status("atlas")["entitled_until"], self.t + TICKET_REACH)
        self.r.grant("atlas", self.t + 365 * DAY, "by hand")
        c.post("/houses/atlas/carry", json={"ticket": good()}, headers=me)
        self.assertEqual(self.r.status("atlas")["entitled_until"], self.t + 365 * DAY)
        # a plan that stops simply runs out: carried no longer, but the name stays the house's
        self.t += 366 * DAY
        self.assertFalse(self.r.status("atlas")["carried"]); self.assertTrue(self.r.taken("atlas"))

    def test_a_payer_is_added_on_the_volume_without_a_restart(self):
        keyfile = Path(self.dir.name) / "payers"
        payers = Payers(keyfile, env="other=k")
        self.assertEqual(payers.keys(), {"other": "k"})
        keyfile.write_text("bench s3cret\n")
        self.assertEqual(payers.keys(), {"other": "k", "bench": "s3cret"})

    def test_cloud_is_kept_for_the_service(self):
        for name in ("cloud", "cloud-staging", "printers-staging"):
            self.assertEqual(self.c.post("/houses", json={"name": name}).status_code, 422, name)


if __name__ == "__main__":
    unittest.main()


class Nearby(unittest.TestCase):
    """Which printers are on this Wi-Fi: names whose tunnel comes from the asker's public address."""
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.t = 1_790_000_000.0
        self.r = Registry(Path(self.dir.name) / "houses.db", now=lambda: self.t)
        for name in ("atlas", "juno", "janes-voron"):
            secret = self.r.claim(name)["secret"]
            self.r.grant(name, self.t + 365 * DAY)
            ip = "203.0.113.9" if name != "janes-voron" else "198.51.100.7"
            self.assertIsNone(self.r.judge("Login", {"user": name, "metas": {"house": name, "secret": secret},
                                                     "client_address": f"{ip}:51094"}))
        self.r.seed("api", "operator"); self.r.judge("Login", {"user": "api", "metas": {"house": "api", "secret": "operator"},
                                                               "client_address": "203.0.113.9:1"})
        self.app = make(self.r, now=lambda: self.t, nearby_origins=("https://printers.elyir.app",))

    def tearDown(self):
        self.r.db.close(); self.dir.cleanup()

    def test_a_page_sees_the_printers_behind_its_own_address_and_no_others(self):
        home = TestClient(self.app, client=("203.0.113.9", 4000))
        r = home.get("/nearby", headers={"Origin": "https://printers.elyir.app"})
        self.assertEqual(r.json(), {"names": ["atlas", "juno"]}, "the service's own names never show")
        self.assertEqual(r.headers["access-control-allow-origin"], "https://printers.elyir.app")
        self.assertEqual(r.headers["cache-control"], "no-store")
        elsewhere = TestClient(self.app, client=("192.0.2.1", 4000))
        self.assertEqual(elsewhere.get("/nearby").json(), {"names": []})
        self.assertNotIn("access-control-allow-origin", home.get("/nearby", headers={"Origin": "https://evil.example"}).headers)

    def test_a_house_that_stops_being_carried_drops_off_and_a_move_follows_it(self):
        self.r.grant("juno", self.t - 1)
        self.assertEqual(self.r.nearby("203.0.113.9"), ["atlas"])
        self.r.seen("atlas", "[2001:db8::5]:443")
        self.assertEqual(self.r.nearby("203.0.113.9"), [])
        self.assertEqual(self.r.nearby("2001:db8::5"), ["atlas"])

class OwnNames(unittest.TestCase):
    """The names the box carries for itself: each app is carried from the secret cloud-init hands it, and may
    read /nearby from a page, while staying out of the list /nearby gives."""
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.t = 1_790_000_000.0
        self.r = Registry(Path(self.dir.name) / "houses.db", now=lambda: self.t)

    def tearDown(self):
        self.r.db.close(); self.dir.cleanup()

    def test_every_app_on_this_box_is_always_carried(self):
        env = {"RELAY_SELF_SECRET": "a", "RELAY_PRINTERS_SECRET": "p", "RELAY_HOUSES_SECRET": "h", "RELAY_NEARBY_SECRET": "n"}
        seed_own_names(self.r, env)
        for name, secret in (("api", "a"), ("printers", "p"), ("houses", "h"), ("nearby", "n")):
            self.assertIsNone(self.r.judge("Login", {"user": name, "metas": {"house": name, "secret": secret},
                                                     "client_address": "203.0.113.9:1"}), name)
        self.t += 50 * 365 * DAY
        self.assertIsNone(self.r.judge("Login", {"user": "houses", "metas": {"house": "houses", "secret": "h"}}))
        self.assertEqual(self.r.nearby("203.0.113.9"), [], "the service's own names never show on /nearby")

    def test_a_name_without_its_secret_is_not_seeded(self):
        seed_own_names(self.r, {"RELAY_PRINTERS_SECRET": "p"})
        self.assertIsNotNone(self.r.judge("Login", {"user": "houses", "metas": {"house": "houses", "secret": ""}}))

    def test_both_apps_may_read_nearby_and_their_dev_servers_too(self):
        self.assertEqual(nearby_origins("elyir.app", {}), ("https://printers.elyir.app", "https://houses.elyir.app",
                                                           "http://localhost:5173", "http://localhost:5174"))
        self.assertEqual(nearby_origins("elyir.app", {"RELAY_NEARBY_ORIGINS": " https://houses.elyir.app , "}), ("https://houses.elyir.app",))
        app = make(self.r, nearby_origins=nearby_origins("elyir.app", {}))
        r = TestClient(app, client=("203.0.113.9", 4000)).get("/nearby", headers={"Origin": "https://houses.elyir.app"})
        self.assertEqual(r.headers["access-control-allow-origin"], "https://houses.elyir.app")
