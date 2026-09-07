# Phase 4: Intelligence

Design for the part of the plan that says *presence, light level and time drive room states, then
the assistant: onboarding, natural-language authoring, explanations.* Done when a guest uses the
house for a weekend without instructions.

Status, 6 September 2026: milestones 1 to 4 are built. The brain side is `brain/hub/rules.py`,
`brain/rules.json`, holds, presence (`brain/hub/presence.py`, the `presence` trigger and condition, the
`/presence` route and `presence` stream message), the `/rules` and `/rooms/{id}/why` routes and the
`intent` stream message. The panel side is the *set by* line on a room (`app/src/views/RoomView.vue`),
the why sheet (`app/src/WhySheet.vue`) and the routines sheet (`app/src/RoutinesSheet.vue`, on and off
only), with the wording in `app/src/why.ts`. The assistant (milestone 5) authors and explains:
`brain/hub/assistant.py` turns a sentence into a draft under `drafts` (structured output, validated by the
same `validate` the file goes through, one retry with the errors), the routines sheet shows drafts with
Approve and Discard, and the why sheet takes a question answered from the log. Suggesting is built without a model:
once a day the brain looks for the same scene chosen by hand in the same half hour on four of the last
fourteen days and writes a `time` draft with a *noticed* line; a discarded habit is remembered and not
offered again. The key comes from the panel (`/assistant/key`, behind the settings code) or
`ANTHROPIC_API_KEY` on the hub. The home screen's house line says when nobody is home and since when, and Recently
shows people leaving and returning. Entry rooms are chosen on the routines sheet.

## What we have

The brain already sees every state change in the house (`Hub._on_state`), knows which devices are
motion, contact and illuminance sensors (`model.capability_for`), and can move a room into a state
deterministically (`_apply` runs the plan from `scenes.json`). Room state changes only when someone
taps the panel. The event log records taps and device changes with a `source` column that is always
`user`, `device` or `system`.

So the inputs exist and the outputs exist. What is missing is the thing in between that decides.

## Principles carried in

- **Rules are data, evaluated by plain code.** A rule is a row in a JSON file, like a scene. The
  evaluator is a few hundred lines with no model in it. A light never waits on the network.
- **The assistant writes and explains. It never runs anything.** It can propose a rule; a person
  approves it; the evaluator runs it. The assistant has no route that changes a device.
- **A hand on the panel beats a rule.** When someone chooses a state, rules leave that room alone
  for a while.
- **Every automatic change says why.** If the hallway light came on, the log names the rule and
  the trigger, and the panel can show it.
- **Room states, not devices.** A rule's normal outcome is "this room is now *occupied*". It does
  not say "turn on light 3". The scene table already knows what *occupied* means in that room.

## Vocabulary

Two words that the code currently blurs and this phase separates:

- **Intent** is what the room was told to be: `occupied`, `empty`, `asleep`, `away`, `movie`,
  `guests`. Today it is `Room.intent`. It changes by tap or, after this phase, by rule.
- **Signals** are what the house observes: motion in a room, a door opening, how bright it is, the
  time, the sun, who is home. Signals never change intent directly; a rule turns signals into
  intent.

A room grows three fields, all derived, none persisted:

```
intent:      "occupied"            # as today
set_by:      "user" | "rule:<id>"  # who last set it
hold_until:  1788660000.0 | null   # rules keep off until then (set by a tap)
motion_at:   1788659400.0 | null   # last motion from any motion device in the room
```

## Rules as data

`brain/rules.json`, next to `scenes.json`, re-read on change the same way. On a hub both live in the data
volume (`HUB_DATA`, next to `settings.json` and the event log), seeded from the repo copies the first time,
so panel switches, drafts and hold lengths survive an image update. A rule's `room` may also be `entry`:
every room the family comes in through, chosen on the panel (`POST /home/entry`); such a rule runs once
per entry room and does nothing while none are chosen.

```json
{
  "_comment": "Each rule: when <trigger> [if <conditions>] then <outcome>. Order matters within a room.",
  "rules": [
    {
      "id": "hall-evening",
      "name": "Hallway lights on when someone walks through after dark",
      "room": "hallway",
      "when": {"motion": "on"},
      "if": [["sun", "below", 0], ["intent", "not", "asleep"]],
      "then": {"intent": "occupied"},
      "enabled": true,
      "by": "user"
    },
    {
      "id": "hall-idle",
      "name": "Hallway off after ten minutes of nothing",
      "room": "hallway",
      "when": {"idle": 600},
      "then": {"intent": "empty"},
      "enabled": true,
      "by": "user"
    },
    {
      "id": "everyone-out",
      "name": "Everything off when the last person leaves",
      "room": "home",
      "when": {"presence": "nobody", "for": 300},
      "then": {"intent": "away"},
      "enabled": true,
      "by": "user"
    }
  ]
}
```

### Triggers (`when`, exactly one)

