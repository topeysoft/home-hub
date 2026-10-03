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
