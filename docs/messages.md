# Messages: the catalog, and the way one reaches a phone

*Written 13 September 2026, from the question asked of the app: what does it take to catalog the house's messages
properly? The catalog in this file is not invented — it is the house's whole vocabulary read out of the code as it
stands today, 65 call sites in the panel and 15 kinds in the log. The plan is what to do with it. Delivery to a phone
that is not in the house waits on `docs/away.md` step 5; everything before that is work the browser path wants anyway.*

## The question, and the short answer

**One catalog, in the brain, where every message has an id and a class — and the class, not the call site, decides
where it goes.** Three channels: a receipt on the screen that asked, a chip in the band on every screen, and a push.
Two libraries for the whole thing: `pywebpush` on the hub, and nothing at all in the panel — the service worker is
sixty lines and hand-written, for a reason given below. No i18n library, no toast library, no notification framework.

Three answers were hiding in the one:

| | Answer | Why |
|---|---|---|
| **Where the catalog lives** | The brain | *The words come from the brain* is already the rule (`docs/settings.md`, README). A native shell must not reimplement them, and the panel ships with the hub so they version together |
| **What a message is** | An id, a class, a template and its subject | Today a message is a string built at the call site. Nothing can count them, route them, hold them back, or read them all in one place |
| **How one leaves the house** | Web push behind a service worker, after a trusted origin | `docs/apps.md` already has this as step 2 of *what to do now*, and `docs/away.md` step 6. Nothing here moves that order |

## What a message is here today

Six families, and they have almost nothing in common with each other. This is the catalog as it stands.

| Family | Written in | Who ever sees it | Survives the screen? | Reaches a phone away? |
|---|---|---|---|---|
| **Receipts** — *Renamed to Hall lamp.*, *Copied.* | 65 `notify()` calls across 19 files in `app/src` | Only the screen that did the thing | No, 2.8s | No |
| **The brain's words, carried** | `health.py`, `phones.py`'s refusal, every HTTP `detail` | Whoever hit the error; *Needs a look* on every screen | The note does, the toast does not | No |
| **The band** — a phone at the door, needs a look, an update | `Attention.vue`, `Asks.vue` | Every screen at home | Until answered | No |
| **A rule's note** — `{"notify": "<text>"}` | `rules.py` | **Nobody.** See below | In the log only | No |
| **The log** — 15 kinds: `home` `phone` `intent` `said` `state` `notify` `ask` `action` `draft` `held` `shadowed` `failed` `presence` `proposal` `comfort` | `log.add(...)` throughout `brain/hub/` | *Recent*, and *why* | Yes | No |
| **Sounds** | `sounds.py` | Whoever is in the room | No | No |

Four things are worth pulling out of that table before any plan is written on top of it.

**A rule's note reaches nobody, today.** `rules.py:262` broadcasts `{"type": "notify", "text": ..., "rule": ...}` on
the stream, and `connect()` in `app/src/api.ts:186-196` has a branch for `device`, `home`, `ambient`, `status`,
`intent`, `drafts`, `presence` and `phones` — and none for `notify`. The message is built, logged, and dropped on the
floor. `docs/phase4-intelligence.md` says of that outcome: *a message on the panel and, later, a push*. The panel half
was never wired. `why.ts:78` will even explain to a person that a rule *"Sends a note"* that no one will ever receive.
This is five lines and a test, it needs nothing from this plan, and it should be fixed before the plan is read.

**Nineteen of the 65 receipts are the brain's sentence in the panel's clothing** — `notify(e.message, 'error')`, or
worse, `` notify(`Couldn't move it: ${e.message}`, 'error') ``, which glues a panel phrase onto a brain phrase and
produces a sentence neither of them wrote. That is the seam a catalog exists to remove.

**Nothing here has an identity.** Not one of those 65 strings can be counted, suppressed, repeated, deduplicated,
translated, tested for tone, or looked up from a log line. The catalog's first value is not delivery. It is that the
house's vocabulary becomes a thing you can read in one sitting.

**The wall is not a phone.** Every family above assumes somebody is looking at a screen. That assumption is the whole
gap: it is fine for a receipt, and it is wrong for a door that unlocked at 2am.

## Rules that do not change

- **The class decides the channel, never the call site.** No code anywhere says "and push this". It says what happened;
  the catalog says what that is worth. This is the rule that keeps a future shell honest and keeps push rare.
- **The words come from the brain, except for the ones that only describe a tap.** *Copied.* and *Renamed to X.* are
  the panel narrating its own hand and stay in the panel forever. Anything the house knows — a device offline, a phone
  at the door, a rule that fired, an account signed out — is the brain's sentence, and the panel only carries it.
- **A message is never the only way to know something.** The panel's state is the truth; a message is a courtesy that
  arrives sooner. A missed push must cost a person nothing but time, or the house has become the notification.
