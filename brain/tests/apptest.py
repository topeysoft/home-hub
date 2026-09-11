"""A brain to make requests against, with no engine behind it and nothing on disk that outlives the test.

The routes in hub/api.py reach for one module-level `hub`, so a test gets its own by building a Hub
with its settings and event log pointed at a temp directory and putting that in the module's place.
Nothing here starts the lifecycle loop: TestClient only runs lifespan inside a `with`, and every test
below wants a house that holds still rather than one that reconnects underneath it.

Run from brain/: .venv/bin/python -m unittest -v
"""
import shutil, tempfile, time, unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from hub import api, backup as backup_mod, phones as phones_mod, rules as rules_mod, updates as updates_mod
from hub.events import EventLog
from hub.settings import Settings

# Modules that work out where the hub's state lives at import time. A test must not read the developer's
# own house, and must never write to it: every one of these is pointed at the temp directory instead.
DATA_BOUND = [(phones_mod, "DATA", lambda d: d), (rules_mod, "RULES_PATH", lambda d: d / "rules.json"),
              (updates_mod, "REQUEST", lambda d: d / "update.request"), (updates_mod, "STATE", lambda d: d / "update.json"),
              (backup_mod, "REQUEST", lambda d: d / "restore.request"), (backup_mod, "STATE", lambda d: d / "restore.json"),
              (backup_mod, "ARCHIVE", lambda d: d / "restore.tar.gz"), (backup_mod, "DATA", lambda d: d)]


def area(area_id, name):
    return {"area_id": area_id, "name": name}


def hardware(id, area_id=None, name="", manufacturer="Acme", model="Thing"):
    return {"id": id, "area_id": area_id, "name": name, "manufacturer": manufacturer, "model": model, "name_by_user": None}


def entity(entity_id, device_id=None, area_id=None, **kw):
    return {"entity_id": entity_id, "device_id": device_id, "area_id": area_id, "disabled_by": None,
            "hidden_by": None, "entity_category": None, "original_name": None, "original_device_class": None, **kw}


def state(entity_id, state, **attrs):
    # A fresh timestamp on every state: model.seen_at reads these, and health treats an old one as a device gone quiet.
    now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())
    return {"entity_id": entity_id, "state": state, "attributes": attrs, "last_changed": now, "last_updated": now, "last_reported": now}


def house():
    """A small house that still has one of everything the routes act on: a dimmable light, a switch, a player,
    a thermostat, a fan, a lock, a motion sensor, a temperature reading, and one thing in no room yet."""
    areas = [area("living", "Living room"), area("kitchen", "Kitchen"), area("front", "Front door")]
    devices = [hardware("hw-ceiling", "living", "Ceiling light"), hardware("hw-tv", "living", "TV"),
               hardware("hw-nest", "living", "Thermostat"), hardware("hw-fan", "living", "Fan"),
               hardware("hw-kitchen", "kitchen", "Kitchen lights"), hardware("hw-kettle", "kitchen", "Kettle"),
               hardware("hw-motion", "kitchen", "Motion"), hardware("hw-temp", "kitchen", "Temperature"),
               hardware("hw-lock", "front", "Front door"), hardware("hw-new", None, "New lamp")]
    entities = [entity("light.ceiling", "hw-ceiling"), entity("media_player.tv", "hw-tv"),
                entity("climate.nest", "hw-nest"), entity("fan.ceiling_fan", "hw-fan"),
                entity("light.kitchen", "hw-kitchen"), entity("switch.kettle", "hw-kettle"),
                entity("binary_sensor.kitchen_motion", "hw-motion", original_device_class="motion"),
                entity("sensor.kitchen_temp", "hw-temp", original_device_class="temperature"),
                entity("lock.front", "hw-lock"), entity("light.new_lamp", "hw-new"),
                # Never product surface: a diagnostic reading and an entity HA itself has switched off.
                entity("sensor.tv_signal", "hw-tv", entity_category="diagnostic", original_device_class="temperature"),
                entity("light.broken", "hw-ceiling", disabled_by="integration")]
    states = [state("light.ceiling", "on", friendly_name="Ceiling light", brightness=200, supported_color_modes=["brightness"]),
              state("media_player.tv", "playing", friendly_name="TV", media_title="The Bear", volume_level=0.4),
              state("climate.nest", "cool", friendly_name="Thermostat", current_temperature=74, temperature=71,
                    hvac_modes=["heat", "cool", "off"], fan_modes=["on", "auto"], fan_mode="auto"),
              state("fan.ceiling_fan", "off", friendly_name="Ceiling fan", percentage=0),
              state("light.kitchen", "off", friendly_name="Kitchen lights", supported_color_modes=["brightness"]),
              state("switch.kettle", "off", friendly_name="Kettle"),
              state("binary_sensor.kitchen_motion", "off", friendly_name="Motion", device_class="motion"),
              state("sensor.kitchen_temp", "68.2", friendly_name="Temperature", device_class="temperature", unit_of_measurement="°F"),
              state("lock.front", "locked", friendly_name="Front door"),
              state("light.new_lamp", "off", friendly_name="New lamp", supported_color_modes=["brightness"]),
              state("sensor.tv_signal", "40", friendly_name="TV signal", device_class="temperature"),
              state("light.broken", "off", friendly_name="Broken")]
    return areas, devices, entities, states


