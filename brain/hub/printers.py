# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""3D printers in the house: found on the Wi-Fi, let in at the printer, and followed. docs/printers.md.

A printer here is anything that speaks a printer door's small public protocol: `/door/me` says it is a
printer and where it lives, `/door/ask` asks to be let in and somebody at the printer says yes, and a
token then opens Moonraker's websocket behind it. The hub knows printers; a printer never knows the hub,
and nothing here imports a line of the printer's own software. The printer keeps telling its own phones
what it tells them; the hub adds the wall, the house's log and its "Needs a look".

WORKS WITH THE INTERNET DOWN, once a printer is in. Its name at home spells its LAN address --
192-168-86-73.obi1.home.elyir.app -- so the hub connects to that address straight and checks the
certificate against the name: no DNS, no relay. Finding a printer the first time asks the relay which
printers share the house's public address, which does need the internet; that is a convenience, not a
path anything else depends on.

What the hub may do to a printer is the short list a phone away may do (pause, resume, stop, cool down,
switch spools, "later"), wherever the asker is. The printer would let the hub do more -- it is at home --
but a wall in the kitchen is not somebody standing at the printer, which is what starting a print or
saying the bed is clear needs.
"""
import asyncio, http.client, ipaddress, json, logging, os, re, socket, ssl, time

from .settings import DATA

log = logging.getLogger("hub.printers")

STATE = DATA / "printers.json"      # {"printers": {id: {"name", "away", "home", "token", "phone", "added"}}}, 0600
NEARBY = "https://nearby.elyir.app/nearby"   # which printers share the house's public address (relay/README.md)
ZONE = "elyir.app"
LOOK_EVERY = 300                    # how often the hub asks which printers are on the Wi-Fi
ASK_FOR = 130                       # an ask lasts 120 s at the printer; give up a little after
ACTIONS = {"pause", "resume", "cancel", "cool_down", "swap_slot", "dismiss_swap", "care_later", "help"}
NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,28}[a-z0-9])?$")
PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]


def lan_address(home: str | None) -> str | None:
    """https://192-168-86-73.obi1.home.elyir.app -> 192.168.86.73, and only an address inside a house."""
    host = (home or "").split("://", 1)[-1].split("/", 1)[0]
    m = re.match(r"^(\d{1,3})-(\d{1,3})-(\d{1,3})-(\d{1,3})\.", host)
    if not m:
        return None
    try:
        ip = ipaddress.ip_address(".".join(m.groups()))
    except ValueError:
        return None
    return str(ip) if any(ip in n for n in PRIVATE) else None


def host_of(url: str) -> str:
    return url.split("://", 1)[-1].split("/", 1)[0]


def https(method: str, url: str, body=None, headers=None, timeout=10.0, stream=False):
    """One HTTPS request. A printer's name at home goes straight to the address it spells, with the
    certificate still checked against the name; anything else resolves the ordinary way. Returns
    (status, headers, bytes) -- or, with stream, (status, headers, response) for the caller to read."""
    host, _, path = url.split("://", 1)[-1].partition("/")
    path = "/" + path
    ctx = ssl.create_default_context()
    ip = lan_address(url)
    conn = http.client.HTTPSConnection(host, 443, timeout=timeout, context=ctx)
    if ip:
        raw = socket.create_connection((ip, 443), timeout=timeout)
        conn.sock = ctx.wrap_socket(raw, server_hostname=host)
    data = json.dumps(body).encode() if body is not None else None
    h = {"Accept": "application/json", **({"Content-Type": "application/json"} if data else {}), **(headers or {})}
    conn.request(method, path, body=data, headers=h)
    r = conn.getresponse()
    if stream:
        return r.status, dict(r.getheaders()), r
    out = r.read()
    conn.close()
    return r.status, dict(r.getheaders()), out


def as_json(raw: bytes):
    try:
        return json.loads(raw.decode() or "null")
    except ValueError:
        return None


