# Away from home: the plan

*Decided 10 September 2026. One app, paired to the house once at home, reachable anywhere after that. No second app,
no vendor login, no certificate to install by hand.*

## The decision

Https was never the blocker; Caddy has served the brain on `https://hub.local` from its own certificate authority since
the start. The blocker was trust: no public authority issues a certificate for a name that only exists on one Wi‑Fi,
so every phone had to install the hub's root certificate by hand, which fails the plug-in-and-open-hub.local promise.
And reaching the house from outside was ruled out entirely, because driving the house is deliberately open on the LAN
(the code guards changes to the house, not taps), so anything that exposed the brain to the internet would have exposed
the front door lock with it.

Three shapes were on the table:

| Shape | What a person does | Why not |
|---|---|---|
| A VPN app (Tailscale, WireGuard) | Installs a second app, logs in to a vendor, accepts an invite | The house stops feeling like one product; a login outside the hub |
| A cloud tunnel (Cloudflare) | Nothing, but every tap goes through a cloud even on the sofa | A cloud between a person and their light switch |
| **The hub's own door and a relay you run** | Scans the code on the wall once; the same icon works everywhere | This is the one |

The third shape is what HomeKit, Hue and Home Assistant Cloud all converge on, and it is what selling a box means: the
maker runs a small service (a domain, a cheap relay, certificates) and the house never depends on it.

## Rules that do not change

- **Being in the house gets a phone nothing on its own.** The owner lets a phone in, and only the owner can let it out
  of the house. A guest with the wall to themselves can ask, not approve.
- **The house works entirely without the relay.** The wall panel and every phone on the Wi‑Fi talk to the hub directly.
  The relay is only in the path when a phone is away, and it only ever carries encrypted bytes.
- **Nothing to install.** The phone's browser and its home-screen icon are the app. Pairing is a scan and a tap.
- **Every phone is visible and removable.** *People* lists them under the people they belong to; Remove is one tap
  and takes effect at once.

## Three pieces, in order

### 1. Pairing and tokens on the hub *(landed 10 September 2026)*

Once the house has a code, only its own phones get in. A phone gets in one of three ways:

- **The screen that set the code during setup** is paired on the spot: it is the wall.
- **Type the code on the phone.** The owner's way in. Wrong codes count against the address as anywhere else.
- **Ask, and be allowed.** A new phone opens the hub and sees *Join Nadine's house*: it gives a name ("Sam" becomes
  *Sam's iPhone*), taps *Ask to join*, and waits. Every screen that is already in shows a card: *Sam's iPhone wants to
  join the house · Allow · Not now*. Allow asks *For today / For the weekend / Keep*, then the code. A phone knocking
  wakes the wall from its clock so the card is seen.

Underneath: `brain/hub/phones.py` keeps `phones.json` in the data directory (it rides the backup). Each phone holds a
random token in an `HttpOnly` cookie and the hub keeps only its hash; removing a phone deletes the hash, and there is
nothing on the phone worth keeping. Every join, ask, refusal, removal and expiry is a `phone` event in the log and a
line under *Recent*. The gate is the same middleware as the code: with a code set, every request except the app's own
files, the join routes and a speaker's sound files needs a phone cookie, and the live stream refuses a stranger. Driving
the house still needs no code; letting a phone in or out does. Without a code the house is open on the Wi‑Fi exactly
as before, and *This hub* says so.

Every phone starts **home-only**. `remote` is recorded per phone, off by default, and nothing reads it yet; the switch
that turns it on arrives with the relay, so the panel never shows a promise it cannot keep.

Two things to know:

- A house that already had a code sees the join screen once after this update, on the wall as well. Typing the code
  there pairs the wall; phones ask or type the code.
- On iOS, a page added to the home screen keeps its own cookies, so a phone paired in Safari joins once more from the
  icon. Twenty seconds, once. *This hub* then lists it twice; remove the one that says Safari's browser, or leave it.

### 2. A relay you run

*Not started. What follows is the build, worked out on 12 September 2026 so it can be picked up cold.*

Each hub holds one outbound connection open to a small server the maker runs, and a name per house routes to that
hub. Nothing is forwarded on the household's router, nothing is installed on the phone, and the relay never holds a
certificate for a house's name, so it carries bytes it cannot read.

**The tunnel.** The hub dials out on port 443 and multiplexes every stream over that one connection. Outbound 443
because it is the one port that survives a hotel, an office and a mobile network; UDP and anything WireGuard-shaped
does not. First cut: `frp` — `frps` on the VPS, `frpc` alongside Caddy in `driver-layer/docker-compose.yml`, one Go
binary each and no code of ours to maintain. **Verify before committing** that its https proxy really forwards by SNI
without terminating TLS; if it does not, the fallback is a small relay of our own over one TLS connection, which is
the same shape with our code inside it.

**The routing.** The relay reads the SNI of each incoming handshake, matches it to a registered house, and forwards
the raw bytes into that house's tunnel. It never decrypts. What it can see is worth saying in plain words, because
*This hub* should say it too: **which house is being talked to, when, and how many bytes — not a tap, not a camera
frame, not a code.**

