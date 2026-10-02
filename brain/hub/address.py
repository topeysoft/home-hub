# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The house's own address -- temi.elyir.app -- and the switch that lets it be reached from outside.

The house is complete without any of this. Reaching it away from home goes through the maker's relay,
which is an optional service somebody pays for (docs/service.md), and this module is the hub's half of
that conversation: is a name free, take it, keep the secret it came with, and ask the host to bring the
tunnel up or down. design/address/ is what a household sees; docs/away.md, step 4, is the build.

The secret is the house's whole credential to the relay and the service shows it exactly once, in the
answer to the claim. It is kept in brain-data, beside the passcode's hash, so a backup restored onto new
hardware is still the same house to the relay. It never goes to the panel.

The brain never runs docker. Turning outside on or off is a file the host is watching (away.request),
naming a want from a fixed pair, beside away.env carrying the values; host/away.sh checks every one of
them again before it writes a line of .env -- the same arrangement restart.request has, for the same
reason. Nothing here is on the path of a tap, a light or the panel coming up: with the service down the
house is exactly as it is now.
"""
import json, logging, os, re, time, urllib.error, urllib.parse, urllib.request

from .settings import DATA

log = logging.getLogger("hub.address")

API = os.environ.get("HUB_RELAY_API") or "https://api.elyir.app"
STATE = DATA / "address.json"      # {"house", "secret", "relay": {"addr", "token"}, "zone", "claimed", "want"}
VALUES = DATA / "away.env"         # what host/away.sh writes into .env, checked again there
REQUEST = DATA / "away.request"    # the host's home-hub-away.path is watching for exactly this
DONE = DATA / "away.json"          # host/away.sh's answer: what it did and when
OFFER_EVERY, STATUS_EVERY = 600, 60

HOUSE = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,28}[a-z0-9])?$")
SECRET = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
HOST = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?$")


def first_guess(home: str | None) -> str:
    """The address the field starts with, from what the house was called in setup: Temi's house -> temi."""
    t = (home or "").strip().lower()
    t = re.sub(r"['’]s\b", "", t)
    t = re.sub(r"\b(the|house|home|place)\b", " ", t)
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:30].strip("-") or "home-hub"


class Unreachable(Exception):
    """The service did not answer. Said as a sentence, because it is the one failure a household can see."""


