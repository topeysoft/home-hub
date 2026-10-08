# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which houses the relay will carry, and under what name.

A house claims a name -- jordan, for jordan.elyir.app -- and is handed a secret once, in the answer to the
claim. That secret is the house's whole credential: it goes in the hub's frpc.toml, frps passes it here
on every login, and this decides whether to carry the house at all. Only its hash is kept, so the file
this writes could leak without letting anyone dial in as a house.

A secret rather than the signed calls docs/away.md first imagined, and for a reason found by trying it:
frps hands a plugin the client's metadata as frpc read it from its config at start, so nothing a hub
sends at login can be fresh. A signature over a timestamp written once into a file is a bearer token
with extra steps. So it is a bearer token, plainly, carried inside frpc's own TLS.

Being carried needs an entitlement: the relay is an optional paid service (docs/service.md), and a name
costs something, which is also what keeps a thousand of them from being squatted. Until payments exist,
the operator grants entitlements by hand (cli.py), and a name claimed without one is held for a day and
then let go. Nothing here touches DNS: every house is already covered by the zone's one wildcard.

An invite is a grant made ahead of time: the operator mints a code (cli.py invite), hands it to somebody,
and the house that brings it is carried the moment it does -- with its claim, or any time after on a name
it already holds. It is the flash-time token docs/service.md keeps for boxes that were bought, minted by
hand for testers until then. One use each, kept only as a hash like the secrets.
"""
import hashlib, hmac, re, secrets, sqlite3, threading, time
from contextlib import contextmanager
from pathlib import Path

DAY = 24 * 3600
HOLD = DAY                       # a claim nobody pays for is let go after this
ALWAYS = 4102444800.0            # 2100: "always", as a number JSON can carry
LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,28}[a-z0-9])?$")
INVITE_KEEP = 30 * DAY           # an invite nobody used by then is no good
# Crockford's letters without the ones a person misreads (0 O 1 I L U): twelve of them is ~59 bits, read
# aloud or typed off a phone, and nobody guesses one at five claims a day.
INVITE_LETTERS = "23456789ABCDEFGHJKMNPQRSTVWXYZ"

# Names a house may never have. The service's own (api), the maker's (www, mail, status), the zone's
# future (home is the subzone the address-in-the-name lives under, docs/away.md), and the ones a
# phishing page would want. Short names are not reserved for being short; a two-letter house is fine.
# The apps this box serves are on the list too (printers, houses), and so is nearby: a house that held
# one of those names would be handed every phone that came looking for the app. Being here also keeps
# them off /nearby, which is a list of houses and printers rather than of the service's own names.
RESERVED = frozenset("""
    api relay www mail smtp imap pop ftp ns ns1 ns2 dns home lan local localhost admin root operator
    status help support billing pay account accounts login signin auth app apps elyir hub hubs test
    selftest staging dev _acme-challenge printers nearby houses
""".split())

SCHEMA = """
create table if not exists houses (
    name            text primary key,
    secret_hash     text not null,
    claimed         real not null,
    held_until      real,             -- unpaid claims are let go after this; null once entitled
    entitled_until  real,             -- carried while this is in the future
    note            text not null default ''
);
create table if not exists invites (
    code_hash       text primary key,
    hint            text not null,    -- its last four letters, so the operator can tell codes apart
    made            real not null,
    use_by          real not null,    -- no good after this
    until           real not null,    -- the house that brings it is carried until then
    note            text not null default '',
    used_by         text,
    used_at         real
)"""


def _hash(secret: str) -> str:
    # The secret is 32 random bytes, not something a person chose, so a fast hash is the right one:
    # there is nothing to guess and nothing a slow hash would protect.
    return hashlib.sha256(secret.encode()).hexdigest()


def invite_code(raw: str) -> str:
    """What somebody typed, as the code it means: k7qx m2pd-9htf -> K7QXM2PD9HTF."""
    return re.sub(r"[^A-Z0-9]", "", (raw or "").upper())


def problem(label: str) -> str | None:
    """Why a name cannot be a house's, in words the hub can show -- or None if it can."""
    if not label: return "A name is needed."
    if len(label) > 30: return "That is longer than 30 letters."
    if not LABEL.match(label): return "Letters, numbers and dashes only, not starting or ending with a dash."
    if label in RESERVED: return "That one is kept for the service itself."
    return None


def clean(text: str) -> str:
    """What somebody typed, as the name it would become: Jordan's House -> jordans-house."""
    t = re.sub(r"['’]", "", text.strip().lower())
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:30].strip("-")


