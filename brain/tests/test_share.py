# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What this house will and will not hand to somebody else's assistant: docs/matter.md.

The bridge publishes the list it is handed, so this file is where the decisions of 17 September 2026
actually live. Two of them are the reason the file exists and each is held down on its own:

  - An alarm is never shared. Not a default -- a refusal, asserted with the household switching it
    every way a household could.
  - A lock is shared only where somebody said so. Matter's Door Lock carries the unlock with the lock
    and there is no half to publish, so the gate is a switch and the switch has to be thrown.

The rest is the ordinary contract: nothing leaves a house that has not said yes, the owner's names,
rooms and KINDS travel, and a command arriving from Apple Home goes the same way a tap does.

Run from brain/: .venv/bin/python -m unittest -v
"""
import unittest
from unittest import mock

from hub import share as share_mod
from hub.share import DEFAULT_KINDS, allowed, endpoint_id
from tests.apptest import ApiTest

TOKEN = "a-test-sharing-key"


class SharingTest(ApiTest):
    """A hub whose installer left it a sharing key, the way install.sh does."""

    def setUp(self):
        super().setUp()
        p = mock.patch.dict("os.environ", {"HUB_SHARE_TOKEN": TOKEN})
        p.start(); self.addCleanup(p.stop)

    def bridge(self, method, path, **kw):
        return getattr(self.client, method)(path, headers={"x-hub-service": TOKEN}, **kw)

    def published(self):
        return {d["id"]: d for d in self.bridge("get", "/share/bridge/devices").json()["devices"]}

    def share(self, **body):
        r = self.client.post("/share", json=body)
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()


class NothingUntilSomebodySaysSo(SharingTest):
    def test_a_house_that_has_not_been_asked_shares_nothing(self):
        state = self.client.get("/share").json()
        self.assertEqual((state["on"], state["shared"]), (False, 0))
        self.assertEqual(self.published(), {})

    def test_turning_it_on_publishes_the_lights_and_the_plugs_and_nothing_else(self):
        self.share(on=True)
        out = self.published()
        self.assertIn("light.kitchen", out)
        self.assertIn("switch.kettle", out)
        # A speaker and a thermostat have no Matter device type this bridge can build yet.
        self.assertNotIn("media_player.tv", out)
        self.assertNotIn("climate.nest", out)

    def test_switching_the_whole_thing_off_again_empties_the_bridge(self):
        self.share(on=True)
        self.assertTrue(self.published())
        self.share(on=False)
        self.assertEqual(self.published(), {})

    def test_a_kind_the_household_turned_off_stops_being_published(self):
        self.share(on=True, kinds=["light"])
        out = self.published()
        self.assertIn("light.kitchen", out)
        self.assertNotIn("switch.kettle", out)


class WhatTheScreenIsToldBeforeAnybodySaysYes(SharingTest):
    """The page argues the feature while it is still off, so it has to know what WOULD go out."""

    def test_a_house_that_has_not_said_yes_is_still_told_what_is_ready(self):
        state = self.client.get("/share").json()
        self.assertFalse(state["on"])
        self.assertEqual(state["shared"], 0)          # nothing is going out
        self.assertGreater(state["candidates"], 0)    # ...and this is what would
        self.assertEqual(self.published(), {})        # and the bridge is still handed nothing

    def test_it_is_told_a_few_of_them_by_name(self):
        names = [p["name"] for p in self.client.get("/share").json()["preview"]]
        self.assertIn("Kitchen lights", names)
        self.assertLessEqual(len(names), 3)

    def test_the_preview_obeys_the_same_gates_as_the_list(self):
        # Whatever a household would see drawn on its way out is the list it would actually send.
        self.client.post("/devices/switch.kettle/kind", json={"kind": "alarm"})
        state = self.client.get("/share").json()
        self.assertNotIn("Kettle", [p["name"] for p in state["preview"]])


class LeavingOneThingOut(SharingTest):
    """A kind is the coarse decision; this is the exception to it. Thirty-two lights is what a real
    house has, and Apple Home cannot curate a bridge from its side -- so if this hub does not offer
    it, nobody can."""

    def leave(self, device_id, shared=False):
        r = self.client.post(f"/devices/{device_id}/share", json={"shared": shared})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def test_one_lamp_can_stay_home_while_its_kind_goes_out(self):
        self.share(on=True)
        self.assertIn("light.kitchen", self.published())
        self.leave("light.kitchen")
        out = self.published()
        self.assertNotIn("light.kitchen", out)
        self.assertIn("light.ceiling", out)        # the rest of the kind is untouched

    def test_and_can_be_put_back(self):
        self.share(on=True)
        self.leave("light.kitchen")
        self.leave("light.kitchen", shared=True)
        self.assertIn("light.kitchen", self.published())

    def test_the_page_counts_the_exceptions_and_never_lists_them_as_the_rule(self):
        self.share(on=True)
        before = self.client.get("/share").json()
        self.assertEqual(before["left_out_now"], 0)
        self.leave("light.kitchen")
        after = self.client.get("/share").json()
        self.assertEqual(after["left_out_now"], 1)
        self.assertEqual(after["shared"], before["shared"] - 1)
        self.assertIn("light.kitchen", after["left_out"])

    def test_an_exception_survives_its_kind_being_switched_off_and_on(self):
        # The reason it is stored as the exception and not as the rule: a household that turns lights
        # off and on again has not changed its mind about the one lamp it meant to keep home.
        self.share(on=True)
        self.leave("light.kitchen")
        self.share(on=True, kinds=["switch"])
        self.share(on=True, kinds=["light", "switch", "appliance"])
        self.assertNotIn("light.kitchen", self.published())

    def test_a_lamp_left_out_of_a_kind_nobody_shares_is_not_counted_as_held_back(self):
        self.share(on=True)
        self.leave("light.kitchen")
        self.share(on=True, kinds=["switch"])      # lights are not going out at all now
        self.assertEqual(self.client.get("/share").json()["left_out_now"], 0)

    def test_nothing_the_house_is_not_sharing_can_be_left_out_of_it(self):
        # No switch is drawn for these, and the route says the same thing the screen does.
        self.share(on=True)
        for device_id in ("lock.front", "media_player.tv", "climate.nest"):
            with self.subTest(device_id=device_id):
                self.assertEqual(self.client.post(f"/devices/{device_id}/share", json={"shared": False}).status_code, 409)

    def test_it_is_refused_while_the_house_shares_nothing_at_all(self):
        self.assertEqual(self.client.post("/devices/light.kitchen/share", json={"shared": False}).status_code, 409)

    def test_a_thing_left_out_is_refused_at_the_moment_of_acting_too(self):
        self.share(on=True)
        self.leave("light.kitchen")
        self.assertEqual(self.bridge("post", "/share/bridge/act/light.kitchen/on").status_code, 403)

    def test_leaving_one_out_is_a_change_to_the_house_and_needs_the_code(self):
        from hub.lock import needs_code
        self.assertTrue(needs_code("POST", "/devices/light.kitchen/share"))


class TheAlarmIsNeverShared(SharingTest):
    """The decision, and the reason it is a rule and not a switch: an On/Off endpoint is one word away
    from sounding, from any room and any guest, and Matter has no way to ask for the second tap."""

    def siren(self):
        r = self.client.post("/devices/switch.kettle/kind", json={"kind": "alarm"})
        self.assertEqual(r.status_code, 200, r.text)

    def test_a_siren_is_not_published_with_the_plugs_it_arrived_as(self):
        self.siren()
        self.share(on=True)
        self.assertNotIn("switch.kettle", self.published())

    def test_a_household_cannot_switch_it_on_however_it_asks(self):
        self.siren()
        for kinds in (["light", "switch", "alarm"], ["alarm"], list(DEFAULT_KINDS) + ["alarm"]):
            with self.subTest(kinds=kinds):
                state = self.share(on=True, kinds=kinds)
                self.assertNotIn("alarm", state["kinds"])
                self.assertNotIn("switch.kettle", self.published())

    def test_it_is_refused_before_any_setting_is_read(self):
        # Belt and braces, and deliberately: the day `alarm` is added to TYPE by somebody filling in
        # piece 2, this is the assertion that stops it going out with the plugs.
        for share in ({"on": True, "kinds": ["alarm"]}, {"on": True, "kinds": list(share_mod.TYPE), "locks": True}):
            with self.subTest(share=share): self.assertFalse(allowed("alarm", share))

    def test_a_siren_the_house_guessed_is_refused_without_anybody_re_typing_it(self):
        """The gap piece 1 turned up, and what closed it: the refusal reads `kind_of`, and until the
        house guessed, a siren nobody had re-typed was a `switch` and went out with the plugs."""
        self.hub.home.devices["switch.kettle"].guess = "alarm"     # as model.guessed_kind would set it
        self.share(on=True)
        self.assertNotIn("switch.kettle", self.published())
        self.assertEqual(self.bridge("post", "/share/bridge/act/switch.kettle/on").status_code, 403)

    def test_it_is_not_even_on_offer_to_the_screen(self):
        self.assertNotIn("alarm", self.client.get("/share").json()["offer"])


class ALockNeedsSomebodyToSaySo(SharingTest):
    def test_a_lock_is_not_shared_by_a_house_that_shared_everything_else(self):
        self.share(on=True, kinds=list(share_mod.TYPE))
        self.assertFalse(allowed("lock", self.hub.share.settings))
        self.assertNotIn("lock.front", self.published())

    def test_the_switch_of_its_own_is_what_opens_it(self):
        self.share(on=True, locks=True)
        self.assertTrue(allowed("lock", self.hub.share.settings))
        self.assertTrue(allowed("cover", self.hub.share.settings))

    def test_the_lock_switch_is_not_reachable_through_the_ordinary_kind_list(self):
        # The gate is its own switch. Naming it among the kinds must not throw it.
        state = self.share(on=True, kinds=["light", "switch", "lock", "cover"])
        self.assertEqual(state["locks"], False)
        self.assertFalse(allowed("lock", self.hub.share.settings))
        self.assertNotIn("lock", state["offer"])


class WhatTheBridgeIsTold(SharingTest):
    def test_the_house_s_own_names_and_rooms_travel(self):
        self.share(on=True)
        kitchen = self.published()["light.kitchen"]
        self.assertEqual((kitchen["name"], kitchen["room"]), ("Kitchen lights", "Kitchen"))

    def test_a_lamp_the_owner_re_typed_as_a_light_arrives_as_a_light(self):
        # The whole argument of docs/kinds.md, carried out of the house: bridging the driver's entity
        # list would ship HA's opinion of a plug with a lamp on it and lose the owner's.
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})
        self.share(on=True)
        self.assertEqual(self.published()["switch.kettle"]["type"], "light")

    def test_a_light_that_can_dim_is_marked_and_one_that_cannot_is_not(self):
        self.share(on=True)
        out = self.published()
        self.assertTrue(out["light.kitchen"]["dim"])
        self.assertFalse(out["switch.kettle"]["dim"])

    def test_a_device_the_driver_has_lost_is_unreachable_rather_than_off(self):
        self.hub.home.devices["light.kitchen"].state = "unavailable"
        self.share(on=True)
        self.assertFalse(self.published()["light.kitchen"]["reachable"])

    def test_an_endpoint_id_is_stable_and_does_not_collide(self):
        self.assertEqual(endpoint_id("light.kitchen"), endpoint_id("light.kitchen"))
        self.assertNotEqual(endpoint_id("light.a-b"), endpoint_id("light.a.b"))


class ACommandFromSomebodyElsesAssistant(SharingTest):
    def test_it_goes_the_way_a_tap_does_and_by_the_driver_s_own_word(self):
        # capability, not kind: a re-typed plug is still a switch to Home Assistant, and light.turn_on
        # on it would be refused. docs/kinds.md's trap stays shut because the brain still does the call.
        self.client.post("/devices/switch.kettle/kind", json={"kind": "light"})
        self.share(on=True)
        r = self.bridge("post", "/share/bridge/act/switch.kettle/on")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertTrue(self.ha.called("switch", "turn_on", "switch.kettle"))

    def test_it_is_logged_as_matter_so_recent_can_say_a_voice_did_it(self):
        self.share(on=True)
        self.bridge("post", "/share/bridge/act/light.kitchen/on")
        self.assertIn("matter", [e["source"] for e in self.hub.log.recent(20)])

    def test_something_the_house_stopped_sharing_is_refused_even_if_a_controller_still_holds_it(self):
        self.share(on=True)
        self.assertEqual(self.bridge("post", "/share/bridge/act/light.kitchen/on").status_code, 200)
        self.share(on=True, kinds=["switch"])
        self.assertEqual(self.bridge("post", "/share/bridge/act/light.kitchen/on").status_code, 403)

    def test_a_lock_nobody_shared_is_refused_at_the_moment_of_acting_too(self):
        self.share(on=True)
        self.assertEqual(self.bridge("post", "/share/bridge/act/lock.front/unlock").status_code, 403)


class LettingOneMoreAppIn(SharingTest):
    """A Matter node takes several apps at once, but only through a door somebody opens on purpose:
    one sitting open with a printed code will join whoever has the code."""

    def waiting(self, commissioned=False, fabrics=()):
        """What the bridge says about itself, as it would post it."""
        self.bridge("post", "/share/bridge/status", json={"running": True, "commissioned": commissioned,
                                                          "fabrics": list(fabrics), "manual": "00330338072", "qr": "MT:-24J0C0R157HQV43C10"})

    def test_the_door_is_shut_until_it_is_asked_for(self):
        self.share(on=True)
        self.waiting(commissioned=True, fabrics=[{"index": 1, "vendor": 4937, "label": ""}])
        self.assertFalse(self.client.get("/share").json()["open"])
        self.assertIsNone(self.bridge("get", "/share/bridge/devices").json()["window"]["asked"])

    def test_asking_opens_it_for_five_minutes_and_the_bridge_is_told(self):
        self.share(on=True)
        self.waiting(commissioned=True, fabrics=[{"index": 1, "vendor": 4937, "label": ""}])
        state = self.client.post("/share/window", json={}).json()
        self.assertTrue(state["open"])
        self.assertGreater(state["seconds_left"], 240)
        self.assertIsNotNone(self.bridge("get", "/share/bridge/devices").json()["window"]["asked"])

    def test_a_window_that_has_run_out_is_not_reported_to_the_bridge_at_all(self):
        """The bug: a bridge that restarts has served no window requests, so the one somebody made
        three hours ago read as new and the commissioning door swung open again -- every restart, for
        ever, on the feature whose whole premise is that the door is shut."""
        import time as _t
        from hub import share as _share
        self.share(on=True)
        self.waiting(commissioned=True, fabrics=[{"index": 1, "vendor": 4937, "label": ""}])
        self.client.post("/share/window", json={})
        self.assertIsNotNone(self.bridge("get", "/share/bridge/devices").json()["window"]["asked"])
        # ...and once it has run out, the bridge is told about no request at all.
        s = dict(self.hub.share.settings); s["window_asked"] = _t.time() - _share.WINDOW - 1
        self.hub.settings.set(share=s)
        self.assertIsNone(self.bridge("get", "/share/bridge/devices").json()["window"]["asked"])
        self.assertFalse(self.client.get("/share").json()["open"])

    def test_a_bridge_nobody_holds_is_already_waiting_to_be_scanned(self):
        # Nothing has commissioned it, so there is no door to open -- it is standing open, and the
        # panel should show the code rather than a button that does nothing.
        self.share(on=True)
        self.waiting(commissioned=False)
        state = self.client.get("/share").json()
        self.assertTrue(state["open"])
        self.assertEqual(state["code"], "00330338072")

    def test_a_house_sharing_nothing_has_no_door_to_open(self):
        self.assertEqual(self.client.post("/share/window", json={}).status_code, 409)

    def test_and_neither_has_a_house_whose_bridge_is_not_running(self):
        """The bug this is written against: the panel said *the door is open for five minutes* when
        there was no bridge, no door, and nothing had happened. On the one page about where a
        household's devices go, a cheerful answer to a request that did nothing is the worst kind."""
        self.share(on=True)                     # sharing on, but nothing has ever reported in
        r = self.client.post("/share/window", json={})
        self.assertEqual(r.status_code, 409)
        self.assertIn("not running", r.json()["detail"])
        self.assertFalse(self.client.get("/share").json()["bridge"].get("running"))

    def test_a_bridge_that_has_stopped_reporting_is_not_running(self):
        import time as _t
        from hub import share as _share
        self.share(on=True)
        self.waiting(commissioned=True, fabrics=[{"index": 1, "vendor": 4937, "label": ""}])
        self.assertTrue(self.client.get("/share").json()["bridge"]["running"])
        # ...and the same answer, three heartbeats later, is not the same answer.
        self.hub.share_status["at"] = _t.time() - _share.BRIDGE_STALE - 1
        state = self.client.get("/share").json()
        self.assertFalse(state["bridge"]["running"])
        self.assertTrue(state["bridge"]["stale"])
        self.assertFalse(state["open"])
        self.assertEqual(self.client.post("/share/window", json={}).status_code, 409)

    def test_but_a_stopped_bridge_does_not_mean_nobody_holds_the_house(self):
        # Apple Home has not forgotten this house because a container fell over, and saying the house
        # is held by nobody would be the wrong lie to tell in its place.
        import time as _t
        from hub import share as _share
        self.share(on=True)
        self.waiting(commissioned=True, fabrics=[{"index": 1, "vendor": 4937, "label": ""}])
        self.hub.share_status["at"] = _t.time() - _share.BRIDGE_STALE - 1
        self.assertEqual([h["name"] for h in self.client.get("/share").json()["holders"]], ["Apple Home"])

    def test_the_code_is_drawn_only_while_the_door_is_open(self):
        self.share(on=True)
        self.assertEqual(self.client.get("/share/qr.svg").status_code, 404)
        self.waiting(commissioned=False)
        r = self.client.get("/share/qr.svg")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["content-type"], "image/svg+xml")


