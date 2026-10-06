# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The roofline: one light outside, its holidays, its evenings, and the way round.

design/roofline/, decided 1 October 2026: the occasion owns its motion and the one control is Hold it
still (A), a look can be said and plays before it is kept (C); the roof keeps evenings of its own like a
porch light and an occasion still turns nothing on (B); several boxes are one Roofline, and the way round
is asked only when a chase is first wanted, from a guess (C then A).
"""
import json, tempfile, time, unittest
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from hub import roofline as R
from hub.commands import Commands, NotUnderstood, read_look
from hub.model import Device, Home, Room
from hub.settings import Settings
from hub.strip import Strips
from tests.test_strip import FakeHA, FakeLog, FakeRadio, run

TZ = ZoneInfo("America/Chicago")
HOLTS_SUMMIT = {"name": "Holts Summit", "lat": 38.64, "lon": -92.12}


class House:
    """Just enough of a hub for the roofline: settings, a clock, a place, lights, and the broker."""

    def __init__(self, tmp):
        self.settings = Settings(Path(tmp) / "settings.json")
        self.tz, self.location = TZ, dict(HOLTS_SUMMIT)
        self.ha, self.log = FakeHA(), FakeLog()
        self.home = Home()
        self.home.rooms = {"outside": Room("outside", "Outside"), "unassigned": Room("unassigned", "New devices")}
        self.acts, self.rebuilt = [], 0
        self.strip = Strips(self, FakeRadio())
        self.roofline = R.Roofline(self)
        self.pushed = []

    def _broadcast(self, m): self.pushed.append(json.loads(m))
    def rebuild_soon(self): self.rebuilt += 1

    def box(self, chip, hw, count=150, run2=0, online=True):
        d = Device(f"light.strip_{chip}", "Light strip", "outside", "light", "off", {}, hw)
        self.home.devices[d.id] = d
        self.home.rooms["outside"].devices.append(d)
        self.strip.strips[chip] = {"online": online, "count": count, **({"run2": {"count": run2}} if run2 else {})}
        self.strip._devices[chip] = hw
        return d

    async def act(self, dev, action, data=None, source="user", said=None):
        self.acts.append((dev.id, action, source))
        dev.state = "on" if action == "on" else "off"

    def looks(self):
        """Every look told to a box: chip -> the last body."""
        out = {}
        for t, p, _ in self.ha.published:
            if t.endswith("/look/set"): out[t.split("/")[1]] = json.loads(p)
        return out


class TheOccasions(unittest.TestCase):
    """Dates decide which occasion is showing. They decide how it looks and nothing else."""

    def test_the_dates_said_on_the_look_card(self):
        """The look card says when its occasion runs (design/roofline/DrawnC.dc.html): "Dec 1 – Jan 6"."""
        self.assertEqual(R.dates_of("christmas", 2026), "Dec 1 – Jan 6")
        self.assertEqual(R.dates_of("halloween", 2026), "Oct 24 – Nov 1")
        self.assertEqual(R.dates_of("july4", 2026), "Jul 3 – 5")
        self.assertEqual(R.dates_of("easter", 2026), "Apr 4 – 6")     # Easter Sunday 2026 is April 5
        self.assertEqual(R.dates_of("easter", 2027), "Mar 27 – 29")   # and 2027's is March 28
        self.assertIsNone(R.dates_of(None, 2026))

    def test_the_dates(self):
        on = R.occasion_on
        self.assertEqual(on(date(2026, 10, 23)), None)
        self.assertEqual(on(date(2026, 10, 24)), "halloween")
        self.assertEqual(on(date(2026, 11, 1)), "halloween")
        self.assertEqual(on(date(2026, 11, 2)), None)
        self.assertEqual(on(date(2026, 12, 1)), "christmas")
        self.assertEqual(on(date(2027, 1, 6)), "christmas")
        self.assertEqual(on(date(2027, 1, 7)), None)
        self.assertEqual(on(date(2026, 7, 4)), "july4")
        self.assertEqual(on(date(2026, 7, 6)), None)

    def test_easter_is_its_weekend_saturday_to_monday(self):
        self.assertEqual(R.easter(2026), date(2026, 4, 5))
        self.assertEqual(R.easter(2027), date(2027, 3, 28))
        self.assertEqual([R.occasion_on(date(2026, 4, d)) for d in (3, 4, 5, 6, 7)],
                         [None, "easter", "easter", "easter", None])

    def test_each_owns_its_motion_in_emitter_colors(self):
        """Christmas chases red and green; Halloween is unsteady like embers; Easter drifts; July 4th
        twinkles. The colors are the boards' LED values, never the panel's pastels."""
        self.assertEqual(R.look_of("christmas")["motion"], "chase")
        self.assertEqual(R.look_of("christmas")["colors"], [[255, 45, 36], [20, 216, 96]])
        self.assertEqual(R.look_of("halloween")["motion"], "flicker")
        self.assertEqual(R.look_of("halloween")["colors"], [[255, 116, 16], [255, 116, 16], [154, 69, 255]])
        self.assertEqual(R.look_of("easter")["motion"], "drift")
        self.assertEqual(R.look_of("july4")["motion"], "twinkle")
        for occ in R.OCCASIONS:
            for c in R.look_of(occ)["colors"]:
                self.assertNotEqual(c, [233, 184, 114], "the panel's --lamp on an LED")

    def test_hold_it_still_is_the_one_control(self):
        held = R.look_of("christmas", still=True)
        self.assertEqual((held["motion"], held["colors"]), ("still", R.look_of("christmas")["colors"]))
        self.assertGreaterEqual(held["block"], 3)

    def test_strips_inside_stay_still(self):
        self.assertEqual(R.look_of("halloween", outside=False)["motion"], "still")

    def test_no_occasion_is_the_households_own_light(self):
        self.assertEqual(R.look_of(None), {"motion": "off"})


class WhereEachRunSits(unittest.TestCase):
    """Each box draws its own frames from where its runs sit along the roof and which way each goes."""

    parts = [{"chip": "a", "run": 1, "count": 100}, {"chip": "b", "run": 1, "count": 60},
             {"chip": "b", "run": 2, "count": 40}, {"chip": "c", "run": 1, "count": 80}]

    def test_with_no_order_every_run_goes_away_from_its_own_box(self):
        lay = R.layout(self.parts, None)
        self.assertEqual(lay["b"], [{"at": 0, "dir": 1}, {"at": 0, "dir": 1}])

    def test_with_an_order_runs_are_laid_end_to_end(self):
        order = [{"chip": "a", "run": 1, "dir": 1}, {"chip": "b", "run": 2, "dir": -1},
                 {"chip": "b", "run": 1, "dir": 1}, {"chip": "c", "run": 1, "dir": -1}]
        lay = R.layout(self.parts, order)
        self.assertEqual(lay["a"][0], {"at": 0, "dir": 1})
        # b's second run goes against the way round: its first light is the far end, at 100+40-1
        self.assertEqual(lay["b"][1], {"at": 139, "dir": -1})
        self.assertEqual(lay["b"][0], {"at": 140, "dir": 1})
        self.assertEqual(lay["c"][0], {"at": 279, "dir": -1})
        # and every light of the roof has exactly one place: no seam, no overlap
        seen = []
        for p in self.parts:
            run_ = lay[p["chip"]][p["run"] - 1]
            seen += [run_["at"] + run_["dir"] * k for k in range(p["count"])]
        self.assertEqual(sorted(seen), list(range(280)))

    def test_the_guess_is_the_order_the_boxes_were_set_up(self):
        self.assertEqual([(g["chip"], g["run"], g["dir"]) for g in R.guess(self.parts)],
                         [("a", 1, 1), ("b", 1, 1), ("b", 2, 1), ("c", 1, 1)])


class OneLightOnTheWall(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = House(self.tmp.name)
        self.a = self.h.box("a", "hwA")
        self.b = self.h.box("b", "hwB", run2=40)

    def tearDown(self): self.tmp.cleanup()

    def test_a_second_box_is_folded_into_the_first_ones_tile(self):
        self.h.roofline.begin("a", "hwA")
        self.h.roofline.join("b", "hwB", "Garage end")
        self.assertEqual(self.h.home.folded, {"hwB": "hwA"})
        self.assertEqual(self.h.roofline.lead().id, self.a.id)
        self.assertEqual([d.id for d in self.h.roofline.members(self.a.id)], [self.b.id])
        self.assertGreater(self.h.rebuilt, 0)

    def test_and_the_house_leaves_it_out_of_its_room(self):
        home = Home()
        home.folded = {"hwB": "hwA"}
        areas = [{"area_id": "outside", "name": "Outside"}]
        devs = [{"id": "hwA", "area_id": "outside"}, {"id": "hwB", "area_id": "outside"}]
        ents = [{"entity_id": "light.a", "device_id": "hwA"}, {"entity_id": "light.b", "device_id": "hwB"}]
        states = [{"entity_id": "light.a", "state": "on", "attributes": {}}, {"entity_id": "light.b", "state": "on", "attributes": {}}]
        home.build(areas, devs, ents, states)
        self.assertEqual([d.id for d in home.rooms["outside"].devices], ["light.a"])
        self.assertIn("light.b", home.devices)       # still a device: a tap on the roof reaches it

    def test_forgetting_a_box_takes_it_out_of_the_roofline_and_nothing_else(self):
        self.h.roofline.begin("a", "hwA")
        self.h.roofline.join("b", "hwB")
        run(self.h.strip.forget("b"))
        self.assertEqual(self.h.roofline.chips(), ["a"])
        self.assertEqual(self.h.home.folded, {})

    def test_boxes_are_named_by_where_they_are(self):
        self.h.roofline.begin("a", "hwA", "Left corner")
        self.h.roofline.join("b", "hwB", "Garage end")
        self.assertEqual([b["place"] for b in self.h.roofline.status()["boxes"]], ["Left corner", "Garage end"])
        self.h.roofline.rename("b", "Right of the door")
        self.assertEqual(self.h.roofline.status()["boxes"][1]["place"], "Right of the door")

    def test_a_dark_box_says_which_part_and_why_never_unavailable(self):
        from tests.test_controller import power
        self.h.roofline.begin("a", "hwA", "Left corner")
        self.h.roofline.join("b", "hwB", "Garage end")
        self.h.strip.strips["b"]["power"] = power()
        boxes = self.h.roofline.status()["boxes"]
        self.assertEqual(boxes[0]["state"], "Fine")
        self.assertEqual(boxes[1]["state"], "Dark")
        self.assertIn("Plug the 12 V supply back in", boxes[1]["sub"])
        self.assertNotIn("unavailable", json.dumps(boxes))

    def test_a_dark_box_says_which_of_its_runs_are_dark(self):
        """The pane draws a dark run dark where it is (design/roofline/DrawnC.dc.html), so a box with two
        runs says which one the controller is holding."""
        from tests.test_controller import power, run1
        self.h.roofline.begin("a", "hwA", "Left corner")
        self.h.roofline.join("b", "hwB", "Right of the door")
        self.h.strip.strips["b"]["power"] = power(runs=[run1(), run1(on=False, held="supply")])
        dark = self.h.roofline.status()["boxes"][1]
        self.assertEqual((dark["state"], dark["dark_runs"]), ("Dark", [2]))
        self.assertNotIn("dark_runs", self.h.roofline.status()["boxes"][0])

    def test_the_pane_is_told_each_runs_length_in_the_order_they_were_set_up(self):
        """Each run drawn as long as its lights: the same counts the boxes are sent their places from."""
        self.h.roofline.begin("a", "hwA", "Left corner")
        self.h.roofline.join("b", "hwB", "Right of the door")
        self.assertEqual(self.h.roofline.status()["parts"],
                         [{"chip": "a", "run": 1, "count": 150}, {"chip": "b", "run": 1, "count": 150}, {"chip": "b", "run": 2, "count": 40}])


class TheWayRound(unittest.TestCase):
    """C until a chase is wanted, then A in the yard, pre-filled with B's guess."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = House(self.tmp.name)
        self.h.box("a", "hwA", 100); self.h.box("b", "hwB", 60, run2=40)
        self.h.roofline.begin("a", "hwA"); self.h.roofline.join("b", "hwB")

    def tearDown(self): self.tmp.cleanup()

    def test_it_is_never_asked_until_a_chase_is_wanted(self):
        self.h.roofline.look = lambda today=None: R.look_of("halloween")
        self.assertFalse(self.h.roofline.wants_order())
        self.h.roofline.look = lambda today=None: R.look_of("christmas")
        self.assertTrue(self.h.roofline.wants_order())

    def test_held_still_a_chase_is_not_wanted(self):
        self.h.roofline.hold_still(True)
        self.h.roofline.showing = lambda today=None: "christmas"
        self.assertFalse(self.h.roofline.wants_order())

    def test_the_yard_starts_from_the_guess_with_every_run_its_own_color(self):
        y = run(self.h.roofline.yard_begin())
        self.assertEqual([r["name"] for r in y["rows"]], ["Red", "Blue", "Green"])
        self.assertEqual([r["nth"] for r in y["rows"]], [0, 1, 2])
        self.assertTrue(y["all"])
        sent = self.h.looks()
        self.assertEqual(sent["a"]["motion"], "head")
        self.assertEqual(sent["b"]["runs"][1]["rgb"], list(R.LED["green"]))

    def test_tapped_again_turns_one_round(self):
        run(self.h.roofline.yard_begin())
        y = run(self.h.roofline.yard_tap("b", 2))
        self.assertTrue(next(r for r in y["rows"] if (r["chip"], r["run"]) == ("b", 2))["turned"])

    def test_start_again_taps_in_order_then_one_light_goes_round_and_it_is_kept(self):
        run(self.h.roofline.yard_begin())
        run(self.h.roofline.yard_again())
        for chip, run_ in (("b", 2), ("a", 1), ("b", 1)): run(self.h.roofline.yard_tap(chip, run_))
        run(self.h.roofline.yard_done())
        self.assertEqual(self.h.looks()["a"]["id"], "round")
        self.h.roofline.yard_keep()
        order = self.h.roofline.status()["order"]
        self.assertEqual([(o["chip"], o["run"]) for o in order], [("b", 2), ("a", 1), ("b", 1)])

    def test_done_before_every_color_is_tapped_is_refused(self):
        run(self.h.roofline.yard_begin()); run(self.h.roofline.yard_again())
        run(self.h.roofline.yard_tap("a", 1))
        with self.assertRaises(ValueError): run(self.h.roofline.yard_done())

    def test_a_new_box_puts_the_way_round_back_to_unknown(self):
        run(self.h.roofline.yard_begin()); run(self.h.roofline.yard_done()); self.h.roofline.yard_keep()
        self.h.box("c", "hwC")
        self.h.roofline.join("c", "hwC")
        self.assertIsNone(self.h.roofline.status()["order"])


