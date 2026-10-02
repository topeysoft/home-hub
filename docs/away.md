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
sends. Who pays for it, and what that may never buy, is `docs/service.md`; running your own instead of the maker's is
a supported path and always will be.

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
  for. Gray cloud, and a line in the health list if a hub ever finds itself behind one.
- **No house ever holds a Cloudflare credential.** Cloudflare's API tokens scope to a zone, not to a record, so the
  narrow per-house credential imagined below cannot be minted: a token letting one hub write its own
  `_acme-challenge` lets it write every other house's too. Piece 3 is what removes the need for one.

**All of it in Terraform.** The zone, the records, the relay's box and the tokens are infrastructure as code; nothing
about `elyir.app` is clicked in a console. What the maker runs is then reviewable, reproducible and recoverable from
the repository, which matters more here than it would elsewhere, because this is the one piece of the product a
household cannot fix for itself.

**And it is one record.** The relay routes by SNI and the certificate is proved over TLS, so **DNS never has to learn
a house's name**: a single gray-cloud wildcard `*.elyir.app` pointing at the relay covers every house that will ever
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
   - **One port carries both**, checked against frp's documentation on 19 September 2026 rather than assumed: the hub
     dials in on 443 and phones arrive on 443, because `frps` detects the protocol and multiplexes `bindPort` and
     `vhostHTTPSPort` onto the same port. This is what lets the hub dial out on the one port that survives a hotel.
     It costs one line on the *client*: `transport.tls.disableCustomTLSFirstByte = false` in `frpc.toml`, which is
     what lets the relay tell a hub dialling in from a phone opening a house. Without it the two collide and the
     tunnel fails to establish. Note the nesting — that key is client-level, while
     `transport.proxyProtocolVersion` above belongs to the individual proxy.

   **Built, 1 October 2026, with step 5's certificate in it; not yet on a real house.** `frpc` is a service in
   `driver-layer/docker-compose.yml` behind the `away` profile, configured by `driver-layer/frp/frpc.toml` from
   `.env` alone. The away door is now one of two files: `caddy/away/off.caddy` is the plain door steps 1 and 2
   were built on, and every house stays on it; `caddy/away/on.caddy` is the house's public name with a certificate
   proved over TLS-ALPN-01, chosen by `HUB_AWAY=on`. The PROXY header is read on `:9443` only and only from
   loopback, in every mode, so the LAN doors are untouched. `.env.example` says how to turn it on. Checked end to
   end in miniature — Pebble as the CA, `frps` with the relay's own `frps.toml`, the real `Caddyfile` and
   `frpc.toml`, and a phone on the far side:

   - The certificate was issued through the relay on Caddy's first retry, a minute after the tunnel came up (the
     first attempt raced the tunnel and failed, which is expected and needs nothing).
   - The phone verified the chain, and the certificate it was shown has the same fingerprint as the one in the
     hub's storage. The relay holds no certificate or key file.
   - The brain was told the phone's own address in `X-Forwarded-For`, not `127.0.0.1`, with `X-Hub-Via: relay`
     and `X-Forwarded-Proto: https`. A forged `X-Hub-Via: lan` arrived as `relay`.
   - The house's name in the handshake with `Host: hub.local` after it reached no site and nothing reached the
     brain. An unregistered name, and no name at all, got no handshake.
   - The relay restarted under the tunnel and `frpc` was back in two seconds.

   **And then against the real thing, the same evening:** the relay on its Hetzner box (`relay/terraform`), the
   real `elyir.app`, and Let's Encrypt itself, with this branch's `Caddyfile` and `frpc.toml` running on a mac as
   `selftest.elyir.app` and a header echo standing in for the brain. Staging first, then production: the real
   certificate was issued on the first attempt, and a client with nothing but its system trust store opened the
   name and verified it. Everything the miniature showed held — same fingerprint at both ends, the client's
   public address in `X-Forwarded-For`, a forged `lan` stamp arriving as `relay`, `Host: hub.local` reaching
   nothing — and with the test stopped the name went back to `unrecognized_name`. Still not on a real house.

   **What the first tap from outside will find.** A phone paired at home holds its cookie for `hub.local`, and a
   browser keeps cookies per origin, so the same phone opening the public name is a stranger there: it gets
   *This house is not open from here*, and the join routes are closed from away by design. The relay, the
   certificate and the gate all work and a let-out phone still cannot get in until a phone can carry its pairing
   from the house's LAN name to its public one. That is the next thing to decide, with the alias in *Open
   decisions*, and the *People* switch lands with it.
