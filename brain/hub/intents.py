"""Room intents: the product's unit of control. Deterministic; the assistant may author these, never run them."""
from enum import Enum


class RoomState(str, Enum):
    occupied = "occupied"
    empty = "empty"
    asleep = "asleep"
    away = "away"
    movie = "movie"
    guests = "guests"


# intent -> list of (capability, action, data). First cut; rules will become data, not code.
INTENT_ACTIONS = {
    RoomState.occupied: [],
    RoomState.empty:   [("light", "off", {}), ("media", "pause", {})],
    RoomState.asleep:  [("light", "off", {}), ("media", "off", {}), ("lock", "lock", {})],
    RoomState.away:    [("light", "off", {}), ("media", "off", {}), ("lock", "lock", {}), ("switch", "off", {})],
    RoomState.movie:   [("light", "on", {"brightness_pct": 15}), ("media", "on", {})],
    RoomState.guests:  [("light", "on", {"brightness_pct": 80})],
}

# capability action -> HA (domain, service). The only HA-shaped table outside the adapter.
SERVICE = {
    ("light", "on"): ("light", "turn_on"), ("light", "off"): ("light", "turn_off"),
    ("switch", "on"): ("switch", "turn_on"), ("switch", "off"): ("switch", "turn_off"),
    ("media", "on"): ("media_player", "turn_on"), ("media", "off"): ("media_player", "turn_off"),
    ("media", "pause"): ("media_player", "media_pause"), ("media", "play"): ("media_player", "media_play"),
    ("fan", "on"): ("fan", "turn_on"), ("fan", "off"): ("fan", "turn_off"),
    ("cover", "open"): ("cover", "open_cover"), ("cover", "close"): ("cover", "close_cover"),
    ("lock", "lock"): ("lock", "lock"), ("lock", "unlock"): ("lock", "unlock"),
}


def plan(room, state: RoomState):
    """Return the concrete calls needed to move a room into `state`."""
    calls = []
    for cap, action, data in INTENT_ACTIONS[state]:
        for d in room.devices:
            if d.capability == cap and (cap, action) in SERVICE:
                domain, service = SERVICE[(cap, action)]
                calls.append((domain, service, d.id, data))
    return calls
