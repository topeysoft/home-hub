"""The routes the panel leans on every second it is open: what the house is, and what a tap does to it.

Run from brain/: .venv/bin/python -m unittest -v
"""
import unittest

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
