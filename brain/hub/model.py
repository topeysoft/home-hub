# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
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
# A switch that is a FEATURE of a machine rather than a plug with something on it: a fridge's ice maker, a
# dishwasher's delay start, a pool's heater. Narrower than APPLIANCE on purpose. A kettle or a coffee maker
# on a smart plug is exactly what a plug is for, and Everything off switching it off when the house empties
# is the promise a plug makes; a fridge's ice maker going off with it is a fridge with no ice in the morning.
# The words tried are the entity's and its hardware's together, so "Refrigerator" on the unit names all of
# its switches. What HA calls an outlet stays a plug whatever it is named. docs/kinds.md, *An appliance*.
MACHINE = re.compile(r"\b(fridge|refrigerator|freezer|ice ?maker|ice|dishwasher|washer|washing machine|dryer|oven|"
                     r"range|cooktop|stove|hob|hood|water heater|boiler|furnace|aquarium|pool|spa|hot tub|sauna|wine|humidor)\b", re.I)


# A switch that is LOUD. Nothing in Home Assistant's domains says so -- a siren arrives as a `switch`
# and is indistinguishable from a plug with a lamp on it -- so the only thing that can tell the house
# is its name. Getting this wrong in the safe direction costs somebody a second tap on a plug; getting
# it wrong the other way is a siren at 2am under a stray finger, which is the whole reason `alarm`
# exists as a kind at all. docs/kinds.md, *An alarm, and the tap that woke the baby*.
#
# Narrower than it could be, deliberately. `bell` and `chime` are left out: a doorbell is not the
# thing this rule is for, and every word here has to be one that only ever names something loud.
SIREN = re.compile(r"\b(siren|klaxon|sounder|strobe|horn|alarm)\b", re.I)


