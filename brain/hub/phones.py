"""The phones that belong to the house.

Being on the Wi‑Fi gets a phone nothing on its own once the house has a code. A phone gets in one of
three ways: the person types the code on it; someone at a paired screen taps Allow (and types the code)
after the phone asks; or it is the screen that set the code during setup. Each phone holds a random
token in a cookie; the hub keeps only the hash, so removing a phone deletes the hash and the phone is
out, at once, with nothing on it worth keeping. Phones can be let in for a day or a weekend, and every
one starts home-only: reaching the house from outside is a separate promotion (the relay, when it
exists, checks `remote`). Without a code the house is open on the LAN, as it always was; the join
screen never appears, and setting a code is what turns the door on.
"""
import hashlib, json, os, secrets, time, uuid
from pathlib import Path

from .settings import DATA

COOKIE = "hub_phone"
ASK_TTL = 10 * 60          # an unanswered ask fades after ten minutes
SEEN_EVERY = 5 * 60        # last_seen is written at most this often
SPANS = {"day": 24 * 3600, "weekend": 3 * 24 * 3600, "keep": None}

# Which phones may decide who else gets in, by how they got in themselves.
#
# The screen that set the house up, and the phones whose owner typed the code on them. NOT a phone that
# was let in at a wall -- `how` is "wall" for those, meaning "admitted by somebody at a wall", and being
# admitted is not the same as being able to admit. That difference is the whole reason `how` is written
# down, and until now nothing read it: the code was the only thing between a phone let in for the
# afternoon and the door to the rest of the house.
#
# A second wall panel becomes one of these the way it already does -- somebody stands at it and types the
# code -- rather than by being let in from the first wall, which would make it a guest that happens to be
# screwed to a wall. `kind` is not consulted anywhere here on purpose: it is a guess from the user agent
# (api.py), so it can say whatever the phone holding it wants it to say.
KEYS = ("setup", "code")


