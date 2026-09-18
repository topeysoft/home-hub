# Matter: the house, shared

*Written 17 September 2026, from "will the hub work with Google Home, Apple HomeKit and Alexa — specifically their
voice assistants". Today it does not, in that direction: the hub is a client of those ecosystems and is invisible to
them. This is the plan to turn the house around and let it be spoken to by Siri, the Assistant and Alexa without
giving any of them the house.*

## Where we start, and which direction is missing

Two directions, and only one of them is built.

**Inbound works.** `cast` drives the Home Minis and the bedroom TV; `sounds.py` hands them a URL on the hub's own LAN
address, so rain plays with the internet down. Nest arrives through `onboarding.py`'s hand-written Google key guide.
HomeKit accessories can be taken over with `homekit_controller`, and `matter-server` is already in the compose file
commissioning Matter devices into the house.

**Outbound is not built at all.** `configuration.yaml` is eight lines of `default_config` — no `homekit:` bridge, no
`alexa:`, no `google_assistant:`, and `cloud` sits in `onboarding.py`'s `HIDE` set so the panel never offers Nabu
Casa. A Home Mini in the kitchen cannot turn on a kitchen light. Siri cannot see a scene.

**And the driver layer will not fix this for us.** Home Assistant's own Matter page says it outright: *"Home Assistant,
as a Matter controller, only supports control of Matter devices. Home Assistant is not a bridge itself and it cannot
turn existing devices within Home Assistant into Matter compatible devices."* The container already running is the
opposite end of the wire from the one this plan needs.

## Why Matter and not three integrations

HomeKit would have been cheapest — HA ships a HAP bridge, it is local, it needs no account — and it buys Apple only.
Alexa and Google each want a public HTTPS endpoint and OAuth account-linking, which means the maker running a service
that is in the path of somebody's light switch. `docs/away.md` spent a whole document refusing exactly that shape.

Matter buys all three from one bridge, on the LAN, with no account anywhere and no maker in the path. One thing to
build, three ecosystems, and **up to five fabrics at once** on most implementations — so Apple, Google and Alexa can
hold the same house simultaneously, each one added by opening a commissioning window from the panel.

It is also the direction the spec is going: Matter 1.6 (17 June 2026) added no new device categories and spent itself
on setup, multi-ecosystem management and status reporting. The interop problem is the one being worked on.

## Rules that do not change

- **The house works with every ecosystem removed.** The bridge is a way in for somebody else's app, never a
  dependency. Unplug the Echo and nothing in this house notices.
- **Nothing is shared until somebody shares it.** The bridge starts empty. A house that never opens the screen is a
  house with no bridge running at all.
- **The commissioning window is closed.** A Matter device with an open window and a printed code will join any
  commissioner that has the code. So the window opens from the panel, for a few minutes, and shuts itself — the same
  promise `docs/away.md` makes about a phone: being on the Wi-Fi gets you nothing on its own.
- **The gate leaves the house with the device.** `docs/voice.md` gates by route, not by kind: anything woken by a
  wake word may do everything except open a way into the house. A shared lock is a wake word on a HomePod in a hall,
  and this house cannot gate what Siri does. See *The two that must be decided*.
- **The panel is still the only UI.** No second web interface to configure the bridge, for the reason
  `docs/settings.md` and the product direction both give.

## The shape: one Node container, fed by the brain

Matter's device side has one mature implementation to build on — **matter.js**, TypeScript on Node. `python-matter-server`,
which the hub already runs, is a controller only. So this is a new container, `matter-bridge`, and it is the first
Node process this hub runs at runtime. That is a real cost and it is the price of the direction.

**It reads the brain, not Home Assistant.** This is the decision the rest of the design hangs off, and the repo has
already argued it twice. `GET /home` for the house, `WS /stream` for changes, `POST /devices/{id}/{action}` to act.
Three things follow, and each is the reason:

