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
address `AddPanel.vue` hands a maker's page that asks for it.

## What still needs another interface

Found by reading the brain and the panel, ranked by how soon a household hits it.

1. **Signing in again.** Tokens expire and get revoked; Google and Ring do it within a year. Health already says
   "*Nest needs signing in again*" (`brain/hub/health.py`), but the panel has nowhere to do it: `brain/hub/onboarding.py`
   skips every flow whose source is `reauth` or `reconfigure`, so the only fix is Home Assistant's UI.
2. **Removing anything.** No route deletes an account, a bridge or a device. Selling a camera means opening Home Assistant.
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
  is). Health's "*needs a look*" row for a driver opens straight here.
- **Sign in again.** Stop skipping `reauth` and `reconfigure` flows; draw them through the same form path the Add
  sheet already uses. A re-sign-in is the same conversation as the first, minus the key.
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

- **Forget.** On the tile's long-press, next to rename and move. Removes it from Home Assistant's registry and the
  brain's model; for a radio device, also offers to exclude it from the network so it can be paired elsewhere.
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

## Order

By how soon a non-technical person is stuck, and by what each unlocks.

1. **Sign in again from the panel.** Drop the filter in `onboarding.py`, list open reauth flows, draw them, link from
   *Needs a look*. Smallest change, largest payoff, and it is the shape of the Accounts sheet.
2. **Remove an account or device.** One route, one confirmation, the model cleaned up.
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
