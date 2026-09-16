# Updates: the plan

*Decided 16 September 2026. A hub in somebody else's house stays current without being asked, undoes an update that
does not come back, and installs nothing the maker's key did not sign. Release notes say what changed in the house,
not what changed in the repository.*

## Why this needs a plan at all

Updating already works, and the shape of it is right. The brain knows which build it is, asks GitHub a few times a day
whether there is a newer one, and when there is, Home says *An update is ready*. One tap, behind the settings code,
writes `brain-data/update.request`; a systemd path unit on the host sees the file and runs `update.sh`, which runs
`install.sh`, which moves the checkout to the newest tag on this hub's channel, pulls the images and starts everything
again. `update.json` in the same directory says how it went, and the brain reads it back to the panel.

Three properties of that are worth keeping and are not in question. **The brain never runs Docker and never restarts
anything** — it parks a file and waits, so the thing with a network port is not the thing with root. **The request file
is advisory only**: `update.sh` takes the channel from `driver-layer/.env`, never from the file, so a process that can
write into `brain-data/` can ask for an update but cannot choose what gets installed. And **code and container move
together**: a hub on `v0.2.0` runs the `0.2.0` image, not whatever is newest.

What is missing only starts to matter when the hub is in a house that is not this one.

| Gap | What it looks like in a house | What it costs |
|---|---|---|
| Nothing verifies what arrives | `git reset --hard` to the newest `v*` tag; `docker compose pull` by tag | The trust anchor for root-level code in someone's home is "whoever can push to GitHub" |
| No way back | The brain does not start; the wall is dark | A family with no ssh and no recourse, and a maker who finds out by telephone |
| Nobody taps | The hub sits three releases behind for a year | The security fixes do not land, which is the actual security problem |

The third is the one that makes the other two urgent. Every appliance a household already owns — the television, the
speakers, the thermostat — installs its own updates overnight and tells them in the morning. A hub that waits to be
asked is a hub that is never asked, and a stale hub is not a neutral outcome: it is the one running the bug that was
fixed in March. So this plan ends with the hub updating itself. Everything before that exists to make automatic safe:
**a hub may only install without being asked once it can prove what it installed and undo what did not work.**

## Rules that do not change

- **The brain never runs Docker.** It writes a file. The host does the work, as root, out of the brain's reach.
- **Nothing installs that the maker's key did not sign.** The transport is untrusted on purpose: a CDN, a registry and
  a git remote are all things somebody else runs. The signature is what makes them not matter.
- **An update that does not come back is undone by the hub, not by a person with ssh.** A household's only repair
  tool is the wall, and the wall is the thing that is missing.
- **A person can always still decide.** Automatic is the default because it is the right default, not because the
  choice was taken away. One switch turns it off and it stays off.
- **Notes are about the house.** No filename, no container, no commit subject, no version of anything rented, and —
  the rule that already holds everywhere else — nothing that mentions Home Assistant.
- **The house says what it did.** Every update, every refusal and every rollback is an event in the log, and the
  morning after is where a household finds out what changed.
- **Works with the internet down.** A hub that cannot reach the maker installs nothing and says nothing, and the house
  is untouched. Undoing an update never needs the network, because the image it goes back to is already on the disk.

## Where this stands today (16 September 2026)

- `brain/hub/updates.py` — `HUB_VERSION` and `HUB_COMMIT` are baked into the image by CI (`brain-image.yml` passes
  them as build args). `Updates.check()` runs 90 seconds after start and every six hours, asks
  `/repos/{repo}/releases/latest` on the `release` channel or `/commits/main` on `main`, and `available` is deliberately
  three-valued: `None` when nobody can tell, because a panel saying *Up to date* when it does not know is a lie
  somebody acts on.
- `POST /update` is behind the settings code (`brain/hub/lock.py`), and `request()` writes the file.
- `driver-layer/host/update.sh` — reads the channel out of `.env`, runs `install.sh`, writes `running` / `done` /
  `failed` into `update.json`, and keeps the installer's output in `update.log`.
- `brain/hub/health.py` — a `failed` state becomes a *Needs a look* line with *Try again*.
- The panel — `Attention.vue` nudges on Home, `HubPage.vue` shows the version and the button.
- **Notes: the release title, cut at 120 characters.** `fetch()` takes `d["name"]` and drops `d["body"]` on the floor,
  so what a household reads is a commit subject: *feat(sort): implement scrolling behavior for New devices list*.
- **There is no stable identifier for a hub.** Piece 5 needs one and nothing else in the repository provides it.
- **The driver layer is pinned by tag, not by digest.** `2026.9.1` is a name upstream can move.

One nuance the panel already gets almost right. *Tap to install; the lights keep working* is true for an ordinary
update, because the pins in `docker-compose.yml` have not changed and `compose up -d` recreates only the brain. It is
not true for the update that bumps Home Assistant, where the engine restarts and the house is deaf for half a minute.
The sentence should be earned rather than assumed: the manifest of piece 2 knows which images are moving, so the panel
can say *a minute where switches still work but the app does not* only when that is what is about to happen.

