# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rules: signals in, room intents out.

A rule is one row in ../rules.json: `when <trigger> [if <conditions>] then <outcome>`. The Engine
turns state changes and the clock into firings, and every firing goes through the same path the
panel uses, logged with source="rule" and enough detail to say why. Deterministic on purpose: the
assistant may draft a rule, a person approves it, this code runs it. Design: docs/phase4-intelligence.md.
"""
import asyncio, json, logging, os, shutil, time
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from . import sun
from .intents import RoomState, SERVICE
from .presence import word as presence_word
from .settings import DATA

log = logging.getLogger("hub.rules")
SEED = Path(__file__).resolve().parent.parent / "rules.json"   # the repo's copy: a new hub starts from it
RULES_PATH = DATA / "rules.json"                                # the hub's own, in the data volume; panel switches and drafts live here
ENTRY = "entry"   # a rule's room may be "entry": every room the family comes in through, chosen on the panel

TRIGGERS = ("motion", "contact", "device", "idle", "time", "sun", "presence", "intent")
OUTCOMES = ("intent", "device", "notify")
SUBJECTS = ("sun", "time", "weekday", "intent", "home", "presence", "light", "device", "quiet")
OPS = ("is", "not", "below", "above", "between", "in")
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _hhmm(s):
    h, m = str(s).split(":")
    h, m = int(h), int(m)
    if not (0 <= h < 24 and 0 <= m < 60): raise ValueError(f"bad time {s!r}")
    return h, m


def _num(s):
    try: float(s); return True
    except (TypeError, ValueError): return False


def _compare(op, actual, val) -> bool:
    try:
        if op == "is": return str(actual) == str(val)
        if op == "not": return str(actual) != str(val)
        if op == "below": return float(actual) < float(val)
        if op == "above": return float(actual) > float(val)
        if op == "in": return actual in val
        if op == "between":
            a, b = val
            if isinstance(actual, str) and ":" in actual:        # a time window, possibly across midnight
                return a <= actual <= b if a <= b else (actual >= a or actual <= b)
            return float(a) <= float(actual) <= float(b)
    except (TypeError, ValueError):
        return False
    return False


def _wait(when: dict) -> float:
    """A trigger's `for`: how long the thing has to have been true before the rule counts. Seconds, and
    zero means none. Shared by the two triggers that take one, so they cannot drift apart -- and `bool`
    is refused by hand, because in Python `True` is an int and "for": true is a typo, not three seconds."""
    w = when.get("for", 0)
    if isinstance(w, bool) or not isinstance(w, (int, float)) or w < 0: raise ValueError('"for" is seconds, 0 or more')
    return float(w)


def rooms_of(r) -> list:
    """A rule's rooms, always a list. `room` is one id, "home", "entry", or a list of ids -- and the list is
    what keeps "the hallway, the stairs and the landing" one rule instead of three copies drifting apart."""
    room = r.get("room") if isinstance(r, dict) else None
    return [x for x in room if isinstance(x, str)] if isinstance(room, list) else [room]


def outcomes_of(r) -> list:
    """A rule's outcomes, always a list. `then` is one object or a list of them, run in order."""
    then = r.get("then") if isinstance(r, dict) else None
    if isinstance(then, list): return [t for t in then if isinstance(t, dict)]
    return [then] if isinstance(then, dict) else []


def _condition_parts(c):
    """[subject, op, value], or [device, id, value] / [device, id, op, value] / [quiet, rooms, op, seconds]
    -> (subject, arg, op, value). A `quiet` with no rooms named means the rule's own room."""
    if c[0] == "device":
        return "device", c[1], (c[2] if len(c) == 4 else "is"), c[-1]
    if c[0] == "quiet" and len(c) >= 4:
        return "quiet", c[1], c[2], c[3]
    return c[0], None, c[1], c[2]


