# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Printers, against a fake printer door and a fake websocket: found, let in, followed, acted on, forgotten."""
import asyncio, json, os, stat, tempfile, unittest
from pathlib import Path

from hub import printers as P
from hub.settings import Settings

from tests.apptest import ApiTest

HOME = "https://192-168-86-73.obi1.home.elyir.app"
AWAY = "https://obi1.elyir.app"


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, kind, subject, old=None, new=None, source="device", detail=None, who=None):
        self.rows.append((kind, subject, new, detail))


class FakeRoom:
    def __init__(self, id, name): self.id, self.name = id, name


class FakeHome:
    def __init__(self):
        self.rooms = {r.id: r for r in (FakeRoom("workshop", "Workshop"), FakeRoom("garage", "Garage"),
                                        FakeRoom("unassigned", "New devices"))}


class FakeHub:
    def __init__(self, tmp):
        self.settings = Settings(Path(tmp) / "settings.json")
        self.settings.set(home_name="Maple Court")
        self.log = FakeLog()
        self.home = FakeHome()
        self.pushed = []
    def _broadcast(self, msg): self.pushed.append(json.loads(msg))


class FakeDoor:
    """The printer door's public routes, as a request function: (method, url, body, headers, timeout, stream)."""
    def __init__(self):
        self.calls, self.polls, self.answer = [], 0, "allowed"

    def __call__(self, method, url, body=None, headers=None, timeout=10.0, stream=False):
        self.calls.append((method, url, body, headers))
        if url == P.NEARBY:
            return 200, {}, json.dumps({"names": ["maple-court", "obi1"]}).encode()
        if url == "https://maple-court.elyir.app/door/me":
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
        self.assertEqual(ask[2], {"name": "Maple Court hub", "kind": "hub"})
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


PRINTING = {"state": "printing", "headline": "Phone stand", "detail": "Done at about 4:20 pm",
            "actions": [{"id": "pause", "label": "Pause"}, {"id": "cancel", "label": "Stop this print"}],
            "job": {"name": "Phone stand", "progress": 0.42, "layer": 118, "layers": 280, "remaining_s": 5580,
                    "eta_clock": "4:20 pm", "elapsed_s": 7440, "colors": ["#f4f1ea"], "material": "PLA"},
            "printer": {"nozzle": {"temperature": 220}, "bed": {"temperature": 60}, "chamber": {"temperature": 38}}}


class WhereItLives(Base):
    """A room is the household's choice, from the printer's pane, and never a question when it is added
    (design/printers/RoomChoiceB). The view carries it so the room can show the printer."""

    async def test_a_new_printer_has_no_room(self):
        await self.added()
        self.assertIsNone(self.p.view("obi1")["room"])

    async def test_a_room_is_kept_and_named_in_the_view(self):
        await self.added()
        v = self.p.set_room("obi1", "workshop")
        self.assertEqual(v["room"], {"id": "workshop", "name": "Workshop"})
        self.assertEqual(json.loads(P.STATE.read_text())["printers"]["obi1"]["room"], "workshop")
        self.assertEqual(self.hub.pushed[-1]["printers"]["printers"][0]["room"]["name"], "Workshop")

    async def test_and_it_can_go_back_to_none(self):
        await self.added()
        self.p.set_room("obi1", "workshop")
        self.assertIsNone(self.p.set_room("obi1", None)["room"])

    async def test_only_a_room_the_house_has(self):
        await self.added()
        for wrong in ("attic", "unassigned"):
            with self.assertRaises(ValueError): self.p.set_room("obi1", wrong)
        with self.assertRaises(KeyError): self.p.set_room("r2d2", "workshop")

    async def test_a_room_taken_away_is_no_room(self):
        await self.added()
        self.p.set_room("obi1", "garage")
        del self.hub.home.rooms["garage"]
        self.assertIsNone(self.p.view("obi1")["room"])


class TheWordsTheWallUses(Base):
    async def test_a_print_says_what_it_is_made_of_and_how_long_it_has_run(self):
        await self.added()
        await self.sockets[-1].notify("notify_intent_update", PRINTING)
        await turn()
        v = self.p.view("obi1")
        self.assertEqual((v["word"], v["job"]["filament"], v["job"]["elapsed_s"]), ("printing", "White PLA", 7440))
        self.assertEqual(v["temps"], {"nozzle": 220, "bed": 60, "chamber": 38})
        self.assertIsNotNone(v["since"])

    def test_colors_said_the_way_a_household_says_them(self):
        for hex_, name in (("#f4f1ea", "White"), ("#111111", "Black"), ("#808080", "Gray"), ("#d43a2f", "Red"),
                           ("#2f6fd4", "Blue"), ("#3fae4f", "Green"), ("#7a4a1c", "Brown"), ("nope", None)):
            self.assertEqual(P.color_name(hex_), name, hex_)
        self.assertEqual(P.filament({"colors": [], "material": "PETG"}), "PETG")
        self.assertIsNone(P.filament({}))

    async def test_a_stopped_printer_is_a_job_on_needs_a_look_with_its_name_on_the_button(self):
        await self.added()
        self.p.set_room("obi1", "garage")
        await self.sockets[-1].notify("notify_intent_update", {"state": "problem", "headline": "OBI1 stopped",
                                                               "detail": "Check the cable to the head.", "actions": []})
        await turn()
        n = self.p.notes()[0]
        self.assertEqual((n["text"], n["more"], n["where"]), ("OBI1 stopped", "Check the cable to the head.", "Garage · a 3D printer"))
        self.assertEqual(n["acts"], [{"do": "Open OBI1", "act": "printer", "to": "obi1"}])
        self.assertEqual(self.p.view("obi1")["word"], "stopped")

    async def test_found_printers_say_they_are_printers(self):
        await self.p.look()
        self.assertEqual(self.p.status()["found"][0]["kind"], "3D printer")


