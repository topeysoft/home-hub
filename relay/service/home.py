# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The address in the name: how a phone on the house's public name reaches the hub directly at home.

A house's public name, temi.elyir.app, resolves to the relay -- right for a phone away, wrong for one on
the sofa, which would go out to the relay and back for every tap (docs/away.md: the relay is only in the
path when a phone is away). So each house also has a name that spells its own LAN address,
192-168-86-53.temi.home.elyir.app, and this answers it with that address. It is the shape of Plex's
plex.direct, chosen on 1 October 2026 because NO HOUSE EVER CAUSES A DNS WRITE: Terraform delegates
home.elyir.app here once, and every house's name is worked out from the question rather than stored.

Three rules keep it from being anything else. It answers only for houses the relay carries, so it is
not a general service for pointing names at addresses. It answers only private addresses (10/8,
172.16/12, 192.168/16), so a name under elyir.app can never be aimed at somebody else's public server.
And the certificate for that name is proved over DNS-01 with a TXT record a house can set only for its
own names, with its own secret -- served here, so no house ever holds a Cloudflare credential and there
is still no wildcard certificate anywhere under the zone.
"""
import ipaddress, re, time

from dnslib import CAA, NS, QTYPE, RCODE, RR, SOA, TXT, A, DNSLabel, DNSRecord
from dnslib.server import BaseResolver, DNSServer

CHALLENGE_TTL = 3600          # a TXT record nobody cleans up is gone within the hour
PRIVATE = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
DASHED = re.compile(r"^(\d{1,3})-(\d{1,3})-(\d{1,3})-(\d{1,3})$")

SCHEMA = """
create table if not exists challenges (
    fqdn    text primary key,     -- _acme-challenge.<address>.<house>.home.<zone>, no trailing dot
    house   text not null,
    value   text not null,
    set_at  real not null
)"""


def private_address(label: str) -> str | None:
    """192-168-86-53 -> 192.168.86.53, if that is an address inside a house and nothing else."""
    m = DASHED.match(label)
    if not m: return None
    try: ip = ipaddress.ip_address(".".join(m.groups()))
    except ValueError: return None
    return str(ip) if any(ip in n for n in PRIVATE) else None


class Home:
    def __init__(self, registry, now=time.time):
        self.registry, self.now = registry, now
        self.zone = f"home.{registry.zone}"
        self.registry.db.execute(SCHEMA)

    def lan_name(self, house: str, address: str) -> str:
        return f"{address.replace('.', '-')}.{house}.{self.zone}"

    def parse(self, name: str) -> tuple[str, str, bool] | None:
        """<address>.<house>.home.<zone>, or the same with _acme-challenge in front: (house, address, challenge)."""
        name = name.rstrip(".").lower()
        if not name.endswith("." + self.zone): return None
        labels = name[: -len(self.zone) - 1].split(".")
        challenge = bool(labels) and labels[0] == "_acme-challenge"
        if challenge: labels = labels[1:]
        if len(labels) != 2: return None
        address = private_address(labels[0])
        return (labels[1], address, challenge) if address else None

    def address(self, name: str) -> str | None:
        """The A record for a LAN name, if it is a carried house's and spells a private address."""
        p = self.parse(name)
        if not p or p[2]: return None
        house, address, _ = p
        return address if self.registry.status(house)["carried"] else None

    # ---- the DNS-01 challenge, set by the house for its own names ----
    def present(self, house: str, fqdn: str, value: str) -> str | None:
        """Put a challenge up. None is done; a string is why not."""
        p = self.parse(fqdn)
        if not p or not p[2]: return "that is not a challenge name under home"
        if p[0] != house: return "a house may answer challenges for its own names only"
        if not self.registry.status(house)["carried"]: return "this house is not carried by this relay"
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", value or ""): return "that does not look like a challenge value"
        self.registry.db.execute("insert into challenges (fqdn, house, value, set_at) values (?, ?, ?, ?) "
                                 "on conflict(fqdn) do update set value = excluded.value, set_at = excluded.set_at",
                                 (fqdn.rstrip(".").lower(), house, value, self.now()))
        return None

    def cleanup(self, house: str, fqdn: str):
        self.registry.db.execute("delete from challenges where fqdn = ? and house = ?", (fqdn.rstrip(".").lower(), house))

    def txt(self, name: str) -> list[str]:
        self.registry.db.execute("delete from challenges where set_at < ?", (self.now() - CHALLENGE_TTL,))
        rows = self.registry.db.execute("select value from challenges where fqdn = ?", (name.rstrip(".").lower(),)).fetchall()
        return [r["value"] for r in rows]


