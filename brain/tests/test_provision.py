"""Run from brain/: .venv/bin/python -m unittest tests.test_provision -v"""
import asyncio, unittest
from unittest.mock import patch
from hub import provision


class FakeAdd:
    """A config flow as HA would run it: a script of steps, and a record of what was submitted."""
    def __init__(self, script):
        self.script, self.submitted, self.cancelled = list(script), [], []
    async def start(self, handler): return self.script.pop(0)
    async def step(self, flow_id): return self.script.pop(0)
    async def submit(self, flow_id, data):
        self.submitted.append(data); return self.script.pop(0)
    async def cancel(self, flow_id): self.cancelled.append(flow_id)


class FakeHA:
    def __init__(self, entries=(), devices=()):
        self.entries, self.devices = list(entries), list(devices)
    async def send(self, type_, **kw):
        if type_ == "config_entries/get": return [{"domain": d} for d in self.entries]
        if type_ == "config/device_registry/list": return self.devices
        raise AssertionError(type_)


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, *a, **kw): self.rows.append((a, kw))


class FakeHub:
    def __init__(self, add=None, ha=None):
        self.env, self.driver, self.add, self.ha, self.log, self.sent = {}, "ready", add, ha or FakeHA(), FakeLog(), []
    def _broadcast(self, msg): self.sent.append(msg)
    def status(self): return {"drivers": self.provision.summary()}


def form(fields, **kw): return {"type": "form", "flow_id": "f1", "step_id": "manual", "fields": [{"name": n, "default": d} for n, d in fields], **kw}


class AddTests(unittest.IsolatedAsyncioTestCase):
    async def test_fills_a_form_from_answers_and_defaults(self):
        add = FakeAdd([form([("url", "ws://localhost:3000"), ("extra", True)]), {"type": "create_entry", "flow_id": "f1"}])
        hub = FakeHub(add); p = provision.Provision(hub)
        await p.add("zwave_js", {"url": "ws://hub:3000"})
        self.assertEqual(add.submitted, [{"url": "ws://hub:3000", "extra": True}])
        self.assertEqual(add.cancelled, [])

    async def test_takes_the_manual_path_through_a_menu(self):
        add = FakeAdd([{"type": "menu", "flow_id": "f1", "options": [{"id": "on_supervisor"}, {"id": "manual"}]},
                       form([("url", None)]), {"type": "create_entry"}])
        p = provision.Provision(FakeHub(add))
        await p.add("matter", {"url": "ws://h:5580/ws"})
        self.assertEqual(add.submitted, [{"next_step_id": "manual"}, {"url": "ws://h:5580/ws"}])

    async def test_already_configured_counts_as_done(self):
        add = FakeAdd([{"type": "abort", "flow_id": "f1", "reason": "Already configured"}])
        await provision.Provision(FakeHub(add)).add("mqtt", {})
        self.assertEqual(add.cancelled, [])

    async def test_form_errors_fail_and_cancel(self):
        add = FakeAdd([form([("broker", None)]), form([("broker", None)], errors={"base": "Cannot connect"})])
        with self.assertRaises(RuntimeError) as cm:
            await provision.Provision(FakeHub(add)).add("mqtt", {"broker": "x"})
        self.assertIn("Cannot connect", str(cm.exception))
        self.assertEqual(add.cancelled, ["f1"])


class RefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_adds_what_answers_and_reports_the_rest(self):
        up = {1883, 3000, 55123}
        async def fake_probe(host, port, timeout=1.5): return port in up
        add = FakeAdd([form([("url", "ws://localhost:3000")]), {"type": "create_entry"}])
        hub = FakeHub(add, FakeHA(entries=["mqtt"], devices=[]))
        hub.provision = p = provision.Provision(hub)
        with patch.object(provision, "probe", fake_probe):
            await p.refresh()
        s = {d["id"]: d for d in p.summary()}
        self.assertEqual(s["mqtt"]["state"], "ready")
        self.assertEqual(s["zwave"]["state"], "ready")
        self.assertEqual(add.submitted, [{"url": "ws://localhost:3000"}])
        self.assertEqual(s["zigbee"]["state"], "off")
        self.assertEqual(s["matter"]["state"], "off")
        self.assertEqual(s["ring"]["state"], "sign-in")
        self.assertTrue(hub.sent)                                     # the panel was told
        self.assertEqual(hub.log.rows[0][0][3], "Z-Wave radio connected")

    async def test_a_failure_waits_before_retrying(self):
        async def fake_probe(host, port, timeout=1.5): return port == 5580
        add = FakeAdd([{"type": "abort", "flow_id": "f1", "reason": "cannot_connect"}])
        hub = FakeHub(add, FakeHA()); hub.provision = p = provision.Provision(hub)
        with patch.object(provision, "probe", fake_probe):
            await p.refresh(); await p.refresh()
        self.assertEqual(p.parts["matter"]["state"], "failed")
        self.assertEqual(add.script, [])                              # only one attempt was made
        self.assertEqual(add.cancelled, ["f1"])

    async def test_ring_is_ready_once_its_devices_exist(self):
        async def fake_probe(host, port, timeout=1.5): return port == 55123
        hub = FakeHub(None, FakeHA(devices=[{"manufacturer": "Ring"}])); hub.provision = p = provision.Provision(hub)
        with patch.object(provision, "probe", fake_probe):
            await p.refresh()
        self.assertEqual(p.parts["ring"]["state"], "ready")

    async def test_driver_host_comes_from_env(self):
        hub = FakeHub(); hub.env = {"HUB_DRIVER_HOST": "mosquitto"}
        self.assertEqual(provision.Provision(hub).host, "mosquitto")