class FakeHA:
    """Stands where the websocket adapter stands. Records what the house was told to do, so a test can
    assert on the call rather than on a light that no driver is there to change."""
    def __init__(self):
        self.calls = []       # (domain, service, entity_id, data)
        self.sent = []        # (type, kwargs) for everything that is not a service call
        self.answers = {}     # type -> result, or a callable taking the kwargs
        self.fail = {}        # type -> exception to raise instead

    async def call(self, domain, service, entity_id=None, **data):
        self.calls.append((domain, service, entity_id, data))
        return {}

    # What HA answers when a test has not said otherwise. Registry writes answer with the row they made,
    # which the routes read straight back, so a bare None here would look like a crash rather than a stub.
    DEFAULTS = {"config/area_registry/create": lambda name=None, **kw: {"area_id": (name or "").lower().replace(" ", "_"), "name": name},
                "config/area_registry/update": lambda **kw: {"area_id": kw.get("area_id"), "name": kw.get("name")},
                "config/area_registry/delete": lambda **kw: None,
                "config/entity_registry/update": lambda **kw: {"entity_entry": {"entity_id": kw.get("entity_id")}},
                "config/device_registry/update": lambda **kw: {"id": kw.get("device_id")},
                "get_config": lambda **kw: {"unit_system": {"temperature": "\u00b0F"}, "time_zone": "America/Chicago",
                                            "latitude": 41.88, "longitude": -87.63, "location_name": "Home"}}

    async def send(self, type_, **kw):
        self.sent.append((type_, kw))
        if type_ in self.fail: raise self.fail[type_]
        a = self.answers[type_] if type_ in self.answers else self.DEFAULTS.get(type_)
        return a(**kw) if callable(a) else a

    async def snapshot(self): return house()
    async def close(self): pass
    async def wait_closed(self): pass
    def on_event(self, cb): self.listener = cb

    def called(self, domain=None, service=None, entity_id=None):
        """The recorded calls narrowed to the ones a test is asking about."""
        return [c for c in self.calls if (domain is None or c[0] == domain)
                and (service is None or c[1] == service) and (entity_id is None or c[2] == entity_id)]


class ApiTest(unittest.TestCase):
    """Base for anything that makes a request. `self.client` talks to a hub that is ready, holds the
    house above, and answers for a driver layer that is not running."""
    ready = True          # subclasses testing the starting screens turn this off
    seed_rules = False    # turn on to start from the rules the product ships, the way a new hub does

    def setUp(self):
        self.data = Path(tempfile.mkdtemp(prefix="hub-test-"))
        self.addCleanup(shutil.rmtree, self.data, True)
        for module, name, where in DATA_BOUND:
            p = mock.patch.object(module, name, where(self.data))
            p.start(); self.addCleanup(p.stop)
        # A hub with no rules unless the test writes some. Without this the engine seeds from the repo's
        # rules.json, and a test would be asserting against whatever rules the product happens to ship today.
        if not self.seed_rules: (self.data / "rules.json").write_text('{"rules": []}')
        # Settings' path default is bound at definition, so the temp directory has to be handed in by name.
        with mock.patch.object(api, "Settings", lambda: Settings(self.data / "settings.json")), \
             mock.patch.object(api, "DATA", self.data), \
             mock.patch.object(api, "EventLog", lambda _p: EventLog(self.data / "events.db")):
            self.hub = api.Hub()
        self.addCleanup(self.hub.log.db.close)   # sqlite holds the temp file open; a test that leaks one warns
        self.ha = FakeHA()
        self.hub.ha = self.ha
        self.hub.home.build(*house())
        self.hub.location = {"name": "Home", "lat": 41.88, "lon": -87.63}
        if self.ready: self.hub.driver = "ready"
        self.broadcasts = []
        self.hub._broadcast = self.broadcasts.append   # no websockets are open; keep what would have gone out
        self._swap = mock.patch.object(api, "hub", self.hub)
        self._swap.start(); self.addCleanup(self._swap.stop)
        self.client = TestClient(api.app)
        self.addCleanup(self.client.close)

    # ---- helpers the tests read better for ----
    def sent(self, kind):
        """Broadcasts of one type, decoded. The panel learns about every change this way, so a route that
        changes the house and says nothing is a bug a test should see."""
        import json
        out = []
        for m in self.broadcasts:
            try: d = json.loads(m)
            except Exception: continue
            if d.get("type") == kind: out.append(d)
        return out

    def lock_the_house(self, code="1234"):
        """Give the house a code, the way setup does. Returns the code."""
        self.hub.lock.set(code)
        return code