def guessed_kind(capability: str, device_class: str | None, words: str = "") -> str | None:
    """What the house makes of a thing from its name, under the owner's word and over the driver's.

    Two guesses, and the loud one is asked first: a thing called an alarm siren is an alarm before it
    is a machine's feature, and reading the words in the other order would put a siren in the group
    that is quietly left out of Everything off rather than the group that asks before it sounds."""
    if capability == "switch" and device_class != "outlet":
        words = words or ""
        if SIREN.search(words): return "alarm"
        if MACHINE.search(words): return "appliance"
    return None


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
#
# `alarm` is in the on/off group for a different reason from the other three, and it is worth saying:
# a siren reaches this house as a `switch` and there is nothing in HA's domains that says "this one is
# loud". Shown as a plug it gets a plug's tile, which fires on one tap -- and the failure mode of a
# stray finger on a plug is a lamp, while the failure mode of a stray finger on this is a siren at 2am.
# The kind is how a person tells the house which of the two it is holding; everything that asks before
# it acts hangs off it (app/src/twice.ts, and the scenes that step over it in intents.py).
#
# `appliance` is in the same group for the opposite reason from `alarm`: nothing about it needs a second
# tap, but nothing about it should be swept up either. A plug promises to go off when the house empties.
# A fridge's ice maker is a switch entity too, and it must not keep that promise.
CONTROLS = {"light": ("onoff",), "switch": ("onoff",), "fan": ("onoff",), "alarm": ("onoff",), "appliance": ("onoff",),
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
    return d.kind or d.guess or d.capability


def default_kind(d) -> str:
    """What this thing is shown as when nobody has said otherwise: the house's guess where it made one,
    the driver's word where it did not. The owner's answer is stored only where it differs from this,
    which is how "it is a plug" over a guessed appliance is a record and not a no-op."""
    return d.guess or d.capability


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
    model: str | None = None       # what the maker calls this model ("Hue white A19"). Said beside the maker on New devices, where a thing is still called whatever the driver called it and the name alone tells nobody which bulb this is
    kind: str | None = None        # what the OWNER says this is, where they have said anything: a lamp on a plug is a light. Read it through kind_of(), never instead of capability
    guess: str | None = None       # what the HOUSE makes of it from its name, under the owner's word: a switch on a fridge is an appliance. guessed_kind() is the only thing that sets it
    hw_name: str | None = None     # what the unit it belongs to is called ("Refrigerator"), so the panel can show a machine's features as one thing
    named_by_unit: bool = False    # HA composes its name from the unit's ("Garage Light" + "Motion"), so renaming the unit renames it; the old style carries its own name and must be renamed by hand
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
        # Which lights somebody has actually chosen a color for. The house has to keep this because
        # HA cannot: a bulb sitting at 2700K is indistinguishable from one a person deliberately set
        # to 2700K, and the difference -- who decided -- is the whole of what Automatic means. Kept
        # in settings beside `kinds` so a restore brings it back with the rest of the house.
        self.color_pinned: set[str] = set()
        self.lamps: dict[str, str] = {}    # camera id -> the light built into the same unit (Ring floodlight and spotlight cams)
        self.eyes: dict[str, str] = {}     # light/switch/fan id -> the motion sensor built into the same unit (a Brilliant switch, a Ring pathlight): docs/units.md
        self.fixtures: dict[str, dict] = {}   # device id -> what a fan-with-a-light's parts know about each other ({"light": id} on the fan, {"fan": id} on the light, "leads" on both): docs/units.md
        self.leads: dict[str, str] = {}    # hardware id -> which part of a fixture is the tile ("fan" or "light"), where the owner has said; fan otherwise. Kept in settings with `kinds`
        self.hardware: dict[str, dict] = {}   # driver device id -> {"name", "manufacturer", "model"}: what the maker called the unit, for naming new things
        self.kinds: dict[str, str] = {}    # device id -> what the owner said it is. Kept here so a rebuild carries it; the hub loads and saves it with the rest of the settings

    def attrs_for(self, eid, cap, a):
        """HA's attributes plus what the brain knows. While the brain runs a fan timer the fan is on whatever the
        thermostat has got round to reporting (Nest tells HA about its fan timer late)."""
        extra = self.extras.get(eid, {})
        out = {**self._keep_attrs(cap, a), **extra}
        if cap == "camera" and eid in self.lamps: out["light"] = self.lamps[eid]
        if eid in self.eyes: out["motion"] = self.eyes[eid]
        out.update(self.fixtures.get(eid, {}))
        if extra.get("fan_until", 0) > time.time(): out["fan_mode"] = "on"
        if cap.split(".")[0] == "light" and eid in self.color_pinned: out["color_pinned"] = True
        return out

    @staticmethod
    def _keep_attrs(cap, a):
        # color_mode, not just rgb_color: HA reports rgb_color whatever mode a bulb is in, and in
        # color_temp mode it is the RGB rendering of the white point. Without the mode the panel
        # cannot tell a bulb somebody set to magenta from a warm white one, and would draw both
        # as colored. See art.ts/bulbColor, which falls back for hubs older than this line.
        keys = {"light": ("brightness", "color_temp_kelvin", "color_mode", "rgb_color", "supported_color_modes"),
                "media": ("volume_level", "media_title", "media_artist", "app_name", "source", "entity_picture"),
                # device_class tells a blind from a garage door, and that is the whole of what decides
                # whether a cover can leave the house with the ordinary kinds or needs the switch that
                # locks need: a bedroom blind is not a way into the house and a garage door is.
                # hub/share.py, WAYS_IN.
                "cover": ("current_position", "device_class"),
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
            d.model = self.hardware.get(e.get("device_id") or "", {}).get("model") or None
            d.hw_name = self.hardware.get(e.get("device_id") or "", {}).get("name") or None
            d.named_by_unit = bool(e.get("has_entity_name"))
            d.guess = guessed_kind(cap, s["attributes"].get("device_class") or e.get("original_device_class"), words)
            d.kind = self.shown_as(eid, cap, d.guess)
            self.devices[eid] = d
            self.rooms[room].devices.append(d)
        # A camera with a lamp built in: the viewer offers the lamp beside the picture, the way Ring's own app does.
        # The lamp stays a light of its own as well, so the room and its scenes can use it like any other.
        lights = {}
        for d in self.devices.values():
            if d.capability == "light" and d.hw: lights.setdefault(d.hw, d.id)
        self.lamps = {d.id: lights[d.hw] for d in self.devices.values() if d.capability == "camera" and d.hw in lights}
        for cid, lid in self.lamps.items(): self.devices[cid].attrs["light"] = lid
        # A switch with a motion sensor built in -- a Brilliant dimmer, a Ring pathlight, a motion switch --
        # is one thing on the wall, and its tile is where its motion belongs. The sensor stays a device of
        # its own as well, so rules and the room's line read it as they always did. docs/units.md.
        eyes = {}
        for d in self.devices.values():
            if d.capability == "motion" and d.hw: eyes.setdefault(d.hw, d.id)
        self.eyes = {d.id: eyes[d.hw] for d in self.devices.values() if d.capability in ("light", "switch", "fan") and d.hw in eyes}
        for cid, mid in self.eyes.items(): self.devices[cid].attrs["motion"] = mid
        # A fan with a light in it: one fixture on the ceiling, two devices to the driver. Each part is told
        # the other, and both are told which of them is the tile -- the fan unless the owner says the light
        # (`leads`). Only a fan and a light pair up: two lights on one double switch are two lights.
        self.fixtures = {}
        fans = {d.hw: d.id for d in self.devices.values() if d.capability == "fan" and d.hw}
        for d in self.devices.values():
            if d.capability == "light" and d.hw in fans and fans[d.hw] not in self.fixtures:
                fid, lead = fans[d.hw], self.lead_for(d.hw)
                self.fixtures[fid] = {"light": d.id, "leads": lead}
                self.fixtures[d.id] = {"fan": fid, "leads": lead}
        for eid, more in self.fixtures.items(): self.devices[eid].attrs.update(more)
        return self

    def lead_for(self, hw: str | None) -> str:
        """Which part of a fixture is the tile: the owner's word where they have given one, the fan otherwise --
        it is the thing on the ceiling, and the light is a part of it."""
        return self.leads.get(hw or "", "fan")

    def set_lead(self, dev, lead: str) -> list:
        """Say which part of this device's fixture is the tile. Returns the parts that changed, for the panel."""
        if lead not in ("fan", "light"): raise ValueError("A fixture is led by its fan or by its light.")
        parts = [d for d in self.devices.values() if d.id in self.fixtures and d.hw == dev.hw]
        if dev.id not in self.fixtures or not parts: raise ValueError(f"{dev.name} is not a fan with a light in it.")
        if lead == "fan": self.leads.pop(dev.hw or "", None)
        else: self.leads[dev.hw or ""] = lead
        for part in parts:
            self.fixtures[part.id]["leads"] = lead
            part.attrs["leads"] = lead
        return parts

    def shown_as(self, eid: str, capability: str, guess: str | None = None) -> str | None:
        """The owner's kind for this device, or None where they have not given one or it no longer fits.

        The stored answer is kept either way. A thing whose capability changes underneath it — a plug
        pulled out and a real bulb put in — keeps what the owner said as long as the new thing can still
        serve it, and the record survives a spell where it cannot rather than being quietly thrown away.
        Measured against the house's guess where it made one: "plug" is an answer on a switch the house
        took for an appliance, and nothing at all on one it did not."""
        k = self.kinds.get(eid)
        return k if k and k != (guess or capability) and k in kinds_for(capability) else None

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
