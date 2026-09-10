"""Sensing a room from somewhere other than the thermostat.

A thermostat only knows the temperature where it hangs. Pick another sensor the house can see and the
number on the card becomes what you want *there*: the brain keeps the thermostat's setpoint offset by
the difference between the two readings, so the room with the sensor lands on the number. Nest's own
remote sensors are invisible to Home Assistant, so this is how the house does what the Nest app does,
with any sensor and any thermostat. Deterministic, logged with source="comfort", and only in heat or
cool: in auto the thermostat keeps its own range and its own sensor.

Three things keep it from running away with the equipment. The thermostat's own reading answers the
plant far faster than a sensor two rooms off, so correcting on the raw difference between them feeds
back on itself: the setpoint chases the reading it just moved, all the way to the thermostat's floor.
MAX_OFFSET bounds how far from `wanted` a correction may land, which turns that chase into a limp.
SETTLE is a compressor's minimum rest, and it is remembered in the event log so a hub that restarts in
a loop cannot hammer a compressor. STALE drops a sensor that has stopped reporting, and the thermostat
goes back to its own reading rather than steering by a number that stopped being true hours ago.
"""
import json, logging, time

log = logging.getLogger("hub.comfort")
SETTLE = 300       # seconds between corrections for one thermostat: a compressor needs five minutes between starts
STALE = 3600       # a sensor older than this is not trusted; the thermostat runs on its own reading
MAX_OFFSET_F = 5.0   # how far a correction may sit from `wanted`, in °F, so the loop cannot wind up
MAX_OFFSET_C = 2.5   # the same in °C


def round_to(x: float, step: float) -> float:
    return round(round(x / step) * step, 1)


def setpoint_for(wanted: float, sensor_temp: float, thermostat_temp: float, step: float, lo: float, hi: float,
                 max_offset: float) -> float:
    """Where to put the thermostat so the sensor's room reaches `wanted`. Never further than `max_offset` from
    `wanted`: the difference between the two readings widens as the correction takes effect, and without a bound
    each look would push the setpoint further in the same direction until it hit the thermostat's floor. Stays a
    step inside the thermostat's limits too: HA rounds those for display and refuses the last fraction of a degree."""
    target = round_to(wanted + (thermostat_temp - sensor_temp), step)
    target = max(wanted - max_offset, min(wanted + max_offset, target))
    return max(lo + step, min(hi - step, target))


def in_unit(value: float, from_unit: str | None, to_unit: str | None) -> float:
    """A temperature in the thermostat's unit. Sensors may still report in their own (°C from a Nest)."""
    if not from_unit or not to_unit: return value     # no unit stated: take it as already in the house's
    f, t = ("F" in from_unit), ("F" in to_unit)
    if f == t: return value
    return value * 9 / 5 + 32 if t else (value - 32) * 5 / 9


