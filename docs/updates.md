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

### 2. A signature *(landed 16 September 2026)*

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

**What landed.** `tools/release-manifest.py` builds the record for a tag, resolving every digest by asking the
registries anonymously rather than the local Docker daemon — a laptop with an old layer cached would otherwise sign a
digest nobody else can pull. `tools/release.sh` makes the keypair (`--new-key`, once ever) and signs a tag;
`driver-layer/host/verify.sh` is what a hub checks with, and `install.sh` calls it before the checkout moves and then
checks out **the commit the manifest names**, not the tag. Every image in `docker-compose.yml` became
`${HUB_IMG_<SERVICE>:-<the tag>}`, so a verified release pins by digest and the tag stays as the readable default and
the record of what was tested.

**Where the keys live is the whole design.** Not in `$DIR`: that is the thing being updated, so a key kept only there
could be replaced by the same push it exists to catch. They are copied once into `/etc/home-hub/release-keys.d/` on
the first install and never added to. **The first install trusts the repository it came from; every update after it
trusts the keys.** That boundary is real, and the flashed image narrows it, because the image was built from a tag and
carries the keys already.

**A directory, not one file**, and that part is done now because it cannot be done later. A hub never adds a key after
its first install — a key arriving from the repository afterwards is exactly the push this exists to catch — so a
second key has to be there from the beginning or it can never be there at all, and without one, losing the first means
no hub in any house can be updated again, ever. `tools/release.sh --new-key spare` makes it; keep it offline,
somewhere other than the first, and never sign with it until you have to. Any key in the directory may sign a release.
This closes the open decision this document opened with.

**Two corrections to what this document said before it was built.**

- **`rollout` and `hold` are not in the release manifest.** They were written down here as fields of it, and they
  cannot be: a signed per-release file cannot be changed without re-signing, and piece 5 wants a hold that takes
  effect in minutes. They belong in a separate, separately signed channel file. Piece 5 owns it.
- **A release that cannot be checked is not a failed update,** and folding the two together would have been the
  panel's mistake, not the host's. `install.sh` exits 3, `update.sh` writes a `refused` state, and the health line
  says the house is working and carries **no Try again** — the same tap refuses the same release, and sending a
  household round that loop is worse than telling them plainly that this one is not theirs to fix.

**Cosign is checked by the maker, not by the hub.** CI signs the image keylessly on every tag, and `tools/release.sh`
verifies that signature — the workflow, the repository and the tag — before it will put the maker's key to a manifest.
So the two signatures nest rather than sit side by side: hubs hold one ed25519 public key and need no cosign binary,
no Sigstore root and no network beyond the release, and the maker's signature still cannot be given to an image this
repository's workflow did not build.

**What was verified**, again by standing it up rather than reading it: a real git repository with two tags, a real
ed25519 keypair, real `openssl`, and a fake releases server behind a `file://` URL. It installs a release signed by
the maker whose tag and commit agree, and refuses, with a sentence naming the reason each time: a tag moved onto
another commit after signing; a manifest signed by a different key; a manifest edited after signing; a release with no
signed record at all; a record naming a different version; and an upgrade path below `min_from`. A hub with no key yet
returns 2 and says so rather than pretending either way. Separately checked that a good verification leaves the caller
holding `VERIFIED_COMMIT`, the brain digest and one `HUB_IMG_*` per service — under exactly the names
`docker-compose.yml` reads, which is a spelling mistake away from silently falling back to tags — and that the compose
file still resolves to the pinned tags when nothing is set.

**What is not covered.** The first install, by construction: `curl | bash` from `main` trusts the repository, and so
does the `git clone` under it. Nothing verifies `install.sh` itself on that first run, and the honest fix is the
flashed image rather than a cleverer script. Also `tools/release.sh` has to be run by hand after CI publishes a tag's
images — it needs the digests to exist — so there is a window where a tagged release exists and hubs refuse it. That
is the right way round, and it is still a reason not to leave a tag sitting unsigned.

### 3. By itself, at night *(landed 16 September 2026)*

Only after 1 and 2, and the order is the point: automatic updating from an unverified source is the supply-chain
problem with the human taken out of it.

**On by default, in the small hours, when nothing has been asked of the house for a while.** Not a fixed 3am for every
hub — a window, jittered by the hub's own identifier, so a bad release does not take every house in the same minute
and so the maker's endpoint is not asked for a manifest by ten thousand hubs at once. Never while somebody is driving
the house, and never inside a few minutes of anyone touching the wall.

**One switch, under *This hub*, and it stays where it is put.** *Install updates on its own — Yes / Ask me first*.
Choosing *Ask me first* is the panel exactly as it is today.

**Urgent is a property of the release, not of the hub.** A manifest may say `urgent: true`, and an urgent release
installs at the next quiet moment rather than waiting for the window. It still respects a household that turned
automatic off; what it does there is nudge harder and say why. *(Not built — see the correction below.)*

**The morning after is the feature.** This is the piece that changes what notes are *for*: nobody reads them before a
tap they never make, so they belong on the wall the next morning, as one dismissible card saying what is new. Which is
piece 4.

**What landed.** `Settings.hub_id()` is the identifier — random, made once, kept in `settings.json` so it rides the
backup, and deliberately not derived from the hardware: a MAC address would leak something about the house to anything
the id is ever shown to, and would change under a household that moved the hub onto a new box, which is the one moment
it most wants to still be the same hub. `Updates.minute_of_the_night()` hashes it into a minute of the window;
`due()` holds the conditions; the loop ticks every five minutes and asks. `EventLog.last_user()` is the "is anybody up"
test, with an index to match. The switch is `POST /update/auto`, behind the settings code like every other change to
the house, and a row under *This hub*.

