# The relay: what the maker runs

Everything in this directory is the maker's side of `docs/away.md` — the part a household does not
have and cannot fix for itself. It is deliberately small: a domain, one box, and a name per house.
The house never depends on any of it. With the relay down, a phone away sees the sentence the gate
gives it and everything on the Wi‑Fi carries on exactly as before.

- `terraform/` — the Cloudflare zone for `elyir.app`. Nothing here is clicked in a console.

- `terraform/relay.tf` — the box, since 19 September 2026: a Hetzner server in the EU, a firewall
  that opens 443 and ssh and nothing else, and cloud-init that installs `frps` pinned to the version
  the pass-through property was checked against. It holds no certificate and no key for any house;
  it routes by SNI and forwards bytes it cannot read (checked, 12 September 2026 — `docs/away.md`,
  *What was verified*). Set `relay_ipv4` to bring your own box instead and nothing here is rented.

**Applying it.** Two tokens, from the environment and never from a file. `CLOUDFLARE_API_TOKEN` is a
*custom* token — not the "Edit zone DNS" template, which omits the zone read the lookup in `dns.tf`
needs — carrying **Zone → Zone → Read**, **Zone → DNS → Edit** and **Zone → SSL and Certificates → Edit**
(the last turns Universal SSL off, see `dns.tf`), and included on the **specific zone** rather than
all of them. That token is the operator's and is the most dangerous secret here:
whoever holds it can repoint the wildcard and, through a DNS-01 challenge, obtain real certificates
for house names. The CAA records narrow that; keeping the token off every hub and off the relay box
is what closes it, and is the reason piece 3 proves certificates over TLS instead. `HCLOUD_TOKEN` is
a project token, read and write. They are the only things in this design minted by hand,
because they are what Terraform authenticates with. Then `terraform.tfvars` from the example beside
it, and `terraform apply`. The wildcard and the CAA pair land at the same time as the box.

- `service/` — the registration service, since 1 October 2026. It hands out a name per house and the
  secret that proves it, holds each house's entitlement, and answers frps before it carries anyone:
  frps's server plugin asks on every login and every proxy, and a house is carried only if its secret
  matches, it is entitled, and it asks for nothing but its own name as raw https. It never touches
  DNS -- every house is under the zone's one wildcard -- and it stores only the hash of each secret.
  It runs on the relay box, built there from this repository at `relay_service_ref`, with its file on
  a Hetzner volume that outlives the box. Hubs reach it at `https://api.elyir.app`, which is carried
  through frps like a house and has its own certificate proved the same way, so nothing new is open.

- `service/home.py` — the address in the name, since 2 October 2026: the service is also the
  nameserver for `home.elyir.app` (delegated once in `dns.tf`, port 53 opened in `relay.tf`). It
  answers `192-168-86-53.<house>.home.elyir.app` with that LAN address for a carried house and
  nothing else -- only private addresses, only houses the relay carries -- and serves the DNS-01
  TXT record a house sets for its own name through `/acme/present`, shaped like lego's `httpreq`
  provider so the hub uses a stock ACME client (`driver-layer/lan-cert/`). No house causes a DNS
  write and there is still no wildcard certificate anywhere under the zone.

**Carrying a house, by hand, until payments exist.** The relay is an optional paid service
(`docs/service.md`) and the payment side is not built, so the operator grants entitlements:

```sh
# the house claims its name (the panel will do this; until then, from anywhere):
curl -s https://api.elyir.app/houses -H 'content-type: application/json' -d '{"name":"temi"}'
#   -> {"name":"temi","address":"temi.elyir.app","secret":"...", ...}   the secret is shown once
ssh root@<relay> docker exec relay-service python cli.py grant temi 2027-10-01 "Temi, by hand"
ssh root@<relay> docker exec relay-service python cli.py list
```

The hub then needs `HUB_AWAY_HOUSE=temi` and `HUB_RELAY_SECRET=<the secret>` in its `.env`
(`driver-layer/.env.example`). A name claimed and not granted is let go after a day. `cli.py` also
stops a house (it keeps its name), rotates a lost secret, and releases a name.

**The printer app** (`printers.elyir.app`, since 2 October 2026) is static files served by the same
Caddy as `api`, carried through frps as one more always-carried name whose secret is derived from the
relay token. It belongs to the printer project and is published from that repository, never edited on
the box: each version is unpacked into `/var/lib/relay/printers/<version>/` on the volume and
`current` is switched to it, so a rebuilt box keeps serving the last one. Every phone that opens it
trusts that code with its printers' tokens, which is why the site sends a strict
`Content-Security-Policy` (scripts from itself only; talking and framing only to names under the zone)
and may not be framed itself.

**The Houses app** (`houses.elyir.app`, since 3 October 2026) is the phone's one app for every house it
has joined, and is set up on the box exactly as the printer app is: static files from the same Caddy,
carried as one more always-carried name, its secret derived from the relay token, `houses` kept from any
house. It belongs to this repository (`app/`, built with `npm run build:houses`) and is published with
`tools/publish-houses.sh`, never edited on the box: the script builds a commit in a clean checkout,
unpacks it into `/var/lib/relay/houses/<version>/` and switches `current` to it, keeping the last five so
`ROLLBACK=<version> tools/publish-houses.sh` can switch back. Each house's screen is framed inside it from
that house's own name, so its `Content-Security-Policy` is the printer app's -- talking and framing only to
names under the zone, and never framed itself -- and it asks for no camera of its own. It may read
`/nearby` from a page too.

**Which printers are on this Wi-Fi** (`nearby.elyir.app`, since 2 October 2026): the service notes the public
address each house's tunnel logs in from, and `GET https://nearby.elyir.app/nearby` answers with the carried
names behind the asker's own address, so the printer app can list a house's printers without anybody typing
a name. Names only; connecting still means asking from that house's own Wi-Fi. The name has an A record and
no AAAA on purpose: tunnels arrive over IPv4, and a dual-stack phone asking over IPv6 would match nothing.
Only the printer app's and the Houses app's origins may read the answer from a page.

The box's ssh host keys live on the volume as well, so a rebuild is the same host to every client that
has connected before.

**Moving the box to new service code** is a new `relay_service_ref` -- a commit, ideally -- and
`terraform apply`, which replaces the server. The volume is detached and attached to the new one, so
every house and the api certificate come across; open tunnels drop for the minute the box takes, and
every hub's frpc dials back in on its own.
