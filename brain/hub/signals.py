# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the lights tell you: a few things worth knowing without looking at a screen.

A SIGNAL IS NOT AN EFFECT, and design/signal/ is the argument. An effect takes the color a household
chose away to show off, and design/occasion/ said no to that. A run of light down a drive toward the
house says something -- somebody is coming in -- and then gives the light back exactly as it was. So a
signal is one of four motions that each MEAN something (px::Signal in strip/firmware/main/pixels.h),
started by something happening, never picked from a menu, and over in seconds.

WHERE THEY COME FROM, direction A with C (picked 24 September):

    the house's own four   someone's arriving, someone's leaving, a door's been left open, something's
                           nearly done. Each is switched on or off on "What the lights tell you", and
                           the house works out when each one is true -- ONCE, here, rather than in a
                           rule per strip that could disagree with the next one.
    a household's own      a routine whose outcome is `{"signal": ...}`, asked for in words and approved
                           in Routines like any other. hub/rules.py runs it; this draws it.

ARRIVING OR LEAVING, which is the hard part of the whole idea and is decided in exactly one place:
somebody's phone coming home is arriving; and in a room the family comes in through (Routines, "where
you come in"), a door or gate that opens with nobody moving by it first is somebody coming IN, while
one that opens after motion by it is somebody going OUT. A room with no motion sensor cannot tell the
two apart, and so decides nothing rather than guessing -- and says so, when somebody tries it.

TRY, on every row, because a signal that never fires is indistinguishable from one that is broken:

    now      plays it once on its lights, even in daylight, and each light says whether it answered --
             the strip on MQTT, with the id of the signal it started (it does not just get asked).
    watch    for WATCH_FOR the house watches for the real thing, with "after dark" set aside, and
             writes down every link of the chain as it happens: the sensor heard, what the house
             decided and why, each light. A chain that breaks says which link, and that link's own
             last word ("last heard 3 days ago"), because "it didn't work" is not a thing anybody can fix.
"""
import asyncio, json, logging, time, uuid
from . import sun

log = logging.getLogger("hub.signals")

KINDS = ("way", "call", "fill", "end")
TOWARD = ("house", "out")

# The four the house has, in the order the page shows them. The words are the panel's: a meaning is
# named for what a person would say, never for the motion that shows it.
MEANINGS = (
    {"id": "arriving", "name": "Someone’s arriving", "kind": "way", "toward": "house", "dark": True},
    {"id": "leaving", "name": "Someone’s leaving", "kind": "way", "toward": "out", "dark": True},
    {"id": "open", "name": "A door’s been left open", "kind": "call", "dark": False},
    {"id": "done", "name": "Something’s nearly done", "kind": "fill", "dark": False},
)
BY_ID = {m["id"]: m for m in MEANINGS}

# EMITTER COLORS, NOT SCREEN COLORS (AGENTS.md section 4). An LED gives the eye no reference, so a
# pastel reads as white: every one of these has its off-channels near zero. They are what the strip is
# sent, and the panel draws its preview in the same four.
EMITTER = {"arriving": (255, 138, 0), "leaving": (30, 107, 255), "open": (255, 42, 74), "done": (0, 208, 106)}
DEFAULT_RGB = (255, 138, 0)

# How each motion is timed. A run is three passes of 2.2 s: one is easy to miss from a car, and more
# than three stops being a signal and starts being a decoration.
TIMING = {"way": (2200, 3), "call": (1600, 3), "fill": (3000, 2), "end": (1000, 6)}

WINDOW = 45          # seconds of motion by a door before it opens that make it somebody going OUT
QUIET_AFTER = 90     # a room that has just said something does not say it again for this long
OPEN_AFTER = 600     # a door open this long has been left open
OPEN_CALL_FOR = 30 * 60   # and the strip breathes until it is shut, or for this long at most
WATCH_FOR = 600      # how long "wait for the real thing" waits
ACK_WAIT = 2.0       # how long a strip has to say it started
STALE = 24 * 3600    # a sensor not heard from in this long is named as the likely reason
ENDS_SHOW = 20_000   # how long one end stays lit while somebody decides which end it is (ms)


def in_or_out(opened_at: float, motion_at: float | None, window: float = WINDOW) -> str:
    """A door in a way-in room has opened. Motion by it just before means somebody walked up to it from
    inside; none means it opened from outside. The one rule, so the tests can hold it."""
    return "leaving" if motion_at is not None and 0 <= opened_at - motion_at <= window else "arriving"


def ago(ts: float | None, now: float | None = None) -> str:
    """"3 days ago", for the one line that names a sensor's last word."""
    if not ts: return "never"
    s = max(0, (now or time.time()) - ts)
    if s < 90: return "just now"
    if s < 90 * 60: return f"{round(s / 60)} min ago"
    if s < 36 * 3600: return f"{round(s / 3600)} hours ago"
    return f"{round(s / 86400)} days ago"


