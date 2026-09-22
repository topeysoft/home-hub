# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A light strip arriving, without a light strip.

The machine is what the panel draws (design/strip/Spine.dc.html), so what these hold is the sequence
somebody standing in the room would see: it knocks, nothing of the house's moves until they say yes,
it joins the Wi-Fi, it says what color it is showing, it fills up and is stopped, it gets a room.
And the two questions only a strip has -- which color comes out first, and how far it goes -- both of
which exist because nothing can be read back off a strip.
"""
import asyncio, json, sqlite3, tempfile, time, unittest
from pathlib import Path

from hub.settings import Settings
from hub.strip import (ASSUME, DEV_CODE, ORDERS, TEST_VID, Radio, StripError, Strips,
                       lit_index, narrow, probe, resolve)


class FakeRadio:
    """What Bluetooth would have said, in the shape a commissionable Matter device says it.

    Note what is NOT here: no Wi-Fi, no credentials of any kind. Commissioning carries those itself,
    which is the whole reason the firmware left the Arduino framework."""
    def __init__(self):
        self.advertising = []
        self.ours = []            # strips knocking at OUR door, as strip_door.find() returns them
        self.commissioned = []
        self.adopted = []         # (addr, rhythm, ssid, password, where-we-are)
        self.told_wifi = []
        self.commission_fails = None
        self.adopt_fails = None
        self.scan_boom = None
        # The press, as the strip would report it. `hold` keeps the session waiting the way a real
        # one waits, so a test can look at the wall while nothing of the house's has moved.
        self.hold = False
        self.pressing = None      # the callback, kept so a test can press whenever it likes
        self.asked_rhythm = 0     # how many times the strip was asked to drop a rung
        self.not_pressed = False  # the two minutes ran out with nobody touching it

    async def scan_ours(self, seconds=8.0):
        return [{"addr": s["address"], "rssi": s["rssi"], "name": s.get("name"),
                 "door": "ours", "ours": True} for s in self.ours]

    async def adopt_ours(self, addr, ssid, password, hub=None, rhythm="",
                         on_pressed=None, out_of_reach=None):
        if self.adopt_fails:
            raise StripError(self.adopt_fails if isinstance(self.adopt_fails, str)
                             else "Those were not the flashes it is showing.")
        if not rhythm:
            # Waiting for the press. A real session holds a BLE link open here with the credentials
            # still on the hub; this holds the coroutine, which is the same fact for the machine.
            self.pressing = on_pressed
            while self.hold:
                if out_of_reach is not None and out_of_reach.is_set():
                    self.asked_rhythm += 1
                    return "rhythm"
                if self.not_pressed:
                    raise StripError("Nobody pressed the button on it. The button is on the "
                                     "controller, at the end it plugs in at \u2014 say it is yours "
                                     "again to start over.")
                await asyncio.sleep(0)
            if on_pressed: on_pressed()
        self.adopted.append((addr, rhythm, ssid, password, hub or {}))
        return "done"

    async def set_wifi(self, ssid, password):
        self.told_wifi.append((ssid, password))

    async def scan(self, seconds=4.0):
        if self.scan_boom: raise self.scan_boom
        return list(self.advertising)

    async def commission(self, code):
        if self.commission_fails: raise StripError(self.commission_fails)
        if not code: raise StripError("That light strip needs its setup code.")
        self.commissioned.append(code); return {"node_id": 7}

    async def forget(self, id): return None


class FakeHA:
    """The broker. `answers` maps a leaf we publish to the leaf+payload the strip replies with."""
    def __init__(self):
        self.cb = None
        self.published = []
        self.answers = {}
        self.devices = []      # what the house's device registry holds
        self.moved = []        # (device_id, area_id) for every move we asked for

    async def subscribe(self, type_, cb, **kw): self.cb = cb; return 1

    async def send(self, type_, **kw):
        """Home Assistant's own registry, as much of it as a strip ever touches."""
        if type_ == "config/device_registry/list": return getattr(self, "devices", [])
        if type_ == "config/device_registry/update":
            self.moved.append((kw.get("device_id"), kw.get("area_id")))
            return {"ok": True}
        return None

    async def call(self, domain, service, target, **kw):
        topic, payload = kw.get("topic"), kw.get("payload")
        self.published.append((topic, payload, bool(kw.get("retain"))))
        leaf = "/".join(topic.split("/")[2:])
        if leaf in self.answers and self.cb:
            back_leaf, back_payload = self.answers[leaf]
            id_ = topic.split("/")[1]
            self.cb({"topic": f"strip/{id_}/{back_leaf}", "payload": back_payload})


class FakeBridges:
    """The one thing a strip asks the puck's half of the hub for: where the broker is and how to get
    into it. Real `Bridges.broker()` reads exactly these out of the environment."""
    def broker(self):
        return {"host": "192.168.1.9", "name": "hub", "port": 1883, "user": "hub", "pass": "pw"}


class FakeHub:
    def __init__(self, tmp, wifi=True):
        self.settings = Settings(Path(tmp) / "settings.json")
        self.settings.set(wifi={"ssid": "House", "pass": "hunter2 with space"} if wifi else None)
        self.env = {"MQTT_USER": "hub", "MQTT_PASSWORD": "pw"}
        self.hostname = "hub"
        self.bridge = FakeBridges()
        self.ha = FakeHA()
        self.home = None
        self.pushed = []
        self.steps = []
        self.placed = []

    def _broadcast(self, msg):
        st = json.loads(msg)["strip"]
        self.pushed.append(st["state"])
        if st.get("step"): self.steps.append(st["step"])
    async def strip_placed(self, id_, room): self.placed.append((id_, room))


def run(coro): return asyncio.run(coro)


async def turn(times: int = 60):
    """Let every task that is ready have a go, without letting the clock move."""
    for _ in range(times): await asyncio.sleep(0)