4. **The registration service and the switch in *This hub*.** Names, keys, more than one house.

   **The service is built, 1 October 2026, and so is the hub's half, minus payments.** `relay/service/` claims names (free or
   taken, three suggestions, the reserved ones refused), hands each house a secret once and keeps its hash, and
   answers frps's server plugin on Login and NewProxy -- checked against the real frps 0.71.0: a refused house is
   told why, a house is carried only under its own name as raw https, and with the service down frps refuses new
   logins rather than letting them through. A secret and not the signed calls imagined above, because frps hands
   the plugin the metadata frpc read from its config at start, so nothing a hub sends at login can be fresh.
   Entitlements are granted by hand (`relay/README.md`) until payments exist. On the box it is built from a
   pinned ref, its file on a volume, and reached at `api.elyir.app` through frps itself. The hub's half landed the same night:
   `brain/hub/address.py` looks, claims, keeps the secret and asks the host; `driver-layer/host/away.sh` checks
   every value again before it writes `.env` and brings frpc and the away door up; and the panel asks once, as
   the optional last step of setup (`AddressStep.vue`), with a row on *This hub* after. The panel offers it only
   when the service's `/offer` is open -- closed until payments exist -- and `HUB_AWAY_OFFER=on` is the maker's
   own hub, offered it by hand before then. Still to come: payments, the phones moving to the address and the
   *From outside* switch on *People*, and the home alias.
5. **The certificate:** TLS-ALPN-01 on the hub — which is why this now comes before the first tap in step 3 —
   then the alias that covers home.
6. **Web push, then the microphone** — both waiting on 5 and neither on each other.

## Where it stands, and turning it on for the maker's own house

*Written 2 October 2026, after the first deploy to a real relay and a real hub. Read this before touching
either: it is what is running, what broke on the way, and the steps that are still done by hand.*

**What is running.** The relay box (`relay/terraform`, Hetzner `cx23` in Helsinki, 37.27.145.43) runs frps,
the registration service, and `api.elyir.app` on its own Let's Encrypt certificate. The service is built on
the box from the commit in `relay_service_ref`, which lives in `relay/terraform/terraform.tfvars` on the
operator's machine -- gitignored, so it is not in this repository; moving to new service code is a new ref
and `terraform apply`, which replaces the box while the volume carries every house across. `/offer` is
closed (`relay_offer_open = false`): no household is offered an address until payments exist. No house is
carried yet. Checked from outside: `/alive` answers on a certificate any phone trusts, an unregistered name
gets `unrecognized_name`, and the plugin route is 404 to anything but frps on the box.

**What broke on the way, so nobody walks into it again.**

- *hub.local went dark after the update that added the away door.* The Caddyfile began importing
  `caddy/away/off.caddy`, and the compose file mounted the Caddyfile alone, so Caddy could not find the
  import and would not start -- the whole front door, with the brain healthy behind it on :8300. The live
  test of piece 2 had mounted the folder by hand, which is how it got past. Fixed in #53; `test_shipped.py`
  now checks every folder the Caddyfile imports is mounted. If a hub is ever in that state again, the brain
  still answers on `http://hub.local:8300`.
