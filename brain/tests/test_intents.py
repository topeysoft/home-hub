"""The scene table: what each room state means, and the one place capability actions become HA services.

The table has two lives — the defaults compiled in, and ../scenes.json, which is what a hub actually
runs and what a person may edit. Both are checked, and each test says which one it is looking at,
because a test that reads whichever file happens to be on disk is not a test.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock

from hub import intents
from hub.intents import SERVICE, RoomState, plan
from hub.model import Device, Room


def room(*devices):
    r = Room("living", "Living room")
    r.devices = list(devices)
    return r


class TableTest(unittest.TestCase):
    """Points the scene table at one known file for the length of a test, rather than at whatever
    the developer's data directory holds."""
    path = None            # None means: nothing on disk, so the compiled-in defaults apply

    def setUp(self):
        p = mock.patch.object(intents, "RULES_PATH", self.path or Path(tempfile.mkdtemp()) / "absent.json")
        p.start(); self.addCleanup(p.stop)
        intents._rules["mtime"] = None      # the table caches on mtime; make it read again
        self.addCleanup(intents._rules.update, {"mtime": None})


class ServiceTableTests(unittest.TestCase):
    def test_every_action_maps_onto_a_real_home_assistant_domain_and_service(self):
        domains = {"light", "switch", "media_player", "fan", "cover", "lock", "climate"}
        for (cap, action), (domain, service) in SERVICE.items():
            with self.subTest(cap=cap, action=action):
                self.assertIn(domain, domains)
                self.assertTrue(service.islower() and " " not in service)

    def test_everything_that_can_be_switched_can_be_switched_both_ways(self):
        for cap in ("light", "switch", "media", "fan"):
            with self.subTest(cap=cap):
                self.assertIn((cap, "on"), SERVICE)
                self.assertIn((cap, "off"), SERVICE)

    def test_a_door_can_be_locked_and_unlocked_and_a_blind_opened_and_closed(self):
        for key in (("lock", "lock"), ("lock", "unlock"), ("cover", "open"), ("cover", "close")):
            with self.subTest(key=key): self.assertIn(key, SERVICE)


class DefaultTableTests(TableTest):
    """With no scenes.json at all — a hub whose data volume is empty, or whose file went missing."""

    def test_the_house_still_has_a_scene_for_every_state_it_can_be_in(self):
        self.assertEqual(set(intents.rules()), set(RoomState))

    def test_a_room_going_to_sleep_turns_its_lights_off_and_locks_its_door(self):
        r = room(Device("light.a", "A", "living", "light", "on"),
                 Device("lock.front", "Front", "living", "lock", "unlocked"))
        calls = plan(r, RoomState.asleep)
        self.assertIn(("light", "turn_off", "light.a", {}), calls)
        self.assertIn(("lock", "lock", "lock.front", {}), calls)

    def test_a_room_nobody_is_in_is_not_locked_up_the_way_an_empty_house_is(self):
        r = room(Device("switch.k", "Kettle", "living", "switch", "on"))
        self.assertEqual(plan(r, RoomState.empty), [])              # empty leaves switches alone
        self.assertIn(("switch", "turn_off", "switch.k", {}), plan(r, RoomState.away))

    def test_movie_dims_rather_than_switches_off(self):
        r = room(Device("light.a", "A", "living", "light", "on"))
        self.assertEqual(plan(r, RoomState.movie), [("light", "turn_on", "light.a", {"brightness_pct": 15})])

    def test_a_room_with_nothing_in_it_plans_nothing(self):
        self.assertEqual(plan(room(), RoomState.away), [])

    def test_a_sensor_is_never_something_a_scene_acts_on(self):
        r = room(Device("sensor.t", "Temp", "living", "sensor.temperature", "70"),
                 Device("binary_sensor.m", "Motion", "living", "motion", "off"))
        for state in RoomState:
            with self.subTest(state=state):
                self.assertEqual(plan(r, state), [])


class ShippedTableTests(TableTest):
    """../scenes.json: what a new hub copies into its data volume and runs from day one."""
    path = intents.SEED

    def test_the_file_the_product_ships_covers_every_state_a_room_can_be_in(self):
        self.assertEqual(set(intents.rules()), set(RoomState))

    def test_every_scene_it_defines_is_something_the_house_can_actually_do(self):
        for state, actions in intents.rules().items():
            for cap, action, data in actions:
                with self.subTest(state=state, cap=cap, action=action):
                    self.assertIn((cap, action), SERVICE)
                    self.assertIsInstance(data, dict)

    def test_walking_into_a_room_puts_its_lights_on(self):
        r = room(Device("light.a", "A", "living", "light", "off"))
        self.assertEqual(plan(r, RoomState.occupied), [("light", "turn_on", "light.a", {})])

    def test_a_hand_set_room_holds_the_rules_off_for_a_while(self):
        holds = intents.holds()
        self.assertGreater(holds["movie"], holds["occupied"])       # a film outlasts a visit
        self.assertEqual(holds["asleep"], 0)                        # released by a rule, not by a clock
        self.assertEqual(holds["away"], 0)

    def test_the_table_the_panel_gets_is_plain_data_it_can_match_a_room_against(self):
        data = intents.rules_as_data()
        self.assertEqual(set(data), {s.value for s in RoomState})
        json.dumps(data)                                             # it has to survive the wire


class BadFileTests(TableTest):
    def test_a_scenes_file_that_got_mangled_leaves_the_last_good_rules_running(self):
        # Scenes are editable by hand. A bad edit must not take the house's lights with it.
        bad = Path(tempfile.mkdtemp()) / "scenes.json"
        bad.write_text("{oops")
        with mock.patch.object(intents, "RULES_PATH", bad):
            intents._rules["mtime"] = None
            self.assertEqual(set(intents.rules()), set(RoomState))

    def test_a_scene_naming_a_state_the_house_has_no_word_for_does_not_take_the_rest_down(self):
        odd = Path(tempfile.mkdtemp()) / "scenes.json"
        odd.write_text(json.dumps({"asleep": [["light", "off", {}]], "dancing": [["light", "on", {}]]}))
        with mock.patch.object(intents, "RULES_PATH", odd):
            intents._rules["mtime"] = None
            self.assertEqual(set(intents.rules()), set(RoomState))
            self.assertNotIn("dancing", [s.value for s in intents.rules()])


if __name__ == "__main__":
    unittest.main()