class TheOrderTheColorsComeIn(unittest.TestCase):
    """Nothing can be read back off a strip -- the data line is write-only on every one of these
    parts -- so the ordering cannot be detected and has to be shown. These pin the arithmetic that
    turns what somebody can see into which of the six it is."""

    def test_the_probe_is_red_on_the_strip_we_guessed(self):
        """Not (255,0,0). We send what red WOULD be if the guess is right, so a household with the
        common strip sees red and taps once."""
        self.assertEqual(probe("grb"), (0, 255, 0))
        self.assertEqual(probe("rgb"), (255, 0, 0))
        self.assertEqual(probe("bgr"), (0, 0, 255))

    def test_the_first_answer_always_leaves_a_pair(self):
        """Which is why "one tap" is a prior and not a proof, and why the pane has a way back."""
        for seen in ("r", "g", "b"):
            self.assertEqual(len(narrow(seen, lit_index())), 2, seen)

    def test_two_answers_settle_every_one_of_the_six(self):
        """The real claim on the board. For each ordering, work out what a household would actually
        see at each question and check we land back on the ordering we started from."""
        for order in ORDERS:
            first = order[lit_index()]          # the channel our probe lights on THIS strip
            second = order[0]                   # the second question makes the first byte loud
            self.assertEqual(resolve(first, second), order, order)

    def test_a_household_that_says_red_gets_the_common_strip(self):
        self.assertEqual(resolve("r"), ASSUME)
        self.assertEqual(ASSUME, "grb")

    def test_and_the_other_two_answers_wait_for_the_second_question(self):
        self.assertIsNone(resolve("g"))
        self.assertIsNone(resolve("b"))


class Knocking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.s = Strips(self.hub, radio=self.radio)

    def tearDown(self): self.tmp.cleanup()

    def arrive(self, addr="AA:BB:CC:DD:EE:FF", discriminator=3840, rssi=-52):
        self.radio.advertising = [{"addr": addr, "discriminator": discriminator, "rssi": rssi,
                                   "vendor": 0xFFF1, "product": 0x8000, "ours": True}]

    def test_nothing_to_say_when_nothing_is_advertising(self):
        run(self.s.look())
        self.assertEqual(self.s.status()["state"], "none")

    def test_a_strip_that_has_never_been_set_up_knocks(self):
        self.arrive()
        run(self.s.look())
        self.assertEqual(self.s.status()["state"], "knocking")
        self.assertEqual(self.radio.commissioned, [])    # nothing of the house's has gone anywhere

    def test_the_wall_is_never_shown_an_address(self):
        """The identity check is the object: it is two meters of lit strip and it is the only one
        lit. A household shown a MAC has been handed the inside of the product."""
        self.arrive(addr="AA:BB:CC:DD:EE:FF")
        run(self.s.look())
        said = json.dumps(self.s.status())
        self.assertNotIn("AA:BB", said)
        self.assertNotIn("3840", said)

    def test_a_matter_advertisement_carries_no_id_of_ours(self):
        """Which is the whole reason setup now stops at commissioned: everything after it is
        addressed by the strip's chip, and only the broker can say what that is."""
        self.arrive()
        run(self.s.look())
        self.assertIsNone(self.s.job["id"])
        self.assertEqual(self.s.job["discriminator"], 3840)

    def test_not_mine_needs_no_code_and_sends_nothing(self):
        self.arrive()
        run(self.s.look())
        run(self.s.dismiss())
        self.assertEqual(self.s.status()["state"], "none")
        self.assertEqual(self.hub.ha.published, [])

    def test_and_a_dismissed_strip_does_not_knock_again(self):
        """Otherwise refusing is a loop: it is still advertising, so the next scan finds it and asks
        again, faster than anybody can say no."""
        self.arrive()
        run(self.s.look()); run(self.s.dismiss()); run(self.s.look())
        self.assertEqual(self.s.status()["state"], "none")

    def test_the_wifi_goes_to_the_controller_and_not_to_the_strip(self):
        """This file claimed for a while that the hub never touched a household's password again. It
        was too strong and had to be corrected by reading Home Assistant's own API: the Matter
        controller cannot commission onto a network it has not been told about, so the hub does hand
        it over -- once, to matter-server, which delivers it inside the commissioning session. That is
        a different thing from the unauthenticated BLE link this replaced, and worth being exact
        about rather than keeping the tidier sentence."""
        self.arrive()
        run(self.s.look())
        run(self.s.adopt("3497-011-2332"))
        for _ in range(40): run(asyncio.sleep(0))
        self.assertEqual(self.radio.told_wifi, [("House", "hunter2 with space")])

    def test_and_a_hub_that_has_never_been_told_asks_once(self):
        """Exactly the way bridge.py asks it, and no strip after this one asks again."""
        self.hub.settings.set(wifi=None)
        self.arrive()
        run(self.s.look())
        run(self.s.adopt("3497-011-2332"))
        s = self.s.status()
        self.assertEqual((s["state"], s["needs"]), ("working", "wifi"))
        self.assertEqual(self.radio.commissioned, [])