class Printers:
    def __init__(self, hub, request=https, connect=None, now=time.time):
        self.hub, self.request, self.now = hub, request, now
        self.connect = connect or self._connect
        try:
            self.known: dict = json.loads(STATE.read_text()).get("printers", {})
        except (OSError, ValueError):
            self.known = {}
        self.live: dict = {}         # id -> {"intent", "connected", "via", "since"}
        self.found: list = []        # [{"id", "name", "home", "away"}] on the Wi-Fi and not yet in
        self.asking: dict = {}       # id -> "waiting" | "refused" | "expired" | "failed"
        self.links: dict = {}        # id -> the task following it
        self.sockets: dict = {}      # id -> the open websocket, for actions
        self._calls: dict = {}
        self._ids = iter(range(1, 1 << 62))

    # ---- keeping ----
    def _save(self):
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"printers": self.known}, indent=1))
        os.chmod(tmp, 0o600)
        os.replace(tmp, STATE)

    def _changed(self):
        self.hub._broadcast(json.dumps({"type": "printers", "printers": self.status()}))

    # ---- what the panel sees ----
    def view(self, pid: str) -> dict:
        p, live = self.known[pid], self.live.get(pid) or {}
        it = live.get("intent") or {}
        job, printer = it.get("job") or None, it.get("printer") or {}
        out = {"id": pid, "name": p["name"], "connected": bool(live.get("connected")), "via": live.get("via"),
               "state": it.get("state"), "headline": it.get("headline"), "detail": it.get("detail"),
               "actions": [a for a in it.get("actions") or [] if a.get("id") in ACTIONS],
               "temps": {k: (printer.get(k) or {}).get("temperature") for k in ("nozzle", "bed", "chamber") if printer.get(k)},
               "camera": f"/printers/{pid}/camera", "job": None}
        if job:
            out["job"] = {k: job.get(k) for k in ("name", "progress", "layer", "layers", "remaining_s", "eta_clock", "colors", "material")}
            out["job"]["thumbnail"] = f"/printers/{pid}/thumbnail" if job.get("thumbnail") else None
        return out

    def status(self) -> dict:
        return {"printers": [self.view(pid) for pid in sorted(self.known)],
                "found": [f for f in self.found if f["id"] not in self.known],
                "asking": dict(self.asking)}

    def notes(self) -> list:
        """A printer that needs somebody, for "Needs a look": its own words, never ours."""
        out = []
        for pid in sorted(self.known):
            v = self.view(pid)
            if v["state"] in ("needs_you", "problem"):
                out.append({"kind": "printer", "subject": pid, "since": self.live[pid].get("since"),
                            "where": "printer", "name": v["name"], "text": v["headline"] or "", "detail": v["detail"],
                            "acts": [{"do": "open", "act": "printer", "to": pid}]})
        return out

    # ---- finding ----
    async def look(self) -> list:
        """Which printers share the house's public address, by the relay; then each one's own word that it is
        a printer. A hub, or anything else on the list, says otherwise and is left out."""
        try:
            st, _, raw = await asyncio.to_thread(self.request, "GET", NEARBY)
            names = (as_json(raw) or {}).get("names", []) if st == 200 else []
        except Exception as e:
            log.info("printers: could not ask who is nearby: %s", e)
            return self.found
        found = []
        for name in names:
            if not NAME.match(str(name)) or name in self.known:
                continue
            try:
                st, _, raw = await asyncio.to_thread(self.request, "GET", f"https://{name}.{ZONE}/door/me", None, None, 5.0)
            except Exception:
                continue
            me = as_json(raw) if st == 200 else None
            if isinstance(me, dict) and isinstance(me.get("printer"), dict) and (me.get("addresses") or {}).get("home"):
                found.append({"id": me["printer"].get("id") or name, "name": me["printer"].get("name") or name.upper(),
                              "home": me["addresses"]["home"], "away": me["addresses"].get("away") or f"https://{name}.{ZONE}"})
        if found != self.found:
            self.found = found
            self._changed()
        return found

    # ---- letting the hub in ----
    async def add(self, pid: str) -> str:
        """Ask the printer to let the hub in. Somebody says yes on the printer's screen, or on a phone already
        paired with it; until then the panel shows it waiting."""
        f = next((f for f in self.found if f["id"] == pid), None)
        if not f:
            raise KeyError("No printer by that name on the Wi-Fi.")
        hub_name = f"{self.hub.settings.get('home_name') or 'Home'} hub"
        self.asking[pid] = "waiting"
        self._changed()
        try:
            st, _, raw = await asyncio.to_thread(self.request, "POST", f"{f['home']}/door/ask", {"name": hub_name, "kind": "hub"})
            handle = (as_json(raw) or {}).get("handle") if st == 201 else None
            if not handle:
                raise RuntimeError(f"the printer answered {st}")
            until = self.now() + ASK_FOR
            while self.now() < until:
                await asyncio.sleep(2)
                st, _, raw = await asyncio.to_thread(self.request, "GET", f"{f['home']}/door/ask/{handle}")
                got = as_json(raw) or {}
                if got.get("state") == "allowed" and got.get("token"):
                    addr = got.get("addresses") or {}
                    self.known[pid] = {"name": f["name"], "home": addr.get("home") or f["home"], "away": addr.get("away") or f["away"],
                                       "token": got["token"], "phone": (got.get("phone") or {}).get("id"), "added": self.now()}
                    self._save()
                    self.asking.pop(pid, None)
                    self.hub.log.add("printer", pid, None, "added", source="user", detail={"name": f["name"]})
                    self.follow(pid)
                    self._changed()
                    return "allowed"
                if got.get("state") in ("refused", "expired") or st == 404:
                    self.asking[pid] = got.get("state") or "expired"
                    self._changed()
                    return self.asking[pid]
            self.asking[pid] = "expired"
        except Exception as e:
            log.info("printers: asking %s failed: %s", pid, e)
            self.asking[pid] = "failed"
        self._changed()
        return self.asking[pid]

    async def forget(self, pid: str):
        """Take a printer off the wall, and the hub off the printer's list of devices."""
        p = self.known.get(pid)
        if not p:
            raise KeyError("No printer by that name.")
        if p.get("phone"):
            try:
                await asyncio.to_thread(self.request, "DELETE", f"{p['home']}/door/phones/{p['phone']}", None,
                                        {"Authorization": f"Bearer {p['token']}"})
            except Exception as e:
                log.info("printers: could not take the hub off %s: %s", pid, e)
        t = self.links.pop(pid, None)
        if t:
            t.cancel()
        self.known.pop(pid, None)
        self.live.pop(pid, None)
        self._save()
        self.hub.log.add("printer", pid, None, "removed", source="user", detail={"name": p["name"]})
        self._changed()

    # ---- following ----
    def follow(self, pid: str):
        if pid in self.links and not self.links[pid].done():
            return
        self.links[pid] = asyncio.create_task(self._follow(pid))

    async def _connect(self, url: str, token: str):
        from websockets.asyncio.client import connect
        ip, host = lan_address(url), host_of(url)
        extra = {"host": ip, "port": 443} if ip else {}
        return await connect(f"wss://{host}/websocket", subprotocols=["astromech", f"astromech-token.{token}"],
                             ssl=ssl.create_default_context(), open_timeout=8, max_size=8 * 1024 * 1024, **extra)

    async def _follow(self, pid: str):
        delay = 2
        while pid in self.known:
            p = self.known[pid]
            for via, url in (("home", p.get("home")), ("away", p.get("away"))):
                if not url:
                    continue
                try:
                    ws = await self.connect(url, p["token"])
                except Exception as e:
                    log.debug("printers: %s by %s: %s", pid, via, e)
                    continue
                try:
                    await self._session(pid, via, ws)
                    delay = 2
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log.info("printers: %s dropped (%s)", pid, e)
                finally:
                    self.sockets.pop(pid, None)
                    try:
                        await ws.close()
                    except Exception:
                        pass
                break
            if (self.live.get(pid) or {}).get("connected"):
                self.live[pid]["connected"] = False
                self._changed()
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)

    async def _session(self, pid: str, via: str, ws):
        self.sockets[pid] = ws
        reader = asyncio.create_task(self._read(pid, ws))
        try:
            await self.call(pid, "server.connection.identify", {"client_name": "home-hub", "version": "1", "type": "other",
                                                                 "url": "https://github.com/topeysoft/home-hub"})
            intent = await self.call(pid, "printer.intent")
            self.live[pid] = {"intent": intent, "connected": True, "via": via,
                              "since": (self.live.get(pid) or {}).get("since") or self.now()}
            self._changed()
            await reader
        finally:
            reader.cancel()

    async def call(self, pid: str, method: str, params: dict | None = None, timeout: float = 15):
        ws = self.sockets.get(pid)
        if ws is None:
            raise ConnectionError("The printer isn't connected.")
        rid = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._calls[rid] = fut
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}))
        try:
            return await asyncio.wait_for(fut, timeout)
        finally:
            self._calls.pop(rid, None)

    async def _read(self, pid: str, ws):
        async for raw in ws:
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            if "id" in m and m["id"] in self._calls:
                fut = self._calls[m["id"]]
                if not fut.done():
                    fut.set_exception(RuntimeError((m["error"] or {}).get("message"))) if "error" in m else fut.set_result(m.get("result"))
            elif m.get("method") == "notify_intent_update":
                self._intent(pid, (m.get("params") or [None])[0])
            elif m.get("method") == "notify_astromech_event":
                for ev in m.get("params") or []:
                    self._event(pid, ev)

    def _intent(self, pid: str, intent):
        if not isinstance(intent, dict):
            return
        live = self.live.setdefault(pid, {"connected": True})
        was = (live.get("intent") or {}).get("state")
        live["intent"] = intent
        if intent.get("state") != was:
            live["since"] = self.now()
        self._changed()

    def _event(self, pid: str, ev):
        """What the printer told its phones, written in the house's log under the printer's own words."""
        if isinstance(ev, dict) and ev.get("kind"):
            self.hub.log.add("printer", pid, None, ev["kind"], source="device",
                             detail={"name": self.known.get(pid, {}).get("name"), "title": ev.get("title"), "body": ev.get("body")})

    # ---- acting ----
    async def act(self, pid: str, action: str, args: dict | None = None):
        if pid not in self.known:
            raise KeyError("No printer by that name.")
        if action not in ACTIONS:
            raise PermissionError("That has to be done at the printer.")
        return await self.call(pid, "printer.intent.action", {"action": action, "args": args or {}})

    def fetch(self, pid: str, what: str, query: str = ""):
        """The camera or the current thumbnail, for the panel, which never holds a printer's token. Streams."""
        p, live = self.known.get(pid), self.live.get(pid) or {}
        if not p:
            raise KeyError("No printer by that name.")
        base = p["home"] if live.get("via") != "away" else p["away"]
        if what == "thumbnail":
            thumb = ((live.get("intent") or {}).get("job") or {}).get("thumbnail")
            if not thumb:
                raise KeyError("Nothing printing.")
            path = "/server/files/gcodes/" + "/".join(s for s in thumb.split("/") if s not in ("", "..", "."))
        else:
            path = "/webcam/" + ("?" + query if query else "?action=stream")
        sep = "&" if "?" in path else "?"
        return self.request("GET", f"{base}{path}{sep}access_token={p['token']}", None, None, 15.0, True)

    # ---- running ----
    async def run(self):
        for pid in list(self.known):
            self.follow(pid)
        while True:
            await self.look()
            await asyncio.sleep(LOOK_EVERY)