def validate(raw, rooms: set) -> tuple[list, list]:
    """The rules that can run and one message per problem. A bad rule is dropped; the rest still run."""
    good, errors, seen = [], [], set()
    if not isinstance(raw, dict) or not isinstance(raw.get("rules"), list):
        return [], ['the file needs a "rules" list']
    for i, r in enumerate(raw["rules"]):
        label = (r.get("id") if isinstance(r, dict) and r.get("id") else None) or f"rule #{i + 1}"
        try:
            if not isinstance(r, dict): raise ValueError("not an object")
            rid = r.get("id")
            if not rid or not isinstance(rid, str): raise ValueError("needs an id")
            if rid in seen: raise ValueError("duplicate id")
            room = r.get("room")
            if isinstance(room, list):
                if not room: raise ValueError('"room" is a list of room ids, and it cannot be empty')
                if len(set(room)) != len(room): raise ValueError('"room" names the same room twice')
                for x in room:
                    # "home" and "entry" already mean a set of rooms; nesting one inside a list would give
                    # two ways to say the same thing and a question about what the overlap means.
                    if x in ("home", ENTRY): raise ValueError(f'{x!r} cannot go in a list of rooms; use it on its own')
                    if x not in rooms: raise ValueError(f"unknown room {x!r}")
            elif room not in ("home", ENTRY) and room not in rooms:
                raise ValueError(f"unknown room {room!r}")
            when = r.get("when")
            if not isinstance(when, dict): raise ValueError('needs a "when"')
            kinds = [k for k in when if k in TRIGGERS]
            if len(kinds) != 1: raise ValueError('"when" needs exactly one trigger')
            kind = kinds[0]
            if kind in ("motion", "contact", "idle", "device") and "home" in rooms_of(r):
                raise ValueError(f"{kind} needs a room, not home")
            if kind == "motion" and when[kind] != "on": raise ValueError('motion can only be "on"')
            if kind == "contact" and when[kind] not in ("open", "closed"): raise ValueError("contact must be open or closed")
            if kind == "idle" and not (isinstance(when[kind], (int, float)) and when[kind] > 0): raise ValueError("idle is seconds, above 0")
            if kind == "time": _hhmm(when[kind])
            if kind == "sun" and when[kind] not in ("rise", "set"): raise ValueError("sun must be rise or set")
            if kind == "presence":
                if when[kind] not in ("somebody", "nobody"): raise ValueError("presence must be somebody or nobody")
                _wait(when)
            if kind == "intent": RoomState(when[kind])
            if kind == "device":
                if not (isinstance(when[kind], str) and when.get("state") is not None):
                    raise ValueError("a device trigger needs a device id and a state")
                # and it may WAIT, which turns an event into a standing condition: "the front door has
                # been unlocked for three hours" is a different rule from "the front door unlocked".
                _wait(when)
            for c in r.get("if") or []:
                if not (isinstance(c, list) and len(c) >= 3 and c[0] in SUBJECTS): raise ValueError(f"bad condition {c}")
                subject, arg, op, val = _condition_parts(c)
                if op not in OPS: raise ValueError(f"bad operator {op!r} in {c}")
                if subject == "quiet":
                    if op not in ("above", "below"): raise ValueError("quiet takes above or below, in seconds")
                    if isinstance(val, bool) or not isinstance(val, (int, float)) or val < 0:
                        raise ValueError("quiet is seconds, 0 or more")
                    named = [arg] if isinstance(arg, str) else arg if isinstance(arg, list) else []
                    if arg is not None and not named: raise ValueError("quiet names a room, a list of rooms, or nothing")
                    for x in named:
                        if x not in rooms: raise ValueError(f"unknown room {x!r} in {c}")
            then = r.get("then")
            if isinstance(then, list) and not then: raise ValueError('"then" is a list of outcomes, and it cannot be empty')
            if not isinstance(then, (dict, list)): raise ValueError('needs a "then"')
            for t in (then if isinstance(then, list) else [then]):
                if not isinstance(t, dict): raise ValueError("an outcome is an object")
                outs = [k for k in t if k in OUTCOMES]
                if len(outs) != 1: raise ValueError('each outcome in "then" is exactly one of ' + ", ".join(OUTCOMES))
                if outs[0] == "intent": RoomState(t["intent"])
                if outs[0] == "device" and not t.get("action"): raise ValueError("a device outcome needs an action")
        except (ValueError, KeyError, TypeError) as e:
            errors.append(f"{label}: {e}"); continue
        seen.add(rid); good.append(r)
    return good, errors


