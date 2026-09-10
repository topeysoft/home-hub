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
- **Every phone is visible and removable.** *This hub → Phones* lists them; Remove is one tap and takes effect at once.

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

Each hub keeps an outbound tunnel open to a small server of yours, and a name like `nadine.homehub.app` routes to that
hub by hostname (SNI passthrough: the relay never terminates TLS, so it never sees a tap). The phone's app tries the hub
directly on the Wi‑Fi first and the relay only when that fails, the way Plex does, so the relay is not in the path at
home. A request arriving through the tunnel is only honoured from a phone whose `remote` flag is on; the switch under
*This hub → Phones* turns it on per phone, behind the code, and web push (once https lands) tells the owner's phone the
moment any phone is promoted.

What the maker runs: a domain, one small VPS with the relay, and the record that maps each house's name to it. A house
is registered from *This hub* with one switch, *Reachable from outside the house*, and one sentence under it.

### 3. A real certificate per hub

With a public name the hub can hold a proper certificate for `nadine.homehub.app` and for a local alias that resolves
to its LAN address, so the app has a trusted https origin at home too. That unlocks the browser microphone (the voice
plan's shape 1 on phones), web push and a clean Add to Home Screen, with no certificate profiles ever. The rough edge is
a phone at home with the internet down, which loses the public name and falls back to `http://hub.local`; the wall
panel never depends on the name at all.

## What this replaces

The https question in *Out of the Box* closes: plain http and the local certificate on the LAN stay as they are, and
the relay name is the https origin for phones. Tailscale and any VPN are out. `docs/voice.md` shape 1 waits on piece 3
for phones and on nothing for the wall.
