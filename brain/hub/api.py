import asyncio, json, logging, shutil, time, urllib.parse, urllib.request
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, JSONResponse, FileResponse, StreamingResponse
from starlette.background import BackgroundTask
from fastapi import Request
from . import ha_setup
from .ha_adapter import HAAdapter, AuthError
from .model import Home
from .events import EventLog
from .intents import RoomState, SERVICE, plan, rules_as_data, holds
from .onboarding import Onboarding
from .provision import Provision
from .comfort import Comfort
from .rules import Engine
from .presence import Presence, WATCHED, word as presence_word
from .assistant import Assistant, AssistantError
from .updates import Updates
from .health import Health
from .backup import Backup
from .sounds import Sounds, DIR as SOUNDS_DIR
from .commands import Commands, NotUnderstood
from .suggest import Suggestions
from .settings import Settings, DATA, env_file
from .lock import Lock, needs_code
from .pairing import Pairing
from .phones import Phones, COOKIE, open_to_strangers
from . import camera

log = logging.getLogger("hub")
DEFAULT_HA = "http://localhost:8123"
# How the panel looks. The keys are the whole vocabulary: anything else a screen
# sends is dropped, so an old panel cannot teach the house a setting it will not
# understand. Values are checked in the panel, which owns what they mean.
LOOK = {"tone": "follow", "layout": "stack"}
US_ZONES = ("America/New_York", "America/Chicago", "America/Denver", "America/Phoenix", "America/Los_Angeles", "America/Anchorage",
            "America/Juneau", "America/Sitka", "America/Nome", "America/Adak", "America/Boise", "America/Detroit", "America/Menominee",
            "America/Indiana/", "America/Kentucky/", "America/North_Dakota/", "Pacific/Honolulu", "US/")


def unit_system_for(tz: str) -> str:
    return "us_customary" if tz.startswith(US_ZONES) else "metric"


def qr_svg_bytes(text: str) -> bytes:
    """A QR code as SVG paths in the panel's colours; the panel puts it on a light card."""
    import io, qrcode
    from qrcode.image.svg import SvgPathImage
    q = qrcode.QRCode(box_size=10, border=2, error_correction=qrcode.constants.ERROR_CORRECT_M, image_factory=SvgPathImage)
    q.add_data(text); q.make(fit=True)
    b = io.BytesIO(); q.make_image().save(b)
    return b.getvalue()