| Trigger | Fires when | Needs |
|---|---|---|
| `{"motion": "on"}` | any motion device in the room turns on | a motion sensor in the room |
| `{"contact": "open"}` / `"closed"` | any contact device in the room changes to that | a door or window sensor |
| `{"device": "<id>", "state": "<s>"}` | one named device reaches a state | escape hatch, discouraged |
| `{"idle": 600}` | the room has had no motion for that many seconds | a motion sensor; counts from `motion_at` |
| `{"time": "22:30"}` | the wall clock reaches that time, once a day | the home's timezone |
| `{"sun": "set", "offset": -1800}` / `"rise"` | sunset or sunrise, with an offset in seconds | the home's location |
| `{"presence": "nobody"}` / `"somebody"`, with `"for"` | everyone is away (or someone is back) and has been for that long | person entities from HA |
| `{"intent": "<state>"}` | another room, or the home, was set to that state | nothing |

Triggers with `for` or `idle` are timers. The evaluator arms them when the condition starts and
fires them if it still holds when the time is up.

### Conditions (`if`, all must hold)

Triples of `[subject, operator, value]`. Subjects: `sun` (elevation in degrees), `time` (window,
`["time", "between", ["22:00", "06:00"]]`), `weekday`, `intent` (this room's), `home` (the home's
intent), `presence` (`somebody` / `nobody`), `light` (the room's illuminance in lux, if it has a
sensor), `device` (`["device", "media_player.x", "playing"]`). Operators: `is`, `not`, `below`,
`above`, `between`, `in`.

### Outcome (`then`, exactly one)

- `{"intent": "<state>"}`: set this room's intent. The normal case. `room: "home"` sets every room.
- `{"device": "<id>", "action": "<a>", "data": {}}`: one capability action. The escape hatch for
  things scenes cannot say, like "open the garage". Goes through the same `SERVICE` table as the
  panel, so it can only do what the panel can do.
- `{"notify": "<text>"}`: a message on the panel and, later, a push. No device changes.

### Ordering and conflicts

Rules are evaluated in file order. Within one evaluation, the first rule that sets a room's intent
wins for that room; later ones that would set the same room are skipped and logged as *shadowed*.
This keeps the file readable as a priority list and avoids inventing a priority field.

## The evaluator

New module `brain/hub/rules.py`, one class, owned by the `Hub`.

```
class Engine:
    def on_state(self, dev, old, new)   # called from Hub._on_state after the model is updated
    def on_intent(self, room, state, source)  # called from _apply, so intent-triggered rules see taps and rules alike
    async def tick(self)                # every second: time, sun, idle and "for" timers
    async def fire(self, rule, room, trigger, why)  # conditions → hold check → _apply → log
```

**On a state change.** If the device is motion and turned on, stamp `room.motion_at`, then run the
motion rules for that room. Contact and device rules the same way. Motion sensors flap, so a second
`on` within a few seconds re-stamps `motion_at` without re-firing.

**On the tick.** Compute the sun's elevation from the location (port of `app/src/sun.ts`, about
twenty lines; no dependency on HA's `sun.sun`, which needs the location HA may not have). Check
time and sun rules against the last tick so each fires once. For every room with an `idle` rule and
a `motion_at`, fire when `now - motion_at` crosses the threshold. Presence `for` timers the same.

**Firing.** Evaluate the conditions. If any fails, do nothing, but record the failing one in the
log's detail when debug logging is on. If the room is held (`hold_until > now`) and the rule would
change its intent, log `held` and stop. Otherwise call the existing `_apply`, set `set_by` to the
rule's id, and log:

```
kind=intent  subject=<room>  old=<previous intent>  new=<state>  source=rule
detail={"rule": "hall-evening", "trigger": {"motion": "on", "device": "binary_sensor.hall_motion"},
        "checked": [["sun", "below", 0, -12.4, true], ["intent", "not", "asleep", "empty", true]]}
```

That detail is the whole "why". The assistant's explanation is a sentence made from it.

**Loops.** A rule fired by an `intent` trigger runs with depth 1 and cannot fire further `intent`
rules. Two rules cannot ping-pong a room.

**Restart.** Rules and timers are rebuilt from the current state on connect. `motion_at` starts as
the time of the last motion event in the log for that room, so an `idle` rule does not fire the
moment the brain comes back after a reboot at 3 a.m. Nothing else is persisted.

**Driver down.** No state changes arrive, the tick still runs, but `_apply` fails and is logged as
such. When the link returns, rules see the fresh snapshot as a stream of changes and behave as if
the house had just been switched on.

## Holds: a hand beats a rule

When a person sets a room's intent from the panel, the room gets `hold_until = now + hold`, where
`hold` is per scene in `scenes.json`:

```json
"_hold": {"occupied": 7200, "movie": 14400, "guests": 43200, "asleep": 0, "away": 0, "empty": 900}
```

`asleep` and `away` carry no hold: they are meant to be released by a rule (morning, someone came
home). A direct device action from the panel (turn this light on) also holds its room, for the
`occupied` duration, so a rule does not switch off a light someone just switched on. Physical
switches are device actions from HA's point of view and get the same treatment when the device
was changed with `source=device` and no rule or tap caused it.

A held room shows it on the panel: the scene chip gets a hand icon and the time left.

## Presence

