# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Room intents: the product's unit of control. Deterministic; the assistant may author these, never run them."""
import json, logging, shutil
from enum import Enum
from pathlib import Path
from .model import kind_of
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
#
# No scene names `alarm`, in either direction, and the omission is the decision. A siren shown as a plug
# used to go off with the plugs at Everything off, which looks like a mercy until you notice that a great
# many sirens put their ARMED state on that same switch: a nightly Good night would then disarm the house,
# silently, and a person would find out the hard way. Sounding one from a scene is worse again. So the
# sweep steps over it and silencing stays one tap, on the tile, in On right now, or in a sentence that
# says so. Held down by test_kinds.py.
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
    ("fan", "on"): ("fan", "turn_on"), ("fan", "off"): ("fan", "turn_off"), ("fan", "set"): ("fan", "set_percentage"),
    ("cover", "open"): ("cover", "open_cover"), ("cover", "close"): ("cover", "close_cover"),
    ("cover", "set"): ("cover", "set_cover_position"), ("cover", "stop"): ("cover", "stop_cover"),
    ("lock", "lock"): ("lock", "lock"), ("lock", "unlock"): ("lock", "unlock"),
    ("climate", "set"): ("climate", "set_temperature"), ("climate", "mode"): ("climate", "set_hvac_mode"),
    ("climate", "preset"): ("climate", "set_preset_mode"), ("climate", "fan"): ("climate", "set_fan_mode"),
    ("climate", "on"): ("climate", "turn_on"), ("climate", "off"): ("climate", "turn_off"),
    # A vacuum or a mower has nowhere to go but out and back, which is why it has no on.
    ("vacuum", "start"): ("vacuum", "start"), ("vacuum", "return"): ("vacuum", "return_to_base"),
    ("vacuum", "stop"): ("vacuum", "stop"),
}


def plan(room, state: RoomState):
    """Return the concrete calls needed to move a room into `state`.

    The two lines that used to be one `if`, and the reason they are apart. WHICH devices a scene sweeps
    up is what the owner says they are, so a lamp on a plug shown as a light goes off at bedtime with
    the rest of the lights. WHAT is then called on each one is what the driver says it is: `switch` is
    a switch entity whatever it is shown as, and asking HA for light.turn_off on it is refused. Both
    lines reading the same field is how this fails, and it fails silently — the scene runs, the lamp
    does not move, and nobody is told.

    The data goes with the kind it was written for. A scene that dims the lights to 15% has nothing to
    say to a plug, so a device standing in for another kind gets the bare action: on is all it has."""
    calls = []
    for cap, action, data in rules()[state]:
        for d in room.devices:
            if kind_of(d) != cap: continue
            own = d.capability.split(".")[0]              # the driver's, always: this picks the service
            if (own, action) not in SERVICE: continue
            domain, service = SERVICE[(own, action)]
            calls.append((domain, service, d.id, data if own == cap else {}))
    return calls
