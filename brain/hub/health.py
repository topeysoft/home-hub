# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Health in plain words. The facts are already in the house: which devices have gone quiet and since when
(the event log), how full the hub's storage is, which driver parts want attention, whether the last update
finished. This turns them into a short list for one quiet place on the panel.

It used to only say. A page of nine true sentences with two buttons on it is a report, and a person who
opens it because the panel told them eight things need a look has been handed a report and no way out of
it. So two rules turn a sentence into a job.

**A fault is said once.** A radio that stops answering takes everything on it quiet with it, and a house
that reports that eight times has buried the one thing worth doing. The fault is the line; what went
quiet behind it rides along in `with`, named, so a person can see it is their front door and their
dimmer and not wonder. Fix the radio and the eight go together. This is why a device carries the entry
that brought it (model.Device.entry) and why Provision keeps what each entry is (Provision.domains):
without those two the panel can only show effects and never the cause.

**Every line carries what can be done about it,** in `acts`: `{do, act, to}`, and `ask`/`yes` where the
doing is worth a second's thought first -- the question and the words that answer it, both with the name
in them, because "Are you sure?" is not a question anybody can answer. The panel draws them as buttons and invents none of its own, because
it does not know what it is looking at. An empty `acts` is a line worth saying and not worth tapping --
which should be rare, and where it is not, the thing to fix is here rather than in the panel.
"""
import shutil, time
from datetime import datetime
from .model import kind_of
from .provision import PARTS
from .settings import DATA

LOW_FREE = 2 * 1024 ** 3     # bytes; below this, or below a tenth of the disk, storage is "nearly full"

# Which integration each part the hub runs itself is, so the things on it can be gathered under it when it
# stops. The parts with no integration of their own (Zigbee, Ring) arrive over Messages and group under that.
PART_DOMAIN = {pid: domain for pid, _, _, domain, _ in PARTS if domain}

# What a thing is, for a line that has to help somebody walk to it. The panel's own KIND_WORD (api.py) is
# the label on a menu; these are the same idea in the middle of a sentence.
KIND_WORDS = {"light": "a light", "switch": "a plug", "fan": "a fan", "media": "a speaker", "cover": "a blind",
              "climate": "a thermostat", "lock": "a lock", "camera": "a camera", "vacuum": "a vacuum"}


def when(ts, tz, now=None) -> str:
    """'3:10 pm' today, 'yesterday', a weekday within the week, else 'Aug 30'."""
    now = now or time.time()
    d, n = datetime.fromtimestamp(ts, tz), datetime.fromtimestamp(now, tz)
    days = (n.date() - d.date()).days
    if days <= 0: return d.strftime("%-I:%M %p").lower()
    if days == 1: return "yesterday"
    if days < 7: return d.strftime("%A")
    return d.strftime("%b %-d")


class Health:
    def __init__(self, hub): self.hub = hub

    def notes(self) -> list:
        """The jobs, causes first. A fault that explains a device takes it out of the list of its own, so
        a house with one dead radio has one line and not nine."""
        gone = [d for d in self.hub.home.devices.values() if d.state == "unavailable" and d.room_id != "unassigned"]
        since = self.hub.log.last_by_subject("state", "unavailable") if gone else {}
        gone.sort(key=lambda d: since.get(d.id, float("inf")))
        faults = self.drivers(gone)
        claimed = {w["id"] for f in faults for w in f.get("with", ())}
        return faults + self.offline([d for d in gone if d.id not in claimed], since) + self.storage() + self.update()

    def where(self, d) -> str:
        """Which room, and what sort of thing -- the two facts somebody needs to go and look at it. A name
        on its own ("Dimmer is offline") is a riddle in a house with more than one room."""
        room = self.hub.home.rooms.get(d.room_id)
        what = KIND_WORDS.get(kind_of(d).split(".")[0])
        return " · ".join(x for x in ((room.name if room else None), what) if x)

    def about(self, d) -> dict:
        """One quiet thing, as it rides along under the fault that took it."""
        return {"id": d.id, "name": d.name, "where": self.where(d)}

    def offline(self, gone, since: dict | None = None) -> list:
        """The things nothing else explains. Every one of them is here -- the list used to stop at five and
        end with "And 3 more things are offline", which is a sentence with nowhere to go. The panel folds
        a long list itself, where the fold can be opened."""
        if since is None: since = self.hub.log.last_by_subject("state", "unavailable") if gone else {}
        out = []
        for d in gone:
            ts = since.get(d.id)
            out.append({"kind": "offline", "subject": d.id, "since": ts, "where": self.where(d), "name": d.name,
                        "text": f"{d.name} has been offline since {when(ts, self.hub.tz)}." if ts else f"{d.name} is offline.",
                        "acts": [{"do": "Check again", "act": "check", "to": d.id},
                                 {"do": "It's gone, remove it", "act": "forget", "to": d.id, "yes": f"Yes, remove {d.name}",
                                  "ask": f"Remove {d.name} from the house? It comes off the account that brought it."}]})
        return out

    def storage(self) -> list:
        try: u = shutil.disk_usage(DATA)
        except OSError: return []
        if u.free < LOW_FREE or u.free < u.total / 10:
            gb = u.free / 1024 ** 3
            left = f"{gb:.1f} GB" if gb >= 1 else f"{u.free / 1024 ** 2:.0f} MB"
            return [{"kind": "storage", "subject": None, "since": None, "acts": [],
                     "text": f"The hub's storage is nearly full: {left} left."}]
        return []

    def drivers(self, gone=()) -> list:
        """What the house talks through, where it has stopped talking -- and, under each one, the devices
        that went quiet with it.

        A device says which entry brought it and Provision says what each entry is, so a fault can claim
        its own: an account by the integration it signs into, a part of the driver layer by the integration
        it adds, something HA could not start by the entry it could not start. Nothing is claimed twice; the
        first fault that can explain a device keeps it.
        """
        out, claimed = [], set()
        domains = getattr(self.hub.provision, "domains", None) or {}
        by_domain, by_entry = {}, {}
        for d in gone:
            by_entry.setdefault(d.entry, []).append(d)
            if d.entry in domains: by_domain.setdefault(domains[d.entry], []).append(d)

        def took(*, domain=None, entry=None) -> list:
            pool = by_domain.get(domain, []) if domain else by_entry.get(entry, [])
            mine = [self.about(d) for d in pool if d.id not in claimed]
            claimed.update(w["id"] for w in mine)
            return mine

        # accounts waiting for a person. `flow` is the conversation that finishes it, so the panel can offer it here.
        for w in self.hub.provision.sign_ins:
            checking = w.get("source") == "reconfigure"
            what = "needs a setting checked" if checking else "needs signing in again"
            who = w.get("kind") or w.get("title") or "An account"
            tail = f": {w['title']}" if w.get("title") and w["title"] != who else ""
            out.append({"kind": "driver", "subject": w.get("handler"), "since": None, "text": f"{who} {what}{tail}.",
                        "with": took(domain=w.get("handler")),
                        "acts": [{"do": "Check it" if checking else "Sign in again", "act": "flow", "to": w["flow_id"]}]})
        for p in self.hub.provision.summary():
            mine = took(domain=PART_DOMAIN.get(p["id"]))
            if p.get("state") == "sign-in":
                out.append({"kind": "driver", "subject": p["id"], "since": None, "acts": [], "with": mine,
                            "text": f"{p['name']} needs signing in again."})
            elif p.get("state") == "failed":
                out.append({"kind": "driver", "subject": p["id"], "since": None, "with": mine,
                            "text": f"{p['name']} is not running: {p.get('text') or 'it stopped'}",
                            "acts": [{"do": "Try again", "act": "part", "to": p["id"]}]})
            elif p.get("state") == "off" and mine:
                # A part that is simply not there is only news when something was depending on it. A Zigbee
                # stick nobody has plugged in is not a fault; a Zigbee stick six devices are waiting on is.
                out.append({"kind": "driver", "subject": p["id"], "since": None, "with": mine,
                            "text": p.get("text") or f"{p['name']} is not running.",
                            "acts": [{"do": "Try again", "act": "part", "to": p["id"]}]})
            else:
                claimed.difference_update(w["id"] for w in mine)   # a part that is fine explains nothing
        # something HA has but could not start. `retry` is the entry to ask again, once whatever it complained about is fixed.
        for q in self.hub.provision.problems:
            out.append({"kind": "driver", "subject": q.get("entry_id"), "since": None, "with": took(entry=q.get("entry_id")),
                        "text": f"{q.get('title')} could not connect{': ' + q['reason'] if q.get('reason') else '.'}",
                        "acts": [{"do": "Try again", "act": "entry", "to": q.get("entry_id")}]})
        return out

    def update(self) -> list:
        """An update that did not finish, did not start, or could not be undone.

        All three end in the same *Try again*, because that is the only thing a household can do from
        the wall, and all three say the house is working -- which is true, and is the sentence somebody
        standing in front of a panel full of warnings most needs to read.
        """
        st = self.hub.updates.state() or {}
        state, bad = st.get("state"), st.get("bad")
        what = f"Version {bad}" if bad else "The last update"
        if state == "refused":
            # Nothing was installed and nothing is broken, so this is news rather than a job. And it
            # carries no Try again: the same tap would refuse the same release, and sending somebody
            # round that loop is worse than telling them plainly that it is not theirs to fix.
            return [{"kind": "update", "subject": None, "since": st.get("finished"), "acts": [],
                     "text": f"{what} could not be checked, so the hub did not install it. Nothing has changed and the house is working normally."}]
        if state == "reverted":
            text = f"{what} did not start, so the hub put back the one it was on. Everything is working; you can try it again from here."
        elif state == "failed" and st.get("reverted") is False:
            text = f"{what} did not start, and the hub could not put back the one it was on. Try it again; if this keeps saying the same thing, the hub needs a hand."
        elif state == "failed":
            text = "The last update did not finish. You can try it again from here."
        else:
            return []
        return [{"kind": "update", "subject": None, "since": st.get("finished"), "text": text,
                 "acts": [{"do": "Try again", "act": "update", "to": None}]}]