class Resolver(BaseResolver):
    """Authoritative for home.<zone> and nothing else: anything outside it is refused, not recursed."""
    def __init__(self, home: Home, ns: str, ttl: int = 300):
        self.home, self.ns, self.ttl = home, DNSLabel(ns), ttl
        self.origin = DNSLabel(home.zone)
        self.soa = SOA(self.ns, DNSLabel(f"hostmaster.{home.registry.zone}"), (int(time.time()) // 60, 3600, 600, 86400, 60))

    def resolve(self, request: DNSRecord, handler):
        reply = request.reply()
        q = request.q
        name, qtype = q.qname, QTYPE[q.qtype]
        if not name.matchSuffix(self.origin):
            reply.header.rcode = RCODE.REFUSED
            return reply
        reply.header.aa = 1
        if name == self.origin:
            if qtype in ("SOA", "ANY"): reply.add_answer(RR(name, QTYPE.SOA, rdata=self.soa, ttl=self.ttl))
            if qtype in ("NS", "ANY"): reply.add_answer(RR(name, QTYPE.NS, rdata=NS(self.ns), ttl=self.ttl))
            if qtype in ("CAA", "ANY"):
                # The zone's own rule, said again here so it holds even for a CA that stops at the delegation.
                reply.add_answer(RR(name, QTYPE.CAA, rdata=CAA(0, "issue", "letsencrypt.org"), ttl=self.ttl))
                reply.add_answer(RR(name, QTYPE.CAA, rdata=CAA(0, "issuewild", ";"), ttl=self.ttl))
            if not reply.rr: reply.add_auth(RR(self.origin, QTYPE.SOA, rdata=self.soa, ttl=60))
            return reply
        text = str(name)
        address = self.home.address(text)
        values = self.home.txt(text) if qtype in ("TXT", "ANY") else []
        if address and qtype in ("A", "ANY"): reply.add_answer(RR(name, QTYPE.A, rdata=A(address), ttl=self.ttl))
        for v in values: reply.add_answer(RR(name, QTYPE.TXT, rdata=TXT(v), ttl=60))
        if not reply.rr:
            exists = address is not None or bool(self.home.parse(text) and self.home.parse(text)[2] and values)
            if not exists and not self._is_parent(text): reply.header.rcode = RCODE.NXDOMAIN
            reply.add_auth(RR(self.origin, QTYPE.SOA, rdata=self.soa, ttl=60))
        return reply

    def _is_parent(self, name: str) -> bool:
        """<house>.home.<zone> and <address>.<house>.home.<zone> exist as names, so asking them for TXT is
        NODATA rather than NXDOMAIN -- a resolver that cached NXDOMAIN there would hide the challenge below."""
        p = self.home.parse("_acme-challenge." + name.rstrip("."))
        return p is not None and self.home.registry.status(p[0])["carried"]


def serve(home: Home, ns: str, port: int = 53, address: str = "") -> list[DNSServer]:
    """UDP and TCP both: a CA's resolver falls back to TCP for anything that does not fit a datagram."""
    resolver = Resolver(home, ns)
    servers = [DNSServer(resolver, port=port, address=address, tcp=False), DNSServer(resolver, port=port, address=address, tcp=True)]
    for s in servers: s.start_thread()
    return servers

