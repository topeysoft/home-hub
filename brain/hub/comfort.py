"""Sensing a room from somewhere other than the thermostat.

A thermostat only knows the temperature where it hangs. Pick another sensor the house can see and the
number on the card becomes what you want *there*: the brain keeps the thermostat's setpoint offset by
the difference between the two readings, so the room with the sensor lands on the number. Nest's own
remote sensors are invisible to Home Assistant, so this is how the house does what the Nest app does,
with any sensor and any thermostat. Deterministic, logged with source="comfort", and only in heat or
cool: in auto the thermostat keeps its own range and its own sensor.
"""
import json, logging, time

log = logging.getLogger("hub.comfort")
SETTLE = 90        # seconds between corrections for one thermostat: the room needs time to answer
STALE = 3600       # a sensor older than this is not trusted; the thermostat runs on its own reading


def round_to(x: float, step: float) -> float:
    return round(round(x / step) * step, 1)


def setpoint_for(wanted: float, sensor_temp: float, thermostat_temp: float, step: float, lo: float, hi: float) -> float:
    """Where to put the thermostat so the sensor's room reaches `wanted`. Stays a step inside the thermostat's
    limits: HA rounds those for display and refuses the last fraction of a degree."""
    return max(lo + step, min(hi - step, round_to(wanted + (thermostat_temp - sensor_temp), step)))


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

    # ---- what the card shows ----
    def _step(self) -> float:
        return 1.0 if "F" in (self.hub.temp_unit or "") else 0.5

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
        for cid in list(self.cfg): self._apply_extras(cid)

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
        sensor_temp = self._reading(s) if s and s.state not in ("unavailable", "unknown") else None
        here = dev.attrs.get("current_temperature")
        current = dev.attrs.get("temperature")
        if sensor_temp is None or here is None or current is None or c.get("wanted") is None: return
        if time.time() - self._acted.get(climate_id, 0) < SETTLE: return
        step = self._step()
        target = setpoint_for(float(c["wanted"]), sensor_temp, float(here), step, float(dev.attrs.get("min_temp") or 5), float(dev.attrs.get("max_temp") or 35))
        if abs(target - float(current)) < step * 0.75: return
        try:
            await self.hub.ha.call("climate", "set_temperature", climate_id, temperature=target)
        except Exception as e:
            log.warning("comfort: could not move %s: %s", climate_id, e); return
        self._acted[climate_id] = time.time()
        self.hub.log.add("comfort", climate_id, str(current), str(target), source="comfort",
                         detail={"sensor": c["sensor"], "sensor_temp": sensor_temp, "thermostat_temp": here, "wanted": c["wanted"], "why": why})
        log.info("comfort: %s -> %s (wanted %s at %s reading %s, thermostat reads %s)", climate_id, target, c["wanted"], c["sensor"], sensor_temp, here)

    async def tick(self):
        for cid in list(self.cfg):
            try: await self.check(cid)
            except Exception: log.exception("comfort %s", cid)