class TheRowThatAsked(Base):
    """Add says, in the row that asked, where to tap and how long is left, and then each of the four ways
    the wait ends (design/printers/AddAsking, AddAnswers)."""

    async def test_while_waiting_it_names_the_printer_and_when_the_ask_runs_out(self):
        await self.p.look()
        self.p.now = lambda: 1000.0
        self.door.polls = -10_000                       # the printer keeps saying "waiting"
        task = self.p.ask("obi1")
        await turn()
        ask = self.p.status()["asks"][0]
        self.assertEqual((ask["state"], ask["title"], ask["until"]), ("waiting", "Tap Allow on OBI1’s screen", 1120.0))
        self.assertIn("phone that already has OBI1", ask["detail"])
        self.p.stop("obi1")
        await turn()
        self.assertTrue(task.cancelled() or task.done())
        self.assertEqual(self.p.status()["asking"], {}, "stopped asking is no answer at all")

    async def test_allowed_stays_said_until_add_is_opened_again(self):
        await self.added()
        await self.sockets[-1].notify("notify_intent_update", PRINTING)
        await turn()
        ask = self.p.status()["asks"][0]
        self.assertEqual((ask["state"], ask["title"], ask["detail"]), ("allowed", "OBI1 is in the house", "Printing Phone stand, 42%."))
        self.p.clear_answers()
        self.assertEqual(self.p.status()["asks"], [])

    async def test_each_way_an_ask_ends_has_its_own_sentence(self):
        await self.p.look()
        for state, title in (("refused", "OBI1 said no"), ("expired", "Nobody answered on OBI1"), ("failed", "Couldn’t reach OBI1")):
            self.p.asking["obi1"] = state
            words = self.p.ask_words("obi1")
            self.assertEqual(words["title"], title)
            self.assertTrue(words["detail"])
            self.assertIsNone(words["until"])

    async def test_a_waiting_ask_survives_the_door_opening_again(self):
        await self.p.look()
        self.p.asking["obi1"] = "waiting"
        self.p.clear_answers()
        self.assertEqual(self.p.asking, {"obi1": "waiting"})

    async def test_only_a_printer_on_the_wifi_can_be_asked(self):
        with self.assertRaises(KeyError): self.p.ask("r2d2")


class TheRoutes(ApiTest):
    """The room and the Stop asking, as the panel reaches them."""

    def setUp(self):
        super().setUp()
        self.hub.printers.known["obi1"] = {"name": "OBI1", "home": HOME, "away": AWAY, "token": "TOK", "phone": None, "added": 0}

    def test_a_room_from_the_house_and_back_to_none(self):
        r = self.client.post("/printers/obi1/room", json={"room": "kitchen"})
        self.assertEqual((r.status_code, r.json()["room"]), (200, {"id": "kitchen", "name": "Kitchen"}))
        self.assertEqual(self.client.get("/printers").json()["printers"][0]["room"]["id"], "kitchen")
        self.assertIsNone(self.client.post("/printers/obi1/room", json={"room": None}).json()["room"])

    def test_a_room_the_house_does_not_have_is_refused(self):
        self.assertEqual(self.client.post("/printers/obi1/room", json={"room": "attic"}).status_code, 400)
        self.assertEqual(self.client.post("/printers/r2d2/room", json={"room": "kitchen"}).status_code, 404)

    def test_asking_a_printer_that_is_not_on_the_wifi_is_a_404_and_stopping_is_harmless(self):
        self.assertEqual(self.client.post("/printers/r2d2/add").status_code, 404)
        self.assertEqual(self.client.delete("/printers/r2d2/add").status_code, 200)


class LanAddress(unittest.TestCase):
    def test_only_an_address_inside_a_house(self):
        self.assertEqual(P.lan_address(HOME), "192.168.86.73")
        self.assertEqual(P.lan_address("https://10-0-0-5.x.home.elyir.app/door/me"), "10.0.0.5")
        self.assertIsNone(P.lan_address(AWAY))
        self.assertIsNone(P.lan_address("https://8-8-8-8.x.home.elyir.app"), "a public address is nobody's home")
        self.assertIsNone(P.lan_address("https://999-1-1-1.x.home.elyir.app"))


if __name__ == "__main__":
    unittest.main()
