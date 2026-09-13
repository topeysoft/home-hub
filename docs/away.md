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
- **Nothing between a phone and the house terminates TLS.** The relay routes by SNI and carries bytes it cannot read;
  the house holds the only key. So the record for a house's name is DNS-only and never proxied — Cloudflare's orange
  cloud would put a cloud back in the path, and it is one checkbox with no visible symptom, which is the worst kind
  of mistake this design can make.

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
does not. It is `frp` — `frps` on the VPS, `frpc` alongside Caddy in `driver-layer/docker-compose.yml`, one Go binary
each and no code of ours to maintain. **Checked on 12 September 2026, and it does pass TLS through untouched** (see
*What was verified* below), so the relay of our own is not needed.

The relay's whole configuration is two lines — `bindPort` and `vhostHTTPSPort` — and the hub's proxy is
`type = "https"` with `customDomains` and a `localPort`. **The trap to know about: `frp` also ships an `https2http`
plugin, and that one terminates.** The pass-through property is a property of not using a plugin, so anything that
adds one to this proxy gives the relay the ability to read the house's traffic. Pin the version (`0.71.0` is what was
tested) and treat the plugin line as the thing not to add.

**The routing.** The relay reads the SNI of each incoming handshake, matches it to a registered house, and forwards
the raw bytes into that house's tunnel. It never decrypts. What it can see is worth saying in plain words, because
*This hub* should say it too: **which house is being talked to, when, and how many bytes — not a tap, not a camera
frame, not a code.**

**The listener split, which is the part to get right.** Traffic that arrives through the tunnel must land on a
listener of its own. If it shared Caddy's ordinary `:443`, a request routed by SNI `nadine.elyir.app` could carry
`Host: hub.local` after the handshake and fall into the local site block — which is the front door propped open from
the internet. So `frpc` forwards into a Caddy site on `:9443` that `bind`s to loopback and is unreachable from the
LAN, and **everything arriving there is away traffic whatever Host it claims**.

That last phrase is why the site address carries no host of its own: a door that only answered to the right Host would
be trusting the one thing about a request that cannot be trusted. Caddy stamps `X-Hub-Via: relay` on that site and
deletes any copy a client brought on every other, so the tag cannot be forged from either side — a phone on the Wi-Fi
cannot claim to be away, and a phone away cannot claim to be home. The relay adds nothing: it never terminates TLS, so
it could not stamp a header if it wanted to. Nothing in front of the brain at all, which is how a developer runs it,
means every request is at home, and that is the right answer there.

**The gate.** One more rule in the middleware that already holds the code and the phone cookie: a request tagged away
is refused unless it carries a paired phone whose `remote` is on. Two things follow.

- **The join screen is never open from outside.** `open_to_strangers()` applies on the LAN only. A stranger can ask to
  join from the kitchen; a stranger on the internet gets nothing at all, not even the question.
- **A home-only phone away from home gets one sentence**, not an error: *this phone works at home. Someone at the wall
  can let it out.*

**The switch.** *People → Phones*, per phone, behind the code, off by default and forever: being let into the house is
one decision and being let out of it is another. The route and the log lines are already there and the gate already
reads them; what waits for the relay is only the control on the page, because until then it would promise something
the house cannot do. Every promotion and demotion is a `phone` event in the log like every
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

**The name is `elyir.app`**, bought 12 September 2026, its DNS run from Cloudflare, and a house is a subdomain of
it: `nadine.elyir.app`. Three things follow from the choice of domain rather than from anything in this design.

- **`.app` is on the HSTS preload list at the top level, with `includeSubDomains`.** Every browser shipping that list
  refuses plain http to anything under `elyir.app` — and, the part that decides the order below, an HSTS host whose
  certificate the browser does not trust offers **no click-through**. There is no half-state where the first tap from
  outside happens over a certificate somebody accepts once. Piece 3 is a prerequisite of step 3, not a step after it.
- **The record is DNS-only, never proxied.** Cloudflare's orange cloud terminates TLS at Cloudflare, which is the
  cloud this document ruled out on its first page, and it would quietly undo the pass-through the relay was chosen
  for. Grey cloud, and a line in the health list if a hub ever finds itself behind one.
- **No house ever holds a Cloudflare credential.** Cloudflare's API tokens scope to a zone, not to a record, so the
  narrow per-house credential imagined below cannot be minted: a token letting one hub write its own
  `_acme-challenge` lets it write every other house's too. Piece 3 is what removes the need for one.