## Five pieces, in order

### 1. Undo *(landed 16 September 2026)*

Nothing else on this list is safe to ship first, and the reason is narrow: every later piece makes updates happen more
often and with less human attention, and the current failure mode is unbounded. `git reset --hard`, `compose up -d`,
and if the brain does not start there is nothing on the wall to press.

**Snapshot, apply, prove, keep or put back.** Before `install.sh` is called, `update.sh` records where the hub is —
the current commit and the image the brain container is actually running, taken by digest from the daemon rather than
from any file that could disagree with it — into `update.prev`. After the installer returns, the host proves the house
came back by asking the brain itself, on `127.0.0.1:8300`, and waits for an answer for up to five minutes.

**What counts as proof.** A single answer is not enough: an image that starts, answers, and then crash-loops would
pass. The brain must answer, and then still be answering after a settle of forty-five seconds. That is cheap, it
needs no new state, and it catches the two failures that actually happen — an image that will not start at all, and
one that starts and immediately falls over on the data it found.

**Putting it back needs no network.** The previous image is still in the local store, so the revert is a
`git reset --hard` to the recorded commit, the recorded digest pinned into `.env` as `HUB_BRAIN_IMAGE`, and
`compose up -d`. A hub that broke itself on a bad release recovers with the internet down, which is the condition it
is most likely to be in if the thing that broke was the network.

**And then it must not do it again.** `update.json` gains a fourth state, `reverted`, carrying the version that was
rejected. The brain reads it and stops *offering* that version: Home does not nudge for it, `This hub` says
*Version 0.3.1 did not start, so the hub put back 0.3.0*, and the button underneath still works, because a person
choosing to try again is a different thing from a hub deciding to. Piece 3 reads the same state and will not install
a rejected version by itself, ever.

**The probe is a new route.** `GET /alive` — `{"ok": true, "version": ..., "commit": ...}`, open to strangers because
the host asking is a stranger, and carrying nothing about the house. Everything else the brain serves is either behind
the phone cookie or is the panel's own files, and reusing one of those to mean "alive" would tie the safety net to a
pairing decision that has nothing to do with it.

**A small latent bug closes with it.** `install.sh` exports `HUB_BRAIN_IMAGE` into the environment of its own
`compose` call and writes it nowhere, so a hub whose containers are recreated by any other means — a person running
`docker compose up -d` by hand — silently falls back to `:latest` and breaks the rule that code and container move
together. The pin belongs in `.env` next to `HUB_CHANNEL`, written on every run.

**What landed.** `driver-layer/host/update.sh` does the snapshot, the proof and the put-back; `update.prev` holds the
commit and the image; `update.json` gains `reverted` and names the version in `bad`. `GET /alive` is the probe, open in
`hub/phones.py` alongside the panel's own files. `Updates.offer` in `hub/updates.py` is `available` minus a rejected
version, and the panel's nudge reads `offer` where it used to read `available` (`store.ts`, `Attention.vue`); *This hub*
says which version was put back and its button becomes *Try again*. `install.sh` now writes `HUB_BRAIN_IMAGE` into
`.env`, which is what makes the pin survive a compose run by any other hand.

**What was verified**, by standing it up rather than reading it: a real git repository with two commits, a fake
installer that moves the checkout the way the real one does, and a `curl` and a `docker` that can be told whether the
house answers. Four endings, each one checked for the state written, where the checkout ended up, and whether the pin
was left behind — it installed and came back (`done`, on the new commit); it installed and did not come back
(`reverted`, back on the old commit, old digest pinned in `.env`); it did not come back and neither did the one put
back (`failed`, `reverted: false`, and the version named rather than a rollback claimed that did not take); and the
installer itself stopping part way (put back, `failed`). The request file is gone in all four, so a hub cannot loop.

**What is not covered, and is worth knowing.** The proof is *the brain answers*. An image that starts, serves, and is
subtly wrong — a panel that renders nothing, a migration that quietly dropped the rules — passes. Catching that needs
the panel to check itself, which is a different piece and probably belongs with piece 5's telemetry rather than here.
And CI lints `update.sh` but does not run it; the harness above is a scratchpad script, not a test, which is a gap to
close when the shell job grows a way to run one.

### 2. A signature

Today the answer to *what may run as root in this house* is *whatever the newest `v*` tag points at*. Tags move; a
stolen token, a compromised Action or a bad afternoon at GitHub all reach every hub. The fix is not to trust the
transport less carefully — it is to stop trusting it at all.

**A signed manifest per release.** CI publishes `release.json`: the version, the commit, the brain image **by digest**,
every driver-layer image **by digest**, the oldest version that may upgrade straight to it, the rollout state piece 5
needs, and the notes piece 4 writes. It is signed with an ed25519 key **that does not live on GitHub**, and the public
key is in the image and in the checkout. The hub verifies the signature before `install.sh` moves a byte, and pulls
every image by digest. A tag that moves then changes nothing, because nothing reads a tag any more.