class Hub:
    """Keeps the house model alive whatever the driver layer is doing.

    driver: "down" (HA not answering) → "fresh" (HA has no owner yet) → "needs-login" (HA is set up
    but we hold no token) → "connecting" → "ready". Setup endpoints move it along; the loop keeps
    retrying on its own, and the panel is told every time it changes.
    """
    def __init__(self):
        self.settings = Settings()
        self.env = env_file()
        self.ha: HAAdapter | None = None
        self.home = Home()
        self.log = EventLog(DATA / "events.db")
        self.streams: set[WebSocket] = set()
        self.driver, self.reason = "down", ""
        self.location = self.settings.get("location")   # {"name", "lat", "lon"}: chosen in the panel, else HA's config, else HOME_LAT/HOME_LON in .env
        self.entry: list = list(self.settings.get("entry") or [])   # room ids the family comes in through; rules for "entry" run there
        self.look = {**LOOK, **(self.settings.get("look") or {})}   # how the panel looks: one house, one answer, every screen
        self.weather = None
        self.temp_unit = "°F"
        self.tz = datetime.now().astimezone().tzinfo   # the home's zone, from HA's config once connected
        self.add = Onboarding(self)
        self.lock = Lock(self.settings)
        self.pair = Pairing(self)
        self.phones = Phones(self)                     # which phones belong to the house, once it has a code
        self.engine = Engine(self)                     # rules: signals in, room intents out
        self.presence = Presence(self)                 # who is home, from HA's persons and the alarm's mode
        self.assistant = Assistant(self)               # writes drafts and explains from the log; never runs anything
        self.updates = Updates(self)                   # which build this is, whether a newer one exists, and the panel's ask
        self.health = Health(self)                     # what needs a look, as sentences
        self.backup = Backup(self)                     # the house as one file, and back
        self.sounds = Sounds(self)                     # noise and rain on a speaker, looped here, with a sleep timer
        self.commands = Commands(self)                 # plain words into moves, by a fixed grammar first and the assistant after
        self.suggest = Suggestions(self)               # names and rooms for things not placed yet; proposes, never moves
        self._timers: dict[str, asyncio.Task] = {}     # things the brain will do later for a device (switch a fan off)
        self.comfort = Comfort(self)                   # a thermostat sensing its room from another sensor
        self._comfort_task = None
        self.provision = Provision(self)               # connects the radios, Matter and MQTT to HA itself
        self._tick_task = self._drivers_task = None
        self._wake = asyncio.Event()
        self._rebuild_task = None
        self._loop_task = None
        self._loop: asyncio.AbstractEventLoop | None = None   # the server's loop, for broadcasts from worker threads

    # ---- where HA is and how to get in ----
    @property
    def ha_url(self) -> str:
        return (self.settings.get("ha") or {}).get("url") or self.env.get("HA_URL") or DEFAULT_HA

    @property
    def ha_token(self) -> str | None:
        return (self.settings.get("ha") or {}).get("token") or self.env.get("HA_TOKEN")

    def status(self) -> dict:
        return {"driver": self.driver, "reason": self.reason, "setup_done": bool(self.settings.get("setup_done")),
                "owner": (self.settings.get("owner") or {}).get("name"), "home": self.settings.get("home_name"),
                "location": bool(self.location), "rooms": sum(1 for r in self.home.rooms.values() if r.id != "unassigned"),
                "devices": len(self.home.devices), "drivers": self.provision.summary(), "problems": self.provision.problems,
                "locked": self.lock.locked, "version": self.updates.version, "update": self.updates.summary()}

    def _set(self, driver, reason=""):
        if (driver, reason) == (self.driver, self.reason): return
        self.driver, self.reason = driver, reason
        log.info("driver %s %s", driver, reason)
        self._broadcast(json.dumps({"type": "status", "status": self.status()}))

    def wake(self):
        self._wake.set()

    async def _nap(self, seconds):
        try: await asyncio.wait_for(self._wake.wait(), seconds)
        except asyncio.TimeoutError: pass
        self._wake.clear()

    # ---- the lifecycle loop ----
    async def run(self):
        while True:
            try:
                try: state = await asyncio.to_thread(ha_setup.driver_state, self.ha_url)
                except Exception as e:
                    self._set("down", "The hub's engine is not answering yet."); await self._nap(3); continue
                if state == "fresh":
                    self._set("fresh"); await self._nap(10); continue
                if not self.ha_token:
                    self._set("needs-login", "The engine was set up separately."); await self._nap(10); continue
                self._set("connecting")
                ha = HAAdapter(self.ha_url, self.ha_token)
                try: await ha.connect()
                except AuthError as e:
                    self._set("needs-login", "The saved key no longer works."); await self._nap(10); continue
                except Exception as e:
                    self._set("down", f"{e}"); await self._nap(3); continue
                self.ha = ha
                try:
                    await self._connected()
                except Exception:
                    log.exception("could not read the house"); await ha.close(); await self._nap(3); continue
                await ha.wait_closed()
                self._set("connecting", "Reconnecting to the engine.")
                await self._nap(1)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("lifecycle loop"); await self._nap(3)

    async def _connected(self):
        cfg = await self.ha.send("get_config")
        self.temp_unit = (cfg.get("unit_system") or {}).get("temperature", "°F")
        if cfg.get("time_zone"):
            try: self.tz = ZoneInfo(cfg["time_zone"])
            except Exception: log.warning("unknown time zone %r; using the host's", cfg["time_zone"])
        lat, lon = cfg.get("latitude") or 0, cfg.get("longitude") or 0
        if self.settings.get("location"): self.location = self.settings.get("location")
        elif lat and lon: self.location = {"name": cfg.get("location_name") or "Home", "lat": lat, "lon": lon}
        elif self.env.get("HOME_LAT") and self.env.get("HOME_LON"): self.location = {"name": "Home", "lat": float(self.env["HOME_LAT"]), "lon": float(self.env["HOME_LON"])}
        else: log.info("no home location yet: the panel will ask for one")
        snap = await self.ha.snapshot()
        self.home.build(*snap)
        self.presence.load(snap[3]); self.presence.seed(self.log)
        self.engine.load(force=True); self.engine.seed()
        self.comfort.load()
        self._pick_weather(snap[3])
        self.ha.on_event(self._on_event)
        self._set("ready")
        asyncio.create_task(self.provision.refresh())   # look at the driver layer now, not at the next half-minute
        asyncio.create_task(self.sounds.ensure())        # the generated noises, once
        self._broadcast(json.dumps({"type": "home", "home": self.home_dict()}))
        self._broadcast(json.dumps({"type": "ambient", "ambient": self.ambient()}))
        log.info("home: %d rooms, %d devices, weather=%s", len(self.home.rooms), len(self.home.devices), self.weather and self.weather["id"])

    def ready(self):
        if self.driver != "ready": raise HTTPException(503, "The hub is still starting.")

    def home_dict(self):
        return {"name": self.settings.get("home_name"), "temp_unit": self.temp_unit, "entry": self.entry, **self.home.to_dict()}

    def set_entry(self, rooms):
        """Which rooms people come in through. Unknown ids are dropped rather than refused: a room may be renamed later."""
        self.entry = [r for r in dict.fromkeys(rooms or []) if isinstance(r, str) and r in self.home.rooms and r != "unassigned"]
        self.settings.set(entry=self.entry)
        self.log.add("home", "entry", None, ",".join(self.entry), source="user")
        self._broadcast(json.dumps({"type": "home", "home": self.home_dict()}))
        return self.entry

    # ---- setup, driven by the panel ----
    async def create_owner(self, name: str, home: str):
        if self.driver == "fresh":
            acct = await ha_setup.onboard(self.ha_url, name)
            self.settings.set(ha={"url": self.ha_url, **acct})
            self.log.add("home", "setup", None, "owner created", source="user")
        self.settings.set(owner={"name": name}, home_name=home)
        self.wake()

    async def sign_in(self, username: str, password: str):
        acct = await ha_setup.sign_in(self.ha_url, username, password)
        self.settings.set(ha={"url": self.ha_url, **acct})
        self.wake()

    # ---- weather and the sky ----
    def _pick_weather(self, states):
        """Prefer the plain 'home' forecast over hourly/daily variants; any weather entity beats none."""
        ws = [s for s in states if s["entity_id"].startswith("weather.")]
        ws.sort(key=lambda s: ("hourly" in s["entity_id"] or "daily" in s["entity_id"], s["entity_id"]))
        self.weather = self._weather_of(ws[0]) if ws else None

    def _weather_of(self, s):
        a = s["attributes"]
        return {"id": s["entity_id"], "condition": s["state"], "temperature": a.get("temperature"),
                "unit": a.get("temperature_unit", self.temp_unit), "humidity": a.get("humidity"),
                "wind_speed": a.get("wind_speed"), "wind_unit": a.get("wind_speed_unit")}

    def ambient(self):
        return {"location": self.location, "weather": self.weather, "look": self.look}

    def set_look(self, look):
        """How the panel looks, kept by the house rather than by the screen: a
        tone for the cards and an arrangement for Home. Every screen in the
        house shows the same one, and a new screen is already right."""
        self.look = {**self.look, **{k: v for k, v in look.items() if k in LOOK}}
        self.settings.set(look=self.look)
        self._broadcast(json.dumps({"type": "ambient", "ambient": self.ambient()}))
        return self.look

    async def set_location(self, place):
        """Remember the home's location, tell HA (fixes sun.sun), and set up Met.no weather if there is none yet."""
        self.location = {"name": place["name"], "lat": place["lat"], "lon": place["lon"]}
        self.settings.set(location=self.location)
        core = {"latitude": place["lat"], "longitude": place["lon"], "location_name": place["name"]}
        if place.get("tz"):
            core["time_zone"] = place["tz"]
            core["unit_system"] = unit_system_for(place["tz"])   # a house in the US reads in °F; everyone else in °C
        weather = None
        if self.driver == "ready":
            try:
                await self.ha.send("config/core/update", **core)
                cfg = await self.ha.send("get_config")
                unit = (cfg.get("unit_system") or {}).get("temperature", self.temp_unit)
                if unit != self.temp_unit:
                    self.temp_unit = unit
                    if self._rebuild_task: self._rebuild_task.cancel()
                    self._rebuild_task = asyncio.create_task(self._rebuild())   # thermostats now report in the new unit
            except Exception as e: log.warning("HA would not take the location: %s", e)
            if not self.weather:
                weather = await asyncio.to_thread(self._setup_met, place)
        self._broadcast(json.dumps({"type": "ambient", "ambient": self.ambient()}))
        return weather

    def _setup_met(self, place):
        """Create the Met.no config entry through HA's REST config-flow API. Free, no key, local forecast."""
        def post(path, data):
            r = urllib.request.Request(f"{self.ha_url}{path}", data=json.dumps(data).encode(), method="POST",
                                       headers={"Authorization": f"Bearer {self.ha_token}", "Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=30) as resp: return json.loads(resp.read())
        try:
            r = post("/api/config/config_entries/flow", {"handler": "met"})
            if r.get("type") == "form":
                r = post(f"/api/config/config_entries/flow/{r['flow_id']}", {"name": place["name"], "latitude": place["lat"], "longitude": place["lon"], "elevation": 0})
            log.info("met.no setup: %s %s", r.get("type"), r.get("reason") or r.get("title") or r.get("errors") or "")
            return r.get("title") if r.get("type") == "create_entry" else None
        except Exception as e:
            log.warning("met.no setup failed: %s", e); return None

    # ---- live updates ----
    def _broadcast(self, msg):
        """Push to every open panel. Safe from a worker thread too: a plain `def` route runs off the loop."""
        async def fan_out():
            for ws in list(self.streams): asyncio.create_task(self._push(ws, msg))
        try: asyncio.get_running_loop(); asyncio.create_task(fan_out())
        except RuntimeError:
            if self._loop: asyncio.run_coroutine_threadsafe(fan_out(), self._loop)

    def _on_event(self, ev):
        if ev["event_type"] == "state_changed":
            return self._on_state(ev)
        # registry changed (new device, renamed, moved rooms): rebuild once, debounced
        if self._rebuild_task: self._rebuild_task.cancel()
        self._rebuild_task = asyncio.create_task(self._rebuild())

    async def _rebuild(self):
        await asyncio.sleep(1.0)
        snap = await self.ha.snapshot()
        self.home.build(*snap)
        self.presence.load(snap[3])
        self.engine.load(force=True); self.engine.seed()
        self.comfort.load()
        had = self.weather and self.weather["id"]
        self._pick_weather(snap[3])
        if (self.weather and self.weather["id"]) != had: self._broadcast(json.dumps({"type": "ambient", "ambient": self.ambient()}))
        self.log.add("home", "registry", None, "rebuilt", source="system",
                     detail={"rooms": len(self.home.rooms), "devices": len(self.home.devices)})
        self._broadcast(json.dumps({"type": "home", "home": self.home_dict()}))
        log.info("home rebuilt: %d rooms, %d devices", len(self.home.rooms), len(self.home.devices))

    def _on_state(self, ev):
        d = ev["data"]
        if d["entity_id"].startswith("weather.") and d.get("new_state"):
            if not self.weather or self.weather["id"] == d["entity_id"]:
                self.weather = self._weather_of(d["new_state"])
                self._broadcast(json.dumps({"type": "ambient", "ambient": self.ambient()}))
            return
        if d["entity_id"].startswith(WATCHED):
            was = self.presence.somebody
            if self.presence.on_state(d["entity_id"], d.get("new_state")):
                self.log.add("presence", "home", presence_word(was), presence_word(self.presence.somebody), source="device", detail=self.presence.as_dict())
                self._broadcast(json.dumps({"type": "presence", "presence": self.presence.as_dict()}))
                self.engine.on_presence()
            return
        old_state = d.get("old_state") or {}
        before = self.home.devices.get(d["entity_id"])
        old_attrs = self.home._keep_attrs(before.capability, old_state.get("attributes", {})) if before else None
        dev = self.home.apply_state(d["entity_id"], d.get("new_state"))
        if not dev: return
        old = old_state.get("state")
        # Cameras and media players re-announce the same state constantly; only real changes go in the log.
        if old != dev.state or old_attrs != dev.attrs:
            self.log.add("state", dev.id, old, dev.state, source="device", detail=dev.attrs)
        self._broadcast(json.dumps({"type": "device", "device": dev.__dict__}))
        self.engine.on_state(dev, old)
        self.sounds.on_state(dev, old)
        if dev.capability in ("climate", "sensor.temperature"): asyncio.create_task(self.comfort.on_state(dev))

    async def _comfort_loop(self):
        while True:
            await asyncio.sleep(120)
            try:
                if self.driver == "ready": await self.comfort.tick()
            except Exception:
                log.exception("comfort tick")

    # ---- intents: the one path that changes a room, for taps and rules alike ----
    async def _run_plan(self, room, state: RoomState):
        """Run a room's plan, skipping devices that refuse. A scene does as much as it can."""
        done, failed = 0, []
        for domain, service, eid, data in plan(room, state):
            try:
                await self.ha.call(domain, service, eid, **data); done += 1
            except Exception as e:
                failed.append(eid); log.warning("%s %s failed: %s", eid, service, e)
        return done, failed

    def hold_for(self, state: RoomState) -> float | None:
        secs = holds().get(state.value, 0)
        return time.time() + secs if secs else None

    def _mark(self, room, state: RoomState, source, detail):
        if not room.devices: return
        room.intent = state.value
        room.set_by = f"rule:{detail['rule']}" if source == "rule" else source
        room.hold_until = self.hold_for(state) if source == "user" else None
        self._broadcast(json.dumps({"type": "intent", "room": room.id, "intent": room.intent, "set_by": room.set_by, "hold_until": room.hold_until}))

    async def set_intent(self, room, state: RoomState, source="user", detail=None, depth=0):
        """Move one room into a state. A tap holds the room against rules; a rule records why it fired."""
        done, failed = await self._run_plan(room, state)
        old = room.intent
        self._mark(room, state, source, detail or {})
        self.log.add("intent", room.id, old, state.value, source=source, detail={**(detail or {}), "calls": done, "failed": failed})
        self.engine.on_intent(room.id, state, depth)
        return done, failed

    async def set_home_intent(self, state: RoomState, source="user", detail=None, depth=0):
        """The same intent in every room at once: good night, everything off."""
        done, failed = 0, []
        for room in self.home.rooms.values():
            n, f = await self._run_plan(room, state); done += n; failed += f
            self._mark(room, state, source, detail or {})
        old, self.home.intent = self.home.intent, state.value
        self.log.add("intent", "home", old, state.value, source=source, detail={**(detail or {}), "calls": done, "failed": failed})
        self.engine.on_intent("home", state, depth)
        return done, failed

    # ---- the fan on a thermostat, for a while ----
    async def fan(self, dev, minutes: int):
        """Run a thermostat's fan for `minutes`, then switch it off; 0 switches it off now. HA only knows on and off,
        and its "on" means hours, so the timer lives here. A restart forgets it, and the fan then runs HA's length."""
        if t := self._timers.pop(dev.id, None): t.cancel()
        if minutes <= 0:
            await self.ha.call("climate", "set_fan_mode", dev.id, fan_mode="off")
            self.home.extras.pop(dev.id, None)
            self.log.add("action", dev.id, None, "fan off", source="user")
        else:
            await self.ha.call("climate", "set_fan_mode", dev.id, fan_mode="on")
            self.home.extras[dev.id] = {"fan_until": time.time() + minutes * 60}
            self._timers[dev.id] = asyncio.create_task(self._fan_off_later(dev.id, minutes * 60))
            self.log.add("action", dev.id, None, f"fan {minutes} min", source="user", detail={"minutes": minutes})
        dev.attrs = {**{k: v for k, v in dev.attrs.items() if k != "fan_until"}, "fan_mode": "on" if minutes > 0 else "off", **self.home.extras.get(dev.id, {})}
        self._broadcast(json.dumps({"type": "device", "device": dev.__dict__}))

    async def _fan_off_later(self, eid: str, seconds: int):
        await asyncio.sleep(seconds)
        self._timers.pop(eid, None); self.home.extras.pop(eid, None)
        dev = self.home.devices.get(eid)
        try:
            await self.ha.call("climate", "set_fan_mode", eid, fan_mode="off")
            self.log.add("action", eid, None, "fan off", source="timer")
        except Exception as e:
            log.warning("could not switch the fan off on %s: %s", eid, e)
        if dev:
            dev.attrs = {k: v for k, v in dev.attrs.items() if k != "fan_until"}
            self._broadcast(json.dumps({"type": "device", "device": dev.__dict__}))

    async def act(self, dev, action: str, data: dict | None = None, source="user", said: str | None = None):
        """One device, one action: the path a tile's tap, a typed command and a confirmed proposal all take.
        Raises ValueError when the thing cannot do that; whatever the driver raises comes through as it is."""
        data = dict(data or {})
        if action == "set" and dev.capability == "climate" and self.comfort.sensing(dev.id) and data.get("temperature") is not None:
            await self.comfort.want(dev, float(data["temperature"]))     # while sensing from elsewhere, the number is what the other room should reach
        elif action in ("sound", "sound_off"):
            if action == "sound": await self.sounds.play(dev, str(data.get("sound", "")), data.get("minutes"), data.get("volume"), source=source)
            else: await self.sounds.stop(dev, source=source)
        else:
            key = (dev.capability.split(".")[0], action)
            if key not in SERVICE: raise ValueError(f"{dev.capability} cannot {action}")
            domain, service = SERVICE[key]
            await self.ha.call(domain, service, dev.id, **data)
            self.log.add("action", dev.id, None, action, source=source, detail={**data, **({"said": said} if said else {})} or None)
        if dev.capability != "camera" and dev.room_id in self.home.rooms: self.hold(self.home.rooms[dev.room_id])

    def hold(self, room, state: RoomState = RoomState.occupied):
        """Someone touched a device in this room by hand: rules leave it alone for a while."""
        until = self.hold_for(state)
        if until and (room.hold_until or 0) < until:
            room.hold_until = until
            self._broadcast(json.dumps({"type": "intent", "room": room.id, "intent": room.intent, "set_by": room.set_by, "hold_until": room.hold_until}))

    async def _push(self, ws, msg):
        try: await ws.send_text(msg)
        except Exception: self.streams.discard(ws)


hub = Hub()


@asynccontextmanager
async def lifespan(app):
    hub._loop = asyncio.get_running_loop()
    hub._loop_task = asyncio.create_task(hub.run())
    hub._tick_task = asyncio.create_task(hub.engine.run())
    hub._drivers_task = asyncio.create_task(hub.provision.run())
    hub._comfort_task = asyncio.create_task(hub._comfort_loop())
    hub._update_task = asyncio.create_task(hub.updates.run())
    hub._suggest_task = asyncio.create_task(hub.assistant.run())
    yield
    for t in (hub._loop_task, hub._tick_task, hub._drivers_task, hub._comfort_task, hub._update_task, hub._suggest_task): t.cancel()
    if hub.ha: await hub.ha.close()


app = FastAPI(title="home-hub brain", lifespan=lifespan)


@app.middleware("http")
async def settings_lock(request: Request, call_next):
    """Once the house has a code: only its own phones get in, and changing the house needs the code. Driving it never does."""
    request.state.phone = None
    if hub.lock.locked:
        m, path = request.method, request.url.path
        if not open_to_strangers(m, path):
            phone = hub.phones.identify(request.cookies.get(COOKIE))
            if not phone: return JSONResponse({"detail": "phone"}, status_code=401)
            request.state.phone = phone
        if needs_code(m, path):
            who = request.client.host if request.client else ""
            wait = hub.lock.waiting(who)
            if wait > 0: return JSONResponse({"detail": f"Too many tries. Wait {int(wait) + 1} seconds."}, status_code=429)
            if not hub.lock.check(request.headers.get("x-hub-code"), who):
                return JSONResponse({"detail": "code"}, status_code=401)
    return await call_next(request)


def _with_cookie(body: dict, request: Request, phone: dict, token: str) -> JSONResponse:
    """The phone's token, in a cookie the page's scripts cannot read. Secure when the front door was https."""
    r = JSONResponse(body)
    life = int(phone["expires"] - time.time()) if phone.get("expires") else 10 * 365 * 24 * 3600
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    r.set_cookie(COOKIE, token, max_age=max(life, 60), httponly=True, samesite="lax", secure=https, path="/")
    return r


def _device_kind(request: Request) -> str:
    ua = request.headers.get("user-agent", "")
    return "wall" if "Mobile" not in ua and "iPhone" not in ua and "Android" not in ua else "phone"


# ---------- setup ----------
@app.get("/setup/status")
def setup_status(): return hub.status()


@app.post("/setup/owner")
async def setup_owner(body: dict):
    name, home = (body.get("name") or "").strip(), (body.get("home") or "").strip()
    if not name: raise HTTPException(400, "A name is needed.")
    if hub.driver not in ("fresh", "ready", "connecting", "needs-login"): raise HTTPException(503, "The hub's engine is not ready yet.")
    try: await hub.create_owner(name, home or "Home")
    except ha_setup.SetupError as e: raise HTTPException(502, str(e))
    return hub.status()


@app.post("/setup/login")
async def setup_login(body: dict):
    u, p = (body.get("username") or "").strip(), body.get("password") or ""
    if not u or not p: raise HTTPException(400, "Both the name and the password are needed.")
    try: await hub.sign_in(u, p)
    except ha_setup.SetupError as e: raise HTTPException(401, str(e))
    return hub.status()


@app.post("/setup/home")
async def setup_home(body: dict):
    hub.settings.set(home_name=(body.get("name") or "").strip() or "Home")
    hub._broadcast(json.dumps({"type": "home", "home": hub.home_dict()}))
    return hub.status()


@app.post("/setup/drivers")
async def setup_drivers():
    """Look at the driver layer now rather than at the next half-minute: the panel asks after a stick was plugged in."""
    hub.ready()
    await hub.provision.refresh()
    return hub.status()


@app.post("/setup/retry/{entry_id}")
async def setup_retry(entry_id: str):
    """Try an integration HA could not set up again (after the person fixed what it complained about)."""
    hub.ready()
    try: await hub.provision.retry(entry_id)
    except Exception as e: raise HTTPException(502, str(e))
    return hub.status()


@app.post("/setup/pin")
def setup_pin(body: dict, request: Request):
    """Set, change or (with an empty pin) remove the code. Changing one needs the old one, like any setting.
    The screen that sets the first code becomes the house's first paired phone: the door turns on and it is inside."""
    was = hub.lock.locked
    try: hub.lock.set(str(body.get("pin") or "").strip())
    except ValueError as e: raise HTTPException(400, str(e))
    hub.log.add("home", "setup", None, "code set" if hub.lock.locked else "code removed", source="user")
    hub._broadcast(json.dumps({"type": "status", "status": hub.status()}))
    if hub.lock.locked and not was and not request.state.phone:
        phone, token = hub.phones.from_setup(_device_kind(request))
        return _with_cookie(hub.status(), request, phone, token)
    return hub.status()


@app.get("/setup/advanced")
def setup_advanced():
    """The engine's own sign-in, for the Advanced door. Behind the code."""
    ha = hub.settings.get("ha") or {}
    return {"url": hub.ha_url, "username": ha.get("username") or hub.env.get("HA_USER"), "password": ha.get("password") or hub.env.get("HA_PASSWORD")}


@app.post("/setup/done")
async def setup_done():
    hub.settings.set(setup_done=True)
    hub.log.add("home", "setup", None, "finished", source="user")
    hub._broadcast(json.dumps({"type": "status", "status": hub.status()}))
    return hub.status()


# ---------- the house ----------
@app.get("/home")
def get_home(): return hub.home_dict()


@app.get("/scenes")
def get_scenes():
    """Scene rules as data: the app uses them to tell whether a room still matches the scene it was set to."""
    return rules_as_data()


@app.get("/ambient")
def get_ambient():
    """What the sky should look like: the home's location (the app computes the sun) and the current weather."""
    return hub.ambient()


@app.post("/rooms")
async def add_room(body: dict):
    hub.ready()
    name = (body.get("name") or "").strip()
    if not name: raise HTTPException(400, "A room needs a name.")
    for r in hub.home.rooms.values():
        if r.name.lower() == name.lower(): return {"id": r.id, "name": r.name}
    try: a = await hub.ha.send("config/area_registry/create", name=name)
    except Exception as e: raise HTTPException(502, f"could not add the room: {e}")
    hub.log.add("home", "room", None, name, source="user")
    return {"id": a["area_id"], "name": a["name"]}


@app.post("/rooms/{room_id}/rename")
async def rename_room(room_id: str, body: dict):
    hub.ready()
    if room_id == "unassigned" or room_id not in hub.home.rooms: raise HTTPException(404, "unknown room")
    name = (body.get("name") or "").strip()
    if not name: raise HTTPException(400, "A room needs a name.")
    try: await hub.ha.send("config/area_registry/update", area_id=room_id, name=name)
    except Exception as e: raise HTTPException(502, f"could not rename the room: {e}")
    return {"ok": True}


@app.delete("/rooms/{room_id}")
async def remove_room(room_id: str):
    hub.ready()
    if room_id == "unassigned" or room_id not in hub.home.rooms: raise HTTPException(404, "unknown room")
    try: await hub.ha.send("config/area_registry/delete", area_id=room_id)
    except Exception as e: raise HTTPException(502, f"could not remove the room: {e}")
    return {"ok": True}


@app.post("/devices/{device_id}/move")
async def move_device(device_id: str, body: dict):
    """Put a device in a room. Moves the physical thing when there is one, so its other parts follow."""
    hub.ready()
    dev = hub.home.devices.get(device_id)
    if not dev: raise HTTPException(404, "unknown device")
    room = body.get("room_id") or None
    if room == "unassigned": room = None
    if room and room not in hub.home.rooms: raise HTTPException(404, "unknown room")
    try:
        if dev.hw: await hub.ha.send("config/device_registry/update", device_id=dev.hw, area_id=room)
        if dev.own_room or not dev.hw: await hub.ha.send("config/entity_registry/update", entity_id=dev.id, area_id=None if dev.hw else room)
    except Exception as e: raise HTTPException(502, f"could not move it: {e}")
    hub.log.add("home", dev.id, dev.room_id, room or "unassigned", source="user", detail={"moved": True})
    return {"ok": True}


@app.post("/devices/{device_id}/rename")
async def rename_device(device_id: str, body: dict):
    hub.ready()
    dev = hub.home.devices.get(device_id)
    if not dev: raise HTTPException(404, "unknown device")
    name = (body.get("name") or "").strip()
    if not name: raise HTTPException(400, "A name is needed.")
    try: await hub.ha.send("config/entity_registry/update", entity_id=dev.id, name=name)
    except Exception as e: raise HTTPException(502, f"could not rename it: {e}")
    return {"ok": True}


# ---------- adding things ----------
@app.get("/discovered")
async def discovered():
    if hub.driver != "ready": return []
    return await hub.add.discovered()


@app.get("/catalog")
async def catalog():
    hub.ready()
    return await hub.add.catalog()


@app.post("/flows")
async def start_flow(body: dict):
    hub.ready()
    handler = body.get("handler")
    if not handler: raise HTTPException(400, "what to add is needed")
    try: return await hub.add.start(handler)
    except Exception as e: raise HTTPException(502, str(e))


@app.get("/flows/{flow_id}")
async def get_flow(flow_id: str):
    hub.ready()
    try: return await hub.add.step(flow_id)
    except Exception as e: raise HTTPException(502, str(e))


@app.post("/flows/{flow_id}")
async def submit_flow(flow_id: str, body: dict | None = None):
    hub.ready()
    try: r = await hub.add.submit(flow_id, body or {})
    except Exception as e: raise HTTPException(502, str(e))
    if r.get("type") == "create_entry": hub.log.add("home", "device", None, r.get("entry_title") or r["kind"], source="user", detail={"added": r["handler"]})
    return r


@app.post("/credentials")
async def set_credentials(body: dict):
    """The key an account-based integration needs (OAuth client ID and secret); then its flow begins."""
    hub.ready()
    h, cid, sec = body.get("handler"), (body.get("client_id") or "").strip(), (body.get("client_secret") or "").strip()
    if not (h and cid and sec): raise HTTPException(400, "The client ID and the client secret are both needed.")
    hints = body.get("hints") if isinstance(body.get("hints"), dict) else None
    try: return await hub.add.set_credentials(h, cid, sec, hints)
    except Exception as e: raise HTTPException(502, str(e))


@app.delete("/flows/{flow_id}")
async def cancel_flow(flow_id: str):
    await hub.add.cancel(flow_id)
    return {"ok": True}


# ---------- pairing radio devices ----------
@app.get("/pair")
def pair_status(): return hub.pair.status()


@app.post("/pair")
async def pair_start(body: dict):
    hub.ready()
    try: return await hub.pair.start(body.get("kind") or "", body.get("code"))
    except ValueError as e: raise HTTPException(400, str(e))


@app.post("/pair/pin")
async def pair_pin(body: dict):
    hub.ready()
    try: return await hub.pair.pin(str(body.get("pin") or "").strip())
    except ValueError as e: raise HTTPException(400, str(e))
    except Exception as e: raise HTTPException(502, f"The radio did not take the code: {e}")


@app.delete("/pair")
async def pair_stop(): return await hub.pair.stop()


# ---------- location ----------
def _get_json(url, headers=None):
    r = urllib.request.Request(url, headers={"User-Agent": "home-hub/0.1", **(headers or {})})
    with urllib.request.urlopen(r, timeout=12) as resp: return json.loads(resp.read())


def _place_name(parts): return ", ".join(p for p in parts if p)


@app.post("/location")
async def set_location(place: dict):
    if not all(k in place for k in ("lat", "lon")): raise HTTPException(400, "lat and lon are required")
    place = {"name": place.get("name") or "Home", "lat": float(place["lat"]), "lon": float(place["lon"]), "tz": place.get("tz")}
    if not (-90 <= place["lat"] <= 90 and -180 <= place["lon"] <= 180): raise HTTPException(400, "those coordinates are not on Earth")
    weather = await hub.set_location(place)
    hub.log.add("home", "location", None, place["name"], source="user", detail={"lat": place["lat"], "lon": place["lon"]})
    return {"ok": True, "weather": weather}


@app.post("/look")
def set_look(look: dict):
    """The house's own look. Unknown keys are ignored rather than refused, so a
    screen running an older panel can still save the settings it does know."""
    if not isinstance(look, dict) or not any(k in LOOK for k in look):
        raise HTTPException(400, f"nothing to set; expected any of {', '.join(LOOK)}")
    return hub.set_look(look)


@app.get("/geo/search")
async def geo_search(q: str):
    """Towns matching a name, from Open-Meteo's free geocoder."""
    try: r = await asyncio.to_thread(_get_json, f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(q)}&count=6&language=en&format=json")
    except Exception as e: raise HTTPException(502, f"search unavailable: {e}")
    return [{"name": _place_name([x.get("name"), x.get("admin1"), None if x.get("country_code") == "US" else x.get("country")]),
             "lat": x["latitude"], "lon": x["longitude"], "tz": x.get("timezone")} for x in r.get("results", [])]


@app.get("/geo/auto")
async def geo_auto():
    """Roughly where the hub is, from its public address. City-level, which is all the sky needs."""
    try:
        d = await asyncio.to_thread(_get_json, "https://ipwho.is/")
        if not d.get("success"): raise RuntimeError(d.get("message", "no answer"))
        return {"name": _place_name([d.get("city"), d.get("region_code") or d.get("region"), None if d.get("country_code") == "US" else d.get("country")]),
                "lat": d["latitude"], "lon": d["longitude"], "tz": (d.get("timezone") or {}).get("id")}
    except Exception as e:
        raise HTTPException(502, f"could not locate the hub: {e}")


@app.get("/geo/reverse")
async def geo_reverse(lat: float, lon: float):
    """A name for a point, so a device location or typed coordinates read as a town."""
    try:
        d = await asyncio.to_thread(_get_json, f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=jsonv2&zoom=10")
        a = d.get("address", {})
        town = a.get("city") or a.get("town") or a.get("village") or a.get("municipality") or a.get("county")
        name = _place_name([town, a.get("state"), None if a.get("country_code") == "us" else a.get("country")]) or f"{lat:.3f}, {lon:.3f}"
    except Exception:
        name = f"{lat:.3f}, {lon:.3f}"
    return {"name": name, "lat": lat, "lon": lon}


# ---------- events, images, actions ----------
@app.get("/events")
def get_events(limit: int = 100, subject: str | None = None): return hub.log.recent(limit, subject)


@app.get("/devices/{device_id}/image")
async def device_image(device_id: str):
    """Latest still from a camera. The app polls this; the brain never stores frames."""
    hub.ready()
    dev = hub.home.devices.get(device_id)
    if not dev: raise HTTPException(404, "unknown device")
    if dev.capability == "camera": path = f"/api/camera_proxy/{dev.id}"
    elif dev.capability == "media" and dev.attrs.get("entity_picture"): path = dev.attrs["entity_picture"]
    else: raise HTTPException(404, "no image for this device")
    url, token = hub.ha.url, hub.ha.token
    def fetch():
        # Artwork can be an absolute URL (Cast apps hand out their own); HA-relative paths need the token.
        full = path if path.startswith("http") else f"{url}{path}"
        headers = {} if path.startswith("http") else {"Authorization": f"Bearer {token}"}
        r = urllib.request.Request(full, headers=headers)
        with urllib.request.urlopen(r, timeout=15) as resp: return resp.read(), resp.headers.get("Content-Type", "image/jpeg")
    try:
        data, ctype = await asyncio.to_thread(fetch)
    except Exception as e:
        raise HTTPException(502, f"image unavailable: {e}")
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "no-store"})


def _camera(device_id: str):
    hub.ready()
    dev = hub.home.devices.get(device_id)
    if not dev or dev.capability != "camera": raise HTTPException(404, "not a camera")
    return dev


@app.get("/devices/{device_id}/stream")
async def device_stream(device_id: str):
    """Motion JPEG from a camera, passed through: the viewer's fallback when WebRTC cannot be had."""
    dev = _camera(device_id)
    try: ctype, chunks = await asyncio.to_thread(camera.mjpeg, hub.ha.url, hub.ha.token, dev.id)
    except Exception as e: raise HTTPException(502, f"stream unavailable: {e}")
    return StreamingResponse(chunks, media_type=ctype, headers={"Cache-Control": "no-store"})


@app.websocket("/devices/{device_id}/webrtc")
async def device_webrtc(ws: WebSocket, device_id: str):
    """WebRTC signalling for one viewer: see hub/camera.py for the messages."""
    await ws.accept()
    dev = hub.home.devices.get(device_id) if hub.driver == "ready" else None
    if not dev or dev.capability != "camera":
        await ws.send_text(json.dumps({"type": "error", "code": "unknown", "message": "not a camera"}))
        await ws.close(); return
    try: await camera.relay(hub.ha, dev.id, ws)
    except WebSocketDisconnect: return
    except Exception as e: log.warning("live view of %s ended: %s", dev.id, e)
    try: await ws.close()
    except Exception: pass


@app.post("/devices/{device_id}/fan")
async def device_fan(device_id: str, body: dict | None = None):
    """A thermostat's fan for a while: {"minutes": 30}; 0 stops it."""
    hub.ready()
    dev = hub.home.devices.get(device_id)
    if not dev: raise HTTPException(404, "unknown device")
    if dev.capability != "climate" or "on" not in (dev.attrs.get("fan_modes") or []): raise HTTPException(400, "this thermostat has no fan control")
    try: minutes = max(0, min(720, int((body or {}).get("minutes") or 0)))
    except (TypeError, ValueError): raise HTTPException(400, "minutes must be a number")
    await hub.fan(dev, minutes)
    if dev.room_id in hub.home.rooms: hub.hold(hub.home.rooms[dev.room_id])
    return {"ok": True, "fan_until": dev.attrs.get("fan_until")}


@app.post("/devices/{device_id}/sense")
async def device_sense(device_id: str, body: dict | None = None):
    """Sense a thermostat's room from another temperature sensor: {"sensor": "<id>"}; null goes back to its own."""
    hub.ready()
    dev = hub.home.devices.get(device_id)
    if not dev or dev.capability != "climate": raise HTTPException(404, "unknown thermostat")
    try: await hub.comfort.set_sensor(dev, (body or {}).get("sensor") or None)
    except ValueError as e: raise HTTPException(400, str(e))
    return {"ok": True, **hub.comfort.describe(dev.id)}


@app.post("/devices/{device_id}/{action}")
async def device_action(device_id: str, action: str, data: dict | None = None):
    hub.ready()
    dev = hub.home.devices.get(device_id)
    if not dev: raise HTTPException(404, "unknown device")
    try: await hub.act(dev, action, data)
    except ValueError as e: raise HTTPException(400, str(e))
    if action in ("sound", "sound_off"): return {"ok": True, "playing": hub.sounds.describe(dev.id)}
    return {"ok": True}


@app.post("/say")
async def say(body: dict):
    """{"text": "kitchen lights off", "room": "<optional room id the panel is showing>"}. The grammar runs at once, the way a tap
    does; what it cannot place goes to the assistant, which only proposes. Answers: {"kind": "done" | "answer" | "explain" |
    "action" | "rule", ...}. Driving the house never needs the code, and neither does asking."""
    hub.ready()
    try: return await hub.commands.say(str(body.get("text") or ""), body.get("room"))
    except NotUnderstood as e: raise HTTPException(422, str(e))
    except AssistantError as e: raise HTTPException(e.status, str(e))


# ---------- placing new things ----------
@app.get("/suggestions")
async def suggestions():
    """A name and a room for each thing under New devices, from the house's own reasoning and then the assistant's.
    Nothing moves until a person taps Use; that goes through /devices/{id}/move and /rename like any other change."""
    hub.ready()
    return await hub.suggest.all()


# ---------- the phone ----------
@app.get("/qr.svg")
def qr_svg(text: str):
    """A QR code for the panel's address, so a phone opens the house from the wall or the Done screen."""
    text = (text or "").strip()
    if not text.startswith(("http://", "https://")) or len(text) > 200: raise HTTPException(400, "an http address, please")
    return Response(content=qr_svg_bytes(text), media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})


