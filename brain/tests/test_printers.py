# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Printers, against a fake printer door and a fake websocket: found, let in, followed, acted on, forgotten."""
import asyncio, json, os, stat, tempfile, unittest
from pathlib import Path

from hub import printers as P
from hub.settings import Settings

HOME = "https://192-168-86-73.obi1.home.elyir.app"
AWAY = "https://obi1.elyir.app"


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, kind, subject, old=None, new=None, source="device", detail=None, who=None):
        self.rows.append((kind, subject, new, detail))


class FakeHub:
    def __init__(self, tmp):
        self.settings = Settings(Path(tmp) / "settings.json")
        self.settings.set(home_name="Main Palace")
        self.log = FakeLog()
        self.pushed = []
    def _broadcast(self, msg): self.pushed.append(json.loads(msg))


class FakeDoor:
    """The printer door's public routes, as a request function: (method, url, body, headers, timeout, stream)."""
    def __init__(self):
        self.calls, self.polls, self.answer = [], 0, "allowed"

    def __call__(self, method, url, body=None, headers=None, timeout=10.0, stream=False):
        self.calls.append((method, url, body, headers))
        if url == P.NEARBY:
            return 200, {}, json.dumps({"names": ["main-palace", "obi1"]}).encode()
        if url == "https://main-palace.elyir.app/door/me":
            return 403, {}, b'{"detail": "away"}'
        if url == f"{AWAY}/door/me":
            return 200, {}, json.dumps({"paired": False, "printer": {"id": "obi1", "name": "OBI1"},
                                        "addresses": {"home": HOME, "away": AWAY}}).encode()
        if url == f"{HOME}/door/ask" and method == "POST":
            return 201, {}, json.dumps({"handle": "h1", "expires": 0}).encode()
        if url == f"{HOME}/door/ask/h1":
            self.polls += 1
            if self.polls < 2:
                return 200, {}, b'{"state": "waiting"}'
            if self.answer == "allowed":
                return 200, {}, json.dumps({"state": "allowed", "token": "TOK", "phone": {"id": "ph1"},
                                            "addresses": {"home": HOME, "away": AWAY}}).encode()
            return 200, {}, json.dumps({"state": self.answer}).encode()
        if method == "DELETE":
            return 204, {}, b""
        if stream:
            return 200, {"Content-Type": "image/png"}, FakeStream(b"PNG")
        return 404, {}, b"{}"


class FakeStream:
    def __init__(self, data): self.data = data
    def read(self, n=-1): d, self.data = self.data, b""; return d
    def close(self): pass


class FakeSocket:
    """Moonraker's websocket behind the door: answers calls, and lets the test push notifications."""
    def __init__(self, intent):
        self.intent, self.sent, self.inbox = intent, [], asyncio.Queue()
    async def send(self, raw):
        m = json.loads(raw)
        self.sent.append(m)
        result = self.intent if m["method"] == "printer.intent" else {"ok": True}
        await self.inbox.put(json.dumps({"jsonrpc": "2.0", "id": m["id"], "result": result}))
    async def notify(self, method, *params):
        await self.inbox.put(json.dumps({"jsonrpc": "2.0", "method": method, "params": list(params)}))
    async def close(self): await self.inbox.put(None)
    def __aiter__(self): return self
    async def __anext__(self):
        m = await self.inbox.get()
        if m is None: raise StopAsyncIteration
        return m


async def turn(times=40):
    for _ in range(times): await asyncio.sleep(0)


READY = {"state": "ready", "headline": "Ready", "detail": "8 spools loaded.", "actions": [], "job": None,
         "printer": {"nozzle": {"temperature": 28.9}, "bed": {"temperature": 26.2}}}