def holds_keys(p: dict | None) -> bool:
    """May this phone hand out keys to the house, or only hold its own?"""
    return bool(p) and p.get("how") in KEYS


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class Phones:
    def __init__(self, hub, path: Path | None = None):
        self.hub = hub
        self.path = path or DATA / "phones.json"
        self.asks: dict[str, dict] = {}      # in memory: id -> {"id", "name", "asked", "token": str | None, "denied": bool, "expires"}
        try: self.data = json.loads(self.path.read_text()) if self.path.exists() else []
        except Exception: self.data = []

    # ---- the list ----
    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        os.replace(tmp, self.path)

    def _sweep(self):
        """Drop phones whose stay is over and asks nobody answered."""
        now = time.time()
        gone = [p for p in self.data if p.get("expires") and p["expires"] < now]
        if gone:
            self.data = [p for p in self.data if p not in gone]
            for p in gone: self.hub.log.add("phone", p["id"], None, "left", source="hub", detail={"name": p["name"], "why": "its stay was over"})
            self._save(); self._changed()
        for k, a in list(self.asks.items()):
            if now - a["asked"] > ASK_TTL and not a.get("token"): self.asks.pop(k, None)

    @staticmethod
    def _public(p: dict, me: dict | None = None) -> dict:
        return {k: p.get(k) for k in ("id", "name", "kind", "joined", "expires", "remote", "last_seen", "how")} | {"me": bool(me and me["id"] == p["id"])}

    def list(self, me: dict | None = None) -> dict:
        """What this phone may see. A phone that holds no keys sees itself and nothing else.

        Everyone in the house used to get the whole roster -- every name, how each one got in, when each
        was last seen, and who was knocking right now. That is the household and its visitors, handed to
        a phone let in for the afternoon. It is also what put the knock on their screen at all: the pane
        rises on whatever is in `asks`, so a guest with no asks has nothing to answer.
        """
        self._sweep()
        rows = sorted(self.data, key=lambda p: p.get("joined") or 0)
        if me and not holds_keys(me):
            return {"phones": [self._public(p, me) for p in rows if p["id"] == me["id"]], "asks": []}
        return {"phones": [self._public(p, me) for p in rows],
                "asks": [self._ask_public(a) for a in self.asks.values() if not a.get("token") and not a.get("denied")]}

    def get(self, phone_id: str) -> dict | None:
        return next((p for p in self.data if p["id"] == phone_id), None)

    def identify(self, token: str | None) -> dict | None:
        """The phone behind a cookie, or None. Touches last_seen now and then."""
        if not token: return None
        self._sweep()
        h = _hash(token)
        p = next((p for p in self.data if p.get("hash") == h), None)
        if not p: return None
        if time.time() - (p.get("last_seen") or 0) > SEEN_EVERY:
            p["last_seen"] = time.time(); self._save()
        return p

    # ---- getting in ----
    def _admit(self, name: str, kind: str, how: str, span: str | None = None) -> tuple[dict, str]:
        token = secrets.token_urlsafe(32)
        life = SPANS.get(span or "keep")
        p = {"id": uuid.uuid4().hex[:12], "name": name, "kind": kind, "joined": time.time(), "expires": (time.time() + life) if life else None,
             "remote": False, "last_seen": time.time(), "how": how, "hash": _hash(token)}
        self.data.append(p); self._save()
        self.hub.log.add("phone", p["id"], None, "joined", source="user", detail={"name": name, "how": how, "span": span or "keep"})
        self._changed()
        return p, token

    def with_code(self, name: str, kind: str = "phone") -> tuple[dict, str]:
        """The code was typed on the phone itself: it is the owner's, and it stays."""
        return self._admit(self._clean(name) or "A phone", kind, "code")

    def from_setup(self, kind: str = "wall") -> tuple[dict, str]:
        """The screen that set the code during setup is paired without asking; it is the wall."""
        return self._admit("This wall" if kind == "wall" else "The phone that set up the house", kind, "setup")

    def ask(self, name: str, kind: str = "phone") -> dict:
        """A phone on the Wi‑Fi asks to join. Nothing is issued until a paired screen allows it."""
        self._sweep()
        a = {"id": uuid.uuid4().hex[:12], "name": self._clean(name) or "A phone", "kind": kind, "asked": time.time(), "token": None, "denied": False, "expires": None}
        self.asks[a["id"]] = a
        self.hub.log.add("phone", a["id"], None, "asked", source="user", detail={"name": a["name"]})
        self._changed()
        return self._ask_public(a)

    def allow(self, ask_id: str, span: str = "keep") -> dict:
        a = self.asks.get(ask_id)
        if not a or a.get("token") or a.get("denied"): raise KeyError("That phone is no longer asking.")
        if span not in SPANS: raise ValueError("For today, for the weekend, or keep.")
        p, token = self._admit(a["name"], a.get("kind") or "phone", "wall", span)
        a["token"], a["phone"], a["allowed"] = token, p["id"], time.time()
        # _admit already said the phones changed, but it said it a line too early: the ask still had no
        # token then, so every screen was told the phone was in AND that it was still at the door. Say it
        # again now that the ask is answered, so the knock clears off the walls that did not answer it.
        self._changed()
        return self._public(p)

    def deny(self, ask_id: str):
        a = self.asks.pop(ask_id, None)
        if a: self.hub.log.add("phone", a["id"], None, "not now", source="user", detail={"name": a["name"]}); self._changed()

    def claim(self, ask_id: str) -> tuple[str, dict | None, str | None]:
        """The asking phone polls. ('waiting' | 'allowed' | 'gone', phone, token). The token is handed over once."""
        self._sweep()
        a = self.asks.get(ask_id)
        if not a or a.get("denied"): return "gone", None, None
        if not a.get("token"): return "waiting", None, None
        self.asks.pop(ask_id, None)
        return "allowed", self.get(a["phone"]), a["token"]

    # ---- leaving ----
    def remove(self, phone_id: str) -> bool:
        p = self.get(phone_id)
        if not p: return False
        self.data.remove(p); self._save()
        self.hub.log.add("phone", p["id"], None, "removed", source="user", detail={"name": p["name"]})
        self._changed()
        return True

    def set_remote(self, phone_id: str, remote: bool) -> dict:
        p = self.get(phone_id)
        if not p: raise KeyError("No such phone.")
        p["remote"] = bool(remote); self._save()
        self.hub.log.add("phone", p["id"], None, "can reach the house from outside" if remote else "home only", source="user", detail={"name": p["name"]})
        self._changed()
        return self._public(p)

    # ---- helpers ----
    @staticmethod
    def _clean(name: str) -> str:
        return " ".join((name or "").split())[:40]

    @staticmethod
    def _ask_public(a: dict) -> dict:
        return {"id": a["id"], "name": a["name"], "kind": a.get("kind"), "asked": a["asked"]}

    def _changed(self):
        """Tell the panels the phones changed -- and only that.

        This is one message to every open panel at once, so it cannot carry the roster: what a phone may
        see depends on which phone it is, and that is a question only `list` can answer, per request, with
        the cookie in hand. So the panels are nudged and each asks for its own answer.
        """
        try: self.hub._broadcast(json.dumps({"type": "phones"}))
        except Exception: pass


