# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turning it off and on again.

Everybody knows the verb and nobody means the same thing by it, so the panel has one door and this
module keeps the ladder behind it. Four rungs, deepest last:

  part        one part of the driver layer          provision.retry_part, offered on Needs a look
  hub         the brain                             this module, and it costs nothing to build
  everything  the whole stack, engine included      the host, through restart.request
  machine     the box                               the host, through restart.request

Rung `hub` is the one a household reaches for most and it needs no privilege at all: the brain
finishes the response, says where it went, and raises SIGTERM on itself. Compose brings it back
(`restart: unless-stopped`) within a second or two. Nothing here runs docker, and nothing here holds
a socket that could -- the same rule updates.py keeps, and for the same reason: it is what stops
anything able to write into the data volume from choosing what runs on the machine.

The two deeper rungs go out the way an update does: a file the host is watching, carrying **a rung
from a fixed set and never a command**. host/restart.sh validates the word again on its side before
it does anything with it.

What comes back up reads restart.json and learns from it. A hub that takes ninety seconds to come
back should say ninety seconds next time rather than the figure that was true on the maker's desk;
that is the whole reason this writes anything down. See docs/restart.md.
"""
import asyncio, json, logging, os, signal, time

from . import backup as backup_mod
from .settings import DATA

log = logging.getLogger("hub.restart")

REQUEST = DATA / "restart.request"   # the host's home-hub-restart.path is watching for exactly this
STATE = DATA / "restart.json"        # written on the way down, read and cleared on the way back up

RUNGS = ("hub", "everything", "machine")
DEEPER = {"hub": "everything", "everything": "machine", "machine": None}
HOSTS = ("everything", "machine")    # the two the brain cannot do itself
USUALLY = {"hub": 30, "everything": 120, "machine": 180}   # seconds, until this hub has measured its own
GOING = 1.0        # how long the brain waits before going, so the answer reaches the screen first
CAP = 900          # a gap longer than this was not a restart, so nothing is learned from it
IN_FLIGHT = 300    # after this, a restart that never came back stops standing in the way of the next
WEARY, HOUR = 3, 3600.0   # restarts in an hour past which the same rung has stopped being the answer

TITLE = {"hub": "Restart the hub?", "everything": "Restart everything?", "machine": "Restart the little computer?"}
DO = {"hub": "Restart the hub", "everything": "Restart everything", "machine": "Restart the little computer"}
# What is still true while it is away. This is the first line and it is the one people are actually
# asking about: a Zigbee group bound coordinator-side keeps switching, a Brilliant pair migrated to
# the house's own network talks switch-to-switch with the hub out of the path, and a wall switch is a
# wall switch. "The house goes dark" is the fear; it is not what happens.
KEEPS = {"hub": "Lights and switches keep working.",
         "everything": "Switches on the wall keep working.",
         "machine": "Switches on the wall keep working."}


def plainly(seconds: int) -> str:
    """Seconds as a household says them. Shared with updates.py, which asks the same question."""
    if seconds < 90: return f"about {int(round(seconds / 10.0)) * 10} seconds"
    return f"about {int(round(seconds / 60.0))} minutes"


class Restart:
    def __init__(self, hub):
        self.hub = hub
        self.went: dict | None = None     # what this process was told on the way down, if it was told anything
        self._came_back()

    # ---- coming back ----
    def _came_back(self):
        """Read what the last of us left, learn how long it took, and say so in the log.

        Only ever called at start. A hub that was pulled out of the wall left nothing here, which is
        the honest answer: it did not restart, it stopped.
        """
        try: went = json.loads(STATE.read_text())
        except (OSError, ValueError): return
        try: STATE.unlink()
        except OSError: pass
        rung, at = went.get("rung"), float(went.get("at") or 0)
        took = time.time() - at
        if rung in RUNGS and 0 < took < CAP:
            self.went = {**went, "took": round(took)}
            kept = dict(self.hub.settings.get("restart_took") or {})
            kept[rung] = round(took)
            self.hub.settings.set(restart_took=kept)
            self.hub.log.add("home", "restart", rung, "back", source=went.get("source") or "user",
                             detail={"took": round(took), "who": went.get("who")})
            log.info("back from a %s restart after %ds", rung, round(took))

    # ---- what a restart would cost, in this house, right now ----
    def seconds(self, rung: str) -> int:
        """How long this hub's own last restart at this rung took, or a careful guess until it has one."""
        kept = self.hub.settings.get("restart_took") or {}
        try: measured = int(kept.get(rung) or 0)
        except (TypeError, ValueError): measured = 0
        return measured if 5 <= measured < CAP else USUALLY[rung]

    def stops(self, rung: str, away: bool = False) -> list[str]:
        """What actually stops, said only where it is true of this house.

        A sentence that is true of *some* house is how a panel earns the reputation of exaggerating,
        so every line here is asked of the house before it is offered.
        """
        out = []
        hub = self.hub
        if rung == "hub":
            if getattr(getattr(hub, "rules", None), "rules", None): out.append("Motion lights and schedules pause.")
            try: talks = bool(hub.assistant.status().get("configured"))
            except Exception: talks = False
            if talks: out.append("The assistant can't answer.")
        else:
            out.append("Everything the hub talks to goes quiet until it's back — lights, sensors and the radios.")
        try: shared = bool(hub.share.settings.get("on"))
        except Exception: shared = False
        if shared: out.append("Apple Home, Google Home and Alexa say “no response” until it's back.")
        if away: out.append("This phone loses the house until it's back.")
        return out

    def flight(self, rung: str) -> list[str]:
        """What is half-done right now and will not survive. Nothing vanishes under a tap unnamed."""
        out = []
        s = getattr(getattr(self.hub, "pair", None), "session", None) or {}
        if s.get("state") in ("listening", "found", "pin", "working"):
            out.append("The house is waiting for a new device to pair; you'll need to start that again.")
        j = getattr(getattr(self.hub, "bridge", None), "job", None) or {}
        if j.get("state") in ("working", "placing"):
            out.append("You're partway through setting up a bridge; you'll need to start that again.")
        return out

    # ---- whether it may happen at all ----
    def blocked(self) -> str | None:
        """The one refusal, in the words the row shows. The panel hides the button too; this is what
        answers a phone whose page is an hour old and still has it."""
        if self.hub.updates.running():
            return "The hub is installing an update. It restarts itself when that's done."
        if (self.hub.backup.state() or {}).get("state") == "running" or backup_mod.REQUEST.exists():
            return "The hub is putting a backup back. It restarts itself when that's done."
        return None

    def pending(self) -> bool:
        """One at a time. A restart that never came back stops standing in the way after IN_FLIGHT,
        because the alternative is a house that can never be restarted again."""
        try: went = json.loads(STATE.read_text())
        except (OSError, ValueError): return False
        return time.time() - float(went.get("at") or 0) < IN_FLIGHT

    def lately(self, within: float = HOUR) -> int:
        """How many restarts somebody has asked for in the past hour. Read off the event log, which is
        the one record that survives the thing it is counting."""
        now = time.time()
        return sum(1 for e in self.hub.log.recent(limit=50, subject="restart", kinds=("home",))
                   if e["new"] == "asked" and now - e["ts"] < within)

    # ---- the sheet ----
    def ask(self, rung: str = "hub", away: bool = False) -> dict:
        """Everything the confirmation needs, written here rather than in the panel: the panel does not
        know what it is looking at and so decides none of these words."""
        rung = rung if rung in RUNGS else "hub"
        lately = self.lately()        # a query against the log; the sheet asked it three times over
        weary = lately >= WEARY
        secs = self.seconds(rung)
        return {"rung": rung, "title": TITLE[rung], "yes": DO[rung], "keeps": KEEPS[rung],
                "stops": self.stops(rung, away), "flight": self.flight(rung),
                "seconds": secs, "how_long": plainly(secs),
                "blocked": self.blocked(), "busy": self.pending(), "lately": lately,
                # Once the same rung has been tried three times in an hour it has stopped being the
                # answer, and saying so is worth more than offering it a fourth time.
                "harder": DEEPER[rung] if weary else None,
                "weary": f"The hub has restarted {lately} times in the past hour. Something is wrong that restarting isn't fixing." if weary else None,
                # Nobody is home to reach the plug, and no rung below this one can be undone from away
                # either. The away phone is told, and then allowed: the household that most needs this
                # is the one furthest from the socket.
                "warn": ("Nobody is home to unplug it. If it doesn't come back, the house stays like this "
                         "until somebody's there.") if (away and rung == "machine") else None}

    # ---- and the doing ----
    def go(self, rung: str, who: str = "the wall", *, away: bool = False, understood: bool = False, source: str = "user") -> dict:
        """Write down where we went, say so, and go. Raises ValueError with the sentence to show."""
        if rung not in RUNGS: raise ValueError("That is not something the hub knows how to restart.")
        blocked = self.blocked()
        if blocked: raise ValueError(blocked)
        if self.pending(): raise ValueError("The hub is already restarting. Give it a moment.")
        if away and rung == "machine" and not understood:
            raise ValueError(self.ask(rung, away=True)["warn"])
        went = {"rung": rung, "at": time.time(), "who": who, "away": away, "source": source}
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(went))
        self.hub.log.add("home", "restart", rung, "asked", source=source, detail={"who": who, "away": away})
        log.info("%s asked for a %s restart", who, rung)
        answer = {"rung": rung, "seconds": self.seconds(rung), "how_long": plainly(self.seconds(rung))}
        if rung in HOSTS:
            # Advisory, like the update request beside it: it names a rung from a fixed set and never
            # a command, and the host checks the word again before it acts on it.
            REQUEST.write_text(json.dumps({"at": went["at"], "rung": rung}))
        else:
            self.quit()
        return answer

    def quit(self, after: float = GOING):
        """Go, a moment after the answer has left. SIGTERM rather than exit: uvicorn then shuts down the
        way it does for a `docker restart`, the lifespan closes the engine's socket and the event log,
        and compose brings the container straight back."""
        async def then():
            await asyncio.sleep(after)
            log.info("going down now")
            signal.raise_signal(signal.SIGTERM)
        try: asyncio.get_running_loop().create_task(then())
        except RuntimeError: os.kill(os.getpid(), signal.SIGTERM)   # no loop: a test, or a hub going down anyway