**All of it in Terraform.** The zone, the records, the relay's box and the tokens are infrastructure as code; nothing
about `elyir.app` is clicked in a console. What the maker runs is then reviewable, reproducible and recoverable from
the repository, which matters more here than it would elsewhere, because this is the one piece of the product a
household cannot fix for itself.

**And it is one record.** The relay routes by SNI and the certificate is proved over TLS, so **DNS never has to learn
a house's name**: a single grey-cloud wildcard `*.elyir.app` pointing at the relay covers every house that will ever
register, and registering one writes nothing to DNS at all. The registration service hands out names and keys; it does
not touch the zone. A zone that never changes at runtime is a zone Terraform can own completely.

### 3. A real certificate per hub

*Not started, and no longer a step after the relay: `.app` leaves no click-through, so the first tap from outside
needs a certificate a phone already trusts. This piece comes before step 3 finishes.*

Because the relay never terminates TLS, **the hub holds the certificate** — for a name that does not resolve to it.
That was read as ruling out every challenge but DNS-01. It does not.

**ACME over TLS-ALPN-01.** The validator opens a TLS connection to the name on 443 offering the ALPN protocol
`acme-tls/1`; the relay routes it by SNI like anything else, and the house answers it on the port it already has. No
DNS record is written, no credential is minted, no house is trusted with the zone — and **the stock `caddy:2` does
this out of the box**, so the custom Caddy with a DNS provider compiled in is not needed, which was the snag that made
this piece expensive. Checked on 12 September 2026 that the relay is blind to ALPN (see *What was verified*). What has
**not** been checked, because it needs the VPS and the real name, is a live issuance end to end; that is step 5's own
exit test.

**DNS-01 stays the fallback**, and if it is ever needed the credential belongs to the registration service, not to the
house: the hub asks the service to publish the TXT, and the service is the only thing holding a Cloudflare token. That
keeps the rule that no house can touch another house's name.

**A trusted origin at home too.** The app should not drop to an untrusted certificate the moment it is on the sofa, so
the same certificate covers a name that resolves to the hub's LAN address. Simplest first cut is a record in the
maker's DNS pointing at the private address — it works, it publishes the house's LAN IP, and it breaks when that IP
changes. The alternative is the hub answering for its public name on the LAN itself. Start with the first.

**What it unlocks:** the browser microphone on phones (`docs/voice.md` shape 1), web push, and a clean Add to Home
Screen with no certificate profile to install, ever. The wall panel keeps working on `hub.local` and never depends on
any of it.

**The rough edge:** a hub off the internet longer than a renewal window lets its certificate lapse, and phones away
lose the name until it is back. With TLS-ALPN-01 the renewal needs the tunnel up, which is the same condition as being
reachable at all, so nothing new can break — but a hub that has been dark for sixty days comes back needing the relay
before it can prove its own name. The LAN is unaffected. *This hub* should say this rather than let it surprise someone.

## The order to build it

The first two steps need nothing from the maker and can land and be tested on a laptop.

1. ~~**The listener split and the away tag.**~~ **Done, 12 September 2026.** `:9443` in `caddy/Caddyfile`, bound to
   loopback on the hub and published only to the mac in the dev compose file; `from_away()` in `hub/phones.py`;
   `request.state.away` set in the one middleware that already holds the code and the cookie; `/phones/me` says which
   door answered, so the app can tell too. Nothing is refused on it yet — `test_away_changes_nothing_yet` in
   `tests/test_api_lock.py` says so on purpose, and step 2 is what changes it. Checked against a real Caddy: the LAN
   door strips a forged stamp, and the away door stamps `relay` even when the request claims `Host: hub.local`, which
   is the bypass the split exists to stop.
2. ~~**The gate.**~~ **Done, 12 September 2026.** `away_refused()` and `away_refusal()` in `hub/phones.py`, applied in
   the same middleware that holds the code and the cookie. From outside the house: only a phone the house has let
   out; the join routes never, not even to a phone that *is* let out, because a phone joins the house from inside it
   where somebody can see who is asking; and the app's own files always, so it can load and say why it is not showing
   the house. `/phones/me` gives no name and no way in to anyone out there it has not let out. A house with no code
   has no phones and so lets nobody in from away at all. The words are the brain's and the panel only carries them
   (`Away.vue`, `?away=1` previews it). `AwayGateTests` in `tests/test_api_lock.py`.

   **The visible switch is deliberately not in this step.** `set_remote()`, `POST /phones/{id}/remote` and the log
   lines have existed since pairing landed, and the gate now reads what they write — but until there is a relay,
   turning a phone's switch on changes nothing a household could see. Piece 1 of this document says the panel never
   shows a promise it cannot keep, so the switch on *People* lands with step 3 and not before. Nothing is missing
   underneath it.