**The default resolves itself, so it needed no decision.** `auto` is on where the hub can check what it is installing
and off where it cannot — `install.sh` writes `HUB_VERIFIED=1` into the compose environment when the key directory has
something in it, and the brain reads that and nothing else. So the rule is one sentence: **a hub only updates itself
without being asked if it can prove what it installed and undo what did not work**, which is pieces 2 and 1 exactly.
A household's own answer outranks both and stays said. Getting `HUB_VERIFIED` wrong makes a hub shy, never reckless.

**An automatic install is logged as `source: "hub"`**, not `"user"`. A household that finds the hub on a new version in
the morning should be able to see under *Recent* that nobody in the house did it.

**One correction.** `urgent` was written down here as part of this piece and is not built. It needs the brain to read
the manifest, which is piece 4's fetch, and on its own it buys very little now that updates land nightly anyway: the
gap it closes is the few hours between a fix being signed and the next window. It moves to piece 4.

**What was verified.** Sixteen tests over `due()`, because it is a conjunction and every term is a way to get it
wrong: off for a hub that cannot verify, on for one that can, the household's answer beating both; nothing at half
nine at night, at half past midnight, at half five in the morning or at noon; nothing a minute before this hub's own
minute and something a minute after; still due half an hour later, so a hub that was busy at its minute tries again
the same night rather than waiting a day; six hub ids landing on more than three different minutes, all inside the
window, and the same id landing on the same minute every night; nothing while somebody was up in the last half hour
and something once they have been quiet for it; nothing when there is nothing to install, when the version was put
back, when an update is already running, or when somebody has just tapped; one go a night and then the next night;
and the log saying `hub`.

### 4. Notes written for a house *(landed 16 September 2026)*

`releases/0.3.0.md` in the repository, with a `what` section of two to four plain sentences about effects — *speakers
remember their volume*, *the kitchen appears on the wall faster* — and an optional `details` for whoever wants it. CI
folds it into the signed manifest and into the GitHub release body, so there is one copy and it is the signed one. The
hub caches it, which is what makes notes readable with the internet down and, more to the point, readable **after** the
update, when the household actually wants them.

On the panel: a *What's new* card the morning after, dismissible, and a *What's new* sheet under *This hub* with the
current release at the top and the history under it. The history is what answers *when did the hub start doing that?*,
which is the question a household actually asks.

**A release with no notes file does not ship.** Better a tag that fails CI than a family reading a commit subject.

**What landed, and the one place it departs from the plan above.** The notes are **not fetched and not read out of the
manifest** — they are copied into the brain's image (`COPY releases/ /srv/releases/`) and read from there. That is
strictly better than what this document originally described, and it fell out of a constraint: the brain has no
ed25519 anywhere in its dependencies, so it could not have verified a manifest it fetched. Reading them from the image
means the notes a hub shows are the notes for the code it is actually running, they need no verification of their own
because the image was already verified, they read with the internet down, and **the history is free** — the image
carries every release file up to its own version, so *This hub → What's new* has one without storing anything.

The rest: `releases/README.md` is the format and the rules; `brain/hub/notes.py` is the parser;
`tools/release-manifest.py` **refuses to build a record for a tag whose notes are missing or read like a changelog**,
which is the part that makes the rule real rather than aspirational. `tools/release.sh` publishes the same file as the
GitHub release body, and `Updates.fetch()` parses it, so the release *waiting* to install is described in its own words
too — that one is unverified, and it describes without ever deciding.

**The card is on Home the morning after, and does not vanish under the tap.** It carries the words themselves rather
than a link to them, it opens *This hub* when tapped, and **opening that page is what marks it read** — somebody who
came to look has, by definition, looked. A hub that has only ever run the version it is on marks its own version read
at startup and says nothing: somebody who has just plugged one in is being set up, not caught up.

**Checked on the glass**, not only in tests: `WHATSNEW=1 npm run mock` puts both states in the panel. The first attempt
put the lines in a `<ul>` inside the row and every line came out wearing the row's own pill, which is what looking at
it is for; the second reads as prose, like every other row on that page.

**What was verified.** Sixteen tests in `brain/tests/test_notes.py` over the parser (both sections, only one section,
prose outside a heading, `*` bullets, nothing at all, the `v` prefix, a build with no notes), the history (newest by
version and not by name, so `0.10.0` beats `0.9.0`; the README in that folder is not a release; no folder at all is an
empty history and not a crash) and what the wall shows (nothing on a hub that has only ever run this version; once,
and then not again, on one that updated; nothing for a release that shipped without notes; nothing for one with only
a Details section, which is still readable on *This hub*). Nine cases against the checker: a commit subject, Home
Assistant, entities, a filename, a commit hash, a container, no lines, too many lines, no file at all.

### 5. A hold and a rollout

~~**A stable hub identifier**~~ — **done with piece 3.** `Settings.hub_id()`, and `minute_of_the_night()` is the
worked example of hashing it into a bucket that piece 5 repeats against `rollout`.

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

- **Whether there is a spare key, and where it lives.** The mechanism no longer forces the answer — `verify.sh` trusts
  a directory — but the answer still has to be given before the first hub ships, because a hub never adds a key after
  its first install. Recommended: two keys, made at the same time, on different machines, the spare never used until
  it has to be.
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