- *Sharing with Apple Home, Google Home and Alexa had never worked on a real hub.* `HUB_SHARE_TOKEN` was
  handed to the Matter bridge and never to the brain, so the brain refused the bridge every time (28,851
  refusals in one hub's log). Not part of this work, found while looking at that hub. Fixed in #54.
- *`HUB_AWAY_OFFER` and `HUB_RELAY_API` were never handed to the brain either*, so setting them in `.env`
  did nothing. Fixed in #54, with a test that every `HUB_*` setting the brain reads is handed to it by the
  compose file, apart from four named developer-only ones. All three were the same mistake: a value in
  `.env` that the container reading it was never given, with a test that set the value itself.

**Turning it on for the maker's own house, before payments.** A house set up before addresses existed
never sees the setup step, so this is the way in:

1. The hub follows `development` and has #53 and #54 (install the update from *This hub*; done on the
   maker's hub on 2 October, when sharing with Apple Home, Google Home and Alexa started working there too). `sudo docker
   inspect brain` should list `HUB_SHARE_TOKEN`, `HUB_AWAY_OFFER` and `HUB_RELAY_API`.
2. `HUB_AWAY_OFFER=on` in `/opt/home-hub/driver-layer/.env`, then `sudo docker compose up -d brain` from
   `/opt/home-hub/driver-layer` so the brain is recreated with it (an update from *This hub* does the same).
   `sudo docker inspect brain` then lists `HUB_AWAY_OFFER=on`. Do not check it with `curl localhost:8300/address`:
   on a house with a passcode that route wants a paired phone and answers `{"detail":"phone"}` to curl --
   the step in 3 opening is the check.
3. On the wall, open `http://hub.local/?setup=1&page=address`. Choose the name -- the household's to choose,
   and taken for a day once claimed -- and *Give it this address*. The step waits to be turned on.
4. On the relay: `ssh root@37.27.145.43 docker exec relay-service python cli.py grant <name> 2027-10-01 "by hand"`.
   The step moves on by itself, and *This hub* shows the Outside row.
5. The brain has already written `away.request`; the host's `home-hub-away.path` runs `away.sh`, which writes
   the house's values into `.env`, adds `away` to the profiles and brings up `caddy` and `frpc`. Check with
   `sudo docker ps` (frpc running), `brain-data/away.log`, and from a phone off the Wi-Fi,
   `https://<name>.elyir.app` -- the house's own certificate, through the relay.

**The alias that covers home, built 2 October 2026.** The relay box is the nameserver for `home.elyir.app`
(`relay/service/home.py`): `192-168-86-53.main-palace.home.elyir.app` answers `192.168.86.53` for a carried house,
only for private addresses. `host/away.sh` writes `HUB_LAN_NAME` from the address the hub really has -- not
`HUB_IP`, which a DHCP lease had left behind on the maker's hub -- and `lan-cert` (stock lego) proves that one
name over DNS-01 through the service, so Caddy serves it on the LAN (`caddy/away/on.caddy`). Caddy fetches the
certificate at each handshake from a loopback-only file server, so until there is one only that name fails and
nothing on the front door waits for it. Checked in miniature with Pebble as the CA and the service's own DNS
server answering the challenge; not yet on the real relay, which needs a new `relay_service_ref` and an apply.
If the hub's LAN address changes, the name changes with it the next time outside is turned on; nothing re-runs
`away.sh` on its own yet.

**What does not work yet, said plainly.** A phone off the Wi-Fi reaching that name gets *This house is not open
from here*, because no phone has moved to the address and the *From outside* switch on *People* is not built
(design/away/, C). That and payments are what is left; until then the address proves the pipe and nothing
more.

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

- ~~**What stops a thousand names being registered?**~~ **Closed, 19 September 2026**, together with who pays for the
  VPS: the relay is offered as an optional paid service, so a name costs something and scarcity needs no mechanism of
  its own. The entitlement is checked **at the relay and never in the hub** — `frps` asks the registration service
  when a hub dials in. Nothing in this document changes; step 4 gains entitlement state beside the public key, and the
  box in step 3 is sized for a few thousand houses rather than one. The reasoning, the tiers and what may never be
  sold are `docs/service.md`.
- ~~**The alias that covers home**~~ **Closed, 1 October 2026: the address in the name.** A small maker-run DNS server
  answers names that spell the hub's LAN address -- `192-168-86-59.temi.home.elyir.app` is `192.168.86.59` -- the way
  Plex's `plex.direct` does. Terraform delegates the one subzone to it once and **no house ever causes a DNS write**,
  which is the rule the zone was built on. The hub's certificate for that name is proved over DNS-01, with the
  challenge answered by the same server for the house that signed the request, so still no house holds a Cloudflare
  credential. A home router that drops private addresses from DNS answers (rebind protection) leaves that house on
  the relay at home, and *This hub* should say so. Not chosen: a record per house written by the registration service
  (a per-house write from a zone-wide token, and the LAN address published in Cloudflare), and the hub as the house's
  DNS server (a router setting, which is not out of the box).
- ~~**How a phone carries its pairing to the public name.**~~ **Closed, 1 October 2026: every phone moves once, when
  the house gets its name** (`design/away/`, direction C). Cookies are per origin, so pairing on `hub.local` gives a
  phone nothing under `elyir.app`. Rather than a hand-off each time a phone is let out, the evening a house is given its
  name every phone at home gets one line in the band and moves to it in three steps, and new phones join on it from the
  start. Letting a phone out is then only the switch on *People*, and it works while the phone is already away. Not
  chosen and kept on the canvas: a second outside icon (A), and moving each phone when it is let out (B). C makes **the
  alias that covers home** mandatory rather than nice: a phone on the public name must reach the hub directly at home.
- **Does the wall panel ever get `remote`?** Recommended no: it never leaves the house, so it never needs the door.

## What this replaces

The https question in *Out of the Box* closes: plain http and the local certificate on the LAN stay as they are, and
the relay name is the https origin for phones. Tailscale and any VPN are out. `docs/voice.md` shape 1 waits on piece 3
for phones and on nothing for the wall.
