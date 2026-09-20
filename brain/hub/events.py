# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only event log. The assistant explains from this; nothing executes from it."""
import logging, sqlite3, time, json, threading

log = logging.getLogger(__name__)


class EventLog:
    def __init__(self, path):
        # 30 seconds, not the 5 Python gives you. The one moment two things want this file at once is
        # a hub update: the old brain is finishing what it was doing while the new one starts and
        # opens the same database. Five seconds of a Pi writing container layers to an SD card is
        # nothing, and the write that lost the race raised straight into whatever was mid-job.
        self.db = sqlite3.connect(path, check_same_thread=False, timeout=30)
        self.lock = threading.Lock()
        # WAL, so a reader never blocks the writer. The assistant reads five thousand rows at a time
        # and the backup copies the whole file; under the rollback journal either of those excludes
        # an INSERT for as long as it runs. NORMAL is WAL's safe pairing and spares the card a
        # fsync per line -- a crash can cost the last few events, which is the right thing to risk
        # in a diary. Wrapped because a database opened by something else will refuse the change,
        # and a hub that will not start is worse than a hub without WAL.
        for pragma in ("journal_mode=WAL", "busy_timeout=30000", "synchronous=NORMAL"):
            try: self.db.execute(f"PRAGMA {pragma}")
            except sqlite3.Error as e: log.warning("events.db: could not set %s (%s)", pragma, e)
        self.db.execute("""CREATE TABLE IF NOT EXISTS events(
            ts REAL, kind TEXT, subject TEXT, old TEXT, new TEXT, source TEXT, detail TEXT)""")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_ts ON events(ts)")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_source_ts ON events(source, ts)")

    def add(self, kind, subject, old=None, new=None, source="device", detail=None):
        """Write one line down. NEVER raises.

        This is a diary, and 75 places in the house call it -- mid-job, mid-request, inside a
        `try` that belongs to something else entirely. A bridge had its firmware written, its Wi-Fi
        configured and its keys handed over, and then failed with "database is locked" on the
        screen, because the line saying so could not be written. Losing a line of the diary is not
        losing the thing it was about, and it must never be able to say otherwise.
        """
        try:
            with self.lock:
                self.db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",
                                (time.time(), kind, subject, old, new, source, json.dumps(detail) if detail else None))
                self.db.commit()
        except Exception as e:
            log.warning("events.db: %s %s not written (%s)", kind, subject, e)

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

    def last_user(self) -> float:
        """When somebody last asked the house for something, or 0. Nothing in a house is a better
        proxy for "is anyone up" than this: taps, sentences, scenes and settings all land here."""
        return self.db.execute("SELECT MAX(ts) FROM events WHERE source='user'").fetchone()[0] or 0.0

    def last_by_subject(self, kind, new) -> dict:
        """subject -> the last time it was logged reaching `new`. Rooms rebuild motion_at from this after a restart."""
        rows = self.db.execute("SELECT subject, MAX(ts) FROM events WHERE kind=? AND new=? GROUP BY subject", (kind, new)).fetchall()
        return dict(rows)
