"""Run from brain/: .venv/bin/python -m unittest tests.test_onboarding -v"""
import unittest
from hub import onboarding


class FakeHA:
    def __init__(self, domains=("nest",), existing=()):
        self.domains, self.existing, self.created = list(domains), list(existing), []
    async def send(self, type_, **kw):
        if type_ == "application_credentials/config":
            return {"domains": self.domains, "integrations": {"nest": {"description_placeholders": {"oauth_creds_url": "https://c", "oauth_consent_url": "https://s", "redirect_url": "https://my/redirect"}}}}
        if type_ == "application_credentials/list": return [{"domain": d} for d in self.existing]
        if type_ == "application_credentials/create": self.created.append(kw); self.existing.append(kw["domain"]); return {}
        if type_ == "manifest/get": return {"name": {"nest": "Google Nest"}.get(kw["integration"], kw["integration"])}
        raise AssertionError(type_)


class FakeLog:
    def add(self, *a, **kw): pass


class FakeHub:
    def __init__(self, ha): self.ha, self.env, self.log = ha, {"HUB_HOST": "hub.local"}, FakeLog()


async def _ready(v): return v


class MarkdownTests(unittest.TestCase):
    def test_steps_links_bold_and_escaping(self):
        out = onboarding._md("Go to the [console]({url}) & press **Create**.\n\n1. one\n1. two <b>x</b>\n\nDone {missing}", {"url": "https://x?a=1&b=2"})
        self.assertEqual(out, '<p>Go to the <a href="https://x?a=1&amp;b=2" target="_blank" rel="noopener">console</a> &amp; press <b>Create</b>.</p>'
                              '<ol><li>one</li><li>two x</li></ol><p>Done {missing}</p>')
        self.assertEqual(onboarding._md("", {}), "")


class CatalogTests(unittest.TestCase):
    def test_brands_are_flattened_and_internals_hidden(self):
        core = {
            "roku": {"name": "Roku", "integration_type": "device", "config_flow": True, "iot_class": "local_polling"},
            "mqtt": {"name": "MQTT", "integration_type": "hub", "config_flow": True},
            "google": {"name": "Google", "integrations": {
                "nest": {"name": "Google Nest", "integration_type": "hub", "config_flow": True, "iot_class": "cloud_push"},
                "cast": {"name": "Google Cast", "integration_type": "hub", "config_flow": True, "iot_class": "local_polling"},
                "google_maps": {"name": "Google Maps", "integration_type": "hub", "config_flow": False},
                "google_translate": {"integration_type": "service", "config_flow": True}}},
            "tplink": {"name": "TP-Link", "integrations": {"tplink_tapo": {"integration_type": "virtual", "supported_by": "tplink"}}},
        }
        rows = onboarding.catalog_from(core)
        self.assertEqual([r["domain"] for r in rows], ["cast", "nest", "roku"])
        self.assertEqual(rows[1], {"domain": "nest", "name": "Google Nest", "brand": "Google", "local": False})
        self.assertIsNone(rows[2]["brand"])


class FieldTests(unittest.TestCase):
    def test_expandable_becomes_a_section_with_nested_fields(self):
        f = onboarding._field({"type": "expandable", "name": "other_settings", "required": True, "expanded": False,
                               "schema": [{"name": "set_client_cert", "required": True, "selector": {"boolean": {}}},
                                          {"name": "transport", "required": True, "default": "tcp", "selector": {"select": {"options": [{"value": "tcp", "label": "TCP"}]}}}]},
                              {"component.mqtt.config.step.broker.sections.other_settings.name": "Advanced options"}, "component.mqtt.config", "broker", {})
        self.assertEqual((f["kind"], f["label"], f["required"], f["expanded"]), ("section", "Advanced options", True, False))
        self.assertEqual([(g["name"], g["kind"]) for g in f["fields"]], [("set_client_cert", "boolean"), ("transport", "select")])


class CredentialsTests(unittest.IsolatedAsyncioTestCase):
    async def test_nest_asks_for_a_key_first(self):
        ha = FakeHA(); add = onboarding.Onboarding(FakeHub(ha))
        step = await add.start("nest")
        self.assertEqual(step["type"], "credentials")
        self.assertEqual(step["kind"], "Google Nest")
        self.assertIn("https://my/redirect", step["description"])
        self.assertIn("http://hub.local:8123", step["description"])
        self.assertIn('href="https://c"', step["description"])
        self.assertEqual([f["name"] for f in step["fields"]], ["client_id", "client_secret"])

    async def test_no_key_needed_when_one_exists_or_not_required(self):
        add = onboarding.Onboarding(FakeHub(FakeHA(existing=["nest"])))
        self.assertIsNone(await add.needs_credentials("nest"))
        self.assertIsNone(await add.needs_credentials("roku"))

    async def test_saving_the_key_then_starts_the_flow(self):
        ha = FakeHA(); add = onboarding.Onboarding(FakeHub(ha))
        started = []
        async def fake_start(handler): started.append(handler); return {"type": "form", "handler": handler}
        add.start = fake_start
        r = await add.set_credentials("nest", "id", "secret")
        self.assertEqual(ha.created, [{"domain": "nest", "client_id": "id", "client_secret": "secret", "name": "home-hub"}])
        self.assertEqual((started, r["type"]), (["nest"], "form"))

    async def test_a_key_files_project_id_prefills_the_later_step(self):
        ha = FakeHA(); add = onboarding.Onboarding(FakeHub(ha))
        add.start = lambda handler: _ready({"type": "form", "handler": handler})
        await add.set_credentials("nest", "id", "secret", {"cloud_project_id": "my-project-123", "junk": 5, "empty": " "})
        step = await add.describe({"type": "form", "flow_id": "f", "handler": "nest", "step_id": "cloud_project",
                                   "data_schema": [{"name": "cloud_project_id", "type": "string", "required": True}, {"name": "other", "type": "string", "default": "x"}]})
        self.assertEqual([f["default"] for f in step["fields"]], ["my-project-123", "x"])
        self.assertEqual(add._hints["nest"], {"cloud_project_id": "my-project-123"})

    async def test_generic_guide_for_other_makers(self):
        ha = FakeHA(domains=["tesla_fleet"]); add = onboarding.Onboarding(FakeHub(ha))
        step = await add.credentials_step("tesla_fleet")
        self.assertIn("tesla_fleet asks each home", step["description"])
        self.assertIn("home-assistant.io/integrations/tesla_fleet", step["description"])
