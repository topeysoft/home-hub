"""The assistant: it writes and explains, and never runs anything.

Two jobs. Authoring turns a sentence ("when I leave, everything off") into a rule in the vocabulary of
rules.json, saved under "drafts" until a person approves it on the panel; the evaluator never reads
drafts. Explaining answers "why did the hallway light come on" from the event log; the model turns the
log's detail into prose and adds nothing the log does not say. The brain is the only thing that talks
to the model, and the model never sees a token for the driver layer. Design: docs/phase4-intelligence.md.
"""
import asyncio, json, logging, os, re, time
from collections import defaultdict
from datetime import datetime
from . import rules as rules_mod
from .presence import word as presence_word

LABEL = {"occupied": "Here", "empty": "All off", "asleep": "Sleep", "away": "Everything off", "movie": "Movie", "guests": "Guests"}
LOOKBACK_DAYS, MIN_DAYS, BIN_MINUTES = 14, 4, 30   # a habit: the same tap in the same half hour on four of the last fourteen days

try:
    import anthropic
except ImportError:          # optional: without the package the panel says the assistant is not available
    anthropic = None

log = logging.getLogger("hub.assistant")
MODEL = "claude-opus-5"
FALLBACK_BETA = "server-side-fallback-2026-07-01"   # a declined request is answered by a fallback model instead of failing


class AssistantError(Exception):
    def __init__(self, msg, status=502):
        super().__init__(msg); self.status = status


VOCABULARY = """A rule is one JSON object: {"id", "name", "room", "when", "if", "then"}.
- "name": one plain sentence a person would say about it, no jargon. "id": short kebab-case.
- "room": a room id from the house, "home" for the whole house, or "entry" for every room the family comes in through
  (they choose those on the panel; a rule for "entry" runs in each of them).
- "when", exactly one trigger:
  {"motion": "on"}                                  any motion sensor in the room (room rules only)
  {"contact": "open"} or {"contact": "closed"}      a door or window sensor in the room (room rules only)
  {"idle": <seconds>}                               no motion in the room for that long (room rules only)
  {"time": "HH:MM"}                                 once a day, 24-hour clock
  {"sun": "set" | "rise", "offset": <seconds>}      sunset or sunrise; a negative offset is before
  {"presence": "nobody" | "somebody", "for": <seconds>}   everyone has left, or someone is back; "for" is optional
  {"intent": "<state>", "in": "<room id or home>"}  a room, or the home, was just set to that state
  {"device": "<device id>", "state": "<state>"}     one named device reached a state (room rules only; last resort)
- "if", optional, all must hold; each is [subject, op, value]:
  ["sun", "below" | "above", <degrees>]             below 0 means after dark
  ["time", "between", ["HH:MM", "HH:MM"]]           may cross midnight; or "below" / "above" one time
  ["weekday", "in", ["mon", "tue", ...]] or ["weekday", "is" | "not", "sat"]
  ["intent", "is" | "not", "<state>"]               this room's current state
  ["home", "is" | "not", "<state>"]                 the whole house's current state
  ["presence", "is", "nobody" | "somebody"]
  ["light", "below" | "above", <lux>]               needs a light sensor in the room
  ["device", "<device id>", "is" | "not", "<state>"]
- "then", exactly one outcome:
  {"intent": "<state>"}                             the normal outcome: the room, or the house, goes to that state
  {"device": "<device id>", "action": "on" | "off" | "lock" | "unlock" | "open" | "close" | "pause" | "play"}
  {"device": "<speaker id>", "action": "sound", "data": {"sound": "<sound id>", "minutes": <optional>}}   a sound on a speaker
  {"device": "<speaker id>", "action": "sound_off"}
  {"notify": "<short text>"}
States and what they do in a room: occupied = lights on; empty = lights off, media paused; asleep = lights and
media off, doors locked; away = everything off, doors locked; movie = lights low, screen on; guests = lights bright.
A rule says one thing. Exceptions ("everything off except the porch"), several steps, or anything outside this
vocabulary cannot be one rule: then set ok to false and say, in one plain sentence, what you could do instead."""