@app.get("/phone")
def phone():
    """What a phone needs to reach this hub: its address on the Wi‑Fi, for when hub.local does not answer."""
    return {"ip": Sounds._lan_ip()}


# ---------- the phones that belong to the house ----------
@app.get("/phones/me")
def phones_me(request: Request):
    """Open to anyone on the Wi‑Fi: is this phone in, and what is the house called. The join screen starts here."""
    phone = hub.phones.identify(request.cookies.get(COOKIE)) if hub.lock.locked else None
    return {"locked": hub.lock.locked, "paired": (not hub.lock.locked) or bool(phone), "home": hub.settings.get("home_name") or "Home",
            "phone": hub.phones._public(phone) if phone else None}


@app.get("/phones")
def phones_list(request: Request): return hub.phones.list(request.state.phone)


@app.post("/phones/ask")
def phones_ask(body: dict, request: Request):
    """A phone asks to join. Someone at a paired screen answers; the phone polls /phones/claim meanwhile."""
    if not hub.lock.locked: raise HTTPException(409, "The house has no code, so every phone on the Wi‑Fi is already in.")
    return hub.phones.ask(str(body.get("name") or ""), _device_kind(request))


@app.get("/phones/claim/{ask_id}")
def phones_claim(ask_id: str, request: Request):
    state, phone, token = hub.phones.claim(ask_id)
    if state != "allowed": return {"state": state}
    return _with_cookie({"state": state, "phone": hub.phones._public(phone)}, request, phone, token)


