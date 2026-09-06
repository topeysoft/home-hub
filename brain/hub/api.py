import asyncio, json, logging, os, urllib.parse, urllib.request
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from .ha_adapter import HAAdapter
from .model import Home
from .events import EventLog
from .intents import RoomState, SERVICE, plan, rules_as_data

log = logging.getLogger("hub")
ROOT = Path(__file__).resolve().parent.parent


def load_env():
    env = {}
    for p in (ROOT.parent / "driver-layer" / ".env",):
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1); env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith(("HA_", "HOME_"))})
    return env


class Hub:
    def __init__(self):
        env = load_env()
        self.ha = HAAdapter(env["HA_URL"], env["HA_TOKEN"])
        self.home = Home()
        self.log = EventLog(ROOT / "events.db")
        self.streams: set[WebSocket] = set()
        self.location = None      # {"name", "lat", "lon"}: chosen in the panel, else HA's config, else HOME_LAT/HOME_LON in .env
        self.weather = None       # the first weather entity HA has, in the app's shape
        self.temp_unit = "°F"
        self.settings_path = ROOT / "settings.json"
        self.settings = json.loads(self.settings_path.read_text()) if self.settings_path.exists() else {}

    async def start(self):
        await self.ha.connect()
        cfg = await self.ha.send("get_config")
        self.temp_unit = (cfg.get("unit_system") or {}).get("temperature", "°F")
        lat, lon = cfg.get("latitude") or 0, cfg.get("longitude") or 0
        env = load_env()
        if self.settings.get("location"): self.location = self.settings["location"]
        elif lat and lon: self.location = {"name": cfg.get("location_name") or "Home", "lat": lat, "lon": lon}
        elif env.get("HOME_LAT") and env.get("HOME_LON"): self.location = {"name": "Home", "lat": float(env["HOME_LAT"]), "lon": float(env["HOME_LON"])}
        else: log.warning("no home location yet: the panel will ask for one")
        snap = await self.ha.snapshot()
        self.home.build(*snap)
        self._pick_weather(snap[3])
        self.ha.on_event(self._on_event)
        self._rebuild_task = None
        log.info("home: %d rooms, %d devices, weather=%s", len(self.home.rooms), len(self.home.devices), self.weather and self.weather["id"])

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
        return {"location": self.location, "weather": self.weather}

    async def set_location(self, place):
        """Remember the home's location, tell HA (fixes sun.sun), and set up Met.no weather if there is none yet."""
        self.location = {"name": place["name"], "lat": place["lat"], "lon": place["lon"]}
        self.settings["location"] = self.location
        self.settings_path.write_text(json.dumps(self.settings, indent=1))
        core = {"latitude": place["lat"], "longitude": place["lon"], "location_name": place["name"]}
        if place.get("tz"): core["time_zone"] = place["tz"]
        try: await self.ha.send("config/core/update", **core)
        except Exception as e: log.warning("HA would not take the location: %s", e)
        weather = None
        if not self.weather:
            weather = await asyncio.to_thread(self._setup_met, place)
        self._broadcast(json.dumps({"type": "ambient", "ambient": self.ambient()}))
        return weather

    def _setup_met(self, place):
        """Create the Met.no config entry through HA's REST config-flow API. Free, no key, local forecast."""
        env = load_env()
        def post(path, data):
            r = urllib.request.Request(f"{env['HA_URL']}{path}", data=json.dumps(data).encode(), method="POST",
                                       headers={"Authorization": f"Bearer {env['HA_TOKEN']}", "Content-Type": "application/json"})
            with urllib.request.urlopen(r, timeout=30) as resp: return json.loads(resp.read())
        try:
            r = post("/api/config/config_entries/flow", {"handler": "met"})
            if r.get("type") == "form":
                r = post(f"/api/config/config_entries/flow/{r['flow_id']}", {"name": place["name"], "latitude": place["lat"], "longitude": place["lon"], "elevation": 0})
            log.info("met.no setup: %s %s", r.get("type"), r.get("reason") or r.get("title") or r.get("errors") or "")
            return r.get("title") if r.get("type") == "create_entry" else None
        except Exception as e:
            log.warning("met.no setup failed: %s", e); return None

    def _broadcast(self, msg):
        for ws in list(self.streams): asyncio.create_task(self._push(ws, msg))

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
        had = self.weather and self.weather["id"]
        self._pick_weather(snap[3])
        if (self.weather and self.weather["id"]) != had: self._broadcast(json.dumps({"type": "ambient", "ambient": self.ambient()}))
        self.log.add("home", "registry", None, "rebuilt", source="system",
                     detail={"rooms": len(self.home.rooms), "devices": len(self.home.devices)})
        msg = json.dumps({"type": "home", "home": self.home.to_dict()})
        for ws in list(self.streams): asyncio.create_task(self._push(ws, msg))
        log.info("home rebuilt: %d rooms, %d devices", len(self.home.rooms), len(self.home.devices))

    def _on_state(self, ev):
        d = ev["data"]
        if d["entity_id"].startswith("weather.") and d.get("new_state"):
            if not self.weather or self.weather["id"] == d["entity_id"]:
                self.weather = self._weather_of(d["new_state"])
                self._broadcast(json.dumps({"type": "ambient", "ambient": self.ambient()}))
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
        msg = json.dumps({"type": "device", "device": dev.__dict__})
        for ws in list(self.streams):
            asyncio.create_task(self._push(ws, msg))

    async def _push(self, ws, msg):
        try: await ws.send_text(msg)
        except Exception: self.streams.discard(ws)