- **The house's own names and rooms travel.** Apple Home gets *Kitchen counter*, not `light.shelly_1_relay_0`.
- **`kind_of` travels, which is the whole of `docs/kinds.md`.** A lamp on a plug that the owner re-typed as a light
  arrives in Apple Home as a light. Bridging HA's entity list would ship the driver's opinion and lose the owner's —
  and the plug-and-a-lamp case is exactly the one this feature exists for.
- **The trap stays shut.** `act()` still picks the Home Assistant service by `capability`, in the brain, where it
  already does. The bridge never calls HA and so cannot re-open the hole `docs/kinds.md` names.

**One thing the bridge needs that does not exist: a way in past the phone gate.** `settings_lock` 401s anything with
no phone cookie once a code is set, and the bridge is not a phone. It gets a service token in `settings.json` and
sends it as a header; `open_to_strangers` is not touched, because widening that list for a local process is how the
front door gets widened for everything else.

## What can be shared, and what cannot

Each shared device is a bridged endpoint under one Aggregator, carrying Bridged Device Basic Information with the
house's name for it and a stable UniqueID.

| The house's kind | Matter device type | Notes |
|---|---|---|
| `light` | On/Off, Dimmable, Color Temperature or Extended Color Light | picked from `supported_color_modes`, which `_keep_attrs` already keeps |
| `switch`, `appliance` | On/Off Plug-in Unit | the kind matters to the hub, not to Apple Home |
| `fan` | Fan | `percentage` is already kept |
| `cover` | Window Covering | `current_position` is already kept |
| `climate` | Thermostat | the richest mapping and the one most likely to disagree; Matter 1.6 spent effort on thermostat behavior |
| `motion` | Occupancy Sensor | |
| `contact` | Contact Sensor | |
| `sensor.temperature` / `.humidity` / `.illuminance` | Temperature / Humidity / Light Sensor | |
| `vacuum` | Robotic Vacuum Cleaner | controller support is patchy; last in |
| `lock` | Door Lock | **gated — see below** |
| `alarm` | — | **not shared. See below** |
| `media` | — | Matter has no speaker or media player device type. The Home Minis stay inbound-only |
| `camera` | — | cameras arrived in Matter 1.5 and were refined in 1.5.1, but no ecosystem controller usefully takes a *bridged* camera today. Out of scope, revisit in a year |
| scenes | — | no device type. If they are ever shared it is as on/off switches, and that is its own decision |

**Rooms do not travel, and we should stop pretending they might.** There is no standard way to push a room assignment
to a commissioner; a Fixed Label with the room name is worth writing and worth not promising, because Apple and Google
have historically ignored it. Somebody assigns rooms once more in the other app. Say so on the screen rather than
letting them find out.

**The endpoint numbers are the classic bridge bug.** A device's endpoint number must be stable for the life of the
bridge and must never be reused — shift them and Apple Home shows ghosts and duplicates. Endpoint assignment is
persisted beside the fabric credentials, and both ride `backup.py`, because losing that storage means every ecosystem
re-commissions from scratch.

## The two that are decided, and what they cost

*Settled 17 September 2026, before any code, because they change what the bridge is allowed to publish and what the
screen has to say.*

**A lock is shared only where somebody has said so, out loud, once.** `model.py`'s `GATED = ("lock", "cover")` exists
so a kind override cannot walk around the voice gate, and `docs/voice.md` states the principle: *the direction matters
more than the device* — closing and locking are free because the failure mode of a misheard "close the garage" is a
closed garage; opening and unlocking are the dangerous half. Sharing a lock hands the dangerous half to an assistant
this house does not control, standing in a hall, within earshot of a letterbox.

So: **locks and garage covers are never in the bridge by default, and the switch that puts them there is their own,
with the risk in the sentence beside it** — *anything that can ask Siri, the Assistant or Alexa can then unlock this
door.* It is not a refusal. It is the household's decision, made once, in words, in the place where it is made.

