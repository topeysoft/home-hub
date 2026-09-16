"""Run from brain/: .venv/bin/python -m unittest tests.test_provision -v"""
import unittest
from unittest.mock import patch
from hub import provision


class FakeAdd:
    """A config flow as HA would run it: a script of steps, and a record of what was submitted."""
    def __init__(self, script, waiting=()):
        self.script, self.submitted, self.cancelled, self.waiting = list(script), [], [], list(waiting)
    async def sign_ins(self): return list(self.waiting)
    async def start(self, handler): return self.script.pop(0)
    async def reconfigure(self, handler, entry_id):
        self.reconfigured.append((handler, entry_id)); return self.script.pop(0)
    reconfigured: list = []
    async def step(self, flow_id): return self.script.pop(0)
    async def submit(self, flow_id, data):
        self.submitted.append(data); return self.script.pop(0)
    async def cancel(self, flow_id): self.cancelled.append(flow_id)
    def _rest(self, method, path, data=None): self.rested.append((method, path)); return {}
    rested: list = []


class FakeHA:
    def __init__(self, entries=(), devices=(), broken=()):
        self.entries, self.devices, self.broken, self.reloaded = list(entries), list(devices), list(broken), []
    async def send(self, type_, **kw):
        if type_ == "config_entries/get":
            return [{"domain": d, "entry_id": f"e-{d}", "title": d.title(), "state": "loaded"} for d in self.entries] + list(self.broken)
        if type_ == "config/device_registry/list": return self.devices
        raise AssertionError(type_)


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, *a, **kw): self.rows.append((a, kw))


class FakeSettings:
    def __init__(self, **data): self.data = dict(data)
    def get(self, k, default=None): return self.data.get(k, default)
    def set(self, **updates): self.data.update(updates)


class FakeHub:
    def __init__(self, add=None, ha=None, env=None, settings=None):
        self.env, self.driver, self.add, self.ha, self.log, self.sent = dict(env or {}), "ready", add or FakeAdd([]), ha or FakeHA(), FakeLog(), []
        self.settings = settings or FakeSettings()
    def _broadcast(self, msg): self.sent.append(msg)
    def status(self): return {"drivers": self.provision.summary()}


def form(fields, **kw): return {"type": "form", "flow_id": "f1", "step_id": "manual", "fields": [{"name": n, "default": d} for n, d in fields], **kw}


async def _nosleep(*a): pass


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


def _only(port_open):
    async def probe(host, port, timeout=1.5): return port in port_open
    return probe


AUTH = {"MQTT_USER": "hub", "MQTT_PASSWORD": "s3cret"}


class MessagesPasswordTests(unittest.IsolatedAsyncioTestCase):
    """The broker takes a password (driver-layer/mqtt-auth.sh); the engine has to be told it, once per password."""

    async def test_adding_messages_sends_the_password_and_remembers_it(self):
        add = FakeAdd([form([("broker", None), ("port", 1883), ("username", None), ("password", None)]), {"type": "create_entry"}])
        hub = FakeHub(add, FakeHA(), env=AUTH); p = provision.Provision(hub); hub.provision = p
        with patch.object(provision, "probe", _only({1883})):
            await p.refresh()
        self.assertEqual(add.submitted[0]["username"], "hub")
        self.assertEqual(add.submitted[0]["password"], "s3cret")
        self.assertEqual(hub.settings.get("mqtt_auth"), p._mqtt_fp())
        self.assertEqual(p.parts["mqtt"]["state"], "ready")

    async def test_without_a_password_nothing_is_sent_for_one(self):
        add = FakeAdd([form([("broker", None), ("username", None), ("password", None)]), {"type": "create_entry"}])
        hub = FakeHub(add); p = provision.Provision(hub); hub.provision = p
        with patch.object(provision, "probe", _only({1883})):
            await p.refresh()
        self.assertNotIn("username", add.submitted[0])
        self.assertIsNone(hub.settings.get("mqtt_auth"))

    async def test_an_entry_that_predates_the_password_is_reconfigured_in_place(self):
        add = FakeAdd([form([("broker", None), ("username", None), ("password", None)]), {"type": "abort", "reason": "Re-configuration was successful", "reason_id": "reconfigure_successful"}])
        add.reconfigured = []
        hub = FakeHub(add, FakeHA(entries=["mqtt"]), env=AUTH); p = provision.Provision(hub); hub.provision = p
        with patch.object(provision, "probe", _only({1883})):
            await p.refresh()
        self.assertEqual(add.reconfigured, [("mqtt", "e-mqtt")])
        self.assertEqual(add.submitted, [{"broker": "localhost", "username": "hub", "password": "s3cret"}])
        self.assertEqual(add.cancelled, [])
        self.assertEqual(hub.settings.get("mqtt_auth"), p._mqtt_fp())
        self.assertEqual(p.parts["mqtt"]["state"], "ready")
        self.assertIn("Messages signed in", [a[3] for a, _ in hub.log.rows])

    async def test_an_entry_that_already_knows_the_password_is_left_alone(self):
        add = FakeAdd([]); add.reconfigured = []
        hub = FakeHub(add, FakeHA(entries=["mqtt"]), env=AUTH); p = provision.Provision(hub); hub.provision = p
        hub.settings.set(mqtt_auth=p._mqtt_fp())
        with patch.object(provision, "probe", _only({1883})):
            await p.refresh()
        self.assertEqual(add.reconfigured, [])
        self.assertEqual(p.parts["mqtt"]["state"], "ready")

    async def test_a_failed_reconfigure_says_so_and_backs_off(self):
        add = FakeAdd([form([("broker", None)], errors={"base": "Cannot connect"})]); add.reconfigured = []
        hub = FakeHub(add, FakeHA(entries=["mqtt"]), env=AUTH); p = provision.Provision(hub); hub.provision = p
        with patch.object(provision, "probe", _only({1883})):
            await p.refresh()
        self.assertEqual(p.parts["mqtt"]["state"], "failed")
        self.assertIn("Cannot connect", p.parts["mqtt"]["text"])
        self.assertIsNone(hub.settings.get("mqtt_auth"))
        self.assertEqual(add.cancelled, ["f1"])
        with patch.object(provision, "probe", _only({1883})):
            await p.refresh()                      # inside RETRY_AFTER: not asked again
        self.assertEqual(len(add.reconfigured), 1)