@app.post("/phones/code")
def phones_code(body: dict, request: Request):
    """The code, typed on the phone itself: the owner's way in. Wrong codes count against the address like anywhere else."""
    if not hub.lock.locked: raise HTTPException(409, "The house has no code.")
    who = request.client.host if request.client else ""
    wait = hub.lock.waiting(who)
    if wait > 0: raise HTTPException(429, f"Too many tries. Wait {int(wait) + 1} seconds.")
    if not hub.lock.check(str(body.get("code") or ""), who): raise HTTPException(401, "That wasn't it.")
    phone, token = hub.phones.with_code(str(body.get("name") or ""), _device_kind(request))
    return _with_cookie({"ok": True, "phone": hub.phones._public(phone)}, request, phone, token)


@app.post("/phones/asks/{ask_id}/allow")
def phones_allow(ask_id: str, body: dict | None = None):
    """Behind the code, from a paired screen: {"span": "day" | "weekend" | "keep"}."""
    try: return hub.phones.allow(ask_id, (body or {}).get("span") or "keep")
    except KeyError as e: raise HTTPException(404, str(e.args[0]))
    except ValueError as e: raise HTTPException(400, str(e))


@app.delete("/phones/asks/{ask_id}")
def phones_deny(ask_id: str):
    hub.phones.deny(ask_id); return {"ok": True}


