# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The address in the name: what home.elyir.app answers, to whom, and what it never will."""
import base64, socket, tempfile, unittest
from pathlib import Path

from dnslib import QTYPE, RCODE, DNSRecord
from fastapi.testclient import TestClient

from app import make
from home import Home, private_address, serve
from registry import DAY, Registry

VALUE = "LHDhK3oGRvkiefQnx7OOczTY5Tic_xZ6HcMOc_gmtoM"


def free_port() -> int:
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.t = 1_790_000_000.0
        self.r = Registry(Path(self.dir.name) / "houses.db", now=lambda: self.t)
        self.home = Home(self.r, now=lambda: self.t)
        self.secret = self.r.claim("jordan")["secret"]
        self.r.grant("jordan", self.t + 365 * DAY)
        self.other = self.r.claim("palace")["secret"]      # claimed, never paid for

    def tearDown(self):
        self.r.db.close(); self.dir.cleanup()


class Names(Base):
    def test_only_addresses_inside_a_house(self):
        for ok, ip in (("192-168-86-53", "192.168.86.53"), ("10-0-0-2", "10.0.0.2"), ("172-16-4-1", "172.16.4.1"), ("172-31-255-255", "172.31.255.255")):
            self.assertEqual(private_address(ok), ip)
        for bad in ("8-8-8-8", "172-32-0-1", "127-0-0-1", "192-168-1", "192-168-1-256", "169-254-1-1", "nope"):
            self.assertIsNone(private_address(bad), bad)

    def test_a_carried_house_is_answered_with_its_own_address(self):
        self.assertEqual(self.home.address("192-168-86-53.jordan.home.elyir.app."), "192.168.86.53")
        self.assertEqual(self.home.lan_name("jordan", "192.168.86.53"), "192-168-86-53.jordan.home.elyir.app")

    def test_nothing_for_a_house_nobody_pays_for_or_nobody_has(self):
        self.assertIsNone(self.home.address("192-168-86-53.palace.home.elyir.app"))
        self.assertIsNone(self.home.address("192-168-86-53.nobody.home.elyir.app"))

    def test_nothing_that_is_not_shaped_like_a_house_name(self):
        for n in ("8-8-8-8.jordan.home.elyir.app", "192-168-86-53.home.elyir.app", "x.192-168-86-53.jordan.home.elyir.app",
                  "192-168-86-53.jordan.elyir.app", "192-168-86-53.jordan.home.evil.com"):
            self.assertIsNone(self.home.address(n), n)


class Challenges(Base):
    NAME = "_acme-challenge.192-168-86-53.jordan.home.elyir.app."

    def test_a_house_answers_a_challenge_for_its_own_name(self):
        self.assertIsNone(self.home.present("jordan", self.NAME, VALUE))
        self.assertEqual(self.home.txt(self.NAME), [VALUE])
        self.home.cleanup("jordan", self.NAME)
        self.assertEqual(self.home.txt(self.NAME), [])

    def test_and_never_for_another_houses(self):
        self.assertEqual(self.home.present("palace", self.NAME, VALUE), "a house may answer challenges for its own names only")
        self.assertEqual(self.home.present("jordan", "_acme-challenge.8-8-8-8.jordan.home.elyir.app", VALUE), "that is not a challenge name under home")
        self.assertEqual(self.home.present("jordan", "_acme-challenge.jordan.elyir.app", VALUE), "that is not a challenge name under home")
        self.assertEqual(self.home.present("jordan", self.NAME, "bad value; rm"), "that does not look like a challenge value")

    def test_a_house_nobody_pays_for_gets_no_certificate(self):
        self.assertEqual(self.home.present("palace", "_acme-challenge.192-168-86-53.palace.home.elyir.app", VALUE),
                         "this house is not carried by this relay")

    def test_one_nobody_cleaned_up_goes_within_the_hour(self):
        self.home.present("jordan", self.NAME, VALUE)
        self.t += 3601
        self.assertEqual(self.home.txt(self.NAME), [])

    def test_over_http_as_lego_sends_it(self):
        c = TestClient(make(self.r, now=lambda: self.t, home=self.home))
        auth = {"Authorization": "Basic " + base64.b64encode(f"jordan:{self.secret}".encode()).decode()}
        self.assertEqual(c.post("/acme/present", json={"fqdn": self.NAME, "value": VALUE}, headers=auth).status_code, 200)
        self.assertEqual(self.home.txt(self.NAME), [VALUE])
        self.assertEqual(c.post("/acme/cleanup", json={"fqdn": self.NAME, "value": VALUE}, headers=auth).status_code, 200)
        wrong = {"Authorization": "Basic " + base64.b64encode(b"jordan:guess").decode()}
        self.assertEqual(c.post("/acme/present", json={"fqdn": self.NAME, "value": VALUE}, headers=wrong).status_code, 401)
        theirs = {"Authorization": "Basic " + base64.b64encode(f"palace:{self.other}".encode()).decode()}
        self.assertEqual(c.post("/acme/present", json={"fqdn": self.NAME, "value": VALUE}, headers=theirs).status_code, 403)


