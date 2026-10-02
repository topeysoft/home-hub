# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which houses the relay will carry, and under what name.

A house claims a name -- temi, for temi.elyir.app -- and is handed a secret once, in the answer to the
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
"""
import hashlib, hmac, re, secrets, sqlite3, time
from pathlib import Path

DAY = 24 * 3600
HOLD = DAY                       # a claim nobody pays for is let go after this
ALWAYS = 4102444800.0            # 2100: "always", as a number JSON can carry
LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,28}[a-z0-9])?$")

# Names a house may never have. The service's own (api), the maker's (www, mail, status), the zone's
# future (home is the subzone the address-in-the-name lives under, docs/away.md), and the ones a
# phishing page would want. Short names are not reserved for being short; a two-letter house is fine.
RESERVED = frozenset("""
    api relay www mail smtp imap pop ftp ns ns1 ns2 dns home lan local localhost admin root operator
    status help support billing pay account accounts login signin auth app apps elyir hub hubs test
    selftest staging dev _acme-challenge
""".split())

SCHEMA = """
create table if not exists houses (
    name            text primary key,
    secret_hash     text not null,
    claimed         real not null,
    held_until      real,             -- unpaid claims are let go after this; null once entitled
    entitled_until  real,             -- carried while this is in the future
    note            text not null default ''
)"""


def _hash(secret: str) -> str:
    # The secret is 32 random bytes, not something a person chose, so a fast hash is the right one:
    # there is nothing to guess and nothing a slow hash would protect.
    return hashlib.sha256(secret.encode()).hexdigest()


def problem(label: str) -> str | None:
    """Why a name cannot be a house's, in words the hub can show -- or None if it can."""
    if not label: return "A name is needed."
    if len(label) > 30: return "That is longer than 30 letters."
    if not LABEL.match(label): return "Letters, numbers and dashes only, not starting or ending with a dash."
    if label in RESERVED: return "That one is kept for the service itself."
    return None


def clean(text: str) -> str:
    """What somebody typed, as the name it would become: Temi's House -> temis-house."""
    t = re.sub(r"['’]", "", text.strip().lower())
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:30].strip("-")


class Registry:
    def __init__(self, path: Path | str, zone: str = "elyir.app", now=time.time):
        self.zone, self.now = zone, now
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("pragma journal_mode=wal")
        self.db.execute(SCHEMA)

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

    def claim(self, label: str) -> dict:
        """Take a name for a house. The secret is in this answer and nowhere else, ever."""
        label = label.strip().lower()
        why = problem(label)
        if why: raise ValueError(why)
        self._sweep()
        secret = secrets.token_urlsafe(32)
        try:
            self.db.execute("insert into houses (name, secret_hash, claimed, held_until) values (?, ?, ?, ?)",
                            (label, _hash(secret), self.now(), self.now() + HOLD))
        except sqlite3.IntegrityError:
            raise LookupError("taken") from None
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
            return None
        if op == "NewProxy":
            if content.get("proxy_type") != "https": return "only https is carried"
            if list(content.get("custom_domains") or []) != [f"{house}.{self.zone}"]: return "a house is carried only under its own name"
            if content.get("subdomain"): return "a house is carried only under its own name"
            return None
        return None