@app.delete("/phones/{phone_id}")
def phones_remove(phone_id: str):
    if not hub.phones.remove(phone_id): raise HTTPException(404, "No such phone.")
    return {"ok": True}


@app.post("/phones/{phone_id}/remote")
def phones_remote(phone_id: str, body: dict):
    try: return hub.phones.set_remote(phone_id, bool(body.get("remote")))
    except KeyError as e: raise HTTPException(404, str(e.args[0]))


@app.post("/rooms/{room_id}/intent/{state}")
async def room_intent(room_id: str, state: RoomState):
    hub.ready()
    room = hub.home.rooms.get(room_id)
    if not room: raise HTTPException(404, "unknown room")
    done, failed = await hub.set_intent(room, state, source="user")
    return {"ok": True, "calls": done, "failed": failed}


@app.post("/home/entry")
def home_entry(body: dict):
    """{"rooms": ["living_room", "garage"]}: where the family comes in. Routines written for "entry" run in these."""
    hub.ready()
    return {"entry": hub.set_entry(body.get("rooms"))}


@app.post("/home/intent/{state}")
async def home_intent(state: RoomState):
    hub.ready()
    done, failed = await hub.set_home_intent(state, source="user")
    return {"ok": True, "calls": done, "failed": failed}


@app.get("/rooms/{room_id}/why")
def room_why(room_id: str, limit: int = 5):
    """The last few times this room was set, held or shadowed, with each rule's reasons. The assistant explains from this.
    House-wide taps (Bedtime, Everything off) are logged once under `home`, so a room's story includes them."""
    if room_id != "home" and room_id not in hub.home.rooms: raise HTTPException(404, "unknown room")
    subjects = "home" if room_id == "home" else (room_id, "home")
    return hub.log.recent(limit, subject=subjects, kinds=("intent", "held", "shadowed", "failed"))