class TheWholeWay(unittest.TestCase):
    """Knock to commissioned, which is as far as setup honestly goes now.

    It used to run on through the color question, the fill and a room. All of those are addressed by
    the strip's chip over the broker, and a Matter advertisement does not carry one -- so the old test
    was passing because a fake handed it an id that nothing real would have. What is left is true."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.radio.advertising = [{"addr": "AA:BB:CC:DD:EE:FF", "discriminator": 3840, "rssi": -50,
                                   "vendor": 0xFFF1, "product": 0x8000, "ours": True}]
        self.s = Strips(self.hub, radio=self.radio)
        run(self.s.listen())

    def tearDown(self): self.tmp.cleanup()

    async def adopt(self, code="3497-011-2332"):
        await self.s.look()
        await self.s.adopt(code)
        for _ in range(50): await asyncio.sleep(0)

    def test_it_knocks_then_is_commissioned(self):
        run(self.adopt())
        self.assertEqual(self.s.status()["state"], "ready")
        self.assertEqual(self.radio.commissioned, ["3497-011-2332"])

    def test_and_the_beats_it_can_still_honestly_claim(self):
        """design/strip/Spine.dc.html is six beats. Three of them are reachable today and the board
        has not changed -- so this says what is true rather than what is drawn, and the gap is
        docs/strip.md item 2a rather than a board nobody updated."""
        run(self.adopt())
        beats = [b for i, b in enumerate(self.hub.pushed) if i == 0 or b != self.hub.pushed[i - 1]]
        self.assertEqual(beats, ["knocking", "working", "ready"])
        self.assertEqual(self.hub.steps, ["letting"])

    def test_a_development_board_needs_no_code_typed_at_it(self):
        """Its passcode is CHIP's own 20202021, compiled in and published in their source, so asking
        somebody to copy it off a terminal would be ceremony rather than security."""
        run(self.adopt(code=""))
        self.assertEqual(self.s.status()["state"], "ready")
        self.assertEqual(self.radio.commissioned, ["34970112332"])

    def test_but_a_real_unit_still_has_to_be_told(self):
        """The shortcut is keyed on the TEST vendor id, so it stops applying by itself the day a unit
        ships with a passcode of its own. Nothing has to be remembered or switched off."""
        self.radio.advertising = [{"addr": "AA:BB:CC:DD:EE:FF", "discriminator": 3840, "rssi": -50,
                                   "vendor": 0x1234, "product": 0x8000, "ours": False}]
        run(self.adopt(code=""))
        s = self.s.status()
        self.assertEqual(s["state"], "failed")
        self.assertIn("setup code", s["text"])
        self.assertEqual(self.radio.commissioned, [])

    def test_and_a_finished_job_stops_reporting_once_it_is_read(self):
        run(self.adopt())
        run(self.s.done())
        self.assertEqual(self.s.status()["state"], "none")


class TheRadioIsWiredUp(unittest.TestCase):
    """The commissioning call goes out over Home Assistant, so the radio needs the hub. It was built
    without one, every commissioning failed, and the wall said "This hub cannot set Matter devices up
    yet" -- a sentence that was confident, wrong, and would have been believed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def test_a_radio_the_hub_made_for_itself_knows_the_hub(self):
        s = Strips(self.hub)
        self.assertIs(s.radio.hub, self.hub)

    def test_and_it_actually_reaches_the_engine(self):
        """Not just that the attribute is set: that the call lands somewhere."""
        sent = []
        class Engine:
            async def send(self, type_, **kw): sent.append((type_, kw)); return {"node_id": 3}
        self.hub.ha = Engine()
        run(Strips(self.hub).radio.commission("3497-011-2332"))
        self.assertEqual(sent, [("matter/commission", {"code": "3497-011-2332"})])

    def test_a_house_with_no_matter_controller_is_told_that_and_not_to_check_a_code(self):
        """The real first failure on hardware: matter-server was not running, HA had no Matter
        integration, and the wall said "check the code and that the strip is still lit" -- which
        points at a strip that was working perfectly and hides the one thing that was wrong."""
        class Engine:
            async def send(self, type_, **kw): raise RuntimeError("matter/commission: unknown_command")
        self.hub.ha = Engine()
        with self.assertRaises(StripError) as e:
            run(Strips(self.hub).radio.commission("3497-011-2332"))
        said = str(e.exception)
        self.assertIn("cannot let that kind of light in yet", said)
        self.assertNotIn("Check it", said)
        # AND IT NAMES NOTHING THE HOUSEHOLD DID NOT BUY. This sentence said "matter-server" and
        # "Home Assistant" for weeks, on a wall, to somebody who can do nothing with either.
        for word in ("matter-server", "matter\u2011server", "Home Assistant", "integration"):
            self.assertNotIn(word.lower(), said.lower())

    def test_and_the_same_answer_comes_out_of_the_wifi_call(self):
        """Both calls reach the same engine and fail the same way when nothing is listening. The
        answer was got right in one and wrong in the other a commit later, and a household sent to
        check their Wi-Fi by one and to add an integration by the other is being sent to opposite
        ends of the house for one cause."""
        class Engine:
            async def send(self, type_, **kw): raise RuntimeError("unknown_command")
        self.hub.ha = Engine()
        with self.assertRaises(StripError) as e:
            run(Strips(self.hub).radio.set_wifi("House", "hunter2"))
        self.assertIn("cannot let that kind of light in yet", str(e.exception))

    def test_but_a_refused_code_still_says_so(self):
        class Engine:
            async def send(self, type_, **kw): raise RuntimeError("commissioning failed: timeout")
        self.hub.ha = Engine()
        with self.assertRaises(StripError) as e:
            run(Strips(self.hub).radio.commission("3497-011-2332"))
        self.assertIn("did not take the code", str(e.exception))

    def test_and_says_something_true_when_there_is_no_engine(self):
        self.hub.ha = None
        with self.assertRaises(StripError) as e:
            run(Strips(self.hub).radio.commission("3497-011-2332"))
        self.assertNotIn("cannot set Matter devices up", str(e.exception))


