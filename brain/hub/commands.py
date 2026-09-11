"""Plain words into the house's own moves, with no model in the way.

The command box on Home (and, later, a microphone) hands every sentence here first. A fixed grammar over the
house's own names — its rooms, devices, kinds, scenes and sounds — runs at once, the way a tap does: "kitchen
lights off", "movie in the den", "lock the front door", "rain in the bedroom for an hour", "is the garage
closed?". Whatever the grammar cannot place goes to the assistant, which may only propose: an action a person
confirms, or a routine a person approves. So the model is never in the control loop; what runs on its own is
this file, and this file is deterministic. Every sentence is logged, understood or not, so the grammar can grow
from what people actually say. The plan for the microphone is docs/voice.md.
"""
import re
from .intents import RoomState

WORD_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
            "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "forty five": 45, "fifty": 50, "sixty": 60, "ninety": 90}
# Other words for a room, by the words a room is usually called. An alias only counts when no room's own name matched
# and a room whose name contains the canonical words exists ("hall" finds "Hallway"; "den" is only ever a room called Den).
ROOM_ALIASES = {"living room": ("lounge", "family room", "front room", "sitting room", "tv room", "living"),
                "hallway": ("hall", "landing", "corridor", "entryway", "foyer"),
                "bedroom": ("master", "master bedroom", "main bedroom", "our room"),
                "kids": ("kids room", "kid's room", "children's room", "nursery", "playroom"),
                "bathroom": ("bath", "loo", "toilet", "washroom", "ensuite", "en suite", "restroom"),
                "office": ("study",), "dining room": ("dining",), "backyard": ("yard", "back yard", "garden", "patio"),
                "basement": ("cellar",), "porch": ("front porch", "stoop"), "theatre": ("theater", "cinema"), "theater": ("theatre", "cinema")}
EVERYWHERE = r"(everywhere|in every room|in all( the)? rooms|in the (whole )?house|(the )?whole house|all over( the house)?|downstairs and upstairs)"
POLITE = r"^((hey|ok|okay|please|hi|house|hub|home|alexa|siri|computer)[, ]+|(can|could|would|will) you (please )?|i('?d| would) like (you )?to |i want (you )?to |let'?s |go ahead and )+"
KINDS = (   # words for a kind of thing, in the order they are tried; the garage door is a cover before "door" is a lock
    (r"garage( door)?|blinds?|shades?|curtains?|shutters?|awnings?", "cover", None),
    (r"lights?|lamps?|lighting", "light", None),
    (r"tvs?|telly|television|screen|projector", "media", "tv"),
    (r"speakers?|music|radio|stereo|sound system|audio|sonos|homepod|echo", "media", "speaker"),
    (r"fans?", "fan", None),
    (r"plugs?|outlets?|sockets?|switch(es)?", "switch", None),
    (r"doors?|locks?|deadbolt", "lock", None),
    (r"thermostat|heat(ing|er)?|ac|a/c|air ?con(ditioning|ditioner)?|temperature|temp|furnace", "climate", None),
)
TV = re.compile(r"\b(tv|television|telly|roku|apple tv|fire tv|chromecast|shield|screen|projector|theatre|theater)\b", re.I)
STATE_WORDS = {"on": "on", "off": "off", "open": "open", "opened": "open", "closed": "closed", "shut": "closed", "locked": "locked", "unlocked": "unlocked",
               "playing": "playing", "paused": "paused", "running": "on", "home": "home", "in": "home", "here": "home", "out": "away", "away": "away"}
SCENES = ((r"movie( time| night)?|film( night)?", RoomState.movie), (r"guests?|party( mode)?|company|entertain(ing)?", RoomState.guests),
          (r"sleep|asleep|bed ?time|good ?night|night night|lights out", RoomState.asleep))
LABEL = {"occupied": "Here", "empty": "All off", "asleep": "Sleep", "away": "Everything off", "movie": "Movie", "guests": "Guests"}


class NotUnderstood(Exception):
    """The grammar has nothing for this sentence. The message is for the person."""


def norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("‘", "'").lower()
    s = re.sub(r"[^\w\s'%/-]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _tidy(text: str) -> str:
    """Lower case, no punctuation, no politeness on either end."""
    t = norm(text)
    t = re.sub(POLITE, "", t)
    t = re.sub(r"( please| thanks| thank you| for me| now| right now)+$", "", t).strip()
    return t


def _has(word: str, text: str) -> bool:
    return re.search(rf"(?<![\w'])(?:{word})(?![\w'])", text) is not None


def _cut(word: str, text: str) -> str:
    """Take a phrase out, with the little words that introduced it."""
    return re.sub(r"\s+", " ", re.sub(rf"(\b(in|for|of|at|to|from|through) )?(the |my |our )?(?<![\w'])(?:{word})(?![\w'])", " ", text, count=1)).strip()


def _number(text: str):
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    if m: return float(m.group(1))
    for w, n in sorted(WORD_NUM.items(), key=lambda kv: -len(kv[0])):
        if _has(w, text): return float(n)
    return None


def _minutes(text: str):
    """"for an hour", "for 20 minutes", "for half an hour" -> minutes and the text without them."""
    m = re.search(r"\bfor (half an hour|an hour and a half|(?:(\w+(?: \w+)?) )?(hours?|hrs?|minutes?|mins?))\b", text)
    if not m: return None, text
    whole = m.group(1)
    if whole == "half an hour": mins = 30
    elif whole == "an hour and a half": mins = 90
    else:
        n = _number(m.group(2) or "") if m.group(2) else 1
        if n is None: return None, text
        mins = n * 60 if m.group(3).startswith("h") else n
    return int(mins), re.sub(r"\s+", " ", text[:m.start()] + text[m.end():]).strip()


def room_names(room) -> list:
    """The ways a room is written: its name, and without an apostrophe-s."""
    n = norm(room.name)
    out = [n]
    if "'" in n: out.append(n.replace("'s", "s").replace("'", ""))
    return out


def find_room(text: str, rooms: dict):
    """The room a sentence names, longest match first, aliases only when no room's own name is there. (room, text without it)."""
    best = None
    for r in rooms.values():
        if r.id == "unassigned": continue
        for n in room_names(r):
            if n and _has(re.escape(n), text) and (best is None or len(n) > len(best[1])): best = (r, n)
    if best is None:
        for canon, aliases in ROOM_ALIASES.items():
            for r in rooms.values():
                if r.id == "unassigned" or canon not in norm(r.name): continue
                for a in aliases:
                    if _has(re.escape(a), text) and (best is None or len(a) > len(best[1])): best = (r, a)
    if best is None: return None, text
    return best[0], _cut(re.escape(best[1]), text)


def _plural(n: int, one: str, many: str | None = None) -> str:
    return one if n == 1 else (many or one + "s")


class Commands:
    def __init__(self, hub):
        self.hub = hub

    # ---- what the panel calls ----
    async def say(self, text: str, room_id: str | None = None) -> dict:
        """One sentence in, one answer out: {"kind": "done" | "answer" | "explain" | "action" | "rule", ...}.
        done and answer come from the grammar and have already happened; action and rule are the assistant's
        proposals and have not. Raises NotUnderstood with words for the person."""
        said = " ".join((text or "").split())
        if len(said) < 2: raise NotUnderstood("Say what you'd like the house to do.")
        here = self.hub.home.rooms.get(room_id) if room_id and room_id != "unassigned" else None
        try:
            out = await self._grammar(said, here)
            if out is None: out = await self._assistant(said, here)
        except Exception as e:
            self._log(said, here, {"understood": False, "reason": str(e)})
            raise
        self._log(said, here, {"understood": out["kind"] in ("done", "answer", "explain"), "kind": out["kind"], "text": out.get("text") or out.get("name") or out.get("answer")})
        return {**out, "said": said}

    def _log(self, said, here, detail):
        self.hub.log.add("said", here.id if here else "home", None, said, source="user", detail=detail)

    async def _assistant(self, said, here) -> dict:
        a = self.hub.assistant
        if not a.status()["configured"]:
            raise NotUnderstood("The house didn't catch that. Try \"kitchen lights off\", \"movie in the den\" or \"is the front door locked?\". "
                                "Connect the assistant under Routines to ask in your own words.")
        if re.match(r"^(why|what|how|when|who|where|which|did|does|do|is|are|was|were|has|have|can|should)\b", _tidy(said)):
            room, _ = find_room(_tidy(said), self.hub.home.rooms)
            out = await a.explain(room.id if room else here.id if here else "home", said)
            return {"kind": "explain", **out}
        return await a.draft(said)

    # ---- the grammar ----
    async def _grammar(self, said: str, here):
        t = _tidy(said)
        if not t: raise NotUnderstood("Say what you'd like the house to do.")
        home = self.hub.home
        # whole-house phrases first
        if re.fullmatch(r"(good ?night|bed ?time|night night|everyone to bed|time for bed|(i'?m |we'?re )?(going|off) to bed)", t):
            return await self._home(RoomState.asleep, said)
        if re.fullmatch(r"((turn |switch |shut )?(everything|it all|all|the house) (off|down)|all off|(i'?m |we'?re )?(leaving|heading out|going out|off out|out of here)|goodbye|bye)( now)?", t):
            return await self._home(RoomState.away, said)
        if re.fullmatch(r"(lock|secure) (the |all the |all |every )?(doors?|locks?|house|up)( please)?", t):
            return await self._all_locks("lock", said)
        if re.fullmatch(r"unlock (the |all the |all )?(doors?|locks?|house)", t):
            return await self._all_locks("unlock", said)
        # where: a named room, "everywhere", or the room the panel is showing
        everywhere = re.search(EVERYWHERE, t) is not None
        if everywhere: t = re.sub(r"\s+", " ", re.sub(EVERYWHERE, " ", t)).strip()
        placed = [d for r in home.rooms.values() if r.id != "unassigned" for d in r.devices]
        question = re.match(r"^(is|are|what|who|how|why|when|which|does|do|did)\b", t) is not None
        named, phrase = (None, "") if question or self._sound_in(t) else self._by_name(t, placed)
        room, cut = find_room(t, home.rooms)
        # a thing named in full beats a room hiding inside its name: "garage door" is the door, not the Garage
        if named and (room is None or len(phrase) >= len(t) - len(cut) - 4):
            room, t = home.rooms.get(named.room_id), _cut(re.escape(phrase), t)
            return await self._device([named], t, named.capability.split(".")[0], None, said, room, False)
        t = cut
        if room is None and not everywhere: room = here
        scope = [room] if room else [r for r in home.rooms.values() if r.id != "unassigned"]
        devices = [d for r in scope for d in r.devices]
        # questions
        if question: return await self._question(t, said, room, scope, devices, everywhere)
        # a sound on a speaker
        out = await self._sound(t, said, room, scope, devices)
        if out: return out
        # a scene for a room, or the house
        for pat, state in SCENES:
            if re.fullmatch(rf"(set |put |make |start |go |it'?s |time for )?(the |a |to )?({pat})( mode| time| in here| here| now)?( please)?", t):
                if room: return await self._room(room, state, said)
                if state is RoomState.asleep: return await self._home(RoomState.asleep, said)
                raise NotUnderstood(f"{LABEL[state.value]} for which room? Say the room's name.")
        # a room and a plain on/off: "kitchen off" is the All off scene; "kitchen on" is its lights
        if room and re.fullmatch(r"((turn |switch |shut |put )?(it |everything |all |things )?(off|out|down)|all off|everything off|off please|quiet)", t):
            return await self._room(room, RoomState.empty, said)
        if room and re.fullmatch(r"((turn |switch |put )?(it |everything |all )?(on|up)|on please|wake up|come on)", t):
            lights = [d for d in room.devices if d.capability == "light"]
            if lights: return await self._do(lights, "on", {}, said, f"{room.name} {_plural(len(lights), 'light')} on.")
        # a room and a bare verb: the kind is in the verb
        if room:
            for pat, kind in ((r"(open|close|shut|raise|lower)( up| it| them| the blinds)?", "cover"), (r"(lock|unlock)( it| them| up)?", "lock"),
                              (r"(make( it)? |a bit |a little |turn( it)? |it'?s )?(warmer|cooler|hotter|colder|too (hot|cold|warm|chilly)|up a bit|down a bit)( in here)?", "climate")):
                if re.fullmatch(pat, t):
                    found = [d for d in room.devices if d.capability == kind]
                    if not found: raise NotUnderstood(f"There is no {dict(cover='blind or door', lock='lock', climate='thermostat')[kind]} in the {room.name}.")
                    return await self._device(found, t, kind, None, said, room, False)
        # a thing, or a kind of thing, and what to do with it
        target, rest, kind, flavour = self._target(t, devices, room)
        if target is not None:
            return await self._device(target, rest, kind, flavour, said, room, everywhere or (room is None and len(scope) > 1))
        if room and not t:
            raise NotUnderstood(f"What should the {room.name} do? Try \"{room.name} lights off\" or \"movie in the {room.name}\".")
        return None

    # ---- scenes ----
    async def _room(self, room, state, said):
        await self.hub.set_intent(room, state, source="user", detail={"said": said})
        return {"kind": "done", "text": f"{room.name} · {LABEL[state.value]}", "room": room.id, "intent": state.value}

    async def _home(self, state, said):
        await self.hub.set_home_intent(state, source="user", detail={"said": said})
        return {"kind": "done", "text": "Good night. The house is off." if state is RoomState.asleep else "Everything is off.", "room": "home", "intent": state.value}

    async def _all_locks(self, action, said):
        locks = [d for d in self.hub.home.devices.values() if d.capability == "lock" and d.room_id != "unassigned"]
        if not locks: raise NotUnderstood("There is no lock in the house yet.")
        return await self._do(locks, action, {}, said, f"{_plural(len(locks), 'Door', 'All doors')} {action}ed.".replace("unlockeded", "unlocked").replace("lockeded", "locked"))

    # ---- devices ----
    def _by_name(self, t: str, devices: list):
        """The device whose name (or its name without its room's) is in the sentence, longest first. (device, the words matched)."""
        best = None
        for d in devices:
            if d.room_id == "unassigned": continue
            names = [norm(d.name)]
            r = self.hub.home.rooms.get(d.room_id)
            if r:
                for rn in room_names(r):
                    if names[0].startswith(rn + " "): names.append(names[0][len(rn) + 1:])
            for n in names:
                if n and len(n) > 1 and _has(re.escape(n), t) and (best is None or len(n) > len(best[1])): best = (d, n)
        return best if best else (None, "")

    def _target(self, t: str, devices: list, room):
        """A device by name, else a kind of thing by its word. (devices, the rest of the sentence, kind, flavour)."""
        d, n = self._by_name(t, devices)
        if d: return [d], _cut(re.escape(n), t), d.capability.split(".")[0], None
        for pat, kind, flavour in KINDS:
            m = re.search(rf"(?<![\w'])(?:{pat})(?![\w'])", t)
            if not m: continue
            found = [d for d in devices if d.capability.split(".")[0] == kind and d.room_id != "unassigned"]
            if flavour == "tv": found = [d for d in found if TV.search(d.name)] or found
            elif flavour == "speaker": found = [d for d in found if not TV.search(d.name)] or found
            if not found:
                where = f" in the {room.name}" if room else ""
                raise NotUnderstood(f"There is no {m.group(0).rstrip('s') if kind != 'media' else 'screen or speaker'}{where}.")
            return found, _cut(re.escape(m.group(0)), t), kind, flavour
        return None, t, None, None

    async def _device(self, targets, rest, kind, flavour, said, room, spread):
        """What to do with the thing named. `rest` is the sentence with the thing taken out."""
        first = targets[0]
        who = self._who(targets, kind, room, spread)
        if kind in ("light", "switch", "fan", "media", "climate"):
            pct = re.search(r"(\d+)\s*(%|percent)", rest)
            if kind == "light":
                if pct: return await self._do(targets, "on", {"brightness_pct": max(1, min(100, int(pct.group(1))))}, said, f"{who} to {pct.group(1)}%.")
                if _has("dim|dimmer|lower|low|soft|softer|down", rest): return await self._do(targets, "on", {"brightness_pct": 30}, said, f"{who} dimmed.")
                if _has("bright|brighter|brighten|full|up|max|all the way", rest): return await self._do(targets, "on", {"brightness_pct": 100}, said, f"{who} up bright.")
            if kind == "media":
                if _has("pause|stop|hold", rest): return await self._do(targets, "pause", {}, said, f"{who} paused.")
                if _has("play|resume|continue|unpause|start", rest) and not _has("off", rest): return await self._do(targets, "play", {}, said, f"{who} playing.")
                if _has("next|skip", rest): return await self._do(targets, "next", {}, said, "Next track.")
                if _has("previous|back|last track|again", rest): return await self._do(targets, "previous", {}, said, "Previous track.")
                if _has("mute|silence|silent", rest): return await self._do(targets, "volume", {"volume_level": 0.0}, said, f"{who} muted.")
                if pct or _has("volume|louder|quieter|softer|turn (it )?up|turn (it )?down|up|down", rest):
                    if pct: level = int(pct.group(1)) / 100
                    else:
                        now = float(first.attrs.get("volume_level") or 0.3)
                        level = now + (0.1 if _has("up|louder|more", rest) else -0.1)
                    level = max(0.0, min(1.0, round(level, 2)))
                    return await self._do(targets, "volume", {"volume_level": level}, said, f"{who} volume {int(level * 100)}%.")
            if kind == "climate":
                n = _number(re.sub(r"\bac\b|a/c", "", rest))
                if n is not None and 40 <= n <= 95 or (n is not None and 5 <= n <= 35):
                    return await self._do(targets, "set", {"temperature": n}, said, f"{who} set to {n:g}°.")
                if _has("warmer|hotter|up|higher|more heat|too cold|too chilly", rest) or _has("cooler|colder|down|lower|too hot|too warm", rest):
                    cur = first.attrs.get("temperature")
                    if cur is None: raise NotUnderstood(f"{first.name} has no set temperature to move from.")
                    want = float(cur) + (2 if _has("warmer|hotter|up|higher|more heat|too cold|too chilly", rest) else -2)
                    return await self._do(targets, "set", {"temperature": want}, said, f"{who} set to {want:g}°.")
                for mode in ("heat", "cool", "auto", "off"):
                    if re.fullmatch(rf"(set |switch |put )?(to |on )?{mode}( mode)?", rest) and mode in (first.attrs.get("hvac_modes") or [mode]):
                        if mode == "off": return await self._do(targets, "off", {}, said, f"{who} off.")
                        return await self._do(targets, "mode", {"hvac_mode": mode}, said, f"{who} set to {mode}.")
            if _has("off|out|kill|down|shut", rest) and not _has("on", rest): return await self._do(targets, "off", {}, said, f"{who} off.")
            if _has("on|up|start|wake", rest) or rest == "": return await self._do(targets, "on", {}, said, f"{who} on.")
        if kind == "lock":
            if _has("unlock|unlocked|open", rest): return await self._do(targets, "unlock", {}, said, f"{who} unlocked.")
            if _has("lock|locked|close|shut|secure", rest) or rest == "": return await self._do(targets, "lock", {}, said, f"{who} locked.")
        if kind == "cover":
            if _has("open|raise|up|lift", rest): return await self._do(targets, "open", {}, said, f"{who} opening.")
            if _has("close|shut|lower|down|drop", rest): return await self._do(targets, "close", {}, said, f"{who} closing.")
        raise NotUnderstood(f"What should {who[0].lower() + who[1:]} do? Try \"{first.name} off\".")

    def _who(self, targets, kind, room, spread) -> str:
        if len(targets) == 1:
            d = targets[0]
            r = self.hub.home.rooms.get(d.room_id)
            return d.name if not r or norm(d.name).startswith(norm(r.name)) or not spread else f"{r.name} {d.name[0].lower() + d.name[1:]}"
        noun = {"light": "light", "switch": "plug", "fan": "fan", "media": "screen", "climate": "thermostat", "lock": "door", "cover": "blind"}.get(kind, "thing")
        if room: return f"{room.name} {_plural(len(targets), noun)}"
        return f"All {len(targets)} {_plural(len(targets), noun)}"

    async def _do(self, targets, action, data, said, text):
        failed = []
        for d in targets:
            try: await self.hub.act(d, action, data, source="user", said=said)
            except Exception: failed.append(d.name)
        if failed and len(failed) == len(targets):
            raise NotUnderstood(f"{failed[0]} didn't respond." if len(failed) == 1 else "None of them responded.")
        if failed: text = f"{text[:-1]}; {', '.join(failed)} didn't respond."
        return {"kind": "done", "text": text, "devices": [d.id for d in targets], "action": action, "count": len(targets) - len(failed)}

    # ---- sounds on a speaker ----
    def _sound_in(self, t) -> bool:
        return _has("noise", t) or any(_has(re.escape(n), t) for s in self.hub.sounds.catalog() for n in (norm(s["name"]), norm(s["id"].replace("-", " "))) if n)

    async def _sound(self, t, said, room, scope, devices):
        catalog = self.hub.sounds.catalog()
        if re.fullmatch(r"((stop|turn off|switch off|kill|end|no more) (the |that )?(sound|noise|rain|music|it)|sound off|noise off|(quiet|silence|shh+)( please)?)", t):
            playing = [d for d in devices if d.id in self.hub.sounds.sessions]
            if not playing: raise NotUnderstood("Nothing is playing from the hub right now.")
            for d in playing: await self.hub.act(d, "sound_off", {}, source="user", said=said)
            return {"kind": "done", "text": f"{_plural(len(playing), 'Sound', 'Sounds')} off.", "devices": [d.id for d in playing], "action": "sound_off", "count": len(playing)}
        minutes, t2 = _minutes(t)
        best = None
        for s in catalog:
            for n in {norm(s["name"]), norm(s["id"].replace("-", " "))}:
                if n and _has(re.escape(n), t2) and (best is None or len(n) > len(best[1])): best = (s, n)
        if best is None and _has("noise", t2):
            white = next((s for s in catalog if s["id"] in ("white", "white-noise")), None)
            if white: best = (white, "noise")
        if best is None: return None
        sound, word = best
        rest = _cut(re.escape(word), t2)
        rest = re.sub(r"^(play|put on|put|start|turn on|some|a bit of|a little|the|on)\b\s*", "", rest).strip()
        speakers = [d for d in devices if d.capability == "media" and not TV.search(d.name)] or [d for d in devices if d.capability == "media"]
        named = [d for d in speakers if _has(re.escape(norm(d.name)), rest)]
        if named: speakers = named
        if not speakers: raise NotUnderstood(f"There is no speaker{f' in the {room.name}' if room else ' in the house yet'}.")
        if len(speakers) > 1 and not room:
            raise NotUnderstood(f"Which speaker? Say the room: \"{sound['name'].lower()} in the {self.hub.home.rooms[speakers[0].room_id].name}\".")
        dev = speakers[0]
        await self.hub.act(dev, "sound", {"sound": sound["id"], **({"minutes": minutes} if minutes else {})}, source="user", said=said)
        r = self.hub.home.rooms.get(dev.room_id)
        where = f" in the {r.name}" if r else ""
        for_ = f" for {minutes} minutes" if minutes and minutes < 60 else (f" for {minutes // 60} hour{'s' if minutes >= 120 else ''}" if minutes else "")
        return {"kind": "done", "text": f"{sound['name']}{where}{for_}.", "devices": [dev.id], "action": "sound", "count": 1}

    # ---- questions answered from what the house knows right now ----
    async def _question(self, t, said, room, scope, devices, everywhere):
        p = self.hub.presence
        m = re.fullmatch(r"(is|are) (anyone|anybody|someone|somebody|everyone|everybody|nobody) (home|in|here|out|away|around)\??", t) or re.fullmatch(r"(who'?s|who is|whos) (home|in|here|out|away|around)\??", t)
        if m:
            if p.somebody is None: return {"kind": "answer", "text": "The house can't tell who is home yet."}
            names = [x["name"] for x in p.as_dict().get("people", []) if x.get("home")]
            if names: return {"kind": "answer", "text": f"{' and '.join(names)} {'is' if len(names) == 1 else 'are'} home."}
            return {"kind": "answer", "text": "Someone is home." if p.somebody else "Nobody is home."}
        if re.fullmatch(r"(what'?s|what is|whats|how (warm|cold|hot)( is)?|how is) (it |the temperature |the temp |temperature )?(like )?(outside|out|outdoors)\??", t):
            w = self.hub.weather
            if not w or w.get("temperature") is None: return {"kind": "answer", "text": "The house has no weather yet. Set its location on Home."}
            return {"kind": "answer", "text": f"{round(w['temperature'])}{(w.get('unit') or '°')[:1]} and {str(w.get('condition') or '').replace('-', ' ')} outside."}
        if re.fullmatch(r"(what'?s|what is|whats|how (warm|cold|hot)) (is )?(it |the temperature|the temp|temperature)( in here| here)?\??", t) or re.fullmatch(r"(what'?s|what is) (the )?(temperature|temp)\??", t):
            reads = [d for d in devices if d.capability == "sensor.temperature" and _num(d.state) is not None]
            if not reads:
                reads = [d for d in devices if d.capability == "climate" and _num(d.attrs.get("current_temperature")) is not None]
                vals = [(d, _num(d.attrs.get("current_temperature"))) for d in reads]
            else: vals = [(d, _num(d.state)) for d in reads]
            if not vals: raise NotUnderstood(f"Nothing in the {room.name} reads a temperature." if room else "Nothing in the house reads a temperature.")
            if len(vals) == 1 or room:
                d, v = vals[0]; r = self.hub.home.rooms.get(d.room_id)
                return {"kind": "answer", "text": f"{round(v)}° in the {r.name if r else 'house'}."}
            return {"kind": "answer", "text": ", ".join(f"{self.hub.home.rooms[d.room_id].name} {round(v)}°" for d, v in vals if d.room_id in self.hub.home.rooms) + "."}
        m = re.fullmatch(r"(what'?s|what is|whats) (still )?(on|playing|open|unlocked)( in here| here| at the moment)?\??", t)
        if m:
            want = m.group(3)
            active = {"on": ("on", "playing"), "playing": ("playing",), "open": ("open",), "unlocked": ("unlocked",)}[want]
            hits = [d for d in devices if d.state in active and d.capability.split(".")[0] not in ("camera", "motion", "contact", "sensor")]
            if want == "open": hits += [d for d in devices if d.capability == "contact" and d.state == "on"]
            if not hits: return {"kind": "answer", "text": f"Nothing is {want}{f' in the {room.name}' if room else ''}."}
            return {"kind": "answer", "text": ", ".join(self._named(d, room) for d in hits[:6]) + (f" and {len(hits) - 6} more" if len(hits) > 6 else "") + "."}
        m = room and re.fullmatch(r"(is|are) (it |everything |anything )?(open|opened|closed|shut|locked|unlocked|on|off)\??", t)
        if m:
            want = m.group(3)
            kinds = ("cover", "contact") if want in ("open", "opened", "closed", "shut") else ("lock",) if want in ("locked", "unlocked") else ("light",)
            found = [d for d in room.devices if d.capability in kinds]
            if not found: raise NotUnderstood(f"Nothing in the {room.name} can be {want}.")
            return {"kind": "answer", "text": self._state_line(found, found[0].capability, room)}
        m = re.fullmatch(r"(is|are) (the |my |our )?(.+?) (on|off|open|opened|closed|shut|locked|unlocked|playing|paused|running|still on|still open)\??", t)
        if m:
            target, _, kind, _ = self._target(m.group(3), devices, room)
            if target is None: raise NotUnderstood(f"The house has nothing called \"{m.group(3)}\"{f' in the {room.name}' if room else ''}.")
            return {"kind": "answer", "text": self._state_line(target, kind, room)}
        m = re.fullmatch(r"(is|are) (the |my |our )?(.+?)\??", t)
        if m and not t.startswith(("is it", "is there", "is anything")):
            target, _, kind, _ = self._target(m.group(3), devices, room)
            if target is not None: return {"kind": "answer", "text": self._state_line(target, kind, room)}
        if t.startswith("why"): return None       # the assistant explains from the log
        return None

    def _named(self, d, room) -> str:
        r = self.hub.home.rooms.get(d.room_id)
        if room or not r or norm(d.name).startswith(norm(r.name)): return d.name
        return f"{r.name} {d.name[0].lower() + d.name[1:]}"

    def _state_line(self, targets, kind, room) -> str:
        def word(d):
            s = d.state
            if s in ("unavailable", "unknown"): return "not responding"
            if d.capability == "contact": return "open" if s == "on" else "closed"
            if d.capability == "motion": return "seeing motion" if s == "on" else "seeing no motion"
            return s.replace("_", " ")
        if len(targets) == 1:
            d = targets[0]
            return f"{d.name} is {word(d)}."
        states = {}
        for d in targets: states.setdefault(word(d), []).append(d)
        noun = {"light": "light", "switch": "plug", "fan": "fan", "media": "screen", "lock": "door", "cover": "blind", "climate": "thermostat"}.get(kind, "thing")
        if len(states) == 1: return f"All {len(targets)} {_plural(len(targets), noun)} are {next(iter(states))}."
        return ". ".join(f"{', '.join(self._named(d, room) for d in ds)} {'is' if len(ds) == 1 else 'are'} {s}" for s, ds in states.items()) + "."


def _num(v):
    try: return float(v)
    except (TypeError, ValueError): return None