DRAFT_SYSTEM = f"""You write routines for a family's house. The person says what they want in their own words; you
answer with one rule in the house's vocabulary, or say why you cannot. Prefer room states over devices. Use only
the rooms and devices listed. Never invent ids. Keep the name in the person's own plain words.

{VOCABULARY}

Some requests are for right now, not a standing rule: "play rain on Nadine's speaker", "turn the theater light off",
"white noise in the bedroom for an hour". Those are an action, not a rule: one device, one action, optional data
(a sound needs {{"sound": "<id>", "minutes": <optional>}}; volume takes {{"volume_level": 0.0-1.0}}), and a name saying
what will happen in plain words. The person confirms it on the panel before anything moves.

Answer as JSON. A rule: {{"ok": true, "kind": "rule", "reason": "", "rule_json": "<the rule as a JSON string>", "action_json": ""}}.
An action: {{"ok": true, "kind": "action", "reason": "", "rule_json": "", "action_json": "{{\"device\": \"<id>\", \"action\": \"<action>\", \"data\": {{}}, \"name\": \"<what will happen>\"}}"}}.
Neither: {{"ok": false, "kind": "", "reason": "<one plain sentence for the person>", "rule_json": "", "action_json": ""}}."""

DRAFT_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}, "kind": {"type": "string", "enum": ["rule", "action", ""]},
                                                 "reason": {"type": "string"}, "rule_json": {"type": "string"}, "action_json": {"type": "string"}},
                "required": ["ok", "kind", "reason", "rule_json", "action_json"], "additionalProperties": False}
ACTIONS = {"on", "off", "play", "pause", "next", "previous", "volume", "lock", "unlock", "open", "close", "set", "mode", "preset", "fan", "sound", "sound_off"}

EXPLAIN_SYSTEM = """You explain what a house did to the people who live in it. You get the house's recent log and a
question. Answer in two or three short sentences of plain English, using only what the log says; if the log does
not say, say so plainly rather than guess. Rules are called routines and go by their names. Never mention ids,
JSON, entities, Home Assistant, or the log itself. Use the times as given."""


