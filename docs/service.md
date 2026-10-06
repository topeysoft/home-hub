# The relay as a service: what is sold, and what is never sold

*Written 19 September 2026, when two decisions were taken together: home-hub is published as free software, and the
maker-run side of it is what earns. This document owns the commercial shape. `docs/away.md` owns how the relay works
and is not repeated here; `relay/` is the code and the Terraform; `docs/shipping.md` owns the box. What follows is the
reasoning as well as the answer, so a session picking this up cold can disagree with a specific line rather than with
a feeling.*

## The short answers

| Question | Answer |
|---|---|
| **Should the relay be sold at all?** | Yes. It is the one part of this product with a real, recurring cost to run, which makes it the one part that can be charged for without holding anything back. |
| **What is actually sold?** | A box that stays up, a name under a domain somebody renews, and the bytes. Not a feature. |
| **What is never sold?** | Any capability in the software. Every line of the relay, the registration service and the Terraform is AGPL and genuinely self-hostable. |
| **Where does the payment check live?** | At the relay, never in the hub. See *Rules that do not change*. |
| **What happens when somebody stops paying?** | Away stops. The house on its own Wi‑Fi carries on exactly as before, and nothing is deleted. |
| **Does this change the license?** | No. AGPL-3.0 with the CLA already reserves what this needs. Nothing about `LICENSE` or `CLA.md` moves. |

## Rules that do not change

- **The paid thing is never a software capability.** If a household can run the relay themselves, they get identical
  function for nothing, forever. What is sold is not having to.
- **The check lives at the relay, never in the hub.** A subscription enforced inside the house would be DRM in free
  software: trivially removed, insulting to the people this project wants as contributors, and a direct breach of the
  rule below it. The relay declining to carry bytes is not DRM; it is a server saying no.
- **The house never depends on the maker, and never phones home for anything else.** The moment a payment check
  touches ordinary operation — a tap, a lock, the panel coming up — the whole claim of this project is gone.
  `docs/shipping.md`, *Rules that do not change*.
- **Self-hosting is a first-class path, documented as one.** Not a grudging footnote, not a worse version. A
  household that points its hub at its own `frps` on its own domain is doing the intended thing.
- **The relay still carries bytes it cannot read.** Selling it changes nothing about the pass-through property
  verified on 12 September 2026. No plugin, no termination, no exceptions bought with money.

## Why selling this is honest

The usual way open source earns is to withhold a feature and charge for it, and the usual result is that the people
who were given the code notice what was kept from them and fork it. They are right to. A relay is not that. It is a
VPS invoice every month, a domain renewed every year, and bandwidth that somebody pays for whether or not anyone is
charged. Offering to carry that is a service, not a toll on software already given away.

That shape is also what makes it hard to compete with, and for a reason worth being clear-eyed about: **the software
was never the moat.** Anyone may take `relay/`, stand up their own box, and sell the same thing. What they cannot
take is an operated service with a name people already trust and hubs already pointed at it. A fork gets the code,
which was always free, and inherits the whole cost of running it. There is nothing here to resent, which is the
point.

It is the same bargain a Mastodon host or a Bitwarden server makes, and the crowd that cares about the AGPL
recognizes it on sight.

## Where the check goes

The registration service described in `relay/README.md` is already the right boundary and was designed before this
question was asked. It hands out a name per house and holds the public key each hub signs with. Entitlement is one
more column beside that key: this house is paid up until this date.

`frps` then asks it. `frp` supports server-side plugins as HTTP callbacks on connection lifecycle events — `Login`
and `NewProxy` are the two that matter — so the relay calls the registration service when a hub dials in and is told
yes or no. **Verify that callback surface against the pinned `0.71.0` before building on it**; the version was pinned
for the pass-through property and this document is not a reason to move it.

Two things follow from putting it there, and both are the reason it goes there.

- **Nothing sits in the data path.** The check happens once, when a tunnel is established, not per request and never
  per tap. The relay's job while a phone is using the house is unchanged: route by SNI, forward bytes it cannot read.
- **The hub needs no opinion about money at all.** It dials out and either gets a tunnel or does not. A hub that has
  never paid, a hub whose subscription lapsed, and a hub pointed at a self-hosted relay are all the same code.

## Billing and abuse turn out to be one mechanism

`docs/away.md` left a question open: *what stops a thousand names being registered?* The answers on the table were a
token written at flash time or open registration behind rate limits, and both were work that bought nothing else.

Requiring an entitlement to claim a name answers it without adding a mechanism. Names are scarce because they cost
something, which is the only rate limit that has never needed tuning. The flash-time token survives, but as the way a
box that was *bought* proves it already has an entitlement — not as a separate anti-abuse scheme.