class Evenings(unittest.TestCase):
    """B: like a porch light. On at dusk, off at the end; an occasion decides only how it looks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = House(self.tmp.name)
        self.lead = self.h.box("a", "hwA")
        self.h.roofline.begin("a", "hwA")

    def tearDown(self): self.tmp.cleanup()

    def at(self, y, m, d, hh, mm): return datetime(y, m, d, hh, mm, tzinfo=TZ)

    def test_dusk_is_a_little_after_sunset(self):
        dusk = self.h.roofline.dusk(date(2026, 10, 24))
        self.assertEqual((dusk.hour, dusk.minute // 10), (18, 3))     # about 6:3x PM, as the board drew 6:41

    def test_every_evening_on_at_dusk_off_at_eleven(self):
        self.h.roofline.set_evenings("every")
        self.assertIsNone(run(self.h.roofline.tick(self.at(2026, 7, 9, 18, 0))))
        self.assertEqual(run(self.h.roofline.tick(self.at(2026, 7, 9, 21, 15))), "on")
        self.assertIsNone(run(self.h.roofline.tick(self.at(2026, 7, 9, 21, 45))))       # once, not every tick
        self.assertEqual(run(self.h.roofline.tick(self.at(2026, 7, 9, 23, 1))), "off")
        self.assertEqual([a[2] for a in self.h.acts], ["evenings", "evenings"])

    def test_a_household_that_switches_it_off_at_nine_has_switched_it_off(self):
        self.h.roofline.set_evenings("every")
        run(self.h.roofline.tick(self.at(2026, 7, 9, 21, 15)))
        self.lead.state = "off"
        self.assertIsNone(run(self.h.roofline.tick(self.at(2026, 7, 9, 21, 30))))

    def test_only_in_an_occasion_is_dark_in_july_and_lit_at_halloween(self):
        self.h.roofline.set_evenings("occasion")
        self.assertIsNone(run(self.h.roofline.tick(self.at(2026, 7, 9, 21, 15))))
        self.assertEqual(run(self.h.roofline.tick(self.at(2026, 10, 24, 18, 50))), "on")

    def test_not_by_itself_never_turns_anything_on(self):
        self.h.roofline.set_evenings("never")
        for when in (self.at(2026, 10, 24, 18, 50), self.at(2026, 12, 20, 18, 0)):
            self.assertIsNone(run(self.h.roofline.tick(when)))
        self.assertEqual(self.h.acts, [])

    def test_an_occasion_turns_nothing_on_by_itself(self):
        """The rule stays whole: at Christmas, with no evenings asked for, the roof stays dark."""
        self.assertIsNone(self.h.roofline.data.get("evenings"))
        self.assertIsNone(run(self.h.roofline.tick(self.at(2026, 12, 19, 18, 52))))
        self.assertEqual(self.h.acts, [])

    def test_at_three_in_the_morning_in_december_the_house_is_dark(self):
        self.h.roofline.set_evenings("every")
        run(self.h.roofline.tick(self.at(2026, 12, 19, 18, 0)))
        run(self.h.roofline.tick(self.at(2026, 12, 19, 23, 5)))
        self.assertIsNone(run(self.h.roofline.tick(self.at(2026, 12, 20, 3, 5))))
        self.assertEqual(self.lead.state, "off")

    def test_an_end_after_midnight_is_after_midnight(self):
        self.h.roofline.set_evenings("every", "01:00")
        run(self.h.roofline.tick(self.at(2026, 7, 9, 21, 15)))
        self.assertIsNone(run(self.h.roofline.tick(self.at(2026, 7, 9, 23, 30))))
        self.assertEqual(run(self.h.roofline.tick(self.at(2026, 7, 10, 1, 1))), "off")

    def test_why_is_it_on_has_one_sentence(self):
        self.h.roofline.set_evenings("every")
        self.assertEqual(self.h.roofline.why(self.at(2026, 10, 24, 18, 50), True),
                         "On at dusk because it keeps evenings. Halloween is on in the house, so that is how it looks.")
        self.assertIn("everyday warm white", self.h.roofline.why(self.at(2026, 7, 9, 21, 15), True))
        self.assertEqual(self.h.roofline.why(self.at(2026, 10, 24, 23, 20), False), "Off at 11 PM, the end of its evenings.")
        self.h.roofline.set_evenings("occasion")
        self.assertEqual(self.h.roofline.why(self.at(2026, 7, 9, 21, 15), False),
                         "No occasion tonight, and its evenings are only for occasions.")

    def test_the_look_goes_to_every_box_with_the_hubs_clock(self):
        self.h.box("b", "hwB"); self.h.roofline.join("b", "hwB")
        self.h.roofline.showing = lambda today=None: "christmas"
        run(self.h.roofline.send_looks())
        sent = self.h.looks()
        self.assertEqual(set(sent), {"a", "b"})
        self.assertEqual(sent["a"]["motion"], "chase")
        self.assertEqual(sent["a"]["t0"], 0)
        self.assertLess(abs(sent["a"]["now"] - time.time() * 1000), 5000)

    def test_and_is_said_only_when_it_changes(self):
        self.h.roofline.showing = lambda today=None: "halloween"
        self.h.roofline.hold_still(True)
        run(self.h.roofline.send_looks()); n = len(self.h.ha.published)
        run(self.h.roofline.send_looks())
        self.assertEqual(len(self.h.ha.published), n)


class ALookSaid(unittest.IsolatedAsyncioTestCase):
    """C: a fixed grammar, no model. It plays on the roof before it is kept."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = House(self.tmp.name)
        self.h.box("a", "hwA")
        self.h.roofline.begin("a", "hwA")
        self.h.commands = Commands(self.h)
        self.h.commands._log = lambda *a, **k: None

    def tearDown(self): self.tmp.cleanup()

    def test_the_grammar(self):
        self.assertEqual(read_look("christmas red and green chasing"), ("christmas", ["red", "green"], "chase", False))
        self.assertEqual(read_look("make the roofline red and white twinkling quickly for christmas"),
                         ("christmas", ["red", "white"], "twinkle", True))
        self.assertEqual(read_look("halloween orange and purple flickering"), ("halloween", ["orange", "purple"], "flicker", False))
        self.assertEqual(read_look("4th of july red white and blue twinkling"), ("july4", ["red", "white", "blue"], "twinkle", False))
        self.assertEqual(read_look("warm white still"), (None, ["warm"], "still", False))

    def test_it_never_takes_a_sentence_meant_for_something_else(self):
        for s in ("kitchen lights red", "red", "turn the porch light on", "movie in the den", "chasing"):
            self.assertIsNone(read_look(s), s)

    def test_a_motion_it_does_not_have_is_answered_with_the_five_it_has(self):
        with self.assertRaises(NotUnderstood) as e: read_look("christmas red and green meteor")
        self.assertIn("still, drifting, flickering, chasing or twinkling", str(e.exception))

    async def test_it_plays_on_the_roof_as_a_draft_and_is_kept_only_when_told(self):
        out = await self.h.commands.say("Christmas: red and white, twinkling")
        self.assertEqual(out["kind"], "look")
        self.assertEqual((out["occasion"], out["motion"], out["words"]), ("christmas", "twinkle", "Red and white, twinkling slowly"))
        sent = self.h.looks()["a"]
        self.assertEqual((sent["motion"], sent["colors"]), ("twinkle", [list(R.LED["red"]), list(R.LED["white"])]))
        self.assertEqual(self.h.roofline.data.get("looks"), {})
        self.h.roofline.keep_draft()
        self.assertEqual(self.h.roofline.data["looks"]["christmas"]["motion"], "twinkle")

    async def test_walking_away_puts_the_roof_back(self):
        await self.h.commands.say("christmas red and white twinkling")
        self.h.roofline._draft_until = time.time() - 1
        self.h.roofline.showing = lambda today=None: None
        await self.h.roofline.send_looks()
        self.assertEqual(self.h.looks()["a"]["motion"], "off")

    async def test_not_this_puts_it_back_at_once(self):
        await self.h.commands.say("christmas red and white twinkling")
        self.h.roofline.drop_draft()
        self.assertIsNone(self.h.roofline.status()["draft"])

    async def test_a_house_with_no_roofline_says_so(self):
        self.h.settings.set(roofline={})
        with self.assertRaises(NotUnderstood) as e: await self.h.commands.say("christmas red and green chasing")
        self.assertIn("no roofline", str(e.exception))

    def test_a_kept_look_replaces_ours_for_that_occasion_only(self):
        self.h.roofline.draft("christmas", R.said_look(["red", "white"], "twinkle"))
        self.h.roofline.keep_draft()
        self.assertEqual(self.h.roofline.look(date(2026, 12, 19))["motion"], "twinkle")
        self.assertEqual(self.h.roofline.look(date(2026, 10, 30))["motion"], "flicker")
        self.assertEqual(self.h.roofline.words("christmas", {}), "Red and white, twinkling slowly")
        self.h.roofline.forget_look("christmas")
        self.assertEqual(self.h.roofline.look(date(2026, 12, 19))["motion"], "chase")