class NamingWhoHoldsTheHouse(SharingTest):
    """The vendor ids are read off the CSA's ledger, not guessed: a wrong name here would tell
    somebody the wrong app is in their house."""

    def holders(self, *fabrics):
        self.bridge("post", "/share/bridge/status", json={"running": True, "commissioned": True, "fabrics": list(fabrics)})
        return [h["name"] for h in self.client.get("/share").json()["holders"]]

    def test_the_ecosystems_are_named(self):
        self.assertEqual(self.holders({"index": 1, "vendor": 4937, "label": ""}), ["Apple Home"])
        self.assertEqual(self.holders({"index": 1, "vendor": 24582, "label": ""}), ["Google Home"])
        self.assertEqual(self.holders({"index": 1, "vendor": 4631, "label": ""}), ["Alexa"])

    def test_a_vendor_we_do_not_know_falls_back_to_what_it_called_itself(self):
        self.assertEqual(self.holders({"index": 1, "vendor": 65521, "label": "Somebody's hub"}), ["Somebody's hub"])

    def test_and_to_a_plain_noun_where_it_said_nothing(self):
        self.assertEqual(self.holders({"index": 1, "vendor": 65521, "label": ""}), ["An app"])

    def test_several_at_once_is_the_ordinary_case(self):
        self.assertEqual(self.holders({"index": 1, "vendor": 4937, "label": ""}, {"index": 2, "vendor": 24582, "label": ""}),
                         ["Apple Home", "Google Home"])


