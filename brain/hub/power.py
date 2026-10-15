# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The house's own power: what the sun on the roof is making, where it goes, the battery, and the grid.

design/energy/, B with C's sun. The wall says something about power only when it changes what somebody
would do -- the battery is full and the roof is still sending power away, the grid is down and the
battery has the house, the power is back -- and the sun in the weather drawing warms with what the roof
is making. Everything else waits in the pane for whoever opens it.

A Tesla gateway comes in through Home Assistant's own Powerwall setup, and its readings are found by the
key that setup gives each one (`translation_key`), never by a name: a household renames things, and the
key is what the setup itself says the reading is. None of it is a device in a room. Two Powerwalls
behind one gateway are one system to the gateway and to the house.
"""
import time
from datetime import datetime

from .model import changed_at, kilowatts

PLATFORMS = {"powerwall"}
ROLES = {"solar_instant_power": "solar", "load_instant_power": "house", "battery_instant_power": "battery",
         "site_instant_power": "grid", "charge": "charge", "backup_reserve": "reserve", "grid_status": "grid_up",
         "solar_export": "made", "load_import": "used", "battery_remaining": "left"}

# Sun to spare: the battery is full and the roof is still sending this much to the grid. Both ways are
# held for SETTLE first, so a cloud going over does not make the line come and go.
SPARE_ON, SPARE_OFF, FULL, SETTLE = 1.0, 0.3, 95, 600
BACK_FOR = 3600   # how long "The power is back" is said after it is
DAY_EVERY = 300   # recorder statistics are written every five minutes; asking more often learns nothing


def parts(entities) -> dict[str, list[str]]:
    """Role -> the entity ids that carry it. Empty unless there is a system here at all."""
    found: dict[str, list[str]] = {}
    for e in entities:
        if e.get("platform") not in PLATFORMS or e.get("disabled_by"): continue
        role = ROLES.get(e.get("translation_key") or "")
        if role: found.setdefault(role, []).append(e["entity_id"])
    return found if "solar" in found or "charge" in found else {}


def number(s: dict | None) -> float | None:
    try: return float(s["state"])
    except (TypeError, ValueError, KeyError): return None


def kwh(s: dict | None) -> float | None:
    v = number(s)
    if v is None: return None
    unit = ((s or {}).get("attributes") or {}).get("unit_of_measurement") or "kWh"
    return v / 1000 if unit == "Wh" else v


class Power:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.parts: dict[str, list[str]] = {}
        self.roles: dict[str, str] = {}
        self.states: dict[str, dict] = {}
        self.spare = False
        self._turning: float | None = None   # when the reading first said spare should flip; it flips after SETTLE
        self.out_since: float | None = None
        self.back: dict | None = None        # {"at", "lasted"}: the grid came back, said for BACK_FOR
        self._day: dict | None = None
        self._day_at = 0.0

    def load(self, entities, states):
        self.parts = parts(entities)
        self.roles = {eid: role for role, eids in self.parts.items() for eid in eids}
        self.states = {s["entity_id"]: s for s in states if s["entity_id"] in self.roles}
        self._day = None
        self._judge()

    def exists(self) -> bool:
        return bool(self.parts)

    def on_state(self, eid: str, new: dict | None) -> bool:
        """True when the reading is one of ours, whether or not anything worth saying changed."""
        if eid not in self.roles: return False
        if new: self.states[eid] = new
        else: self.states.pop(eid, None)
        self._judge()
        return True

    def _state(self, role):
        eids = self.parts.get(role) or []
        return self.states.get(eids[0]) if eids else None

    def _kw(self, role):
        return kilowatts(self._state(role))

    def grid_up(self) -> bool | None:
        s = self._state("grid_up")
        return {"on": True, "off": False}.get((s or {}).get("state"))

    def _judge(self):
        now, up = self.clock(), self.grid_up()
        if up is False and self.out_since is None:
            self.out_since, self.back = changed_at(self._state("grid_up")), None
        elif up is True and self.out_since is not None:
            self.back, self.out_since = {"at": now, "lasted": max(0.0, now - self.out_since)}, None
        if self.back and now - self.back["at"] > BACK_FOR: self.back = None
        if up is False:
            self.spare, self._turning = False, None
            return
        grid, charge = self._kw("grid"), number(self._state("charge"))
        out = -grid if grid is not None else None
        full = charge >= FULL if charge is not None else "charge" not in self.parts
        flip = (out is None or out < SPARE_OFF) if self.spare else (out is not None and out >= SPARE_ON and full)
        if not flip: self._turning = None
        elif self._turning is None: self._turning = now
        elif now - self._turning >= SETTLE: self.spare, self._turning = not self.spare, None

    def now(self) -> dict | None:
        if not self.parts: return None
        self._judge()
        battery, left = self._kw("battery"), [kwh(self.states.get(e)) for e in self.parts.get("left", [])]
        return {
            "solar": self._kw("solar"), "house": self._kw("house"),
            "battery": -battery if battery is not None else None,   # into the battery; the gateway counts the other way
            "grid": self._kw("grid"),                                # from the grid; negative is going out to it
            "charge": number(self._state("charge")), "reserve": number(self._state("reserve")),
            "grid_up": self.grid_up(), "left": round(sum(left), 1) if left and None not in left else None,
            "has_battery": "charge" in self.parts,
            "spare": self.spare, "out_since": self.out_since, "back": self.back,
        }

    def said(self) -> tuple:
        """What the band would say, so a change to it goes out at once and not with the next quiet update."""
        return (self.exists(), self.spare, self.out_since, bool(self.back), self.grid_up())

    async def day(self, ha, tz) -> dict:
        """Today so far, from Home Assistant's own statistics: what was made and used since midnight, the
        sun and the house through the day in five-minute steps, and the most the roof has made in a month,
        which is what the sun's warmth in the drawing is measured against."""
        if self._day is not None and self.clock() - self._day_at < DAY_EVERY: return self._day
        first = lambda role: (self.parts.get(role) or [None])[0]
        out: dict = {"made": None, "used": None, "peak": None, "curve": []}

        async def change(role):
            if not first(role): return None
            r = await ha.send("recorder/statistic_during_period", statistic_id=first(role), calendar={"period": "day"},
                              types=["change"], units={"energy": "kWh"})
            return round(r["change"], 1) if r and r.get("change") is not None else None
        try: out["made"], out["used"] = await change("made"), await change("used")
        except Exception: pass
        midnight = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        out["since"] = midnight.timestamp()
        ids = [x for x in (first("solar"), first("house")) if x]
        if ids:
            try:
                rows = await ha.send("recorder/statistics_during_period", start_time=midnight.isoformat(), statistic_ids=ids,
                                     period="5minute", types=["mean"], units={"power": "kW"}) or {}
                sun, house = rows.get(first("solar"), []), {r["start"]: r.get("mean") for r in rows.get(first("house"), [])}
                out["curve"] = [{"at": r["start"] / 1000, "solar": r.get("mean"), "house": house.get(r["start"])} for r in sun]
            except Exception: pass
            try:
                r = await ha.send("recorder/statistic_during_period", statistic_id=first("solar"), rolling_window={"duration": {"days": 30}},
                                  types=["max"], units={"power": "kW"})
                out["peak"] = r.get("max") if r else None
            except Exception: pass
        self._day, self._day_at = out, self.clock()
        return out