class Engine:
    def __init__(self, hub):
        self.hub = hub
        self.raw, self.rules, self.errors, self._mtime = {"rules": []}, [], [], None
        self._last_tick = None      # when the tick last ran, so time and sun triggers fire exactly once
        self._idle_done = {}        # (rule id, room id) -> the motion_at an idle rule already fired for
        self._presence_done = {}    # rule id -> the presence `since` a waiting presence rule already fired for
        self._device_done = {}      # rule id -> the device `since` a waiting device rule already fired for: once per spell, not once a second
        self._sun_cache = {}        # (date, lat, lon) -> (sunrise, sunset)
        self._once = set()          # rule ids whose absolute outcomes have run THIS wake-up: see _pass()

    # ---- the file ----
    def load(self, force=False):
        """Re-read rules.json when it changed. A file that will not parse keeps the previous rules running."""
        if not RULES_PATH.exists() and SEED.exists() and SEED.resolve() != RULES_PATH.resolve():
            try: RULES_PATH.parent.mkdir(parents=True, exist_ok=True); shutil.copy(SEED, RULES_PATH); log.info("rules seeded from %s", SEED)
            except OSError as e: log.warning("could not seed rules.json: %s", e)
        try:
            mtime = RULES_PATH.stat().st_mtime
        except FileNotFoundError:
            self.raw, self.rules, self.errors, self._mtime = {"rules": []}, [], [], None
            return
        if mtime == self._mtime and not force: return
        try:
            raw = json.loads(RULES_PATH.read_text())
        except Exception as e:
            self.errors = [f"rules.json is not valid JSON: {e}"]; self._mtime = mtime
            log.warning("rules.json is not usable (%s); keeping the previous rules", e); return
        self.raw = raw
        self.rules, self.errors = validate(raw, set(self.hub.home.rooms))
        self._mtime = mtime
        log.info("rules loaded: %d active, %d problems", len(self.rules), len(self.errors))
        for e in self.errors: log.warning("rules.json: %s", e)

    def save(self, raw):
        """Replace the file, but only with something every rule of which can run."""
        _, errors = validate(raw, set(self.hub.home.rooms))
        if errors: raise ValueError("; ".join(errors))
        tmp = RULES_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(raw, indent=2) + "\n")
        os.replace(tmp, RULES_PATH)
        self.load(force=True)

    def as_data(self):
        self.load()
        return {**self.raw, "valid": not self.errors, "errors": self.errors}

    def get(self, rule_id):
        self.load()
        return next((r for r in self.rules if r["id"] == rule_id), None)

    def _concrete(self, r):
        """One rule per room it runs in. A list of rooms is that list; "entry" is every room the family comes
        in through, and with none chosen it is nothing. Everything downstream sees a rule with one room."""
        out = []
        for rid in rooms_of(r):
            if rid == ENTRY:
                out += [{**r, "room": x} for x in self.hub.entry if x in self.hub.home.rooms]
            else:
                out.append({**r, "room": rid})
        return out

    def _active(self, kind=None, room_id=None):
        self.load()
        for r in self.rules:
            if not r.get("enabled", True): continue
            if kind and kind not in r["when"]: continue
            for rr in self._concrete(r):
                if room_id and rr["room"] != room_id: continue
                yield rr

    # ---- signals ----
    def now(self) -> datetime:
        return datetime.now(self.hub.tz)

    def _sun_times(self, day):
        loc = self.hub.location
        if not loc: return None, None
        key = (day, loc["lat"], loc["lon"])
        if key not in self._sun_cache:
            start = datetime.combine(day, dtime(0, 0), tzinfo=self.hub.tz)
            self._sun_cache = {key: sun.crossings(start, loc["lat"], loc["lon"])}
        return self._sun_cache[key]

    def value(self, subject, arg, room, now):
        """What a condition's subject is right now, or None when the house cannot tell."""
        if subject == "sun":
            loc = self.hub.location
            return round(sun.elevation(now, loc["lat"], loc["lon"]), 1) if loc else None
        if subject == "time": return now.strftime("%H:%M")
        if subject == "weekday": return WEEKDAYS[now.weekday()]
        if subject == "intent": return room.intent if room else None
        if subject == "home": return self.hub.home.intent
        if subject == "presence": return presence_word(self.hub.presence.somebody)
        if subject == "light":
            vals = [float(d.state) for d in (room.devices if room else []) if d.capability == "sensor.illuminance" and _num(d.state)]
            return round(sum(vals) / len(vals), 1) if vals else None
        if subject == "device":
            d = self.hub.home.devices.get(arg)
            return d.state if d else None
        if subject == "quiet":
            # Seconds since anything last moved in the rooms named -- the LEAST quiet of them governs, so
            # "above 1200" means every one of them has been still that long. A room the house cannot speak
            # for (no motion sensor, or none seen since the hub came up) makes the whole thing unknown, and
            # an unknown condition never passes: the failure lands on leaving lights ON, never on putting a
            # house dark around somebody it could not see.
            ids = [arg] if isinstance(arg, str) else list(arg) if isinstance(arg, list) else [room.id if room else None]
            now_ts, seen = time.time(), []
            for rid in ids:
                rm = self.hub.home.rooms.get(rid)
                if not rm or not rm.motion_at: return None
                seen.append(now_ts - rm.motion_at)
            return round(min(seen), 1) if seen else None
        return None

    def check(self, cond, room, now):
        """A condition with what it saw: [..., actual, ok]. An unknown subject never passes."""
        subject, arg, op, val = _condition_parts(cond)
        actual = self.value(subject, arg, room, now)
        ok = actual is not None and _compare(op, actual, val)
        shown = [subject, arg, op, val] if arg is not None else [subject, op, val]
        return shown + [actual, ok]

    # ---- deciding ----
    def _consider(self, rules, trigger):
        """Every rule's verdict now, as (concrete rule, why, verdict). The first that sets a room's intent
        wins it; the rest are shadowed.

        The verdict matters to the timer triggers. "wait" means the conditions were not ready, and a rule
        that is merely not ready keeps its turn -- *everything off upstairs once the landing is still too*
        must get another look when the landing goes still, not be spent on the first tick where it did not
        hold. "held" and "shadowed" mean the room has already spoken, and asking again each second would
        only write the same line to the log over and over."""
        now, ts, taken, out = self.now(), time.time(), set(), []
        for r in rules:
            target = self.hub.home.rooms.get(r["room"])          # None for "home"
            checked = [self.check(c, target, now) for c in r.get("if") or []]
            why = {"rule": r["id"], "trigger": trigger, "checked": checked}
            if not all(c[-1] for c in checked):
                log.debug("rule %s: conditions not met %s", r["id"], checked)
                out.append((r, why, "wait")); continue
            # A rule claims a room if ANY of its outcomes sets that room's intent; the rest of the
            # outcomes ride with it, so a shadowed or held rule does none of its work rather than half.
            wants = next((t["intent"] for t in outcomes_of(r) if "intent" in t), None)
            if wants is not None:
                if r["room"] in taken:
                    self.hub.log.add("shadowed", r["room"], None, wants, source="rule", detail=why)
                    out.append((r, why, "shadowed")); continue
                if target and target.hold_until and target.hold_until > ts:
                    self.hub.log.add("held", r["room"], target.intent, wants, source="rule",
                                     detail={**why, "until": target.hold_until, "set_by": target.set_by})
                    out.append((r, why, "held")); continue
                taken.add(r["room"])
            keep = []
            for t in outcomes_of(r):
                if "intent" in t: keep.append(t); continue
                # A rule naming several rooms is several concrete rules by here, and only `intent` varies by
                # room: a device outcome names an absolute id and a notify is one sentence. Running those
                # once per room would turn a light on twice and say the same thing to the panel three times.
                if r["id"] in self._once: continue
                # And a hand beats a rule here too, not only on an intent. Without this a rule that names a
                # light directly turns it straight back on at the next flicker of motion, seconds after
                # somebody switched it off -- the one thing a hold exists to stop. The room that governs is
                # the one the DEVICE is in, which is not always the room the rule is filed under.
                d = "device" in t and self.hub.home.devices.get(t["device"])
                held = d and self.hub.home.rooms.get(d.room_id)
                if held and held.hold_until and held.hold_until > ts:
                    self.hub.log.add("held", d.id, None, t.get("action"), source="rule",
                                     detail={**why, "until": held.hold_until, "set_by": held.set_by})
                    continue
                keep.append(t)
            self._once.add(r["id"])
            if not keep: out.append((r, why, "done")); continue
            out.append(({**r, "then": keep}, why, "fire"))
        return out

    def _pass(self):
        """Start a fresh evaluation pass. `_once` spans one wake-up rather than one `_consider`, because the
        timer triggers evaluate a multi-room rule one room at a time -- `tick` loops over concrete rules and
        calls `_run` for each, since every room carries its own idle clock. Without this, one rule saying
        "everything off upstairs, and tell me" would tell you once per room."""
        self._once = set()

    @staticmethod
    def _decided(verdicts) -> bool:
        """Did the rule get a real answer, or was it only not ready yet? A timer trigger spends its
        once-per-spell turn on the first, and keeps it on the second."""
        return any(v != "wait" for _, _, v in verdicts)

    def _run(self, rules, trigger, depth=0):
        """Schedules what fires and hands back every verdict, so a caller holding a once-per-spell latch can
        tell "it did not hold yet" from "the room said no"."""
        out = self._consider(list(rules), trigger)
        for r, why, verdict in out:
            if verdict == "fire": asyncio.get_running_loop().create_task(self.fire(r, why, depth))
        return out

    async def fire(self, rule, why, depth=0):
        """Run a rule's outcomes in the order they are written. One that fails is logged and the rest still
        run: a rule that lights the hall and opens the blind should not lose the hall to a dead blind."""
        for then in outcomes_of(rule):
            try:
                if "intent" in then:
                    state = RoomState(then["intent"])
                    if rule["room"] == "home":
                        await self.hub.set_home_intent(state, source="rule", detail=why, depth=depth)
                    else:
                        await self.hub.set_intent(self.hub.home.rooms[rule["room"]], state, source="rule", detail=why, depth=depth)
                elif "device" in then:
                    d = self.hub.home.devices.get(then["device"])
                    data = then.get("data") or {}
                    if d and then["action"] == "sound":
                        await self.hub.sounds.play(d, str(data.get("sound", "")), data.get("minutes"), data.get("volume"), source="rule"); continue
                    if d and then["action"] == "sound_off":
                        await self.hub.sounds.stop(d, source="rule"); continue
                    key = (d.capability.split(".")[0], then["action"]) if d else None
                    if key not in SERVICE: raise ValueError(f"{then['device']} cannot {then.get('action')}")
                    domain, service = SERVICE[key]
                    await self.hub.ha.call(domain, service, d.id, **data)
                    self.hub.log.add("action", d.id, None, then["action"], source="rule", detail=why)
                elif "notify" in then:
                    self.hub.log.add("notify", rule["room"], None, then["notify"], source="rule", detail=why)
                    self.hub._broadcast(json.dumps({"type": "notify", "text": then["notify"], "rule": rule["id"]}))
            except Exception as e:
                log.warning("rule %s failed: %s", rule["id"], e)
                self.hub.log.add("failed", rule["room"], None, str(e), source="rule", detail=why)

    # ---- what wakes rules ----
    def on_state(self, dev, old):
        """A device changed. Motion stamps its room and wakes motion rules; contact and device rules likewise."""
        self._pass()
        room = self.hub.home.rooms.get(dev.room_id)
        if not room or old == dev.state: return
        if dev.capability == "motion" and dev.state == "on":
            room.motion_at = time.time()
            self._run(self._active("motion", room.id), {"motion": "on", "device": dev.id})
        elif dev.capability == "contact" and dev.state in ("on", "off"):
            want = "open" if dev.state == "on" else "closed"
            self._run((r for r in self._active("contact", room.id) if r["when"]["contact"] == want),
                      {"contact": want, "device": dev.id})
        self._run((r for r in self._active("device")
                   if r["when"]["device"] == dev.id and str(r["when"]["state"]) == dev.state and not r["when"].get("for")),
                  {"device": dev.id, "state": dev.state})

    def on_presence(self):
        """Who is home changed. Presence rules with no wait fire now; those with `for` arm, and the tick decides."""
        self._pass()
        p = self.hub.presence
        if p.somebody is None: return
        now = presence_word(p.somebody)
        self._run((r for r in self._active("presence") if not r["when"].get("for") and r["when"]["presence"] == now),
                  {"presence": now})

    def on_intent(self, subject, state: RoomState, depth=0):
        """A room, or the home, was set to a state. Rules waiting on that run once; they cannot chain."""
        self._pass()
        if depth >= 1: return
        self._run((r for r in self._active("intent")
                   if r["when"]["intent"] == state.value and r["when"].get("in") in (None, subject)),
                  {"intent": state.value, "in": subject}, depth=depth + 1)

    def seed(self):
        """After a (re)connect, rooms remember their last motion, so idle rules count from something real."""
        last = self.hub.log.last_by_subject("state", "on")
        now = time.time()
        for room in self.hub.home.rooms.values():
            motion = [d for d in room.devices if d.capability == "motion"]
            if any(d.state == "on" for d in motion): room.motion_at = now
            elif not room.motion_at:
                ts = [last[d.id] for d in motion if d.id in last]
                if ts: room.motion_at = max(ts)

    async def run(self):
        while True:
            try:
                if self.hub.driver == "ready": self.tick()
            except Exception:
                log.exception("rules tick")
            await asyncio.sleep(1)

    def tick(self, now=None):
        """Once a second: clock times, sunrise and sunset, and rooms that have gone quiet."""
        self._pass()
        now = now or self.now()
        last, self._last_tick = self._last_tick, now
        if last is None or now - last > timedelta(minutes=5):
            return     # first tick, or the clock jumped (sleep, NTP): a whole day's triggers are not replayed
        days = (now.date(), (now - timedelta(days=1)).date())
        for r in self._active("time"):
            h, m = _hhmm(r["when"]["time"])
            for day in days:
                t = datetime.combine(day, dtime(h, m), tzinfo=now.tzinfo)
                if last < t <= now:
                    self._run([r], {"time": r["when"]["time"]}); break
        for r in self._active("sun"):
            off = timedelta(seconds=r["when"].get("offset", 0))
            for day in days:
                rise, set_ = self._sun_times(day)
                t = rise if r["when"]["sun"] == "rise" else set_
                if t and last < t + off <= now:
                    self._run([r], {"sun": r["when"]["sun"], "offset": r["when"].get("offset", 0), "at": (t + off).isoformat(timespec="minutes")}); break
        ts = time.time()
        for r in self._active("idle"):
            room = self.hub.home.rooms.get(r["room"])
            if not room or not room.motion_at: continue
            key = (r["id"], room.id)
            if ts - room.motion_at >= r["when"]["idle"] and self._idle_done.get(key) != room.motion_at:
                if self._decided(self._run([r], {"idle": r["when"]["idle"], "since": room.motion_at})):
                    self._idle_done[key] = room.motion_at
        p = self.hub.presence
        if p.somebody is not None and p.since:
            now_word = presence_word(p.somebody)
            for r in self._active("presence"):
                wait = r["when"].get("for") or 0
                if not wait or r["when"]["presence"] != now_word: continue
                if ts - p.since >= wait and self._presence_done.get(r["id"]) != p.since:
                    if self._decided(self._run([r], {"presence": now_word, "for": wait, "since": p.since})):
                        self._presence_done[r["id"]] = p.since
        # and a device that has STAYED somewhere. `d.since` is HA's own last_changed, so a brain that
        # restarts an hour in still fires at three hours rather than at four: the wait is the door's,
        # not this process's. Dedupe on that same `since`, so one spell unlocked says it once.
        for r in self._active("device"):
            wait = r["when"].get("for") or 0
            d = self.hub.home.devices.get(r["when"]["device"]) if wait else None
            if not d or str(r["when"]["state"]) != d.state: continue
            if ts - d.since >= wait and self._device_done.get(r["id"]) != d.since:
                if self._decided(self._run([r], {"device": d.id, "state": d.state, "for": wait, "since": d.since})):
                    self._device_done[r["id"]] = d.since

    def dry_run(self, rule_id):
        """What a rule would do, with every condition's current value. `would` is off, not yet, wait (a condition
        fails), held (a hand set the room), fire (an event rule, the moment its trigger comes) or armed (a timer
        rule, at `next`). Changes nothing."""
        r = self.get(rule_id)
        if not r: return None
        now, ts = self.now(), time.time()
        concrete = self._concrete(r)
        if not concrete: return {"rule": r, "would": "wait", "next": None, "checked": [], "time": now.strftime("%H:%M"),
                                 "sun": self.value("sun", None, None, now), "room": None, "note": "no entry rooms chosen yet"}
        r = concrete[0]                                  # the first room stands for them all here
        target = self.hub.home.rooms.get(r["room"])
        checked = [self.check(c, target, now) for c in r.get("if") or []]
        held = bool(target and target.hold_until and target.hold_until > ts and any("intent" in t for t in outcomes_of(r)))
        when, nxt = r["when"], None                      # timer triggers also say when they would next go off
        if "idle" in when:
            nxt = target.motion_at + when["idle"] if target and target.motion_at else None
        elif "time" in when:
            h, m = _hhmm(when["time"]); t = datetime.combine(now.date(), dtime(h, m), tzinfo=now.tzinfo)
            nxt = (t if t > now else t + timedelta(days=1)).timestamp()
        elif "sun" in when:
            for day in (now.date(), (now + timedelta(days=1)).date()):
                rise, set_ = self._sun_times(day)
                t = rise if when["sun"] == "rise" else set_
                if t and t + timedelta(seconds=when.get("offset", 0)) > now:
                    nxt = (t + timedelta(seconds=when.get("offset", 0))).timestamp(); break
        elif "presence" in when and when.get("for"):
            p = self.hub.presence
            nxt = p.since + when["for"] if p.since and presence_word(p.somebody) == when["presence"] else None
        elif "device" in when and when.get("for"):
            d = self.hub.home.devices.get(when["device"])
            nxt = d.since + when["for"] if d and str(when["state"]) == d.state else None
        timer = any(k in when for k in ("idle", "time", "sun")) or (bool(when.get("for")) and any(k in when for k in ("presence", "device")))
        if not r.get("enabled", True): would = "off"
        elif "presence" in when and self.hub.presence.somebody is None: would = "wait"   # the house cannot tell who is home yet
        elif not all(c[-1] for c in checked): would = "wait"
        elif held: would = "held"
        elif timer: would = "armed" if nxt else "wait"   # conditions hold; it fires at `next`, or never without motion
        else: would = "fire"                             # the moment the trigger happens
        return {"rule": r, "would": would, "next": nxt, "checked": checked, "time": now.strftime("%H:%M"),
                "sun": self.value("sun", None, None, now),
                "room": target and {"intent": target.intent, "set_by": target.set_by, "hold_until": target.hold_until, "motion_at": target.motion_at}}