class TheLastBeatsOutside(unittest.TestCase):
    """A light that is outside is asked its evenings once (B), or whether it is more of the Roofline."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.h = House(self.tmp.name)
        self.h.ha.devices = [{"id": "hwA", "identifiers": [["mqtt", "strip_a"]]},
                             {"id": "hwB", "identifiers": [["mqtt", "strip_b"]]}]

    def tearDown(self): self.tmp.cleanup()

    def placed(self, chip):
        self.h.strip.job = {"state": "room", "id": chip, "label": "A light strip", "first": None}
        return run(self.h.strip.put("outside"))

    def test_the_first_outside_strip_is_the_roofline_and_is_asked_its_evenings(self):
        st = self.placed("a")
        self.assertEqual(st["state"], "evenings")
        self.assertEqual(self.h.roofline.chips(), ["a"])
        st = run(self.h.strip.evenings("every"))
        self.assertEqual(st["state"], "ready")
        self.assertEqual(self.h.roofline.data["evenings"], "every")

    def test_the_next_is_asked_if_it_is_more_of_the_roofline(self):
        self.placed("a"); run(self.h.strip.evenings("occasion"))
        st = self.placed("b")
        self.assertEqual(st["state"], "roofline")
        run(self.h.strip.more_of_the_roofline(True, "Garage end"))
        self.assertEqual(self.h.roofline.chips(), ["a", "b"])

    def test_a_light_of_its_own_stays_a_light_of_its_own(self):
        self.placed("a"); run(self.h.strip.evenings("every"))
        self.placed("b")
        self.assertEqual(run(self.h.strip.more_of_the_roofline(False))["state"], "ready")
        self.assertEqual(self.h.roofline.chips(), ["a"])

    def test_a_strip_inside_is_asked_neither(self):
        self.h.home.rooms["den"] = Room("den", "Den")
        self.h.strip.job = {"state": "room", "id": "a", "label": "A light strip", "first": None}
        self.assertEqual(run(self.h.strip.put("den"))["state"], "ready")
        self.assertFalse(self.h.roofline.exists())

    def test_outside_is_read_from_the_households_own_room_names(self):
        for name in ("Outside", "Front porch", "Back yard", "Roofline", "Patio"):
            self.assertTrue(R.is_outside(name), name)
        for name in ("Front room", "Kitchen", "Garage", "Living room", None):
            self.assertFalse(R.is_outside(name), name)


if __name__ == "__main__":
    unittest.main()
