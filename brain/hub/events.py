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

    def recent(self, limit=100, subject=None):
        q = "SELECT ts,kind,subject,old,new,source,detail FROM events"
        args = ()
        if subject: q += " WHERE subject=?"; args = (subject,)
        q += " ORDER BY ts DESC LIMIT ?"
        rows = self.db.execute(q, args + (limit,)).fetchall()
        return [dict(zip(("ts", "kind", "subject", "old", "new", "source", "detail"), r)) for r in rows]
