# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run from brain/: .venv/bin/python -m unittest tests.test_power -v

design/energy/, B with C's sun: the house's power is said only when it changes what somebody would do."""
import asyncio, unittest
from zoneinfo import ZoneInfo
from hub.model import Home
from hub.power import Power, SETTLE, BACK_FOR


class Clock:
    def __init__(self): self.now = 1_000_000.0
    def __call__(self): return self.now


def gateway(solar="5.8", house="1.2", battery="-2.4", grid="-2.2", charge="84", grid_up="on", left=("12100", "11900")):
    """Two Powerwall+ behind one gateway, as HA's Powerwall setup makes them: meters in kW, each battery's
    energy left in Wh, and names a household may have changed -- which is why nothing here reads them."""
    rows = [("sensor.roof_now", "solar_instant_power", solar, "kW"), ("sensor.house_now", "load_instant_power", house, "kW"),
            ("sensor.pw_battery_now", "battery_instant_power", battery, "kW"), ("sensor.pw_site_now", "site_instant_power", grid, "kW"),
            ("sensor.pw_charge", "charge", charge, "%"), ("sensor.pw_backup_reserve", "backup_reserve", "20", "%"),
            ("binary_sensor.pw_grid_status", "grid_status", grid_up, None),
            ("sensor.pw_solar_export", "solar_export", "40211.3", "kWh"), ("sensor.pw_load_import", "load_import", "61002.9", "kWh"),
            ("sensor.pw_site_frequency", "site_instant_frequency", "60.0", "Hz")]
    rows += [(f"sensor.pw{i}_battery_remaining", "battery_remaining", v, "Wh") for i, v in enumerate(left)]
    entities = [{"entity_id": eid, "platform": "powerwall", "translation_key": key, "device_id": "gw"} for eid, key, _, _ in rows]
    states = [{"entity_id": eid, "state": v, "attributes": {"unit_of_measurement": u} if u else {}, "last_changed": "2026-10-10T14:00:00+00:00"}
              for eid, _, v, u in rows]
    return entities, states


def at(eid, value, unit="kW"):
    return {"entity_id": eid, "state": value, "attributes": {"unit_of_measurement": unit} if unit else {}, "last_changed": "2026-10-10T15:00:00+00:00"}


class WhatTheGatewayIs(unittest.TestCase):
    def test_its_readings_are_found_by_what_the_setup_says_they_are(self):
        p = Power(Clock()); p.load(*gateway())
        n = p.now()
        self.assertEqual((n["solar"], n["house"], n["battery"], n["grid"], n["charge"], n["reserve"], n["grid_up"], n["left"]),
                         (5.8, 1.2, 2.4, -2.2, 84.0, 20.0, True, 24.0))
        self.assertTrue(n["has_battery"])

    def test_a_house_without_one_has_nothing_to_say(self):
        p = Power(Clock()); p.load([{"entity_id": "sensor.x", "platform": "met", "translation_key": "charge"}], [])
        self.assertFalse(p.exists())
        self.assertIsNone(p.now())

    def test_none_of_it_is_a_device_in_a_room(self):
        entities, states = gateway()
        home = Home().build([{"area_id": "garage", "name": "Garage"}], [{"id": "gw", "area_id": "garage", "name": "Gateway"}], entities,
                            [{**s, "attributes": {**s["attributes"], "device_class": "power"}} for s in states])
        self.assertEqual(home.devices, {})

    def test_a_reading_that_is_not_ours_is_left_alone(self):
        p = Power(Clock()); p.load(*gateway())
        self.assertFalse(p.on_state("light.kitchen", {"state": "on"}))
        self.assertTrue(p.on_state("sensor.roof_now", at("sensor.roof_now", "4.1")))
        self.assertEqual(p.now()["solar"], 4.1)


class SunToSpare(unittest.TestCase):
    def full(self, clock):
        p = Power(clock); p.load(*gateway(charge="100", grid="-3.4"))
        return p

    def test_it_is_said_only_once_the_battery_is_full_and_power_has_gone_out_for_ten_minutes(self):
        clock = Clock(); p = self.full(clock)
        self.assertFalse(p.now()["spare"])
        clock.now += SETTLE
        p.on_state("sensor.pw_site_now", at("sensor.pw_site_now", "-3.1"))
        self.assertTrue(p.now()["spare"])

    def test_not_while_the_battery_is_still_filling(self):
        clock = Clock(); p = Power(clock); p.load(*gateway(charge="84", grid="-2.2"))
        clock.now += SETTLE * 2
        self.assertFalse(p.now()["spare"])

    def test_a_cloud_going_over_does_not_take_it_away(self):
        clock = Clock(); p = self.full(clock)
        clock.now += SETTLE; p.now()
        p.on_state("sensor.pw_site_now", at("sensor.pw_site_now", "0.4"))
        clock.now += 120
        p.on_state("sensor.pw_site_now", at("sensor.pw_site_now", "-2.9"))
        clock.now += SETTLE
        self.assertTrue(p.now()["spare"])

    def test_the_evening_does(self):
        clock = Clock(); p = self.full(clock)
        clock.now += SETTLE; p.now()
        p.on_state("sensor.pw_site_now", at("sensor.pw_site_now", "0.1"))
        clock.now += SETTLE
        self.assertFalse(p.now()["spare"])


class ThePowerGoingOut(unittest.TestCase):
    def test_out_then_back_and_how_long_it_was(self):
        clock = Clock(); p = Power(clock); p.load(*gateway())
        p.on_state("binary_sensor.pw_grid_status", {**at("binary_sensor.pw_grid_status", "off", None), "last_changed": "1970-01-12T13:46:40+00:00"})
        n = p.now()
        self.assertEqual((n["grid_up"], n["out_since"], n["spare"]), (False, 1_000_000.0, False))
        clock.now += 7800
        p.on_state("binary_sensor.pw_grid_status", at("binary_sensor.pw_grid_status", "on", None))
        n = p.now()
        self.assertEqual((n["grid_up"], n["out_since"], n["back"]), (True, None, {"at": 1_007_800.0, "lasted": 7800.0}))
        clock.now += BACK_FOR + 1
        self.assertIsNone(p.now()["back"])

    def test_an_outage_ends_sun_to_spare_at_once(self):
        clock = Clock(); p = Power(clock); p.load(*gateway(charge="100", grid="-3.4"))
        clock.now += SETTLE; self.assertTrue(p.now()["spare"])
        p.on_state("binary_sensor.pw_grid_status", at("binary_sensor.pw_grid_status", "off", None))
        self.assertFalse(p.now()["spare"])

    def test_the_band_changing_is_what_sends_at_once(self):
        p = Power(Clock()); p.load(*gateway())
        before = p.said()
        p.on_state("sensor.roof_now", at("sensor.roof_now", "3.0"))
        self.assertEqual(p.said(), before)
        p.on_state("binary_sensor.pw_grid_status", at("binary_sensor.pw_grid_status", "off", None))
        self.assertNotEqual(p.said(), before)


class FakeHA:
    def __init__(self): self.asked = []
    async def send(self, type_, **kw):
        self.asked.append((type_, kw))
        if type_ == "recorder/statistic_during_period":
            return {"change": 24.63} if "calendar" in kw and kw["statistic_id"] == "sensor.pw_solar_export" else \
                   {"change": 9.81} if "calendar" in kw else {"max": 7.9}
        return {"sensor.roof_now": [{"start": 1_760_000_000_000.0, "mean": 0.4}, {"start": 1_760_000_300_000.0, "mean": 0.9}],
                "sensor.house_now": [{"start": 1_760_000_000_000.0, "mean": 1.1}]}


class TheDaySoFar(unittest.TestCase):
    def test_from_home_assistants_own_statistics_and_asked_once_per_five_minutes(self):
        clock, ha = Clock(), FakeHA()
        p = Power(clock); p.load(*gateway())
        day = asyncio.run(p.day(ha, ZoneInfo("America/Los_Angeles")))
        self.assertEqual((day["made"], day["used"], day["peak"]), (24.6, 9.8, 7.9))
        self.assertEqual(day["curve"], [{"at": 1_760_000_000.0, "solar": 0.4, "house": 1.1}, {"at": 1_760_000_300.0, "solar": 0.9, "house": None}])
        asked = len(ha.asked)
        asyncio.run(p.day(ha, ZoneInfo("America/Los_Angeles")))
        self.assertEqual(len(ha.asked), asked)


if __name__ == "__main__":
    unittest.main()
