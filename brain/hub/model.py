"""Semantic model: home → rooms → devices → one capability each.

The vocabulary is deliberately small. Anything HA exposes that does not fit is invisible to the
product (it is still reachable through the Advanced door).
"""
import time
from dataclasses import dataclass, field, asdict

CAP_BY_DOMAIN = {"light": "light", "switch": "switch", "media_player": "media", "cover": "cover",
                 "climate": "climate", "lock": "lock", "fan": "fan", "camera": "camera", "vacuum": "vacuum"}
MOTION_CLASSES = {"motion", "occupancy", "presence"}
SENSOR_CLASSES = {"temperature", "humidity", "illuminance"}   # power/energy belong to an energy view, not room tiles


def capability_for(domain: str, device_class: str | None) -> str | None:
    if domain in CAP_BY_DOMAIN: return CAP_BY_DOMAIN[domain]
    if domain == "binary_sensor" and device_class in MOTION_CLASSES: return "motion"
    if domain == "binary_sensor" and device_class in ("door", "window", "opening"): return "contact"
    if domain == "sensor" and device_class in SENSOR_CLASSES: return f"sensor.{device_class}"
    return None


@dataclass
class Device:
    id: str                 # stable product id = HA entity_id for now
    name: str
    room_id: str
    capability: str
    state: str
    attrs: dict = field(default_factory=dict)
    hw: str | None = None          # the physical thing this belongs to (the driver's device id), for moving rooms
    own_room: bool = False         # room set on this entry itself rather than inherited from the hardware


@dataclass
class Room:
    id: str
    name: str
    devices: list = field(default_factory=list)
    intent: str = "unknown"          # see intents.RoomState
    set_by: str | None = None        # "user", or "rule:<id>": who last set the intent
    hold_until: float | None = None  # rules leave the room alone until then (a hand on the panel set it)
    motion_at: float | None = None   # last motion from any motion device here; idle rules count from it


class Home:
    def __init__(self):
        self.rooms: dict[str, Room] = {}
        self.devices: dict[str, Device] = {}
        self.intent: str = "unknown"     # the last home-wide intent (bedtime, everything off)
        self.extras: dict[str, dict] = {}  # what the brain knows about a device that HA does not (a fan timer's end); shown with its attrs

    def attrs_for(self, eid, cap, a):
        """HA's attributes plus what the brain knows. While the brain runs a fan timer the fan is on whatever the
        thermostat has got round to reporting (Nest tells HA about its fan timer late)."""
        extra = self.extras.get(eid, {})
        out = {**self._keep_attrs(cap, a), **extra}
        if extra.get("fan_until", 0) > time.time(): out["fan_mode"] = "on"
        return out

    @staticmethod
    def _keep_attrs(cap, a):
        keys = {"light": ("brightness", "color_temp_kelvin", "rgb_color", "supported_color_modes"),
                "media": ("volume_level", "media_title", "media_artist", "app_name", "source", "entity_picture"),
                "cover": ("current_position",),
                "climate": ("temperature", "current_temperature", "hvac_modes", "hvac_action", "target_temp_low", "target_temp_high",
                            "min_temp", "max_temp", "current_humidity", "preset_mode", "preset_modes", "fan_mode", "fan_modes"),
                "fan": ("percentage",)}.get(cap.split(".")[0], ())
        return {k: a[k] for k in keys if k in a}

    def build(self, areas, ha_devices, entities, states):
        was = self.rooms
        self.rooms = {a["area_id"]: Room(a["area_id"], a["name"]) for a in areas}
        self.rooms["unassigned"] = Room("unassigned", "New devices")   # things that have not been put in a room yet
        for rid, r in self.rooms.items():           # a rebuild must not forget what rooms were told or when they last moved
            if rid in was:
                r.intent, r.set_by, r.hold_until, r.motion_at = was[rid].intent, was[rid].set_by, was[rid].hold_until, was[rid].motion_at
        dev_area = {d["id"]: d.get("area_id") for d in ha_devices}
        reg = {e["entity_id"]: e for e in entities}
        st = {s["entity_id"]: s for s in states}
        camera_devices = {e["device_id"] for e in entities if e["entity_id"].startswith("camera.") and e.get("device_id")}
        self.devices = {}
        for eid, s in st.items():
            e = reg.get(eid, {})
            if e.get("disabled_by") or e.get("hidden_by") or e.get("entity_category"):
                continue      # diagnostics and config entities are not product surface
            domain = eid.split(".")[0]
            if domain == "switch" and e.get("device_id") in camera_devices:
                continue      # a switch on a camera is a setting (motion detection, siren arm), not a room control
            cap = capability_for(domain, s["attributes"].get("device_class") or e.get("original_device_class"))
            if not cap: continue
            room = e.get("area_id") or dev_area.get(e.get("device_id")) or "unassigned"
            if room not in self.rooms: room = "unassigned"
            name = s["attributes"].get("friendly_name", eid)
            if cap == "camera":
                for suffix in (" Live view", " Live View", " Camera"):
                    if name.endswith(suffix): name = name[: -len(suffix)]
            d = Device(eid, name, room, cap, s["state"], self.attrs_for(eid, cap, s["attributes"]), e.get("device_id"), bool(e.get("area_id")))
            self.devices[eid] = d
            self.rooms[room].devices.append(d)
        return self

    def apply_state(self, entity_id, new_state) -> Device | None:
        d = self.devices.get(entity_id)
        if not d or not new_state: return None
        d.state = new_state["state"]
        d.attrs = self.attrs_for(entity_id, d.capability, new_state["attributes"])
        d.name = new_state["attributes"].get("friendly_name", d.name)   # a rename shows up here first
        return d

    def to_dict(self):
        return {"rooms": [asdict(r) for r in self.rooms.values() if r.devices or r.id != "unassigned"]}