# ---- which requests a phone may make before it belongs ----
OPEN_PREFIXES = ("/phones/claim/", "/assets/", "/sounds/", "/icons/")
OPEN_PATHS = {"/", "/alive", "/phones/me", "/phones/ask", "/phones/code", "/qr.svg", "/phone", "/index.html", "/manifest.webmanifest", "/sw.js", "/favicon.ico", "/favicon.svg", "/robots.txt"}
OPEN_SUFFIXES = (".js", ".css", ".svg", ".png", ".ico", ".woff2", ".webmanifest", ".json", ".html", ".txt", ".map")


# ---- how a request reached the house ----
VIA, AWAY = "x-hub-via", "relay"


def from_away(headers) -> bool:
    """Did this request come in through the relay, rather than off the Wi-Fi?

    The front door stamps `X-Hub-Via: relay` on the one site the tunnel feeds and deletes any copy a
    client brought on every other site, so a phone on the Wi-Fi cannot claim to be away and a phone
    away cannot claim to be home. The relay itself never adds anything: it does not terminate TLS and
    could not stamp a header if it wanted to. With nothing in front of the brain at all -- a developer
    on :8300 -- nothing stamps it and every request is at home, which is the right answer there.

    Nothing is refused on the strength of this yet; step 2 in docs/away.md is the gate that reads it.
    """
    return (headers.get(VIA) or "").strip().lower() == AWAY


# ---- and what may pass from outside it ----
JOIN_AT_HOME = ("/phones/ask", "/phones/code", "/phones/claim/")
HOME_ONLY = "This phone works at home. Someone at the wall can let it out."
NOT_YOURS = "This house is not open from here."


def open_from_away(method: str, path: str) -> bool:
    """What passes from outside the house without a phone the house has let out.

    The app's own files, so it can load and say why it is not showing the house, and the one route that
    tells it which door it came in at. Never the way in: a stranger on the internet is not offered the
    question, and a phone is let out of the house from inside it or not at all.
    """
    if path.startswith(JOIN_AT_HOME): return False
    return open_to_strangers(method, path)


def away_refused(method: str, path: str, let_out: bool) -> bool:
    """Is this request from outside the house turned away?

    The way in is never open out there, not even to a phone the house has already let out: a phone joins
    the house from inside it, where somebody can see who is asking. Everything else comes down to whether
    this phone has been let out, and the app's own files pass either way so it can load and say so.
    """
    if path.startswith(JOIN_AT_HOME): return True
    return not let_out and not open_from_away(method, path)


def away_refusal(phone: dict | None, let_out: bool = False) -> dict:
    """The words a request from away is turned down with, and a key the app can act on.

    One of the house's own phones is told how that changes, because somebody at the wall can do it for
    them. Anybody else is told nothing they could act on: from outside the house the join screen does not
    exist, so there is nothing to offer and no house to name.
    """
    if let_out: return {"detail": "at-home", "message": "A phone joins the house from inside it."}
    return {"detail": "remote", "message": HOME_ONLY} if phone else {"detail": "away", "message": NOT_YOURS}


def open_to_strangers(method: str, path: str) -> bool:
    """What the panel needs before it is paired: the app itself, the join screen's own routes, and the sounds a speaker fetches."""
    if method.upper() in ("OPTIONS", "HEAD"): return True
    if path in OPEN_PATHS or path.startswith(OPEN_PREFIXES): return True
    return "." in path.rsplit("/", 1)[-1] and path.endswith(OPEN_SUFFIXES)