Two consequences, and the second is the one that matters. The rule lives in the brain, in `share.py`, not in the
bridge — the bridge publishes the list it is handed, so the gate is where the tests are. And **the gate cannot be a
direction**: Matter's Door Lock is one device with a lock and an unlock, and there is no way to publish half of it.
That is exactly why this is a switch and not a default. Where `docs/voice.md` could give the closing half away free,
this cannot, and pretending otherwise would be the more dangerous design.

**An alarm is never shared, and there is no switch.** `docs/kinds.md` gave the siren a second tap because the failure
mode of a stray finger is a noise the whole house hears at 2am, gave it no scene, and gave it no timer. A voice
assistant has no second tap, and Matter has no way to ask for one: an On/Off endpoint is one word away from sounding,
from any room, from any guest, and from a television that said the wrong thing. Silencing is the half worth having
and it cannot be had without the other, the same trade that kept alarms out of `intents.py`.

This one is a rule rather than a default, so it is held down by a test and not by a screen: a house may not turn it
on, so `share.py` refuses `alarm` before it reads any setting, and `test_share.py` asserts it with the alarm switched
every way a household could switch it.

**What both have in common, and it is the reason to write them down now.** The hub's own rules are enforced by taps,
words and tables that a commissioner never sees. Everything the bridge publishes leaves that behind and gets whatever
Apple, Google or Amazon decide it means. So the question for every kind added after piece 2 is not *can Matter carry
it* but *what does this house promise about it that a bridged endpoint cannot keep* — and where the answer is
something, it is a switch, a refusal or a sentence, decided before it ships rather than after.

## Where it lives on the panel

*Written before it was built. What it turned out to be, and why the three rows below were wrong, is in **What the
screen turned out to be** further down; this is left as it was so the change is visible rather than tidied away.*

Under *This hub*, the fourth noun, as **Share this house** — three rows, one per ecosystem, each saying *Not shared*
or *Shared · 14 things*. Sharing one shows a QR and the eleven-digit code (`qr.svg` already draws QRs for phone
pairing), says the window is open for five minutes, and closes it. Adding the second ecosystem is the same screen
again; nothing is torn down.

Under it, what is shared: a switch per kind, lights and plugs on, the gated ones off with their sentence. Not a list
of every device — that is the list this panel keeps refusing to draw.

## The order to build it, and what each piece proves

**Piece 0 — settle the two above.** *Done, 17 September 2026.* They changed what piece 3 draws and what piece 1 is
allowed to publish, which is why they came first.

**Piece 1 — one bridge, lights and plugs, Apple Home.** *Built 17 September 2026; see **What was built** below.*
The container, the service token, the aggregator, stable endpoints, state both ways. *Exit test: from the wall,
Share this house → Apple Home; scan; the kitchen lights appear in the Home app under the house's own names; "Hey
Siri, kitchen lights off" turns them off and the panel's tile follows within a second. Pull the hub's uplink and
repeat it.* **That test has not been run: it needs the panel screen (piece 3) and an iPhone in the house.**

**Piece 2 — the rest of the kinds.** *Built 18 September 2026; see **What piece 2 cost** below.* Covers, thermostat,
fan, sensors, locks. *Exit test: a re-typed lamp on a plug appears as a light, and the thermostat's setpoint set from
the Home app is the setpoint the panel shows.* **The second half needs a controller and has not been run.**

**Piece 3 — the panel screen**, the per-kind switches, the lock switch with its sentence, and re-opening the window
for a second ecosystem. *Built 17 September 2026; see **What the screen turned out to be** below.* *Exit test: the same
house held by Apple Home and one more at once, both live.* **Not run: it needs two ecosystems and a phone.**

**Piece 4 — Google, then Alexa, and they are not the same difficulty.** See below.

**Piece 5 — certification, only if the box is sold.** See below.

## What the ecosystems actually do with an uncertified bridge

This is the part that decides the order, and it is measured from other people's bridges rather than ours.

