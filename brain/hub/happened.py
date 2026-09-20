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


def plainly(subject: str) -> str:
    """`light.frontyard_light` -> `Frontyard light`. For a thing the house no longer has, where the id
    is all that is left of it and an id is the one thing the panel may never show."""
    tail = (subject or "").split(".", 1)[-1].replace("_", " ").strip()
    return (tail[:1].upper() + tail[1:]) if tail else (subject or "something")


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
                    "left": f"ended {name}'s stay, which was only ever for a while.", "asked": f"{name} asked to join."}.get(r["new"])
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
# What a device is treated as, in the words the panel uses for it rather than the engine's.
KIND_AS = {"light": "a light", "switch": "a plug", "fan": "a fan", "media": "a speaker", "cover": "a blind",
           "climate": "a thermostat", "lock": "a lock", "camera": "a camera", "vacuum": "a vacuum",
           "alarm": "an alarm", "appliance": "an appliance", "motion": "a motion sensor", "contact": "a door sensor"}


# Rows that are the house doing housekeeping to itself rather than anybody changing anything:
# re-reading Home Assistant's registry (36 of 134 rows in one real log), and a suggestion the
# assistant merely offered. Named here, as a list somebody wrote down, rather than falling out of
# `sentence()` having no words for them.
SKIP = {("home", "registry"), ("draft", "proposed")}