class UnitTests(unittest.TestCase):
    def test_us_zones_read_in_fahrenheit(self):
        from hub.api import unit_system_for
        self.assertEqual([unit_system_for(z) for z in ("America/Chicago", "America/Indiana/Indianapolis", "Pacific/Honolulu", "Europe/London", "America/Toronto")],
                         ["us_customary", "us_customary", "us_customary", "metric", "metric"])


class FillTests(unittest.TestCase):
    def test_sections_and_required_fields_get_quiet_answers(self):
        fields = [{"name": "broker", "kind": "text", "required": True, "default": None},
                  {"name": "port", "kind": "number", "required": True, "default": 1883},
                  {"name": "username", "kind": "text", "required": False, "default": None},
                  {"name": "other_settings", "kind": "section", "required": True, "default": None, "fields": [
                      {"name": "client_id", "kind": "text", "required": False, "default": None},
                      {"name": "set_client_cert", "kind": "boolean", "required": True, "default": None},
                      {"name": "set_ca_cert", "kind": "select", "required": True, "default": None, "options": [{"value": "off", "label": "Off"}, {"value": "auto", "label": "Auto"}]},
                      {"name": "transport", "kind": "select", "required": True, "default": "tcp", "options": [{"value": "tcp", "label": "TCP"}]}]}]
        self.assertEqual(provision.fill(fields, {"broker": "localhost", "port": 1883}),
                         {"broker": "localhost", "port": 1883, "other_settings": {"set_client_cert": False, "set_ca_cert": "off", "transport": "tcp"}})


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

    async def test_integrations_ha_could_not_set_up_are_problems(self):
        async def fake_probe(host, port, timeout=1.5): return False
        nest = {"domain": "nest", "entry_id": "e-nest", "title": "home-hub", "state": "setup_retry", "reason": "Error communicating with the Device Access API"}
        add = FakeAdd([]); add.rested = []
        hub = FakeHub(add, FakeHA(entries=["mqtt"], broken=[nest])); hub.provision = p = provision.Provision(hub)
        with patch.object(provision, "probe", fake_probe):
            await p.refresh()
            self.assertEqual(p.problems, [{"entry_id": "e-nest", "domain": "nest", "title": "home-hub", "state": "setup_retry", "reason": "Error communicating with the Device Access API"}])
            hub.ha.broken = []
            with patch.object(provision.asyncio, "sleep", _nosleep):
                await p.retry("e-nest")
        self.assertEqual((add.rested, p.problems), ([("POST", "/api/config/config_entries/entry/e-nest/reload")], []))

    async def test_an_account_waiting_to_be_signed_in_is_kept_and_speaks_for_its_complaint(self):
        """A dead token makes HA complain about the entry *and* open a flow. Only the flow is worth offering."""
        async def fake_probe(host, port, timeout=1.5): return False
        nest = {"domain": "nest", "entry_id": "e-nest", "title": "home-hub", "state": "setup_retry", "reason": "expired"}
        hue = {"domain": "hue", "entry_id": "e-hue", "title": "Hue bridge", "state": "setup_error", "reason": "no route"}
        waiting = [{"flow_id": "f-nest", "handler": "nest", "kind": "Google Nest", "title": "home-hub", "source": "reauth"}]
        add = FakeAdd([], waiting=waiting)
        hub = FakeHub(add, FakeHA(broken=[nest, hue])); hub.provision = p = provision.Provision(hub)
        with patch.object(provision, "probe", fake_probe):
            await p.refresh()
        self.assertEqual(p.sign_ins, waiting)
        self.assertEqual([q["domain"] for q in p.problems], ["hue"])    # nest's complaint gave way to its sign-in

    async def test_driver_host_comes_from_env(self):
        hub = FakeHub(); hub.env = {"HUB_DRIVER_HOST": "mosquitto"}
        self.assertEqual(provision.Provision(hub).host, "mosquitto")
