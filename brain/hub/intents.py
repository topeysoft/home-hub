"""Room intents: the product's unit of control. Deterministic; the assistant may author these, never run them."""
import json, logging, shutil
from enum import Enum
from pathlib import Path
from .settings import DATA

log = logging.getLogger("hub.scenes")


class RoomState(str, Enum):
    occupied = "occupied"
    empty = "empty"
    asleep = "asleep"
    away = "away"
    movie = "movie"
    guests = "guests"


# intent -> list of (capability, action, data). Lives in ../scenes.json so it can be edited, and later authored
# by the assistant, without touching code. These defaults only apply if that file is missing or broken.
DEFAULT_ACTIONS = {
    RoomState.occupied: [],
    RoomState.empty:   [("light", "off", {}), ("media", "pause", {})],
    RoomState.asleep:  [("light", "off", {}), ("media", "off", {}), ("lock", "lock", {})],
    RoomState.away:    [("light", "off", {}), ("media", "off", {}), ("lock", "lock", {}), ("switch", "off", {})],
    RoomState.movie:   [("light", "on", {"brightness_pct": 15}), ("media", "on", {})],
    RoomState.guests:  [("light", "on", {"brightness_pct": 80})],
}
# How long a room stays as a person set it before rules may move it again, in seconds. asleep and away
# carry no hold: they are meant to be released by a rule (morning, someone came home). `_hold` in scenes.json.
DEFAULT_HOLD = {"occupied": 7200, "movie": 14400, "guests": 43200, "asleep": 0, "away": 0, "empty": 900}
SEED = Path(__file__).resolve().parent.parent / "scenes.json"   # the repo's copy seeds a new hub's data directory
RULES_PATH = DATA / "scenes.json"
_rules = {"mtime": None, "actions": DEFAULT_ACTIONS, "hold": DEFAULT_HOLD}


def rules() -> dict:
    """The current scene table, re-read whenever scenes.json changes."""
    try:
        if not RULES_PATH.exists() and SEED.exists() and SEED.resolve() != RULES_PATH.resolve():
            RULES_PATH.parent.mkdir(parents=True, exist_ok=True); shutil.copy(SEED, RULES_PATH)
        mtime = RULES_PATH.stat().st_mtime
        if mtime != _rules["mtime"]:
            raw = json.loads(RULES_PATH.read_text())
            actions = {RoomState(k): [(c, a, d or {}) for c, a, d in v] for k, v in raw.items() if not k.startswith("_")}
            for st in RoomState: actions.setdefault(st, [])
            hold = {**DEFAULT_HOLD, **{k: float(v) for k, v in (raw.get("_hold") or {}).items() if k in RoomState.__members__}}
            _rules.update(mtime=mtime, actions=actions, hold=hold)
            log.info("scenes loaded from %s", RULES_PATH.name)
    except FileNotFoundError:
        _rules.update(mtime=None, actions=DEFAULT_ACTIONS, hold=DEFAULT_HOLD)
    except Exception as e:
        log.warning("scenes.json is not usable (%s); keeping the previous rules", e)
    return _rules["actions"]


def holds() -> dict:
    """Seconds a hand-set state holds rules off the room, per state."""
    rules(); return _rules["hold"]


def rules_as_data() -> dict:
    return {st.value: [[c, a, d] for c, a, d in acts] for st, acts in rules().items()}


# capability action -> HA (domain, service). The only HA-shaped table outside the adapter.
SERVICE = {
    ("light", "on"): ("light", "turn_on"), ("light", "off"): ("light", "turn_off"),
    ("switch", "on"): ("switch", "turn_on"), ("switch", "off"): ("switch", "turn_off"),
    ("media", "on"): ("media_player", "turn_on"), ("media", "off"): ("media_player", "turn_off"),
    ("media", "pause"): ("media_player", "media_pause"), ("media", "play"): ("media_player", "media_play"),
    ("media", "next"): ("media_player", "media_next_track"), ("media", "previous"): ("media_player", "media_previous_track"),
    ("media", "volume"): ("media_player", "volume_set"),
    ("fan", "on"): ("fan", "turn_on"), ("fan", "off"): ("fan", "turn_off"),
    ("cover", "open"): ("cover", "open_cover"), ("cover", "close"): ("cover", "close_cover"),
    ("lock", "lock"): ("lock", "lock"), ("lock", "unlock"): ("lock", "unlock"),
    ("climate", "set"): ("climate", "set_temperature"), ("climate", "mode"): ("climate", "set_hvac_mode"),
    ("climate", "preset"): ("climate", "set_preset_mode"), ("climate", "fan"): ("climate", "set_fan_mode"),
    ("climate", "on"): ("climate", "turn_on"), ("climate", "off"): ("climate", "turn_off"),
}


def plan(room, state: RoomState):
    """Return the concrete calls needed to move a room into `state`."""
    calls = []
    for cap, action, data in rules()[state]:
        for d in room.devices:
            if d.capability == cap and (cap, action) in SERVICE:
                domain, service = SERVICE[(cap, action)]
                calls.append((domain, service, d.id, data))
    return calls
