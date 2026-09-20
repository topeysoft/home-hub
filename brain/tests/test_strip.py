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
    """What Bluetooth would have said. `advertising` is every strip that has never been set up."""
    def __init__(self):
        self.advertising = []
        self.joined = []
        self.join_fails = None
        self.scan_boom = None

    async def scan(self, seconds=4.0):
        if self.scan_boom: raise self.scan_boom
        return list(self.advertising)

    async def join(self, addr, cfg):
        if self.join_fails: raise StripError(self.join_fails)
        self.joined.append((addr, cfg)); return {"addr": addr}

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

    def arrive(self, id="c8ebba", addr="AA:BB:CC:DD:EE:FF", rssi=-52):
        self.radio.advertising = [{"id": id, "addr": addr, "rssi": rssi}]

    def test_nothing_to_say_when_nothing_is_advertising(self):
        run(self.s.look())
        self.assertEqual(self.s.status()["state"], "none")

    def test_a_strip_that_has_never_been_set_up_knocks(self):
        self.arrive()
        run(self.s.look())
        self.assertEqual(self.s.status()["state"], "knocking")
        self.assertEqual(self.radio.joined, [])          # nothing of the house's has gone anywhere

    def test_the_wall_is_never_shown_an_address(self):
        """The identity check is the object: it is two meters of lit strip and it is the only one
        lit. A household shown a MAC has been handed the inside of the product."""
        self.arrive(id="c8ebba", addr="AA:BB:CC:DD:EE:FF")
        run(self.s.look())
        said = json.dumps(self.s.status())
        self.assertNotIn("AA:BB", said)
        self.assertNotIn("c8ebba", said)

    def test_the_chip_is_the_id_and_the_address_is_only_how_to_reach_it(self):
        """They are not interchangeable: the strip publishes on its chip for the rest of its life,
        and the Bluetooth address it was found at is not even the same kind of thing on every host."""
        self.arrive(id="c8ebba", addr="AA:BB:CC:DD:EE:FF")
        run(self.s.look())
        self.assertEqual((self.s.job["id"], self.s.job["addr"]), ("c8ebba", "AA:BB:CC:DD:EE:FF"))

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

    def test_a_hub_with_no_wifi_asks_for_it_rather_than_failing(self):
        self.hub.settings.set(wifi=None)
        self.arrive()
        run(self.s.look())
        run(self.s.adopt())
        s = self.s.status()
        self.assertEqual((s["state"], s["needs"]), ("working", "wifi"))
        self.assertEqual(self.radio.joined, [])