| | What happens today |
|---|---|
| **Apple Home** | Commissions a bridge on the test vendor ID 0xFFF1 and works. This is why Apple is piece 1. |
| **Google Home** | Wants the test VID/PID pair registered in the Google Home Developer Console before it will pair, and needs a real Google hub in the house — the app alone is not a controller. Workable, with a step we have to document and a piece of maker-side setup per product, not per house. |
| **Alexa** | **Currently the one that does not work.** Commissioning of uncertified bridges stops after the attestation request and the failsafe expires — reported against both the Home Assistant Matter Hub fork and Matterbridge. Nothing we write fixes that; it is fixed by certification or by Amazon. |

So the honest order is Apple, Google, Alexa — and Alexa is a line in *Share this house* that says *not yet* until one
of those two things changes. Worth saying now rather than discovering it in piece 4.

## Certification, which is the shipping question

A test vendor ID may not be used in a product that is sold. Production needs a CSA-issued VID, which needs at minimum
**Adopter membership at US $7,000 a year**, plus per-model certification — one worked example puts a single model at
about **$19,500 in certification against $22,500 of membership, near $42,000 all in**. There is a provisional tier
with no annual fee and a certification-transfer route that is cheaper, and both are worth reading properly before
budgeting.

Three things follow. Nothing here blocks building: a hub in this house, and in a friend's, runs on the test VID today.
The *shipping* decision is separate and later. And it is the same decision `docs/shipping.md` is already holding for
the appliance under the product — this is one more line on that page, not a new argument.

## What was built

*17 September 2026. Piece 1, less the screen: everything from the brain out to a bridge announcing itself on the LAN,
proved against a real brain with a real matter.js node. What has not happened is a commissioner scanning it.*

1. **The rules, in the brain.** `hub/share.py`: `REFUSED` (the alarm, before any setting is read), `BY_HAND` (the lock
   and the garage, behind a switch of their own), `UNCARRIED` (the speaker and the camera, which are an absence rather
   than a decision), and `TYPE`, the kinds the bridge can build today. `Share.devices()` returns exactly what is to be
   published, in the house's own names and rooms and by `kind_of` — so a re-typed lamp on a plug leaves the house as a
   light. `brain/tests/test_share.py` holds all of it: 25 tests, and the two decisions are asserted with the household
   switching them every way a household could.

2. **A door that is not a phone's.** The bridge is a container on this host, so it carries a key install.sh writes into
   `driver-layer/.env` and sends it on `x-hub-service`. It opens `/share/bridge/` and **nothing else** — `open_to_strangers`
   was deliberately not widened, because that list is the front door for everything. A test asserts the key does not
   open `/home`, `/accounts` or `/phones`.

3. **The gate again at the moment of acting.** The list is the decision, but a household that switches locks off while
   Apple Home still holds the endpoint must not be obeyed on the strength of a list fetched an hour ago. Every command
   is re-checked, and it runs through `hub.act()` — so the driver's service is still chosen by `capability` and
   `docs/kinds.md`'s trap stays shut — logged with source `matter`, so *Recent* can say a voice did it.

4. **The bridge.** `matter-bridge/`, TypeScript on matter.js 0.17.9, the first Node process this hub runs at runtime.
   An Aggregator with one bridged endpoint per thing: Dimmable Light, On/Off Light or On/Off Plug-in Unit, each built in
   a typed branch so a `currentLevel` can never be pushed at a plug. It reconciles against a fresh list on every nudge
   from the panel's own stream, with a sixty-second backstop under it.

5. **Three things it is careful about**, each of which is a way bridges go wrong: the endpoint number (made from the
   device id, so renaming a lamp does not hand Apple Home a second lamp), the echo (a change that agrees with what we
   last pushed is our own state coming back, not a command — told apart by value, which is the only way with no race in
   it), and silence (an empty list is no bridge at all, so a house that never opened the screen announces nothing).

**Proved by running it**, against a brain holding the test house: four endpoints published under the house's own names
and rooms, the node online and announcing `_matterc._udp` with a manual pairing code and a QR, those codes back at the
brain where the panel will draw them, and — switching plugs off in the panel — the Kettle's endpoint gone from the
bridge within three seconds.

