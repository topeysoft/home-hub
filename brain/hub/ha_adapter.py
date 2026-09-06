"""The only module that knows Home Assistant exists.

Talks to HA over its websocket API. Everything above this file speaks in the semantic model.
One adapter per connection: when the link drops, the hub makes a new one.
"""
import asyncio, itertools, json, logging
import websockets

log = logging.getLogger(__name__)


class AuthError(RuntimeError):
    pass


class HAAdapter:
    def __init__(self, url: str, token: str):
        self.url = url.rstrip("/")
        self.ws_url = self.url.replace("http", "ws", 1) + "/api/websocket"
        self.token = token
        self._ws = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._listeners = []
        self._subs: dict[int, object] = {}      # subscription id -> callback, for streams like mqtt/subscribe and zwave_js/add_node
        self._reader: asyncio.Task | None = None
        self._closed = asyncio.Event()

    async def connect(self):
        self._ws = await websockets.connect(self.ws_url, max_size=2**25, open_timeout=10)
        assert json.loads(await self._ws.recv())["type"] == "auth_required"
        await self._ws.send(json.dumps({"type": "auth", "access_token": self.token}))
        r = json.loads(await self._ws.recv())
        if r["type"] != "auth_ok":
            await self._ws.close()
            raise AuthError(r.get("message") or "HA refused the token")
        self._reader = asyncio.create_task(self._read())
        for ev in ("state_changed", "entity_registry_updated", "device_registry_updated", "area_registry_updated"):
            await self.send("subscribe_events", event_type=ev)
        log.info("connected to %s (HA %s)", self.ws_url, r.get("ha_version"))

    async def close(self):
        if self._reader: self._reader.cancel()
        if self._ws: await self._ws.close()
        self._closed.set()

    async def wait_closed(self):
        await self._closed.wait()

    async def _read(self):
        try:
            async for raw in self._ws:
                m = json.loads(raw)
                if m["type"] == "result":
                    fut = self._pending.pop(m["id"], None)
                    if fut and not fut.done(): fut.set_result(m)
                elif m["type"] == "event":
                    sub = self._subs.get(m.get("id"))
                    if sub is not None:
                        try: sub(m["event"])
                        except Exception: log.exception("subscription %s failed", m.get("id"))
                        continue
                    for cb in self._listeners:
                        try: cb(m["event"])
                        except Exception: log.exception("listener failed")
        except Exception as e:
            log.warning("link to HA dropped: %s", e)
        finally:
            for fut in self._pending.values():
                if not fut.done(): fut.set_exception(ConnectionError("link to HA closed"))
            self._pending.clear()
            self._closed.set()

    async def send(self, type_: str, **kw):
        if self._ws is None or self._closed.is_set(): raise ConnectionError("not connected to HA")
        i = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[i] = fut
        await self._ws.send(json.dumps({"id": i, "type": type_, **kw}))
        m = await fut
        if not m.get("success"):
            raise RuntimeError(f"{type_}: {(m.get('error') or {}).get('message') or m.get('error')}")
        return m.get("result")

    def on_event(self, cb): self._listeners.append(cb)

    async def subscribe(self, type_: str, cb, **kw) -> int:
        """Open a stream (mqtt/subscribe, zwave_js/add_node…): every event on it goes to `cb`. Returns the id to unsubscribe with."""
        if self._ws is None or self._closed.is_set(): raise ConnectionError("not connected to HA")
        i = next(self._ids)
        fut = asyncio.get_running_loop().create_future()
        self._pending[i] = fut
        self._subs[i] = cb
        await self._ws.send(json.dumps({"id": i, "type": type_, **kw}))
        m = await fut
        if not m.get("success"):
            self._subs.pop(i, None)
            raise RuntimeError(f"{type_}: {(m.get('error') or {}).get('message') or m.get('error')}")
        return i

    async def unsubscribe(self, sub_id: int):
        self._subs.pop(sub_id, None)
        try: await self.send("unsubscribe_events", subscription=sub_id)
        except Exception: pass

    async def snapshot(self):
        areas, devices, entities, states = await asyncio.gather(
            self.send("config/area_registry/list"), self.send("config/device_registry/list"),
            self.send("config/entity_registry/list"), self.send("get_states"))
        return areas, devices, entities, states

    async def call(self, domain: str, service: str, entity_id: str | None, **data):
        kw = {"target": {"entity_id": entity_id}} if entity_id else {}
        return await self.send("call_service", domain=domain, service=service, service_data=data, **kw)
