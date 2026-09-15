"""What is coming, turned into numbers.

Two things worth keeping apart: the SHAPING, which is all the rules about HA's rows and takes no
connection at all, and the FETCH, which is one service call made twice and has to survive an
integration that serves only half a forecast.

Run from brain/: .venv/bin/python -m unittest -v
"""
import unittest
from datetime import UTC, datetime
from unittest import mock

from hub import forecast


def resp(entity, rows):
    return {entity: {"forecast": rows}}


HOURS = [{"datetime": "2026-09-15T13:00:00+00:00", "condition": "partlycloudy", "temperature": 82, "precipitation_probability": 10},
         {"datetime": "2026-09-15T14:00:00+00:00", "condition": "rainy", "temperature": 76, "precipitation_probability": 80}]
DAYS = [{"datetime": "2026-09-15T00:00:00+00:00", "condition": "rainy", "temperature": 84, "templow": 61, "precipitation_probability": 70},
        {"datetime": "2026-09-16T00:00:00+00:00", "condition": "sunny", "temperature": 88, "templow": 64}]


class ShapeTests(unittest.TestCase):
    def test_both_halves(self):
        f = forecast.shape(resp("weather.home", HOURS), resp("weather.home", DAYS), "weather.home")
        self.assertEqual([h["condition"] for h in f["hourly"]], ["partlycloudy", "rainy"])
        self.assertEqual(f["hourly"][1]["temperature"], 76.0)
        self.assertEqual(f["hourly"][1]["rain"], 80.0)
        # a daily row's `temperature` is the day's HIGH and `templow` its low
        self.assertEqual((f["daily"][0]["high"], f["daily"][0]["low"]), (84.0, 61.0))

    def test_half_a_forecast_is_still_a_forecast(self):
        """An integration that serves daily and refuses hourly is a normal thing to be."""
        f = forecast.shape(None, resp("weather.home", DAYS), "weather.home")
        self.assertEqual(f["hourly"], [])
        self.assertEqual(len(f["daily"]), 2)

    def test_nothing_at_all_is_none(self):
        """Not an empty shape: the panel branches on whether there IS a forecast, and {} is not a no."""
        self.assertIsNone(forecast.shape(None, None, "weather.home"))
        self.assertIsNone(forecast.shape(resp("weather.home", []), resp("weather.home", []), "weather.home"))

    def test_answer_keyed_by_another_name(self):
        """HA keys the response by the entity it was asked about, but a single-entity answer under
        any other key is still that entity's answer -- and refusing it would lose the forecast over
        a spelling."""
        f = forecast.shape(resp("weather.forecast_home", HOURS), None, "weather.home")
        self.assertEqual(len(f["hourly"]), 2)
        # two keys and neither of them ours is genuinely ambiguous, so nothing is taken
        two = {"weather.a": {"forecast": HOURS}, "weather.b": {"forecast": HOURS}}
        self.assertIsNone(forecast.shape(two, None, "weather.home"))

    def test_a_row_without_a_clock_is_dropped(self):
        """A forecast row is a time and a number. One with no time cannot be placed on a clock, and
        guessing where it goes would put rain at the wrong hour."""
        rows = [{"condition": "rainy", "temperature": 70}, HOURS[0]]
        f = forecast.shape(resp("weather.home", rows), None, "weather.home")
        self.assertEqual(len(f["hourly"]), 1)

    def test_readings_that_are_not_numbers(self):
        """Integrations are not consistent about types, and a string must not reach a panel as the
        literal text on the screen."""
        rows = [{"datetime": "2026-09-15T13:00:00+00:00", "condition": "sunny", "temperature": "82.5", "precipitation_probability": "nope"}]
        f = forecast.shape(resp("weather.home", rows), None, "weather.home")
        self.assertEqual(f["hourly"][0]["temperature"], 82.5)
        self.assertIsNone(f["hourly"][0]["rain"])

    def test_a_datetime_object_passes_as_iso(self):
        rows = [{"datetime": datetime(2026, 9, 15, 13, tzinfo=UTC), "condition": "sunny", "temperature": 80}]
        f = forecast.shape(resp("weather.home", rows), None, "weather.home")
        self.assertEqual(f["hourly"][0]["at"], "2026-09-15T13:00:00+00:00")

    def test_only_as_far_ahead_as_anybody_reads(self):
        many = [{"datetime": f"2026-09-15T{h % 24:02d}:00:00+00:00", "condition": "sunny", "temperature": 70} for h in range(40)]
        f = forecast.shape(resp("weather.home", many), resp("weather.home", many), "weather.home")
        self.assertEqual(len(f["hourly"]), forecast.HOURS)
        self.assertEqual(len(f["daily"]), forecast.DAYS)


class FetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_asks_for_both_types(self):
        ha = mock.Mock()
        ha.forecast = mock.AsyncMock(side_effect=[resp("weather.home", HOURS), resp("weather.home", DAYS)])
        f = await forecast.fetch(ha, "weather.home")
        self.assertEqual([c.args[1] for c in ha.forecast.await_args_list], ["hourly", "daily"])
        self.assertEqual(len(f["hourly"]), 2)
        self.assertEqual(len(f["daily"]), 2)

    async def test_one_type_refused_does_not_lose_the_other(self):
        ha = mock.Mock()
        ha.forecast = mock.AsyncMock(side_effect=[RuntimeError("hourly not supported"), resp("weather.home", DAYS)])
        f = await forecast.fetch(ha, "weather.home")
        self.assertEqual(f["hourly"], [])
        self.assertEqual(len(f["daily"]), 2)

    async def test_no_weather_entity_asks_nothing(self):
        ha = mock.Mock()
        ha.forecast = mock.AsyncMock()
        self.assertIsNone(await forecast.fetch(ha, None))
        ha.forecast.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