class Afterwards(unittest.TestCase):
    """Both setup answers go stale -- a strip gets cut down, extended, or replaced by another make --
    and none of that should mean setting it up again from the beginning. design/strip/Later.dc.html."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.s = Strips(self.hub, radio=FakeRadio())
        run(self.s.listen())
        # a strip that is already in, the way the broker would have told us about it
        self.s.strips["c8ebba"] = {"online": True, "count": 186, "order": "grb"}
        self.hub.ha.answers = {"fill/stop": ("count", "240")}

    def tearDown(self): self.tmp.cleanup()

    def said(self, leaf):
        return [p for t, p, _ in self.hub.ha.published if t.endswith("/" + leaf)]

    def test_the_house_can_list_what_it_has(self):
        self.hub.ha.devices = [{"id": "dev1", "identifiers": [["mqtt", "strip_c8ebba"]]}]
        self.assertEqual(run(self.s.each()),
                         [{"id": "c8ebba", "online": True, "count": 186, "order": "grb",
                           "device": "dev1"}])

    def test_a_strip_the_house_has_not_made_a_device_for_yet_is_still_listed(self):
        """Discovery is a moment behind everything else, and a strip with no hardware id yet is a
        strip the pane simply cannot offer its two questions about -- not one it should hide."""
        self.hub.ha.devices = []
        self.assertEqual(run(self.s.each())[0]["device"], None)
        # And the miss is not remembered: it would make the pane permanently sure of a wrong thing.
        self.hub.ha.devices = [{"id": "dev1", "identifiers": [["mqtt", "strip_c8ebba"]]}]
        self.assertEqual(run(self.s.each())[0]["device"], "dev1")

    def test_the_colors_can_be_asked_again(self):
        run(self.s.revisit("c8ebba", "colors"))
        st = self.s.status()
        self.assertEqual((st["state"], st["asking"], st["revisit"]), ("order", "red", "colors"))
        self.assertEqual(self.said("show/set"), ["raw 0 255 0"])

    def test_and_it_stops_there_rather_than_walking_setup_again(self):
        """Somebody who came back to fix the colors did not ask to measure the strip again."""
        run(self.s.revisit("c8ebba", "colors"))
        run(self.s.saw("red"))
        self.assertEqual(self.s.status()["state"], "ready")
        self.assertEqual(self.said("order/set"), ["grb"])

    def test_the_length_can_be_asked_again_and_keeps_its_room(self):
        run(self.s.revisit("c8ebba", "length"))
        self.assertEqual(self.s.status()["state"], "length")
        run(self.s.ends())
        st = self.s.status()
        self.assertEqual((st["state"], st["count"]), ("ready", 240))
        self.assertEqual(self.said("count/set"), ["240"])

    def test_and_neither_the_color_order_nor_the_length_is_left_on_the_broker(self):
        """The other two of the three. See TheLastTwoBeats for why, and item 31."""
        run(self.s.revisit("c8ebba", "colors"))
        run(self.s.saw("red"))
        run(self.s.done())
        run(self.s.revisit("c8ebba", "length"))
        run(self.s.ends())
        said = [t.split("/", 2)[2] for t, _, _ in self.hub.ha.published]
        self.assertIn("order/set", said)
        self.assertIn("count/set", said)
        self.assertEqual([t for t, _, retain in self.hub.ha.published if retain], [])

    def test_a_strip_the_hub_has_never_heard_of_is_refused(self):
        with self.assertRaises(StripError):
            run(self.s.revisit("nope", "colors"))

    def test_and_so_is_one_that_is_not_answering(self):
        """Every one of these questions works by lighting the thing up, so an offline strip has
        nothing to show and the sheet would open on a question that cannot move."""
        self.s.strips["c8ebba"]["online"] = False
        with self.assertRaises(StripError):
            run(self.s.revisit("c8ebba", "colors"))

    def test_and_never_while_something_else_is_being_set_up(self):
        self.s.job = {"state": "knocking", "id": "other", "first": None}
        with self.assertRaises(StripError):
            run(self.s.revisit("c8ebba", "colors"))

    def test_only_the_two_questions_that_exist(self):
        with self.assertRaises(StripError):
            run(self.s.revisit("c8ebba", "brightness"))


class WhenItGoesWrong(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.radio.advertising = [{"addr": "AA:BB:CC:DD:EE:FF", "discriminator": 3840, "rssi": -50,
                                   "vendor": 0xFFF1, "product": 0x8000, "ours": True}]
        self.s = Strips(self.hub, radio=self.radio)
        run(self.s.listen())

    def tearDown(self): self.tmp.cleanup()

    async def adopt(self, settle: float = 0.0):
        await self.s.look(); await self.s.adopt("3497-011-2332")
        for _ in range(50): await asyncio.sleep(0)
        if settle: await asyncio.sleep(settle)

    def test_a_library_s_own_words_never_reach_the_wall(self):
        """bridge.py learned this the expensive way: a bridge once failed with "database is locked"
        on the wall, which tells nobody anything and was not even true about their bridge."""
        async def boom(code): raise sqlite3.OperationalError("database is locked")
        self.radio.commission = boom
        run(self.adopt())
        s = self.s.status()
        self.assertEqual(s["state"], "failed")
        self.assertNotIn("database", s["text"])

    def test_but_a_sentence_written_for_the_wall_comes_through_as_itself(self):
        self.radio.commission_fails = "This hub has no Bluetooth to look for a light strip with."
        run(self.adopt())
        self.assertIn("no Bluetooth", self.s.status()["text"])


if __name__ == "__main__":
    unittest.main()


class OurOwnDoor(unittest.TestCase):
    """A strip that offers our door is asked one thing and it is not a code.

    design/strip/Ours.dc.html and Press.dc.html: the identity check is two meters of light, and the
    proof of possession is a press on the button of the thing somebody has just unpacked. Nothing is
    printed on a strip and nothing is derived from its chip, so there is nothing to read out and
    nothing to leak. Matter's door is unchanged and still wants a code."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.strips = Strips(self.hub, self.radio)
        self.hub.settings.set(wifi={"ssid": "House", "pass": "secret"})

    def tearDown(self): self.tmp.cleanup()

    def knock(self):
        self.radio.ours = [{"address": "AA:BB", "rssi": -40, "name": "PROV_52e20"}]
        run(self.strips.look())

    # THE PRESS BEAT HOLDS, and these run in ONE event loop for that reason. A session waiting to be
    # pressed is a coroutine parked with the credentials still on the hub; asyncio.run() per step
    # tears that down, so a test written the way the older ones are would be testing a shape the
    # machine never has in a house.

    async def waiting(self):
        """Knocked, said yes, and now the wall is asking for a press."""
        self.radio.hold = True
        self.radio.ours = [{"address": "AA:BB", "rssi": -40, "name": "PROV_52e20"}]
        await self.strips.look()
        await self.strips.adopt()
        await turn()
        return self.strips.status()

    async def out_of_reach(self):
        """...and nobody can get at the button, so it drops to the flashes."""
        await self.waiting()
        await self.strips.reach()
        await turn()
        self.radio.hold = False

    def test_a_strip_at_our_door_is_asked_for_a_press_and_not_a_code(self):
        async def go():
            st = await self.waiting()
            self.assertEqual(st["state"], "press")
            self.assertEqual(self.radio.adopted, [])   # nothing of the house's has moved yet
            self.assertNotIn("groups", st)             # and nothing to count
        run(go())

    def test_the_press_is_what_moves_the_wall_on_and_it_comes_from_the_strip(self):
        """The beat ends because the THING was touched, never because a timer here ran out."""
        async def go():
            self.assertEqual((await self.waiting())["state"], "press")
            self.radio.hold = False                    # somebody presses it
            await turn()
            self.assertEqual(self.strips.status()["step"], "letting")
            self.assertEqual(len(self.radio.adopted), 1)
        run(go())

    def test_a_press_hands_over_the_wifi_and_where_we_are_with_no_secret_at_all(self):
        async def go():
            await self.waiting()
            self.radio.hold = False
            await turn()
            self.assertEqual(len(self.radio.adopted), 1)
            addr, rhythm, ssid, password, where = self.radio.adopted[0]
            # No secret of any kind went over that link: the press is the whole proof.
            self.assertEqual((addr, rhythm, ssid, password), ("AA:BB", "", "House", "secret"))
            # THE BROKER, WITH THE WAY IN. Not just where it is: a strip handed a host and no
            # credentials joins the house, reaches the broker and is refused, and the wall then says
            # it never found the hub. It is the same thing a puck is told, from the same place.
            self.assertEqual(where["mhost"], "hub")
            self.assertEqual((where["muser"], where["mpass"]), ("hub", "pw"))
            self.assertIn("base", where)
            # And our door never goes near Matter's commissioner.
            self.assertEqual(self.radio.commissioned, [])
            self.assertEqual(self.radio.told_wifi, [])
        run(go())

    def test_nobody_pressing_it_is_never_reported_as_a_radio_failure(self):
        async def go():
            await self.waiting()
            self.radio.not_pressed = True      # the two minutes run out
            await turn()
            said = self.strips.status()["text"]
            self.assertIn("Nobody pressed", said)
            self.assertNotIn("nearer", said)
        run(go())

    def test_the_strip_you_are_standing_next_to_is_the_one_the_hub_talks_to(self):
        """Two strips knocking is an ordinary evening -- somebody unpacks a pair. The hub used to
        take whichever advertised first, so a household pressing the button on the one in front of
        them could be waited out by a hub listening to the one upstairs. Matter's side has sorted by
        signal since it was written; ours did not."""
        async def go():
            self.radio.ours = [
                {"address": "FAR", "rssi": -81, "name": "PROV_far"},
                {"address": "NEAR", "rssi": -34, "name": "PROV_near"},
            ]
            await self.strips.look()
            self.assertEqual(self.strips.job["addr"], "NEAR")
            self.assertEqual(self.strips.job["rssi"], -34)
        run(go())

    # ---- and then it has to be found again, on the broker ----

    def test_the_strip_is_found_by_whoever_turns_up_on_the_broker(self):
        """Our door leaves the hub with nothing to address the strip by -- a Matter advertisement
        carries a discriminator, not an id of ours. It used to ask `strip/None/hello`, which nothing
        subscribes to, so every strip taken through our own door failed here however close it was."""
        async def go():
            await self.waiting()
            self.radio.hold = False
            await turn()
            # On the Wi-Fi, not yet on the broker: there is nothing to call it yet.
            self.assertEqual(self.strips.status()["state"], "working")
            self.strips._on_mqtt({"topic": "strip/52e204/status", "payload": "online"})
            await turn()
            self.assertEqual(self.strips.job["id"], "52e204")
            self.assertEqual(self.strips.status()["state"], "order")   # on to the color question
        run(go())

    def test_a_strip_being_set_up_a_SECOND_time_is_still_found(self):
        """The broker keeps what a strip said last, retained, and the brain reads all of it the
        moment it subscribes. So a strip that has ever connected is in the list before the session
        starts -- marked offline -- and "an id that was not there before" can never match it again.
        That is a strip somebody has just factory reset and is standing over."""
        async def go():
            # It has been here before: the broker still holds its last word, and it is offline.
            self.strips._on_mqtt({"topic": "strip/52e204/status", "payload": "offline"})
            self.strips._on_mqtt({"topic": "strip/52e204/order", "payload": "grb"})
            await self.waiting()
            self.radio.hold = False
            await turn()
            self.assertIsNone(self.strips.job["id"])
            self.strips._on_mqtt({"topic": "strip/52e204/status", "payload": "online"})
            await turn()
            self.assertEqual(self.strips.job["id"], "52e204")
            self.assertEqual(self.strips.status()["state"], "order")
        run(go())

    def test_a_strip_the_broker_still_thinks_is_online_is_still_found(self):
        """A strip that goes away does not say so -- the broker says it for it, from the last will,
        and only once the keepalive has run out. A factory reset, a reboot, a knock and a press all
        happen well inside that, so the hub can still believe the old connection is alive while the
        household is standing over the strip that replaced it. It says hello either way."""
        async def go():
            self.strips._on_mqtt({"topic": "strip/52e204/status", "payload": "online"})
            await self.waiting()          # the will has still not fired
            self.radio.hold = False
            await turn()
            self.assertIsNone(self.strips.job["id"])
            # It joins and says hello, on a connection the hub thought it already had.
            self.strips._on_mqtt({"topic": "strip/52e204/status", "payload": "online"})
            await turn()
            self.assertEqual(self.strips.job["id"], "52e204")
            self.assertEqual(self.strips.status()["state"], "order")
        run(go())

    def test_a_strip_the_house_already_had_is_not_mistaken_for_the_new_one(self):
        """A house with strips in it has every one of them online, and they are not this one."""
        async def go():
            self.strips._on_mqtt({"topic": "strip/olderone/status", "payload": "online"})
            await self.waiting()
            self.radio.hold = False
            await turn()
            self.assertIsNone(self.strips.job["id"])
            self.strips._on_mqtt({"topic": "strip/52e204/status", "payload": "online"})
            await turn()
            self.assertEqual(self.strips.job["id"], "52e204")
        run(go())

    # ---- the rung below, reached one way only (design/strip/ReachRhythm.dc.html) ----

    def test_the_flashes_are_reached_only_by_saying_the_button_is_out_of_reach(self):
        async def go():
            await self.out_of_reach()
            st = self.strips.status()
            self.assertEqual(st["state"], "rhythm")
            self.assertEqual((st["groups"], st["most"]), (4, 6))
            self.assertEqual(self.radio.asked_rhythm, 1)   # and the STRIP was told to mint one
            self.assertEqual(self.radio.adopted, [])       # still nothing of the house's
        run(go())

    def test_nothing_drops_a_rung_on_its_own(self):
        async def go():
            self.radio.ours = [{"address": "AA:BB", "rssi": -40, "name": "PROV_52e20"}]
            await self.strips.look()
            with self.assertRaises(StripError): await self.strips.reach()   # still only knocking
            await self.strips.adopt()
            await turn()
            with self.assertRaises(StripError): await self.strips.reach()   # the press already landed
        run(go())

    def test_the_counts_have_to_be_four_groups_of_one_to_six(self):
        async def go():
            await self.out_of_reach()
            for bad in ("", "123", "12345", "1207", "abcd"):
                with self.assertRaises(StripError): await self.strips.counted(bad)
            self.assertEqual(self.strips.status()["state"], "rhythm")
        run(go())

    def test_counting_right_hands_the_flashes_to_the_door_as_the_password(self):
        async def go():
            await self.out_of_reach()
            await self.strips.counted("3164")
            await turn()
            self.assertEqual(len(self.radio.adopted), 1)
            addr, rhythm, ssid, password, where = self.radio.adopted[0]
            self.assertEqual((addr, rhythm, ssid, password), ("AA:BB", "3164", "House", "secret"))
            self.assertEqual(where["mhost"], "hub")
        run(go())

    def test_a_strip_at_matters_door_is_unchanged_and_still_wants_a_code(self):
        self.radio.advertising = [{"addr": "CC:DD", "rssi": -50, "discriminator": 3840,
                                   "vendor": TEST_VID, "ours": True}]
        run(self.strips.look())
        run(self.strips.adopt())
        for _ in range(60): run(asyncio.sleep(0))
        self.assertEqual(self.radio.commissioned, [DEV_CODE])
        self.assertEqual(self.radio.adopted, [])

    def test_a_miscount_says_the_strip_will_show_a_new_one(self):
        async def go():
            await self.out_of_reach()
            self.radio.adopt_fails = True
            await self.strips.counted("1111")
            await turn()
            st = self.strips.status()
            self.assertEqual(st["state"], "failed")
            self.assertIn("flashes", st["text"])
        run(go())