def _http(method: str, path: str, body: dict | None = None, secret: str | None = None, timeout: float = 8.0):
    req = urllib.request.Request(API.rstrip("/") + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "User-Agent": "home-hub",
                                          **({"Authorization": f"Bearer {secret}"} if secret else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:   # noqa: S310 -- API is ours, https, set by the maker
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read()
        try: return e.code, json.loads(raw) if raw else None
        except ValueError: return e.code, None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Unreachable("The address service is not answering right now. The house is fine; try again in a while.") from e


class Address:
    def __init__(self, hub, fetch=_http, now=time.time):
        self.hub, self.fetch, self.now = hub, fetch, now
        self._offer: tuple[float, dict] | None = None
        self._status: tuple[float, dict] | None = None

    # ---- what is kept ----
    def _state(self) -> dict:
        try: return json.loads(STATE.read_text()) if STATE.exists() else {}
        except ValueError: return {}

    def _save(self, state: dict):
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=1))
        os.chmod(tmp, 0o600)
        os.replace(tmp, STATE)

    # ---- what the panel may offer ----
    def offer(self) -> dict:
        """Whether to offer an address at all, at what price, and where it is paid for.

        Closed until the service says it is open -- an address nobody can pay for is a promise the house
        cannot keep. HUB_AWAY_OFFER=on is the maker's own hub, carried by hand before payments exist: the
        panel then offers it with no price and no payment page, and the house waits to be turned on.
        """
        if os.environ.get("HUB_AWAY_OFFER") == "on":
            return {"open": True, "price": None, "pay": None, "by_hand": True}
        if self._offer and self.now() - self._offer[0] < OFFER_EVERY: return self._offer[1]
        try: code, body = self.fetch("GET", "/offer")
        except Unreachable: return {"open": False, "price": None, "pay": None}
        out = {"open": bool(body and body.get("open")), "price": (body or {}).get("price"), "pay": (body or {}).get("pay")} if code == 200 else {"open": False, "price": None, "pay": None}
        self._offer = (self.now(), out)
        return out

    def hints(self) -> list[str]:
        """What the service may build suggestions from: the town, and the owner's name."""
        out = []
        place = (self.hub.location or {}).get("name") if getattr(self.hub, "location", None) else None
        if place: out.append(place.split(",")[0])
        owner = (self.hub.settings.get("owner") or {}).get("name")
        if owner: out.append(owner.split()[-1])
        return out

    def look(self, name: str) -> dict:
        code, body = self.fetch("GET", f"/names/{urllib.parse.quote(name.strip().lower(), safe='')}?" +
                                urllib.parse.urlencode([("also", h) for h in self.hints()]))
        if code != 200: raise Unreachable("The address service could not check that name just now.")
        return body

    # ---- taking one, and keeping it ----
    def claim(self, name: str, who: str = "the wall") -> dict:
        if self._state().get("house"): raise ValueError("This house already has an address.")
        code, body = self.fetch("POST", "/houses", {"name": name.strip().lower()})
        if code == 409: raise LookupError((body or {}).get("detail") or {"why": "taken", "suggestions": []})
        if code == 422: raise ValueError((body or {}).get("detail") or "That cannot be an address.")
        if code == 429: raise ValueError((body or {}).get("detail") or "Too many tries today. Try again tomorrow.")
        if code != 201 or not body: raise Unreachable("The address service could not take that name just now.")
        relay = body.get("relay") or {}
        state = {"house": body["name"], "secret": body["secret"], "zone": body["address"].split(".", 1)[1],
                 "relay": {"addr": relay.get("addr") or "", "token": relay.get("token") or ""}, "claimed": self.now(), "want": "on"}
        self._save(state)
        self._status = None
        self.hub.log.add("home", "address", None, "claimed", source="hub", detail={"address": body["address"], "who": who})
        self._ask_host("on", state)
        return self.summary()

    def status(self) -> dict:
        """What the service says about this house: carried or not, and until when. Cached for a minute."""
        s = self._state()
        if not s.get("house"): return {}
        if self._status and self.now() - self._status[0] < STATUS_EVERY: return self._status[1]
        try: code, body = self.fetch("GET", f"/houses/{s['house']}", secret=s["secret"])
        except Unreachable: return self._status[1] if self._status else {}
        out = {k: (body or {}).get(k) for k in ("carried", "held_until", "entitled_until")} if code == 200 else {"lost": True}
        relay = (body or {}).get("relay") or {}
        if code == 200 and relay and relay != s.get("relay"):
            s["relay"] = {"addr": relay.get("addr") or "", "token": relay.get("token") or ""}
            self._save(s)
            if s.get("want") == "on": self._ask_host("on", s)      # the relay moved or its token changed: follow it
        self._status = (self.now(), out)
        return out

    def turn(self, on: bool, who: str = "the wall") -> dict:
        s = self._state()
        if not s.get("house"): raise ValueError("This house has no address yet.")
        s["want"] = "on" if on else "off"
        self._save(s)
        self.hub.log.add("home", "address", None, "on" if on else "off", source="hub", detail={"who": who})
        self._ask_host(s["want"], s)
        return self.summary()

    def forget(self, who: str = "the wall") -> dict:
        """Give the name back. The house stops being reachable from outside and the name is anyone's."""
        s = self._state()
        if not s.get("house"): return self.summary()
        try: self.fetch("DELETE", f"/houses/{s['house']}", secret=s["secret"])
        except Unreachable: pass      # the service lets an unpaid name go on its own; forgetting here is what matters
        self._ask_host("forget", {})      # off, and the secret taken out of .env as well
        STATE.unlink(missing_ok=True)
        self._status = None
        self.hub.log.add("home", "address", None, "released", source="hub", detail={"who": who})
        return self.summary()

    def _ask_host(self, want: str, s: dict):
        """away.env with the values, then away.request with the want -- on, off, or forget. The host checks both again."""
        house, secret = s.get("house", ""), s.get("secret", "")
        relay = s.get("relay") or {}
        lines = {"HUB_AWAY_HOUSE": house, "HUB_RELAY_SECRET": secret, "HUB_RELAY_TOKEN": relay.get("token", ""),
                 "HUB_RELAY_ADDR": relay.get("addr", ""), "HUB_AWAY_ZONE": s.get("zone", "")}
        ok = HOUSE.match(house) and SECRET.match(secret) and SECRET.match(lines["HUB_RELAY_TOKEN"]) and HOST.match(lines["HUB_RELAY_ADDR"]) and HOST.match(lines["HUB_AWAY_ZONE"])
        if want == "on" and not ok:
            log.warning("not asking the host to turn outside on: the service's answer did not look right")
            return
        tmp = VALUES.with_suffix(".tmp")
        tmp.write_text("".join(f"{k}={v}\n" for k, v in lines.items()) if ok else "")
        os.chmod(tmp, 0o600)
        os.replace(tmp, VALUES)
        REQUEST.write_text(json.dumps({"at": self.now(), "want": want}))

    def public_origin(self) -> str | None:
        """https://<house>.<zone>, once the house has an address: the one origin allowed to call this hub across names."""
        st = self._state()
        return f"https://{st['house']}.{st['zone']}" if st.get("house") and st.get("zone") else None

    def lan_name(self) -> str | None:
        """The house's name at home, as host/away.sh last wrote it into .env -- read from the driver layer the brain
        can see, because away.sh writes it after the brain started and the brain's own environment would be stale."""
        if not self._state().get("house"): return None
        env = os.path.join(os.environ.get("HUB_DRIVER") or "/driver", ".env")
        try:
            with open(env) as f:
                for line in f:
                    if line.startswith("HUB_LAN_NAME="):
                        v = line.split("=", 1)[1].strip()
                        return v if HOST.match(v) and ".home." in v else None
        except OSError: return None
        return None

    # ---- what the panel shows ----
    def summary(self) -> dict:
        s = self._state()
        try: done = json.loads(DONE.read_text()) if DONE.exists() else {}
        except ValueError: done = {}
        out = {"offer": self.offer(), "guess": first_guess(self.hub.settings.get("home_name")), "house": s.get("house")}
        if s.get("house"):
            out |= {"address": f"{s['house']}.{s['zone']}", "want": s.get("want"), "on": done.get("on") is True and done.get("house") == s["house"],
                    "waiting": REQUEST.exists(), **self.status()}
        return out
