"""Names and rooms for the things that have not been placed yet.

New devices arrive called whatever their maker called them: "TP-LINK Kasa KL125 Bulb", "lumi.sensor_motion.aq2",
"Zooz ZEN32 Scene Controller". The New devices screen should be mostly confirming, so this proposes a plain name
and a room for each one. First the house's own reasoning: a room's name (or one of its usual other names) inside
the device's name or its hardware's name places it; maker and model words come out of the name and a kind word
goes in when nothing else says what it is. Then, when the assistant is connected, one call asks the model about
whatever is still unplaced, with the rooms, the device's neighbours on the same hardware and its kind. The model
only ever proposes; a person taps Use, and the move and rename go through the same guarded routes as by hand.
"""
import json, logging, re
from .commands import find_room, norm

log = logging.getLogger("hub.suggest")

NOISE = {"philips", "hue", "signify", "tp-link", "tplink", "tp link", "kasa", "tapo", "sonoff", "itead", "aqara", "lumi", "xiaomi", "mi", "zooz", "ge", "jasco",
         "enbrighten", "ring", "nest", "google", "wyze", "shelly", "tuya", "smart", "wifi", "wi-fi", "zigbee", "z-wave", "zwave", "matter", "thread", "lsc",
         "ikea", "tradfri", "sengled", "innr", "lifx", "wemo", "belkin", "meross", "eve", "ecobee", "honeywell", "levoit", "roborock", "ecovacs", "irobot",
         "device", "entity", "module", "controller", "hub", "bridge", "gen", "generation", "series", "pro", "plus", "mini", "v2", "v3", "2nd", "3rd", "the",
         "scene", "dimmer", "relay", "bulb", "a19", "e26", "e27", "br30", "gu10", "rgbw", "rgb", "cct", "led", "color", "colour", "white", "ambiance", "ambience"}
KIND_NOUN = {"light": "light", "switch": "plug", "media": "speaker", "cover": "blind", "lock": "lock", "fan": "fan", "climate": "thermostat", "camera": "camera",
             "motion": "motion", "contact": "door sensor", "vacuum": "vacuum", "sensor.temperature": "temperature", "sensor.humidity": "humidity", "sensor.illuminance": "light level"}
KIND_HINT = {"light": r"\b(light|lights|lamp|lamps|bulb|strip|sconce|chandelier|pendant)\b", "switch": r"\b(plug|outlet|switch|socket)\b", "media": r"\b(tv|speaker|display|player|roku|cast|receiver|soundbar)\b",
             "cover": r"\b(blind|blinds|shade|shades|curtain|garage|door|shutter)\b", "lock": r"\b(lock|door|deadbolt)\b", "fan": r"\b(fan)\b", "climate": r"\b(thermostat)\b",
             "camera": r"\b(cam|camera|doorbell)\b", "motion": r"\b(motion|occupancy|presence|sensor)\b", "contact": r"\b(door|window|contact|sensor)\b", "vacuum": r"\b(vacuum|robot|roomba)\b"}
MODEL_CODE = re.compile(r"^(?=.*\d)[a-z0-9][a-z0-9.\-_/]*$")   # letters with digits in them: KL125, zen32, aq2

SYSTEM = """You help a family name the new devices in their house and say which room each is in. You get the rooms
(id: name), and each unplaced device: its id, the name its maker gave it, what kind of thing it is, and the names of
the other parts on the same piece of hardware. Answer for every device. A name is two or three plain words a
person would say, without the maker, model or protocol ("Ceiling light", "Front door", "Kitchen speaker", "Hallway
motion"); keep a name that is already plain. A room is one of the given ids, or "" when nothing in the words says
where it is; never guess a room from the kind alone. Say why in a few words. Answer as JSON."""
SCHEMA = {"type": "object", "properties": {"items": {"type": "array", "items": {"type": "object", "properties": {
          "id": {"type": "string"}, "name": {"type": "string"}, "room": {"type": "string"}, "why": {"type": "string"}},
          "required": ["id", "name", "room", "why"], "additionalProperties": False}}}, "required": ["items"], "additionalProperties": False}