HA already models people through `person.*` entities, fed by the companion app, the router, or
Ring's arm state. The brain maps them to a single home-level signal: `somebody` if any person is
`home`, `nobody` otherwise. Which people count is a setting the panel asks for once: the owner
from setup, plus anyone added later. Ring Alarm's mode (`away` / `home`) arrives through
ring-mqtt and is a second, coarser source; both are signals, neither sets intent on its own.

Room-level presence is motion only in this phase. mmWave presence sensors slot in later as
`motion` devices that stay `on`.

## What the panel gains

- **Who set it.** The scene chip on a room reads *Occupied · by rule* or *Occupied · by hand, 1h
  left*. One line, no jargon.
- **Why.** A tap on that line shows the last three intent events for the room from the log, each
  as a sentence: *8:12 pm, the hallway became occupied because someone walked through after dark.*
  This is rendered from the event detail, no model involved.
- **Routines sheet.** A list of rules by room, each with its name and an on/off switch, reached
  from the same bottom-of-sheet place as the Advanced door. Editing is by hand in the file in this
  phase; the assistant authors in the next.

Stream messages: `intent` (room, state, set_by, hold_until) so the chip updates without a poll.

## API

```
GET  /rules                      the file, plus a "valid" flag and any parse errors
PUT  /rules                      replace the file, validated first; bad file is refused, old one keeps running
POST /rules/{id}/enable          {"enabled": false}
GET  /rules/{id}/dry-run         what this rule would do right now: conditions with their current values, held or not
GET  /rooms/{id}/why             the last intent events for the room with their detail
GET  /presence                   {"somebody": true, "people": [...]}
```

`PUT /rules` is the assistant's only way in, and it goes through a human first (below).

## The assistant, in outline

Not built in this phase's first half, but the contract is fixed now so the rules file does not
have to change later.

- **Authoring.** *"When I leave, everything off except the porch"* becomes a draft rule in
  `rules.json` under `"drafts"`, with `by: "assistant"` and the sentence it came from. The panel
  shows it as a card with Approve and Discard. Approve moves it to `rules`. The evaluator never
  reads `drafts`.
- **Explaining.** *"Why did the hallway light come on?"* is answered from `/rooms/hallway/why`
  and `/events`. The model turns detail into prose; the facts come from the log.
- **Suggesting.** The same authoring path, started from a pattern the brain notices (the same tap
  at the same time five days running). Always a draft.

The model runs wherever it runs; the brain is the only thing that talks to it, and it holds no
token for HA.

## Sensors: what triggers today

| Signal | Source in the house now | Arrives as |
|---|---|---|
| Motion, per Brilliant panel | Brilliant Control panels | `binary_sensor` via brilliant-mqtt |
| Contact and motion, Ring Alarm | Ring Alarm sensors | `binary_sensor` via ring-mqtt |
| Home / away | Ring Alarm mode, HA persons | `alarm_control_panel`, `person`. People decide when there are any; armed-away overrides a lagging phone; arming and pending keep the last answer |
| Sun, time | the brain's own clock and location | computed |
| Illuminance | nothing yet | |

The first rules should be written against Brilliant motion and Ring contact sensors, which need no
new hardware. One Zigbee motion-and-lux sensor per main room (Aqara P1 or similar) comes with the
Pi and the Zigbee stick and is what makes the `light` condition real.

## Milestones

1. **The loop closes.** `rules.py` with `motion`, `idle`, `time` and `sun` triggers; `rules.json`
   with the two hallway rules above; `source=rule` in the log with full detail. Proof: the hallway
   comes on by itself after dark and goes off ten minutes later, and `/events` says why.
2. **Hands win.** Holds from taps and device actions; `held` events; the chip shows *by hand*.
3. **Away and back.** Presence from persons and Ring mode; `presence` trigger and condition; the
   home goes to `away` on its own and comes back to `occupied` at the door.
4. **Why.** `/rooms/{id}/why`, the routines sheet, the `intent` stream message.
5. **Drafts.** The assistant writes rules into `drafts`; approve and discard on the panel; explain
   from the log.

The exit test is the plan's: a guest for a weekend, no instructions. Practically: the lights they
walk into come on, the ones they leave go off, nothing surprises them at night, and nobody has to
explain a tablet.

## Decisions to make now

| Question | Proposal |
|---|---|
| Where do rules live | `brain/rules.json`, data next to scenes, not in HA automations |
| Sun from HA or computed | Computed from location; works with HA's location unset and with the internet down |
| Room presence | Motion plus idle timeout; no per-room inference beyond that in this phase |
| Conflict between rules | File order; first intent per room per evaluation wins |
| Hold length | Per scene in `scenes.json`; `asleep` and `away` never hold |
| Rule editor in the panel | Not in this phase; on/off only. Authoring is the assistant's job |
| Does the assistant get an HA token | No. It sees `rules.json` and the log through the brain, nothing else |

## Not in this phase

Climate schedules, energy, voice, per-person preferences, geofencing beyond what the companion app
already does, and any rule that HA's own automation engine would need. If a rule cannot be said in
the vocabulary above, the vocabulary grows, not the number of places rules live.
