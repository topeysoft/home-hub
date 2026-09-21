# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A light strip arriving, without a light strip.

The machine is what the panel draws (design/strip/Spine.dc.html), so what these hold is the sequence
somebody standing in the room would see: it knocks, nothing of the house's moves until they say yes,
it joins the Wi-Fi, it says what color it is showing, it fills up and is stopped, it gets a room.
And the two questions only a strip has -- which color comes out first, and how far it goes -- both of
which exist because nothing can be read back off a strip.
"""
import asyncio, json, sqlite3, tempfile, unittest
from pathlib import Path

from hub.settings import Settings
from hub.strip import ASSUME, ORDERS, StripError, Strips, lit_index, narrow, probe, resolve


class FakeRadio:
    """What Bluetooth would have said, in the shape a commissionable Matter device says it.

    Note what is NOT here: no Wi-Fi, no credentials of any kind. Commissioning carries those itself,
    which is the whole reason the firmware left the Arduino framework."""
    def __init__(self):
        self.advertising = []
        self.commissioned = []
        self.commission_fails = None
        self.scan_boom = None

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

    async def subscribe(self, type_, cb, **kw): self.cb = cb; return 1

    async def call(self, domain, service, target, **kw):
        topic, payload = kw.get("topic"), kw.get("payload")
        self.published.append((topic, payload))
        leaf = "/".join(topic.split("/")[2:])
        if leaf in self.answers and self.cb:
            back_leaf, back_payload = self.answers[leaf]
            id_ = topic.split("/")[1]
            self.cb({"topic": f"strip/{id_}/{back_leaf}", "payload": back_payload})


class FakeHub:
    def __init__(self, tmp, wifi=True):
        self.settings = Settings(Path(tmp) / "settings.json")
        self.settings.set(wifi={"ssid": "House", "pass": "hunter2 with space"} if wifi else None)
        self.env = {"MQTT_USER": "hub", "MQTT_PASSWORD": "pw"}
        self.hostname = "hub"
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

    def test_the_hub_never_handles_the_wifi_password_at_all_any_more(self):
        """It used to, twice, and both were wrong: a hand-rolled BLE characteristic that sent the
        password in the clear, then WiFiProv, which only existed because Arduino compiles
        Matter-over-BLE out. Commissioning carries the credentials itself now, so there is no route
        through this module that could leak one -- and the old one refuses rather than lying."""
        with self.assertRaises(StripError):
            run(self.s.wifi("House", "hunter2"))


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
        self.assertEqual(self.hub.steps, ["wifi", "hub"])

    def test_a_strip_with_no_code_is_refused_rather_than_half_set_up(self):
        run(self.adopt(code=""))
        s = self.s.status()
        self.assertEqual(s["state"], "failed")
        self.assertIn("setup code", s["text"])
        self.assertEqual(self.radio.commissioned, [])

    def test_and_a_finished_job_stops_reporting_once_it_is_read(self):
        run(self.adopt())
        run(self.s.done())
        self.assertEqual(self.s.status()["state"], "none")


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
        return [p for t, p in self.hub.ha.published if t.endswith("/" + leaf)]

    def test_the_house_can_list_what_it_has(self):
        self.assertEqual(self.s.each(), [{"id": "c8ebba", "online": True, "count": 186, "order": "grb"}])

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
