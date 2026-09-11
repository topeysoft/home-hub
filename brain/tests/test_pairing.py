import asyncio, json, unittest
from hub.pairing import Pairing, TOPIC_JOIN


class FakeHA:
    """Records commands; hands back the callback of each stream so a test can feed it events."""
    def __init__(self):
        self.sent, self.calls, self.subs, self.unsubs = [], [], {}, []
        self.results = {"config_entries/get": [{"domain": "zwave_js", "state": "loaded", "entry_id": "zw1"}]}
        self._ids = iter(range(100, 200))
        self.fail = set()

    async def send(self, type_, **kw):
        self.sent.append((type_, kw))
        if type_ in self.fail: raise RuntimeError("no")
        return self.results.get(type_)

    async def call(self, domain, service, entity_id, **data):
        self.calls.append((domain, service, entity_id, data))

    async def subscribe(self, type_, cb, **kw):
        if type_ in self.fail: raise RuntimeError("no")
        i = next(self._ids); self.subs[i] = (type_, cb, kw); return i

    async def unsubscribe(self, i): self.unsubs.append(i); self.subs.pop(i, None)


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, *a, **k): self.rows.append((a, k))


class FakeHub:
    def __init__(self):
        self.ha, self.log, self.pushed = FakeHA(), FakeLog(), []
    def _broadcast(self, msg): self.pushed.append(json.loads(msg))


def run(coro): return asyncio.run(coro)


async def settle(): await asyncio.sleep(0.01)


class ZigbeeTests(unittest.TestCase):
    def test_opens_window_then_hears_a_bulb_join(self):
        async def go():
            hub = FakeHub(); p = Pairing(hub)
            s = await p.start("zigbee")
            self.assertEqual(s["state"], "listening"); self.assertGreater(s["seconds_left"], 200)
            self.assertEqual(hub.ha.calls[0][:2], ("mqtt", "publish"))
            self.assertEqual(hub.ha.calls[0][3]["topic"], TOPIC_JOIN)
            self.assertEqual(json.loads(hub.ha.calls[0][3]["payload"])["time"], 240)
            (_, cb, kw), = hub.ha.subs.values()
            self.assertEqual(kw["topic"], "zigbee2mqtt/bridge/event")
            cb({"topic": kw["topic"], "payload": json.dumps({"type": "device_joined", "data": {"friendly_name": "0xabc", "ieee_address": "0xabc"}})})
            self.assertEqual(p.status()["state"], "found")
            cb({"topic": kw["topic"], "payload": json.dumps({"type": "device_interview", "data": {"friendly_name": "0xabc", "ieee_address": "0xabc", "status": "successful", "supported": True,
                                                              "definition": {"vendor": "IKEA", "model": "LED1624G9", "description": "TRADFRI LED bulb"}}})})
            await settle()
            s = p.status()
            self.assertEqual(s["state"], "done"); self.assertIn("IKEA TRADFRI LED bulb", s["text"]); self.assertEqual(s["device"]["name"], "IKEA TRADFRI LED bulb")
            self.assertEqual(json.loads(hub.ha.calls[-1][3]["payload"])["time"], 0)     # window closed after the join
            self.assertEqual(len(hub.ha.subs), 0)
            self.assertTrue(any(a[3] == "IKEA TRADFRI LED bulb" for a, k in hub.log.rows))
        run(go())

    def test_stop_closes_the_window(self):
        async def go():
            hub = FakeHub(); p = Pairing(hub)
            await p.start("zigbee"); s = await p.stop()
            self.assertEqual(s["state"], "closed")
            self.assertEqual(json.loads(hub.ha.calls[-1][3]["payload"])["time"], 0)
        run(go())

    def test_cannot_start_without_the_radio(self):
        async def go():
            hub = FakeHub(); hub.ha.fail.add("mqtt/subscribe"); p = Pairing(hub)
            s = await p.start("zigbee")
            self.assertEqual(s["state"], "failed"); self.assertIn("Could not start", s["text"])
        run(go())


class ZWaveTests(unittest.TestCase):
    def test_s2_lock_asks_for_a_pin_and_grants_classes(self):
        async def go():
            hub = FakeHub(); p = Pairing(hub)
            s = await p.start("zwave")
            self.assertEqual(s["state"], "listening")
            (t, cb, kw), = hub.ha.subs.values()
            self.assertEqual((t, kw["entry_id"], kw["inclusion_strategy"]), ("zwave_js/add_node", "zw1", 0))
            cb({"event": "node found", "node": {"node_id": 7}})
            cb({"event": "grant security classes", "requested_grant": {"securityClasses": [0, 1, 2], "clientSideAuth": False}})
            await settle()
            self.assertIn(("zwave_js/grant_security_classes", {"entry_id": "zw1", "securityClasses": [0, 1, 2], "clientSideAuth": False}), hub.ha.sent)
            cb({"event": "validate dsk and enter pin", "dsk": "12345-11111-22222"})
            self.assertEqual(p.status()["needs"], "pin")
            with self.assertRaises(ValueError): await p.pin("12")
            s = await p.pin("12345")
            self.assertIn(("zwave_js/validate_dsk_and_enter_pin", {"entry_id": "zw1", "pin": "12345"}), hub.ha.sent)
            self.assertIsNone(s["needs"])
            cb({"event": "node added", "node": {"node_id": 7}, "low_security": False})
            cb({"event": "device registered", "device": {"id": "d1", "manufacturer": "Zooz", "model": "ZEN76", "name": "Zooz ZEN76"}})
            cb({"event": "interview completed"})
            await settle()
            s = p.status()
            self.assertEqual(s["state"], "done"); self.assertIn("Zooz ZEN76 joined", s["text"])
            self.assertIn(("zwave_js/stop_inclusion", {"entry_id": "zw1"}), hub.ha.sent)
        run(go())

    def test_no_zwave_radio(self):
        async def go():
            hub = FakeHub(); hub.ha.results["config_entries/get"] = []; p = Pairing(hub)
            s = await p.start("zwave")
            self.assertEqual(s["state"], "failed"); self.assertIn("not connected", s["text"])
        run(go())


class MatterTests(unittest.TestCase):
    def test_commissions_with_the_code(self):
        async def go():
            hub = FakeHub(); p = Pairing(hub)
            await p.start("matter", "MT:Y.K9042C00KA0648G00")
            await settle()
            self.assertEqual(p.status()["state"], "done")
            self.assertIn(("matter/commission", {"code": "MT:Y.K9042C00KA0648G00", "network_only": False}), hub.ha.sent)
        run(go())

    def test_needs_a_code_and_reports_failure(self):
        async def go():
            hub = FakeHub(); p = Pairing(hub)
            self.assertEqual((await p.start("matter", ""))["state"], "failed")
            hub.ha.fail.add("matter/commission")
            await p.start("matter", "1234-567-8901"); await settle()
            self.assertEqual(p.status()["state"], "failed"); self.assertIn("pairing mode", p.status()["text"])
        run(go())

    def test_unknown_kind(self):
        with self.assertRaises(ValueError): run(Pairing(FakeHub()).start("bluetooth"))


if __name__ == "__main__":
    unittest.main()