class Comfort:
    def __init__(self, hub):
        self.hub = hub
        self.cfg: dict[str, dict] = dict(hub.settings.get("comfort") or {})   # climate id -> {"sensor": id, "wanted": temp}
        self._acted: dict[str, float] = {}
        self._untrusted: set[str] = set()      # thermostats whose sensor has gone quiet, so it is said once

    # ---- what the card shows ----
    def _step(self) -> float:
        return 1.0 if "F" in (self.hub.temp_unit or "") else 0.5

    def _max_offset(self) -> float:
        return MAX_OFFSET_F if "F" in (self.hub.temp_unit or "") else MAX_OFFSET_C

    def _usable(self, sensor) -> bool:
        """A reading the thermostat may steer by: the sensor is answering, and it has reported recently enough
        that the number still describes the room."""
        if sensor.state in ("unavailable", "unknown"): return False
        return time.time() - (sensor.seen or 0) <= STALE

    def _sensor(self, sensor_id):
        d = self.hub.home.devices.get(sensor_id)
        if not d or d.capability != "sensor.temperature": return None
        return d

    def _reading(self, sensor):
        try: return round(in_unit(float(sensor.state), sensor.attrs.get("unit_of_measurement"), self.hub.temp_unit), 1)
        except (TypeError, ValueError): return None

    def describe(self, climate_id: str) -> dict:
        """The extras a climate device carries while it senses from elsewhere."""
        c = self.cfg.get(climate_id)
        if not c: return {}
        s = self._sensor(c["sensor"])
        room = self.hub.home.rooms.get(s.room_id) if s else None
        return {"sense_from": c["sensor"], "sense_name": (room.name if room and room.id != "unassigned" else (s.name if s else "a sensor")),
                "sense_temp": self._reading(s) if s else None, "wanted": c.get("wanted")}

    def _apply_extras(self, climate_id: str):
        ex = self.hub.home.extras.setdefault(climate_id, {})
        for k in ("sense_from", "sense_name", "sense_temp", "wanted"): ex.pop(k, None)
        ex.update(self.describe(climate_id))
        if not ex: self.hub.home.extras.pop(climate_id, None)
        dev = self.hub.home.devices.get(climate_id)
        if dev:
            dev.attrs = {k: v for k, v in dev.attrs.items() if k not in ("sense_from", "sense_name", "sense_temp", "wanted")}
            dev.attrs.update(self.describe(climate_id))
            self.hub._broadcast(json.dumps({"type": "device", "device": dev.__dict__}))

    def load(self):
        for cid in list(self.cfg):
            self._apply_extras(cid)
            self._seed_acted(cid)

    def _seed_acted(self, climate_id: str):
        """A restart must not shorten a compressor's rest. The last correction is in the event log, so a hub that
        keeps restarting picks the wait up where it left off instead of moving the thermostat on every boot."""
        try: rows = self.hub.log.recent(10, subject=climate_id, kinds=("comfort",))
        except Exception: return
        # only a correction carries the setpoint it moved from; choosing a sensor, changing the target and
        # losing a sensor all log against the same thermostat with no `old`.
        ts = next((r["ts"] for r in rows if r.get("source") == "comfort" and r.get("old") is not None), None)
        if ts: self._acted[climate_id] = max(self._acted.get(climate_id, 0), ts)

    def _save(self):
        self.hub.settings.set(comfort=self.cfg)

    # ---- what a person does ----
    async def set_sensor(self, dev, sensor_id):
        """Sense this thermostat's room from `sensor_id`, or from itself again (None)."""
        if sensor_id is None:
            self.cfg.pop(dev.id, None); self._save(); self._apply_extras(dev.id)
            self.hub.log.add("comfort", dev.id, None, "thermostat's own sensor", source="user")
            return
        s = self._sensor(sensor_id)
        if not s: raise ValueError("that is not a temperature sensor the house knows")
        wanted = self.cfg.get(dev.id, {}).get("wanted") or dev.attrs.get("temperature") or dev.attrs.get("current_temperature")
        self.cfg[dev.id] = {"sensor": sensor_id, "wanted": wanted}
        self._save(); self._apply_extras(dev.id)
        self.hub.log.add("comfort", dev.id, None, sensor_id, source="user", detail={"wanted": wanted})
        self._acted.pop(dev.id, None)
        await self.check(dev.id, why="sensor chosen")

    def sensing(self, climate_id: str) -> bool:
        return climate_id in self.cfg

    async def want(self, dev, temperature: float):
        """The number on the card while sensing from elsewhere: what the sensor's room should reach."""
        self.cfg[dev.id]["wanted"] = float(temperature)
        self._save(); self._apply_extras(dev.id)
        self.hub.log.add("comfort", dev.id, None, f"want {temperature}", source="user")
        self._acted.pop(dev.id, None)
        await self.check(dev.id, why="target changed")

    # ---- keeping the room there ----
    async def on_state(self, dev):
        """A thermostat or a sensor changed: every thermostat that depends on it takes another look."""
        for cid, c in self.cfg.items():
            if dev.id == cid or dev.id == c["sensor"]:
                await self.check(cid, why=f"{dev.id} changed")

    async def check(self, climate_id: str, why: str = "tick"):
        c = self.cfg.get(climate_id)
        dev = self.hub.home.devices.get(climate_id)
        if not c or not dev or dev.state not in ("heat", "cool"): return
        s = self._sensor(c["sensor"])
        sensor_temp = self._reading(s) if s and self._usable(s) else None
        self._trust(climate_id, c["sensor"], sensor_temp is not None)
        here = dev.attrs.get("current_temperature")
        current = dev.attrs.get("temperature")
        if sensor_temp is None or here is None or current is None or c.get("wanted") is None: return
        if time.time() - self._acted.get(climate_id, 0) < SETTLE: return
        step = self._step()
        target = setpoint_for(float(c["wanted"]), sensor_temp, float(here), step, float(dev.attrs.get("min_temp") or 5),
                              float(dev.attrs.get("max_temp") or 35), self._max_offset())
        if abs(target - float(current)) < step * 0.75: return
        try:
            await self.hub.ha.call("climate", "set_temperature", climate_id, temperature=target)
        except Exception as e:
            log.warning("comfort: could not move %s: %s", climate_id, e); return
        self._acted[climate_id] = time.time()
        self.hub.log.add("comfort", climate_id, str(current), str(target), source="comfort",
                         detail={"sensor": c["sensor"], "sensor_temp": sensor_temp, "thermostat_temp": here, "wanted": c["wanted"], "why": why})
        log.info("comfort: %s -> %s (wanted %s at %s reading %s, thermostat reads %s)", climate_id, target, c["wanted"], c["sensor"], sensor_temp, here)

    def _trust(self, climate_id: str, sensor_id: str, usable: bool):
        """Say once when a sensor stops being steered by, and once when it comes back. Silence either way would
        leave a thermostat quietly on its own reading with the card still showing the other room's number."""
        if usable and climate_id in self._untrusted:
            self._untrusted.discard(climate_id)
            self.hub.log.add("comfort", climate_id, None, "sensing again", source="comfort", detail={"sensor": sensor_id})
            log.info("comfort: %s is steering by %s again", climate_id, sensor_id)
        elif not usable and climate_id not in self._untrusted:
            self._untrusted.add(climate_id)
            self.hub.log.add("comfort", climate_id, None, "on its own sensor", source="comfort",
                             detail={"sensor": sensor_id, "why": "that sensor has stopped reporting"})
            log.warning("comfort: %s has stopped reporting; %s runs on its own reading", sensor_id, climate_id)

    async def tick(self):
        for cid in list(self.cfg):
            try: await self.check(cid)
            except Exception: log.exception("comfort %s", cid)