**The listener split, which is the part to get right.** Traffic that arrives through the tunnel must land on a
listener of its own. If it shared Caddy's ordinary `:443`, a request routed by SNI `nadine.homehub.app` could carry
`Host: hub.local` after the handshake and fall into the local site block — which is the front door propped open from
the internet. So `frpc` forwards into a Caddy site bound to loopback (`HUB_RELAY` on `:8443`, unreachable from the
LAN), and **everything arriving there is away traffic whatever Host it claims**. The brain learns which by the port it
was served on, not by a header: the relay cannot add a header, and that is exactly the property we want from it.

**The gate.** One more rule in the middleware that already holds the code and the phone cookie: a request tagged away
is refused unless it carries a paired phone whose `remote` is on. Two things follow.

- **The join screen is never open from outside.** `open_to_strangers()` applies on the LAN only. A stranger can ask to
  join from the kitchen; a stranger on the internet gets nothing at all, not even the question.
- **A home-only phone away from home gets one sentence**, not an error: *this phone works at home. Someone at the wall
  can let it out.*

**The switch.** *People → Phones*, per phone, behind the code, off by default and forever: being let into the house is
one decision and being let out of it is another. Every promotion and demotion is a `phone` event in the log like every
join and removal. Once web push lands (piece 3), the owner's phone hears the moment any phone is promoted.

**Registering a house.** One switch under *This hub*: **Reachable from outside the house**. The hub makes a keypair
the first time it is asked, claims a name from the maker's service, and signs every later call with that key. The
service answers with the name and with the narrow DNS credential piece 3 needs. A taken name is refused with
suggestions. The name is then shown under *This hub* and is what a phone's app remembers.

**What the maker runs.** A domain, one small VPS with the relay on it, a wildcard record pointing at that VPS, and the
registration service. Bytes only cross it while somebody is away, and camera video is the only heavy thing a house
sends.

**Finding the house.** The app tries the LAN first with a short timeout and the public name second, the way Plex does,
so the relay is never in the path at home. At home with the internet down the name fails and `hub.local` answers. The
relay being down is the same as being away with no signal: the house itself is untouched.

### 3. A real certificate per hub

*Not started. Depends on the name from piece 2.*

Because the relay never terminates TLS, **the hub holds the certificate** — for a name that does not resolve to it.
That rules out the usual challenge and leaves one:

**ACME over DNS-01.** The registration service mints a credential scoped to one house's `_acme-challenge` record and
nothing else; the hub answers the challenge and renews on its own. The private key never leaves the house. The
practical snag is that the stock `caddy:2` image has no DNS provider module compiled in, so either the driver layer
builds a Caddy that does, or the brain runs its own ACME client and hands Caddy the files. Decide by how much of this
we want to own.

**A trusted origin at home too.** The app should not drop to an untrusted certificate the moment it is on the sofa, so
the same certificate covers a name that resolves to the hub's LAN address. Simplest first cut is a record in the
maker's DNS pointing at the private address — it works, it publishes the house's LAN IP, and it breaks when that IP
changes. The alternative is the hub answering for its public name on the LAN itself. Start with the first.

**What it unlocks:** the browser microphone on phones (`docs/voice.md` shape 1), web push, and a clean Add to Home
Screen with no certificate profile to install, ever. The wall panel keeps working on `hub.local` and never depends on
any of it.

**The rough edge:** a hub off the internet longer than a renewal window lets its certificate lapse, and phones away
lose the name until it is back. The LAN is unaffected. *This hub* should say this rather than let it surprise someone.

## The order to build it

The first two steps need nothing from the maker and can land and be tested on a laptop.

1. **The listener split and the away tag.** A loopback-only Caddy site, and the brain knowing a request came in
   through it. Testable by hitting the port directly with nothing on the other end.
2. **The per-phone switch and the gate.** `remote` finally read, the sentence a home-only phone gets, the log lines.
3. **The relay on the VPS and `frpc` in the compose file**, one house, name hard-coded. First tap from outside.
4. **The registration service and the switch in *This hub*.** Names, keys, more than one house.
5. **The certificate:** DNS-01 on the hub, then the alias that covers home.
6. **Web push, then the microphone** — both waiting on 5 and neither on each other.

## Open decisions

- **`frp` or a relay of our own?** Settle it by checking that `frps` passes SNI through without terminating TLS. Ours
  is maybe two hundred lines and one less dependency to trust with the house's bytes.
- **What stops a thousand names being registered?** A token per box written at flash time, or open registration with
  rate limits. This is also the question of who pays for the VPS, and it is the one decision here that is about
  selling a box rather than building one.
- **The alias that covers home** — a private address in public DNS, or the hub answering for its own name on the LAN.
- **Does the wall panel ever get `remote`?** Recommended no: it never leaves the house, so it never needs the door.

## What this replaces

The https question in *Out of the Box* closes: plain http and the local certificate on the LAN stay as they are, and
the relay name is the https origin for phones. Tailscale and any VPN are out. `docs/voice.md` shape 1 waits on piece 3
for phones and on nothing for the wall.