class Changes:
    """The audit trail, in sentences. Every word of it written here rather than in the panel, for the
    reason every health line is: the panel does not know what it is looking at.

    **Nothing is dropped except by name.** This started out dropping any row `sentence()` had no
    words for, which is the wrong default for an audit trail by some distance: a log that quietly
    omits is worse than no log, because what is missing from it cannot be noticed. Checked against a
    real house's log, that silent path was swallowing more than a quarter of the rows. So the only
    rows that do not appear are the ones in SKIP, and everything else the brain has no phrasing for
    yet gets an honest, plain fallback instead of vanishing.
    """

    def __init__(self, hub): self.hub = hub

    @staticmethod
    def skipped(r: dict) -> bool:
        return (r["kind"], r["subject"]) in SKIP or (r["kind"], r["new"]) in SKIP

    def fallback(self, r: dict, detail: dict) -> str:
        """For a shape nobody has written words for. Plain, and never empty -- a row with no sentence
        would draw as a bare icon with nothing beside it, which is how this was noticed."""
        name = self.name_of(r["subject"], detail)
        new = (r["new"] or "").strip()
        return f"changed {name}: {new}." if new else f"changed {name}."

    def name_of(self, subject: str, detail: dict) -> str:
        """What a subject is called, preferring what it is called NOW and falling back to what it was
        called when it happened -- a thing removed from the house is exactly what an audit asks about.

        The last resort is the id, and an id is the one thing that may not reach the panel: nothing a
        household reads ever says `light.frontyard_light`. So it is turned back into words. It is a
        guess at a name rather than the name, which is the right trade against printing the engine's
        vocabulary on the wall."""
        d = self.hub.home.devices.get(subject)
        if d: return d.name
        room = self.hub.home.rooms.get(subject)
        if room: return room.name
        return detail.get("name") or plainly(subject)

    def sentence(self, r: dict) -> str | None:
        """One row as a sentence, without its who. None ONLY for a row in SKIP; anything else this has
        no phrasing for comes back through `fallback` rather than disappearing."""
        kind, subject, new, old = r["kind"], r["subject"], r["new"] or "", r["old"]
        try: detail = json.loads(r["detail"]) if r["detail"] else {}
        except Exception: detail = {}
        if kind == "phone":
            name = detail.get("name") or "a phone"
            span = {"day": " for the day", "weekend": " for the weekend"}.get(detail.get("span"), "")
            return {"joined": f"let {name} into the house{span or ', for good'}.",
                    "removed": f"removed {name} from the house.",
                    "asked": "asked to join the house.",
                    "left": f"ended {name}'s stay, which was only ever for a while.",
                    "home only": f"stopped {name} reaching the house from outside.",
                    "not now": f"turned down {name}'s request to join.",
                    "can reach the house from outside": f"let {name} reach the house from outside.",
                    }.get(new) or self.fallback(r, detail)
        if kind == "draft":
            return {"approved": "approved a suggested routine.",
                    "discarded": "turned down a suggested routine."}.get(new) or self.fallback(r, detail)
        if kind == "bridge":
            return {"set up": f"set up the bridge {subject}.", "forgotten": f"took the bridge {subject} off the house.",
                    "nightlight on": f"turned the bridge {subject}'s nightlight on.",
                    "nightlight off": f"turned the bridge {subject}'s nightlight off.",
                    "light changed": f"changed the bridge {subject}'s light.",
                    "recognised": f"recognized the bridge {subject}.", "recognized": f"recognized the bridge {subject}.",
                    }.get(new) or self.fallback(r, detail)
        if kind == "share":
            if subject == "settings": return f"turned sharing with other apps {new}."
            # The row is ("share", "device", <the device id>, "shared"|"left out"): the id is in `old`,
            # and reading it off `subject` gave every one of these the sentence "shared device."
            if subject == "device":
                what = self.name_of(old or "", detail)
                return f"shared {what} with other apps." if new == "shared" else f"stopped sharing {what}."
            return "opened the window for another app to find the house."
        # kind == "home": the subject says which sort of change it was
        if subject == "room": return f"added the room {new}."
        if subject == "location": return f"set where home is to {new}."
        if subject == "entry": return "changed which rooms the family comes in through."
        if subject == "backup": return "took a backup of the house."
        if subject == "restore": return "asked to restore the house from a backup."
        if subject == "restart": return "asked the house to restart." if new == "asked" else self.fallback(r, detail)
        if subject == "assistant": return "connected the assistant."
        if subject == "credentials": return f"added a key for {new}."
        if subject == "device": return f"added {new} to the house."
        if subject == "driver":
            # The row's `new` is already a phrase ("Messages signed in"), which read as "The hub
            # Messages signed in." once a who was put in front of it.
            if new.endswith(" signed in"): return f"signed in to {new[:-len(' signed in')]}."
            if new.endswith(" connected"): return f"connected {new[:-len(' connected')]}."
            return self.fallback(r, detail)
        if subject == "setup":
            return {"code set": "set the passcode on the settings.", "code removed": "took the passcode off the settings.",
                    "owner created": "set the house up.", "finished": "finished setting the house up."
                    }.get(new) or self.fallback(r, detail)
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
        if detail.get("shown_as"): return f"now treats {name} as {KIND_AS.get(new, new)}."
        if detail.get("leads"): return f"made {name} the one that leads its room."
        if detail.get("paired"): return f"paired {new} over {detail['paired']}."
        return self.fallback(r, detail)

    def who_of(self, r: dict) -> str:
        """Who acted, where no phone was carried on the request. Never a guess at a person: the house
        says it was the house, and a wall with no code on it says only that it was the wall.

        A phone asking to join is its own actor -- the request comes from a phone the house has not
        let in yet, so it carries no name, and "Someone at the wall asked to join the house" describes
        the wrong person entirely."""
        if r["kind"] == "phone" and r["new"] == "asked":
            try: name = json.loads(r["detail"])["name"] if r["detail"] else None
            except Exception: name = None
            if name: return name
        if r["source"] in ("hub", "system"): return "The hub"
        if r["source"] == "assistant": return "The assistant"
        return "Someone at the wall"

    def coded_since(self) -> float | None:
        """When the code was set. Before it there were no phones to tell apart, so nothing before it
        can name anybody -- and the page says that rather than leaving a column mysteriously empty."""
        rows = self.hub.log.recent(20, subject="setup", kinds=("home",))
        setting = [r["ts"] for r in rows if r["new"] == "code set"]
        return max(setting) if setting and self.hub.lock.locked else None

    def rows(self, limit=200) -> list:
        """Newest first, at most `limit`. See the class docstring: the ONLY rows missing are SKIP."""
        out = []
        for r in self.hub.log.recent(limit * 3, kinds=AUDIT):
            if self.skipped(r): continue
            text = self.sentence(r) or self.fallback(r, {})
            if not text.strip(): continue        # belt and braces: a blank draws as a bare icon
            # A person is named; the house acting on its own says so. Neither is ever a guess: `who`
            # is null unless a request carried a phone, and events.py only reads it for source="user".
            who = r["who"] or self.who_of(r)
            out.append({"who": who, "text": text, "ts": r["ts"], "named": bool(r["who"]),
                        "when": when(r["ts"], self.hub.tz), "kind": r["kind"], "subject": r["subject"]})
            if len(out) >= limit: break
        return out

    def page(self, limit=200) -> dict:
        rows = self.rows(limit)
        return {"rows": rows, "coded_since": self.coded_since(),
                "coded_when": when(self.coded_since(), self.hub.tz) if self.coded_since() else None,
                # Said out loud, because a list that simply stops at 200 looks like a list that ended.
                "more": len(rows) >= limit}
