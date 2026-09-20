# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What happened while nobody was watching.

The one idea, and everything here follows from it: **a finding is a span, not an event.** "The porch
light has been on for ten hours" is the news. "The porch light turned on at 7:32am" is a row in a log
nobody reads, and it is the only thing the panel could say before this file existed -- the log holds
transitions, and the interesting fact is the distance between two of them, which may be ten hours and
forty rows apart. A timeline cannot show that by construction: you get "turned on, 7:32am" and there
is simply no row for the ten hours that followed.

Ranked the way health.py ranks, and for the same reason. What is STILL true leads and carries the
only buttons on the page, because it is the only part anybody can do anything about. What is OVER
reads quietly under it with no buttons at all: a door that locked itself at 6:40am is not a job, and
offering an act against it would be offering to do something that has already happened.

Two rules carried in from elsewhere, both load-bearing:

- **The brain writes the words, including the headings.** "Still on" is right over two lights and
  wrong over a door that is still unlocked, so this file names the group from what is actually in it
  and the panel draws whatever it is handed. Same reason every word of a health line lives in
  health.py: the panel does not know what it is looking at, so it decides nothing.
- **Nothing is claimed that cannot be known.** A house with no people set up has no idea when anybody
  left, so it does not guess a window -- it says what it has been doing since yesterday and means it.
