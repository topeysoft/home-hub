"""Where the sun is. A port of app/src/sun.ts, so the panel's sky and the brain's rules agree.

Checked against published times rather than against itself: a port that drifts is the failure worth
catching, and only real almanac values catch it.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from hub import sun

POSITIONS = json.loads((Path(__file__).resolve().parent / "sun-positions.json").read_text())["rows"]

CHICAGO = ZoneInfo("America/Chicago")
UTC = ZoneInfo("UTC")


def at(y, m, d, hh=0, mm=0, tz=CHICAGO):
    return datetime(y, m, d, hh, mm, tzinfo=tz)


class ElevationTests(unittest.TestCase):
    def test_the_sun_is_up_at_midday_and_down_at_midnight(self):
        self.assertGreater(sun.elevation(at(2026, 9, 11, 12), 41.88, -87.63), 40)
        self.assertLess(sun.elevation(at(2026, 9, 11, 0), 41.88, -87.63), -30)

    def test_midsummer_stands_higher_than_midwinter_at_the_same_clock_time(self):
        june = sun.elevation(at(2026, 6, 21, 13), 41.88, -87.63)
        december = sun.elevation(at(2026, 12, 21, 13), 41.88, -87.63)
        self.assertGreater(june, december + 40)

    def test_the_seasons_are_the_other_way_round_below_the_equator(self):
        # Sydney, the same two days. If a sign were flipped this is what would say so.
        june = sun.elevation(at(2026, 6, 21, 12, 0, ZoneInfo("Australia/Sydney")), -33.87, 151.21)
        december = sun.elevation(at(2026, 12, 21, 12, 0, ZoneInfo("Australia/Sydney")), -33.87, 151.21)
        self.assertLess(june, december)


class CrossingsTests(unittest.TestCase):
    def near(self, when, hh, mm, minutes=3):
        self.assertIsNotNone(when)
        want = when.replace(hour=hh, minute=mm, second=0, microsecond=0)
        self.assertLessEqual(abs((when - want).total_seconds()), minutes * 60, f"{when:%H:%M:%S} is not near {hh:02d}:{mm:02d}")

    def test_chicago_matches_the_published_times(self):
        rise, set_ = sun.crossings(at(2026, 9, 11), 41.88, -87.63)
        self.near(rise, 6, 26)
        self.near(set_, 19, 7)

    def test_the_shortest_and_longest_days_are_the_right_way_round(self):
        _, _ = None, None
        june_rise, june_set = sun.crossings(at(2026, 6, 21), 41.88, -87.63)
        dec_rise, dec_set = sun.crossings(at(2026, 12, 21), 41.88, -87.63)
        self.assertGreater((june_set - june_rise), (dec_set - dec_rise) + timedelta(hours=5))

    def test_somewhere_near_the_equator_the_day_is_about_twelve_hours_all_year(self):
        for month in (3, 6, 9, 12):
            with self.subTest(month=month):
                rise, set_ = sun.crossings(datetime(2026, month, 15, tzinfo=UTC), 0.31, 32.58)   # Kampala
                self.assertAlmostEqual((set_ - rise).total_seconds() / 3600, 12.1, delta=0.5)

    def test_a_polar_summer_has_no_sunset_and_a_polar_winter_no_sunrise(self):
        # Neither happens, so neither is a time. A caller that needs to tell the two apart asks for the elevation.
        self.assertEqual(sun.crossings(datetime(2026, 6, 21, tzinfo=UTC), 78.22, 15.65), (None, None))
        self.assertGreater(sun.elevation(datetime(2026, 6, 21, tzinfo=UTC), 78.22, 15.65), 0)

        self.assertEqual(sun.crossings(datetime(2026, 12, 21, tzinfo=UTC), 78.22, 15.65), (None, None))
        self.assertLess(sun.elevation(datetime(2026, 12, 21, tzinfo=UTC), 78.22, 15.65), 0)

    def test_the_crossing_is_the_moment_the_sun_is_actually_at_the_horizon(self):
        rise, set_ = sun.crossings(at(2026, 9, 11), 41.88, -87.63)
        for when in (rise, set_):
            self.assertAlmostEqual(sun.elevation(when, 41.88, -87.63), sun.HORIZON, delta=0.05)


class ParityTests(unittest.TestCase):
    """The same table app/tests/sun.test.ts checks the panel against.

    sun.py and sun.ts are one calculation written twice, and nothing in either would notice the other
    drifting: the panel would paint one dusk and an after-dark rule would fire at another.
    """

    def test_the_brain_still_agrees_with_the_table_the_panel_is_held_to(self):
        for row in POSITIONS:
            with self.subTest(place=row["place"], utc=row["utc"]):
                when = datetime.fromisoformat(row["utc"].replace("Z", "+00:00"))
                self.assertAlmostEqual(sun.elevation(when, row["lat"], row["lon"]), row["elevation"], places=3)

    def test_the_table_covers_both_hemispheres_and_the_awkward_latitudes(self):
        places = {r["place"] for r in POSITIONS}
        self.assertTrue(any(r["lat"] > 60 for r in POSITIONS), "nowhere polar")
        self.assertTrue(any(r["lat"] < 0 for r in POSITIONS), "nowhere southern")
        self.assertTrue(any(abs(r["lat"]) < 5 for r in POSITIONS), "nowhere equatorial")
        self.assertGreaterEqual(len(places), 5)


if __name__ == "__main__":
    unittest.main()
