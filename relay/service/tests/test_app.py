# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The service over HTTP: what a hub can ask, and the door only frps may use."""
import tempfile, unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import CLAIMS_PER_DAY, make
from registry import DAY, Registry


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
        self.assertTrue(self.c.get("/names/temi").json()["free"])
        made = self.c.post("/houses", json={"name": "temi"})
        self.assertEqual(made.status_code, 201)
        secret = made.json()["secret"]
        self.assertFalse(made.json()["carried"])
        self.assertEqual(self.c.get("/names/temi", params={"also": ["Holts"]}).json()["suggestions"][:2], ["temis-house", "temi-house"])
        seen = self.c.get("/houses/temi", headers={"Authorization": f"Bearer {secret}"})
        self.assertEqual(seen.status_code, 200); self.assertEqual(seen.json()["address"], "temi.elyir.app")
        self.assertNotIn("secret", seen.json())

    def test_a_taken_name_answers_with_somewhere_else_to_go(self):
        self.c.post("/houses", json={"name": "temi"})
        again = self.c.post("/houses", json={"name": "temi"})
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["detail"]["why"], "taken")
        self.assertEqual(len(again.json()["detail"]["suggestions"]), 3)

    def test_a_name_that_cannot_be_is_said_in_words(self):
        bad = self.c.post("/houses", json={"name": "-nope"})
        self.assertEqual(bad.status_code, 422); self.assertIn("dash", bad.json()["detail"])

    def test_only_the_house_that_claimed_a_name_can_see_or_release_it(self):
        secret = self.c.post("/houses", json={"name": "temi"}).json()["secret"]
        for wrong in ({}, {"Authorization": "Bearer guess"}, {"Authorization": "Bearer "}):
            self.assertEqual(self.c.get("/houses/temi", headers=wrong).status_code, 404, wrong)
        self.assertEqual(self.c.get("/houses/temi", headers={"Authorization": f"Bearer {secret}"}).status_code, 200)
        self.assertEqual(self.c.delete("/houses/temi", headers={"Authorization": "Bearer guess"}).status_code, 404)
        self.assertEqual(self.c.delete("/houses/temi", headers={"Authorization": f"Bearer {secret}"}).status_code, 204)
        self.assertTrue(self.c.get("/names/temi").json()["free"])

    def test_one_address_cannot_claim_names_all_day(self):
        for i in range(CLAIMS_PER_DAY): self.assertEqual(self.c.post("/houses", json={"name": f"house{i}"}).status_code, 201)
        self.assertEqual(self.c.post("/houses", json={"name": "one-more"}).status_code, 429)
        self.t += DAY + 1
        self.assertEqual(self.c.post("/houses", json={"name": "one-more"}).status_code, 201)

    def test_frps_is_told_yes_or_no(self):
        secret = self.c.post("/houses", json={"name": "temi"}).json()["secret"]
        ask = {"version": "0.1.0", "op": "Login", "content": {"user": "temi", "metas": {"house": "temi", "secret": secret}}}
        self.assertEqual(self.local.post("/frps", json=ask).json(), {"reject": True, "reject_reason": "this house is not carried by this relay"})
        self.r.grant("temi", self.t + 30 * DAY)
        self.assertEqual(self.local.post("/frps", json=ask).json(), {"reject": False, "unchange": True})

    def test_the_relays_door_is_not_open_to_anyone_else(self):
        ask = {"op": "Login", "content": {}}
        self.assertEqual(self.c.post("/frps", json=ask).status_code, 404)                       # not from this box
        self.assertEqual(self.local.post("/frps", json=ask, headers={"X-Forwarded-For": "203.0.113.9"}).status_code, 404)   # came through Caddy


if __name__ == "__main__":
    unittest.main()
