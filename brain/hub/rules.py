"""Rules: signals in, room intents out.

A rule is one row in ../rules.json: `when <trigger> [if <conditions>] then <outcome>`. The Engine
turns state changes and the clock into firings, and every firing goes through the same path the
panel uses, logged with source="rule" and enough detail to say why. Deterministic on purpose: the
assistant may draft a rule, a person approves it, this code runs it. Design: docs/phase4-intelligence.md.
"""
import asyncio, json, logging, os, time
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from . import sun
from .intents import RoomState, SERVICE
from .presence import word as presence_word

log = logging.getLogger("hub.rules")
RULES_PATH = Path(__file__).resolve().parent.parent / "rules.json"

TRIGGERS = ("motion", "contact", "device", "idle", "time", "sun", "presence", "intent")
OUTCOMES = ("intent", "device", "notify")
SUBJECTS = ("sun", "time", "weekday", "intent", "home", "presence", "light", "device")
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


def _condition_parts(c):
    """[subject, op, value], or [device, id, value] / [device, id, op, value] -> (subject, arg, op, value)."""
    if c[0] == "device":
        return "device", c[1], (c[2] if len(c) == 4 else "is"), c[-1]
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
            if room != "home" and room not in rooms: raise ValueError(f"unknown room {room!r}")
            when = r.get("when")
            if not isinstance(when, dict): raise ValueError('needs a "when"')
            kinds = [k for k in when if k in TRIGGERS]
            if len(kinds) != 1: raise ValueError('"when" needs exactly one trigger')
            kind = kinds[0]
            if kind in ("motion", "contact", "idle", "device") and room == "home":
                raise ValueError(f"{kind} needs a room, not home")
            if kind == "motion" and when[kind] != "on": raise ValueError('motion can only be "on"')
            if kind == "contact" and when[kind] not in ("open", "closed"): raise ValueError("contact must be open or closed")
            if kind == "idle" and not (isinstance(when[kind], (int, float)) and when[kind] > 0): raise ValueError("idle is seconds, above 0")
            if kind == "time": _hhmm(when[kind])
            if kind == "sun" and when[kind] not in ("rise", "set"): raise ValueError("sun must be rise or set")
            if kind == "presence":
                if when[kind] not in ("somebody", "nobody"): raise ValueError("presence must be somebody or nobody")
                wait = when.get("for", 0)
                if not (isinstance(wait, (int, float)) and wait >= 0): raise ValueError('"for" is seconds, 0 or more')
            if kind == "intent": RoomState(when[kind])
            if kind == "device" and not (isinstance(when[kind], str) and when.get("state") is not None):
                raise ValueError("a device trigger needs a device id and a state")
            for c in r.get("if") or []:
                if not (isinstance(c, list) and len(c) >= 3 and c[0] in SUBJECTS): raise ValueError(f"bad condition {c}")
                _, _, op, _ = _condition_parts(c)
                if op not in OPS: raise ValueError(f"bad operator {op!r} in {c}")
            then = r.get("then")
            if not isinstance(then, dict): raise ValueError('needs a "then"')
            outs = [k for k in then if k in OUTCOMES]
            if len(outs) != 1: raise ValueError('"then" needs exactly one outcome')
            if outs[0] == "intent": RoomState(then["intent"])
            if outs[0] == "device" and not then.get("action"): raise ValueError("a device outcome needs an action")
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
        self._sun_cache = {}        # (date, lat, lon) -> (sunrise, sunset)

    # ---- the file ----
    def load(self, force=False):
        """Re-read rules.json when it changed. A file that will not parse keeps the previous rules running."""
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

    def _active(self, kind=None, room_id=None):
        self.load()
        for r in self.rules:
            if not r.get("enabled", True): continue
            if kind and kind not in r["when"]: continue
            if room_id and r["room"] != room_id: continue
            yield r

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
        return None

    def check(self, cond, room, now):
        """A condition with what it saw: [..., actual, ok]. An unknown subject never passes."""
        subject, arg, op, val = _condition_parts(cond)
        actual = self.value(subject, arg, room, now)
        ok = actual is not None and _compare(op, actual, val)
        shown = [subject, arg, op, val] if subject == "device" else [subject, op, val]
        return shown + [actual, ok]

    # ---- deciding ----
    def _consider(self, rules, trigger):
        """Which of these rules fire now. The first that sets a room's intent wins it; the rest are shadowed."""
        now, ts, taken, out = self.now(), time.time(), set(), []
        for r in rules:
            target = self.hub.home.rooms.get(r["room"])          # None for "home"
            checked = [self.check(c, target, now) for c in r.get("if") or []]
            why = {"rule": r["id"], "trigger": trigger, "checked": checked}
            if not all(c[-1] for c in checked):
                log.debug("rule %s: conditions not met %s", r["id"], checked); continue
            if "intent" in r["then"]:
                if r["room"] in taken:
                    self.hub.log.add("shadowed", r["room"], None, r["then"]["intent"], source="rule", detail=why); continue
                if target and target.hold_until and target.hold_until > ts:
                    self.hub.log.add("held", r["room"], target.intent, r["then"]["intent"], source="rule",
                                     detail={**why, "until": target.hold_until, "set_by": target.set_by}); continue
                taken.add(r["room"])
            out.append((r, why))
        return out

    def _run(self, rules, trigger, depth=0):
        for r, why in self._consider(list(rules), trigger):
            asyncio.get_running_loop().create_task(self.fire(r, why, depth))

    async def fire(self, rule, why, depth=0):
        then = rule["then"]
        try:
            if "intent" in then:
                state = RoomState(then["intent"])
                if rule["room"] == "home":
                    await self.hub.set_home_intent(state, source="rule", detail=why, depth=depth)
                else:
                    await self.hub.set_intent(self.hub.home.rooms[rule["room"]], state, source="rule", detail=why, depth=depth)
            elif "device" in then:
                d = self.hub.home.devices.get(then["device"])
                key = (d.capability.split(".")[0], then["action"]) if d else None
                if key not in SERVICE: raise ValueError(f"{then['device']} cannot {then.get('action')}")
                domain, service = SERVICE[key]
                await self.hub.ha.call(domain, service, d.id, **(then.get("data") or {}))
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
        room = self.hub.home.rooms.get(dev.room_id)
        if not room or old == dev.state: return
        if dev.capability == "motion" and dev.state == "on":
            room.motion_at = time.time()
            self._run(self._active("motion", room.id), {"motion": "on", "device": dev.id})
        elif dev.capability == "contact" and dev.state in ("on", "off"):
            want = "open" if dev.state == "on" else "closed"
            self._run((r for r in self._active("contact", room.id) if r["when"]["contact"] == want),
                      {"contact": want, "device": dev.id})
        self._run((r for r in self._active("device") if r["when"]["device"] == dev.id and str(r["when"]["state"]) == dev.state),
                  {"device": dev.id, "state": dev.state})

    def on_presence(self):
        """Who is home changed. Presence rules with no wait fire now; those with `for` arm, and the tick decides."""
        p = self.hub.presence
        if p.somebody is None: return
        now = presence_word(p.somebody)
        self._run((r for r in self._active("presence") if not r["when"].get("for") and r["when"]["presence"] == now),
                  {"presence": now})

    def on_intent(self, subject, state: RoomState, depth=0):
        """A room, or the home, was set to a state. Rules waiting on that run once; they cannot chain."""
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
                self._idle_done[key] = room.motion_at
                self._run([r], {"idle": r["when"]["idle"], "since": room.motion_at})
        p = self.hub.presence
        if p.somebody is not None and p.since:
            now_word = presence_word(p.somebody)
            for r in self._active("presence"):
                wait = r["when"].get("for") or 0
                if not wait or r["when"]["presence"] != now_word: continue
                if ts - p.since >= wait and self._presence_done.get(r["id"]) != p.since:
                    self._presence_done[r["id"]] = p.since
                    self._run([r], {"presence": now_word, "for": wait, "since": p.since})

    def dry_run(self, rule_id):
        """What a rule would do, with every condition's current value. `would` is off, not yet, wait (a condition
        fails), held (a hand set the room), fire (an event rule, the moment its trigger comes) or armed (a timer
        rule, at `next`). Changes nothing."""
        r = self.get(rule_id)
        if not r: return None
        now, ts = self.now(), time.time()
        target = self.hub.home.rooms.get(r["room"])
        checked = [self.check(c, target, now) for c in r.get("if") or []]
        held = bool(target and target.hold_until and target.hold_until > ts and "intent" in r["then"])
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
        timer = any(k in when for k in ("idle", "time", "sun")) or ("presence" in when and bool(when.get("for")))
        if not r.get("enabled", True): would = "off"
        elif "presence" in when and self.hub.presence.somebody is None: would = "wait"   # the house cannot tell who is home yet
        elif not all(c[-1] for c in checked): would = "wait"
        elif held: would = "held"
        elif timer: would = "armed" if nxt else "wait"   # conditions hold; it fires at `next`, or never without motion
        else: would = "fire"                             # the moment the trigger happens
        return {"rule": r, "would": would, "next": nxt, "checked": checked, "time": now.strftime("%H:%M"),
                "sun": self.value("sun", None, None, now),
                "room": target and {"intent": target.intent, "set_by": target.set_by, "hold_until": target.hold_until, "motion_at": target.motion_at}}
