"""Run from brain/: .venv/bin/python -m unittest -v. The phones that belong to the house: asking, allowing, the code, leaving."""
import tempfile, time, unittest
from pathlib import Path
from hub.phones import Phones, open_to_strangers, SPANS
from hub.lock import needs_code


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, kind, subject, old=None, new=None, source="device", detail=None): self.rows.append((kind, subject, new, source, detail))


class FakeHub:
    def __init__(self):
        self.log = FakeLog(); self.sent = []
    def _broadcast(self, msg): self.sent.append(msg)


class PhonesTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.hub = FakeHub()
        self.phones = Phones(self.hub, Path(self.dir.name) / "phones.json")

    def tearDown(self): self.dir.cleanup()

    def test_a_stranger_is_nobody(self):
        self.assertIsNone(self.phones.identify(None))
        self.assertIsNone(self.phones.identify("made-up"))
        self.assertEqual(self.phones.list(), {"phones": [], "asks": []})

    def test_the_code_lets_a_phone_in_and_it_stays(self):
        p, token = self.phones.with_code("Sam's iPhone")
        self.assertEqual(self.phones.identify(token)["id"], p["id"])
        self.assertIsNone(p["expires"]); self.assertFalse(p["remote"]); self.assertEqual(p["how"], "code")
        self.assertNotIn(token, (Path(self.dir.name) / "phones.json").read_text())   # only the hash is kept
        self.assertTrue(self.phones.list(me=p)["phones"][0]["me"])

    def test_asking_issues_nothing_until_the_wall_allows(self):
        ask = self.phones.ask("Sam's iPhone")
        self.assertEqual(self.phones.claim(ask["id"]), ("waiting", None, None))
        self.assertEqual(len(self.phones.list()["asks"]), 1)
        self.assertEqual(self.phones.list()["phones"], [])
        allowed = self.phones.allow(ask["id"], "weekend")
        state, phone, token = self.phones.claim(ask["id"])
        self.assertEqual((state, phone["id"]), ("allowed", allowed["id"]))
        self.assertEqual(self.phones.identify(token)["name"], "Sam's iPhone")
        self.assertAlmostEqual(phone["expires"], time.time() + SPANS["weekend"], delta=5)
        self.assertEqual(self.phones.claim(ask["id"]), ("gone", None, None))          # handed over once
        self.assertEqual(self.phones.list()["asks"], [])
        with self.assertRaises(KeyError): self.phones.allow(ask["id"])

    def test_not_now_ends_the_ask(self):
        ask = self.phones.ask("Someone")
        self.phones.deny(ask["id"])
        self.assertEqual(self.phones.claim(ask["id"]), ("gone", None, None))
        with self.assertRaises(KeyError): self.phones.allow(ask["id"])

    def test_only_the_three_spans(self):
        ask = self.phones.ask("Someone")
        with self.assertRaises(ValueError): self.phones.allow(ask["id"], "forever")

    def test_a_stay_ends_on_its_own(self):
        ask = self.phones.ask("A guest")
        self.phones.allow(ask["id"], "day")
        _, phone, token = self.phones.claim(ask["id"])
        phone["expires"] = time.time() - 1
        self.assertIsNone(self.phones.identify(token))
        self.assertEqual(self.phones.list()["phones"], [])
        self.assertIn(("phone", phone["id"], "left", "hub", {"name": "A guest", "why": "its stay was over"}), self.hub.log.rows)

    def test_removing_a_phone_is_instant(self):
        p, token = self.phones.with_code("Old phone")
        self.assertTrue(self.phones.remove(p["id"]))
        self.assertIsNone(self.phones.identify(token))
        self.assertFalse(self.phones.remove(p["id"]))
        again = Phones(self.hub, self.phones.path)                                     # gone from disk too
        self.assertEqual(again.list()["phones"], [])

    def test_home_only_until_promoted(self):
        p, _ = self.phones.with_code("Mine")
        self.assertFalse(p["remote"])
        self.assertTrue(self.phones.set_remote(p["id"], True)["remote"])
        with self.assertRaises(KeyError): self.phones.set_remote("nope", True)

    def test_setup_pairs_the_wall_without_asking(self):
        p, token = self.phones.from_setup("wall")
        self.assertEqual((p["name"], p["how"]), ("This wall", "setup"))
        self.assertEqual(self.phones.identify(token)["id"], p["id"])

    def test_every_change_is_logged_and_told_to_the_panels(self):
        ask = self.phones.ask("Sam")
        self.phones.allow(ask["id"]); self.phones.claim(ask["id"])
        kinds = [(k, new) for k, _, new, _, _ in self.hub.log.rows]
        self.assertEqual(kinds, [("phone", "asked"), ("phone", "joined")])
        self.assertTrue(all('"type": "phones"' in m for m in self.hub.sent))
        self.assertGreaterEqual(len(self.hub.sent), 2)

    def test_names_are_tidied(self):
        p, _ = self.phones.with_code("   Sam's   iPhone  ")
        self.assertEqual(p["name"], "Sam's iPhone")
        q, _ = self.phones.with_code("")
        self.assertEqual(q["name"], "A phone")


class GateTests(unittest.TestCase):
    def test_what_a_stranger_may_ask_for(self):
        for m, p in [("GET", "/"), ("GET", "/index.html"), ("GET", "/assets/index-abc.js"), ("GET", "/manifest.webmanifest"), ("GET", "/icons/192.png"),
                     ("GET", "/phones/me"), ("POST", "/phones/ask"), ("GET", "/phones/claim/abc"), ("POST", "/phones/code"),
                     ("GET", "/qr.svg"), ("GET", "/phone"), ("GET", "/sounds/rain.mp3"), ("OPTIONS", "/home")]:
            self.assertTrue(open_to_strangers(m, p), p)

    def test_the_house_itself_is_not(self):
        for m, p in [("GET", "/home"), ("GET", "/setup/status"), ("GET", "/events"), ("POST", "/devices/light.kitchen/on"), ("GET", "/phones"),
                     ("DELETE", "/phones/abc"), ("POST", "/phones/asks/abc/allow"), ("GET", "/devices/cam/image"), ("GET", "/backup"), ("GET", "/health"), ("GET", "/rooms/kitchen/why")]:
            self.assertFalse(open_to_strangers(m, p), p)

    def test_letting_a_phone_in_or_out_needs_the_code_but_asking_does_not(self):
        for m, p in [("POST", "/phones/asks/abc/allow"), ("DELETE", "/phones/asks/abc"), ("DELETE", "/phones/abc"), ("POST", "/phones/abc/remote")]:
            self.assertTrue(needs_code(m, p), p)
        for m, p in [("POST", "/phones/ask"), ("POST", "/phones/code"), ("GET", "/phones"), ("GET", "/phones/me"), ("GET", "/phones/claim/abc")]:
            self.assertFalse(needs_code(m, p), p)


if __name__ == "__main__":
    unittest.main()