**Two things running it turned up, and neither was visible from reading.** Our `MATTER_STORAGE` collided with
matter.js's own `MATTER_*` configuration namespace and stopped the node starting; our variables are `HUB_*` now.
And the node started with three spec warnings it does not refuse on — a serial number equal to the unique id, a
product label repeating the vendor name, and development values for the hardware and software versions. All three are
fixed, and they are the kind of warning that otherwise survives quietly to a certification lab.

## The gap piece 1 turned up, and it is a decision like piece 0's

**The alarm refusal only bites once somebody has told the house what the thing is.** It reads `kind_of`, which is the
owner's word or the driver's — and `guessed_kind()` in `model.py` guesses appliances and nothing else. A siren that
nobody has re-typed is a `switch`.

This is not hypothetical. The house this was built in has `switch.holts_summit_alarm_siren` — a Ring siren, named
*Holts Summit Alarm Siren* — sitting at `kind: switch`. The first time that house shares its plugs, its siren goes to
Apple Home as a plug, and `docs/kinds.md`'s whole argument about the 2am stray finger arrives in an app that has no
second tap. The rule is right; it is simply downstream of a fact nobody has entered.

Three ways out, in the order of how far each reaches:

| | What it costs |
|---|---|
| **A guess in `model.py`**, beside the appliance one: a switch whose words look like a siren is shown as an alarm | The most reach and the most honest — it also gives the thing its second tap on the panel, which is where the rule came from. It is a change to what every house sees, so it is a decision rather than a fix |
| **A guess only in `share.py`**: not published, still a plug on the panel | Safe direction, cheap, and wrong in the way `kind_of` exists to prevent — the house would hold two opinions about one thing |
| **Nothing automatic**: the screen lists what is about to leave, by name, before the first share | Good regardless, and piece 3 should do it anyway. On its own it puts the whole weight on somebody reading a list |

The recommendation is the first and the third together. It is not built, because piece 0's lesson was that this class
of question is settled before code and not during it.

## What the screen turned out to be, and where it left the plan

*17 September 2026. `app/src/SharePanel.vue`, under *This hub*, with `app/e2e/share.spec.ts` holding it.*

**The plan said three rows, one per ecosystem. That was wrong, and building it is what showed why.** Three fixed rows
means knowing which ecosystem is which, and a bridge does not know that until somebody has already commissioned it —
what comes back is a fabric carrying a vendor id. Two of the three rows would have read *Not shared* forever on a house
that uses one app, which is three rows of furniture to say one thing.

So the screen is one switch and what follows from it:

| | |
|---|---|
| **Share** | Off, and saying so: *Off. Nothing about this house leaves it.* On, it counts what is going out and names who holds it |
| **Apps** | Who holds the house, by name, and *Add an app* — which opens the door for five minutes |
| **Scan this** | Only while the door is open: the QR, the printed number under it, and what happens when the time runs out |
| **What is shared** | A chip per kind, which is what somebody actually decides about. Not a hundred rows of lamps |
| **Locks and garage doors** | Its own switch, off, with the sentence that is the whole of the decision |

**Who holds it is named from the CSA's own ledger, not guessed.** `HOLDERS` in `share.py` maps vendor ids to the names
a person would use, read off `on.dcl.csa-iot.org` rather than from memory: Apple Home is 4937, Google is 24582, Amazon
has several. Anything unknown falls back to the label that app set for itself, and then to a plain noun. A wrong name
here would tell somebody the wrong app is in their house, so the rule is **never invent one**, and four tests hold it.

**The door is a request, not a second socket.** The panel asks, the brain writes down when it was asked, and the bridge
— which already fetches its list on every nudge — opens the window on the next pass. Nothing new listens on the hub for
somebody to find, and the one direction that existed is the one that carries it.

**Three things running it turned up.** The panel's dev proxy would have served `index.html` for `/share`, which a test
already in the repo caught the moment the route existed. The mock brain's share state is the first mutable thing in it,
so those e2e tests had to be made serial and to reset it — they passed before that by luck, which is the kind of green
that goes red the day somebody adds a sixth test. And the *Apps* row said **Open** beside a door that was open with no
countdown to show, which is the word said twice; it now says nothing and lets the row beneath it speak.

