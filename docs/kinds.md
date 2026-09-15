# Kinds: what a thing is, when the house has it wrong

*Written 14 September 2026, from the question "is it possible or advisable to let somebody set a device's kind
by hand if it was assigned the wrong one?" The short answer is yes and yes, and almost all of this file is about
the word ONLY in the sentence that makes it safe. Built the same day; the design below is what shipped, and
**What was built** at the foot says where each part of it lives.*

## The question, and the short answer

**Yes, and the house already does this twice.** `POST /devices/{id}/rename` and `POST /devices/{id}/move` are both
the same shape: the driver says one thing, the owner says another, and the house remembers the owner. A kind is the
third field of the three a person can see and disagree with, and it is the only one they currently cannot touch.

**But a kind is not a label, and that is the whole of the design.** A name is what a thing is called. A room is where
it is. A kind decides what the house will *do* — which controls a pane draws, which words in `commands.py` reach it,
what a scene sweeps up, and, today, which service the brain calls on Home Assistant. Handing that to a text field
would promise abilities the device has not got.

So: a person may say what a thing IS, and may not say what it CAN DO.

## Where the kind comes from now

`brain/hub/model.py`'s `capability_for(domain, device_class, words)`, and it is short enough to quote the whole rule:

- HA's **domain** decides it outright for the nine that matter — `CAP_BY_DOMAIN` maps light, switch, media_player,
  cover, climate, lock, fan, camera, vacuum.
- A `binary_sensor` becomes motion or contact by its **device class**.
- A `sensor` becomes `sensor.<class>` for temperature, humidity and illuminance, unless the words naming it look
  like an appliance — the fridge-thermometer rule.
- Everything else is not a device as far as this house is concerned.

That is a good rule and it is right nearly always. What it cannot know is what a thing is FOR. A smart plug with a
lamp on it is `switch.something`, and HA is not wrong — it is a switch. It is also, in the only sense the person
living there cares about, a light.

## Why this is worth building, and it is not tidiness

Three reasons, in the order they matter.

**The plug-and-a-lamp case is the common one.** A lamp on a smart plug is in a great many houses, and today
"kitchen lights off" does not touch it: `commands.py` matches the word "lights" to the capability `light`, and this
thing is a `switch`. The house is wrong in the one place it is least forgivable — the plain sentence a person said
out loud. Good night misses it. So does Everything off.

**It is exactly the wrongness the panel exists to absorb.** `docs/apps.md` and the product direction both hold that
the panel must never require Home Assistant's own UI. Re-typing a device is, today, something you can only fix by
leaving the panel and editing an entity in HA — which is the one move the whole box is shaped to avoid. A name and
a room can be fixed from the panel. A kind cannot, and it is the one that changes behaviour.

**The failure is silent.** A light that shows as a plug still turns on and off, so nothing looks broken. It simply
never joins in — not in a scene, not in a sentence, not in Everything off. Nobody reports it as a bug; they just
stop expecting the house to include it.

## The rule that makes it safe

> A device may be shown as any kind whose controls it can already serve, and no other.

A switch can be shown as a light, a fan or a plug: the controls those need are on and off, which is all a switch
has. A switch may **not** be shown as a cover, which needs a position, or a climate, which needs a temperature. The
offer is computed from what the entity actually supports, not typed in.

This is not a rule about tidiness either. It is what stops the panel drawing a brightness slider that does nothing.

## The one thing that must not be overridden, and it is a trap

**The override must not be the `capability` field.** `brain/hub/api.py`'s `act()`:

    key = (dev.capability.split(".")[0], action)
    if key not in SERVICE: raise ValueError(f"{dev.capability} cannot {action}")
    domain, service = SERVICE[key]
    await self.ha.call(domain, service, dev.id, **data)

`SERVICE` is keyed by capability, so capability is what picks the Home Assistant service. Write "light" into the
capability of a `switch.porch_lamp` and the brain calls `light.turn_on` on a switch entity, and HA refuses it. The
device would then be worse than mis-typed: it would be untouchable, and the panel would have done it.

**And there is a second place, which is the one that would be found last.** `intents.py`'s `plan()` builds a scene's
service the same way, from the scene's capability rather than the device's:

    if d.capability == cap and (cap, action) in SERVICE:
        domain, service = SERVICE[(cap, action)]

Selecting the device has to read the override — that is the point, so a re-typed lamp joins Good night. Building the
call must not. Both lines are in the same `if`, which is exactly how one of them gets changed and the other does not,
and the failure is silent: the scene runs, the lamp does not move, and nobody is told. Whatever lands here needs a
test with a re-typed device in a scene, not just a re-typed device.

A third guard in `api.py` reads the same way — the timer route at line 1037 asks whether `(capability, "off")` is in
`SERVICE` before putting a thing on a timer. That one is correct as it stands and should stay on capability: a timer
has to know what can really be turned off.

So the shape is two fields, not one:

| | |
|---|---|
| `capability` | what the driver says, unchanged, and what `act()` keeps calling the service by |
| `kind` (new) | what the owner says, where they have said anything. Presentation and grammar read it; the service call never does |