That open decision is now closed, and `docs/away.md` says so.

## What it costs, and therefore what to charge

*Arithmetic, not a price list. The numbers below are the shape of the problem; the actual price is an open decision
at the end of this document.*

An idle house is one held-open TCP connection. It costs almost nothing, and a small VPS holds thousands of them. The
variable cost only appears while somebody is actually away and using the house, and per `docs/away.md` **camera video
is the only heavy thing a house sends**. So: near-zero per house at rest, occasionally spiky per house in use, and a
box sized for a few thousand houses rather than for one.

Three tiers fall out of that, and none of them holds anything back.

- **Included with hardware.** A box or a puck ships with some years of relay in the price, the entitlement written at
  flash time. It costs nearly nothing while those houses sit idle, it makes the hardware worth more, and it stops the
  two revenue streams competing for the same buyer. `docs/shipping.md` owns what the hardware is.
- **A small subscription for everyone else** — the people who built it from this repository on their own hardware and
  want the convenience anyway. Priced under what renting the VPS themselves would cost, because that is the honest
  comparison and it is also true.
- **Self-hosted, free, forever.** Documented in `relay/README.md` as a supported path with its own instructions.

Buy an unmetered or generously allowanced box and write a fair-use line about video rather than metering bytes per
house. Metering would cost more in complexity and in trust than the bandwidth it saved.

## Failing gently

A lapsed subscription is not a broken house. Away stops working; the Wi‑Fi is untouched; nothing is deleted; the
name is held for a grace period long enough that somebody on holiday does not lose it. The panel says all of this
**before** the first payment, not after the first lapse — the same rule as everywhere else here, that the product
never shows a promise it cannot keep, and never springs a consequence it did not mention.

The same sentence answers the obvious objection to paying at all, so it belongs in the sales copy rather than in the
small print: *if the relay is down, or unpaid, or gone, the house works exactly as it does today.* That is already
true and already tested. It is the strongest thing this service can say about itself and it costs nothing to say.

## What is held about a household, and what cannot be

The pass-through property is the pitch and it is also the reason the operator's burden stays small: **the relay
cannot produce what it cannot decrypt.** No camera frame, no tap, no code, not with a subpoena and not by mistake.
The ACME design keeps this honest in the other direction too — TLS-ALPN-01 means no per-house DNS credential is ever
minted, so the service never holds a key that could impersonate a house. That was chosen for other reasons and it is
worth not giving up now that there is a commercial motive to make things convenient.

What *is* held, once money changes hands, is real and is personal data: an email address, a payment relationship, the
house's name, and connection metadata — which house, when, how many bytes. That is a data protection obligation in
the UK and the EU whatever the size of the operation. Keep it minimal, keep it stated plainly in one page a person
can read, and keep payment card data out of it entirely by never touching it: use a payment provider and store a
customer reference, nothing more.

## What is not sold, and will not be

- **No panel feature is gated.** Nothing in the house is behind a subscription.
- **Web push and the browser microphone are not extras.** They are consequences of the certificate, and a
  self-hoster with their own domain earns them the same way. `docs/voice.md` shape 1 does not become a paid tier.
- **No telemetry is sold, and none is collected to sell.** There is nothing readable to collect.
- **The domain is the boundary, not a lever.** `elyir.app` is the maker's; a self-hoster brings their own name. That
  divides the service from the software without crippling either.

## What this adds to the build

`docs/away.md` has the six steps and they do not change. This adds to two of them:

- **Step 3, the box.** Unchanged in shape, but now sized for a few thousand houses rather than one, and paid for by
  the thing it carries. Provider is still the open decision blocking the chain.
- **Step 4, the registration service.** Gains entitlement state beside the public key, the `frps` callback that reads
  it, and a payment provider's webhook to keep it current. The DNS design is untouched: registering a house still
  writes nothing to the zone, which is what let Terraform own it completely.

Nothing else in the tree moves. No change to the hub, the panel, the gate, or the pairing model is required by any of
this, which is the sign that the check was put in the right place.

## Open decisions

- **The actual price, and in what currency**, which depends on where the service is sold from and drags VAT on
  cross-border digital subscriptions with it. Decide whether a payment provider acts as merchant of record before the
  first sale, because changing it afterwards is much harder than choosing it now.
- **How many years of relay ship with a box**, which is really a question about what the hardware costs and how long
  a household keeps one.
- **Whether there is a free tier for people who did not buy hardware.** Generous to the community it is built for,
  and the one thing that would hand the name-squatting question straight back. Self-hosting may be the honest answer
  to the same impulse.
- **Who answers when it breaks at midnight.** The stated expectation is best-effort with no SLA, and that is
  defensible precisely because the house does not depend on it — but somebody still has to be the one who looks.