class Registry:
    def __init__(self, path: Path | str, zone: str = "elyir.app", now=time.time):
        self.zone, self.now = zone, now
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.lock = threading.RLock()    # one connection, many request threads: one transaction at a time
        self.db.execute("pragma journal_mode=wal")
        self.db.executescript(SCHEMA)
        # Where each house's tunnel last came from, for /nearby. Added 2 October 2026 to a file that
        # already had houses in it, so added rather than declared.
        for col in ("last_ip text", "seen_at real"):
            try: self.db.execute(f"alter table houses add column {col}")
            except sqlite3.OperationalError: pass

    # ---- the names ----
    def _sweep(self):
        """Let go of claims whose day is up and nobody paid for."""
        self.db.execute("delete from houses where entitled_until is null and held_until < ?", (self.now(),))

    def taken(self, label: str) -> bool:
        self._sweep()
        return self.db.execute("select 1 from houses where name = ?", (label,)).fetchone() is not None

    def suggest(self, label: str, hints: list[str] = (), n: int = 3) -> list[str]:
        """Free names near one that is not: the house's, with -house, its town or surname, then a number."""
        base = clean(label)
        tried = [f"{base}s-house", f"{base}-house", *(f"{base}-{clean(h)}" for h in hints if clean(h)),
                 *(f"{clean(h)}-home" for h in hints if clean(h)), f"{base}-home",
                 *(f"{base}{i}" for i in range(2, 30))]
        out = []
        for t in dict.fromkeys(tried):
            if t != base and not problem(t) and not self.taken(t): out.append(t)
            if len(out) == n: break
        return out

    def look(self, label: str, hints: list[str] = ()) -> dict:
        """What the hub's name field says as somebody types."""
        label = label.strip().lower()
        why = problem(label)
        if why: return {"name": label, "free": False, "why": why, "suggestions": self.suggest(label, hints) if clean(label) else []}
        if self.taken(label): return {"name": label, "free": False, "why": "taken", "suggestions": self.suggest(label, hints)}
        return {"name": label, "free": True, "address": f"{label}.{self.zone}"}

    @contextmanager
    def _together(self):
        """One transaction: a claim that brings an invite is both or neither."""
        with self.lock:
            self.db.execute("begin immediate")
            try: yield
            except BaseException:
                self.db.execute("rollback"); raise
            self.db.execute("commit")

    def claim(self, label: str, invite: str | None = None) -> dict:
        """Take a name for a house. The secret is in this answer and nowhere else, ever. With an invite the
        house is carried at once; a code that is no good refuses the whole claim (PermissionError), so a
        mistyped one costs nothing and the house can ask again with or without it."""
        label = label.strip().lower()
        why = problem(label)
        if why: raise ValueError(why)
        self._sweep()
        secret = secrets.token_urlsafe(32)
        with self._together():
            if invite is not None:
                bad = self.invite_problem(invite)
                if bad: raise PermissionError(bad)
            try:
                self.db.execute("insert into houses (name, secret_hash, claimed, held_until) values (?, ?, ?, ?)",
                                (label, _hash(secret), self.now(), self.now() + HOLD))
            except sqlite3.IntegrityError:
                raise LookupError("taken") from None
            if invite is not None: self._redeem(label, invite)
        return {"name": label, "address": f"{label}.{self.zone}", "secret": secret, **self.status(label)}

    def _row(self, label: str):
        self._sweep()
        return self.db.execute("select * from houses where name = ?", (label,)).fetchone()

    def status(self, label: str) -> dict:
        r = self._row(label)
        if not r: return {"carried": False, "held_until": None, "entitled_until": None}
        return {"carried": bool(r["entitled_until"] and r["entitled_until"] > self.now()),
                "held_until": r["held_until"], "entitled_until": r["entitled_until"]}

    def holder(self, label: str, secret: str) -> bool:
        """Is this the house that claimed the name? Constant time, so a wrong guess teaches nothing."""
        r = self._row(label) if label and secret else None
        return bool(r) and hmac.compare_digest(r["secret_hash"], _hash(secret))

    def release(self, label: str):
        self.db.execute("delete from houses where name = ?", (label,))

    # ---- the operator's side, until payments do it ----
    def grant(self, label: str, until: float, note: str = ""):
        """Carry this house until then. The name stops being a mere hold and is the house's."""
        n = self.db.execute("update houses set entitled_until = ?, held_until = null, note = ? where name = ?",
                            (until, note, label)).rowcount
        if not n: raise LookupError(label)

    def seed(self, label: str, secret: str, note: str = "the service itself"):
        """A name that is always carried, with a secret the operator chose: the service's own api name."""
        self.db.execute("insert into houses (name, secret_hash, claimed, held_until, entitled_until, note) values (?, ?, ?, null, ?, ?) "
                        "on conflict(name) do update set secret_hash = excluded.secret_hash, entitled_until = excluded.entitled_until, held_until = null",
                        (label, _hash(secret), self.now(), ALWAYS, note))

    def rotate(self, label: str) -> str:
        """A new secret for a house that lost its own. The old one stops working at once."""
        secret = secrets.token_urlsafe(32)
        if not self.db.execute("update houses set secret_hash = ? where name = ?", (_hash(secret), label)).rowcount:
            raise LookupError(label)
        return secret

    # ---- invites: a grant made ahead of time ----
    def invite(self, until: float, note: str = "", keep: float = INVITE_KEEP) -> str:
        """A code that carries whichever house brings it until `until`. Shown once, here; only its hash is kept."""
        code = "".join(secrets.choice(INVITE_LETTERS) for _ in range(12))
        self.db.execute("insert into invites (code_hash, hint, made, use_by, until, note) values (?, ?, ?, ?, ?, ?)",
                        (_hash(code), code[-4:], self.now(), self.now() + keep, until, note))
        return "-".join(code[i:i + 4] for i in (0, 4, 8))

    def _invite_row(self, code: str):
        return self.db.execute("select * from invites where code_hash = ?", (_hash(invite_code(code)),)).fetchone()

    def invite_problem(self, code: str) -> str | None:
        """Why this code carries nobody, in words the printer or hub can show -- or None if it would."""
        r = self._invite_row(code)
        if not r: return "That invite code isn't one of ours. Check it for a typo."
        if r["used_by"]: return "That invite code was used already."
        if r["use_by"] < self.now(): return "That invite code ran out. Ask for a new one."
        return None

    def _redeem(self, label: str, code: str):
        r = self._invite_row(code)
        house = self._row(label)
        if not house: raise LookupError(label)
        if (house["entitled_until"] or 0) >= r["until"]:
            raise PermissionError("This name is carried that long already, so the code was kept for somebody else.")
        if not self.db.execute("update invites set used_by = ?, used_at = ? where code_hash = ? and used_by is null",
                               (label, self.now(), r["code_hash"])).rowcount:
            raise PermissionError("That invite code was used already.")
        self.grant(label, r["until"], f"invite {r['hint']}: {r['note']}".rstrip(": "))

    def redeem(self, label: str, code: str):
        """Bring an invite to a name the house already holds: the tester who set up first and got a code after."""
        with self._together():
            bad = self.invite_problem(code)
            if bad: raise PermissionError(bad)
            self._redeem(label, code)

    def invites(self) -> list[dict]:
        return [dict(r) | {"code_hash": None} for r in self.db.execute("select * from invites order by made")]

    def uninvite(self, hint: str):
        """Take back an unused code, by the four letters the list shows."""
        if not self.db.execute("delete from invites where hint = ? and used_by is null", (invite_code(hint),)).rowcount:
            raise LookupError(hint)

    # ---- who is in the same house as whom ----
    def seen(self, label: str, address: str):
        """Note the public address a house's tunnel came from, for /nearby. "1.2.3.4:5678" or "[::1]:5678"."""
        host = address.rsplit(":", 1)[0].strip("[]") if address else ""
        self.db.execute("update houses set last_ip = ?, seen_at = ? where name = ?", (host or None, self.now(), label))

    def nearby(self, address: str) -> list[str]:
        """The carried names whose tunnel comes from this public address: the printers (and hubs) behind the
        same router as whoever is asking. Names only. Behind a shared address (carrier NAT, an office) a
        neighbor's names show too, which is why a name is all this ever gives: connecting to any of them
        still means asking from that house's own Wi-Fi."""
        if not address: return []
        rows = self.db.execute("select name from houses where last_ip = ? and entitled_until > ? order by name",
                               (address, self.now())).fetchall()
        return [r["name"] for r in rows if r["name"] not in RESERVED]

    def houses(self) -> list[dict]:
        self._sweep()
        return [dict(r) | {"secret_hash": None} for r in self.db.execute("select * from houses order by name")]

    # ---- the relay asking ----
    def judge(self, op: str, content: dict) -> str | None:
        """frps's question, from its server plugin: carry this? None is yes; a string is why not.

        Login: the house names itself in metadata and proves it with its secret, and frps's own `user`
        must be the same name -- frps prefixes every proxy name with it, which is what keeps one house's
        proxies from being mistaken for another's. NewProxy: the same proof again (frps passes the login's
        metadata through), and the only thing a house may ask to be carried for is its own name, as raw
        https. Anything else -- another house's name, a second name, a plain tcp port -- is refused.
        """
        meta = (content.get("user") or {}).get("metas") if op == "NewProxy" else content.get("metas")
        meta = meta or {}
        house, secret = str(meta.get("house") or ""), str(meta.get("secret") or "")
        if not self.holder(house, secret): return "this house is not known here"
        if not self.status(house)["carried"]: return "this house is not carried by this relay"
        if op == "Login":
            if content.get("user") != house: return "user must be the house's name"
            self.seen(house, str(content.get("client_address") or ""))
            return None
        if op == "NewProxy":
            if content.get("proxy_type") != "https": return "only https is carried"
            if list(content.get("custom_domains") or []) != [f"{house}.{self.zone}"]: return "a house is carried only under its own name"
            if content.get("subdomain"): return "a house is carried only under its own name"
            return None
        return None
