"""What a thing IS, when the house has it wrong: docs/kinds.md.

A lamp on a smart plug is a switch as far as the driver is concerned, and Home Assistant is not wrong --
it is a switch. It is also, in the only sense the person living there cares about, a light, and until
they can say so "kitchen lights off" does not touch it and Good night walks past it.

Almost every test here is about the word ONLY in the sentence that makes the feature safe: a person may
say what a thing IS, and may not say what it CAN DO. Two of the three places that must keep reading
`capability` fail SILENTLY when they are changed by accident -- the scene runs, the lamp does not move,
and nobody is told -- so each of them is held down by a test of its own.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json, unittest

from hub import intents
from hub.intents import RoomState, plan
from hub.model import Device, Room, kind_of, kinds_for
from tests.apptest import ApiTest, house


class OfferTests(unittest.TestCase):
    """What may be offered is computed from what the thing can already serve, never typed in."""

    def test_anything_that_switches_on_and_off_may_be_shown_as_anything_else_that_does(self):
        for cap in ("switch", "light", "fan"):
            with self.subTest(cap=cap):
                self.assertEqual(sorted(kinds_for(cap)), ["alarm", "fan", "light", "switch"])

    def test_a_kind_wanting_a_position_a_temperature_or_a_volume_is_never_on_offer(self):
        # This is the rule that stops the panel drawing a brightness slider onto something that cannot dim.
        for cap in ("climate", "media", "cover", "vacuum", "camera"):
            with self.subTest(cap=cap):
                self.assertNotIn("light", kinds_for(cap))

    def test_a_reading_is_not_a_thing_to_re_type(self):
        for cap in ("sensor.temperature", "sensor.illuminance", "motion", "contact"):
            with self.subTest(cap=cap): self.assertEqual(kinds_for(cap), [])

    def test_a_thing_with_no_choice_to_make_offers_nothing_rather_than_a_menu_of_one(self):
        for cap in ("climate", "media", "vacuum", "camera"):
            with self.subTest(cap=cap): self.assertEqual(kinds_for(cap), [])

    def test_a_lock_and_a_garage_door_are_refused_both_ways(self):
        # docs/voice.md gates opening and unlocking by direction. Re-typing is not a way round that gate.
        self.assertEqual(kinds_for("lock"), [])
        self.assertEqual(kinds_for("cover"), [])
        for cap in ("switch", "light", "fan", "media", "climate", "camera", "vacuum"):
            with self.subTest(cap=cap):
                self.assertNotIn("lock", kinds_for(cap))
                self.assertNotIn("cover", kinds_for(cap))


class ScenePlanTests(unittest.TestCase):
    """The one that would be found last. Selecting the device reads the override; building the call must
    not, and both lines used to be the same `if`."""

    def setUp(self):
        intents._rules.update(mtime=object(), actions=intents.DEFAULT_ACTIONS, hold=intents.DEFAULT_HOLD)
        self.addCleanup(intents._rules.update, {"mtime": None})

    def room(self, *devices):
        r = Room("living", "Living room"); r.devices = list(devices); return r

    def test_a_plug_shown_as_a_light_joins_good_night_and_is_switched_off_as_a_switch(self):
        lamp = Device("switch.porch_lamp", "Porch lamp", "living", "switch", "on", kind="light")
        calls = plan(self.room(lamp), RoomState.asleep)
        self.assertIn(("switch", "turn_off", "switch.porch_lamp", {}), calls)
        self.assertNotIn("light", [c[0] for c in calls])   # light.turn_off on a switch entity is refused by HA

    def test_a_plug_left_as_a_plug_is_not_swept_up_by_the_lights(self):
        kettle = Device("switch.kettle", "Kettle", "living", "switch", "on")
        self.assertEqual(plan(self.room(kettle), RoomState.asleep), [])

    def test_what_a_scene_asks_for_goes_with_the_kind_it_was_written_for(self):
        # Movie dims the lights to 15%. A plug has no 15%, and a brightness sent to switch.turn_on is
        # refused outright -- so the lamp gets the part it can do, which is coming on.
        lamp = Device("switch.porch_lamp", "Porch lamp", "living", "switch", "off", kind="light")
        bulb = Device("light.ceiling", "Ceiling", "living", "light", "off")
        calls = plan(self.room(lamp, bulb), RoomState.movie)
        self.assertIn(("switch", "turn_on", "switch.porch_lamp", {}), calls)
        self.assertIn(("light", "turn_on", "light.ceiling", {"brightness_pct": 15}), calls)


class StoredTests(ApiTest):
    """Where the override lives, and what it survives."""

    def plug(self):
        return self.hub.home.devices["switch.kettle"]

    def test_the_panel_is_told_what_may_be_offered_and_why_the_list_is_short(self):
        r = self.client.get("/devices/switch.kettle/kinds").json()
        self.assertEqual(sorted(r["offer"]), ["alarm", "fan", "light", "switch"])
        self.assertEqual(r["kind"], "switch")
        self.assertIn("switched on and off", r["why"])
        self.assertEqual(r["words"]["switch"], "Plug")

    def test_a_thermostat_is_offered_nothing_at_all(self):
        r = self.client.get("/devices/climate.nest/kinds").json()
        self.assertEqual((r["offer"], r["why"]), ([], ""))

    def test_saying_what_a_thing_is_shows_up_on_the_device_and_on_the_home_the_panel_reads(self):
        self.assertEqual(self.client.post("/devices/switch.kettle/kind", json={"kind": "light"}).json()["kind"], "light")
        self.assertEqual(self.plug().kind, "light")
        rooms = {r["id"]: r for r in self.client.get("/home").json()["rooms"]}
        kettle = next(d for d in rooms["kitchen"]["devices"] if d["id"] == "switch.kettle")
        self.assertEqual((kettle["capability"], kettle["kind"]), ("switch", "light"))

    def test_the_panel_hears_about_it_at_once_rather_than_at_the_next_rebuild(self):
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})
        self.assertEqual(self.sent("device")[-1]["device"]["kind"], "light")

    def test_it_is_kept_with_the_rest_of_the_settings_so_a_restore_brings_it_back(self):
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})
        saved = json.loads((self.data / "settings.json").read_text())
        self.assertEqual(saved["kinds"], {"switch.kettle": "light"})

    def test_a_rebuild_does_not_forget_it(self):
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})
        self.hub.home.build(*house())        # what a registry change does: the whole model, made again
        self.assertEqual(self.plug().kind, "light")

    def test_saying_the_drivers_own_word_puts_it_back_and_leaves_no_record_behind(self):
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})
        self.client.post("/devices/switch.kettle/kind", json={"kind": "switch"})
        self.assertIsNone(self.plug().kind)
        self.assertEqual(json.loads((self.data / "settings.json").read_text())["kinds"], {})

    def test_an_empty_answer_clears_it_too(self):
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})
        self.client.post("/devices/switch.kettle/kind", json={"kind": None})
        self.assertIsNone(self.plug().kind)

    def test_a_kind_the_thing_cannot_serve_is_refused_in_the_houses_own_words(self):
        r = self.client.post("/devices/switch.kettle/kind", json={"kind": "climate"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("cannot be shown as", r.json()["detail"])

    def test_a_lock_may_not_be_re_typed_and_nothing_may_be_re_typed_into_one(self):
        self.assertEqual(self.client.post("/devices/lock.front/kind", json={"kind": "light"}).status_code, 400)
        self.assertEqual(self.client.post("/devices/switch.kettle/kind", json={"kind": "lock"}).status_code, 400)
        self.assertEqual(self.client.post("/devices/switch.kettle/kind", json={"kind": "cover"}).status_code, 400)
        self.assertEqual(self.client.get("/devices/lock.front/kinds").json()["offer"], [])

    def test_a_thing_the_house_has_never_heard_of_is_a_404_either_way(self):
        self.assertEqual(self.client.get("/devices/light.nowhere/kinds").status_code, 404)
        self.assertEqual(self.client.post("/devices/light.nowhere/kind", json={"kind": "switch"}).status_code, 404)

    def test_an_answer_the_new_hardware_can_no_longer_serve_stops_applying_without_being_thrown_away(self):
        # A plug pulled out and a thermostat put in its place. The owner's answer is kept -- it is theirs --
        # but a thermostat is not drawn as a lamp while it is standing there.
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})
        self.assertIsNone(self.hub.home.shown_as("switch.kettle", "climate"))
        self.assertEqual(self.hub.home.kinds["switch.kettle"], "light")
        self.assertEqual(self.hub.home.shown_as("switch.kettle", "switch"), "light")


class ServiceTests(ApiTest):
    """A person may say what a thing IS, and may not say what it CAN DO. The device would otherwise be
    left worse than mis-typed: untouchable, and the panel would have done it."""

    def setUp(self):
        super().setUp()
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})

    def test_a_tap_still_reaches_it_as_the_switch_it_really_is(self):
        self.client.post("/devices/switch.kettle/off")
        self.assertEqual(self.ha.called("switch", "turn_off", "switch.kettle"), [("switch", "turn_off", "switch.kettle", {})])
        self.assertEqual(self.ha.called("light"), [])

    def test_a_brightness_meant_for_the_lamp_it_is_shown_as_reaches_it_as_a_plain_on(self):
        self.client.post("/devices/switch.kettle/on", json={"brightness_pct": 30})
        self.assertEqual(self.ha.called("switch", "turn_on", "switch.kettle"), [("switch", "turn_on", "switch.kettle", {})])

    def test_it_can_still_be_put_on_a_timer_because_a_switch_has_a_real_off(self):
        self.assertEqual(self.client.post("/devices/switch.kettle/timer", json={"minutes": 20}).status_code, 200)


class GrammarTests(ApiTest):
    """The sentence this is all for. The house fixture's plug stands in for the lamp on a smart plug that
    is in a great many houses: a `switch` to the driver, and a light to everybody who lives there."""

    def setUp(self):
        super().setUp()
        # Put it where a lamp goes, and call it what a lamp is called. Nothing here touches its capability.
        plug = self.hub.home.devices["switch.kettle"]
        self.hub.home.rooms[plug.room_id].devices.remove(plug)
        plug.room_id, plug.name = "living", "Corner lamp"
        self.hub.home.rooms["living"].devices.append(plug)

    def shown_as_a_light(self):
        self.assertEqual(self.client.post("/devices/switch.kettle/kind", json={"kind": "light"}).status_code, 200)

    def test_a_lamp_on_a_plug_goes_off_when_somebody_says_living_room_lights_off(self):
        self.shown_as_a_light()
        self.assertEqual(self.client.post("/say", json={"text": "living room lights off"}).status_code, 200)
        self.assertEqual(self.ha.called("switch", "turn_off", "switch.kettle"),
                         [("switch", "turn_off", "switch.kettle", {})])
        self.assertEqual(self.ha.called("light", "turn_off", "light.ceiling"),
                         [("light", "turn_off", "light.ceiling", {})])

    def test_until_somebody_says_so_the_same_sentence_walks_straight_past_it(self):
        self.client.post("/say", json={"text": "living room lights off"})
        self.assertEqual(self.ha.called("switch", entity_id="switch.kettle"), [])
        self.assertEqual(len(self.ha.called("light", "turn_off")), 1)

    def test_dimming_the_lights_reaches_it_as_the_part_it_can_do(self):
        self.shown_as_a_light()
        self.client.post("/say", json={"text": "dim the living room lights"})
        self.assertEqual(self.ha.called("switch", "turn_on", "switch.kettle"),
                         [("switch", "turn_on", "switch.kettle", {})])      # a plug has no 30%
        self.assertEqual(self.ha.called("light", "turn_on", "light.ceiling"),
                         [("light", "turn_on", "light.ceiling", {"brightness_pct": 30})])

    def test_the_house_counts_it_when_asked_about_the_lights(self):
        self.hub.home.devices["switch.kettle"].state = "on"
        ask = lambda: self.client.post("/say", json={"text": "are the lights on?", "room": "living"}).json()["text"]
        self.assertEqual(ask(), "Ceiling light is on.")          # one light, and a plug the question walks past
        self.shown_as_a_light()
        self.assertEqual(ask(), "All 2 lights are on.")


class AlarmTests(ApiTest):
    """The kind that exists because of what a mistake costs.

    A siren reaches this house as a `switch` -- there is no siren in CAP_BY_DOMAIN and nothing in HA's
    domains says "this one is loud" -- so it got a plug's tile, which fires on one tap, and a plug's
    instrument, which offered to run it for an hour. The failure mode of a stray finger on a plug is a
    lamp. The failure mode of a stray finger on this one is a siren at 2am. Everything below is the
    house being told which of the two it is holding.

    The second tap itself lives in the panel (app/src/twice.ts, app/tests/twice.test.ts), the way the
    front door's does. What the brain owes is the rest: the kind on offer, the sweep stepping over it,
    the timer refused, and a grammar in which quiet is free and loud has to be asked for."""

    def setUp(self):
        super().setUp()
        siren = self.hub.home.devices["switch.kettle"]
        siren.name = "Siren"                                  # what it is, so the sentences below read as anybody would say them
        self.assertEqual(self.client.post("/devices/switch.kettle/kind", json={"kind": "alarm"}).status_code, 200)

    def say(self, text, **kw):
        return self.client.post("/say", json={"text": text, **kw}).json()

    def test_a_plug_may_be_shown_as_an_alarm_in_the_panels_own_word_for_it(self):
        r = self.client.get("/devices/switch.kettle/kinds").json()
        self.assertIn("alarm", r["offer"])
        self.assertEqual(r["words"]["alarm"], "Alarm")
        self.assertEqual(r["kind"], "alarm")

    def test_it_is_still_a_switch_to_the_driver_and_a_tap_reaches_it_as_one(self):
        self.client.post("/devices/switch.kettle/on")
        self.assertEqual(self.ha.called("switch", "turn_on", "switch.kettle"), [("switch", "turn_on", "switch.kettle", {})])
        self.assertEqual(self.ha.called("alarm"), [])

    def test_no_scene_sounds_it_and_no_scene_silences_it(self):
        # The omission in intents.DEFAULT_ACTIONS is the decision, and this is it written down. A great
        # many sirens put their ARMED state on this same switch, so Everything off sweeping it up with
        # the plugs would disarm the house every night, silently. Nor may a scene ever sound one.
        intents._rules.update(mtime=object(), actions=intents.DEFAULT_ACTIONS, hold=intents.DEFAULT_HOLD)
        self.addCleanup(intents._rules.update, {"mtime": None})
        siren = self.hub.home.devices["switch.kettle"]
        room = Room("kitchen", "Kitchen"); room.devices = [siren]
        for state in RoomState:
            with self.subTest(scene=state.value):
                self.assertEqual([c for c in plan(room, state) if c[2] == "switch.kettle"], [])

    def test_a_plug_that_is_left_a_plug_is_still_swept_up_by_everything_off(self):
        # The sweep is not weakened for everything else: this is the very behaviour being stepped over.
        intents._rules.update(mtime=object(), actions=intents.DEFAULT_ACTIONS, hold=intents.DEFAULT_HOLD)
        self.addCleanup(intents._rules.update, {"mtime": None})
        kettle = Device("switch.kettle2", "Kettle", "kitchen", "switch", "on")
        room = Room("kitchen", "Kitchen"); room.devices = [kettle]
        self.assertIn(("switch", "turn_off", "switch.kettle2", {}), plan(room, RoomState.away))

    def test_an_alarm_is_not_put_on_a_timer(self):
        # "On for thirty minutes" is a coffee maker. The same sentence about a siren is thirty minutes
        # of siren, and the plug's instrument offered it on a card beside the button, in one tap.
        r = self.client.post("/devices/switch.kettle/timer", json={"minutes": 30})
        self.assertEqual(r.status_code, 400)
        self.assertIn("alarm", r.json()["detail"])
        self.assertEqual(self.ha.called("switch", entity_id="switch.kettle"), [])

    def test_it_leaves_the_plug_bucket_so_turning_on_the_plugs_no_longer_reaches_it(self):
        self.say("kitchen plugs on")
        self.assertEqual(self.ha.called("switch", entity_id="switch.kettle"), [])

    def test_silencing_it_answers_to_every_word_anybody_would_use(self):
        for words in ("silence the alarm", "alarm off", "turn off the siren", "stop the alarm", "kitchen alarm off"):
            with self.subTest(said=words):
                self.ha.calls.clear()
                self.say(words, room="kitchen")
                self.assertEqual(self.ha.called("switch", "turn_off", "switch.kettle"),
                                 [("switch", "turn_off", "switch.kettle", {})])

    def test_sounding_it_needs_a_word_that_means_it(self):
        self.say("sound the alarm", room="kitchen")
        self.assertEqual(self.ha.called("switch", "turn_on", "switch.kettle"), [("switch", "turn_on", "switch.kettle", {})])

    def test_naming_it_and_nothing_else_does_not_set_it_off(self):
        # The generic on/off branch ends `or rest == ""`, so a bare "the alarm" used to mean turn it on.
        # That is this accident in the shape of a sentence, and the answer says what to say instead.
        r = self.client.post("/say", json={"text": "the alarm", "room": "kitchen"})
        self.assertEqual(self.ha.called("switch", entity_id="switch.kettle"), [])
        self.assertEqual(r.status_code, 422)                       # not understood, and deliberately so
        self.assertIn("silence", r.json()["detail"].lower())

    def test_the_house_says_it_is_sounding_rather_than_that_it_is_on(self):
        self.hub.home.devices["switch.kettle"].state = "on"
        self.assertIn("sounding", self.say("is the alarm on?", room="kitchen")["text"].lower())


if __name__ == "__main__":
    unittest.main()