# ---------- sounds ----------
@app.get("/sounds")
async def sounds():
    """What a speaker can play: the generated noises and every file in the sounds folder, plus what is playing now.
    Asking also starts preparing any new file, so a fresh rain.mp3 is looped and ready by the time someone taps it."""
    hub.sounds.prepare_soon()
    return {"sounds": hub.sounds.catalog(), "playing": {k: hub.sounds.describe(k) for k in hub.sounds.sessions}, "folder": str(SOUNDS_DIR)}


# ---------- health ----------
@app.get("/health")
def health():
    """What needs a look, in plain words: [{"kind", "text", "since", "subject"}]. Empty is good news."""
    return {"notes": hub.health.notes() if hub.driver == "ready" else []}


# ---------- backup and restore ----------
@app.get("/backup")
def backup():
    """The house as one .tar.gz. Behind the settings code: it holds the engine's key and the code's hash."""
    path = hub.backup.make()
    return FileResponse(path, media_type="application/gzip", filename=path.name, background=BackgroundTask(shutil.rmtree, path.parent, True))


@app.post("/restore")
async def restore(request: Request):
    """The archive as the request body. Parked for the host, which stops the house, unpacks and starts it again."""
    try: return hub.backup.receive(await request.body())
    except ValueError as e: raise HTTPException(400, str(e))


