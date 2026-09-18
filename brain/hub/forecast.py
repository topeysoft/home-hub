# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The forecast, which the weather state does not carry.

Home Assistant took the `forecast` attribute off weather entities in 2024.4. What
is left on the state is the current condition and a handful of readings, which is
what `_weather_of()` reads and all the panel has ever had. The forecast moved
behind the `weather.get_forecasts` service, and a service is asked rather than
watched: it answers once, only when called, and only when the call says
`return_response`.

So this module is a small pump rather than a listener. It is asked on the hour,
and again when the house picks a different weather entity, and it hands the panel
a shape it can read without knowing anything about HA. NOT on every state change:
a weather entity reports a new temperature every few minutes and the rows behind
it move far more slowly than that -- refetching on each one would be a service
call a minute for a payload that changed once.

WHAT IS NOT HERE, deliberately: any judgment about what the forecast MEANS.
"Rain from 4 PM" is a sentence, and sentences belong to the panel -- it already
owns the condition words, the clock and the locale, the same way it owns sunrise
from the location rather than asking the hub for it. This module's job is to turn
HA's rows into plain numbers and stop.
"""
import logging
from datetime import datetime

log = logging.getLogger(__name__)

# How far ahead is worth carrying. The panel draws eight hours and three days; a
# little more than that leaves room to change the drawing without changing the
# hub, and a lot more is a payload nobody reads.
HOURS = 12
DAYS = 5


def _num(v):
    """A reading, or None. HA is not consistent about types across integrations and a string
    temperature must not become the literal text on a panel."""
    if v is None: return None
    try: return float(v)
    except (TypeError, ValueError): return None


def _at(row):
    """The row's own timestamp, passed through as ISO. Every integration sends one; a row without
    one cannot be placed on a clock and is dropped rather than guessed at."""
    v = row.get("datetime")
    if not v: return None
    if isinstance(v, datetime): return v.isoformat()
    try:
        datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return str(v)


def _hour(row):
    at = _at(row)
    if at is None: return None
    return {"at": at, "condition": row.get("condition") or "",
            "temperature": _num(row.get("temperature")),
            "rain": _num(row.get("precipitation_probability"))}


def _day(row):
    at = _at(row)
    if at is None: return None
    # `temperature` is the day's HIGH in a daily forecast and `templow` its low. A day missing its
    # low is still worth showing -- a high on its own is most of what a row says.
    return {"at": at, "condition": row.get("condition") or "",
            "high": _num(row.get("temperature")), "low": _num(row.get("templow")),
            "rain": _num(row.get("precipitation_probability"))}


def shape(hourly_response, daily_response, entity_id):
    """HA's two service responses -> what the panel is given. Either half may be missing: an
    integration that only does daily (or only hourly) is common, and half a forecast is worth more
    than none."""
    def rows(resp):
        # {"weather.home": {"forecast": [ ... ]}}
        if not isinstance(resp, dict): return []
        one = resp.get(entity_id) or (next(iter(resp.values()), None) if len(resp) == 1 else None)
        return (one or {}).get("forecast") or []

    hourly = [h for h in (_hour(r) for r in rows(hourly_response)[:HOURS]) if h]
    daily = [d for d in (_day(r) for r in rows(daily_response)[:DAYS]) if d]
    return {"hourly": hourly, "daily": daily} if (hourly or daily) else None


async def fetch(ha, entity_id):
    """Ask for both forecasts. Returns the shape above, or None.

    Each type is asked for separately and a failure of one is not a failure of both: an integration
    that serves daily and refuses hourly is a normal thing to be, and the panel handles half.
    """
    if not entity_id: return None
    out = {}
    for kind in ("hourly", "daily"):
        try:
            out[kind] = await ha.forecast(entity_id, kind)
        except Exception as e:
            # at debug: a weather integration without hourly says so on every refresh, and that is
            # not news after the first time
            log.debug("no %s forecast from %s: %s", kind, entity_id, e)
            out[kind] = None
    return shape(out["hourly"], out["daily"], entity_id)