class WhichDoorTheStripIsTakenThrough(unittest.TestCase):
    """Matter's identity is in the advertisement and ours is in the scan response, which only
    arrives if the scanner asked and the answer got back. At range the advertisement lands and the
    scan response sometimes does not, so the same strip can turn up at Matter's door alone -- and
    on 21 September a household was asked for a setup code, and the commissioner failed, for a
    strip with a perfectly good door of ours open the whole time."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.strips = Strips(self.hub, self.radio)

    def tearDown(self): self.tmp.cleanup()

    def test_one_strip_at_both_doors_is_taken_through_ours(self):
        self.radio.ours = [{"address": "AA:BB", "rssi": -40, "name": "PROV_1"}]
        self.radio.advertising = [{"addr": "AA:BB", "rssi": -42, "discriminator": 3840,
                                   "vendor": TEST_VID, "ours": True}]
        run(self.strips.look())
        self.assertEqual(self.strips.job["door"], "ours")

    def test_a_missed_scan_response_is_asked_for_again_before_settling_for_matters(self):
        """The bug itself: our scan came back empty, Matter's did not, and the job went to the
        wrong door without anything saying so."""
        self.radio.advertising = [{"addr": "AA:BB", "rssi": -68, "discriminator": 3840,
                                   "vendor": TEST_VID, "ours": True}]
        tries = []

        async def flaky(seconds=8.0):
            tries.append(seconds)
            if len(tries) == 1: return []
            return [{"addr": "AA:BB", "rssi": -68, "name": "PROV_1", "door": "ours", "ours": True}]
        self.radio.scan_ours = flaky
        run(self.strips.look())
        self.assertEqual(len(tries), 2)            # asked again
        self.assertGreater(tries[1], tries[0])     # and for longer
        self.assertEqual(self.strips.job["door"], "ours")

    def test_a_strip_that_really_is_only_matters_still_goes_through_matters(self):
        self.radio.advertising = [{"addr": "CC:DD", "rssi": -50, "discriminator": 3840,
                                   "vendor": TEST_VID, "ours": True}]
        run(self.strips.look())
        self.assertEqual(self.strips.job["door"], "matter")


class LookingProperly(unittest.TestCase):
    """HOW OFTEN THE HUB GOES LOOKING, AND WHO IS WAITING WHEN IT DOES.

    A household measured about two minutes between plugging a strip in and the wall saying anything,
    and read it as the strip and the hub failing to talk. Twenty of those seconds were this loop
    asleep. The answer is not a tighter loop -- a scan is the radio going quiet for every other
    device in the house, all day, to catch an event that happens when somebody is standing right
    there. The answer is that the knock stopped taking the screen (design/knock/), so the loop can be
    the quiet one, and Add is where the looking happens because that is the one moment it is free."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.s = Strips(self.hub, radio=self.radio)

    def tearDown(self): self.tmp.cleanup()

    def test_nobody_is_looking_until_somebody_says_so(self):
        self.assertFalse(self.s.being_watched())

    def test_add_says_somebody_is_standing_there_and_waiting(self):
        run(self.s.looking())
        self.assertTrue(self.s.being_watched())

    def test_and_it_lapses_by_itself_so_a_forgotten_wall_cannot_leave_it_scanning(self):
        """A hold rather than a switch: a wall that goes to rest, is closed or is unplugged simply
        stops saying it, and there is no way to leave a hub scanning for ever by leaving a page
        open."""
        import hub.strip as strip_mod
        was, strip_mod.LOOK_HOLD = strip_mod.LOOK_HOLD, 0.0
        try:
            run(self.s.looking())
            self.assertFalse(self.s.being_watched())
        finally:
            strip_mod.LOOK_HOLD = was

    def test_the_quiet_speed_is_quiet_but_not_slower_than_a_minute(self):
        """A line in the band may be a minute late and still be a line. Five would be the same lie
        in a quieter voice, so the background loop has a floor as well as a ceiling."""
        import hub.strip as strip_mod
        self.assertGreaterEqual(strip_mod.LOOK_EVERY, 30.0)
        self.assertLessEqual(strip_mod.LOOK_EVERY, 60.0)

    def test_a_knock_says_when_it_started_so_the_band_can_stop_shouting(self):
        """The line folds after an hour, and an age worked out by the brain is stale by the time it
        is drawn -- a poll is half a minute apart and a wall reloads. So it is a moment, not an age."""
        self.radio.ours = [{"address": "AA:BB", "rssi": -40, "name": "PROV_52e20"}]
        run(self.s.look())
        st = self.s.status()
        self.assertEqual(st["state"], "knocking")
        self.assertAlmostEqual(st["since"], time.time(), delta=5)

    def test_and_nothing_says_since_when_there_is_nothing_knocking(self):
        self.assertNotIn("since", self.s.status())