class OverDNS(Base):
    """The real server, asked real questions over UDP and TCP."""
    def setUp(self):
        super().setUp()
        self.port = free_port()
        self.servers = serve(self.home, ns="ns1.elyir.app", port=self.port, address="127.0.0.1")

    def tearDown(self):
        for s in self.servers: s.stop()
        super().tearDown()

    def ask(self, name, qtype="A", tcp=False):
        return DNSRecord.parse(DNSRecord.question(name, qtype).send("127.0.0.1", self.port, tcp=tcp, timeout=3))

    def test_a_carried_house_resolves_to_its_lan_address(self):
        for tcp in (False, True):
            r = self.ask("192-168-86-53.jordan.home.elyir.app", tcp=tcp)
            self.assertEqual(r.header.rcode, RCODE.NOERROR); self.assertTrue(r.header.aa)
            self.assertEqual([str(a.rdata) for a in r.rr], ["192.168.86.53"])

    def test_the_challenge_is_served_as_txt(self):
        self.home.present("jordan", "_acme-challenge.192-168-86-53.jordan.home.elyir.app", VALUE)
        r = self.ask("_acme-challenge.192-168-86-53.jordan.home.elyir.app", "TXT")
        self.assertEqual([str(a.rdata).strip('"') for a in r.rr], [VALUE])

    def test_names_that_are_not_there_are_nxdomain_and_the_rest_of_the_internet_is_refused(self):
        self.assertEqual(self.ask("8-8-8-8.jordan.home.elyir.app").header.rcode, RCODE.NXDOMAIN)
        self.assertEqual(self.ask("192-168-86-53.palace.home.elyir.app").header.rcode, RCODE.NXDOMAIN)
        self.assertEqual(self.ask("example.com").header.rcode, RCODE.REFUSED)
        self.assertEqual(self.ask("jordan.elyir.app").header.rcode, RCODE.REFUSED)

    def test_a_name_with_a_challenge_below_it_is_nodata_not_nxdomain(self):
        r = self.ask("192-168-86-53.jordan.home.elyir.app", "TXT")
        self.assertEqual(r.header.rcode, RCODE.NOERROR); self.assertEqual(r.rr, [])

    def test_the_zone_says_only_lets_encrypt_and_no_wildcards(self):
        r = self.ask("home.elyir.app", "CAA")
        said = sorted(str(a.rdata) for a in r.rr)
        self.assertEqual(said, ['0 issue "letsencrypt.org"', '0 issuewild ";"'])
        self.assertEqual(QTYPE[self.ask("home.elyir.app", "NS").rr[0].rtype], "NS")


if __name__ == "__main__":
    unittest.main()
