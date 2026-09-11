"""The only module that knows Home Assistant exists: the websocket protocol, and what happens when it drops.

There is no HA here. A stand-in socket hands over the frames HA would send, so the awkward moments —
a refused token, a link that dies with requests in flight — can be made to happen on purpose.

Run from brain/: .venv/bin/python -m unittest -v
"""
import asyncio, json, unittest
from unittest import mock

from hub import ha_adapter
from hub.ha_adapter import AuthError, HAAdapter


class FakeWS:
    """Stands in for the websocket. `script` is what HA says before the conversation starts; after that
    every frame the adapter sends is answered by `reply`, and anything pushed with `push` is delivered."""
    def __init__(self, script, reply=None):
        self.script = list(script)
        self.reply = reply or (lambda m: {"id": m["id"], "type": "result", "success": True, "result": None})
        self.sent = []
        self.queue = asyncio.Queue()
        self.closed = False

    async def recv(self):
        return json.dumps(self.script.pop(0))

    async def send(self, raw):
        m = json.loads(raw)
        self.sent.append(m)
        if "id" in m:
            r = self.reply(m)
            if r is not None: await self.queue.put(json.dumps(r))

    async def push(self, frame):
        await self.queue.put(json.dumps(frame))

    async def drop(self):
        await self.queue.put(None)          # the iterator ends, the way a dead link ends it

    async def close(self):
        self.closed = True
        await self.queue.put(None)

    def __aiter__(self): return self

    async def __anext__(self):
        raw = await self.queue.get()
        if raw is None: raise StopAsyncIteration
        return raw


def answer(result=None, defer=()):
    """HA's side of the conversation. `defer` names request types to leave unanswered, so a test can hold
    one in flight; the handshake's own subscriptions are always answered, or connect() would never return."""
    def reply(m):
        if m["type"] in defer: return None
        return {"id": m["id"], "type": "result", "success": True, "result": result(m) if callable(result) else result}
    return reply


def connected(reply=None, script=None):
    """An adapter whose connect() has been through the handshake with a fake socket."""
    ws = FakeWS(script or [{"type": "auth_required"}, {"type": "auth_ok", "ha_version": "2026.9.0"}], reply or answer())
    ha = HAAdapter("http://ha:8123", "token")
    return ha, ws


class AddressTests(unittest.TestCase):
    def test_the_websocket_address_is_worked_out_from_the_one_in_the_settings(self):
        self.assertEqual(HAAdapter("http://ha:8123", "t").ws_url, "ws://ha:8123/api/websocket")
        self.assertEqual(HAAdapter("https://ha.example.com/", "t").ws_url, "wss://ha.example.com/api/websocket")


class HandshakeTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_good_token_gets_in_and_subscribes_to_what_the_house_is_built_from(self):
        ha, ws = connected()
        with mock.patch.object(ha_adapter.websockets, "connect", mock.AsyncMock(return_value=ws)):
            await ha.connect()
        self.addAsyncCleanup(ha.close)
        self.assertEqual(ws.sent[0], {"type": "auth", "access_token": "token"})
        subscribed = {m["event_type"] for m in ws.sent if m.get("type") == "subscribe_events"}
        self.assertEqual(subscribed, {"state_changed", "entity_registry_updated", "device_registry_updated", "area_registry_updated"})

    async def test_a_token_the_engine_will_not_take_says_so_rather_than_hanging(self):
        ha, ws = connected(script=[{"type": "auth_required"}, {"type": "auth_invalid", "message": "Invalid access token"}])
        with mock.patch.object(ha_adapter.websockets, "connect", mock.AsyncMock(return_value=ws)):
            with self.assertRaises(AuthError) as e:
                await ha.connect()
        self.assertIn("Invalid access token", str(e.exception))
        self.assertTrue(ws.closed)