hub = Hub()


@asynccontextmanager
async def lifespan(app):
    await hub.start()
    yield
    await hub.ha.close()


app = FastAPI(title="home-hub brain", lifespan=lifespan)


@app.get("/home")
def get_home(): return hub.home.to_dict()


@app.get("/scenes")
def get_scenes():
    """Scene rules as data: the app uses them to tell whether a room still matches the scene it was set to."""
    return rules_as_data()


@app.get("/ambient")
def get_ambient():
    """What the sky should look like: the home's location (the app computes the sun) and the current weather."""
    return hub.ambient()


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


@app.get("/events")
def get_events(limit: int = 100, subject: str | None = None): return hub.log.recent(limit, subject)


@app.get("/devices/{device_id}/image")
async def device_image(device_id: str):
    """Latest still from a camera. The app polls this; the brain never stores frames."""
    dev = hub.home.devices.get(device_id)
    if not dev: raise HTTPException(404, "unknown device")
    if dev.capability == "camera": path = f"/api/camera_proxy/{dev.id}"
    elif dev.capability == "media" and dev.attrs.get("entity_picture"): path = dev.attrs["entity_picture"]
    else: raise HTTPException(404, "no image for this device")
    env = load_env()
    def fetch():
        # Artwork can be an absolute URL (Cast apps hand out their own); HA-relative paths need the token.
        url = path if path.startswith("http") else f"{env['HA_URL']}{path}"
        headers = {} if path.startswith("http") else {"Authorization": f"Bearer {env['HA_TOKEN']}"}
        r = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(r, timeout=15) as resp: return resp.read(), resp.headers.get("Content-Type", "image/jpeg")
    try:
        data, ctype = await asyncio.to_thread(fetch)
    except Exception as e:
        raise HTTPException(502, f"image unavailable: {e}")
    return Response(content=data, media_type=ctype, headers={"Cache-Control": "no-store"})


@app.post("/devices/{device_id}/{action}")
async def device_action(device_id: str, action: str, data: dict | None = None):
    dev = hub.home.devices.get(device_id)
    if not dev: raise HTTPException(404, "unknown device")
    key = (dev.capability.split(".")[0], action)
    if key not in SERVICE: raise HTTPException(400, f"{dev.capability} cannot {action}")
    domain, service = SERVICE[key]
    await hub.ha.call(domain, service, dev.id, **(data or {}))
    hub.log.add("action", dev.id, None, action, source="user", detail=data)
    return {"ok": True}


async def _apply(room, state: RoomState):
    """Run a room's plan, skipping devices that refuse. A scene does as much as it can."""
    done, failed = 0, []
    for domain, service, eid, data in plan(room, state):
        try:
            await hub.ha.call(domain, service, eid, **data); done += 1
        except Exception as e:
            failed.append(eid); log.warning("%s %s failed: %s", eid, service, e)
    if room.devices: room.intent = state.value
    return done, failed


@app.post("/rooms/{room_id}/intent/{state}")
async def room_intent(room_id: str, state: RoomState):
    room = hub.home.rooms.get(room_id)
    if not room: raise HTTPException(404, "unknown room")
    done, failed = await _apply(room, state)
    hub.log.add("intent", room.id, None, state.value, source="user", detail={"calls": done, "failed": failed})
    return {"ok": True, "calls": done, "failed": failed}


@app.post("/home/intent/{state}")
async def home_intent(state: RoomState):
    """The same intent in every room at once: good night, everything off."""
    done, failed = 0, []
    for room in hub.home.rooms.values():
        n, f = await _apply(room, state); done += n; failed += f
    hub.log.add("intent", "home", None, state.value, source="user", detail={"calls": done, "failed": failed})
    return {"ok": True, "calls": done, "failed": failed}


@app.websocket("/stream")
async def stream(ws: WebSocket):
    await ws.accept(); hub.streams.add(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        hub.streams.discard(ws)


# The wall panel / phone app, built with `npm run build` in ../app. Mounted last so API routes win.
DIST = ROOT.parent / "app" / "dist"
if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="app")