class Assistant:
    def __init__(self, hub, client=None):
        self.hub = hub
        self._client, self._made, self._key_used = client, None, None   # tests hand in a fake client

    # ---- the key ----
    @property
    def available(self) -> bool:
        return anthropic is not None or self._client is not None

    def key(self):
        k = (self.hub.settings.get("assistant") or {}).get("key")
        if k: return k, "panel"
        k = self.hub.env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        return (k, "env") if k else (None, None)

    def status(self) -> dict:
        key, source = self.key()
        return {"available": self.available, "configured": bool(key or self._client), "source": source, "model": MODEL}

    def client(self):
        if self._client: return self._client
        if anthropic is None: raise AssistantError("The assistant is not installed on this hub.", 501)
        key, _ = self.key()
        if not key: raise AssistantError("The assistant isn't connected yet.", 409)
        if self._made is None or self._key_used != key:
            self._made, self._key_used = anthropic.AsyncAnthropic(api_key=key, timeout=90.0, max_retries=1), key
        return self._made

    async def set_key(self, key: str) -> dict:
        """Remember a key the panel pasted, after one cheap call proves it works. An empty key forgets it."""
        key = (key or "").strip()
        if not key:
            self.hub.settings.set(assistant={}); self._made = None; return self.status()
        if anthropic is None: raise ValueError("The assistant is not installed on this hub.")
        try: await anthropic.AsyncAnthropic(api_key=key, timeout=20.0, max_retries=0).models.retrieve(MODEL)
        except anthropic.AuthenticationError: raise ValueError("That key didn't work. Check it was copied whole.")
        except anthropic.APIConnectionError: raise ValueError("Couldn't reach the assistant. Is the hub online?")
        except anthropic.APIStatusError as e: raise ValueError(f"The assistant said no ({e.status_code}).")
        self.hub.settings.set(assistant={"key": key}); self._made = None
        self.hub.log.add("home", "assistant", None, "connected", source="user")
        return self.status()

    # ---- one call ----
    async def _ask(self, system, user, schema=None, max_tokens=4000, effort=None) -> str:
        kw = {"model": MODEL, "max_tokens": max_tokens, "system": system, "messages": [{"role": "user", "content": user}],
              "betas": [FALLBACK_BETA], "fallbacks": "default"}
        cfg = {}
        if schema: cfg["format"] = {"type": "json_schema", "schema": schema}
        if effort: cfg["effort"] = effort
        if cfg: kw["output_config"] = cfg
        try:
            r = await self.client().beta.messages.create(**kw)
        except AssistantError: raise
        except Exception as e:
            raise AssistantError(self._plain(e))
        if r.stop_reason == "refusal": raise AssistantError("The assistant wouldn't answer that.", 422)
        return "".join(b.text for b in r.content if getattr(b, "type", "") == "text")

    @staticmethod
    def _plain(e) -> str:
        if anthropic is not None:
            if isinstance(e, anthropic.AuthenticationError): return "The assistant's key no longer works."
            if isinstance(e, anthropic.RateLimitError): return "The assistant is busy. Try again in a minute."
            if isinstance(e, anthropic.APITimeoutError): return "The assistant took too long. Try again."
            if isinstance(e, anthropic.APIConnectionError): return "Couldn't reach the assistant. Is the hub online?"
            if isinstance(e, anthropic.APIStatusError): return f"The assistant had a problem ({e.status_code})."
        log.warning("assistant: %s", e)
        return "The assistant had a problem."

    # ---- what the model is told about the house ----
    def house(self) -> str:
        home, p = self.hub.home, self.hub.presence
        rooms = [f"  {r.id}: {r.name}" for r in home.rooms.values() if r.id != "unassigned"]
        devs = [f"  {d.id} | {d.name} | {d.capability} | in {d.room_id} | now {d.state}" for d in home.devices.values() if d.room_id != "unassigned"]
        ids = [r.get("id") for r in self.hub.engine.raw.get("rules", []) if isinstance(r, dict)]
        sounds = ", ".join(f"{s['id']} ({s['name']})" for s in self.hub.sounds.catalog()) or "none"
        now = datetime.now(self.hub.tz)
        entry = ", ".join(self.hub.entry) or "none chosen yet"
        return "\n".join(["Rooms (id: name):", *rooms, f"Entry rooms (the ones \"entry\" stands for): {entry}", "Devices (id | name | kind | room | state):", *devs,
                          f"Sounds a speaker (kind media) can play, by id: {sounds}",
                          f"Existing rule ids: {', '.join(i for i in ids if i) or 'none'}",
                          f"Now: {now.strftime('%A %H:%M')}. Who is home: {presence_word(p.somebody) or 'unknown'}."])

    # ---- authoring ----
    async def draft(self, said: str) -> dict:
        said = " ".join((said or "").split())
        if len(said) < 3: raise AssistantError("Say what you'd like the house to do.", 422)
        user = f"{self.house()}\n\nThe person said: “{said}”\nWrite the rule, or say why you can't."
        errors = []
        for _ in range(2):                       # one chance to fix a rule the house refuses
            ask = user if not errors else f"{user}\n\nThe house refused your previous rule: {'; '.join(errors)}. Fix it."
            try: out = json.loads(await self._ask(DRAFT_SYSTEM, ask, DRAFT_SCHEMA, max_tokens=2000))
            except ValueError: errors = ["the answer was not JSON"]; continue
            if not out.get("ok"): raise AssistantError(out.get("reason") or "That can't be one routine yet.", 422)
            if out.get("kind") == "action": return self.proposal(out.get("action_json"), said)
            try: rule = json.loads(out.get("rule_json") or "")
            except ValueError: errors = ["rule_json was not valid JSON"]; continue
            rule = self.adopt(rule, said)
            _, errors = rules_mod.validate({"rules": [rule]}, set(self.hub.home.rooms))
            if not errors: return self.keep(rule)
        raise AssistantError("The assistant couldn't write that as a routine the house can run: " + "; ".join(errors), 422)

    def proposal(self, action_json, said: str) -> dict:
        """A one-off action the model proposes. Checked against the house and handed back for a person to confirm; not run, not saved."""
        try: a = json.loads(action_json or "")
        except ValueError: raise AssistantError("The assistant's answer was not an action.", 422)
        if not isinstance(a, dict): raise AssistantError("The assistant's answer was not an action.", 422)
        dev = self.hub.home.devices.get(str(a.get("device") or ""))
        if not dev: raise AssistantError("The assistant named something the house does not have.", 422)
        action = str(a.get("action") or "")
        if action not in ACTIONS: raise AssistantError(f"The house cannot {action or 'do that'}.", 422)
        data = a.get("data") if isinstance(a.get("data"), dict) else {}
        if action == "sound" and not self.hub.sounds.path(str(data.get("sound", ""))): raise AssistantError("There is no such sound on the hub.", 422)
        name = re.sub(r"\s+", " ", str(a.get("name") or f"{action} {dev.name}")).strip().rstrip(".")
        out = {"kind": "action", "device": dev.id, "device_name": dev.name, "action": action, "data": data, "name": name, "said": said}
        self.hub.log.add("proposal", dev.id, None, action, source="assistant", detail=out)
        return out

    def adopt(self, rule, said: str) -> dict:
        """Make the model's rule ours: only the fields that matter, our provenance, an id nothing else has."""
        if not isinstance(rule, dict): raise AssistantError("The assistant's answer was not a rule.", 422)
        keep = {k: rule[k] for k in ("room", "when", "if", "then") if k in rule}
        name = re.sub(r"\s+", " ", str(rule.get("name") or said)).strip().rstrip(".")
        taken = {r.get("id") for r in self.hub.engine.raw.get("rules", []) if isinstance(r, dict)} | {d.get("id") for d in self.drafts()}
        base = re.sub(r"[^a-z0-9]+", "-", str(rule.get("id") or name).lower()).strip("-")[:40] or "routine"
        rid, n = base, 2
        while rid in taken: rid, n = f"{base}-{n}", n + 1
        return {"id": rid, "name": name, **keep, "enabled": True, "by": "assistant", "said": said, "created": time.time()}

    # ---- drafts: written by the assistant, moved by a person ----
    def _raw(self) -> dict:
        self.hub.engine.load()
        raw = {k: v for k, v in self.hub.engine.raw.items() if k not in ("valid", "errors")}
        raw.setdefault("rules", []); raw["drafts"] = [d for d in raw.get("drafts") or [] if isinstance(d, dict)]
        return raw

    def drafts(self) -> list:
        return self._raw()["drafts"]

    def keep(self, rule: dict) -> dict:
        rule = {"kind": "rule", **rule}
        raw = self._raw(); raw["drafts"].append(rule)
        self.hub.engine.save(raw)
        self.hub.log.add("draft", rule["id"], None, "proposed", source="assistant", detail={"said": rule.get("said"), "rule": rule})
        self._announce(); return rule

    def approve(self, rid: str) -> dict:
        raw = self._raw()
        d = next((d for d in raw["drafts"] if d.get("id") == rid), None)
        if not d: raise AssistantError("That suggestion is gone.", 404)
        rule = {**d, "approved": time.time()}
        raw["drafts"] = [x for x in raw["drafts"] if x is not d]
        raw["rules"].append(rule)
        self.hub.engine.save(raw)          # refused, with reasons, if the rule cannot run today; the draft then stays put
        self.hub.log.add("draft", rid, "proposed", "approved", source="user", detail={"rule": rule})
        self._announce(); return rule

    def discard(self, rid: str) -> None:
        raw = self._raw()
        d = next((d for d in raw["drafts"] if d.get("id") == rid), None)
        if not d: raise AssistantError("That suggestion is gone.", 404)
        raw["drafts"] = [x for x in raw["drafts"] if x is not d]
        self.hub.engine.save(raw)
        if d.get("noticed"):                          # a habit they turned down stays turned down
            seen = list(self.hub.settings.get("dismissed") or [])
            if d["noticed"] not in seen: self.hub.settings.set(dismissed=(seen + [d["noticed"]])[-50:])
        self.hub.log.add("draft", rid, "proposed", "discarded", source="user")
        self._announce()

    # ---- suggesting: habits the log shows, offered as drafts, never run ----
    def habits(self, now=None) -> list:
        """The same scene chosen by hand in the same half hour on enough different days: [(room, state, "HH:MM", days)]."""
        now = now or time.time()
        since = now - LOOKBACK_DAYS * 86400
        seen = defaultdict(lambda: defaultdict(list))                 # (room, state, bin) -> day -> [minute of day]
        for e in self.hub.log.recent(5000, kinds=("intent",)):
            if e["source"] != "user" or e["ts"] < since or not e["new"]: continue
            d = datetime.fromtimestamp(e["ts"], self.hub.tz)
            minute = d.hour * 60 + d.minute
            seen[(e["subject"], e["new"], minute // BIN_MINUTES)][d.date()].append(minute)
        out = []
        for (room, state, _), days in seen.items():
            if len(days) < MIN_DAYS: continue
            mins = sorted(m for ms in days.values() for m in ms)
            mid = mins[len(mins) // 2]
            out.append((room, state, f"{mid // 60:02d}:{mid % 60:02d}", len(days)))
        return sorted(out, key=lambda h: -h[3])

    def _covered(self, room, state, hhmm) -> bool:
        """Already a rule or draft for that room, state and time (give or take the bin)?"""
        want = int(hhmm[:2]) * 60 + int(hhmm[3:])
        for r in self.hub.engine.raw.get("rules", []) + self.drafts():
            if not isinstance(r, dict) or r.get("room") != room or (r.get("then") or {}).get("intent") != state: continue
            t = (r.get("when") or {}).get("time")
            if t and abs(int(t[:2]) * 60 + int(t[3:]) - want) <= BIN_MINUTES: return True
        return False

    def suggest(self, now=None) -> list:
        """Turn each new habit into a draft. Returns what it added. Deterministic: no model in here."""
        added, dismissed = [], set(self.hub.settings.get("dismissed") or [])
        for room, state, hhmm, days in self.habits(now):
            key = f"{room}:{state}:{hhmm[:2]}"
            if key in dismissed or self._covered(room, state, hhmm): continue
            if room != "home" and room not in self.hub.home.rooms: continue
            place = "the whole house" if room == "home" else f"the {self.hub.home.rooms[room].name}"
            word = "Bedtime" if (room == "home" and state == "asleep") else LABEL.get(state, state)
            clock = datetime.strptime(hhmm, "%H:%M").strftime("%-I:%M %p").lower()
            rule = self.adopt({"id": f"{room}-{hhmm.replace(':', '')}-{state}", "name": f"{word} for {place} at {clock}, like most evenings" if int(hhmm[:2]) >= 17 else f"{word} for {place} at {clock} every day",
                               "room": room, "when": {"time": hhmm}, "then": {"intent": state}}, "")
            rule["noticed"] = key
            rule["why"] = f"You chose {word} for {place} around {clock} on {days} of the last {LOOKBACK_DAYS} days."
            rule.pop("said", None)
            _, errors = rules_mod.validate({"rules": [rule]}, set(self.hub.home.rooms))
            if errors: continue
            added.append(self.keep(rule))
        return added

    async def run(self):
        """Once a day, look for habits. Cheap, local, and only ever adds drafts."""
        await asyncio.sleep(300)
        while True:
            try:
                if self.hub.driver == "ready": self.suggest()
            except Exception: log.exception("suggest")
            await asyncio.sleep(86400)

    def _announce(self):
        self.hub._broadcast(json.dumps({"type": "drafts", "drafts": self.drafts()}))

    # ---- explaining ----
    def story(self, room_id: str) -> str:
        """The log as lines the model can read: what set the room, and what its devices did, oldest first."""
        home, room = self.hub.home, self.hub.home.rooms.get(room_id)
        subjects = ("home",) if room_id == "home" else (room_id, "home")
        told = self.hub.log.recent(12, subject=subjects, kinds=("intent", "held", "shadowed", "failed", "presence"))
        ids = {d.id for d in (room.devices if room else home.devices.values())}
        seen = [e for e in self.hub.log.recent(300, kinds=("state", "action")) if e["subject"] in ids][:25]
        names = {r.get("id"): r.get("name") for r in self.hub.engine.raw.get("rules", []) if isinstance(r, dict)}
        names.update({d.id: d.name for d in home.devices.values()})
        when = lambda ts: datetime.fromtimestamp(ts, self.hub.tz).strftime("%a %H:%M")
        out = []
        for e in sorted(told + seen, key=lambda e: e["ts"]):
            who = names.get(e["subject"], "the whole house" if e["subject"] == "home" else e["subject"])
            line = f"{when(e['ts'])}  {e['kind']}: {who} {e['old'] or '?'} -> {e['new']} (by {e['source']})"
            if e["kind"] != "state" and e.get("detail"):
                try:
                    d = json.loads(e["detail"])
                    if d.get("rule"): d["rule"] = f"{d['rule']} ({names.get(d['rule'], 'a routine since removed')})"
                    line += f"  {json.dumps({k: v for k, v in d.items() if k in ('rule', 'trigger', 'checked', 'until', 'set_by', 'failed', 'people', 'alarm')})}"
                except ValueError: pass
            out.append(line)
        return "\n".join(out) or "(nothing in the log for this room yet)"

    async def explain(self, room_id: str, question: str | None) -> dict:
        room = self.hub.home.rooms.get(room_id)
        if room_id != "home" and not room: raise AssistantError("Unknown room.", 404)
        question = " ".join((question or "").split()) or "Why is this room the way it is?"
        name = room.name if room else "the whole house"
        state = (f"It is set to {room.intent}, by {room.set_by or 'nobody yet'}" + (f", held until {datetime.fromtimestamp(room.hold_until, self.hub.tz).strftime('%H:%M')}" if room and room.hold_until else "")) if room else f"The house is set to {self.hub.home.intent}"
        routines = [f"  {r.get('name')}" for r in self.hub.engine.raw.get("rules", []) if isinstance(r, dict) and r.get("room") in (room_id, "home")]
        user = "\n".join([f"Room: {name}. {state}. Now: {datetime.now(self.hub.tz).strftime('%A %H:%M')}.",
                          "Routines for it:", *(routines or ["  none"]), "", "Log, oldest first:", self.story(room_id), "",
                          f"Question: {question}"])
        answer = (await self._ask(EXPLAIN_SYSTEM, user, max_tokens=600, effort="low")).strip()
        self.hub.log.add("ask", room_id, None, question, source="user", detail={"answer": answer})
        return {"question": question, "answer": answer}