3. **The relay on the VPS and `frpc` in the compose file**, one house, name hard-coded. First tap from outside.
   Two conditions the verification above puts on this step, neither visible from the outside:

   - **The away door needs a certificate, and on `.app` it has to be a real one.** `type = "https"` forwards raw TLS
     and the house is what terminates it, so a `:9443` speaking plain http — which is what it speaks today — never
     completes a handshake. An earlier draft of this line said a `tls internal` certificate somebody clicks through
     would carry the first tap; `elyir.app` being HSTS-preloaded means there is no click-through to offer. So this is
     not two pieces being coupled: **step 5 lands before step 3's first tap.**
   - **PROXY protocol at both ends**, or the house cannot tell one away phone from another. See *What was verified*.
4. **The registration service and the switch in *This hub*.** Names, keys, more than one house.
5. **The certificate:** TLS-ALPN-01 on the hub — which is why this now comes before the first tap in step 3 —
   then the alias that covers home.
6. **Web push, then the microphone** — both waiting on 5 and neither on each other.

## What was verified

*12 September 2026, by standing the whole shape up in miniature rather than reading about it: a test CA, a leaf for
`nadine.homehub.test`, an origin holding the only copy of the key, `frps` in one container and `frpc` in another.*

- **The relay does not terminate TLS.** The certificate served to the client through the relay was the origin's own,
  to the byte — the same SHA-256 fingerprint — and the client verified the chain against the hub's own CA. The origin
  completed a real TLS handshake. The relay was never given a certificate or a key and had none anywhere in it. Since
  the session keys come from a private key that exists only on the hub, the relay carries bytes it cannot read.
- **Routing is by name and nothing else.** A connection offering an unknown SNI, or no SNI at all, gets no certificate
  and no connection: the hub is not reachable except by the name registered for it. A port scan of the relay finds
  nothing to talk to.
- **And the reason step 1 exists.** The origin saw `Host: nadine.homehub.test:9444` — the client's own Host header,
  carried through untouched after SNI had already chosen the hub. SNI picks the house; the Host header is still
  whatever the request claims. That is exactly the bypass the listener split was built for, confirmed in the small.

*A second run the same day, this time with the pinned `caddy:2` in the chain rather than a stand-in origin, so the
door under test was the `:9443` site as it is actually written.*

- **The stamp cannot be brought by the client.** An `X-Hub-Via: lan` sent from outside arrived at the brain as
  `relay`: `header_up X-Hub-Via relay` replaces what a request carries rather than adding to it. The door's own
  account of where a request came from is the only one that survives.
- **The address the house sees is `frpc`'s, not the phone's.** Every away request arrives from `127.0.0.1`, because
  that is where `frpc` is. `request.client.host` is what `hub/lock.py` counts wrong codes against, so as it stands
  the whole of away would share one bucket: five wrong codes from one phone and every phone away waits the minute
  out. The fix is `transport.proxyProtocolVersion = "v2"` on the proxy and a `proxy_protocol` listener wrapper on the
  `:9443` site, and it was checked working through the real Caddy. The two ends are all or nothing — one without the
  other kills the TLS handshake outright, which is at least a failure that shows itself rather than an address
  quietly going wrong.
- **The relay is blind to ALPN.** A handshake offering `acme-tls/1` through the relay arrives at the house and is what
  the house selects; an ordinary `h2` handshake at the same door still negotiates `h2`; a handshake offering nothing
  negotiates nothing. The relay's configuration mentions none of them. That is what makes TLS-ALPN-01 possible in
  piece 3, and it also means the relay cannot tell an ACME validation from a phone opening the house.

## Open decisions

- **What stops a thousand names being registered?** A token per box written at flash time, or open registration with
  rate limits. This is also the question of who pays for the VPS, and it is the one decision here that is about
  selling a box rather than building one.
- **The alias that covers home** — a private address in public DNS, or the hub answering for its own name on the LAN.
- **Does the wall panel ever get `remote`?** Recommended no: it never leaves the house, so it never needs the door.

## What this replaces

The https question in *Out of the Box* closes: plain http and the local certificate on the LAN stay as they are, and
the relay name is the https origin for phones. Tailscale and any VPN are out. `docs/voice.md` shape 1 waits on piece 3
for phones and on nothing for the wall.