def clean_name(name: str, capability: str, room_name: str | None = None) -> str:
    """The maker's name as a person would say it: maker and model words out, a kind word in when it is needed."""
    kind = capability if capability in KIND_NOUN else capability.split(".")[0]
    words = [w for w in norm(name).replace("_", " ").replace(".", " ").split() if w]
    kept, seen = [], set()
    for w in words:
        if w in NOISE or MODEL_CODE.match(w) or w in seen: continue
        seen.add(w); kept.append(w)
    hint = KIND_HINT.get(kind)
    text = " ".join(kept)
    if not kept or (hint and not re.search(hint, text)):
        noun = KIND_NOUN.get(kind, "")
        if noun and noun not in text: kept.append(noun)
    out = " ".join(kept).strip()
    if room_name and norm(room_name) == out: out = f"{out} {KIND_NOUN.get(kind, '')}".strip()
    out = out.replace(" tv", " TV") if out.endswith(" tv") else out
    if out == "tv": out = "TV"
    return out[:1].upper() + out[1:] if out else name


class Suggestions:
    def __init__(self, hub):
        self.hub = hub

    def waiting(self) -> list:
        return [d for d in self.hub.home.devices.values() if d.room_id == "unassigned"]

    def by_house(self) -> list:
        """What the house can work out on its own: a room named in the words, and a tidier name."""
        out = []
        for d in self.waiting():
            hw = self.hub.home.hardware.get(d.hw or "", {})
            siblings = [x for x in self.hub.home.devices.values() if d.hw and x.hw == d.hw and x.id != d.id]
            words = " ".join([d.name, hw.get("name") or "", d.id.split(".", 1)[-1].replace("_", " "), *(x.name for x in siblings)])
            room, _ = find_room(norm(words), self.hub.home.rooms)
            placed = next((self.hub.home.rooms.get(x.room_id) for x in siblings if x.room_id != "unassigned"), None)
            if room is None and placed is not None: room = placed
            name = clean_name(d.name, d.capability, room.name if room else None)
            why = (f"\"{room.name}\" is in its name" if room and _has_word(room.name, words) else f"the same unit as {placed.devices[0].name}" if room and placed else
                   ("a plainer name" if name != d.name else ""))
            out.append({"id": d.id, "name": name, "room": room.id if room else "", "why": why, "source": "house",
                        "was": d.name, "kind": d.capability, "hardware": hw.get("name") or "", "siblings": [x.name for x in siblings]})
        return out

    async def all(self) -> dict:
        """The house's pass, then the assistant's for whatever is still unplaced. Never moves anything."""
        items = self.by_house()
        used = False
        pending = [i for i in items if not i["room"]]
        if pending and self.hub.assistant.status()["configured"]:
            try:
                answers = await self._ask(pending)
                used = True
            except Exception as e:
                log.info("suggestions from the assistant failed: %s", e); answers = {}
            for i in items:
                a = answers.get(i["id"])
                if not a: continue
                room = a.get("room") or ""
                if not i["room"] and room in self.hub.home.rooms and room != "unassigned": i["room"], i["source"] = room, "assistant"
                name = " ".join(str(a.get("name") or "").split()).strip(" .")
                if name and 1 <= len(name) <= 40: i["name"], i["source"] = name[:1].upper() + name[1:], "assistant"
                if a.get("why"): i["why"] = str(a["why"])[:120]
        for i in items:
            for k in ("was", "kind", "hardware", "siblings"): i.pop(k, None)
        return {"items": [i for i in items if i["room"] or i["name"] != self.hub.home.devices[i["id"]].name], "assistant": used}

    async def _ask(self, pending) -> dict:
        rooms = [f"  {r.id}: {r.name}" for r in self.hub.home.rooms.values() if r.id != "unassigned"]
        lines = []
        for i in pending:
            lines.append(f"  {i['id']} | maker's name: {i['was']} | kind: {KIND_NOUN.get(i['kind'], i['kind'])} | hardware: {i['hardware'] or '?'} | other parts: {', '.join(i['siblings']) or 'none'}")
        user = "\n".join(["Rooms (id: name):", *rooms, "", "Unplaced devices:", *lines])
        raw = await self.hub.assistant._ask(SYSTEM, user, SCHEMA, max_tokens=1500, effort="low")
        out = {}
        for a in (json.loads(raw).get("items") or []):
            if isinstance(a, dict) and a.get("id") in {i["id"] for i in pending}: out[a["id"]] = a
        return out


def _has_word(name: str, text: str) -> bool:
    n = norm(name)
    return n in norm(text) or n.replace("'s", "s").replace("'", "") in norm(text)