"""
import json, time
from datetime import datetime

from .health import when
from .model import kind_of

DAY = 86400
# How long a thing has to have been that way before it is worth a line. A light somebody turned on
# twenty minutes ago is not news; one that has been on since breakfast is. Locks and open doors get a
# shorter fuse because the cost of one being wrong is not the electricity.
LONG = {"light": 4 * 3600, "switch": 4 * 3600, "fan": 4 * 3600, "cover": 4 * 3600,
        "lock": 3600, "contact": 3600}
# Which state each sort of thing is "left that way" in, and the words for it.
LEFT = {"light": ("on", "on"), "switch": ("on", "on"), "fan": ("on", "on"),
        "cover": ("open", "open"), "lock": ("unlocked", "unlocked"), "contact": ("on", "open")}
# The heading each sort of thing wants when it is still that way. Several sorts in one group are
# joined ("Still on, and still unlocked"), which is why these are fragments rather than sentences.
HEADING = {"on": "still on", "open": "still open", "unlocked": "still unlocked"}
NIGHT = (23, 6)          # a span touching this is "overnight", which is the whole point of the lock line
PHONE_DAYS = 14          # how far back People and phones reaches


def lasted(seconds: float) -> str:
    """'7 hours', '25 minutes'. Never '7.3 hours', and never a number somebody has to convert."""
    m = int(round(seconds / 60))
    if m < 60: return f"{m} minutes" if m != 1 else "a minute"
    h = int(round(seconds / 3600))
    if h < 24: return f"{h} hours" if h != 1 else "an hour"
    d = int(round(seconds / DAY))
    return f"{d} days" if d != 1 else "a day"


def spans(rows_desc: list, state_now, since: float, until: float, values) -> list:
    """Every interval in [since, until) where the thing was in one of `values`, newest first.

    `rows_desc` are that subject's state changes inside the window, newest first; each says what it
    BECAME (`new`) and what it was before (`old`). Walking backwards from `until` needs no extra
    query for the state the window opened in: the oldest row in it already carries that in `old`.
    """
    out, end, state = [], until, state_now
    for r in rows_desc:
        if r["ts"] >= end:  continue                 # same second, or out of order: it cannot bound a span
        if r["new"] in values: out.append((r["ts"], end))
        end, state = r["ts"], r["old"]
    if state in values and end > since: out.append((since, end))
    return out


def overnight(a: float, b: float, tz) -> bool:
    """Did this span run through the small hours? An hour of it is enough; the phrase is the news."""
    lo, hi = NIGHT
    t = a
    while t < b:
        h = datetime.fromtimestamp(t, tz).hour
        if h >= lo or h < hi: return True
        t += 3600
    return False


class Happened:
    def __init__(self, hub): self.hub = hub

    # ---- the window ----
    def away(self, now=None) -> dict:
        """When the house was last empty: {"from", "to"}, `to` None while it still is. Empty when unknown.

        Read from the presence rows rather than Presence.since, because Presence only remembers the
        CURRENT answer: once somebody is home again, the moment they left is only in the log.
        """
        now = now or time.time()
        rows = self.hub.log.recent(40, subject="home", kinds=("presence",), since=now - 7 * DAY)
        left = to = None
        for r in rows:                                  # newest first
            if r["new"] == "nobody": left = r["ts"]; break
            if r["new"] == "somebody" and to is None: to = r["ts"]
        if left is None: return {}
        return {"from": left, "to": to}

    def window(self, now=None) -> tuple:
        """(since, lede). The span the page covers, and the sentence that opens it."""
        now = now or time.time()
        tz, a = self.hub.tz, self.away(now)
        if a and a.get("to"):
            return a["from"], (f"You were out from {when(a['from'], tz, now)} until {when(a['to'], tz, now)}.")
        if a:
            return a["from"], f"Nobody has been home since {when(a['from'], tz, now)}."
        # No people set up, or nobody has gone out in a week. Yesterday morning is not a guess about
        # the household -- it is this page saying exactly how far back it looked.
        return now - 36 * 3600, "Here is what the house has been doing since yesterday."

    # ---- the findings ----
    def _watched(self) -> list:
        """The things whose being left on is worth a sentence, with the kind word for each."""
        out = []
        for d in self.hub.home.devices.values():
            if d.room_id == "unassigned": continue
            kind = kind_of(d).split(".")[0]
            if kind in LEFT: out.append((d, kind))
        return out

    def _rows(self, since, until) -> dict:
        """Every state change in the window, by subject, newest first. One query, not one per device."""
        by = {}
        for r in self.hub.log.recent(20000, kinds=("state",), since=since, until=until):
            by.setdefault(r["subject"], []).append(r)
        return by

    def findings(self, now=None) -> tuple:
        """(still, over). Everything long enough to say, ranked by how long it has been that way."""
        now = now or time.time()
        since, _ = self.window(now)
        rows, tz = self._rows(since, now), self.hub.tz
        still, over = [], []
        for d, kind in self._watched():
            value, word = LEFT[kind]
            long_enough = LONG[kind]
            for a, b in spans(rows.get(d.id, []), d.state, since, now, (value,)):
                if b - a < long_enough: continue
                if b >= now: still.append(self._still(d, kind, word, a, now))
                else:        over.append(self._over(d, kind, word, a, b, tz, now))
        still.sort(key=lambda i: -i["seconds"])
        over.sort(key=lambda i: -i["ts"])
        return still, over

    def _still(self, d, kind, word, a, now) -> dict:
        return {"kind": "still", "subject": d.id, "seconds": now - a, "ts": a,
                "text": f"{d.name} has been {word} for {lasted(now - a)}, since {when(a, self.hub.tz, now)}.",
                "where": self.hub.health.where(d), "word": word, "when": "now",
                "acts": self._acts(d, kind)}

    def _over(self, d, kind, word, a, b, tz, now) -> dict:
        night = " overnight" if overnight(a, b, tz) else ""
        back = {"light": "off", "switch": "off", "fan": "off", "cover": "closed",
                "lock": "locked", "contact": "closed"}[kind]
        return {"kind": "over", "subject": d.id, "seconds": b - a, "ts": b,
                "text": (f"{d.name} was {word} for {lasted(b - a)}{night}, "
                         f"{when(a, tz, now)} to {when(b, tz, now)}. It is {back} now."),
                "where": self.hub.health.where(d), "word": word, "when": when(b, tz, now), "acts": []}

    def _acts(self, d, kind) -> list:
        """What can actually be done about it from here, and nothing that cannot.

        A contact sensor is the honest case: nothing closes a door over the network, so the act is to
        show somebody the room and let them go and shut it. Offering "Close" on a thing that cannot
        close is worse than offering nothing.
        """
        if kind in ("light", "switch", "fan"): return [{"do": "Turn off", "act": "device", "to": d.id, "arg": "off"}]
        if kind == "lock":  return [{"do": "Lock it", "act": "device", "to": d.id, "arg": "lock"}]
        if kind == "cover": return [{"do": "Close it", "act": "device", "to": d.id, "arg": "close"}]
        room = self.hub.home.rooms.get(d.room_id)
        return [{"do": "Show me", "act": "room", "to": room.id}] if room else []

    def heading(self, still: list) -> str:
        """The group's name, from what is in it. 'Still on' over an unlocked door would be a lie the
        panel could not know it was telling, which is why this is here and not there."""
        seen = []
        for i in still:
            h = HEADING.get(i["word"], "still on")
            if h not in seen: seen.append(h)
        if not seen: return ""
        line = seen[0] if len(seen) == 1 else ", and ".join((", ".join(seen[:-1]), seen[-1]))
        return line[0].upper() + line[1:]

    # ---- the people ----
    def people(self, now=None) -> list:
        """Phones that arrived or left. Who is in the house is a change to it, so it is on this page."""
        now = now or time.time()
        out = []
        for r in self.hub.log.recent(50, kinds=("phone",), since=now - PHONE_DAYS * DAY):
            name = "A phone"
            if r.get("detail"):
                try: name = json.loads(r["detail"]).get("name") or name
                except Exception: pass
            text = {"joined": f"{name} joined the house.", "removed": f"{name} was removed.",
                    "left": f"{name}'s stay ended on its own.", "asked": f"{name} asked to join."}.get(r["new"])
            if not text: continue
            out.append({"kind": "phone", "subject": r["subject"], "text": text,
                        "when": when(r["ts"], self.hub.tz, now), "ts": r["ts"], "acts": []})
        return out

    # ---- the page ----
    def page(self, now=None) -> dict:
        now = now or time.time()
        since, lede = self.window(now)
        still, over = self.findings(now)
        groups = []
        if still: groups.append({"id": "still", "label": self.heading(still), "items": still})
        if over:  groups.append({"id": "over", "label": "While you were out", "items": over})
        people = self.people(now)
        if people: groups.append({"id": "people", "label": "People and phones", "items": people})
        return {"lede": lede, "since": since, "away": self.away(now), "groups": groups,
                "empty": not groups, "hint": self.hint(still, over)}

    def hint(self, still, over) -> str:
        """The one line under the door, which is what makes somebody open it. Written here for the
        reason the heading is: it has to say what is actually inside."""
        def n(items, thing): return f"1 {thing}" if len(items) == 1 else f"{len(items)} {thing}s"
        if still: return f"{n(still, 'thing')} still {still[0]['word']}"
        if over: return f"{n(over, 'thing')} while you were out"
        return "Nothing to catch up on"


# ---- who changed what ----
# The kinds that are a change to the HOUSE rather than a use of it. Deliberately the same shape as
# lock.needs_code(): if a route needed the code to do it, the record of it having been done belongs
# here. Turning a light on is not on this list, which is also what keeps the page short enough to read.
AUDIT = ("home", "phone", "share", "bridge", "draft")


class Changes:
    """The audit trail, in sentences. Every word of it written here rather than in the panel, for the
    reason every health line is: the panel does not know what it is looking at."""

    def __init__(self, hub): self.hub = hub

    def name_of(self, subject: str, detail: dict) -> str:
        """What a subject is called, preferring what it is called NOW and falling back to what it was
        called when it happened -- a thing removed from the house is exactly what an audit asks about."""
        d = self.hub.home.devices.get(subject)
        if d: return d.name
        room = self.hub.home.rooms.get(subject)
        if room: return room.name
        return detail.get("name") or subject

    def sentence(self, r: dict) -> str | None:
        """One row as a sentence, without its who. None for rows not worth a line."""
        kind, subject, new, old = r["kind"], r["subject"], r["new"] or "", r["old"]
        try: detail = json.loads(r["detail"]) if r["detail"] else {}
        except Exception: detail = {}
        if kind == "phone":
            name = detail.get("name") or "a phone"
            span = {"day": " for the day", "weekend": " for the weekend"}.get(detail.get("span"), "")
            return {"joined": f"let {name} into the house{span or ', for good'}.",
                    "removed": f"removed {name} from the house.",
                    "asked": f"asked to join the house, as {name}.",
                    "left": f"{name}'s stay ended on its own.",
                    "home only": f"stopped {name} reaching the house from outside.",
                    }.get(new) or f"changed {name}: {new}."
        if kind == "draft":
            return {"approved": "approved a suggested routine.", "discarded": "turned down a suggested routine.",
                    "proposed": None}.get(new)
        if kind == "bridge": return f"set up a bridge ({subject})." if new == "set up" else f"{new} a bridge ({subject})."
        if kind == "share":
            if subject == "settings": return f"turned sharing with other apps {new}."
            if subject == "device": return f"{'shared' if new == 'shared' else 'stopped sharing'} {self.name_of(subject, detail)}."
            return "opened the window for another app to find the house."
        # kind == "home": the subject says which sort of change it was
        if subject == "room": return f"added the room {new}."
        if subject == "location": return f"set where home is to {new}."
        if subject == "entry": return "changed which rooms the family comes in through."
        if subject == "backup": return "took a backup of the house."
        if subject == "restore": return "asked to restore the house from a backup."
        if subject == "restart": return "asked the house to restart." if new == "asked" else None
        if subject == "registry": return None                       # the house tidying itself up
        if subject == "assistant": return "connected the assistant."
        if subject == "credentials": return f"added a key for {new}."
        if subject == "device": return f"added {new} to the house."
        if subject == "driver": return f"{new}."
        if subject == "setup":
            return {"code set": "set the code on the settings.", "code removed": "took the code off the settings.",
                    "owner created": "set the house up.", "finished": "finished setting the house up."}.get(new)
        if subject == "update":
            if new == "installed": return f"installed {old or 'an update'}."
            if new and new.startswith("automatic"): return f"turned {new.split()[-1]} automatic updates."
            return f"asked the house to update to {new}."
        if new == "account removed":
            return f"removed the {detail.get('name') or detail.get('integration') or 'account'}. Everything it brought went with it."
        # a device id, with the detail saying which sort of change
        name = self.name_of(subject, detail)
        if detail.get("moved"):
            room = self.hub.home.rooms.get(new)
            return f"moved {name} to the {room.name}." if room else f"took {name} out of its room."
        if detail.get("renamed_unit") is not None or (old and new and not detail):
            return f"renamed {old} to {new}." if old else f"named it {new}."
        if new == "forgotten": return f"removed {name} from the house."
        if detail.get("shown_as"): return f"changed what {name} is treated as."
        if detail.get("leads"): return f"made {name} the one that leads its room."
        if detail.get("paired"): return f"paired {new} over {detail['paired']}."
        return None

    def coded_since(self) -> float | None:
        """When the code was set. Before it there were no phones to tell apart, so nothing before it
        can name anybody -- and the page says that rather than leaving a column mysteriously empty."""
        rows = self.hub.log.recent(20, subject="setup", kinds=("home",))
        setting = [r["ts"] for r in rows if r["new"] == "code set"]
        return max(setting) if setting and self.hub.lock.locked else None

    def rows(self, limit=200) -> list:
        out = []
        for r in self.hub.log.recent(limit * 3, kinds=AUDIT):
            text = self.sentence(r)
            if not text: continue
            # A person is named; the house acting on its own says so. Neither is ever a guess: `who`
            # is null unless a request carried a phone, and events.py only reads it for source="user".
            who = r["who"] or ("The hub" if r["source"] in ("hub", "system") else
                               "The assistant" if r["source"] == "assistant" else "Someone at the wall")
            out.append({"who": who, "text": text, "ts": r["ts"], "named": bool(r["who"]),
                        "when": when(r["ts"], self.hub.tz), "kind": r["kind"], "subject": r["subject"]})
            if len(out) >= limit: break
        return out

    def page(self, limit=200) -> dict:
        return {"rows": self.rows(limit), "coded_since": self.coded_since(),
                "coded_when": when(self.coded_since(), self.hub.tz) if self.coded_since() else None}