- **Nothing vanishes under a tap.** What a message offers must still be there after the message is gone — the band
  chip, the note, the room. A message is not a place.
- **Alert-class is the household's list, not ours.** The hub ships with it nearly empty. A door, a lock, a smoke
  sensor: those are a person's choice on their own house, and the default is quiet.
- **A message never leaves the house in the clear** — and see *what the push service can see* below, because with web
  push that rule is kept by the encryption and broken by the metadata, and *This hub* should say so in plain words the
  way it says it about the relay.

## The catalog

A new `brain/hub/messages.py`: one table, one class, no dependencies. A message is five things.

| Field | What it is |
|---|---|
| `id` | `phone.asked`, `device.offline`, `account.signed_out`, `rule.note`, `update.ready`. Stable forever; the log line, the push tag and the panel's dedupe key are all this |
| `class` | One of the four below. The only thing that decides a channel |
| `text` | A template with named holes — `"{name} wants to join the house."` — and nothing else. No string built at a call site |
| `subject` | The device, room, phone or account it is about, so two messages about one thing can collapse into one |
| `way back` | The route and the words for its button, exactly as `health.py` already does with `flow`, `retry` and `do` |

Four classes, and the whole design is that there are only four:

| Class | Where it goes | Example | Pushed? |
|---|---|---|---|
| **`receipt`** | The screen that asked, for a breath | *Renamed to Hall lamp.* | Never |
| **`house`** | A toast on every screen at home, and the log | *Sam's iPhone joined the house.* | Never |
| **`attention`** | A chip in the band until it is answered, and the log | *Ring needs signing in again.* | To the owner's phones, quiet |
| **`alert`** | The band, the log, and a push that makes a sound | *The front door unlocked.* | Yes, and critical-class on a shell |

`receipt` is the only class the panel may raise on its own. The other three come down the stream, which means they are
already correct for a phone, a wall and a shell without any of them knowing anything.

The stream message grows from `{"type": "notify", "text": ...}` into
`{"type": "message", "id": ..., "class": ..., "text": ..., "subject": ..., "at": ...}`, and since nothing reads the
old one there is nothing to keep compatible — the orphan above is, conveniently, a free hand.

## Recommended: the libraries, and the two places not to take one

### The panel: no library. Write the service worker.

`app/` has exactly one runtime dependency today, and that is not an accident to be spent lightly. The obvious candidate
is `vite-plugin-pwa` (Workbox), and it should be declined — not on weight, but because **its default value is the one
thing this product must not do.** Workbox's whole argument is precaching the app shell and serving it first. The panel
comes from the hub it is talking to, and `docs/apps.md` builds the entire case for a web view on *the panel always
matches the hub*. A precached shell is a stale panel pinned against a newer brain, on a phone, with an update story
that now has two halves. It would reintroduce by build tooling the exact problem a native panel was rejected for.

So: `app/public/sw.js`, hand-written, about sixty lines, doing three things and refusing a fourth.

1. **`push`** — decrypt is the browser's job; the handler reads the JSON, and `showNotification` uses `id` as the tag
   so a second message about one subject replaces the first rather than stacking.
2. **`notificationclick`** — focus an open panel if there is one, else open at the route in *way back*.
3. **`fetch`** — network-first with a cache fallback, so a phone with no signal opens to the shell and the *House is
   not answering* screen instead of the browser's dinosaur. Network-first, never cache-first: the newest panel wins
   every time it can be reached, and the cache is only ever a fallback.
4. **Not** precaching, not versioned asset manifests, not background sync. If this file needs a build step, the plan
   has gone wrong the same way `docs/apps.md` says the shell has gone wrong if its list grows past four.

Registration goes in `main.ts` behind `'serviceWorker' in navigator`, and it will silently do nothing on
`http://hub.local` — which is correct. The wall does not want a service worker; it is never offline from the hub, and
it is the screen a notification would be delivered *to*.

### The hub: `pywebpush`, pinned, in a thread.

The encryption is the part not to hand-roll: RFC 8291 `aes128gcm` with a per-message ephemeral key, plus RFC 8292 VAPID
on the Authorization header. `pywebpush` is the standard implementation and carries `py-vapid`, `http-ece` and
`cryptography` with it.

The one snag is that it is synchronous (`requests`), and the brain is async throughout. `await asyncio.to_thread(...)`
per send is enough — pushes are a handful per day, not a stream. The alternative, `py-vapid` + `http_ece` + the
`httpx` already in dev requirements, is roughly eighty lines of our own and native async; it is the right trade only
if `requests` in the image is judged worse than owning the encoding, and it is not.

**The keypair is the hub's, made once**, kept beside `phones.json` in the data directory so it **rides the backup** —
a house restored onto a new box keeps its phones' subscriptions working, which is the same property pairing already
has and for the same reason. The VAPID `sub:` claim must be the maker's address, never the household's: it is sent to
Apple and Google on every message and it is not the house's business to identify itself to them.

