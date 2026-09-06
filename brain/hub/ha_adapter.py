"""The only module that knows Home Assistant exists.

Talks to HA over its websocket API. Everything above this file speaks in the semantic model.
"""
import asyncio, itertools, json, logging
import websockets

log = logging.getLogger(__name__)


class HAAdapter:
    def __init__(self, url: str, token: str):
        self.ws_url = url.replace("http", "ws", 1).rstrip("/") + "/api/websocket"
        self.token = token
        self._ws = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._listeners = []
        self._reader: asyncio.Task | None = None

    async def connect(self):
        self._ws = await websockets.connect(self.ws_url, max_size=2**25)
        assert json.loads(await self._ws.recv())["type"] == "auth_required"
        await self._ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        r = json.loads(await self._ws.recv())
        if r["type"] != "auth_ok":
            raise RuntimeError(f"HA auth failed: {r}")
        self._reader = asyncio.create_task(self._read())
        for ev in ("state_changed", "entity_registry_updated", "device_registry_updated", "area_registry_updated"):
            await self.send("subscribe_events", event_type=ev)
        log.info("connected to %s (HA %s)", self.ws_url, r.get("ha_version"))

    async def close(self):
        if self._reader: self._reader.cancel()
        if self._ws: await self._ws.close()

    async def _read(self):
        async for raw in self._ws:
            m = json.loads(raw)
            if m["type"] == "result":
                fut = self._pending.pop(m["id"], None)
                if fut and not fut.done(): fut.set_result(m)
            elif m["type"] == "event":
                for cb in self._listeners:
                    try: cb(m["event"])
                    except Exception: log.exception("listener failed")

    async def send(self, type_: str, **kw):
        i = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[i] = fut
        await self._ws.send(json.dumps({"id": i, "type": type_, **kw}))
        m = await fut
        if not m.get("success"):
            raise RuntimeError(f"{type_}: {m.get('error')}")
        return m.get("result")

    def on_event(self, cb): self._listeners.append(cb)

    async def snapshot(self):
        areas, devices, entities, states = await asyncio.gather(
            self.send("config/area_registry/list"), self.send("config/device_registry/list"),
            self.send("config/entity_registry/list"), self.send("get_states"))
        return areas, devices, entities, states

    async def call(self, domain: str, service: str, entity_id: str, **data):
        return await self.send("call_service", domain=domain, service=service,
                               service_data=data, target={"entity_id": entity_id})
