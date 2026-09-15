"""Semantic model: home → rooms → devices → one capability each.

The vocabulary is deliberately small. Anything HA exposes that does not fit is invisible to the
product (it is still reachable through the Advanced door).
"""
import re, time
from dataclasses import dataclass, field, asdict
from datetime import datetime

CAP_BY_DOMAIN = {"light": "light", "switch": "switch", "media_player": "media", "cover": "cover",
                 "climate": "climate", "lock": "lock", "fan": "fan", "camera": "camera", "vacuum": "vacuum"}
MOTION_CLASSES = {"motion", "occupancy", "presence"}
SENSOR_CLASSES = {"temperature", "humidity", "illuminance"}   # power/energy belong to an energy view, not room tiles
# A temperature inside a fridge or an oven is an appliance reading, not the room's. Those stay invisible
# until there is an appliances view; a room's tiles and a thermostat's sensor picker never see them.
APPLIANCE = re.compile(r"\b(fridge|refrigerator|freezer|oven|range|cavity|cooktop|stove|hob|dishwasher|washer|dryer|water heater|"
                       r"boiler|grill|smoker|sous ?vide|setpoint|probe|kettle|coffee|wine|humidor|aquarium|pool|spa|hot tub)\b", re.I)


def seen_at(s) -> float:
    """When the driver last heard from an entity. HA's states carry ISO timestamps; if none of them parse,
    take it as now — an age we cannot read must not make a working sensor look dead."""
    for key in ("last_reported", "last_updated", "last_changed"):
        v = s.get(key)
        if not v: continue
        try: return datetime.fromisoformat(v).timestamp()
        except (TypeError, ValueError): continue
    return time.time()


def changed_at(s) -> float:
    """When an entity last CHANGED, as against when it was last heard from. HA keeps the two apart and a
    rule that waits needs the change: a lock that reports itself every minute has not been unlocked a
    minute. Unreadable, or absent, is taken as now -- the same way round as `seen_at`, so a timestamp we
    cannot parse starts a wait rather than instantly ending one."""
    v = s.get("last_changed") or s.get("last_updated")
    try: return datetime.fromisoformat(v).timestamp()
    except (TypeError, ValueError): return time.time()


def capability_for(domain: str, device_class: str | None, words: str = "") -> str | None:
    """`words` is everything that names the entity and the device it belongs to; it decides sensor versus appliance."""
    if domain in CAP_BY_DOMAIN: return CAP_BY_DOMAIN[domain]
    if domain == "binary_sensor" and device_class in MOTION_CLASSES: return "motion"
    if domain == "binary_sensor" and device_class in ("door", "window", "opening"): return "contact"
    if domain == "sensor" and device_class in SENSOR_CLASSES:
        return None if APPLIANCE.search(words or "") else f"sensor.{device_class}"
    return None


# ---- what a thing is, when the house has it wrong (docs/kinds.md) ----
# A device may be shown as any kind whose controls it can already serve, and no other. What each kind
# needs of a device is below; a kind is offered where the device serves exactly that and nothing more,
# which is why a plug may be a lamp (both want an on and an off) and may not be a blind (which wants a
# position) or a thermostat (which wants a temperature). The offer is computed from this table, never
# typed, and that is what stops the panel drawing a brightness slider onto something that cannot dim.
CONTROLS = {"light": ("onoff",), "switch": ("onoff",), "fan": ("onoff",),
            "media": ("onoff", "playing"), "cover": ("position",), "climate": ("temperature",),
            "lock": ("bolt",), "vacuum": ("errand",), "camera": ("picture",)}
# Neither re-typed into nor out of. docs/voice.md gates what may be opened and unlocked by direction, and
# a kind override is a way to walk around that gate by re-typing the thing the gate is about. The table
# above already keeps both alone in their groups; this is the rule said out loud, so that adding a kind
# later cannot quietly open the door.
GATED = ("lock", "cover")


def kinds_for(capability: str) -> list[str]:
    """Every kind this thing may be shown as, its own included, in the order the panel offers them.
    Empty where there is no choice to make: a reading is not a thing to control, and a lock is not a
    thing to re-type."""
    cap = (capability or "").split(".")[0]
    if cap in GATED or cap not in CONTROLS: return []
    wants = CONTROLS[cap]
    offer = [k for k, needs in CONTROLS.items() if needs == wants and k not in GATED]
    return offer if len(offer) > 1 else []


