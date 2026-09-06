"""Append-only event log. The assistant explains from this; nothing executes from it."""
import sqlite3, time, json, threading


class EventLog:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.execute("""CREATE TABLE IF NOT EXISTS events(
            ts REAL, kind TEXT, subject TEXT, old TEXT, new TEXT, source TEXT, detail TEXT)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_ts ON events(ts)")

    def add(self, kind, subject, old=None, new=None, source="device", detail=None):
        with self.lock:
            self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",
                            (time.time(), kind, subject, old, new, source, json.dumps(detail) if detail else None))
            self.db.commit()

    def recent(self, limit=100, subject=None, kinds=None):
        """Newest first. `subject` is one id or a tuple of them; `kinds` a tuple of event kinds."""
        q = "SELECT ts,kind,subject,old,new,source,detail FROM events"
        where, args = [], ()
        if isinstance(subject, (tuple, list, set)):
            subject = tuple(subject); where.append(f"subject IN ({','.join('?' * len(subject))})"); args += subject
        elif subject: where.append("subject=?"); args += (subject,)
        if kinds: where.append(f"kind IN ({','.join('?' * len(kinds))})"); args += tuple(kinds)
        if where: q += " WHERE " + " AND ".join(where)
        q += " ORDER BY ts DESC LIMIT ?"
        rows = self.db.execute(q, args + (limit,)).fetchall()
        return [dict(zip(("ts", "kind", "subject", "old", "new", "source", "detail"), r)) for r in rows]

    def last_by_subject(self, kind, new) -> dict:
        """subject -> the last time it was logged reaching `new`. Rooms rebuild motion_at from this after a restart."""
        rows = self.db.execute("SELECT subject, MAX(ts) FROM events WHERE kind=? AND new=? GROUP BY subject", (kind, new)).fetchall()
        return dict(rows)