class TalkingTests(unittest.IsolatedAsyncioTestCase):
    async def start(self, reply=None):
        ha, ws = connected(reply)
        with mock.patch.object(ha_adapter.websockets, "connect", mock.AsyncMock(return_value=ws)):
            await ha.connect()
        self.addAsyncCleanup(ha.close)
        return ha, ws

    async def test_a_request_gets_its_own_answer_back_even_with_others_in_flight(self):
        # Every request carries an id and HA may answer them in any order. Mixing two up would put one
        # room's devices in another room, so this is worth pinning down.
        ha, ws = await self.start(reply=answer(defer=("get_states", "get_config")))
        first = asyncio.create_task(ha.send("get_states"))
        second = asyncio.create_task(ha.send("get_config"))
        await asyncio.sleep(0)
        ids = [m["id"] for m in ws.sent if "id" in m and m["type"] in ("get_states", "get_config")]
        await ws.push({"id": ids[1], "type": "result", "success": True, "result": "config"})
        await ws.push({"id": ids[0], "type": "result", "success": True, "result": "states"})
        self.assertEqual(await first, "states")
        self.assertEqual(await second, "config")

    async def test_what_the_engine_refuses_comes_back_as_an_error_with_its_words(self):
        def refuse(m):
            if m["type"] == "subscribe_events": return answer()(m)
            return {"id": m["id"], "type": "result", "success": False, "error": {"message": "Area not found"}}
        ha, _ = await self.start(reply=refuse)
        with self.assertRaises(RuntimeError) as e:
            await ha.send("config/area_registry/delete", area_id="nope")
        self.assertIn("Area not found", str(e.exception))

    async def test_calling_a_service_names_the_thing_it_is_for(self):
        ha, ws = await self.start()
        await ha.call("light", "turn_on", "light.kitchen", brightness_pct=40)
        call = next(m for m in ws.sent if m.get("type") == "call_service")
        self.assertEqual(call["domain"], "light")
        self.assertEqual(call["service"], "turn_on")
        self.assertEqual(call["target"], {"entity_id": "light.kitchen"})
        self.assertEqual(call["service_data"], {"brightness_pct": 40})

    async def test_a_service_for_the_whole_house_names_nothing(self):
        ha, ws = await self.start()
        await ha.call("homeassistant", "restart", None)
        call = next(m for m in ws.sent if m.get("type") == "call_service")
        self.assertNotIn("target", call)

    async def test_the_house_is_read_in_one_go(self):
        ha, ws = await self.start(reply=answer(result=lambda m: m["type"]))
        areas, devices, entities, states = await ha.snapshot()
        self.assertEqual([areas, devices, entities, states],
                         ["config/area_registry/list", "config/device_registry/list", "config/entity_registry/list", "get_states"])


class EventTests(unittest.IsolatedAsyncioTestCase):
    async def start(self):
        ha, ws = connected()
        with mock.patch.object(ha_adapter.websockets, "connect", mock.AsyncMock(return_value=ws)):
            await ha.connect()
        self.addAsyncCleanup(ha.close)
        return ha, ws

    async def test_a_state_change_reaches_whoever_is_listening(self):
        ha, ws = await self.start()
        seen = []
        ha.on_event(seen.append)
        await ws.push({"id": 2, "type": "event", "event": {"event_type": "state_changed", "data": {"entity_id": "light.a"}}})
        await asyncio.sleep(0.01)
        self.assertEqual(seen[0]["data"]["entity_id"], "light.a")

    async def test_one_listener_that_throws_does_not_rob_the_others(self):
        ha, ws = await self.start()
        seen = []
        ha.on_event(lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
        ha.on_event(seen.append)
        with self.assertLogs("hub.ha_adapter", "ERROR"):
            await ws.push({"id": 2, "type": "event", "event": {"event_type": "state_changed"}})
            await asyncio.sleep(0.01)
        self.assertEqual(len(seen), 1)

    async def test_a_stream_goes_to_the_one_that_opened_it_and_not_to_the_house(self):
        # Pairing opens a stream of its own. Its events must not look like state changes to the model.
        ha, ws = await self.start()
        house, pairing = [], []
        ha.on_event(house.append)
        sub = await ha.subscribe("zwave_js/add_node", pairing.append, entry_id="abc")
        await ws.push({"id": sub, "type": "event", "event": {"event": "node added"}})
        await asyncio.sleep(0.01)
        self.assertEqual(pairing, [{"event": "node added"}])
        self.assertEqual(house, [])


class DroppedLinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_request_in_flight_when_the_link_dies_is_told_rather_than_waiting_forever(self):
        # A hub that hangs here is a hub that stops answering the panel until someone restarts it.
        ha, ws = connected(reply=answer(defer=("get_states",)))
        with mock.patch.object(ha_adapter.websockets, "connect", mock.AsyncMock(return_value=ws)):
            await ha.connect()
        pending = asyncio.create_task(ha.send("get_states"))
        await asyncio.sleep(0)
        await ws.drop()
        with self.assertRaises(ConnectionError):
            await pending

    async def test_a_request_made_after_the_link_died_never_reaches_the_socket(self):
        ha, ws = connected()
        with mock.patch.object(ha_adapter.websockets, "connect", mock.AsyncMock(return_value=ws)):
            await ha.connect()
        await ha.close()
        with self.assertRaises(ConnectionError):
            await ha.send("get_states")

    async def test_a_request_before_there_is_a_link_at_all_is_refused(self):
        with self.assertRaises(ConnectionError):
            await HAAdapter("http://ha:8123", "t").send("get_states")

    async def test_the_hub_can_wait_for_the_link_to_end_so_it_knows_to_make_a_new_one(self):
        ha, ws = connected()
        with mock.patch.object(ha_adapter.websockets, "connect", mock.AsyncMock(return_value=ws)):
            await ha.connect()
        waiter = asyncio.create_task(ha.wait_closed())
        await ws.drop()
        await asyncio.wait_for(waiter, timeout=1)


if __name__ == "__main__":
    unittest.main()