class TheRestOfTheKinds(SharingTest):
    """Piece 2: blinds, the thermostat, fans, sensors and locks. What is asserted here is the shape of
    what the bridge is handed -- the house's own units and conventions throughout, because every
    conversion into Matter's is a way to ship an inverted blind, and those live in the bridge."""

    def all_on(self):
        from hub.share import TYPE
        self.share(on=True, kinds=list(TYPE), locks=True)

    def test_every_new_kind_is_on_offer_to_the_screen(self):
        offer = self.client.get("/share").json()["offer"]
        for kind in ("fan", "cover", "climate", "motion", "contact", "sensor.temperature", "sensor.humidity"):
            with self.subTest(kind=kind): self.assertIn(kind, offer)
        self.assertNotIn("lock", offer)      # its own switch, never a chip among the others
        self.assertNotIn("alarm", offer)

    def test_the_lock_switch_is_no_longer_a_promise_nothing_keeps(self):
        # It was drawn, it could be switched on, and the bridge published nothing: piece 3 shipped a
        # screen for something piece 2 had not built yet.
        from hub.share import carried
        self.assertTrue(carried("lock"))
        self.all_on()
        self.assertIn("lock.front", self.published())

    def test_a_thermostat_goes_out_in_the_house_s_own_units(self):
        self.all_on()
        t = self.published()["climate.nest"]
        self.assertEqual(t["type"], "thermostat")
        self.assertEqual(t["unit"], "°F")                  # NOT centi-Celsius: that is the bridge's job
        self.assertEqual(t["state"]["target"], 71)
        self.assertEqual(t["state"]["current"], 74)
        self.assertEqual(t["state"]["mode"], "cool")

    def test_a_reading_goes_out_as_a_number_and_not_as_ha_s_string(self):
        self.all_on()
        r = self.published()["sensor.kitchen_temp"]
        self.assertEqual(r["type"], "temperature")
        self.assertEqual(r["state"]["value"], 68.2)

    def test_a_motion_and_a_contact_go_out_in_the_house_s_own_sense(self):
        self.all_on()
        out = self.published()
        self.assertEqual(out["binary_sensor.kitchen_motion"]["state"], {"detected": False})
        # `open` means open. Matter's contact sensor says the opposite with `true`, and inverting it
        # here rather than in the bridge would put the trap two files from the cluster it belongs to.
        self.assertEqual(out["binary_sensor.kitchen_motion"]["type"], "occupancy")

    def test_a_fan_carries_its_percentage(self):
        self.all_on()
        f = self.published()["fan.ceiling_fan"]
        self.assertEqual((f["type"], f["state"]["on"], f["state"]["percent"]), ("fan", False, 0))


