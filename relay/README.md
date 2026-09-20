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
needs — carrying **Zone → Zone → Read** and **Zone → DNS → Edit**, and included on the **specific
zone** rather than all of them. That token is the operator's and is the most dangerous secret here:
whoever holds it can repoint the wildcard and, through a DNS-01 challenge, obtain real certificates
for house names. The CAA records narrow that; keeping the token off every hub and off the relay box
is what closes it, and is the reason piece 3 proves certificates over TLS instead. `HCLOUD_TOKEN` is
a project token, read and write. They are the only things in this design minted by hand,
because they are what Terraform authenticates with. Then `terraform.tfvars` from the example beside
it, and `terraform apply`. The wildcard and the CAA pair land at the same time as the box.

Not here yet:

- **The registration service.** Hands out a name and holds the public key a hub signs with, and — since
  19 September 2026 — the entitlement beside it, because the relay is offered as an optional paid
  service and `frps` asks this service whether to carry a house at all. The check lives here and
  never in the hub: a household that runs its own relay needs none of it, and every line of this
  directory stays AGPL and self-hostable for exactly that reason. `docs/service.md`. It still does
  not touch DNS: the zone below has one record in it and never changes at runtime, which is the
  whole reason it fits in Terraform.