**Two signatures, and they defend different things.** Cosign keyless on the image build is nearly free and binds *this
image was built by this workflow, in this repository, from this commit* — it stops a registry compromise and a moved
tag. It does **not** stop somebody who can push to the repository, because the workflow would sign their commit just as
happily. Only the offline key does that, and the whole reason it is worth the inconvenience is that it is the one key
an attacker who owns the GitHub account still does not have. Both, and be honest in this document about which does
which.

**Where the manifest is served** is deliberately not interesting: the maker's own zone through Cloudflare, with GitHub
releases as the fallback, because the signature is what makes the path not matter. It is DNS and a static object, so
it is Terraform like everything else in `docs/away.md` — nothing about it is clicked in a console.

**Rented images too.** `2026.9.1` is a name Home Assistant can move, and the hub pulls it as root. Once the manifest
carries digests, the pins in `docker-compose.yml` become the record of what was tested and the manifest becomes what
is installed.

### 3. By itself, at night

Only after 1 and 2, and the order is the point: automatic updating from an unverified source is the supply-chain
problem with the human taken out of it.

**On by default, in the small hours, when nothing has been asked of the house for a while.** Not a fixed 3am for every
hub — a window, jittered by the hub's own identifier, so a bad release does not take every house in the same minute
and so the maker's endpoint is not asked for a manifest by ten thousand hubs at once. Never while somebody is driving
the house, and never inside a few minutes of anyone touching the wall.

**One switch, under *This hub*, and it stays where it is put.** *Install updates on its own — Yes / Ask me first*.
Choosing *Ask me first* is the panel exactly as it is today.

**Urgent is a property of the release, not of the hub.** A manifest may say `urgent: true`, and an urgent release
installs at the next quiet moment rather than waiting for the window or for a week of quiet. It still respects a
household that turned automatic off; what it does there is nudge harder and say why.

**The morning after is the feature.** This is the piece that changes what notes are *for*: nobody reads them before a
tap they never make, so they belong on the wall the next morning, as one dismissible card saying what is new. Which is
piece 4.

### 4. Notes written for a house

`releases/0.3.0.md` in the repository, with a `what` section of two to four plain sentences about effects — *speakers
remember their volume*, *the kitchen appears on the wall faster* — and an optional `details` for whoever wants it. CI
folds it into the signed manifest and into the GitHub release body, so there is one copy and it is the signed one. The
hub caches it, which is what makes notes readable with the internet down and, more to the point, readable **after** the
update, when the household actually wants them.

On the panel: a *What's new* card the morning after, dismissible, and a *What's new* sheet under *This hub* with the
current release at the top and the history under it. The history is what answers *when did the hub start doing that?*,
which is the question a household actually asks.

**A release with no notes file does not ship.** Better a tag that fails CI than a family reading a commit subject.

### 5. A hold and a rollout

**A stable hub identifier**, made once and kept in `settings.json` — random, not derived from hardware, and it rides
the backup. Nothing else in the repository provides one, and pieces 3 and 5 both need it.

**`rollout: 0.1` in the manifest**, against a hash of that identifier, so a tenth of hubs take a release first and the
rest follow when it is raised. **`hold: true`** stops it spreading at all, in the minutes after somebody notices,
without cutting another tag. And **`min_from`** refuses an upgrade path that was never tested rather than discovering
it in a house.

**One line of telemetry**, opt-out, and it needs to be small enough to describe in a sentence on the panel: the hub
identifier, the version it moved from, the version it moved to, and whether it worked. Nothing about the house, ever.
Without it a rollout that is failing looks exactly like a rollout that is going fine.

## One thing to fix regardless of all of the above

`brain/hub/lock.py` only bites when a code is set, and setup *nudges* rather than requires. On a hub with no code,
anyone on the Wi‑Fi can trigger an update, **download the backup** — which carries the radios' network keys, Ring's
sign-in and the hub's own certificate authority — or restore one over the top. That is a defensible choice for a hub
on the builder's own bench and not one for a hub that was handed to somebody. **A code becomes a required step of
setup**, not a nudge that Home repeats.

## Open decisions

- **Who holds the signing key, and what happens when it is lost.** A second key in the manifest from the start costs
  nothing now and is impossible to add later, once hubs are in houses that only trust the first one.
- **Does a hub ever refuse to run an old build?** A release old enough to be dangerous is exactly the one on a hub
  that has been off for a year, and refusing to start is the worst possible way to tell somebody.
- **What the wall says while the engine is restarting.** For most updates only the brain moves and the panel blinks;
  for an update that bumps Home Assistant the house is genuinely deaf for half a minute, and the panel should say so
  in advance rather than apologise afterwards.
- **Whether the driver layer can move without the hub moving.** Today it cannot, which is a good rule and also means a
  Home Assistant security fix waits for a hub release. Probably right; worth writing down that it was chosen.

## What this replaces

Nothing in `docs/away.md` changes. The relay and the manifest endpoint are the same maker infrastructure and the same
Terraform; a hub that has registered a public name has an identifier piece 5 could reuse, but pieces 3 and 5 must not
wait on the relay, so the identifier is made locally and independently. The *Updates* line in `README.md` describes
what is built today and is updated by each piece as it lands.