class ABlindIsNotAGarageDoor(SharingTest):
    """The cover split. `model.GATED` gates the whole kind against a re-TYPING and is right to; on the
    way out of the house the question is different, and the screen already says *Locks and garage
    doors* rather than *locks and blinds*."""

    def cover(self, device_class=None):
        dev = self.hub.home.devices["cover.blind"] = type(self.hub.home.devices["light.kitchen"])(
            id="cover.blind", name="Bedroom blind", room_id="kitchen", capability="cover", state="open",
            attrs={"current_position": 70, **({"device_class": device_class} if device_class else {})})
        self.hub.home.rooms["kitchen"].devices.append(dev)
        return dev

    def test_a_blind_goes_out_with_the_ordinary_kinds(self):
        self.cover("blind")
        self.share(on=True, kinds=["light", "cover"])
        out = self.published()
        self.assertIn("cover.blind", out)
        self.assertEqual(out["cover.blind"]["state"]["position"], 70)

    def test_a_garage_door_needs_the_switch_of_its_own(self):
        self.cover("garage")
        self.share(on=True, kinds=["light", "cover"])
        self.assertNotIn("cover.blind", self.published())
        self.share(on=True, kinds=["light", "cover"], locks=True)
        self.assertIn("cover.blind", self.published())

    def test_a_cover_the_house_knows_nothing_about_is_treated_as_a_way_in(self):
        # The one we would be guessing about is the garage, so the guess goes the safe way.
        self.cover(None)
        self.share(on=True, kinds=["light", "cover"])
        self.assertNotIn("cover.blind", self.published())

    def test_and_is_refused_at_the_moment_of_acting_too(self):
        self.cover("garage")
        self.share(on=True, kinds=["light", "cover"])
        self.assertEqual(self.bridge("post", "/share/bridge/act/cover.blind/open").status_code, 403)