**A subscription belongs to a phone**, not to a person — it joins `phones.json` next to the token hash, so *Remove*
already removes it and there is no second list to keep honest. One route, `POST /phones/me/push`, and nothing else new.

### What the push service can see, and why it is still allowed

The payload is end-to-end encrypted to a key pair the phone made and never sent anywhere, so Apple, Google and Mozilla
carry a message they cannot read — the same property the relay was chosen for in `docs/away.md`, arrived at the same
way. What they do see is **that a house sent something to that phone, and when**. That is metadata the relay does not
leak, it is the one place this product touches a big company's infrastructure, and it is the reason the default stays
quiet: a house that pushes a receipt for every tap has published its occupancy schedule to a third party one heartbeat
at a time. *This hub* should say this in the same plain words it uses for the relay.

### Two libraries explicitly not taken

- **No i18n library.** Nothing in the docs asks for a second language and adding `vue-i18n` now would be a framework
  bought for a requirement that does not exist. But note what the catalog gives away for nothing: an id, a template
  and named parameters *is* a message catalog in the gettext sense. The day a second language is wanted, the work is
  a second table and a lookup — not 65 call sites. That option is worth having, and it is free here.
- **No toast library.** `notify()` and `dismissToast()` in `store.ts` are eight lines and already correct, including
  the Undo affordance. The catalog changes what is passed to it, not it.

### And the shell, when it comes

The catalog is what makes the native shell in `docs/apps.md` small. APNs replaces the transport; `id`, `class`,
`subject` and *way back* cross unchanged, and the shell's push registration is one route the browser also calls.
Critical alerts — the 2am door, the one capability a browser genuinely cannot have — become a property of the `alert`
class on one transport, not a feature anybody writes twice. That is the four-item list in that document staying four.

## Order

The first two are today's work and depend on nothing.

1. **Wire the orphan.** A `message` branch in `connect()`, `notify()` on the far end of it, a test that a rule's note
   reaches a screen. Five lines against a documented outcome that has never worked.
2. **`brain/hub/messages.py` and the classes.** Move the 19 `e.message` receipts and everything in `health.py` onto
   ids. The panel keeps the receipts that describe its own hand and loses the rest. No delivery work at all in this
   step — it is a refactor whose output is a file you can read the house's whole voice out of.
3. **The band and the log read the catalog** rather than each assembling its own sentence. *Recent* can then say
   what a message was, not just that one happened.
4. **The service worker**, with the offline shell only. This is `docs/apps.md` step 2 and it lands as soon as there is
   a trusted origin — `docs/away.md` step 5 — and not before, because a service worker on the wall's plain `http://hub.local` is inert, and on the hub's own CA it is only as trusted as the certificate a phone was made to install.
5. **Push: the keypair, `POST /phones/me/push`, `pywebpush`.** `docs/away.md` step 6.
6. **The switches on *People*** — per phone, `attention` off by default and `alert` off by default, landing with the
   `remote` switch in the same step for the same reason: the panel never shows a promise it cannot keep.

## Open decisions

- **Who gets an `attention` push** — every phone that *can change things*, or one chosen phone? Every owner is the
  simpler rule and the noisier house. Recommend every owner, with the per-phone switch as the answer.
- **Does the wall ever push?** No. It is a screen in the room; it wakes from its clock, which pairing already does for
  a phone at the door. Recorded here so it stops coming back.
- **Does the wall ever SPEAK an alert?** *Asked for on 15 September 2026 — someone at the dining table, and the front
  door opening in the living room.* Yes, eventually, as a **fifth channel on the `alert` class** and never as a
  default: a household turns it on, and the house then announces whether or not anybody is in the room. It is
  `docs/voice.md`'s *Announcing*, and it waits on step 2 of the Order above, because a channel is something a class
  routes to and there is no class yet. Three things about it belong here rather than there: *alert-class is the
  household's list, not ours* is what makes it allowable at all; *a message is never the only way to know something*
  holds, because the band, the log and the push are all still there and the wall is a fourth way rather than the way;
  and the wall speaking does not earn it a push, so *does the wall ever push* above stays No.
- **Is a rule's note ever an `alert`?** The rule's author is a person writing a sentence, which means the class would
  have to be theirs to choose — a switch on the routine. Probably yes, probably not in the first cut.
- **Rate limits.** Push services throttle, and iOS holds a budget per home-screen app that a chatty house will spend.
  The `receipt` class never leaving the screen is most of the defense; a floor on how often one `id` may repeat for
  one `subject` is the rest.
- **How much history a message keeps.** The log already holds it, and *Recent* already renders it, so probably none of
  its own — but a phone that was off for a day and comes back should perhaps see what it missed, and that is a list
  nothing in the panel currently draws.
