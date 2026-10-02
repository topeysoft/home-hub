# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The registry: who gets a name, who gets carried, and what frps is told.

The judge cases are shaped exactly like what frps 0.71.0 sent a plugin on 1 October 2026 (checked with
the real frps and frpc, docs/away.md step 4): Login carries `user` and `metas`, NewProxy carries the
same metas under `user`, and frps has already prefixed the proxy name with the user.
"""
import tempfile, unittest
from pathlib import Path

from registry import DAY, Registry, clean, problem


class Clock:
    def __init__(self): self.t = 1_790_000_000.0
    def __call__(self): return self.t


def login(house, secret, user=None):
    return {"version": "0.71.0", "user": house if user is None else user, "metas": {"house": house, "secret": secret}, "timestamp": 1, "privilege_key": "x"}


def proxy(house, secret, domains, kind="https", user=None):
    return {"user": {"user": house if user is None else user, "metas": {"house": house, "secret": secret}, "run_id": "r"},
            "proxy_name": f"{house}.p", "proxy_type": kind, "custom_domains": domains}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.r = Registry(Path(self.dir.name) / "houses.db", now=self.clock)

    def tearDown(self):
        self.r.db.close(); self.dir.cleanup()


class Names(Base):
    def test_what_a_house_may_be_called(self):
        for ok in ("temi", "palace", "temis-house", "a1", "x", "a" * 30): self.assertIsNone(problem(ok), ok)
        for bad in ("", "-temi", "temi-", "Temi", "temi house", "temi.app", "a" * 31, "café"): self.assertIsNotNone(problem(bad), bad)

    def test_the_services_own_names_are_kept(self):
        for kept in ("api", "www", "home", "relay", "selftest", "printers"):
            self.assertEqual(problem(kept), "That one is kept for the service itself.")

    def test_what_somebody_typed_becomes_a_name(self):
        self.assertEqual(clean("Temi's House"), "temis-house")
        self.assertEqual(clean("  The  Palace!! "), "the-palace")
        self.assertEqual(clean("Temi’s"), "temis")

    def test_a_free_name_says_where_it_will_be(self):
        self.assertEqual(self.r.look("temi"), {"name": "temi", "free": True, "address": "temi.elyir.app"})

    def test_a_taken_name_offers_three_that_are_free(self):
        self.r.claim("temi"); self.r.claim("temis-house")
        seen = self.r.look("temi", ["Holts Summit", "Adeyeri"])
        self.assertFalse(seen["free"]); self.assertEqual(seen["why"], "taken")
        self.assertEqual(seen["suggestions"], ["temi-house", "temi-holts-summit", "temi-adeyeri"])
        for s in seen["suggestions"]: self.assertTrue(self.r.look(s)["free"])

    def test_a_name_that_cannot_be_still_gets_somewhere_to_go(self):
        seen = self.r.look("api")
        self.assertFalse(seen["free"]); self.assertIn("kept", seen["why"])
        self.assertEqual(len(seen["suggestions"]), 3)


class Claiming(Base):
    def test_a_claim_hands_over_a_secret_once_and_keeps_only_its_hash(self):
        out = self.r.claim("temi")
        self.assertEqual(out["address"], "temi.elyir.app")
        self.assertGreater(len(out["secret"]), 30)
        raw = Path(self.dir.name, "houses.db").read_bytes()
        self.assertNotIn(out["secret"].encode(), raw)
        self.assertTrue(self.r.holder("temi", out["secret"]))
        self.assertFalse(self.r.holder("temi", out["secret"] + "x"))
        self.assertFalse(self.r.holder("temi", ""))

    def test_a_taken_name_cannot_be_claimed_twice(self):
        self.r.claim("temi")
        with self.assertRaises(LookupError): self.r.claim("temi")

    def test_a_name_nobody_pays_for_is_let_go_after_a_day(self):
        self.r.claim("temi")
        self.clock.t += DAY - 1; self.assertTrue(self.r.taken("temi"))
        self.clock.t += 2;       self.assertFalse(self.r.taken("temi"))
        self.r.claim("temi")     # somebody else may have it now

    def test_a_granted_name_is_kept_and_carried(self):
        self.r.claim("temi")
        self.r.grant("temi", self.clock.t + 365 * DAY)
        self.clock.t += 30 * DAY
        self.assertTrue(self.r.taken("temi"))
        self.assertTrue(self.r.status("temi")["carried"])

    def test_a_lapsed_house_keeps_its_name_and_is_not_carried(self):
        self.r.claim("temi"); self.r.grant("temi", self.clock.t + DAY)
        self.clock.t += 2 * DAY
        self.assertTrue(self.r.taken("temi"))
        self.assertFalse(self.r.status("temi")["carried"])

    def test_rotating_a_secret_retires_the_old_one(self):
        old = self.r.claim("temi")["secret"]
        new = self.r.rotate("temi")
        self.assertFalse(self.r.holder("temi", old)); self.assertTrue(self.r.holder("temi", new))

    def test_granting_a_name_nobody_holds_says_so(self):
        with self.assertRaises(LookupError): self.r.grant("nobody", self.clock.t + DAY)


class Judging(Base):
    def setUp(self):
        super().setUp()
        self.secret = self.r.claim("temi")["secret"]
        self.r.grant("temi", self.clock.t + 365 * DAY)

    def test_a_carried_house_logs_in_and_is_carried_under_its_own_name(self):
        self.assertIsNone(self.r.judge("Login", login("temi", self.secret)))
        self.assertIsNone(self.r.judge("NewProxy", proxy("temi", self.secret, ["temi.elyir.app"])))

    def test_a_wrong_or_missing_secret_is_refused(self):
        self.assertEqual(self.r.judge("Login", login("temi", "guess")), "this house is not known here")
        self.assertEqual(self.r.judge("Login", {"user": "temi", "metas": {}}), "this house is not known here")
        self.assertEqual(self.r.judge("Login", {}), "this house is not known here")

    def test_a_claimed_house_nobody_has_paid_for_is_not_carried(self):
        other = self.r.claim("palace")["secret"]
        self.assertEqual(self.r.judge("Login", login("palace", other)), "this house is not carried by this relay")

    def test_a_lapsed_house_is_refused_at_its_next_login(self):
        self.clock.t += 400 * DAY
        self.assertEqual(self.r.judge("Login", login("temi", self.secret)), "this house is not carried by this relay")

    def test_the_user_must_be_the_house_because_frps_names_proxies_by_it(self):
        self.assertEqual(self.r.judge("Login", login("temi", self.secret, user="palace")), "user must be the house's name")

    def test_a_house_is_carried_for_its_own_name_and_nothing_else(self):
        for domains in (["palace.elyir.app"], ["temi.elyir.app", "palace.elyir.app"], [], ["temi.elyir.app.evil.com"]):
            self.assertEqual(self.r.judge("NewProxy", proxy("temi", self.secret, domains)), "a house is carried only under its own name", domains)

    def test_only_raw_https_is_carried(self):
        for kind in ("tcp", "http", "udp", "stcp"):
            self.assertEqual(self.r.judge("NewProxy", proxy("temi", self.secret, ["temi.elyir.app"], kind=kind)), "only https is carried", kind)

    def test_the_services_own_name_is_always_carried(self):
        self.r.seed("api", "operator-chosen")
        self.assertIsNone(self.r.judge("Login", login("api", "operator-chosen")))
        self.assertIsNone(self.r.judge("NewProxy", proxy("api", "operator-chosen", ["api.elyir.app"])))
        self.clock.t += 50 * 365 * DAY
        self.assertIsNone(self.r.judge("Login", login("api", "operator-chosen")))


if __name__ == "__main__":
    unittest.main()
