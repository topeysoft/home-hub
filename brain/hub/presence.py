"""Who is home. Read from HA's person entities and the alarm's mode; the house has no other way to know.

People decide when there are any: somebody is home if any person is, nobody if every person is away. The
alarm overrides in one direction: armed away means nobody, whatever a phone still claims. With no people,
disarmed or armed home means somebody. Anything else (arming, pending, triggered, unavailable) leaves the
last answer standing. Before there is any answer at all `somebody` is None and presence rules never fire.
"""
import time

AWAY = {"armed_away", "armed_vacation"}
HERE = {"disarmed", "armed_home", "armed_night", "armed_custom_bypass"}
WATCHED = ("person.", "alarm_control_panel.")


def word(somebody) -> str | None:
    """The rule vocabulary for a presence answer: somebody, nobody, or None while unknown."""
    return None if somebody is None else ("somebody" if somebody else "nobody")


class Presence:
    def __init__(self, hub):
        self.hub = hub
        self.people: dict[str, dict] = {}   # person.<x> -> {"name", "home": True | False | None}
        self.alarm: dict | None = None       # {"id", "state"} for the first alarm panel seen
        self.somebody: bool | None = None
        self.since: float | None = None      # when the answer last flipped; presence timers count from it

    def load(self, states):
        """From a snapshot. `since` survives a rebuild when the answer did not change."""
        self.people, self.alarm = {}, None
        for s in states: self._take(s["entity_id"], s)
        self._settle()

    def seed(self, log):
        """After a restart the answer is the same as before it, so count from the flip the log remembers."""
        rows = log.recent(1, subject="home", kinds=("presence",))
        if rows and rows[0]["new"] == word(self.somebody) and self.somebody is not None:
            self.since = rows[0]["ts"]

    def _take(self, eid, s) -> bool:
        if eid.startswith("person."):
            self.people[eid] = {"name": s["attributes"].get("friendly_name") or eid.split(".", 1)[1], "home": self._is_home(s["state"])}
            return True
        if eid.startswith("alarm_control_panel.") and (self.alarm is None or self.alarm["id"] == eid):
            self.alarm = {"id": eid, "state": s["state"]}
            return True
        return False

    @staticmethod
    def _is_home(state):
        if state in (None, "unknown", "unavailable"): return None
        return state == "home"     # not_home, or the name of some other zone: away

    def on_state(self, eid, new_state) -> bool:
        """A person or the alarm changed. True when the answer flipped."""
        if not new_state or not self._take(eid, new_state): return False
        return self._settle()

    def compute(self) -> bool | None:
        alarm = self.alarm and self.alarm["state"]
        if alarm in AWAY: return False
        known = [p["home"] for p in self.people.values() if p["home"] is not None]
        if known: return any(known)
        if alarm in HERE: return True
        return self.somebody

    def _settle(self) -> bool:
        now = self.compute()
        if now == self.somebody: return False
        self.somebody, self.since = now, time.time()
        return True

    def source(self) -> str | None:
        alarm = self.alarm and self.alarm["state"]
        if alarm in AWAY: return "alarm"
        if any(p["home"] is not None for p in self.people.values()): return "people"
        if alarm in HERE: return "alarm"
        return None

    def as_dict(self):
        return {"somebody": self.somebody, "since": self.since, "source": self.source(),
                "people": [{"name": p["name"], "home": p["home"]} for p in self.people.values()],
                "alarm": self.alarm and self.alarm["state"]}
