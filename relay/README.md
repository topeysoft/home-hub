# The relay: what the maker runs

Everything in this directory is the maker's side of `docs/away.md` — the part a household does not
have and cannot fix for itself. It is deliberately small: a domain, one box, and a name per house.
The house never depends on any of it. With the relay down, a phone away sees the sentence the gate
gives it and everything on the Wi‑Fi carries on exactly as before.

- `terraform/` — the Cloudflare zone for `elyir.app`. Nothing here is clicked in a console.

Not here yet, in the order they are needed:

- **The box.** One small VPS running `frps`. It holds no certificate and no key for any house; it
  routes by SNI and forwards bytes it cannot read (checked, 12 September 2026 — `docs/away.md`,
  *What was verified*). Which provider is not decided, so nothing here assumes one; when it is, the
  host joins this directory and hands its address to `relay_ipv4`.
- **The registration service.** Hands out a name and holds the public key a hub signs with, and — since
  19 September 2026 — the entitlement beside it, because the relay is offered as an optional paid
  service and `frps` asks this service whether to carry a house at all. The check lives here and
  never in the hub: a household that runs its own relay needs none of it, and every line of this
  directory stays AGPL and self-hostable for exactly that reason. `docs/service.md`. It still does
  not touch DNS: the zone below has one record in it and never changes at runtime, which is the
  whole reason it fits in Terraform.