# ---------- updates ----------
@app.get("/update")
def update_status(): return hub.updates.summary()


@app.post("/update/check")
async def update_check(): return await hub.updates.check()


@app.post("/update")
def update_request():
    """Install the update: the host does it, the panel watches. Behind the settings code."""
    return hub.updates.request()


# ---------- the assistant: writes and explains, never runs ----------
@app.get("/assistant")
def assistant_status(): return hub.assistant.status()


@app.post("/assistant/key")
async def assistant_key(body: dict):
    """{"key": "..."}: remember the key after one call proves it; an empty key forgets it."""
    try: return await hub.assistant.set_key(body.get("key", ""))
    except ValueError as e: raise HTTPException(400, str(e))


@app.get("/drafts")
def drafts(): return hub.assistant.drafts()


@app.post("/drafts")
async def make_draft(body: dict):
    """{"text": "when I leave, everything off"} -> a draft rule, waiting for approval. Nothing runs."""
    hub.ready()
    try: return await hub.assistant.draft(body.get("text", ""))
    except AssistantError as e: raise HTTPException(e.status, str(e))


@app.post("/drafts/suggest")
def suggest_drafts():
    """Look for habits now instead of waiting for the daily pass. Adds drafts at most; runs nothing."""
    hub.ready()
    return {"added": hub.assistant.suggest()}


