# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A strip controller on the wall: why a strip is dark, a second strip, and one wire or two.

design/controller-panel/, decided 1 October 2026. These hold the brain to the boards: the words per
reason are Reasons.dc.html's; a strip held dark says so on its tile and on Needs a look, first; running
hot and holding under 5 A change nothing on the tile; a second strip is asked one question and then its
own colors and length, starting from the first's answer; and "nothing at all" is given one more look
only when the controller said it could not tell how many wires the strip has.
"""
import json, tempfile, unittest

from hub import controller
from hub.model import Device, Home, Room
from hub.strip import FORGET, StripError, Strips, probe, resolve, second_at
from tests.test_strip import FakeHub, FakeRadio, run


def power(supply=24.1, cls=24, runs=None, board_c=31):
    return {"board": "reva", "v": supply, "class": cls, "board_c": board_c,
            "runs": runs or [{"on": False, "class": 12, "a": 0.0, "most": 4.75, "dim": 100,
                              "switch": False, "wiring": False, "trips": 0, "held": "supply"}]}


def run1(**kw):
    r = {"on": True, "class": 12, "a": 0.4, "most": 4.75, "dim": 100, "switch": False, "wiring": False,
         "trips": 0, "held": ""}
    r.update(kw)
    return r


class TheWords(unittest.TestCase):
    """Reasons.dc.html, card by card."""

    def test_set_up_on_another_kind_of_supply(self):
        said = controller.held("supply", power(), 1, "Under-cabinet strip")
        self.assertEqual(said["state"], "Staying off")
        self.assertEqual(said["tile"], "on a different power supply")
        self.assertEqual(said["text"], "It was set up on a 12 V power supply, and it’s on a 24 V one now. "
                                       "A 12 V strip would burn on 24 V, so the controller is keeping it off.")
        self.assertEqual(said["next"], "Plug the 12 V supply back in")
        self.assertEqual((said["set_up_on"], said["now_on"]), ("12 V", "24 V"))
        self.assertEqual(said["chip"], "The strip is staying off to protect itself")
        self.assertTrue(said["row"].startswith("Under-cabinet strip is staying off. It was set up on a 12 V"))

    def test_the_burn_is_only_said_the_way_it_is_true(self):
        """A 24 V strip on a 12 V supply does not burn; it is dark and dim. Saying it would is a lie
        told to somebody who already did the right thing by unplugging the big one."""
        p = power(supply=12.0, cls=12, runs=[run1(on=False, **{"class": 24}, held="supply", a=0)])
        self.assertNotIn("burn", controller.held("supply", p, 1)["text"])

    def test_a_supply_no_strip_is_made_for(self):
        said = controller.held("range", power(supply=19.2, cls=0, runs=[run1(on=False, held="range"), run1(on=False, held="range")]), 1)
        self.assertEqual(said["tile"], "wrong kind of power supply")
        self.assertIn("Its power supply gives 19 V. Strips are made for 5, 12 or 24 V, and 19 is none of them", said["text"])
        self.assertIn("laptop charger", said["text"])
        self.assertIn("Both strips on this controller are off.", said["text"])
        self.assertEqual(said["next"], "Use the power supply that came with the strip")

    def test_a_nine_volt_adapter_is_not_called_a_laptop_charger(self):
        said = controller.held("range", power(supply=9.0, cls=0, runs=[run1(held="range")]), 1)
        self.assertNotIn("laptop", said["text"])

    def test_trips_and_wiring_end_in_unplugging_the_controller(self):
        """Both hold until the board is next powered on -- the controller's rule, said in the only words
        that matter."""
        for reason, tile in (("trips", "it kept cutting out"), ("wiring", "a wire in the wrong place")):
            said = controller.held(reason, power(runs=[run1(held=reason)]), 1)
            self.assertEqual(said["state"], "Switched off")
            self.assertEqual(said["tile"], tile)
            self.assertIn("unplug the controller and plug it back in", said["next"])

    def test_starting_is_never_said(self):
        self.assertIsNone(controller.held("starting", power()))
        self.assertIsNone(controller.light(power(runs=[run1(held="starting")]), [1]))

    def test_running_hot_is_not_a_fault_and_the_tile_does_not_change(self):
        p = power(board_c=92, runs=[run1(dim=80)])
        said = controller.light(p, [1])
        self.assertNotIn("held", said)
        self.assertIn("The controller is warm", said["quiet"])

    def test_held_just_under_one_sockets_five_amps_is_quieter_still(self):
        said = controller.light(power(runs=[run1(dim=97)]), [1])
        self.assertNotIn("held", said)
        self.assertIn("Nothing needs doing", said["quiet"])

    def test_a_light_with_one_part_dark_is_on_and_says_which_part(self):
        """A dark garage end is not a dark house (design/roofline/OneLight.dc.html)."""
        p = power(runs=[run1(), run1(on=False, held="supply", a=0)])
        said = controller.light(p, [1, 2])
        self.assertNotIn("held", said)
        self.assertEqual(said["dark"][0]["run"], 2)

    def test_a_light_all_of_whose_parts_are_dark_is_held(self):
        p = power(runs=[run1(on=False, held="supply", a=0), run1(on=False, held="supply", a=0)])
        self.assertEqual(controller.light(p, [1, 2])["held"], "supply")

    def test_anything_that_is_not_a_report_is_nothing(self):
        for junk in ("", "nope", "[]", json.dumps({"runs": "x"}), None):
            self.assertIsNone(controller.read(junk))
        self.assertEqual(controller.read(json.dumps(power()))["v"], 24.1)


class HouseWithAStrip(unittest.TestCase):
    """The brain's half: the report reaches the light it is about, and Needs a look."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        h = Home()
        h.rooms = {"kitchen": Room("kitchen", "Kitchen"), "outside": Room("outside", "Outside"),
                   "unassigned": Room("unassigned", "New devices")}
        self.light = Device("light.under_cabinet", "Under-cabinet strip", "kitchen", "light", "on", {}, "dev1")
        h.devices = {self.light.id: self.light}
        h.rooms["kitchen"].devices.append(self.light)
        self.hub.home = h
        self.broadcast = []
        was = self.hub._broadcast
        self.hub._broadcast = lambda m: (self.broadcast.append(json.loads(m)), was(m) if json.loads(m).get("type") == "strip" else None)
        self.s = Strips(self.hub, FakeRadio())
        self.s.strips["c8ebba"] = {"online": True, "count": 186, "order": "grb"}
        self.s._devices["c8ebba"] = "dev1"

    def tearDown(self): self.tmp.cleanup()

    def tell(self, leaf, payload):
        self.s._on_mqtt({"topic": f"strip/c8ebba/{leaf}", "payload": payload})

    def test_a_held_strip_says_so_on_its_tile(self):
        self.tell("power", json.dumps(power()))
        self.s.carry("c8ebba")
        self.assertEqual(self.light.attrs["strip"]["state"], "Staying off")
        self.assertEqual(self.hub.home.reports["light.under_cabinet"]["strip"]["held"], "supply")
        self.assertEqual(self.broadcast[-1]["type"], "device")

    def test_and_only_a_change_is_said(self):
        self.tell("power", json.dumps(power()))
        self.assertEqual(self.s.carry("c8ebba"), ["light.under_cabinet"])
        self.assertEqual(self.s.carry("c8ebba"), [])

    def test_and_it_goes_when_the_right_supply_is_back(self):
        self.tell("power", json.dumps(power()))
        self.s.carry("c8ebba")
        self.tell("power", json.dumps(power(supply=12.1, cls=12, runs=[run1()])))
        self.s.carry("c8ebba")
        self.assertNotIn("strip", self.light.attrs)
        self.assertNotIn("light.under_cabinet", self.hub.home.reports)

    def test_needs_a_look_carries_a_row_with_the_name_and_where_and_show_me(self):
        self.tell("power", json.dumps(power()))
        self.s.carry("c8ebba")
        rows = self.s.notes()
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual((r["kind"], r["subject"], r["where"]), ("held", "light.under_cabinet", "Kitchen · a light strip"))
        self.assertTrue(r["text"].startswith("Under-cabinet strip is staying off."))
        self.assertEqual(r["acts"], [{"do": "Show me", "act": "open", "to": "light.under_cabinet"}])
        self.assertEqual(r["band"], "The kitchen strip is staying off")

    def test_hot_and_five_amps_put_nothing_on_needs_a_look(self):
        self.tell("power", json.dumps(power(board_c=95, runs=[run1(dim=70)])))
        self.s.carry("c8ebba")
        self.assertEqual(self.s.notes(), [])
        self.assertIn("quiet", self.light.attrs["strip"])
        self.assertNotIn("held", self.light.attrs["strip"])

    def test_health_sorts_it_first(self):
        from hub.health import Health
        from tests.test_health import FakeProvision
        self.tell("power", json.dumps(power()))
        self.s.carry("c8ebba")
        self.hub.strip = self.s
        self.hub.provision = FakeProvision()
        self.hub.provision.parts = [{"id": "zwave", "name": "Z-Wave radio", "state": "failed", "text": "gone"}]
        self.hub.bridge.quiet = lambda: []
        self.hub.log.recent = lambda **k: []
        self.hub.log.last_by_subject = lambda *a: {}
        self.hub.tz = None
        self.hub.updates = type("U", (), {"state": lambda self: {}})()
        notes = Health(self.hub).notes()
        self.assertEqual(notes[0]["kind"], "held")
        self.assertIn("Z-Wave radio", " ".join(n["text"] for n in notes[1:]))

    def test_forgetting_empties_every_word_a_controller_retains(self):
        """docs/strip.md item 51: power, board, type and the run2/ leaves join the list."""
        out = run(self.s.forget("c8ebba"))
        cleared = {t for t, p, retain in self.hub.ha.published if retain and p == ""}
        for leaf in ("power", "board", "type", "wire", "run2/count", "run2/order", "run2/fill",
                     "run2/type", "run2/wire", "run2/own", "run2/light"):
            self.assertIn(leaf, FORGET)
            self.assertIn(f"strip/c8ebba/{leaf}", cleared)
        self.assertIn("homeassistant/light/strip_c8ebba_2/config", cleared)
        self.assertTrue(out["heard"])

    def test_the_second_strips_words_are_filed_under_it(self):
        self.tell("run2/count", "92")
        self.tell("run2/order", "rgb")
        self.tell("run2/own", "1")
        self.tell("type", "two")
        self.tell("wire", json.dumps({"found": "unclear", "idle": 0.01, "one": 0.02, "two": 0.02}))
        s = self.s.strips["c8ebba"]
        self.assertEqual(s["run2"], {"count": 92, "order": "rgb", "own": True})
        self.assertEqual(s["types"][1], "two")
        self.assertEqual(s["wire"][1]["found"], "unclear")