**One thing deliberately not built.** There is no *stop sharing with Apple Home* on this screen. A fabric is removed
from the app that holds it, and a screen offering to do it from here would be offering something Matter does not make
reliable. The switch that turns the whole thing off is honest and is enough.

## The screen again, and the badge on it

*18 September 2026, from "even when toggled on, it doesn't indicate that this is about making the house's devices
available as Matter devices — it's a good selling point, why should we be shy about showcasing it?" The boards are
`design/share/`, and the argument for each is in its `canvas.json`.*

**The note was right, and the fault was in what the page was shaped to do.** Everything it said was true — *Off.
Nothing about this house leaves it* — and all of it was written as reassurance about a risk. The word Matter never
appeared. Nothing said the lights BECOME something over there. A household that already owns a HomePod could not tell
from that page that it had just become useful.

**Three directions were drawn and the mechanism won.** A kept it as rows with the words fixed; B put a badge and four
ecosystem cards at the top; C draws what actually happens — three of the house's own things on the left, one Matter
badge in the middle, the three apps on the right. C is the only one that explains what the feature IS rather than what
it works with, and "your devices become Matter devices" stays an abstraction until somebody sees their own kettle in it.

**So the map is drawn from the house, not from a stock illustration.** `Share.state()` carries `candidates` and a
`preview` of the first few by name, and both go through the same gates the bridge's own list does — `test_share.py`
asserts that a re-typed siren is absent from the picture for the same reason it is absent from the list. What a
household sees on its way out is what would actually go out.

**It has its own door.** *Share this house*, in This house, with the hint *Apple Home, Google Home, Alexa* while it is
off. That hint is the advertisement: nobody opens a door called Share this house unless it says what it works with, and
the one thing a person wants to know is whether it works with the thing they already own.

### The badge is ours, and that is not a detail

The badge asked for is **drawn rather than borrowed**. The Alliance's guidelines say their brands *"may only be used on
Products … that have been Certified with the Alliance"*, and this bridge runs on test vendor id `0xfff1`. Wearing the
Matter mark now would breach that, and would tell a household this hub is certified when it is not — which is the one
lie a page about trust cannot afford.

So the badge is a hub with three things on it, in the panel's own gold, with the word **Matter** beneath. It reads as a
Matter badge, it is ours, and it lives in one block of `SharePage.vue`: the day certification is earned, the certified
mark replaces it there and nowhere else. An e2e test asserts the page never says *certified*.

**Naming the standard in words is a different thing and is fine.** *Works with Matter*, *becomes a Matter device*, and
the three app names are ordinary nominative use, and this page leans on all of them — which is most of what the note
was asking for.

## Leaving one thing out

*18 September 2026, from "can I share a subset of my lights, and is that advisable?" — asked with thirty-two of this
house's lights sitting in Apple Home.*

**Yes, and it turns out to be the missing half of the feature rather than a refinement.** The reason is on the other
side: a bridge cannot be curated from inside Apple Home. Bridged accessories generally cannot be removed or hidden one
at a time there, and Apple's own guidance is to *remove it through the manufacturer's app*. **We are the manufacturer's
app.** So if this hub does not offer it, nobody can: a household's only lever is all its lights or none.

**But not as a list, and that is the whole of the design.** The Share page still refuses to draw a row per lamp —
thirty-two of them is precisely what the kind switches exist to avoid. This follows `docs/kinds.md` instead: like
*Show this as*, it is a decision made **on the device's own page**, standing in front of the thing.

- `Kept out of other apps` — *Shared* / *Kept home* — on the pane, under the name, and **only where the house is
  already sharing that kind**. A switch that cannot mean anything is worse than no switch, so `Share.shareable()`
  decides whether it is drawn at all and the route refuses what the screen would not have offered.
