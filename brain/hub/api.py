import asyncio, json, logging, os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from .ha_adapter import HAAdapter
from .model import Home
from .events import EventLog
from .intents import RoomState, SERVICE, plan

log = logging.getLogger("hub")
ROOT = Path(__file__).resolve().parent.parent


def load_env():
    env = {}
    for p in (ROOT.parent / "driver-layer" / ".env",):
        if p.exists():
            for line in p.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1); env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith("HA_")})
    return env


class Hub:
    def __init__(self):
        env = load_env()
        self.ha = HAAdapter(env["HA_URL"], env["HA_TOKEN"])
        self.home = Home()
        self.log = EventLog(ROOT / "events.db")
        self.streams: set[WebSocket] = set()

    async def start(self):
        await self.ha.connect()
        self.home.build(*await self.ha.snapshot())
        self.ha.on_event(self._on_event)
        self._rebuild_task = None
        log.info("home: %d rooms, %d devices", len(self.home.rooms), len(self.home.devices))

    def _on_event(self, ev):
        if ev["event_type"] == "state_changed":
            return self._on_state(ev)
        # registry changed (new device, renamed, moved rooms): rebuild once, debounced
        if self._rebuild_task: self._rebuild_task.cancel()
        self._rebuild_task = asyncio.create_task(self._rebuild())

    async def _rebuild(self):
        await asyncio.sleep(1.0)
        self.home.build(*await self.ha.snapshot())
        self.log.add("home", "registry", None, "rebuilt", source="system",
                     detail={"rooms": len(self.home.rooms), "devices": len(self.home.devices)})
        msg = json.dumps({"type": "home", "home": self.home.to_dict()})
        for ws in list(self.streams): asyncio.create_task(self._push(ws, msg))
        log.info("home rebuilt: %d rooms, %d devices", len(self.home.rooms), len(self.home.devices))

    def _on_state(self, ev):
        d = ev["data"]
        dev = self.home.apply_state(d["entity_id"], d.get("new_state"))
        if not dev: return
        old = (d.get("old_state") or {}).get("state")
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


@app.get("/events")
def get_events(limit: int = 100, subject: str | None = None): return hub.log.recent(limit, subject)


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


@app.post("/rooms/{room_id}/intent/{state}")
async def room_intent(room_id: str, state: RoomState):
    room = hub.home.rooms.get(room_id)
    if not room: raise HTTPException(404, "unknown room")
    calls = plan(room, state)
    for domain, service, eid, data in calls:
        await hub.ha.call(domain, service, eid, **data)
    room.intent = state.value
    hub.log.add("intent", room.id, None, state.value, source="user", detail={"calls": len(calls)})
    return {"ok": True, "calls": len(calls)}


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