def colorful(d) -> bool:
    modes = set((d.attrs or {}).get("supported_color_modes") or [])
    return bool(modes & {"hs", "rgb", "xy", "rgbw", "rgbww"})


def _ok(steps) -> bool:
    """A try passes when something showed it and nothing that should have, didn't."""
    return any(s["state"] == "ok" for s in steps) and all(s["state"] != "no" for s in steps)


class Signals:
    def __init__(self, hub):
        self.hub = hub
        self.trying: dict | None = None            # the one try running now, or the last one, still on screen
        self.last: dict[str, dict] = {}            # key -> {"line", "ok", "at"}: what the last try of each said
        self._decided_at: dict[str, float] = {}    # room id -> when it last said arriving or leaving
        self._open_done: dict[str, float] = {}     # contact id -> the `since` a left-open door was already called for
        self._calling: dict[str, list] = {}        # contact id -> the strips breathing for it, to stop when it shuts
        self._acks: dict[str, dict] = {}           # strip id -> {signal id: when it said it started}
        self._ack_wake = asyncio.Event()
        self._end_shown: dict[str, str] = {}       # strip id -> the showing of an end still waiting for an answer

    # ---- what the household has said ----
    def _saved(self) -> dict:
        return dict(self.hub.settings.get("signals") or {})

    def is_on(self, mid: str) -> bool:
        return bool((self._saved().get("on") or {}).get(mid, False))

    def set_on(self, mid: str, on: bool) -> dict:
        if mid not in BY_ID: raise ValueError("That is not one of the things the lights can tell you.")
        s = self._saved(); s["on"] = {**(s.get("on") or {}), mid: bool(on)}
        self.hub.settings.set(signals=s)
        self.hub.log.add("signal", mid, None, "on" if on else "off", source="user")
        self._changed()
        return self.as_data()

    def house_end(self, strip_id: str) -> str | None:
        """Which end of a strip is nearer the house: "plug" (the end its wire comes in at) or "far"."""
        return (self._saved().get("ends") or {}).get(strip_id)

    async def set_house_end(self, strip_id: str, end: str) -> dict:
        if end not in ("plug", "far"): raise ValueError("An end is the lit one or the other one.")
        s = self._saved(); s["ends"] = {**(s.get("ends") or {}), strip_id: end}
        self.hub.settings.set(signals=s)
        if self._end_shown.pop(strip_id, None): await self._send(strip_id, {"id": "ends", "kind": "stop"})
        self._changed()
        return self.as_data()

    async def show_end(self, strip_id: str) -> dict:
        """Light the plug end, steady, so somebody standing by the strip can say which end it is."""
        if strip_id not in self.hub.strip.strips: raise ValueError("That light strip is not one this hub knows about.")
        token = self._end_shown[strip_id] = uuid.uuid4().hex[:6]
        await self._send(strip_id, {"id": "ends", "kind": "end", "end": 0, "ms": 0, "times": 1, "rgb": [255, 255, 255]})
        # Steady until it is answered -- and not for ever when it is not: a strip left showing one lit
        # end because somebody walked away is a light stuck in a test.
        async def later():
            await asyncio.sleep(ENDS_SHOW / 1000)
            if self._end_shown.get(strip_id) == token:
                self._end_shown.pop(strip_id, None)
                await self._send(strip_id, {"id": "ends", "kind": "stop"})
        self._later(later())
        return {"ok": True}

    # ---- the lights near a place ----
    async def _strips_by_hw(self) -> dict:
        out = {}
        for sid in list(self.hub.strip.strips):
            hw = await self.hub.strip._device_for(sid)
            if hw: out[hw] = sid
        return out

    async def lights(self, room_ids) -> list[dict]:
        """Every light in these rooms, and what each can do with a signal: a strip draws it, a color bulb
        blinks with it, and a white-only light is left alone because it cannot say anything in color."""
        strips, out, seen = await self._strips_by_hw(), [], set()
        for rid in room_ids:
            room = self.hub.home.rooms.get(rid)
            for d in (room.devices if room else []):
                if d.capability != "light" or d.id in seen: continue
                seen.add(d.id)
                sid = strips.get(d.hw) if d.hw else None
                out.append({"id": d.id, "name": d.name, "room": rid,
                            "as": "strip" if sid else "bulb" if colorful(d) else "plain", "strip": sid})
        return out

    def _way_in(self) -> list:
        return [r for r in (self.hub.entry or []) if r in self.hub.home.rooms]

    def _contacts(self, rooms=None) -> list:
        rs = rooms if rooms is not None else list(self.hub.home.rooms)
        return [d for rid in rs for d in self.hub.home.rooms[rid].devices if d.capability == "contact"]

    # ---- the page ----
    async def page(self) -> dict:
        """Everything "What the lights tell you" draws, worked out now."""
        way_in = self._way_in()
        rows = []
        for m in MEANINGS:
            row = {"id": m["id"], "name": m["name"], "kind": m["kind"], "toward": m.get("toward"),
                   "rgb": list(EMITTER[m["id"]]), "on": self.is_on(m["id"]), "available": True, "lights": []}
            if m["id"] in ("arriving", "leaving"):
                lit = [x for x in await self.lights(way_in) if x["as"] != "plain"]
                row["lights"] = [x["name"] for x in lit]
                where = "the way in" if m["id"] == "arriving" else "the way out"
                if not way_in:
                    row.update(available=False, hint="Choose the rooms you come in through, in Routines, and this can start")
                elif not lit:
                    row.update(available=False, hint="Nothing where you come in can show it yet. A light strip or a color bulb can")
                else:
                    row["hint"] = f"{' and '.join(row['lights'][:2])}{' and more' if len(lit) > 2 else ''} show {where} · after dark"
            elif m["id"] == "open":
                rooms = sorted({d.room_id for d in self._contacts()})
                lit = [x for x in await self.lights(rooms) if x["as"] != "plain"]
                row["lights"] = [x["name"] for x in lit]
                if not self._contacts():
                    row.update(available=False, hint="Nothing in the house says when a door is open")
                elif not lit:
                    row.update(available=False, hint="No room with a door sensor has a light that can show it")
                else:
                    row["hint"] = "Lights in the room it opens off, until it is shut"
            else:
                # Nothing a household owns reports how far along it is in a way the house can trust yet.
                # Drawn, and honest about it, rather than left off: the board has four, and a fifth
                # meaning waits on the same thing this one does.
                row.update(available=False, hint="Nothing in this house says how far along it is yet")
            if m["id"] in self.last: row["tried"] = self.last[m["id"]]
            rows.append(row)
        own = []
        for r in self.hub.engine.rules:
            sig = next((t for t in _outcomes(r) if "signal" in t), None)
            if not sig: continue
            key = f"rule:{r['id']}"
            own.append({"id": r["id"], "key": key, "name": r.get("name") or r["id"], "kind": sig["signal"],
                        "toward": sig.get("toward"), "rgb": list(sig.get("rgb") or DEFAULT_RGB),
                        "on": r.get("enabled", True), **({"tried": self.last[key]} if key in self.last else {})})
        strips = []
        for sid, v in sorted(self.hub.strip.strips.items()):
            strips.append({"id": sid, "online": bool(v.get("online")), "house_end": self.house_end(sid),
                           "device": await self.hub.strip._device_for(sid)})
        return {"meanings": rows, "own": own, "strips": strips, "trying": self.trying}

    def as_data(self) -> dict:
        """The cheap half, for a write's answer. The panel asks for the page itself after a nudge."""
        return {"trying": self.trying, "last": self.last}

    def _changed(self):
        """A nudge to every panel, carrying only whether a try is watching -- because every wall says so
        in its band ("the drive may light up at lunch"), not only the one somebody is trying it from."""
        w = self.trying
        brief = {"of": w["of"], "name": w["name"], "state": w["state"], "ends": w["ends"]} if w else None
        self.hub._broadcast(json.dumps({"type": "signals", "trying": brief}))

    # ---- drawing ----
    def heard(self, strip_id: str, payload: str):
        """A strip said it started one (hub/strip.py forwards `strip/<id>/signal`)."""
        self._acks.setdefault(strip_id, {})[str(payload or "").strip()] = time.time()
        self._ack_wake.set()

    async def _send(self, strip_id: str, body: dict):
        await self.hub.strip._tell(strip_id, "signal/set", json.dumps(body))

    async def _answered(self, strip_id: str, sig_id: str, timeout: float = ACK_WAIT) -> str | None:
        """"ok", "busy", or None if the strip never said."""
        end = time.monotonic() + timeout
        while True:
            got = self._acks.get(strip_id, {})
            if sig_id in got: return "ok"
            if f"busy {sig_id}" in got: return "busy"
            left = end - time.monotonic()
            if left <= 0: return None
            self._ack_wake.clear()
            try: await asyncio.wait_for(self._ack_wake.wait(), timeout=left)
            except TimeoutError: pass

    def _dir(self, target, toward) -> tuple[int, str | None]:
        """Which way a run goes on this strip, in pixel terms (1 away from the plug), and a note when it
        is a guess because nobody has said which end is the house."""
        end = self.house_end(target["strip"])
        into = toward != "out"
        if end is None: return 1, "Nobody has said which end is the house yet, so it ran away from the plug"
        runs_to_plug = (end == "plug") == into
        return (-1 if runs_to_plug else 1), None

    async def show(self, targets, kind: str, *, toward=None, rgb=None, times=None, level=None, end=None,
                   ms=None, label="") -> list[dict]:
        """Draw one signal on these lights, all at once, and say how each one answered."""
        rgb = list(rgb or DEFAULT_RGB)
        base_ms, base_times = TIMING.get(kind, (2000, 3))
        async def one(t):
            step = {"key": f"light:{t['id']}", "text": f"{t['name']} {label}".strip(), "state": "wait"}
            if t["as"] == "plain":
                return {**step, "state": "skip", "sub": "It cannot show a color, so it was left alone"}
            if t["as"] == "bulb":
                try:
                    await self.hub.ha.call("light", "turn_on", t["id"], flash="long")
                    return {**step, "state": "ok", "sub": "Blinked", "at": time.time()}
                except Exception as e:
                    return {**step, "state": "no", "sub": f"It did not blink: {e}"}
            sid = t["strip"]; known = self.hub.strip.strips.get(sid) or {}
            if not known.get("online"):
                d = self.hub.home.devices.get(t["id"])
                return {**step, "state": "no", "sub": f"It is not answering. Last heard from {ago(d.seen if d else None)}"}
            sig_id = uuid.uuid4().hex[:10]
            body = {"id": sig_id, "kind": kind, "rgb": rgb, "ms": ms or base_ms, "times": times or base_times}
            note = None
            if kind == "way": body["dir"], note = self._dir(t, toward)
            if kind == "fill": body["level"] = max(0, min(255, round(255 * float(level if level is not None else 1))))
            if kind == "end":
                e = self.house_end(sid)
                want_house = (end or toward or "house") != "out"
                body["end"] = 0 if (e == "plug") == want_house else 1
            t0 = time.monotonic()
            await self._send(sid, body)
            said = await self._answered(sid, sig_id)
            if said == "ok":
                sub = f"Answered in {max(0.1, round(time.monotonic() - t0, 1))} s" + (f". {note}" if note else "")
                return {**step, "state": "ok", "sub": sub, "at": time.time(), "strip": sid, "sig": sig_id}
            if said == "busy":
                return {**step, "state": "no", "sub": "It is in the middle of being set up, so it showed nothing"}
            return {**step, "state": "no", "sub": "It was asked and did not answer"}
        return list(await asyncio.gather(*(one(t) for t in targets)))

    def _dark(self) -> bool:
        loc = self.hub.location
        if not loc: return True          # a house that has not said where it is cannot be told it is daytime
        from datetime import datetime
        return sun.elevation(datetime.now(self.hub.tz), loc["lat"], loc["lon"]) < 0

    # ---- the house's own four, for real ----
    def on_state(self, dev, old):
        """A device changed. Doors decide arriving, leaving and left-open; any of it may be a try."""
        room = self.hub.home.rooms.get(dev.room_id)
        if not room or old == dev.state: return
        if dev.capability == "contact":
            if dev.state == "on":
                self._later(self._door_opened(dev, room))
            elif dev.state == "off":
                self._later(self._door_shut(dev))
        elif dev.capability == "motion" and dev.state == "on":
            self._note_watch("motion", dev, room)

    def on_people(self, before: dict, after: dict):
        """Somebody's phone came home: arriving, whatever the doors say."""
        came = [p for p, v in after.items() if v.get("home") is True and (before.get(p) or {}).get("home") is not True]
        for p in came:
            self._later(self._arrived_by_phone(after[p].get("name") or "Somebody"))

    def _later(self, coro):
        try: asyncio.get_running_loop().create_task(coro)
        except RuntimeError: coro.close()

    async def _door_opened(self, dev, room):
        now = time.time()
        # Trying "a door's been left open": the ten minutes are the one thing nobody wants to stand
        # through, so the first door that opens is shown at once and the wait is said to be set aside.
        if w := self._watching(("open",)):
            self._step(w, "heard", "ok", f"{dev.name} opened", at=now)
            self._step(w, "decide", "ok", "Treated as left open", "The 10 minutes are set aside while you try.")
            steps = await self.show(await self.lights([room.id]), "call", rgb=EMITTER["open"], times=3)
            self._lights_steps(w, steps)
            self._finish(w, _ok(steps))
            return
        if room.id not in self._way_in(): return
        watch = self._watching(("arriving", "leaving"))
        if watch: self._step(watch, "heard", "ok", f"{dev.name} opened", at=now)
        motions = [d for d in room.devices if d.capability == "motion"]
        if not motions:
            if watch and watch["of"] in ("arriving", "leaving"):
                self._step(watch, "decide", "no", "The house could not tell in from out",
                           f"Nothing in {room.name} sees motion, so a door opening there cannot say which way somebody is going. A phone coming home still can.")
                self._finish(watch, False)
            return
        # Motion stamps land in rules.Engine.on_state; ours runs after it, so room.motion_at is current.
        # A stamp from this very moment is the person who opened it, from the other side of the door
        # sensor's own report -- so only motion from before the door counts.
        before = room.motion_at if room.motion_at and room.motion_at < now - 0.5 else None
        which = in_or_out(now, before)
        why = (f"{dev.name} opened with nobody moving by it first" if which == "arriving"
               else f"there was motion by {dev.name} {round(now - before)} s before it opened")
        await self._meaning(which, [room.id], why, trying=bool(watch))

    async def _arrived_by_phone(self, name):
        watch = self._watching(("arriving",))
        if watch: self._step(watch, "heard", "ok", f"{name}’s phone came home", at=time.time())
        await self._meaning("arriving", self._way_in(), f"{name}’s phone came home", trying=bool(watch))

    async def _meaning(self, mid, rooms, why, trying=False):
        """The house has decided one of its four is true. Show it, unless it should not be shown -- and
        when somebody is trying, what it decided is itself the step being tested."""
        watch = self._watching((mid, "arriving", "leaving") if mid in ("arriving", "leaving") else (mid,))
        now = time.time()
        if watch and trying:
            if watch["of"] != mid:
                wrong = BY_ID[mid]["name"].lower().replace("someone’s ", "")
                self._step(watch, "decide", "no", f"The house decided: {wrong}", f"Because {why}. " + self._why_not(watch["of"], rooms), at=now)
                self._finish(watch, False)
                return
            self._step(watch, "decide", "ok", f"The house decided: {mid}", f"Because {why}.", at=now)
        else:
            m = BY_ID[mid]
            if not self.is_on(mid): return
            if m["dark"] and not self._dark(): return
            if any(now - self._decided_at.get(r, 0) < QUIET_AFTER for r in rooms): return
        for r in rooms: self._decided_at[r] = now
        targets = await self.lights(rooms)
        m = BY_ID[mid]
        steps = await self.show(targets, m["kind"], toward=m.get("toward"), rgb=EMITTER[mid],
                                label="showed the way in" if mid == "arriving" else "showed the way out" if mid == "leaving" else "")
        self.hub.log.add("signal", ",".join(rooms), None, mid, source="house", detail={"why": why, "lights": [s["text"] for s in steps], "trying": trying})
        if watch and trying:
            self._lights_steps(watch, steps)
            self._finish(watch, _ok(steps))

    def _why_not(self, want, rooms) -> str:
        """Why the house heard the opposite of what it was being tested for, in terms of the one sensor
        that decides it: motion by the door."""
        motions = [d for rid in rooms for d in self.hub.home.rooms[rid].devices if d.capability == "motion"]
        if want == "leaving":
            if not motions: return "Going out is motion by the door, then the door, and there is nothing there that sees motion."
            quiet = max(motions, key=lambda d: time.time() - (d.seen or 0))
            if time.time() - (quiet.seen or 0) > STALE:
                return f"Going out is motion by the door, then the door. {quiet.name} was last heard from {ago(quiet.seen)}; its battery is the likely reason."
            return f"Going out is motion by the door, then the door, and {quiet.name} saw nothing in the {WINDOW} s before it."
        return "Coming in is the door opening with nobody moving by it first, and there was motion by it just before."

    async def _door_shut(self, dev):
        for sid in self._calling.pop(dev.id, []):
            await self._send(sid, {"id": f"shut-{dev.id}", "kind": "stop"})

    async def tick(self):
        """Once a second: a door left open, and a watch running out."""
        now = time.time()
        for d in self._contacts():
            if d.state != "on" or now - (d.since or now) < OPEN_AFTER or self._open_done.get(d.id) == d.since: continue
            self._open_done[d.id] = d.since
            if not self.is_on("open"): continue
            targets = await self.lights([d.room_id])
            steps = await self.show(targets, "call", rgb=EMITTER["open"], times=OPEN_CALL_FOR * 1000 // TIMING["call"][0])
            self._calling[d.id] = [s["strip"] for s in steps if s.get("strip")]
            self.hub.log.add("signal", d.room_id, None, "open", source="house", detail={"why": f"{d.name} has been open {round((now - d.since) / 60)} min"})
        w = self.trying
        if w and w["state"] == "watching" and now >= w["ends"]:
            self._timed_out(w)

    async def run(self):
        while True:
            try:
                if self.hub.driver == "ready": await self.tick()
            except Exception:
                log.exception("signals tick")
            await asyncio.sleep(1)

    # ---- a household's own, from a routine ----
    async def outcome(self, rule, then, why, set_aside=False) -> list[dict]:
        """A routine's `{"signal": ...}`, drawn on the lights of the rule's room -- or on one light, where
        it names one. hub/rules.py calls this; a try watching the rule gets the steps."""
        dev = then.get("device")
        rooms = [rule["room"]] if rule.get("room") not in (None, "home") else list(self.hub.home.rooms)
        targets = [x for x in await self.lights(rooms) if not dev or x["id"] == dev]
        steps = await self.show(targets, then["signal"], toward=then.get("toward"), rgb=then.get("rgb"),
                                times=then.get("times"), level=then.get("level"), end=then.get("end"))
        watch = self._watching((f"rule:{rule['id']}",))
        if watch:
            if set_aside: self._step(watch, "decide", "ok", "Its conditions were set aside", "Because you are trying it; it would not have run just now.")
            else: self._step(watch, "decide", "ok", "Its conditions held")
            self._lights_steps(watch, steps)
            self._finish(watch, _ok(steps))
        return steps

    def rule_heard(self, rule, trigger):
        """rules.Engine saw a watched rule's trigger (before its conditions)."""
        w = self._watching((f"rule:{rule['id']}",))
        if not w: return
        dev = self.hub.home.devices.get((trigger or {}).get("device") or "")
        self._step(w, "heard", "ok", f"{dev.name if dev else 'Its trigger'} {'went ' + str(trigger.get('state')) if 'state' in (trigger or {}) else 'was heard'}", at=time.time())

    def watching_rule(self, rule_id) -> bool:
        return bool(self._watching((f"rule:{rule_id}",)))

    # ---- trying ----
    def _watching(self, of) -> dict | None:
        w = self.trying
        return w if w and w["state"] == "watching" and w["of"] in of else None

    async def try_(self, of: str, how: str) -> dict:
        """Start a try of one row. One at a time: a new one ends the last."""
        if how not in ("now", "watch"): raise ValueError("A try is now, or wait for the real thing.")
        name, targets, kind, opts = await self._what(of)
        if self.trying and self.trying["state"] == "watching": self._finish(self.trying, None)
        now = time.time()
        w = {"id": uuid.uuid4().hex[:8], "of": of, "name": name, "how": how, "state": "running", "started": now,
             "ends": now + WATCH_FOR if how == "watch" else now, "steps": []}
        self.trying = w
        if how == "now":
            self._step(w, "decide", "ok", "Shown now, whatever the time",
                       "“After dark” and every other condition set aside while you try.")
            steps = await self.show(targets, kind, **opts)
            self._lights_steps(w, steps)
            self._finish(w, _ok(steps))
            return w
        w["state"] = "watching"
        heard = {"arriving": "A door or gate where you come in opens, or a phone comes home",
                 "leaving": "Somebody moves by a door where you come in, then it opens",
                 "open": "A door opens — the 10 minutes are set aside while you try"}.get(of, "Its trigger happens")
        self._step(w, "heard", "wait", heard)
        self._step(w, "decide", "wait", {"arriving": "The house decides: arriving", "leaving": "The house decides: leaving"}.get(of, "It runs"))
        for t in targets: self._step(w, f"light:{t['id']}", "wait", t["name"])
        self._changed()
        return w

    async def _what(self, of):
        """What trying `of` means: its name, its lights and how to draw it."""
        if of in BY_ID:
            m = BY_ID[of]
            rooms = self._way_in() if of in ("arriving", "leaving") else sorted({d.room_id for d in self._contacts()})
            targets = await self.lights(rooms)
            if not [t for t in targets if t["as"] != "plain"]:
                raise ValueError("There is nothing there that can show it yet.")
            label = "showed the way in" if of == "arriving" else "showed the way out" if of == "leaving" else ""
            return m["name"], targets, m["kind"], {"toward": m.get("toward"), "rgb": EMITTER[of], "label": label}
        if of.startswith("rule:"):
            r = self.hub.engine.get(of[5:])
            then = next((t for t in _outcomes(r) if "signal" in t), None) if r else None
            if not then: raise ValueError("That routine does not show anything on the lights.")
            room = r.get("room")
            rooms = [x for x in (room if isinstance(room, list) else [room]) if x in self.hub.home.rooms] or list(self.hub.home.rooms)
            if room == "entry": rooms = self._way_in()
            targets = [x for x in await self.lights(rooms) if not then.get("device") or x["id"] == then["device"]]
            return r.get("name") or r["id"], targets, then["signal"], {
                "toward": then.get("toward"), "rgb": then.get("rgb"), "times": then.get("times"),
                "level": then.get("level"), "end": then.get("end")}
        raise ValueError("That is not something the lights tell you.")

    def stop(self) -> dict:
        if self.trying and self.trying["state"] == "watching": self._finish(self.trying, None)
        return self.as_data()

    def _step(self, w, key, state, text, sub=None, at=None):
        row = {"key": key, "state": state, "text": text, **({"sub": sub} if sub else {}), **({"at": at} if at else {})}
        for i, s in enumerate(w["steps"]):
            if s["key"] == key: w["steps"][i] = row; break
        else:
            w["steps"].append(row)
        self._changed()

    def _lights_steps(self, w, steps):
        for s in steps:
            self._step(w, s["key"], s["state"], s["text"], s.get("sub"), s.get("at"))

    def _note_watch(self, what, dev, room):
        w = self._watching(("leaving",))
        if w and room.id in self._way_in():
            self._step(w, "moved", "ok", f"{dev.name} saw somebody", at=time.time())

    def _timed_out(self, w):
        """Ten minutes and the real thing never came. Name what was being listened to, and when each of
        them was last heard from, because that is where the fault is."""
        if w["of"] in ("arriving", "leaving", "open"):
            rooms = self._way_in() if w["of"] != "open" else sorted({d.room_id for d in self._contacts()})
            ears = [d for rid in rooms for d in self.hub.home.rooms[rid].devices if d.capability in ("contact", "motion")]
            if not ears:
                self._step(w, "heard", "no", "Nothing was listening", "There is no door or motion sensor where you come in.")
            else:
                said = ", ".join(f"{d.name} (last heard {ago(d.seen)})" for d in ears[:4])
                stale = [d for d in ears if time.time() - (d.seen or 0) > STALE]
                self._step(w, "heard", "no", "Nothing happened while it watched",
                           f"It was listening to {said}." + (f" {stale[0].name} has been quiet longest; its battery is the likely reason." if stale else ""))
        else:
            self._step(w, "heard", "no", "Its trigger never happened while it watched")
        self._finish(w, False)

    def _finish(self, w, ok):
        """A try is over. `ok` None is stopped by hand. Its line stays on its row (the panel keeps it until
        the wall rests, the same as anything else somebody just touched).

        Steps still waiting are left as they are after a break -- drawn empty, not failed, because a
        strip is not at fault for a message it was never sent -- and after a pass they were simply not
        near where it happened."""
        if w["state"] not in ("watching", "running"): return
        w["state"] = "stopped" if ok is None else "passed" if ok else "failed"
        w["ended"] = time.time()
        if ok:
            for s in w["steps"]:
                if s["state"] == "wait": s.update(state="skip", sub="Not near where it happened")
        if ok is not None:
            bad = next((s for s in w["steps"] if s["state"] == "no"), None)
            line = "everything answered" if ok else (bad["text"][0].lower() + bad["text"][1:] if bad else "it did not finish")
            self.last[w["of"]] = {"line": line, "ok": bool(ok), "at": w["ended"]}
            self.hub.log.add("signal", w["of"], None, "tried", source="user", detail={"how": w["how"], "ok": bool(ok), "steps": w["steps"]})
        self._changed()


def _outcomes(r) -> list:
    then = (r or {}).get("then")
    if isinstance(then, list): return [t for t in then if isinstance(t, dict)]
    return [then] if isinstance(then, dict) else []