- Stored as the **exception**, never as the rule: `left_out` is a list of ids, so a household that switches lights off
  and on again has not changed its mind about the one lamp it meant to keep home. A test holds that.
- **Opt-out, not opt-in.** Opt-in would make the kind switches mean nothing and put a walk through thirty-two lamps
  between a household and anything working at all.
- The Share page **counts** them — *1 kept home* — and never names them. The count ignores exceptions whose kind is
  not shared anyway, because a lamp left out of something nobody shares is not being held back in any sense a person
  would recognize.
- It is a change to the house, so it needs the code, the way renaming and moving from the same pane already do.

**And it turned up a hole in the acting gate.** The route that runs a command from somebody else's assistant checked
the kind and the lock switch, and would have obeyed a command for a lamp the owner had just kept home — because Apple
Home still holds that endpoint until the bridge next reconciles. There is now one predicate, `Share.may_act()`, that
knows every way a thing can be kept home, and the route asks it and nothing else. The test that found it is
`test_a_thing_left_out_is_refused_at_the_moment_of_acting_too`.

**What this does not solve.** Removing a thing an ecosystem already holds closes its endpoint, and it disappears over
there — any automation built on it in Apple Home breaks. Putting it back restores the same endpoint number, because
the ids are made from the device id and never reused, but whether Apple reattaches it to the old automation is Apple's
business and not ours. Worth a sentence on the screen if anybody is bitten by it.

## What piece 2 cost, and what running it found

*18 September 2026. Eleven kinds now: lights, plugs, appliance features, fans, blinds, thermostats, locks, motion,
door and window sensors, temperature and humidity.*

**The house keeps speaking its own language all the way to the bridge.** `_state_for()` in `share.py` hands over
degrees in whatever the house speaks, a cover position counted from open the way Home Assistant counts it, and a
contact that is `open` when the door is open. Every conversion into Matter's units lives in `matter-bridge/src/units.ts`,
next to the cluster it belongs to — because **three of them are inversions**, and an inversion two files from its
cluster is one that ships:

| | the house | Matter |
|---|---|---|
| a cover | 100 is fully **open** | `LiftPercent100ths` 0 is fully open, 10000 fully closed |
| a contact | on means **open** | `stateValue` **true** means *closed* |
| a lock's modes | — | in `supportedOperatingModes` a bit that is **set** means *not supported*, and the spec warns about it itself |

`units.test.ts` pins all three, round-trips the temperatures, and asserts a light's level never reaches zero. Twelve
tests, run with `npm test`.

**A blind is not a garage door, and the screen already said so.** `model.GATED` gates the whole `cover` kind against a
re-TYPING and is right to — nobody should be able to call a garage door a plug. On the way out of the house the
question is different, and the screen reads *Locks and garage doors*, not *locks and blinds*. So `WAYS_IN` splits them
by the cover's own device class: garage, door and gate need the switch; blinds, curtains and shades go out with the
ordinary kinds. **A cover whose class the house cannot read is treated as a way in**, because the one being guessed
about is the garage. `model.py` now keeps `device_class` on a cover, which is the whole of what that costs.

**And the lock switch is no longer a promise nothing keeps.** Piece 3 shipped a switch for something piece 2 had not
built; `carried("lock")` is true now, and a test says so.

### Five things only running it could find

Each of these typechecks perfectly and fails at startup, and each was found by pointing the bridge at a house with one
of everything in it:

- A **thermostat** must declare `controlSequenceOfOperation`, and it has to agree with its features — claiming Cooling
  on a heat-only system puts a cooling dial in Apple Home for something that cannot cool. It is built from the house's
  own `hvac_modes` now, in three shapes.
- A **fan** must declare `fanModeSequence`. Off/Low/Medium/High is the one every controller understands.
- An **occupancy sensor** must declare its detector type twice over — as an attribute *and*, since cluster revision 5,
  as a feature.
- A **lock** needs `wrongCodeEntryLimit` and `userCodeTemporaryDisableTime`, both belonging to PIN codes it does not
  have, both validated against a 1..255 range whose default is 0.