class TheLastTwoBeats(unittest.TestCase):
    """What a household actually reported after the first run that got this far, on 21 September:
    asked for a room, tapped one, told there was no light waiting for a room, and put back in front
    of the fill. Three times. And then, when it finally took, the light was not in the room."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.hub.home = type("H", (), {"rooms": {"den": type("R", (), {"id": "den", "name": "Den"})()}})()
        self.radio = FakeRadio()
        self.strips = Strips(self.hub, self.radio)

    def tearDown(self): self.tmp.cleanup()

    def at_the_room_beat(self):
        self.strips.job = {"state": "room", "id": "2e4258", "label": "A light strip", "first": None}
        return self.strips.job

    def test_a_late_fill_message_cannot_drag_the_job_back_to_the_measuring(self):
        """The strip publishes its progress as it goes, and the last of those lands after somebody
        has already said "that's the whole of it"."""
        self.at_the_room_beat()
        self.strips._on_mqtt({"topic": "strip/2e4258/fill", "payload": "37"})
        self.assertEqual(self.strips.status()["state"], "room")

    def test_it_still_follows_the_fill_while_the_fill_is_what_is_on_screen(self):
        self.strips.job = {"state": "length", "id": "2e4258", "label": "A light strip", "first": None}
        self.strips._on_mqtt({"topic": "strip/2e4258/fill", "payload": "37"})
        st = self.strips.status()
        self.assertEqual((st["state"], st["lit"]), ("length", 37))

    def test_choosing_a_room_actually_puts_the_light_in_it(self):
        """It used to call hub.strip_placed(), a method no hub has ever had, inside a try/except
        AttributeError: pass -- so the wall said "It's in" and the household went and did it by
        hand."""
        self.at_the_room_beat()
        self.hub.ha.devices = [{"id": "dev1", "identifiers": [["mqtt", "strip_2e4258"]]},
                               {"id": "other", "identifiers": [["mqtt", "strip_ffffff"]]}]
        run(self.strips.put("den"))
        self.assertIn(("dev1", "den"), self.hub.ha.moved)
        self.assertEqual(self.strips.status()["state"], "ready")

    def test_nothing_a_strip_is_told_is_left_on_the_broker(self):
        """A retained command is a recording of an evening that ended weeks ago, replayed at every
        reconnect, and it wins silently when it is stale. A `count/set 1` from a bench test had a
        board believing it was one pixel long -- and a one-pixel strip looks exactly like a broken
        one, from the wall and from the room.

        The strip writes its length, its color order and its room into its own NVS, so the retain
        was redundant as well as dangerous, and these are only ever said to a strip that is online
        with somebody standing in front of it. Item 31, decided 22 September. The other half is in
        the firmware, which retires a retained one rather than obeying it."""
        self.at_the_room_beat()
        self.hub.ha.devices = [{"id": "dev1", "identifiers": [["mqtt", "strip_2e4258"]]}]
        run(self.strips.put("den"))
        said = [t.split("/", 2)[2] for t, _, _ in self.hub.ha.published]
        self.assertIn("room/set", said)            # or this proves nothing
        kept = [t for t, _, retain in self.hub.ha.published if retain]
        self.assertEqual(kept, [], "a strip was told something the broker will replay for ever")

    def test_a_light_the_house_has_not_made_yet_does_not_fail_the_setup(self):
        """Discovery is a moment behind the room chip, and a strip that is in the house but unplaced
        is still a strip that is in the house."""
        self.at_the_room_beat()
        self.hub.ha.devices = []
        import hub.strip as strip_mod
        was, strip_mod.PLACE_WAIT = strip_mod.PLACE_WAIT, 0
        try: run(self.strips.put("den"))
        finally: strip_mod.PLACE_WAIT = was
        self.assertEqual(self.strips.status()["state"], "ready")


class TheRoomsItOffers(unittest.TestCase):
    """A real house keeps its rooms as a DICT of id -> Room, and iterating a dict gives you its keys.
    So this asked a string for string["id"] and answered 500 to every request the sheet makes,
    including the poll it lives on -- at the one beat that reaches it, which is the last one."""

    class Room:
        def __init__(self, id, name): self.id, self.name = id, name

    def rooms_for(self, rooms):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        hub = FakeHub(tmp.name)
        hub.home = type("H", (), {"rooms": rooms})()
        return Strips(hub, FakeRadio())._rooms()

    def test_a_real_house_keeps_them_in_a_dict_and_that_is_not_a_list_of_rooms(self):
        got = self.rooms_for({"living": self.Room("living", "Living room"),
                              "kitchen": self.Room("kitchen", "Kitchen")})
        self.assertEqual(got, [{"id": "living", "name": "Living room"},
                               {"id": "kitchen", "name": "Kitchen"}])

    def test_unassigned_is_never_offered_as_somewhere_to_put_a_thing(self):
        got = self.rooms_for({"unassigned": self.Room("unassigned", "Unassigned"),
                              "hall": self.Room("hall", "Hall")})
        self.assertEqual([r["id"] for r in got], ["hall"])

    def test_a_house_with_no_rooms_at_all_is_not_an_error(self):
        self.assertEqual(self.rooms_for({}), [])
        self.assertEqual(self.rooms_for(None), [])


class WhenTheRealAnswerIsTheDistance(unittest.TestCase):
    """A strip at the far end of a house fails in whatever way the radio fails that minute, and every
    one of those sentences sends somebody to check a thing that is not wrong. Seen on a real hub on
    21 September: the hub could not hear the strip at all on a twenty-second scan, and the wall said
    "the strip did not take the code". The hub knew how faint it was when it knocked."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.strips = Strips(self.hub, self.radio)
        self.hub.settings.set(wifi={"ssid": "House", "pass": "secret"})

    def tearDown(self): self.tmp.cleanup()

    def said_at(self, rssi: int) -> str:
        async def go():
            self.radio.ours = [{"address": "AA:BB", "rssi": rssi, "name": "PROV_1"}]
            await self.strips.look()
            self.radio.adopt_fails = "The strip did not take the code."
            await self.strips.adopt()
            await turn()
            return self.strips.status()["text"]
        return run(go())

    def test_a_strip_barely_heard_is_told_it_is_too_far_and_nothing_else(self):
        said = self.said_at(-78)
        self.assertIn("long way from the hub", said)
        self.assertIn("same room", said)
        # And NOT the library's reason as well: two answers is the household checking both.
        self.assertNotIn("did not take the code", said)

    def test_a_strip_right_next_to_the_hub_gets_the_real_reason(self):
        said = self.said_at(-38)
        self.assertIn("did not take the code", said)
        self.assertNotIn("long way", said)

    def test_a_strip_with_no_signal_reported_is_not_guessed_about(self):
        """Matter's door does not always give one, and inventing a distance is worse than saying
        what actually failed."""
        async def go():
            self.radio.advertising = [{"addr": "CC:DD", "discriminator": 3840, "vendor": TEST_VID,
                                       "ours": True, "rssi": None}]
            await self.strips.look()
            self.radio.commission_fails = "The strip did not take the code."
            await self.strips.adopt()
            await turn()
            return self.strips.status()["text"]
        self.assertIn("did not take the code", run(go()))


