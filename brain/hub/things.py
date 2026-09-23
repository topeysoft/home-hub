# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Everything this house has, and what brought each of it.

WHY THERE IS ONE LIST AT ALL. Getting rid of a thing used to mean knowing where it was kept: a
device behind a room's pencil, a puck under This hub, an account on Accounts, a light strip nowhere
whatsoever. Four vocabularies, none of them where a person looks, and three kinds of thing with no
way out (design/forget/Today.dc.html). This is the answer the household picked on 22 September --
one door holding all of it, with the row on a thing's own pane as the shortcut for the thing in
your hand.

AND IT IS GROUPED BY WHAT BROUGHT IT, which is not decoration. What brought a thing is exactly what
decides whether it may leave on its own: an account's integration is allowed to refuse, a puck
re-announces its switches whatever the registry says, and a strip has to be told to let go of us as
well. The panel could not draw that fact because nothing gave it to them. Here it IS the row --
"Goes with Ring", with the door to Ring on the group above -- so nothing has to be explained.

THE PANEL INVENTS NO WORDS HERE. Every line, including the words on the buttons and the question
asked before the irreversible one, is written in this file, the way health.py writes Needs a look.
A panel that composed these sentences would have to know which kinds can leave alone, and that is
the one thing only the brain knows.
"""
import logging, re

log = logging.getLogger("hub.things")

# The identifiers the two things of our own carry in Home Assistant's registry. A mesh switch's is
# written by the puck (brilliant/esp32-bridge/src/main.cpp announce()); a strip writes its own
# (strip/firmware/main/app_main.cpp announce_the_light()).
MESH_SWITCH = re.compile(r"^mesh_([0-9a-f]{16})_([0-9a-f]{4})$")
LIGHT_STRIP = re.compile(r"^strip_([0-9a-f]+)$")

# The brain set these up itself: they are the engine, not somebody's account, and a thing that came
# in through one of them was set up in this house rather than brought by a sign-in.
PLUMBING = {"mqtt", "zwave_js", "matter"}


def _identifiers(row: dict | None) -> list[str]:
    return [str(x) for ident in (row or {}).get("identifiers") or []
            for x in (ident if isinstance(ident, (list, tuple)) else [ident])]


def ours(row: dict | None) -> tuple[str, tuple] | None:
    """Whether this hardware is one of the two kinds we make, and which. None for everything else."""
    for name in _identifiers(row):
        if (m := MESH_SWITCH.match(name)): return "switch", m.groups()
        if (m := LIGHT_STRIP.match(name)): return "strip", m.groups()
    return None


def _unit(parts: list) -> tuple[str, str]:
    """One row for one physical thing, and the parts of it under its name.

    A Ring pathlight arrives as a light, a motion sensor and a brightness reading on one piece of
    hardware. Three rows for one object is how a list of what a house HAS turns into a list of what
    Home Assistant knows, which is the failure this whole page exists to avoid."""
    lead = parts[0]
    name = lead.hw_name or lead.name
    if len(parts) == 1: return name, ""
    short = []
    for p in parts:
        w = p.name
        if name and w.lower().startswith(name.lower()): w = w[len(name):].strip(" -–—")
        # A part called exactly what the whole thing is called IS the thing -- a fan whose light is
        # its only other part reads "its light", not "its bedroom fan · its light". Saying the
        # object's own name back as one of its parts is how a list of things becomes a list of rows.
        if w: short.append(f"its {w[:1].lower()}{w[1:]}")
    return name, " · ".join(short)


class Things:
    """Built fresh per request. It is a page somebody opens, not a thing that is watched."""

    def __init__(self, hub):
        self.hub = hub

    async def everything(self) -> dict:
        home = self.hub.home
        try: rows = list(await self.hub.ha.send("config/device_registry/list") or [])
        except Exception as e:
            log.info("things: could not read the house's devices (%s)", e); rows = []
        by_hw = {r.get("id"): r for r in rows}
        try: entries = list(await self.hub.ha.send("config_entries/get") or [])
        except Exception as e:
            log.info("things: could not read the accounts (%s)", e); entries = []
        titles = {e.get("entry_id"): (e.get("title") or e.get("domain")) for e in entries}
        domains = {e.get("entry_id"): e.get("domain") for e in entries}

        room_name = {r.id: r.name for r in home.rooms.values()}
        # One row per physical thing. A device with no hardware behind it stands for itself.
        units: dict = {}
        for d in home.devices.values():
            units.setdefault(d.hw or f"@{d.id}", []).append(d)

        accounts: dict = {}     # entry_id -> rows brought by a sign-in
        here: list = []         # set up in this house, and able to leave on its own
        meshes: dict = {}       # net -> switch rows
        strips: list = []
        for _key, parts in sorted(units.items(), key=lambda kv: (kv[1][0].hw_name or kv[1][0].name).lower()):
            lead = parts[0]
            name, sub = _unit(parts)
            where = room_name.get(lead.room_id) or "No room yet"
            mine = ours(by_hw.get(lead.hw or ""))
            if mine and mine[0] == "switch":
                net, addr = mine[1]
                meshes.setdefault(net, []).append(
                    {"id": lead.id, "name": name, "sub": sub, "where": where,
                     "out": self._take_out(lead.id, name, "a wall switch")})
                continue
            if mine and mine[0] == "strip":
                strips.append({"id": lead.id, "name": name, "sub": sub or "A light strip",
                               "where": where, "out": self._let_strip_go(mine[1][0], name)})
                continue
            entry = lead.entry
            if entry and domains.get(entry) not in PLUMBING and entry in titles:
                accounts.setdefault(entry, []).append(
                    {"id": lead.id, "name": name, "sub": sub, "where": where,
                     "out": None, "why": f"Goes with {titles[entry]}"})
            else:
                here.append({"id": lead.id, "name": name, "sub": sub, "where": where,
                             "out": self._take_out(lead.id, name, None)})

        groups = []
        for entry, things in sorted(accounts.items(), key=lambda kv: titles[kv[0]].lower()):
            title, n = titles[entry], len(things)
            groups.append({
                "id": entry, "kind": "account", "name": f"{title} · signed in", "things": things,
                "act": {"do": f"Remove {title}, and {self._with_it(n)}",
                        "act": "account", "to": entry,
                        "ask": f"Remove {title}? Everything it brought goes with it: "
                               f"{self._and(t['name'] for t in things)}.",
                        "yes": f"Yes, remove {title}", "no": "Keep it"}})
        if here or strips:
            groups.append({"id": "here", "kind": "here", "name": "Set up here", "act": None,
                           "things": sorted(here + strips, key=lambda t: t["name"].lower())})
        for net, things in sorted(meshes.items()):
            chip = self.hub.bridge.carrying(net)
            where = self.hub.bridge.where(chip) if chip else None
            n = len(things)
            groups.append({
                "id": f"mesh-{net}", "kind": "bridge", "things": things,
                "name": f"On the bridge in the {where.lower()}" if where and where != "A bridge"
                        else "On a bridge of this house",
                "act": None if not chip else {
                    "do": f"Forget the bridge, and {self._with_it(n)}",
                    "act": "bridge", "to": chip,
                    "ask": f"Forget {where.lower() if where else 'this bridge'}? Its switches stop "
                           f"working from here until a bridge is set up again.",
                    "yes": "Yes, forget it", "no": "Keep it"}})
        engine = [p for p in (self.hub.provision.summary() if self.hub.provision else [])
                  if p.get("state") == "ready"]
        if engine:
            groups.append({
                "id": "engine", "kind": "engine", "name": "The hub's own parts", "act": None,
                "things": [{"id": "engine", "name": self._and(p["name"] for p in engine),
                            "sub": "", "where": "In the hub", "out": None,
                            "why": "Part of the house"}]})
        return {"groups": groups, "count": sum(len(g["things"]) for g in groups if g["kind"] != "engine")}

    # ---- the words on the buttons, and the question before the one that cannot be taken back ----

    def _take_out(self, id_: str, name: str, what: str | None) -> dict:
        """An ordinary thing, and the one sentence somebody needs before it is gone.

        THERE IS NO UNDO ON THIS ONE. Everywhere else in the panel what you just touched keeps its
        place and IS the undo (AGENTS.md). Here it cannot be, so the whole of the care goes into
        asking first, with the name in the question rather than in a toast afterwards."""
        extra = (" The wall switch itself keeps working; it stops being something this house can "
                 "see or set." if what == "a wall switch" else
                 " Its schedules go with it. Plug it back in one day and the house meets it as "
                 "something new.")
        return {"do": "Take it out", "act": "forget", "to": id_,
                "ask": f"Take {name} out of the house?{extra}",
                "yes": f"Yes, take {name} out", "no": "Keep it"}

    def _let_strip_go(self, strip_id: str, name: str) -> dict:
        return {"do": "Take it out", "act": "strip", "to": strip_id,
                "ask": f"Take {name} out of the house? It is told to forget the house too, so it "
                       f"can be set up again — here, or in somebody else's.",
                "yes": f"Yes, take {name} out", "no": "Keep it"}

    @staticmethod
    def _with_it(n: int) -> str:
        """"and all four with it" reads; "and all one with it" does not, and a door's words are
        read far more often than they are written."""
        return "the one thing with it" if n == 1 else f"all {n} with it"

    @staticmethod
    def _and(names) -> str:
        n = list(names)
        if len(n) <= 1: return n[0] if n else "nothing"
        return f"{', '.join(n[:-1])} and {n[-1]}"
