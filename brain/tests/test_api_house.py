"""The routes the panel leans on every second it is open: what the house is, and what a tap does to it.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json, unittest
from unittest import mock

from hub.lock import needs_code
from tests.apptest import ApiTest


class HouseTests(ApiTest):
    def test_home_is_rooms_with_their_devices_and_the_units_to_read_them_in(self):
        h = self.client.get("/home").json()
        self.assertEqual(h["temp_unit"], "°F")
        rooms = {r["id"]: r for r in h["rooms"]}
        self.assertEqual([d["name"] for d in rooms["front"]["devices"]], ["Front door"])
        ceiling = next(d for d in rooms["living"]["devices"] if d["id"] == "light.ceiling")
        self.assertEqual((ceiling["capability"], ceiling["state"], ceiling["attrs"]["brightness"]), ("light", "on", 200))

    def test_a_diagnostic_entity_never_reaches_a_room(self):
        # HA calls the TV's signal strength a temperature sensor. A room's tiles must not offer it.
        self.assertNotIn("sensor.tv_signal", self.hub.home.devices)
        self.assertNotIn("light.broken", self.hub.home.devices)      # disabled by its integration

    def test_a_room_with_nothing_in_it_is_still_a_room_but_an_empty_new_devices_is_not(self):
        h = self.client.get("/home").json()
        self.assertIn("unassigned", [r["id"] for r in h["rooms"]])   # the new lamp is in it
        self.hub.home.rooms["unassigned"].devices = []
        self.assertNotIn("unassigned", [r["id"] for r in self.client.get("/home").json()["rooms"]])

    def test_the_ambient_route_carries_the_location_the_panel_computes_the_sun_from(self):
        a = self.client.get("/ambient").json()
        self.assertEqual(a["location"]["lat"], 41.88)

    def test_scenes_are_data_the_panel_can_match_a_room_against(self):
        scenes = self.client.get("/scenes").json()
        self.assertIn("asleep", scenes)
        self.assertIn(["light", "off", {}], scenes["asleep"])


class NotReadyTests(ApiTest):
    ready = False       # the engine has not come up; the panel shows the starting screen

    def test_changing_the_house_before_the_engine_is_up_says_so_rather_than_failing_oddly(self):
        r = self.client.post("/rooms", json={"name": "Study"})
        self.assertEqual(r.status_code, 503)
        self.assertIn("starting", r.json()["detail"])

    def test_discovered_is_empty_rather_than_an_error_so_the_setup_screen_still_draws(self):
        self.assertEqual(self.client.get("/discovered").json(), [])


class DeviceActionTests(ApiTest):
    def test_turning_a_light_on_reaches_the_driver_as_the_service_that_domain_uses(self):
        r = self.client.post("/devices/light.kitchen/on", json={"brightness_pct": 40})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.ha.called("light", "turn_on", "light.kitchen"), [("light", "turn_on", "light.kitchen", {"brightness_pct": 40})])

    def test_a_tap_holds_the_room_off_the_rules_and_tells_every_screen(self):
        self.client.post("/devices/light.kitchen/on")
        self.assertGreater(self.hub.home.rooms["kitchen"].hold_until, 0)
        self.assertEqual(self.sent("intent")[-1]["room"], "kitchen")

    def test_an_action_a_thing_cannot_do_is_refused_before_the_driver_hears_about_it(self):
        r = self.client.post("/devices/lock.front/play")
        self.assertEqual(r.status_code, 400)
        self.assertIn("cannot play", r.json()["detail"])
        self.assertEqual(self.ha.calls, [])

    def test_an_unknown_device_is_a_404_not_a_crash(self):
        self.assertEqual(self.client.post("/devices/light.nowhere/on").status_code, 404)

    def test_every_action_a_tile_can_take_is_wired_to_a_real_service(self):
        # The tiles' vocabulary. If a capability loses its mapping the tile goes quiet, and nothing else would say so.
        for device, action in [("light.kitchen", "on"), ("light.kitchen", "off"), ("switch.kettle", "on"),
                               ("media_player.tv", "pause"), ("media_player.tv", "play"), ("media_player.tv", "next"),
                               ("fan.ceiling_fan", "on"), ("fan.ceiling_fan", "off"), ("lock.front", "unlock"),
                               ("lock.front", "lock"), ("climate.nest", "mode")]:
            with self.subTest(device=device, action=action):
                self.assertEqual(self.client.post(f"/devices/{device}/{action}", json={}).status_code, 200)

    def test_a_thermostats_fan_runs_for_a_while_and_is_clamped_to_something_sane(self):
        r = self.client.post("/devices/climate.nest/fan", json={"minutes": 9999})
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.json()["fan_until"])
        self.assertLessEqual(r.json()["fan_until"], __import__("time").time() + 720 * 60 + 1)

    def test_a_fan_on_something_with_no_fan_is_refused(self):
        self.assertEqual(self.client.post("/devices/light.kitchen/fan", json={"minutes": 5}).status_code, 400)


class RoomEditTests(ApiTest):
    def test_adding_a_room_that_already_exists_returns_the_one_there_rather_than_a_second(self):
        r = self.client.post("/rooms", json={"name": "kitchen"})       # same name, different case
        self.assertEqual(r.json()["id"], "kitchen")
        self.assertEqual(self.ha.sent, [])                              # the driver was never asked to make one

    def test_a_room_needs_a_name(self):
        self.assertEqual(self.client.post("/rooms", json={"name": "   "}).status_code, 400)

    def test_new_devices_is_not_a_room_a_person_may_rename_or_remove(self):
        self.assertEqual(self.client.post("/rooms/unassigned/rename", json={"name": "Attic"}).status_code, 404)
        self.assertEqual(self.client.delete("/rooms/unassigned").status_code, 404)

    def test_when_the_driver_refuses_the_panel_is_told_it_was_the_driver(self):
        self.ha.fail["config/area_registry/create"] = RuntimeError("area registry is busy")
        r = self.client.post("/rooms", json={"name": "Study"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("area registry is busy", r.json()["detail"])

    def test_moving_a_device_moves_the_hardware_so_its_other_parts_follow(self):
        r = self.client.post("/devices/light.ceiling/move", json={"room_id": "kitchen"})
        self.assertEqual(r.status_code, 200)
        self.assertIn(("config/device_registry/update", {"device_id": "hw-ceiling", "area_id": "kitchen"}), self.ha.sent)

    def test_moving_a_device_to_a_room_that_is_not_there_is_refused(self):
        self.assertEqual(self.client.post("/devices/light.ceiling/move", json={"room_id": "attic"}).status_code, 404)


class ForgettingTests(ApiTest):
    """Selling a camera, or pulling a bulb out of a lamp for good: the end of a device's life in the house.

    Until this there was no route that removed anything, and the only way was Home Assistant's own UI
    (docs/settings.md, step 2). What the house cannot do on its own it says plainly rather than in the
    engine's words.
    """

    def registry(self, *rows):
        self.ha.answers["config/device_registry/list"] = list(rows)

    def test_forgetting_a_thing_takes_it_off_whatever_brought_it(self):
        self.registry({"id": "hw-ceiling", "config_entries": ["entry-hw-ceiling"]})
        r = self.client.delete("/devices/light.ceiling")
        self.assertEqual(r.status_code, 200)
        self.assertIn(("config/device_registry/remove_config_entry_from_device",
                       {"device_id": "hw-ceiling", "config_entry_id": "entry-hw-ceiling"}), self.ha.sent)

    def test_a_thing_more_than_one_account_brought_is_taken_off_each(self):
        self.registry({"id": "hw-ceiling", "config_entries": ["entry-a", "entry-b"]})
        self.assertEqual(self.client.delete("/devices/light.ceiling").status_code, 200)
        off = [kw["config_entry_id"] for ty, kw in self.ha.sent if ty == "config/device_registry/remove_config_entry_from_device"]
        self.assertEqual(off, ["entry-a", "entry-b"])

    def test_a_thing_that_is_only_an_entry_goes_from_the_entity_registry(self):
        self.hub.home.devices["light.ceiling"].hw = None          # no hardware behind it: nothing to take it off
        self.assertEqual(self.client.delete("/devices/light.ceiling").status_code, 200)
        self.assertIn(("config/entity_registry/remove", {"entity_id": "light.ceiling"}), self.ha.sent)

    def test_what_will_not_go_on_its_own_says_so_in_the_houses_words(self):
        """HA lets an integration refuse. The person is told what to do about it, not what HA said."""
        self.registry({"id": "hw-ceiling", "config_entries": ["entry-hw-ceiling"]})
        self.ha.fail["config/device_registry/remove_config_entry_from_device"] = RuntimeError("Integration does not support device removal")
        r = self.client.delete("/devices/light.ceiling")
        self.assertEqual(r.status_code, 502)
        self.assertIn("Ceiling light", r.json()["detail"])
        self.assertIn("account that brought it", r.json()["detail"])
        self.assertNotIn("Integration does not support", r.json()["detail"])

    def test_a_thing_nothing_brought_is_not_quietly_left_alone(self):
        self.registry({"id": "hw-ceiling", "config_entries": []})
        self.assertEqual(self.client.delete("/devices/light.ceiling").status_code, 502)

    def test_forgetting_something_that_is_not_there(self):
        self.assertEqual(self.client.delete("/devices/light.nowhere").status_code, 404)

    def test_it_is_written_down(self):
        self.registry({"id": "hw-ceiling", "config_entries": ["entry-hw-ceiling"]})
        self.client.delete("/devices/light.ceiling")
        row = self.hub.log.recent(1, subject="light.ceiling")[0]
        self.assertEqual(row["new"], "forgotten")
        self.assertEqual(json.loads(row["detail"])["name"], "Ceiling light")


class EntryTests(ApiTest):
    def test_the_rooms_the_family_comes_in_through_are_kept_and_unknown_ones_dropped(self):
        r = self.client.post("/home/entry", json={"rooms": ["front", "attic", "front"]})
        self.assertEqual(r.json()["entry"], ["front"])                  # deduped, and the attic does not exist
        self.assertEqual(self.hub.settings.get("entry"), ["front"])

    def test_new_devices_can_never_be_a_way_in(self):
        self.assertEqual(self.client.post("/home/entry", json={"rooms": ["unassigned"]}).json()["entry"], [])


class LookTests(ApiTest):
    def test_the_house_has_one_look_and_a_panel_cannot_teach_it_a_setting_it_does_not_know(self):
        r = self.client.post("/look", json={"tone": "warm", "wallpaper": "cats"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.hub.look.get("tone"), "warm")
        self.assertNotIn("wallpaper", self.hub.look)


if __name__ == "__main__":
    unittest.main()


class AccountTests(ApiTest):
    """The accounts the house has signed into, and the end of one. docs/settings.md, step 2's other half.

    Until this there was no route that listed what the house had signed into, which is why removing one had
    nowhere to live: a Remove button with no list under it is not a page.
    """

    ENTRIES = [
        {"entry_id": "e-hue", "domain": "hue", "title": "Philips Hue", "state": "loaded"},
        {"entry_id": "e-nest", "domain": "nest", "title": "Google Nest", "state": "loaded"},
        {"entry_id": "e-mqtt", "domain": "mqtt", "title": "Mosquitto", "state": "loaded"},
        {"entry_id": "e-met", "domain": "met", "title": "Weather", "state": "loaded"},
    ]
    DEVICES = [{"id": "d1", "config_entries": ["e-hue"]}, {"id": "d2", "config_entries": ["e-hue"]},
               {"id": "d3", "config_entries": ["e-nest"]}, {"id": "d4", "config_entries": ["e-mqtt"]}]

    def setUp(self):
        super().setUp()
        self.ha.answers["config_entries/get"] = list(self.ENTRIES)
        self.ha.answers["config/device_registry/list"] = list(self.DEVICES)
        self.ha.answers["manifest/get"] = lambda integration=None, **kw: {"name": integration.title()}

    def accounts(self):
        r = self.client.get("/accounts")
        self.assertEqual(r.status_code, 200)
        return {a["id"]: a for a in r.json()["accounts"]}

    def test_an_account_is_a_thing_that_brought_something_in(self):
        got = self.accounts()
        self.assertIn("e-hue", got)
        self.assertEqual(got["e-hue"]["things"], 2)
        self.assertEqual(got["e-hue"]["state"], "on")

    def test_the_engines_own_plumbing_is_not_somebodys_account(self):
        """The brain added MQTT, Z-Wave and Matter itself; nobody signed into them."""
        self.assertNotIn("e-mqtt", self.accounts())

    def test_nor_is_the_weather(self):
        """It brought no devices, wants nothing from anyone, and is not what this page is about."""
        self.assertNotIn("e-met", self.accounts())

    def test_an_account_waiting_for_a_person_says_so_and_carries_the_way_to_answer(self):
        self.hub.provision.sign_ins = [{"handler": "nest", "flow_id": "flow-1", "kind": "Nest", "title": "Google Nest"}]
        got = self.accounts()["e-nest"]
        self.assertEqual(got["state"], "signin")
        self.assertEqual(got["flow"], "flow-1")

    def test_an_account_that_could_not_start_says_why(self):
        self.hub.provision.problems = [{"entry_id": "e-nest", "domain": "nest", "title": "Google Nest",
                                        "state": "setup_retry", "reason": "the key was revoked"}]
        got = self.accounts()["e-nest"]
        self.assertEqual(got["state"], "stopped")
        self.assertIn("revoked", got["why"])

    def test_what_needs_a_person_is_listed_before_what_is_fine(self):
        self.hub.provision.sign_ins = [{"handler": "nest", "flow_id": "flow-1", "kind": "Nest", "title": "Google Nest"}]
        order = [a["id"] for a in self.client.get("/accounts").json()["accounts"]]
        self.assertLess(order.index("e-nest"), order.index("e-hue"))

    # ---- the end of one ----
    def test_removing_an_account_asks_the_engine_to_take_it_out(self):
        sent = []
        with mock.patch.object(self.hub.add, "_rest", lambda m, p, d=None: sent.append((m, p)) or {}):
            r = self.client.delete("/accounts/e-hue")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sent, [("DELETE", "/api/config/config_entries/entry/e-hue")])

    def test_it_is_written_down_with_the_name_a_person_would_recognise(self):
        with mock.patch.object(self.hub.add, "_rest", lambda m, p, d=None: {}):
            self.client.delete("/accounts/e-hue")
        row = self.hub.log.recent(1, subject="e-hue")[0]
        self.assertEqual(row["new"], "account removed")
        self.assertEqual(json.loads(row["detail"])["name"], "Philips Hue")

    def test_removing_something_that_is_not_there(self):
        self.assertEqual(self.client.delete("/accounts/e-nothing").status_code, 404)

    def test_an_engine_that_refuses_is_passed_on_with_the_name_in_front(self):
        def no(m, p, d=None): raise RuntimeError("Integration not loaded")
        with mock.patch.object(self.hub.add, "_rest", no):
            r = self.client.delete("/accounts/e-hue")
        self.assertEqual(r.status_code, 502)
        self.assertIn("Philips Hue", r.json()["detail"])

    def test_removing_an_account_needs_the_code(self):
        self.assertTrue(needs_code("DELETE", "/accounts/e-hue"))
        self.assertFalse(needs_code("GET", "/accounts"))


class UnitTests(ApiTest):
    """A switch with a motion sensor built in is one thing on the wall: docs/units.md."""

    def pathlight_house(self, has_entity_name=True):
        from tests.apptest import entity, hardware, house, state
        areas, devices, entities, states = house()
        devices = devices + [hardware("hw-path", None, "Walkway Pathlight", manufacturer="Ring", model="Lighting Switch/Light")]
        entities = entities + [entity("light.walkway_pathlight_light", "hw-path", has_entity_name=has_entity_name),
                               entity("binary_sensor.walkway_pathlight_motion", "hw-path", original_device_class="motion", has_entity_name=has_entity_name)]
        states = states + [state("light.walkway_pathlight_light", "off", friendly_name="Walkway Pathlight Light"),
                           state("binary_sensor.walkway_pathlight_motion", "on", friendly_name="Walkway Pathlight Motion", device_class="motion")]
        return areas, devices, entities, states

    def test_a_light_knows_the_motion_sensor_built_into_it_and_the_sensor_is_still_its_own_device(self):
        self.hub.home.build(*self.pathlight_house())
        light = self.hub.home.devices["light.walkway_pathlight_light"]
        self.assertEqual(light.attrs.get("motion"), "binary_sensor.walkway_pathlight_motion")
        self.assertEqual(self.hub.home.devices["binary_sensor.walkway_pathlight_motion"].capability, "motion")
        self.assertNotIn("motion", self.hub.home.devices["light.ceiling"].attrs)   # a bulb with no sensor on its hardware

    def test_it_survives_a_state_change_the_way_a_cameras_lamp_does(self):
        self.hub.home.build(*self.pathlight_house())
        self.hub.home.apply_state("light.walkway_pathlight_light", {"state": "on", "attributes": {"friendly_name": "Walkway Pathlight Light"}})
        self.assertEqual(self.hub.home.devices["light.walkway_pathlight_light"].attrs.get("motion"), "binary_sensor.walkway_pathlight_motion")

    def test_renaming_the_unit_renames_the_hardware_and_leaves_parts_ha_names_after_it_alone(self):
        self.hub.home.build(*self.pathlight_house(has_entity_name=True))
        r = self.client.post("/devices/light.walkway_pathlight_light/rename", json={"name": "Path light", "unit": True})
        self.assertEqual(r.status_code, 200)
        self.assertIn(("config/device_registry/update", {"device_id": "hw-path", "name_by_user": "Path light"}), self.ha.sent)
        self.assertEqual([s for s in self.ha.sent if s[0] == "config/entity_registry/update"], [])

    def test_parts_that_carry_their_own_name_follow_the_unit_where_that_name_began_with_it(self):
        self.hub.home.build(*self.pathlight_house(has_entity_name=False))
        self.hub.home.devices["binary_sensor.walkway_pathlight_motion"].name = "Steps"    # renamed by hand once already
        self.client.post("/devices/light.walkway_pathlight_light/rename", json={"name": "Path light", "unit": True})
        renamed = [(s[1]["entity_id"], s[1]["name"]) for s in self.ha.sent if s[0] == "config/entity_registry/update"]
        self.assertEqual(renamed, [("light.walkway_pathlight_light", "Path light Light")])

    def test_without_the_unit_flag_a_rename_is_the_one_device_as_before(self):
        self.hub.home.build(*self.pathlight_house(has_entity_name=False))
        self.client.post("/devices/light.walkway_pathlight_light/rename", json={"name": "Path light"})
        self.assertNotIn("config/device_registry/update", [s[0] for s in self.ha.sent])