class ThreeFailuresThatAreNotTheSame(unittest.TestCase):
    """A wrong count and a dropped radio both used to say "check the flashes", which sends somebody
    to count again and again at the far end of a room where the real answer was to move nearer. The
    strip refuses a wrong rhythm inside SRP6a and it comes back as an ATT error; a link that died
    comes back as a disconnect. And nobody having pressed the button yet is neither -- the household
    is standing in the right room and has simply not touched the thing. Three sentences."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)

    def tearDown(self): self.tmp.cleanup()

    def said_for(self, boom, rhythm: str = "1234") -> str:
        radio = Radio(self.hub)

        async def go():
            import hub.strip_door as door
            async def bang(*a, **k):
                raise (boom if isinstance(boom, BaseException) else RuntimeError(boom))
            door.adopt = bang
            with self.assertRaises(StripError) as e:
                await radio.adopt_ours("AA:BB", "House", "x", hub={}, rhythm=rhythm)
            return str(e.exception)
        return run(go())

    def test_a_wrong_count_is_told_to_count_again(self):
        said = self.said_for("GATT Protocol Error: Unlikely Error")
        self.assertIn("not the flashes", said)
        self.assertNotIn("nearer", said)

    def test_a_dropped_link_is_told_to_move_nearer_and_not_to_recount(self):
        for boom in ("failed to discover services, device disconnected",
                     "Device not found", "TimeoutError"):
            said = self.said_for(boom)
            self.assertIn("nearer the hub", said)
            self.assertNotIn("Count them again", said)

    def test_nobody_having_pressed_it_is_never_dressed_as_a_radio_failure(self):
        """The one that would be cruellest to get wrong: there is nothing wrong with the radio, the
        strip or the room, and telling somebody to move nearer sends them to fix none of it."""
        import hub.strip_door as door
        said = self.said_for(door.NotPressed("nobody pressed the button on the strip"), rhythm="")
        self.assertIn("Nobody pressed", said)
        self.assertNotIn("nearer", said)
        self.assertNotIn("flashes", said)

    def test_a_failure_with_no_message_at_all_is_still_read_right(self):
        """The commonest one on a real hub, and the one that used to read as "unplug it": a BLE
        connect that times out on BlueZ arrives as a bare asyncio.TimeoutError whose str() is the
        empty string -- and asyncio.TimeoutError has BEEN the builtin since 3.11, so there is only
        one of them to catch. Matching on the message alone missed every one."""
        said = self.said_for(TimeoutError(), rhythm="")
        self.assertIn("nearer the hub", said)
        self.assertNotIn("Unplug it", said)

    def test_a_strip_the_radio_never_reached_is_not_blamed_on_the_strip(self):
        """bleak names the class and says nothing else, and a class name has no spaces in it."""
        class BleakDeviceNotFoundError(Exception): pass
        said = self.said_for(BleakDeviceNotFoundError(), rhythm="")
        self.assertIn("nearer the hub", said)

    def test_a_strip_that_will_not_finish_a_press_session_is_not_told_to_recount(self):
        """There are no flashes on this rung, so "count them again" is an instruction about a thing
        that is not on the wall."""
        said = self.said_for("Unlikely Error", rhythm="")
        self.assertNotIn("Count them again", said)
        self.assertIn("Unplug it", said)