@app.post("/drafts/{rule_id}/approve")
def approve_draft(rule_id: str):
    try: return hub.assistant.approve(rule_id)
    except AssistantError as e: raise HTTPException(e.status, str(e))
    except ValueError as e: raise HTTPException(422, str(e))


@app.delete("/drafts/{rule_id}")
def discard_draft(rule_id: str):
    try: hub.assistant.discard(rule_id)
    except AssistantError as e: raise HTTPException(e.status, str(e))
    return {"ok": True}


@app.post("/rooms/{room_id}/explain")
async def explain_room(room_id: str, body: dict | None = None):
    """{"question": "why did the light come on?"} -> prose from the log. The facts are the log's; the words are the model's."""
    hub.ready()
    try: return await hub.assistant.explain(room_id, (body or {}).get("question"))
    except AssistantError as e: raise HTTPException(e.status, str(e))


@app.get("/presence")
def presence():
    """Who is home: {"somebody": true | false | null, "since", "source": "people" | "alarm" | null, "people": [...], "alarm"}."""
    return hub.presence.as_dict()


# ---------- rules ----------
@app.get("/rules")
def get_rules(): return hub.engine.as_data()


@app.put("/rules")
def put_rules(raw: dict):
    """Replace rules.json. Refused, with reasons, unless every rule can run; the old file keeps running meanwhile."""
    try: hub.engine.save(raw)
    except ValueError as e: raise HTTPException(422, str(e))
    return hub.engine.as_data()


@app.post("/rules/{rule_id}/enable")
def enable_rule(rule_id: str, body: dict):
    raw = hub.engine.as_data()
    row = next((r for r in raw.get("rules", []) if isinstance(r, dict) and r.get("id") == rule_id), None)
    if not row: raise HTTPException(404, "unknown rule")
    row["enabled"] = bool(body.get("enabled", True))
    hub.engine.save({k: v for k, v in raw.items() if k not in ("valid", "errors")})
    return {"ok": True, "enabled": row["enabled"]}


@app.get("/rules/{rule_id}/dry-run")
def dry_run(rule_id: str):
    out = hub.engine.dry_run(rule_id)
    if not out: raise HTTPException(404, "unknown rule")
    return out


@app.websocket("/stream")
async def stream(ws: WebSocket):
    if hub.lock.locked and not hub.phones.identify(ws.cookies.get(COOKIE)):
        await ws.close(code=4401); return        # not one of the house's phones: the join screen is the way in
    await ws.accept(); hub.streams.add(ws)
    try:
        await ws.send_text(json.dumps({"type": "status", "status": hub.status()}))
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        hub.streams.discard(ws)


# Speakers fetch sounds from here (byte ranges served). Mounted before the panel's catch-all below, which would
# otherwise answer every /sounds/... path with its own 404 and the speaker would sit at idle with the title showing.
SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/sounds", StaticFiles(directory=SOUNDS_DIR), name="sounds")

# The wall panel / phone app, built with `npm run build` in ../app. Mounted last so API routes win.
DIST = Path(__file__).resolve().parent.parent.parent / "app" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="app")