def kind_of(d) -> str:
    """What the house should treat a device AS: the owner's answer where they have given one, the
    driver's otherwise. Everything that draws, names or parses reads this.

    The three places that pick a Home Assistant service read `capability` instead, and must keep
    doing so -- api.act(), the timer guard beside it, and intents.plan(). Writing "light" into the
    capability of a switch entity makes the brain call light.turn_on on it, HA refuses, and the thing
    is left worse than mis-typed: untouchable, and the panel did it."""
    return d.kind or d.capability


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
    seen: float = field(default_factory=time.time)   # when the driver last heard from it; a stale sensor is not steered by
    maker: str | None = None       # who made the unit, from the driver's device registry; the one thing a tile can say about hardware it has no picture of
    kind: str | None = None        # what the OWNER says this is, where they have said anything: a lamp on a plug is a light. Read it through kind_of(), never instead of capability
    since: float = field(default_factory=time.time)  # when it entered the state it is in; a rule's `for` counts from here, and HA's own last_changed survives a restart of this brain
    entry: str | None = None       # the account or radio that brought it (the driver's config entry). What a fault is grouped under: when one stops answering, everything on it goes quiet at once, and health.py says that once instead of once per device


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
        self.lamps: dict[str, str] = {}    # camera id -> the light built into the same unit (Ring floodlight and spotlight cams)
        self.hardware: dict[str, dict] = {}   # driver device id -> {"name", "manufacturer", "model"}: what the maker called the unit, for naming new things
        self.kinds: dict[str, str] = {}    # device id -> what the owner said it is. Kept here so a rebuild carries it; the hub loads and saves it with the rest of the settings

    def attrs_for(self, eid, cap, a):
        """HA's attributes plus what the brain knows. While the brain runs a fan timer the fan is on whatever the
        thermostat has got round to reporting (Nest tells HA about its fan timer late)."""
        extra = self.extras.get(eid, {})
        out = {**self._keep_attrs(cap, a), **extra}
        if cap == "camera" and eid in self.lamps: out["light"] = self.lamps[eid]
        if extra.get("fan_until", 0) > time.time(): out["fan_mode"] = "on"
        return out

    @staticmethod
    def _keep_attrs(cap, a):
        keys = {"light": ("brightness", "color_temp_kelvin", "rgb_color", "supported_color_modes"),
                "media": ("volume_level", "media_title", "media_artist", "app_name", "source", "entity_picture"),
                "cover": ("current_position",),
                "climate": ("temperature", "current_temperature", "hvac_modes", "hvac_action", "target_temp_low", "target_temp_high",
                            "min_temp", "max_temp", "current_humidity", "preset_mode", "preset_modes", "fan_mode", "fan_modes"),
                "fan": ("percentage",), "sensor": ("unit_of_measurement",)}.get(cap.split(".")[0], ())
        return {k: a[k] for k in keys if k in a}

    def build(self, areas, ha_devices, entities, states):
        was = self.rooms
        self.rooms = {a["area_id"]: Room(a["area_id"], a["name"]) for a in areas}
        self.rooms["unassigned"] = Room("unassigned", "New devices")   # things that have not been put in a room yet
        for rid, r in self.rooms.items():           # a rebuild must not forget what rooms were told or when they last moved
            if rid in was:
                r.intent, r.set_by, r.hold_until, r.motion_at = was[rid].intent, was[rid].set_by, was[rid].hold_until, was[rid].motion_at
        dev_area = {d["id"]: d.get("area_id") for d in ha_devices}
        dev_words = {d["id"]: " ".join(str(d.get(k) or "") for k in ("name_by_user", "name", "model", "manufacturer")) for d in ha_devices}
        dev_entry = {d["id"]: next(iter(d.get("config_entries") or []), None) for d in ha_devices}   # what brought the hardware, for entries that do not name it themselves
        self.hardware = {d["id"]: {"name": d.get("name_by_user") or d.get("name") or "", "manufacturer": d.get("manufacturer") or "", "model": d.get("model") or ""} for d in ha_devices}
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
            words = " ".join([eid, str(s["attributes"].get("friendly_name") or ""), str(e.get("original_name") or ""), dev_words.get(e.get("device_id") or "", "")])
            cap = capability_for(domain, s["attributes"].get("device_class") or e.get("original_device_class"), words)
            if not cap: continue
            room = e.get("area_id") or dev_area.get(e.get("device_id")) or "unassigned"
            if room not in self.rooms: room = "unassigned"
            name = s["attributes"].get("friendly_name", eid)
            if cap == "camera":
                for suffix in (" Live view", " Live View", " Camera"):
                    if name.endswith(suffix): name = name[: -len(suffix)]
            d = Device(eid, name, room, cap, s["state"], self.attrs_for(eid, cap, s["attributes"]), e.get("device_id"), bool(e.get("area_id")), seen_at(s), since=changed_at(s))
            d.entry = e.get("config_entry_id") or dev_entry.get(e.get("device_id") or "")
            d.maker = self.hardware.get(e.get("device_id") or "", {}).get("manufacturer") or None
            d.kind = self.shown_as(eid, cap)
            self.devices[eid] = d
            self.rooms[room].devices.append(d)
        # A camera with a lamp built in: the viewer offers the lamp beside the picture, the way Ring's own app does.
        # The lamp stays a light of its own as well, so the room and its scenes can use it like any other.
        lights = {}
        for d in self.devices.values():
            if d.capability == "light" and d.hw: lights.setdefault(d.hw, d.id)
        self.lamps = {d.id: lights[d.hw] for d in self.devices.values() if d.capability == "camera" and d.hw in lights}
        for cid, lid in self.lamps.items(): self.devices[cid].attrs["light"] = lid
        return self

    def shown_as(self, eid: str, capability: str) -> str | None:
        """The owner's kind for this device, or None where they have not given one or it no longer fits.

        The stored answer is kept either way. A thing whose capability changes underneath it — a plug
        pulled out and a real bulb put in — keeps what the owner said as long as the new thing can still
        serve it, and the record survives a spell where it cannot rather than being quietly thrown away."""
        k = self.kinds.get(eid)
        return k if k and k != capability and k in kinds_for(capability) else None

    def apply_state(self, entity_id, new_state) -> Device | None:
        d = self.devices.get(entity_id)
        if not d or not new_state: return None
        d.state = new_state["state"]
        d.attrs = self.attrs_for(entity_id, d.capability, new_state["attributes"])
        d.name = new_state["attributes"].get("friendly_name", d.name)   # a rename shows up here first
        d.seen = seen_at(new_state)
        d.since = changed_at(new_state)
        return d

    def to_dict(self):
        return {"rooms": [asdict(r) for r in self.rooms.values() if r.devices or r.id != "unassigned"]}
