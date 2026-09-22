# Settings without a settings page

*Written 10 September 2026. This is a plan, not a build. The goal it serves: nobody who receives a hub ever opens
Home Assistant, ring-mqtt's page, or anything other than the panel. Home Assistant stays the rented engine and is
touched only through its APIs; independence is from its UI, not from it.*

## Where we start

The panel has no settings page on purpose. The rule was **a setting lives next to the thing it changes**: a device is
renamed on its tile, a room on its heading, the place under the sky, the code on the first change that asks for it,
routines on the Routines sheet, the assistant's key beside the routines it writes. *This hub* is the one sheet about
the hub itself: software, backup, restore, the phone. A settings page is where a product puts what it did not want to
design, and the whole point of this one is that a person is never asked to find anything.

That rule was only half of the design. The other half was **the Advanced door**: anything the panel could not do was
sent to Home Assistant's own UI at `:8123`. It was the right shortcut for a first cut, because Home Assistant's
configuration surface is enormous and reproducing all of it is a losing game. But every Advanced link is a place the
product admits it stops, and there are five of them: the bottom of the Add sheet ("for anything this page cannot
add"), the Code sheet, *This hub*, the setup screen ("Stuck? Open Home Assistant to reset the password"), and the raw
address `prove/SignIn.vue` hands a maker's page that asks for it.

## What still needs another interface

Found by reading the brain and the panel, ranked by how soon a household hits it.

1. ~~**Signing in again.**~~ **Done, 10 September 2026.** HA opens a flow of its own when a token dies, and the panel
   now draws it: each one reaches Home as a *Needs a look* line with the button that finishes it. See *What landed*.
2. ~~**Removing anything.**~~ **Done, 12 September 2026.** An account is removed from the *Accounts* door; a device is
   forgotten from its row when a room is being edited. See *What landed* and the order below.
3. **People.** Presence reads Home Assistant's person entities (`brain/hub/presence.py`), and the only way to make a
   person and give them a location is Home Assistant's UI plus its companion app. "Is anyone home?" depends on two
   interfaces the product says do not exist.
4. **Who is using the panel.** One owner, one shared code, no idea who is holding the phone. Fine for two adults; not
   for a household with a child, a guest or a cleaner.
5. **Ring.** ring-mqtt's own page does its sign-in, once. A third interface.
6. **The engine's password.** The brain made that login and keeps it, yet the setup screen sends a stuck person to
   Home Assistant to reset it.
7. **A device's own settings.** Home Assistant's *options flows* (a camera's stream quality, a thermostat's mode, a
   bridge's polling) are not drawn at all.
8. **The long tail.** Brilliant through HACS, anything the catalog hides, anything a maker's integration wants that
   the form renderer does not draw yet.

## The shape: four nouns, not a page of knobs

Keep the rule and give it a home. *This hub* on Home becomes the one entry, and it lists four things. Each is a sheet,
each is a conversation in the house's words, and most already exist in some form. Apple's trick is not having no
Settings; it is that Settings is a list of nouns and every noun opens a conversation.

### People

Who lives here, which phone is theirs, and whether they can change things or only control them.

- **A person is a phone, not an account.** No usernames, no passwords. The QR flow that already puts the house on a
  phone (`PhoneSteps.vue`, `GET /phone`, `GET /qr.svg`) grows one step: *Add a person* on the People sheet shows a
  code, the phone scans it, the panel asks the person's name once, and the phone keeps a key the brain minted for it.
  Every request from that phone carries the key; the brain knows who tapped. The wall panel stays anonymous and keeps
  the shared code for changes.
- **Two roles, in plain words.** *Can change things* (add, rename, move, routines, sign in) and *Can control* (lights,
  scenes, doors). A guest is a *Can control* phone with an end date; the link stops working on its own.
- **Presence without Home Assistant's app.** The house needs to know who is home and it must work with the internet
  down. Two sources, in this order:
  1. *The phone on the Wi-Fi.* The hub already speaks mDNS and sits on the LAN; it can see each known phone come and
     go. Zero install, local, and it covers the person who never opens the app. Phones sleep their radios, so
     "gone" needs a grace period of tens of minutes, and "arrived" is immediate.
  2. *The phone saying where it is.* The PWA reports its location while open or when the system wakes it. Precise,
     but browsers limit it, and iOS limits it most. A refinement, not the foundation.
  The brain's presence module reads its own people instead of `person.*` entities; the alarm keeps its override.
- **Where it lives.** People rows show name, phone, role, and a plain *home* or *away*. Removing a person forgets the
  phone; the phone's app says so next time it opens.

### Accounts

Every service that needed a sign-in, with one of three states and two buttons.

- **States.** *Connected*, *Needs signing in* (the token died), *Not answering* (the service is down or the internet
  is). The first two are already known: `provision.py` holds the open sign-ins and the entries that could not start.
- **Sign in again.** Done, and offered from Home; the sheet gathers the same rows into one place, so an account can be
  signed in again before the house has noticed anything is wrong.
- **Remove.** Delete the config entry through Home Assistant's API; the brain forgets the devices it brought, and any
  room tile that pointed at them. Ask once, in words that say what disappears.
- **Ring inside the panel.** Either the brain drives ring-mqtt's sign-in itself (Ring's token flow is an email,
  a password and a code from a text; the brain writes the refresh token where ring-mqtt reads it and restarts it),
  or Ring moves to Home Assistant's own Ring integration and falls into the standard flow path for free. Decide by
  what ring-mqtt was chosen for (streaming, events) before picking; see *Open decisions*.
- **Keys people had to make.** Nest's and Google's application credentials are already stored and guided; the row
  shows that a key exists and offers to replace it, so a revoked project is fixed without starting over.

### Devices

Already the product: room tiles, *New devices*, *Found nearby*. What is missing is the end of a device's life and its
own settings.

- **Forget.** Built, and **not** where this said it would be: `DELETE /devices/<id>` is reached from the room's
  edit screen and from a fault report, and the tile's long-press still offers only rename and move. That gap is what
  `design/forget/` argues about — the same question for a light strip, a wall switch on the mesh and a sensor with no
  tile at all, none of which a per-device route can answer on its own. Two kinds do not go through the registry:
  a mesh switch is forgotten at its bridge (`docs/brilliant.md`) because the puck re-announces it otherwise, and a
  light strip is asked to forget the house as well (`docs/strip.md` item 37) so it can be set up somewhere else.
- **Settings.** The same long-press draws the device's options flow when its integration has one, through the form
  renderer in `onboarding.py`, in the integration's own English. No new vocabulary; most people never open it.
- **Provisioning.** Keep *Found nearby* first. Add one line of "what to expect" per kind before a flow starts (a bridge
  wants its button pressed; a camera wants its app open once; a Google account wants ten minutes and a key), and keep
  failed flows retryable from the Add sheet, which `POST /setup/retry` already allows.

### This hub

As it is, plus the few things that are about the hub and nothing else.

- **The code.** The Code sheet moves in here; it is a property of the hub, not of the first change that asked.
- **The address.** `hub.local` and the Wi-Fi address (`GET /phone` already knows it), Wi-Fi setup when there is no
  Ethernet, and the certificate for those who want `https://`, with the steps to trust it on a phone.
- **The assistant's key.** Moves here from the Routines sheet; Routines keeps a one-line hint pointing at it.
- **The engine's login.** The brain created it; the brain can rotate it. *Reset* here replaces "open Home Assistant".
- **For the curious.** The Advanced door becomes one line at the bottom of this sheet and nowhere else: the engine's
  address and the login the brain made, for someone who wants the raw system. It is never a step.

## What landed

**Signing in again, 10 September 2026.** The first step of the order below, and the shape the Accounts sheet grows into.

- A flow's *source* says who started it. `onboarding.py` reads HA's one list of open flows twice: `discovered()` for
  what the network offered, `sign_ins()` for what is waiting for a person. Neither screen ever sees the other's.
- `provision.py` keeps the waiting ones beside its other complaints, refreshed on the same half-minute tick. A dead
  token usually makes HA complain about the account *and* open a flow; the flow is the one worth offering, so it
  stands in for the complaint rather than the house saying the same thing twice.
- `health.py` turns each into a *Needs a look* **job**, not a sentence: `acts` is the list of things that can be
  done about it -- the flow for a sign-in, the entry or the part for something that could not start, and for a thing
  that has gone quiet either asking it again or being rid of it. The words on the buttons come from the brain, as
  every other sentence there does, down to the question a removal asks first.
- A fault is said once. A device carries the entry that brought it (`model.Device.entry`) and `provision.domains`
  says what each entry is, so a radio that stopped gathers everything that went quiet with it into its own `with`
  rather than letting them stand as lines of their own. One dead radio was reading as seven separate mysteries with
  the cause last; it is one row now, with the six named under it, and putting the radio right clears all of them.
- Home's list draws those buttons. *Sign in again* hands the flow to the sheet that already draws every other one,
  which then reads as being about that one job: no *Found nearby*, no *Behind the scenes*, no Advanced link. Walking
  away leaves the flow open, so the line on Home still offers it.
- Preview it with `?sheet=add&signin=<flow>`; the mock brain has the whole path behind `NEEDSLOOK=1`.

Not covered yet: an account with no flow open (Ring is the one that matters, and it is step four), and removing one.

## Where this stands

*Read from the tree on 12 September 2026, so a session picking this up does not have to work it out again. Update the
date when you change what is below it.*

**Standing on its own feet.** The code (`brain/hub/lock.py`): controlling the house never asks for it, and
`needs_code()` is the one list of what does — adding, renaming, moving, the location, the rules, the flows, the
engine's sign-in. Five wrong codes from an address and that address waits the minute out. No code set means nothing is
locked, which is how a hub starts. Pairing (`brain/hub/phones.py`, `app/src/Join.vue`, `app/src/PeoplePage.vue`) is
whole: the three ways in, a random token per phone with only its hash kept, day/weekend/keep stays that sweep
themselves, `open_to_strangers()` as the list of what a phone may reach before it belongs. The phones moved onto the
People page, next to the people they belong to. Covered by `brain/tests/test_lock.py`, `test_api_lock.py`,
`test_phones.py`, `test_settings.py`.

**A way in is not a key** (15 September 2026). The code was the only thing standing between a phone and the door to
the rest of the house, and the code is one secret the whole house shares — so a phone let in for the afternoon, once
somebody read the code out in a kitchen, could admit anyone, evict anyone, and let a phone out of the house. `how` had
recorded the difference since pairing was built and nothing read it. `holds_keys()` in `phones.py` now does: the screen
that set the house up and the phones whose owner typed the code themselves may hand out keys; a phone whose `how` is
`wall` — admitted by somebody at a wall — may not, and holding the code does not change that. It still runs the house,
and it may still take itself out of it: leaving is not evicting. `kind` is deliberately not consulted, being a guess
from the user agent. The same rule narrows what a phone may see: `list()` answers a keyless phone with its own row and
no asks, so the household, how each phone got in, when each was last seen, and who is knocking right now stay with the
screens that keep the house. That is also what keeps the join pane off a guest's screen — it rises on `asks`, and
theirs is empty. One consequence worth knowing: the live `phones` message is now a nudge carrying nothing, because one
message goes to every panel at once and the answer differs per phone, so each panel asks `/phones` for its own.

**What the order above still has not touched**, checked rather than assumed:

- **Removing things** (step 2) landed on 12 September 2026, both halves: a device is forgotten from the row it
  sits on when a room is being edited, and an account is removed from the new *Accounts* door on *This house*.
  Selling a camera no longer means opening Home Assistant.
- **People** (step 3) is a page, not yet a model. `PeoplePage.vue` draws what `presence.py` reads, and
  `presence.py` still reads Home Assistant's `person.*` entities and the alarm — so "is anyone home?" still rests on
  the companion app this product says does not exist. A phone has a name, not an owner: nothing mints a per-person
  key. **Roles still do not exist anywhere in the tree** — *can change things* and *can control* are in this document
  and nowhere else. The one distinction that is now real is not a role and does not want to become one by accident:
  `holds_keys()` asks how a phone got in, not who is holding it, so it separates the screens that keep the house from
  the phones let into it and says nothing about people. A guest let in at the wall is the closest thing to *can
  control* that exists, and it arrived as a security fix rather than as the model. Wi-Fi presence is not written; `last_seen` on a phone is touched by that phone making a request, not
  by the hub watching the network.
- **The engine's login** (step 5) is still Home Assistant's to reset: `app/src/Setup.vue` line 131 says so out loud.
- **A device's own settings and Forget** (step 6) are not drawn on the long-press.
- **The Advanced door** (step 7) is still four doors: `AddPage.vue`, `CodePage.vue`, `HousePanel.vue`, `HubPage.vue`
  each mount `AdvancedLink.vue`.
- **`remote` on a phone** is recorded, defaults off, and nothing reads it. It is a promise waiting on the relay;
  see `docs/away.md` piece 2, which now carries the build for it. Turning it on is a key, and not one a phone may turn
  on itself: talking your own way out of the house is the one promotion that has to come from somebody at the wall.

## Order

By how soon a non-technical person is stuck, and by what each unlocks.

1. ~~**Sign in again from the panel.**~~ Done; see *What landed* above.
2. ~~**Remove an account or device.**~~ **Done, 12 September 2026.** **An account can be removed:** `GET
   /accounts` is the list that had to exist first — a Remove button with no list under it is not a page — and
   `DELETE /accounts/{entry_id}` hands the entry to the engine, which takes every device and entity that came in
   under it out of its registries; the house rebuilds off the registry as it does after any other change, so the
   rooms lose those tiles without anything here hunting them down. Behind the code. `AccountTests` in
   `tests/test_api_house.py`, and `AccountsPage.vue` behind a new door on *This house*.

   **What counts as an account** is answered rather than listed: an entry that brought devices in, or has a
   sign-in waiting, or is complaining. That keeps the weather and the clock off a page about accounts with no
   list of names to maintain, and keeps the driver layer's own plumbing off it too — the brain added MQTT,
   Z-Wave and Matter itself and nobody signed into them. Three states and no more: *Signed in*, *Needs signing
   in*, *Not answering*. A row waiting on a person carries the flow that finishes it, handed to the Add page
   that already draws every other one.

   **A device can be forgotten:** `DELETE
   /devices/{id}` takes a thing off whatever brought it (`config/device_registry/remove_config_entry_from_device`
   for each entry behind it) or out of the entity registry when there is no hardware, and the rebuild every other
   change goes through carries it out of the model. It sits at the end of the row it belongs to when a room is
   being edited, next to rename and move, and asks once across the row in words that name what disappears. Behind
   the code, like every change. `ForgettingTests` in `tests/test_api_house.py`.

   One thing is deliberately left. **An integration is allowed to refuse** to let a device go on its own, and
   Home Assistant offers no way to ask in advance, so the house tries and then says *it goes when the account
   that brought it does* — which is now a thing a person can actually act on, because the account is a row on a
   page with a Remove beside it.

   Not offered on *New devices*: a thing forgotten there is only discovered again.
3. **People and presence.** The phone key, the People sheet, Wi-Fi presence with a grace period, presence reading the
   brain's own people. This is the largest item and the one everything else about "who" hangs on.
4. **Ring's sign-in inside the panel.** After the Ring decision below.
5. **The engine's login owned end to end.** Reset from *This hub*; the setup screen's "open Home Assistant" line goes.
6. **Device settings and Forget** on the long-press.
7. **Retire the Advanced links** one by one as each sheet covers its reason to exist. The door shrinks to the one line
   on *This hub*.

Each step is a panel sheet plus a brain route, and each is small enough to land on its own.

## Rules that do not change

- **Controlling the house never needs a code; changing it does.** People and roles refine that, they do not replace it.
- **Nothing on the panel names Home Assistant, an entity, or YAML.** The Accounts sheet says *Google*, not *nest*.
- **A setting lives next to the thing it changes.** The four nouns hold only what has no other home.
- **Works with the internet down.** Presence and who-is-holding-the-phone are local facts; a sign-in that needs the
  internet says so and waits.
- **Home Assistant is touched only through its APIs.** Its UI is for the curious, never a step in any task.

## Open decisions

- **Ring: ring-mqtt or Home Assistant's own integration?** The second makes Ring an ordinary account with a standard
  flow and removes a container and a UI. Check first what ring-mqtt gives (live view, event timing, the doorbell's
  chime) that the native integration does not.
- **Presence: is Wi-Fi presence good enough on its own?** Decide after a week of the hub logging phones coming and
  going next to what the alarm says.
- **Does a person ever sign in on the wall panel?** Recommended no: the wall is the house's, and the code is enough.
- **What does a guest get?** A *Can control* phone that expires, or a code they type once on the wall? Recommended the
  phone; the wall never asks who you are.