class TheSecondStrip(unittest.TestCase):
    """design/controller-panel/AskWhichC.dc.html: one question after the first strip is measured, then
    the second strip's own colors and length, starting from the first's answer."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.hub.home = type("H", (), {"rooms": {"kitchen": Room("kitchen", "Kitchen")}, "devices": {}})()
        self.s = Strips(self.hub, FakeRadio())
        run(self.s.listen())
        self.s.strips["c8ebba"] = {"online": True,
                                   "power": power(supply=12, cls=12, runs=[run1(), run1(a=0.3)])}
        self.s.job = {"state": "length", "id": "c8ebba", "label": "A light strip", "first": None, "order1": "rgb"}
        self.hub.ha.answers["fill/stop"] = ("count", "186")
        self.hub.ha.answers["run2/fill/stop"] = ("run2/count", "92")

    def tearDown(self): self.tmp.cleanup()

    def said(self): return [(t.split("/", 2)[2], p) for t, p, _ in self.hub.ha.published]

    def test_it_is_asked_only_when_there_is_a_second_strip(self):
        self.s.strips["c8ebba"]["power"] = power(supply=12, cls=12, runs=[run1(), run1(a=0.0)])
        self.assertEqual(run(self.s.ends())["state"], "room")

    def test_the_first_rests_and_the_second_glows(self):
        st = run(self.s.ends())
        self.assertEqual(st["state"], "second")
        self.assertIn(("show/set", "off"), self.said())
        self.assertIn(("run2/show/set", "raw 90 90 90"), self.said())

    def test_its_colors_start_from_the_first_strips_answer(self):
        """So the same make is right in one tap."""
        run(self.s.ends())
        st = run(self.s.second("part"))
        self.assertEqual((st["state"], st["run"], st["asking"]), ("order", 2, "red"))
        r, g, b = probe("rgb")
        self.assertIn(("run2/show/set", f"raw {r} {g} {b}"), self.said())
        st = run(self.s.saw("red"))
        self.assertIn(("run2/order/set", "rgb"), self.said())
        self.assertEqual(st["state"], "length")
        self.assertIn(("run2/show/set", "fill"), self.said())

    def test_and_its_length_is_its_own(self):
        run(self.s.ends()); run(self.s.second("part")); run(self.s.saw("red"))
        st = run(self.s.ends())
        self.assertIn(("run2/count/set", "92"), self.said())
        self.assertEqual(st["state"], "room")
        self.assertEqual(self.s.strips["c8ebba"]["run2"]["count"], 92)

    def test_part_of_the_light_is_never_asked_a_room_of_its_own(self):
        self.hub.ha.devices = [{"id": "dev1", "identifiers": [["mqtt", "strip_c8ebba"]]}]
        run(self.s.ends()); run(self.s.second("part")); run(self.s.saw("red")); run(self.s.ends())
        self.assertEqual(run(self.s.put("kitchen"))["state"], "ready")
        self.assertNotIn(("run2/own/set", "1"), self.said())

    def test_a_light_of_its_own_is_announced_and_asked_a_second_room(self):
        self.hub.ha.devices = [{"id": "dev1", "identifiers": [["mqtt", "strip_c8ebba"]]}]
        run(self.s.ends()); run(self.s.second("own")); run(self.s.saw("red")); run(self.s.ends())
        self.assertIn(("run2/own/set", "1"), self.said())
        st = run(self.s.put("kitchen"))
        self.assertEqual((st["state"], st.get("placing_run")), ("room", 2))
        import hub.strip as strip_mod
        was, strip_mod.PLACE_WAIT = strip_mod.PLACE_WAIT, 0
        try: st = run(self.s.put("kitchen"))
        finally: strip_mod.PLACE_WAIT = was
        self.assertEqual(st["state"], "ready")
        self.assertIn("c8ebba#2", self.s._owed)       # its light had not been made yet: kept, not dropped

    def test_a_second_strip_of_another_make_takes_the_second_question(self):
        """First strip rgb (red on byte 0): the second question must light another byte, or it could
        not split the pair -- which is why the second byte is not always the first."""
        self.assertEqual(second_at("rgb"), 1)
        self.assertEqual(second_at("grb"), 0)
        for truth in ("rgb", "rbg", "grb", "gbr", "brg", "bgr"):
            first = truth[probe("rgb").index(255)]
            if first == "r": continue
            second = truth[second_at("rgb")]
            self.assertEqual(resolve(first, second, assume="rgb"), truth)

    def test_one_plugged_in_later_is_one_band_line_and_the_same_question(self):
        self.s.job = None
        self.s.strips["c8ebba"]["count"] = 186
        self.hub.home.devices = {}
        self.s._noticed("c8ebba")
        lines = self.s.status()["plugged"]
        self.assertEqual(lines[0]["id"], "c8ebba")
        self.assertIn("Something new is plugged into", lines[0]["text"])
        st = run(self.s.second_later("c8ebba"))
        self.assertEqual(st["state"], "second")
        self.assertNotIn("plugged", st)


class OneWireOrTwo(unittest.TestCase):
    """design/controller-panel/, "wire": C falling back to A. The controller finds out by itself; the
    household is asked A's question only when it says the reading was unclear."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.s = Strips(self.hub, FakeRadio())
        self.s.strips["c8ebba"] = {"online": True}
        self.s.job = {"state": "order", "id": "c8ebba", "label": "A light strip", "first": None}

    def tearDown(self): self.tmp.cleanup()

    def said(self): return [(t.split("/", 2)[2], p) for t, p, _ in self.hub.ha.published]

    def test_a_clear_reading_leaves_nothing_at_all_the_real_failure(self):
        self.s.strips["c8ebba"]["wire"] = {1: {"found": "one"}}
        st = run(self.s.saw("nothing"))
        self.assertEqual(st["state"], "failed")
        self.assertEqual(self.said(), [])

    def test_a_devkit_says_nothing_about_wires_and_nothing_changes(self):
        self.assertEqual(run(self.s.saw("nothing"))["state"], "failed")

    def test_an_unclear_reading_tries_the_other_way_and_asks_again(self):
        self.s.strips["c8ebba"]["wire"] = {1: {"found": "unclear"}}
        self.s.strips["c8ebba"]["types"] = {1: "one"}
        st = run(self.s.saw("nothing"))
        self.assertEqual((st["state"], st["asking"]), ("order", "lit"))
        self.assertIn(("type/set", "two"), self.said())

    def test_lit_goes_back_to_is_it_red_the_new_way(self):
        self.s.strips["c8ebba"]["wire"] = {1: {"found": "unclear"}}
        run(self.s.saw("nothing"))
        st = run(self.s.saw("lit"))
        self.assertEqual((st["state"], st["asking"]), ("order", "red"))
        self.assertNotIn(("type/set", "one"), self.said())

    def test_still_dark_is_the_real_failure_and_says_so_and_puts_it_back(self):
        self.s.strips["c8ebba"]["wire"] = {1: {"found": "unclear"}}
        run(self.s.saw("nothing"))
        st = run(self.s.saw("dark"))
        self.assertEqual(st["state"], "failed")
        self.assertIn("no power is reaching it", st["text"])
        self.assertEqual(self.said()[-1], ("type/set", "one"))

    def test_it_is_tried_once(self):
        self.s.strips["c8ebba"]["wire"] = {1: {"found": "unclear"}}
        run(self.s.saw("nothing")); run(self.s.saw("lit"))
        self.assertEqual(run(self.s.saw("nothing"))["state"], "failed")

    def test_the_second_strip_is_asked_on_its_own_wire(self):
        self.s.job.update(run=2)
        self.s.strips["c8ebba"]["wire"] = {2: {"found": "unclear"}}
        run(self.s.saw("nothing"))
        self.assertIn(("run2/type/set", "two"), self.said())

    def test_a_word_that_answers_nothing_is_refused(self):
        self.s.strips["c8ebba"]["wire"] = {1: {"found": "unclear"}}
        run(self.s.saw("nothing"))
        with self.assertRaises(StripError): run(self.s.saw("green"))