Everything downstream reads `kind or capability`. `act()` alone keeps reading `capability`, and it is worth a
comment in the code saying why, because it looks like an oversight and is the point.

## What has to read it

- **`commands.py`** — the KINDS table matches words to a capability. This is the reason to build the feature at all;
  if the grammar does not read the override, the plug-and-a-lamp case is not fixed and only the picture changes.
- **The panel** — `cap()` in `store.ts` and `paneKind()` in `pane.ts`, which is where a tile, its pane and its verbs
  are chosen. (An earlier draft of this thinking put the override HERE and only here. That is wrong: the grammar runs
  in the brain, so a panel-only override would fix the tile and leave the sentence broken.)
- **Scenes and intents** — `intents.py`, so a re-typed lamp joins Good night with everything else.

## Where it does not apply

**Locks, and covers that are a garage.** `docs/voice.md` gates what voice may do by direction — closing and locking
from anywhere, opening and unlocking only with more than a voice — and a kind override is a way to walk around that
gate by re-typing the thing the gate is about. Nothing may be re-typed INTO a lock or a cover, and nothing that is
one may be re-typed out. The rule costs nobody anything: a lock is a domain HA is never vague about.

**Sensors.** `sensor.*` and the binary sensors are a reading, not a thing to control. The fridge-thermometer rule in
`capability_for` is a different problem — a device the house should not show at all — and if that rule is wrong for
a house, the fix is to show or hide the reading, not to re-type it.

## What it looks like on the screen

Where the name is changed, because that is where somebody already is when they notice: the device's own pane, under
the name. Not a settings page and not a list of every device in the house — a kind is noticed one device at a time,
standing in front of the thing.

The words matter more than usual here, because "capability" and "domain" are not words this panel uses: **Show this
as** — a short list of what it may be, with what it is now selected, and one sentence saying why the list is short
("this plug can be switched on and off, so it can be shown as anything that switches on and off"). A thing whose
list would have one entry offers nothing at all rather than a menu with no choices in it.

## Decisions to make before building

| Question | Proposal |
|---|---|
| One field or two | Two. `capability` is the driver's and keeps picking the HA service; `kind` is the owner's. See the trap above |
| Where the override is stored | With the other per-device overrides, beside rename and move, so a restore brings it back with the rest of the house |
| What may be offered | Computed from the entity, never typed. On/off things may become each other; anything needing a position, a temperature or a volume may not |
| May a lock or a garage be re-typed | No, either way in. It is the one kind a safety rule is written against |
| Does the grammar read it | Yes, and this is the reason to build it. A panel-only override fixes the picture and leaves the sentence broken |
| What happens when the driver changes its mind | The owner's `kind` wins and stays. A device whose capability changes underneath — a plug replaced by a real bulb — keeps the owner's answer until they change it, and *This hub* is where that would be visible if it ever matters |
| Does it need the assistant | No. This is a list computed from one entity's own abilities |
| Does a re-typed thing say so | On its own pane, quietly — "shown as a light" under the name. Not on the tile: a tile is a glance, and the point of the override is that the thing stops looking unusual |

## Not in this plan

Inventing kinds the house does not have, splitting one entity into two devices, joining two into one, and anything
that changes what the driver reports rather than how the house reads it. A device that is genuinely wrong IN Home
Assistant is a Home Assistant problem, and the Advanced door is how you get to it.

## What was built

1. **The second field.** `Device.kind` beside `capability` in `model.py`, with `kind_of(d)` — `kind or capability` —
   as the one way everything else reads it. The offer is `kinds_for(capability)`, computed from a `CONTROLS` table
   of what each kind needs of a device: kinds that want the same controls may stand in for each other and no others,
   which is why the only group with more than one member is light / plug / fan. Stored in `settings.json` under
   `kinds`, so a backup carries it; held on `Home.kinds` so a registry rebuild does not forget it.

2. **The three that keep reading `capability`**, each with a comment saying why it looks like an oversight and is not:
   `act()`, the timer guard beside it, and `intents.plan()`. `plan()` is the one that would have been found last —
   selecting the device reads `kind_of`, building the call reads `capability`, and they used to be the same `if`.
   There is a fourth thing the trap turned up: a scene's *data* is shaped for the kind it was written for, so Movie's
   `brightness_pct: 15` reaches a re-typed plug as a bare on. `act()` drops the extras the same way.

3. **The grammar reads it.** `commands.py` is `kind_of` throughout — the KINDS table, a thing named in full, the room
   verbs, what is on, what the house answers with. That is the whole reason to build it.

4. **The control on the pane.** *Show this as*, quietly under the name in `Opened.vue`: the line says what it is
   shown as where somebody has disagreed with the driver, and opens a row of what it may be with the one sentence
   under it. Nothing is drawn where the offer has fewer than two entries. `GET /devices/{id}/kinds` computes the
   offer; `POST /devices/{id}/kind` sets it, and the driver's own word clears it.

5. **The gate.** `GATED = ("lock", "cover")` in `model.py`, refused both ways in and tested both ways.

Tests: `brain/tests/test_kinds.py` (the offer, the scene plan, where it is stored, the service calls, and the
sentence this is all for) and `app/tests/kinds.test.ts` (what the panel treats a thing as, and what it says).