class TheWholeWay(unittest.TestCase):
    """Knock to ready, the way one household would go through it once."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.radio.advertising = [{"id": "c8ebba", "addr": "AA:BB:CC:DD:EE:FF", "rssi": -50}]
        self.s = Strips(self.hub, radio=self.radio)
        # the strip answers: it comes online when greeted, and says where the fill got to when stopped
        self.hub.ha.answers = {"hello": ("status", "online"), "fill/stop": ("count", "186")}
        run(self.s.listen())

    def tearDown(self): self.tmp.cleanup()

    async def adopt(self):
        await self.s.look()
        await self.s.adopt()
        for _ in range(50): await asyncio.sleep(0)

    def said(self, leaf):
        return [p for t, p in self.hub.ha.published if t.endswith("/" + leaf)]

    def test_it_joins_and_then_asks_about_color(self):
        run(self.adopt())
        s = self.s.status()
        self.assertEqual((s["state"], s["asking"]), ("order", "red"))
        self.assertEqual(self.radio.joined[0][1]["ssid"], "House")
        self.assertEqual(self.said("show/set"), ["raw 0 255 0"])   # red on a grb strip, sent unmapped

    def test_yes_that_is_red_goes_straight_to_the_fill(self):
        run(self.adopt())
        run(self.s.saw("red"))
        self.assertEqual(self.s.status()["state"], "length")
        self.assertEqual(self.said("order/set"), ["grb"])

    def test_something_else_asks_once_more_and_then_settles(self):
        run(self.adopt())
        run(self.s.saw("green"))
        s = self.s.status()
        self.assertEqual((s["state"], s["asking"]), ("order", "which"))
        self.assertEqual(self.said("show/set")[-1], "raw 255 0 0")
        run(self.s.saw("blue"))
        self.assertEqual(self.said("order/set"), ["bgr"])
        self.assertEqual(self.s.status()["state"], "length")

    def test_stripes_mean_a_white_channel_and_are_not_a_fault(self):
        """A three-byte frame on a four-channel strip misaligns by a byte a pixel and comes out as a
        candy-stripe. It answers how many channels, not which order, so the color question stays open."""
        run(self.adopt())
        run(self.s.saw("stripes"))
        s = self.s.status()
        self.assertEqual((s["state"], s["asking"]), ("order", "red"))
        self.assertEqual(self.said("white/set"), ["1"])

    def test_nothing_at_all_is_a_fault_and_says_something_useful(self):
        run(self.adopt())
        run(self.s.saw("nothing"))
        s = self.s.status()
        self.assertEqual(s["state"], "failed")
        self.assertIn("plugged in", s["text"])

    def test_the_fill_is_stopped_and_the_length_is_the_strip_s_own_number(self):
        """The firmware latches where it had got to when it hears the stop, not when the brain gets
        round to reading a number back -- otherwise a strip measures short by however busy the Wi-Fi
        was, and the person's reaction time is already the error that matters."""
        run(self.adopt()); run(self.s.saw("red"))
        run(self.s.ends())
        s = self.s.status()
        self.assertEqual((s["state"], s["count"]), ("room", 186))
        self.assertEqual(self.said("count/set"), ["186"])

    def test_a_room_finishes_it(self):
        run(self.adopt()); run(self.s.saw("red")); run(self.s.ends())
        run(self.s.put("living"))
        self.assertEqual(self.s.status()["state"], "ready")
        self.assertEqual(self.hub.placed, [("c8ebba", "living")])

    def test_and_a_finished_job_stops_reporting_once_it_is_read(self):
        """Otherwise the sheet goes away and the very next poll brings it straight back, and somebody
        sits there pressing OK at a dialog that will not die."""
        run(self.adopt()); run(self.s.saw("red")); run(self.s.ends()); run(self.s.put("living"))
        run(self.s.done())
        self.assertEqual(self.s.status()["state"], "none")

    def test_the_whole_way_through_is_drawn_beat_for_beat(self):
        """design/strip/Spine.dc.html is six beats and this is the order they happen in. If a beat is
        added, moved or dropped, the board changed and this should fail until it is redrawn."""
        run(self.adopt()); run(self.s.saw("red")); run(self.s.ends()); run(self.s.put("living"))
        self.steps = self.hub.steps
        beats = [b for i, b in enumerate(self.hub.pushed) if i == 0 or b != self.hub.pushed[i - 1]]
        self.assertEqual(beats, ["knocking", "working", "order", "length", "room", "ready"])
        # and the middle beat is TWO steps, not the bridge's three: the software is already on it,
        # which is the whole reason it could knock in the first place.
        self.assertEqual(self.steps, ["wifi", "hub"])


class WhenItGoesWrong(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.radio = FakeRadio()
        self.radio.advertising = [{"id": "c8ebba", "addr": "AA:BB:CC:DD:EE:FF", "rssi": -50}]
        self.s = Strips(self.hub, radio=self.radio)
        run(self.s.listen())

    def tearDown(self): self.tmp.cleanup()

    async def adopt(self, settle: float = 0.0):
        await self.s.look(); await self.s.adopt()
        for _ in range(50): await asyncio.sleep(0)
        if settle: await asyncio.sleep(settle)

    def test_a_strip_that_joins_but_never_finds_the_hub_says_which_it_was(self):
        """Two different failures the household can only fix one of."""
        import hub.strip as mod
        was, mod.JOIN_WAIT = mod.JOIN_WAIT, 0.01
        try: run(self.adopt(settle=0.08))
        finally: mod.JOIN_WAIT = was
        s = self.s.status()
        self.assertEqual(s["state"], "failed")
        self.assertIn("never found the hub", s["text"])

    def test_a_library_s_own_words_never_reach_the_wall(self):
        """bridge.py learned this the expensive way: a bridge once failed with "database is locked"
        on the wall, which tells nobody anything and was not even true about their bridge."""
        async def boom(addr, cfg): raise sqlite3.OperationalError("database is locked")
        self.radio.join = boom
        run(self.adopt())
        s = self.s.status()
        self.assertEqual(s["state"], "failed")
        self.assertNotIn("database", s["text"])

    def test_but_a_sentence_written_for_the_wall_comes_through_as_itself(self):
        self.radio.join_fails = "This hub has no Bluetooth to set a light strip up with."
        run(self.adopt())
        self.assertIn("no Bluetooth", self.s.status()["text"])


if __name__ == "__main__":
    unittest.main()
