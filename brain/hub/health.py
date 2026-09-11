"""Health in plain words. The facts are already in the house: which devices have gone quiet and since when
(the event log), how full the hub's storage is, which driver parts want attention, whether the last update
finished. This turns them into a short list of sentences for one quiet place on the panel. Nothing here
acts; it only says."""
import shutil, time
from datetime import datetime
from .settings import DATA

LOW_FREE = 2 * 1024 ** 3     # bytes; below this, or below a tenth of the disk, storage is "nearly full"
MAX_OFFLINE_LINES = 5


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
        out = []
        out += self.offline()
        out += self.storage()
        out += self.drivers()
        out += self.update()
        return out

    def offline(self) -> list:
        gone = [d for d in self.hub.home.devices.values() if d.state == "unavailable" and d.room_id != "unassigned"]
        if not gone: return []
        since = self.hub.log.last_by_subject("state", "unavailable")
        gone.sort(key=lambda d: since.get(d.id, float("inf")))
        out = []
        for d in gone[:MAX_OFFLINE_LINES]:
            ts = since.get(d.id)
            out.append({"kind": "offline", "subject": d.id, "since": ts,
                        "text": f"{d.name} has been offline since {when(ts, self.hub.tz)}." if ts else f"{d.name} is offline."})
        if len(gone) > MAX_OFFLINE_LINES:
            out.append({"kind": "offline", "subject": None, "since": None, "text": f"And {len(gone) - MAX_OFFLINE_LINES} more things are offline."})
        return out

    def storage(self) -> list:
        try: u = shutil.disk_usage(DATA)
        except OSError: return []
        if u.free < LOW_FREE or u.free < u.total / 10:
            gb = u.free / 1024 ** 3
            left = f"{gb:.1f} GB" if gb >= 1 else f"{u.free / 1024 ** 2:.0f} MB"
            return [{"kind": "storage", "subject": None, "since": None, "text": f"The hub's storage is nearly full: {left} left."}]
        return []

    def drivers(self) -> list:
        out = []
        # accounts waiting for a person. `flow` is the conversation that finishes it, so the panel can offer it here.
        for w in self.hub.provision.sign_ins:
            checking = w.get("source") == "reconfigure"
            what = "needs a setting checked" if checking else "needs signing in again"
            who = w.get("kind") or w.get("title") or "An account"
            tail = f": {w['title']}" if w.get("title") and w["title"] != who else ""
            out.append({"kind": "driver", "subject": w.get("handler"), "since": None, "text": f"{who} {what}{tail}.",
                        "flow": w["flow_id"], "do": "Check it" if checking else "Sign in again"})
        for p in self.hub.provision.summary():
            if p.get("state") == "sign-in": out.append({"kind": "driver", "subject": p["id"], "since": None, "text": f"{p['name']} needs signing in again."})
            elif p.get("state") == "failed": out.append({"kind": "driver", "subject": p["id"], "since": None, "text": f"{p['name']} is not running: {p.get('text') or 'it stopped'}"})
        # something HA has but could not start. `retry` is the entry to ask again, once whatever it complained about is fixed.
        for q in self.hub.provision.problems:
            out.append({"kind": "driver", "subject": q.get("entry_id"), "since": None, "retry": q.get("entry_id"), "do": "Try again",
                        "text": f"{q.get('title')} could not connect{': ' + q['reason'] if q.get('reason') else '.'}"})
        return out

    def update(self) -> list:
        st = self.hub.updates.state() or {}
        if st.get("state") == "failed":
            return [{"kind": "update", "subject": None, "since": st.get("finished"), "text": "The last update did not finish. You can try it again from here."}]
        return []
