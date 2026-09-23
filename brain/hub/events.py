# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Append-only event log. The assistant explains from this; nothing executes from it.

Two things arrived on 20 September 2026 and they pull in opposite directions, so the reasoning for
both lives here.

**It is bounded now.** It never was. A hub that had run a year held a year of every motion sensor in
the house in one file, on eMMC, and the file rode every backup. `prune()` keeps each kind for as
long as that kind is worth keeping (`KEEP`) and caps the whole thing at `CAP` rows. What makes that
safe is one rule, and it is the only interesting line in here: for the kinds in `KEEPERS`, **the
newest row for each (kind, subject, new) is never deleted, at any age**. That is exactly the row
`last_by_subject` returns, and two things in the house read it to answer "since when" -- how long a
thing has been offline (health.py) and when a room last saw motion (rules.seed). Without the rule a
prune would quietly reset those clocks and a device that went quiet in March would start claiming it
went quiet today.

`KEEPERS` is a short list rather than every kind, and the reason is `said`: its `new` is the sentence
somebody spoke, so sparing the newest row per value there would keep one row for every distinct
sentence ever said in the house, for good. The rule buys a clock nothing else can reconstruct, so it
is spent only where a clock is actually read.

**It records who.** `source` says what SORT of thing acted (`user`, `device`, `rule`, `hub`,
`system`, `assistant`, `comfort`); `who` says which one -- the name of the phone that asked, or the
wall. It is written for `source="user"` and nothing else. A rule firing has no who; neither does a
background job that a request happened to start, and that second case is the reason the rule exists
rather than being a nicety: a task spawned mid-request inherits the request's context and outlives
it, so attributing its writes to whoever last tapped something would put a name to work they did not
do. In an audit trail a plausible guess is worse than a blank. A house with no code cannot tell its
phones apart at all, so `who` stays null there and the panel says so rather than inventing one.
"""
import logging, sqlite3, time, json, threading
from contextvars import ContextVar

log = logging.getLogger(__name__)

# Who is asking, for the length of one request. api.py's middleware sets it once it knows which phone
# came in, and `add` reads it, so that 75 call sites did not have to grow an argument they would
# forget. A ContextVar and not a global because a hub answers several phones at once.
asked_by: ContextVar[str | None] = ContextVar("asked_by", default=None)

DAY = 86400
# How long each kind is worth keeping. Device chatter is the overwhelming majority of the rows and
# nothing reads it after a month; what the house IS -- who joined, what was renamed, which account
# was removed -- is the audit trail, and a year is the least that can answer "when did that phone get
# in?". An unlisted kind keeps the long time ON PURPOSE: a kind added next year is far likelier to be
# house news than chatter, and keeping too much is the smaller mistake.
KEEP = {"state": 30, "action": 30,
        "intent": 180, "held": 180, "shadowed": 180, "failed": 180,
        "presence": 180, "comfort": 180, "said": 180, "ask": 180,
        "notify": 180, "proposal": 180}
A_YEAR = 365
# The kinds something reads a clock from, and so the kinds whose newest row per value outlives its
# keeping. `state` answers "offline since when" (health.py) and "when did this room last move"
# (rules.seed); `presence` is how the house remembers, after a restart, when everybody left.
KEEPERS = ("state", "presence")
CAP = 500_000       # a backstop, not the plan: a house writing this much in 30 days has something wrong


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
        # Only a database with no tables yet can be told to keep its free pages tidy, so a new hub
        # gets it and every hub already in the field does not. That is a smaller difference than it
        # sounds: SQLite reuses freed pages either way, so a pruned file plateaus rather than growing.
        # Incremental vacuum only means a new hub also gives the space back. VACUUM proper is never
        # run here -- it rewrites the whole file under an exclusive lock, which on eMMC is exactly the
        # wear this prune exists to avoid.
        fresh = not self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone()
        if fresh:
            try: self.db.execute("PRAGMA auto_vacuum=INCREMENTAL")
            except sqlite3.Error: pass
        self.db.execute("""CREATE TABLE IF NOT EXISTS events(
            ts REAL, kind TEXT, subject TEXT, old TEXT, new TEXT, source TEXT, detail TEXT, who TEXT)""")
        # Every hub in the field has the seven-column table. Adding the column is the whole migration;
        # the rows that predate it say null, which is the truth about them.
        if not any(r[1] == "who" for r in self.db.execute("PRAGMA table_info(events)")):
            try: self.db.execute("ALTER TABLE events ADD COLUMN who TEXT")
            except sqlite3.Error as e: log.warning("events.db: could not add `who` (%s)", e)
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_ts ON events(ts)")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_source_ts ON events(source, ts)")
        self.db.execute("CREATE INDEX IF NOT EXISTS ix_kind_ts ON events(kind, ts)")

    def add(self, kind, subject, old=None, new=None, source="device", detail=None, who=None):
        """Write one line down. NEVER raises.

        This is a diary, and 75 places in the house call it -- mid-job, mid-request, inside a
        `try` that belongs to something else entirely. A bridge had its firmware written, its Wi-Fi
        configured and its keys handed over, and then failed with "database is locked" on the
        screen, because the line saying so could not be written. Losing a line of the diary is not
        losing the thing it was about, and it must never be able to say otherwise.
        """
        try:
            # Only a person has a name worth writing; see the module docstring for why that is a rule
            # and not a shortcut. An explicit `who` still wins, for the few places that know better
            # than the request does (the host installing an update overnight, say).
            if who is None and source == "user": who = asked_by.get()
            with self.lock:
                self.db.execute(
                    "INSERT INTO events(ts,kind,subject,old,new,source,detail,who) VALUES(?,?,?,?,?,?,?,?)",
                    (time.time(), kind, subject, old, new, source,
                     json.dumps(detail) if detail else None, who))
                self.db.commit()
        except Exception as e:
            log.warning("events.db: %s %s not written (%s)", kind, subject, e)

    def recent(self, limit=100, subject=None, kinds=None, since=None, until=None, sources=None):
        """Newest first. `subject` is one id or a tuple of them; `kinds` a tuple of event kinds.

        `since`/`until` are the window, in epoch seconds, and they are what makes a question like
        "what happened between leaving and coming back" answerable at all: without them the only way
        to reach yesterday was to pull thousands of rows and throw most of them away.
        """
        q = "SELECT ts,kind,subject,old,new,source,detail,who FROM events"
        where, args = [], ()
        if isinstance(subject, (tuple, list, set)):
            subject = tuple(subject); where.append(f"subject IN ({','.join('?' * len(subject))})"); args += subject
        elif subject: where.append("subject=?"); args += (subject,)
        if kinds: where.append(f"kind IN ({','.join('?' * len(kinds))})"); args += tuple(kinds)
        if sources: where.append(f"source IN ({','.join('?' * len(sources))})"); args += tuple(sources)
        if since is not None: where.append("ts>=?"); args += (since,)
        if until is not None: where.append("ts<?"); args += (until,)
        if where: q += " WHERE " + " AND ".join(where)
        q += " ORDER BY ts DESC LIMIT ?"
        rows = self.db.execute(q, args + (limit,)).fetchall()
        return [dict(zip(("ts", "kind", "subject", "old", "new", "source", "detail", "who"), r)) for r in rows]

    def last_user(self) -> float:
        """When somebody last asked the house for something, or 0. Nothing in a house is a better
        proxy for "is anyone up" than this: taps, sentences, scenes and settings all land here."""
        return self.db.execute("SELECT MAX(ts) FROM events WHERE source='user'").fetchone()[0] or 0.0

    def last_by_subject(self, kind, new) -> dict:
        """subject -> the last time it was logged reaching `new`. Rooms rebuild motion_at from this after a restart.

        `prune` is built around this query: whatever it would return today it still returns after any
        prune, however old the row. See the module docstring.
        """
        rows = self.db.execute("SELECT subject, MAX(ts) FROM events WHERE kind=? AND new=? GROUP BY subject", (kind, new)).fetchall()
        return dict(rows)

    # ---- keeping it a diary rather than an archive ----
    # The f-strings here and in prune() interpolate a row of `?` and nothing else -- every value
    # still arrives as a bound parameter -- which is why S608 is answered rather than obeyed.
    KEEPERS_SQL = ("SELECT MAX(rowid) FROM events WHERE kind IN "  # noqa: S608
                   f"({','.join('?' * len(KEEPERS))}) GROUP BY kind, subject, new")

    def prune(self, now=None) -> int:
        """Drop what is past its keeping. Returns how many rows went. NEVER raises, for add()'s reasons."""
        now = now or time.time()
        gone = 0
        try:
            with self.lock:
                for (kind,) in self.db.execute("SELECT DISTINCT kind FROM events").fetchall():
                    cutoff = now - KEEP.get(kind, A_YEAR) * DAY
                    if kind in KEEPERS:
                        cur = self.db.execute(
                            "DELETE FROM events WHERE kind=? AND ts<? AND rowid NOT IN "
                            "(SELECT MAX(rowid) FROM events WHERE kind=? GROUP BY subject, new)",
                            (kind, cutoff, kind))
                    else:
                        cur = self.db.execute("DELETE FROM events WHERE kind=? AND ts<?", (kind, cutoff))
                    gone += cur.rowcount
                # The backstop, oldest first. It is not expected to fire: a house that reaches it
                # inside one keeping window is writing something it should not be writing, and the
                # cap is there so that finding out costs a slow panel rather than a full disk.
                over = self.db.execute("SELECT COUNT(*) FROM events").fetchone()[0] - CAP
                if over > 0:
                    cur = self.db.execute(
                        f"DELETE FROM events WHERE rowid IN (SELECT rowid FROM events "  # noqa: S608
                        f"WHERE rowid NOT IN ({self.KEEPERS_SQL}) ORDER BY ts LIMIT ?)",
                        tuple(KEEPERS) + (over,))
                    gone += cur.rowcount
                self.db.commit()
                if gone:
                    # Only does anything on a hub new enough to have been born with it; harmless elsewhere.
                    try: self.db.execute("PRAGMA incremental_vacuum")
                    except sqlite3.Error: pass
        except Exception as e:
            log.warning("events.db: could not prune (%s)", e)
            return gone
        if gone: log.info("events.db: %d rows pruned", gone)
        return gone

    async def run(self):
        """Once a day, and once shortly after a start. The first prune on a hub that has been
        running a year is the big one, and it should not wait for the small ones."""
        import asyncio
        await asyncio.sleep(120)
        while True:
            try: self.prune()
            except Exception: log.exception("prune")
            await asyncio.sleep(DAY)
