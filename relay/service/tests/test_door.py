# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every route a hub calls is let through api.elyir.app's door, and the relay's own route never is.

The door is a Caddy on the relay box (relay/terraform/cloud-init.yaml.tftpl) that passes an explicit
list of paths. /acme/* was added to the service and not to that list, so every house's LAN certificate
failed with a 404 that never reached the service -- found on the maker's hub on 2 October 2026. The
tests in miniature had pointed lego straight at the service, which is how it got past them.
"""
import re, unittest
from pathlib import Path

from app import make
from registry import Registry

CLOUD_INIT = Path(__file__).resolve().parents[2] / "terraform" / "cloud-init.yaml.tftpl"


def passed() -> list[str]:
    m = re.search(r"@public path (.+)", CLOUD_INIT.read_text())
    assert m, "the api door's path list is gone from cloud-init"
    return m.group(1).split()


def let_through(path: str) -> bool:
    """Caddy's path matcher: an exact path, or a prefix ending in /*."""
    return any(path == p or (p.endswith("/*") and path.startswith(p[:-1])) for p in passed())


class Door(unittest.TestCase):
    def setUp(self):
        self.app = make(Registry(":memory:"))

    def test_every_route_a_hub_calls_is_let_through(self):
        routes = {r.path for r in self.app.routes if getattr(r, "methods", None)}
        # /nearby is not a hub's: it has a name of its own, nearby.<zone>, with no IPv6 record (cloud-init, dns.tf).
        for path in sorted(routes - {"/frps", "/nearby"}):
            example = re.sub(r"\{[^}]+\}", "x", path)
            self.assertTrue(let_through(example), f"api.elyir.app's door does not pass {path}")

    def test_the_relays_own_route_never_is(self):
        self.assertFalse(let_through("/frps"))

    def test_nearby_has_its_own_name_and_only_its_one_route(self):
        text = CLOUD_INIT.read_text()
        site = re.search(r"nearby\.\$\{zone\}:9443 \{(.*?)\n      \}\n", text, re.S)
        self.assertTrue(site, "nearby.<zone> has no site in cloud-init")
        self.assertIn("handle /nearby {", site.group(1))
        self.assertIn("respond 404", site.group(1))
        self.assertNotIn("/frps", site.group(1))


class Apps(unittest.TestCase):
    """The two apps this box serves are set up the same way, piece for piece. A piece missing from one is a
    name that is never carried, a site that serves nothing, or a page that cannot read /nearby -- and none of
    those shows until somebody opens the app on a phone."""
    text = CLOUD_INIT.read_text()

    def site(self, name: str) -> str:
        m = re.search(name + r"\.\$\{zone\}:9443 \{(.*?)\n      \}\n", self.text, re.S)
        self.assertTrue(m, f"{name}.<zone> has no site in cloud-init")
        return m.group(1)

    def test_every_piece_of_each_app_is_there(self):
        for name in ("printers", "houses"):
            for piece in (f"/etc/frp/{name}-frpc.toml", f'user = "{name}"', f'metadatas.secret = "${{{name}_secret}}"',
                          f'customDomains = ["{name}.${{zone}}"]', f"relay-{name}-frpc.service",
                          f"systemctl enable --now relay-{name}-frpc", f"-v /var/lib/relay/{name}:/srv/{name}:ro",
                          f"/var/lib/relay/{name}", f"-e RELAY_{name.upper()}_SECRET=${{{name}_secret}}"):
                self.assertIn(piece, self.text, f"{name}: {piece}")
            site = self.site(name)
            self.assertIn(f"root * /srv/{name}/current", site)
            self.assertIn("try_files {path} /index.html", site)
            self.assertIn("alt_tlsalpn_port 9443", site)

    def test_the_houses_app_is_kept_as_tightly_as_the_printer_app(self):
        csp = re.compile(r'Content-Security-Policy "([^"]+)"')
        self.assertEqual(csp.search(self.site("houses")).group(1), csp.search(self.site("printers")).group(1))
        houses = self.site("houses")
        self.assertIn("frame-ancestors 'none'", houses)
        self.assertIn("script-src 'self';", houses)
        # The app uses none of them itself; it passes them on only to a house it frames, under the zone.
        self.assertIn('Permissions-Policy `camera=("https://*.${zone}"), microphone=("https://*.${zone}"), geolocation=("https://*.${zone}")`', houses)

    def test_both_apps_may_read_nearby_on_the_box(self):
        m = re.search(r"-e RELAY_NEARBY_ORIGINS=(\S+)", self.text)
        self.assertTrue(m, "the box does not say who may read /nearby")
        self.assertEqual(m.group(1).split(","), ["https://printers.${zone}", "https://houses.${zone}"])

    def test_each_apps_secret_is_handed_to_the_box(self):
        tf = (CLOUD_INIT.parent / "relay.tf").read_text()
        for name in ("printers", "houses"):
            self.assertIn(f'{name}_secret = sha256("{name}:${{var.relay_auth_token}}")', tf)