class Base(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.saved = P.STATE
        P.STATE = Path(self.dir.name) / "printers.json"
        self.hub, self.door = FakeHub(self.dir.name), FakeDoor()
        self.sockets, self.tried = [], []

        async def connect(url, token):
            self.tried.append((url, token))
            if url in self.refuse: raise OSError("no route")
            ws = FakeSocket(dict(READY))
            self.sockets.append(ws)
            return ws
        self.refuse = set()
        self.p = P.Printers(self.hub, request=self.door, connect=connect)
        self.slept = []
        real = asyncio.sleep

        async def no_sleep(s): self.slept.append(s); await real(0)
        self._sleep, P.asyncio.sleep = real, no_sleep

    def tearDown(self):
        P.asyncio.sleep = self._sleep
        for t in self.p.links.values(): t.cancel()
        P.STATE = self.saved
        self.dir.cleanup()

    async def added(self):
        await self.p.look()
        self.assertEqual(await self.p.add("obi1"), "allowed")
        await turn()


class FindingAndLettingIn(Base):
    async def test_only_what_says_it_is_a_printer_is_found(self):
        found = await self.p.look()
        self.assertEqual(found, [{"id": "obi1", "name": "OBI1", "home": HOME, "away": AWAY}])
        self.assertEqual(self.hub.pushed[-1]["printers"]["found"][0]["name"], "OBI1")

    async def test_the_hub_asks_as_a_hub_and_keeps_the_token_to_itself(self):
        await self.added()
        ask = next(c for c in self.door.calls if c[1] == f"{HOME}/door/ask")
        self.assertEqual(ask[2], {"name": "Main Palace hub", "kind": "hub"})
        kept = json.loads(P.STATE.read_text())["printers"]["obi1"]
        self.assertEqual((kept["token"], kept["phone"], kept["home"]), ("TOK", "ph1", HOME))
        self.assertEqual(stat.S_IMODE(os.stat(P.STATE).st_mode), 0o600)
        self.assertNotIn("TOK", json.dumps(self.p.status()), "the panel never sees a printer's token")
        self.assertEqual(self.hub.log.rows[0][:3], ("printer", "obi1", "added"))
        self.assertEqual(self.p.status()["found"], [], "a printer that is in is not still found")

    async def test_a_no_at_the_printer_is_shown_and_nothing_kept(self):
        self.door.answer = "refused"
        await self.p.look()
        self.assertEqual(await self.p.add("obi1"), "refused")
        self.assertEqual(self.p.status()["asking"], {"obi1": "refused"})
        self.assertFalse(P.STATE.exists())

    async def test_a_printer_not_on_the_wifi_cannot_be_added(self):
        with self.assertRaises(KeyError): await self.p.add("r2d2")


class Following(Base):
    async def test_home_first_and_the_intent_reaches_the_panel(self):
        await self.added()
        self.assertEqual(self.tried[0], (HOME, "TOK"))
        v = self.p.view("obi1")
        self.assertEqual((v["connected"], v["via"], v["state"], v["headline"]), (True, "home", "ready", "Ready"))
        self.assertEqual(v["temps"], {"nozzle": 28.9, "bed": 26.2})

    async def test_away_when_home_does_not_answer(self):
        self.refuse = {HOME}
        await self.added()
        self.assertEqual([u for u, _ in self.tried[:2]], [HOME, AWAY])
        self.assertEqual(self.p.view("obi1")["via"], "away")

    async def test_a_printer_that_needs_somebody_is_a_line_in_needs_a_look_in_its_own_words(self):
        await self.added()
        ws = self.sockets[-1]
        await ws.notify("notify_intent_update", {"state": "needs_you", "headline": "OBI1 needs you",
                                                 "detail": "White PLA ran out.", "actions": [
                                                     {"id": "resume", "label": "Resume"}, {"id": "print_another", "label": "Print another"}]})
        await turn()
        notes = self.p.notes()
        self.assertEqual((notes[0]["kind"], notes[0]["subject"], notes[0]["text"]), ("printer", "obi1", "OBI1 needs you"))
        self.assertEqual([a["id"] for a in self.p.view("obi1")["actions"]], ["resume"], "only what the hub may do is offered")

    async def test_what_the_printer_tells_its_phones_goes_in_the_house_log(self):
        await self.added()
        await self.sockets[-1].notify("notify_astromech_event", {"kind": "finished", "title": "OBI1: Phone stand is done", "body": "b"})
        await turn()
        row = self.hub.log.rows[-1]
        self.assertEqual(row[:3], ("printer", "obi1", "finished"))
        self.assertEqual(row[3]["title"], "OBI1: Phone stand is done")

    async def test_the_job_carries_a_thumbnail_the_panel_can_load_without_a_token(self):
        await self.added()
        await self.sockets[-1].notify("notify_intent_update", {"state": "printing", "headline": "Printing", "actions": [],
                                                               "job": {"name": "Benchy", "progress": 0.42, "thumbnail": ".thumbs/benchy-300x300.png"}})
        await turn()
        job = self.p.view("obi1")["job"]
        self.assertEqual((job["name"], job["progress"], job["thumbnail"]), ("Benchy", 0.42, "/printers/obi1/thumbnail"))
        status, headers, resp = self.p.fetch("obi1", "thumbnail")
        url = self.door.calls[-1][1]
        self.assertEqual(url, f"{HOME}/server/files/gcodes/.thumbs/benchy-300x300.png?access_token=TOK")
        self.assertEqual(resp.read(), b"PNG")


class Acting(Base):
    async def test_the_short_list_only(self):
        await self.added()
        await self.p.act("obi1", "pause")
        sent = self.sockets[-1].sent[-1]
        self.assertEqual((sent["method"], sent["params"]), ("printer.intent.action", {"action": "pause", "args": {}}))
        for refused in ("print_another", "start_file", "taken_off", "care_done"):
            with self.assertRaises(PermissionError): await self.p.act("obi1", refused)

    async def test_forgetting_takes_the_hub_off_the_printer_too(self):
        await self.added()
        await self.p.forget("obi1")
        delete = [c for c in self.door.calls if c[0] == "DELETE"][-1]
        self.assertEqual((delete[1], delete[3]), (f"{HOME}/door/phones/ph1", {"Authorization": "Bearer TOK"}))
        self.assertEqual(json.loads(P.STATE.read_text())["printers"], {})
        self.assertEqual(self.p.status()["printers"], [])


class LanAddress(unittest.TestCase):
    def test_only_an_address_inside_a_house(self):
        self.assertEqual(P.lan_address(HOME), "192.168.86.73")
        self.assertEqual(P.lan_address("https://10-0-0-5.x.home.elyir.app/door/me"), "10.0.0.5")
        self.assertIsNone(P.lan_address(AWAY))
        self.assertIsNone(P.lan_address("https://8-8-8-8.x.home.elyir.app"), "a public address is nobody's home")
        self.assertIsNone(P.lan_address("https://999-1-1-1.x.home.elyir.app"))


if __name__ == "__main__":
    unittest.main()