class TheBridgeIsNotAPhone(SharingTest):
    """It is a container on this host with a key, and it gets its own routes and nothing else."""

    def setUp(self):
        super().setUp()
        self.code = self.lock_the_house("4821")

    def test_it_comes_in_on_its_own_routes_with_the_key(self):
        self.assertEqual(self.bridge("get", "/share/bridge/devices").status_code, 200)

    def test_without_the_key_it_is_a_stranger_like_anything_else(self):
        self.assertEqual(self.client.get("/share/bridge/devices").status_code, 401)
        self.assertEqual(self.client.get("/share/bridge/devices", headers={"x-hub-service": "wrong"}).status_code, 401)

    def test_the_key_does_not_open_the_rest_of_the_house(self):
        # The point of not widening open_to_strangers: the bridge's key is for the bridge's routes.
        for path in ("/home", "/accounts", "/phones"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path, headers={"x-hub-service": TOKEN}).status_code, 401)

    def test_turning_sharing_on_needs_the_code_the_way_letting_a_phone_in_does(self):
        from hub.lock import needs_code
        self.assertTrue(needs_code("POST", "/share"))
        self.assertFalse(needs_code("GET", "/share"))

    def test_and_so_does_letting_one_more_app_in(self):
        from hub.lock import needs_code
        self.assertTrue(needs_code("POST", "/share/window"))


class AHubWithNoKey(ApiTest):
    def test_a_hub_whose_installer_predates_sharing_says_so_rather_than_pretending(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("HUB_SHARE_TOKEN", None)
            self.assertFalse(self.client.get("/share").json()["ready"])
            self.assertEqual(self.client.post("/share", json={"on": True}).status_code, 409)


if __name__ == "__main__":
    unittest.main()