- ...and the `alwaysSet` bit-range on that inverted bitmap, without which the lock refuses to build at all.

**One bug of our own turned up with them.** A device that would not build was retried on every nudge and every
heartbeat, and each attempt allocated a Matter endpoint number it then threw away — so one thing the bridge could not
carry would slowly eat the numbering the rest of the house depends on. A device that fails to build is now named in
the log once and left out until the bridge restarts.

### Still not carried, and why

Illuminance (its Matter measurement is on a log scale and no controller does anything useful with a bridged one),
vacuums (support is patchy enough that it would be a row nobody can use), and the three from the start: speakers and
cameras have nowhere in Matter to go, and an alarm is refused.

**Fixed Labels are not built.** The plan had rooms riding along as labels; both Apple and Google ignore them, and
writing something neither reads in the hope that one day one might is the kind of thing that gets believed later. The
room is in the endpoint's `productLabel`, where a person can at least read it.

## The siren, settled — and how the bridge ships

*18 September 2026. Two questions that had been left open since piece 1, answered together because both are about a
thing being what it says it is.*

### The house guesses a siren now, and the bug was never really about sharing

The refusal reads `kind_of`, so `alarm` only bit once somebody had re-typed their siren by hand. **The live cost of
that was on the wall, not in Apple Home**: `twice.ts` arms a second tap by kind, so a siren sitting at `switch` — which
is every siren nobody has re-typed — had a tile that sounded it on **one tap**. That is exactly the 2am stray finger
`docs/kinds.md` added the second tap for, and it had been missing this device the whole time.

So `guessed_kind()` gains a second guess beside the appliance one: a `switch` that Home Assistant has not called an
outlet, whose words name something loud, is **shown as an alarm everywhere** — the tile's second tap, its own word in
the grammar, no scene, no timer, and refused by the bridge without anybody touching a setting.

Three things were weighed into the shape of it:

- **The loud guess is asked before the machine one.** A *refrigerator door alarm* is an alarm before it is a fridge's
  feature; read the other way round it would land in the group that is quietly left out of Everything off rather than
  the group that asks before it sounds.
- **`SIREN` is narrower than it could be.** `bell` and `chime` are not in it — a doorbell is not what this rule is for,
  and every word in it has to be one that only ever names something loud.
- **What the driver called an outlet is left alone**, the same escape hatch the appliance guess has, and the owner can
  still overrule the whole thing from the device's own page.

Getting this wrong in the safe direction costs somebody a second tap on a plug. The other direction is a siren at 2am.

### The bridge is named by the release, like the brain

`release-manifest.py` left one service out of its rented-image sweep — the brain, "named by the release, not by the
file". The bridge is now the second, and for a reason rather than for symmetry: **the two have a contract between
them** — the shape of what the bridge is handed per device, and how long a request to open the door stays live — so a
hub must never be able to run a new brain against a bridge it cached a month ago.

What that took: `bridge-image.yml` mirroring the brain's, tagged and cosign-signed the same way; `"bridge"` beside
`"brain"` in the manifest; `release.sh` verifying **both** signatures against the workflow allowed to have built each
(checking only one would leave the other a way in); `HUB_BRIDGE_IMAGE` written into `.env` by `install.sh` the way the
brain's is; and `host/update.sh` recording and putting back **both** images, since rolling one back and leaving the
other is the skew the rollback exists to prevent. `host/tests.sh` still passes, which is the part that matters.

CI gained a `matter-bridge` job — typecheck and `npm test` — and the image build now proves on arm64 too, because a Pi
that cannot pull the image builds it, and a build that only ever worked on amd64 would be found by a household rather
than here.

## Not in this plan

Thread (Matter over Wi-Fi is what the hub has, and `docs/shipping.md` already holds Thread as a decision rather than a
default). Re-sharing devices that arrived over Matter or HomeKit — they are already in the other ecosystem and the
round trip is a way to make a light take two hops to do nothing. Sharing scenes, sharing cameras, sharing speakers.
And any second web interface for configuring any of it.
