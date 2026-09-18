# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Sharing the house outward: what a Matter bridge may publish, and what it is told about each thing.

`docs/matter.md`. The rules live here and not in the bridge, because the bridge publishes the list it
is handed -- so the two decisions of 17 September 2026 are rules with tests rather than a screen's
manners. An alarm is never shared. A lock is shared only where the household has said so, once, with
the sentence beside it.

The other half of this module is identity. A commissioner remembers a bridged thing by its endpoint
number, and matter.js remembers an endpoint number against the id we give it: shift those and Apple
Home shows ghosts. So the id is made here, from the device id, and never from anything that moves.
"""
import hashlib, os, secrets, time
from .model import kind_of

# Never, whatever a household switches. docs/matter.md, *The two that are decided*: a siren reaches
# Matter as an On/Off endpoint, which is one word away from sounding, from any room, from any guest
# and from a television that said the wrong thing -- and there is no way to ask for the second tap
# that docs/kinds.md gave it. Silencing is the half worth having and it cannot be had without the other.
REFUSED = ("alarm",)

# Not a decision: an absence. Matter has no speaker or media player device type at all, and no
# controller usefully takes a BRIDGED camera today (they arrived in Matter 1.5 for real devices).
# These are listed so that the reason is written down and nobody adds them by finding a spare cluster.
UNCARRIED = ("media", "camera")

# Only where somebody has said so. Matter's Door Lock is one device with a lock AND an unlock on it,
# so unlike docs/voice.md -- which could give the closing half away free -- there is no half to publish.
# That is exactly why this is a switch somebody throws and not a default.
BY_HAND = ("lock",)

# ...and the covers that are a way INTO the house, which is not all of them. `model.GATED` gates the
# whole kind against a RE-TYPING, which is right there: nobody should be able to call a garage door a
# plug. On the way out of the house the question is different and the screen already says so -- it
# reads *Locks and garage doors*, not *locks and blinds* -- and holding a bedroom blind behind the
# same switch as the front door would be the label lying. A cover whose class we cannot read is
# treated as a way in, because the one we would be guessing about is the garage.
WAYS_IN = ("garage", "door", "gate")

# What the bridge can build today, by the kind the house SHOWS a thing as -- kind_of, so a lamp on a
# plug that the owner re-typed arrives in Apple Home as a light, which is the whole argument of
# docs/kinds.md. Everything absent is simply not carried yet; piece 2 fills it in.
# Everything absent is not carried, and each absence has a reason written beside it in docs/matter.md:
# `media` and `camera` have nowhere in Matter to go, `alarm` is refused, and illuminance and vacuums
# are left for later because no controller does anything useful with a bridged one today.
TYPE = {
    "light": "light", "switch": "plug", "appliance": "plug", "fan": "fan",
    "cover": "cover", "climate": "thermostat", "lock": "lock",
    "motion": "occupancy", "contact": "contact",
    "sensor.temperature": "temperature", "sensor.humidity": "humidity",
}

# What a house shares when it first says yes. The lights and the plugs, and nothing that is gated.
DEFAULT_KINDS = ("light", "switch", "appliance")

# How long the brain believes the bridge is there after it last said so. The bridge reconciles and
# reports every sixty seconds, so this is two and a half beats: one missed report is a slow moment,
# three is a container that has stopped. Without it a bridge that died an hour ago would still be
# reported as running, and the panel would offer to open a door that nothing is behind.
BRIDGE_STALE = 150

# How long the door stands open for a new app, in seconds. The same shape as a radio's pairing window
# and for the same reason: a Matter node with an open window and a printed code will join whoever has
# the code, so it is opened deliberately, from the panel, and it shuts itself. docs/matter.md.
WINDOW = 300

# Who is holding the bridge, in the words a person would use. A fabric carries the vendor id of the
# app that commissioned it, and these are read from the Connectivity Standards Alliance's own ledger
# rather than guessed -- a wrong name here would tell somebody the wrong app is in their house.
#
# Amazon has several and which one an Echo roots a fabric with is NOT established, so all three of its
# ids are here and anything unknown falls back to the label the app set for itself. Never invent a name.
HOLDERS = {
    4937: "Apple Home", 4996: "Apple Home",
    24582: "Google Home",
    4631: "Alexa", 4986: "Alexa", 5495: "Alexa",
    4362: "SmartThings", 4321: "SmartThings", 3: "SmartThings",
    4939: "Home Assistant",
}


def holder(fabric: dict) -> str:
    """What to call whoever holds this fabric: the ledger's name for the app that commissioned it,
    the label it set for itself where we do not know the vendor, and a plain noun where it set none."""
    name = HOLDERS.get(fabric.get("vendor"))
    return name or (fabric.get("label") or "").strip() or "An app"


def endpoint_id(device_id: str) -> str:
    """The bridge's own name for a device, stable for the life of the house.

    A hash of the device id rather than the id itself, for two reasons and neither is tidiness.
    An entity id carries dots and colons that end up in matter.js's storage keys, and sanitising
    them can collide -- `light.a-b` and `light.a.b` would become one endpoint, which is a light
    that answers for another light. The hash cannot collide in any house that will ever exist, and
    it never changes, which is the property Apple Home is actually relying on.
    """
    return "d" + hashlib.sha1(device_id.encode()).hexdigest()[:12]


def left_out(device_id: str, share: dict) -> bool:
    """Has the owner said this particular thing stays home.

    A kind is the coarse decision -- lights, yes -- and this is the exception to it, kept the way
    docs/kinds.md keeps a re-typed device: one id, remembered, and read everywhere the kind is read.
    It is an opt-OUT on purpose. Opt-in would make the kind switches mean nothing and would put a
    shopping trip through thirty-two lamps between a household and anything working at all.
    """
    return device_id in (share.get("left_out") or ())


def by_hand(kind: str, dev=None) -> bool:
    """Does this one need the household to have thrown the switch of its own.

    Every lock, and the covers that are a way into the house. Asked of a DEVICE where there is one,
    because `cover` is the only kind whose answer differs from thing to thing."""
    if kind in BY_HAND: return True
    if kind != "cover": return False
    cls = (getattr(dev, "attrs", None) or {}).get("device_class") if dev is not None else None
    return cls is None or cls in WAYS_IN


def allowed(kind: str, share: dict, dev=None) -> bool:
    """May this leave the house at all -- asked before anything about what a bridge can carry.

    Without a device this is the question about the KIND, and it answers conservatively: a cover with
    nothing known about it is a garage door as far as this is concerned."""
    if kind in REFUSED: return False
    if by_hand(kind, dev): return bool(share.get("locks"))
    return kind in (share.get("kinds") or DEFAULT_KINDS)


def carried(kind: str) -> bool:
    """Can the bridge build an endpoint for this kind yet."""
    return kind in TYPE


def _num(v):
    """A reading as a number, or None. HA hands sensor values over as strings, and a thermostat that
    has never been asked for a setpoint reports None rather than a temperature."""
    try: return float(v)
    except (TypeError, ValueError): return None


def _state_for(kind: str, dev, a: dict) -> dict:
    """What the bridge is told this thing is doing, in the house's OWN units and conventions.

    Nothing here is in Matter's units and that is deliberate. Matter wants centi-Celsius, a lift
    percentage counted from the other end, and a contact sensor whose true means shut -- every one of
    which is a way to ship an inverted blind. Those conversions live in the bridge, next to the
    cluster they belong to, and this side stays the house's own vocabulary throughout.
    """
    if kind in ("light", "switch", "appliance"):
        return {"on": dev.state == "on", "brightness": a.get("brightness")}
    if kind == "fan":
        return {"on": dev.state == "on", "percent": _num(a.get("percentage"))}
    if kind == "cover":
        # HA counts from open: 100 is fully open. A cover with no position at all (a garage door) is
        # all the way one way or the other, and saying so beats reporting a position we do not have.
        pos = _num(a.get("current_position"))
        if pos is None: pos = 0.0 if dev.state == "closed" else 100.0
        return {"position": pos}
    if kind == "lock":
        return {"locked": dev.state == "locked", "known": dev.state in ("locked", "unlocked")}
    if kind == "motion":
        return {"detected": dev.state == "on"}
    if kind == "contact":
        return {"open": dev.state == "on"}           # a binary sensor is ON when the door is OPEN
    if kind.startswith("sensor."):
        return {"value": _num(dev.state)}
    if kind == "climate":
        return {
            "mode": dev.state,                        # off / heat / cool / heat_cool / auto, HA's own words
            "target": _num(a.get("temperature")),
            "target_low": _num(a.get("target_temp_low")),
            "target_high": _num(a.get("target_temp_high")),
            "current": _num(a.get("current_temperature")),
            "min": _num(a.get("min_temp")),
            "max": _num(a.get("max_temp")),
            "modes": list(a.get("hvac_modes") or []),
        }
    return {}


def _dimmable(dev) -> bool:
    """A light the bridge should give a level to. The same test LightPane.vue makes, for the same
    reason: a brightness sent to something that has none is refused by the driver."""
    a = dev.attrs or {}
    return "brightness" in a or any(m != "onoff" for m in (a.get("supported_color_modes") or []))


def endpoint_for(dev, room_name: str, kind: str, unit: str = "°C") -> dict:
    """One thing, as the bridge needs it: who it is, what to build, and where it stands now.

    `unit` is the house's temperature unit and it travels with every endpoint that carries one, in
    both directions: the bridge converts to Matter's centi-Celsius on the way out and back to the
    house's own scale on the way in, because `climate.set_temperature` expects what the house speaks.
    """
    a = dev.attrs or {}
    return {
        "id": dev.id,                       # what the bridge posts back to; the brain still owns the service call
        "eid": endpoint_id(dev.id),         # what the endpoint number is remembered against
        "type": TYPE[kind],
        "kind": kind,
        "dim": kind == "light" and _dimmable(dev),
        "unit": unit,
        "name": dev.name,
        "room": room_name,
        "maker": dev.maker or "",
        # A thing the driver has lost is reachable: false rather than off. Apple Home then says No
        # Response, which is true, instead of showing a lamp as off while nobody knows what it is.
        "reachable": dev.state != "unavailable",
        "state": _state_for(kind, dev, a),
    }


class Share:
    """What this house has agreed to share, and the door the bridge comes in by."""

    def __init__(self, hub):
        self.hub = hub

    # ---- what the household said ----
    @property
    def settings(self) -> dict:
        return self.hub.settings.get("share") or {}

    def set(self, on=None, kinds=None, locks=None) -> dict:
        s = dict(self.settings)
        if on is not None: s["on"] = bool(on)
        if kinds is not None:
            # Only kinds the bridge can carry and the house is allowed to send. A panel that knows a
            # kind this hub does not is not an error; its extra word is simply dropped, the way LOOK
            # drops a setting an older hub never understood.
            s["kinds"] = [k for k in kinds if k in TYPE and k not in REFUSED and k not in BY_HAND]
        if locks is not None: s["locks"] = bool(locks)
        if "kinds" not in s: s["kinds"] = list(DEFAULT_KINDS)
        self.hub.settings.set(share=s)
        self.hub.log.add("share", "settings", None, "on" if s.get("on") else "off", source="user",
                         detail={"kinds": s.get("kinds"), "locks": bool(s.get("locks"))})
        # The bridge watches the same stream the panels do, so switching a kind off reaches it now
        # rather than whenever it next asks. A lock switched off while Apple Home still holds the
        # endpoint is the case this is for.
        self.hub._broadcast(__import__("json").dumps({"type": "share", "share": self.state()}))
        return self.state()

    # ---- the door ----
    def token(self) -> str:
        """The bridge's way past the phone gate. It is a container on this host, not a phone, and
        widening `open_to_strangers` for it would widen the front door for everything else.

        install.sh writes it into driver-layer/.env and gives it to both containers, the way
        ZWAVE_SESSION_SECRET is already done. A hub whose .env predates sharing has none, and then
        nothing can be shared and *This hub* says why -- rather than the brain minting one that the
        bridge, in another container, could never learn.
        """
        return os.environ.get("HUB_SHARE_TOKEN") or ""

    def is_bridge(self, presented: str | None) -> bool:
        tok = self.token()
        return bool(tok) and bool(presented) and secrets.compare_digest(presented, tok)

    def ready(self) -> bool:
        return bool(self.token())

    # ---- what the bridge publishes ----
    def devices(self) -> list[dict]:
        """Exactly the endpoints to publish, in room order, or nothing at all where the house has
        not said yes. The bridge does no filtering of its own; this list IS the decision."""
        if not self.settings.get("on"): return []
        return self._matching()

    def candidates(self) -> list[dict]:
        """The same list as if it were already on: what a house would be sharing if it said yes.

        The screen needs this to say something true and concrete while sharing is off -- *14 lights and
        plugs are ready* rather than an abstraction about ecosystems -- and a household deciding whether
        to turn this on is exactly the person who should be told what would go out."""
        return self._matching()

    def _matching(self, exceptions=True) -> list[dict]:
        """Everything a shared kind covers. With `exceptions` off, the ones the owner has left out
        are included -- which is how the page counts them without enumerating them."""
        s = self.settings
        out = []
        for room in self.hub.home.rooms.values():
            for dev in room.devices:
                k = kind_of(dev)
                if not carried(k) or not allowed(k, s, dev): continue
                if exceptions and left_out(dev.id, s): continue
                out.append(endpoint_for(dev, room.name, k, self.hub.temp_unit))
        return out

    def shareable(self, dev) -> bool:
        """Could this thing go out at all, if the owner had not said otherwise: is its kind carried,
        and is its kind one this house shares. The panel asks before drawing a switch for it."""
        k = kind_of(dev)
        return bool(self.settings.get("on")) and carried(k) and allowed(k, self.settings, dev)

    def may_act(self, dev) -> bool:
        """Is this thing one the house is sharing RIGHT NOW -- kind, exception and all.

        The one predicate the acting route asks, so that every way a thing can be kept home is a way
        a command for it is refused. The list is the decision, but a controller keeps an endpoint it
        was given, and a household that leaves a lamp out must not be obeyed on the strength of a
        list Apple Home fetched an hour ago."""
        return self.shareable(dev) and not left_out(dev.id, self.settings)

    def set_device(self, dev, shared: bool) -> dict:
        """One thing in or out by hand. Stored as the exception rather than as the rule, so a house
        that turns a kind off and on again does not lose the one lamp it meant to keep home."""
        s = dict(self.settings)
        out = [i for i in (s.get("left_out") or []) if i != dev.id]
        if not shared: out.append(dev.id)
        s["left_out"] = out
        self.hub.settings.set(share=s)
        self.hub.log.add("share", "device", dev.id, "shared" if shared else "left out", source="user")
        self.hub._broadcast(__import__("json").dumps({"type": "share", "share": self.state()}))
        return self.state()

    # ---- letting another app in ----
    def running(self) -> bool:
        """Is there actually a bridge behind this page right now."""
        return bool(self.bridge().get("running"))

    def ask_window(self) -> dict:
        """Open the door for one more app, for WINDOW seconds. Recorded rather than sent: the bridge
        asks for its list on every nudge anyway, so this rides along on the one direction that already
        exists and there is no second socket listening on the hub for somebody to find."""
        s = dict(self.settings)
        s["window_asked"] = time.time()
        self.hub.settings.set(share=s)
        self.hub.log.add("share", "window", None, "opened", source="user")
        self.hub._broadcast(__import__("json").dumps({"type": "share", "share": self.state()}))
        return self.state()

    def window(self) -> dict:
        """What the bridge needs to know about the door: when it was asked for, and for how long.

        A request that has already run out is not reported at all, and that is the point rather than
        tidiness. The bridge compares the ask against the last one it served, and a bridge that has
        just started has served none -- so an `asked` from three hours ago read as a fresh request and
        the door swung open again on every restart, for ever. The one place that knows how long a
        window lasts is the one place that should decide when it is over."""
        asked = self.settings.get("window_asked")
        live = bool(asked) and time.time() - asked < WINDOW
        return {"asked": asked if live else None, "seconds": WINDOW}

    def bridge(self) -> dict:
        """What the bridge last said about itself, or nothing where it has stopped saying anything.

        Every reader goes through here rather than at `share_status` directly, so there is one place
        that knows the difference between *is running* and *said it was running, once, on Tuesday*."""
        st = self.hub.share_status or {}
        if not st.get("running"): return dict(st)
        if time.time() - (st.get("at") or 0) > BRIDGE_STALE:
            return {**st, "running": False, "stale": True}
        return dict(st)

    # ---- what the panel shows ----
    def holders(self) -> list[dict]:
        """The apps holding this house, named. Empty until somebody has scanned the code.

        Read from the last report even when it is stale: a bridge that has stopped does not mean
        Apple Home has forgotten this house, and saying nobody holds it would be the wrong lie."""
        return [{"index": f.get("index"), "name": holder(f)} for f in ((self.hub.share_status or {}).get("fabrics") or [])]

    def state(self) -> dict:
        s = self.settings
        bridge = self.bridge()
        cands = self.candidates()
        asked = s.get("window_asked") or 0
        # The door is open while the bridge says it is uncommissioned (nobody holds it yet, so it is
        # waiting to be scanned) or while a window somebody asked for has not run out.
        left = max(0, int(asked + WINDOW - time.time())) if asked else 0
        return {
            "ready": self.ready(),
            "on": bool(s.get("on")),
            "kinds": list(s.get("kinds") or DEFAULT_KINDS),
            "locks": bool(s.get("locks")),
            "offer": [k for k in TYPE if k not in REFUSED and k not in BY_HAND],
            "shared": len(self.devices()),
            "candidates": len(cands),   # what would go out, so the off state can be concrete
            # The exceptions, as ids for the panel to test one device against, and a count of the ones
            # that are actually holding something back right now. A lamp left out of a kind nobody
            # shares is not "left out" in any sense a person would recognise, so it is not counted.
            "left_out": list(s.get("left_out") or []),
            "left_out_now": max(0, len(self._matching(exceptions=False)) - len(cands)),
            # A few of them by name. The panel draws what becomes a Matter device on the way out, and a
            # drawing of THIS house's kettle argues the feature in a way "your devices" never will.
            "preview": [{"name": d["name"], "kind": d["kind"]} for d in cands[:3]],
            "holders": self.holders(),
            "open": bool(bridge.get("running")) and (not bridge.get("commissioned") or left > 0),
            "seconds_left": left if bridge.get("commissioned") else None,
            "code": bridge.get("manual"),
            "bridge": bridge,
        }
