# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The hub starting a part of itself that did not come back, said where a household will see it.

On 26 September the hub was unplugged and carried to the garage, and Messages did not start again with
it: Docker could not restore the container and its restart policy never tried. Every bridge and light
strip sat outside a locked door while the brain went on answering. The host's watchdog now starts a
part like that (driver-layer/host/watchdog.sh), and writes one line to healed.jsonl each time.

This file is the other half, and it exists because docs/restart.md is plain that self-healing must
never be silent: that is how a household runs on a dying card for a year. design/healed/ settled how
it is said, direction C:

- **Once, it is news.** A span on What happened, saying what was cut off and for how long. Nothing on
  Home and nothing on Needs a look, because by the time anybody reads it there is nothing left to do.
- **When it keeps happening, it is a job.** The third time in a week it goes on Needs a look, says
  what the pattern means, and offers the one thing that helps from the wall: a backup.

The host cannot reach the diary, so the line goes through a file. `take()` moves every record into
the event log -- with what was cut off, named NOW, while the house still has those things -- and then
deletes the file. It is called from the two pages that read it, so there is no third timer to keep.
"""
import json, logging, re, time
from datetime import datetime

from .health import when
from .settings import DATA

log = logging.getLogger("hub.healed")

FILE = DATA / "healed.jsonl"
DAY = 86400
WEEK, AGAIN = 7 * DAY, 3      # this many in a week and it has stopped being news
BOOT = 300                    # a part that stopped this close to the hub starting up stopped BECAUSE it did
NAMED = 2                     # what was cut off, by name, before the rest become a count

# Compose's services, in the words the panel already uses for them (provision.PARTS), and the
# integration whose things go quiet when each one stops. "*" is the engine: everything goes with it.
PARTS = {"mosquitto": ("Messages", "mqtt"), "zigbee2mqtt": ("The Zigbee radio", "mqtt"),
         "ring-mqtt": ("Ring", "mqtt"), "zwave-js-ui": ("The Z-Wave radio", "zwave_js"),
         "matter-server": ("Matter", "matter"), "homeassistant": ("The hub's engine", "*"),
         "matter-bridge": ("Sharing with Apple Home, Google Home and Alexa", None),
         "wyoming-piper": ("The hub's voice", None), "caddy": ("The way in to the hub", None),
         "frpc": ("The way in from outside the house", None),
         "lan-cert": ("The house's name at home", None)}


def stamp(docker_time: str) -> float | None:
    """Docker's FinishedAt as epoch seconds. It carries nine digits of fraction and a Z, and Python
    takes six; the zero time is what Docker says for a container that never finished."""
    if not docker_time or docker_time.startswith("0001"): return None
    t = re.sub(r"(\.\d{6})\d+", r"\1", docker_time).replace("Z", "+00:00")
    try: return datetime.fromisoformat(t).timestamp()
    except ValueError: return None


def named(p: str) -> str:
    return PARTS.get(p, ("Part of the hub", None))[0]


def lower(s: str) -> str:
    """A part's name inside a sentence: "the Zigbee radio", but still "Messages" and "Matter"."""
    return s[0].lower() + s[1:] if s.startswith("The ") else s


class Healed:
    def __init__(self, hub): self.hub = hub

    def take(self):
        """Every line the watchdog has written, into the diary; then the file goes. Never raises: a
        page that reads this must still draw if the file is half-written or the disk is full."""
        try: lines = FILE.read_text().splitlines()
        except OSError: return
        try: FILE.unlink()
        except OSError: pass
        for line in lines:
            try: r = json.loads(line)
            except ValueError: continue
            for p in r.get("parts") or []:
                svc = p.get("service") or "?"
                self.hub.log.add("home", "healed", old=svc, new="started", source="watchdog", detail={
                    "at": r.get("at") or time.time(), "stopped": stamp(p.get("stopped") or ""),
                    "boot": r.get("boot"), "with": self.cut_off(svc)})

    def cut_off(self, svc: str) -> list:
        """The names of what could not be reached while it was down, as the house has them now."""
        domain = PARTS.get(svc, (None, None))[1]
        if not domain: return []
        domains = getattr(self.hub.provision, "domains", None) or {}
        return sorted(d.name for d in self.hub.home.devices.values()
                      if d.room_id != "unassigned" and (domain == "*" or domains.get(d.entry) == domain))

    def recent(self, since: float) -> list:
        out = []
        for r in self.hub.log.recent(200, subject="healed", kinds=("home",), since=since):
            try: detail = json.loads(r.get("detail") or "{}")
            except ValueError: detail = {}
            out.append({**detail, "service": r["old"], "ts": r["ts"]})
        return out

    # ---- once: What happened ----
    def over(self, since: float, now=None) -> list:
        """One line each, the way What happened says anything that is over: a span, no buttons."""
        now = now or time.time()
        tz = self.hub.tz
        out = []
        for h in self.recent(since):
            b = float(h.get("at") or h["ts"])
            a = h.get("stopped") or None
            name = named(h["service"])
            whom = self.whom(h.get("with") or [], h["service"])
            after = f", so {whom} cut off until the hub started it again itself." if whom else \
                    ". The hub started it again itself."
            if a and h.get("boot") and abs(a - float(h["boot"])) < BOOT:
                text = f"The hub lost power at {when(a, tz, now)}. When it came back, {lower(name)} did not{after}"
            elif a:
                text = f"{name} stopped at {when(a, tz, now)} and did not start again{after}"
            else:
                text = f"{name} was not running{after}"
            span = f"{when(a, tz, now)} – {when(b, tz, now)}" if a and when(a, tz, now) != when(b, tz, now) else when(b, tz, now)
            out.append({"kind": "over", "subject": f"healed:{h['service']}", "seconds": (b - a) if a else 0,
                        "ts": b, "text": text, "word": "hub", "when": span, "acts": []})
        return out

    def whom(self, names: list, svc: str) -> str:
        if PARTS.get(svc, (None, None))[1] == "*": return "everything in the house was"
        if not names: return ""
        if len(names) == 1: return f"{names[0]} was"
        if len(names) <= NAMED: return f"{names[0]} and {names[1]} were"
        rest = len(names) - NAMED
        return f"{', '.join(names[:NAMED])} and {rest} more {'thing' if rest == 1 else 'things'} were"

    # ---- again: Needs a look ----
    def notes(self, now=None) -> list:
        """The line that asks somebody to do something, and only once it has become a pattern."""
        now = now or time.time()
        week = self.recent(now - WEEK)
        if len(week) < AGAIN: return []
        parts = {h["service"] for h in week}
        name = named(next(iter(parts))) if len(parts) == 1 else None
        power = sum(1 for h in week if h.get("stopped") and h.get("boot") and abs(h["stopped"] - float(h["boot"])) < BOOT)
        what = f"{lower(name)} did not start again by itself" if name else "part of the hub did not start again by itself"
        if power == len(week):
            text = f"The hub has lost power {len(week)} times this week, and each time {what}."
            why = "A power cut can wear out the hub's memory card. A backup now means nothing is lost if it goes."
        else:
            text = f"{what[0].upper() + what[1:]} {len(week)} times this week, and the hub had to start it."
            why = "Something is wrong that starting it again is not fixing. A backup now means nothing is lost if it gets worse."
        return [{"kind": "healed", "subject": None, "since": week[-1]["ts"], "text": text, "more": why,
                 "acts": [{"do": "Back up", "act": "backup", "to": None}]}]