class AfterwardsJoinOrSplit(unittest.TestCase):
    """design/controller-panel/ChangeLaterC.dc.html: split asks only a room; join asks nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.s = Strips(self.hub, FakeRadio())
        self.s.strips["c8ebba"] = {"online": True, "count": 186, "run2": {"count": 92}}

    def tearDown(self): self.tmp.cleanup()

    def test_split_and_join_are_one_word_each_to_the_controller(self):
        run(self.s.split("c8ebba", "kitchen"))
        self.assertIn(("strip/c8ebba/run2/own/set", "1", False), self.hub.ha.published)
        self.assertTrue(self.s.strips["c8ebba"]["run2"]["own"])
        run(self.s.join("c8ebba"))
        self.assertIn(("strip/c8ebba/run2/own/set", "0", False), self.hub.ha.published)
        self.assertFalse(self.s.strips["c8ebba"]["run2"]["own"])

    def test_a_controller_with_one_strip_has_nothing_to_split(self):
        self.s.strips["c8ebba"]["run2"] = {}
        with self.assertRaises(StripError): run(self.s.split("c8ebba", "kitchen"))

    def test_the_second_strips_own_questions_are_asked_with_run2_in_front(self):
        run(self.s.revisit("c8ebba", "length", run=2))
        self.assertIn(("strip/c8ebba/run2/show/set", "fill", False), self.hub.ha.published)


if __name__ == "__main__":
    unittest.main()
