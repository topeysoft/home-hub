# Turning it off and on again

*Written 18 September 2026. This is a plan, not a build. It covers one action — restarting — from the wall,
from a phone in the house, and from a phone that is not in the house. The goal it serves is the same as every
other document here: nobody who receives a hub ever opens Home Assistant, a terminal, or a support article.*

## The problem with "restart"

Everybody knows the verb and nobody means the same thing by it. When somebody says *restart the hub* they have
one of five things in mind, and they do not know which:

1. This screen is stuck. (Reload the panel.)
2. The house is showing me yesterday. (Restart the brain.)
3. My Zigbee lights all went gray at once. (Restart one part of the engine.)
4. Nothing works and I don't know why. (Restart everything.)
5. The plug in the USB socket has gone deaf. (Restart the machine.)

A product that answers this with a menu of five restarts has handed the household the diagnosis and kept the
easy part for itself. The person at the wall cannot tell rung 2 from rung 3 — that is *the whole reason they
are at the wall*. So the design is one door, one word, and a ladder behind it that the house climbs on the
household's behalf: **the hub picks the smallest restart that could fix what it can see is wrong, does that
one, and offers the next rung only once the first has visibly failed to help.**

The second rule is that this is a **repair, not a setting**. A restart button sitting in a list of settings is
an invitation, and every tap on it is the product admitting it could not fix itself. Restarting belongs where
the fault is named, and the fault is already named: `health.py` turns what is wrong into jobs with `acts` on
them. A restart is an act. The standalone door on *This hub* exists only for the case the house cannot see —
somebody who knows something is off when nothing is reporting it.

## Piece 1: the ladder

Five rungs, in the words the panel uses, with what each one actually costs. The costs are not decoration: they
are what the confirmation sentence is made of, and getting them wrong is how a household learns not to trust
the panel's sentences.

| Rung | The house says | What it does | What stops | How long |
|---|---|---|---|---|
| 0 | *Reload the screen* | The panel reloads itself | Nothing. The hub is not told. | a second |
| 1 | *Restart the Zigbee radio* (named) | One driver part: `zigbee2mqtt`, `ring-mqtt`, `matter-bridge` | That radio's devices only | ~20s |
| 2 | *Restart the hub* | The brain | The screen, motion rules, schedules, the assistant, away access, Apple/Google/Alexa | ~30s |
| 3 | *Restart everything* | The whole stack, engine included | Everything the hub drives | ~2 min |
| 4 | *Restart the little computer* | The machine | The same, and the radios come back with it | ~3 min |

Rung 1 already exists: it is the `{"do": "Try again", "act": "part"}` on a driver line in `health.py`, and it
wants nothing from this design except a better word than *Try again* once it is a restart the person chose
rather than a retry the house offered.

**What keeps working through rungs 2, 3 and 4 is worth saying out loud, because it is a design property this
product paid for and should now spend.** A Zigbee group bound coordinator-side keeps switching. A Brilliant
pair that was migrated to the house's own network talks switch-to-switch with the hub out of the path (see
`docs/brilliant.md`) — the stairway lights work with the brain in pieces. Wall switches are wall switches. So
the sentence before a restart is not "the house goes dark for a minute"; it is **"lights and switches keep
working; the screen and the schedules pause."** That is true, it is the thing a person is actually afraid of,
and answering it in the first line is most of this design.

What does *not* keep working through rung 2 is the part people forget, and it must be named: **motion lights
and schedules run in the brain** (`rules.py`), the Matter bridge is `depends_on: [brain]` so Siri, Google and
Alexa answer *no response*, and a phone away from home loses the house entirely until it is back. Naming those
three is the difference between a person restarting with their eyes open and a person wondering for a minute
whether they broke the house.

## Piece 2: where the door is

Two places, and deliberately not a third.

**On the job.** A *Needs a look* line whose fault a restart could plausibly fix carries the restart as one of
its `acts`, at the rung that fits the fault, with the thing's name in the button: *Restart the Zigbee radio*,
not *Restart*. The person never chose a rung; they tapped the thing that was wrong. This is where most real
restarts should originate, and a hub where they do not is a hub whose health module cannot see the fault —
which is the bug, and it is in the brain rather than in the panel.

**On *This hub*.** The last row, under Backup and Restore:

> **Restart** — If something's stuck, turn the hub off and on again. Lights and switches keep working.  *[Restart]*

One button. No menu, no rung picker, no *Advanced restart options*. The rung is the hub's to choose, and it
chooses by what it can see: a part that is complaining gets rung 1 offered by name inside the sheet; nothing
complaining gets rung 2.

**Not a third place.** Not a long-press on the clock, not a gesture, not a hidden corner of the panel — the
hidden corner belongs to the wall app and means something different (piece 7). A repair somebody has to be
told about by another person is not a repair a household has.

## Piece 3: the sentence before

`health.py` already has the right convention and this design should not invent a second one: an act carries
`ask` and `yes`, both with the name in them, because *Are you sure?* is not a question anybody can answer. A
restart's question is built from the rung and from what is true in this house right now:

> **Restart the hub?**
> The screen goes dark for about half a minute. Lights and switches keep working. Motion lights, schedules and
> the assistant pause, and Apple Home says *no response* until it's back.
> *[Restart the hub]  [Not now]*

Three things make that sentence, and each is a rule:

- **Measured, not guessed.** "About half a minute" comes from this hub's own last restart at this rung, kept in
  settings. First time, a conservative default per rung; corrected forever after. A hub on a tired SD card that
  takes ninety seconds says ninety seconds.
- **True of this house.** The Apple Home line appears only where something is shared (`share.py` knows). The
  away line appears only on a phone that is away. A house with no rules does not get the rules line. Sentences
  that are true of *some* house are how a panel earns the reputation of exaggerating.
- **What is in flight is named.** A bridge being adopted, a pairing window open, an account halfway through a
  sign-in, a backup packing: each dies with the restart, and each gets its own line — *You're partway through
  adding a device; you'll need to start that again.* Nothing vanishes under a tap without being named first.

And one refusal, in the same words: while an update or a restore is running, there is no button, and the row
says *The hub is installing an update. It restarts itself when that's done.*

## Piece 4: the minute it is gone

This is the only action in the product that destroys the thing being used to perform it, so the waiting is not
a detail — it is most of the experience.

The panel already knows how to wait: `App.vue`'s offline overlay draws *Updating the hub* / *Restoring your
house* over the same machinery. Restarting is a third word for it, with one difference that matters — it is
short enough to count.

- **A countdown, not a spinner.** *Back in about 30 seconds*, from the measured figure. A spinner says "this may
  never end"; a number that runs out says the house knows what it is doing. When the number reaches zero and the
  hub has not answered, the wording changes rather than the animation: *Taking longer than usual. Still trying.*
- **Watched on `/alive`.** That route is already open and carries nothing about the house (`docs/updates.md`,
  piece 1), which is exactly what a panel needs here: it can watch the hub come back without being signed in,
  and a phone that lost its session mid-restart is not stranded.
- **Comes back where it was.** The person was on *This hub*, or on the kitchen, when they tapped. They are on
  *This hub*, or in the kitchen, when it returns — not on Home. The same rule the rest of the panel keeps.
- **Says it is back, once.** *Back. That took 34 seconds.* A quiet line, not a card to dismiss. Nobody should
  have to guess whether the restart they asked for actually happened, and a household that watched it take
  three minutes twice has learned something about their hardware that the hub should be helping them notice.
- **Rung 0 does not do any of this.** Reloading the screen is a reload; dressing it as an event is a lie.

## Piece 5: when it does not come back

The case the rest of the design exists to avoid, and the one that decides whether this feature is safe to ship.

**At the wall.** The kiosk already gives up gracefully — two minutes of no hub and it says so and starts
looking again (`kiosk/README.md`). What it should add is the one true sentence for this situation, because the
wall is the only place the physical answer applies: *Can't reach the hub. If this lasts a few minutes, unplug
it for ten seconds and plug it back in.* That is the floor of the ladder, it is the thing a support call would
say, and there is no shame in printing it.

**On the host.** A restart that does not come back must be caught by the machine, not by a person with ssh —
the same argument `update.sh` already makes and already implements. The pattern is there to copy: after any
rung 3 or 4, the host waits for the brain on the loopback and, if it does not answer and keep answering,
brings the stack up again itself and writes what happened where the brain will find it. Containers carry
`restart: unless-stopped` and self-heal from a crash already; what has no watchdog today is a *stack* that
came up wrong, and a restart button is what makes that reachable by a household.

**Away from home.** This is the rung that can strand somebody, and it decides piece 6.

## Piece 6: who may, and from where

Restarting is a denial-of-service primitive. Anyone who can restart the house can take the lights' schedules,
the cameras, the alarm's panel and the away tunnel down for a minute, repeatedly, from a phone. So it is not a
tap on the house; it is a change to it, and it sits behind more than the code.

- **The code, always.** `needs_code()` gains `POST /restart`. The code is the established gate for a change to
  the house and this is squarely one.
- **The code is not enough.** The code is one secret the whole house shares and it gets read out in kitchens;
  that argument is already made and already implemented as `holds_keys()` in `phones.py`. A phone admitted at a
  wall for the weekend runs the house and may not hand out keys — and may not take the house down either.
  **Restart requires `holds_keys()`**, like letting a phone in and letting one out. A guest holding the code
  gets the same answer they get for the People page: nothing, quietly.
- **The wall may, and refusing it would be theater.** Somebody standing at the panel can reach the power cable.
  Physical presence is the strongest credential this house has and the design should say so rather than
  pretending otherwise. The wall is `how: "setup"`-class and passes `holds_keys()`; it types the code like any
  other change.
- **Away is allowed, and asks a harder question.** The instinct is to forbid it. The instinct is wrong: the
  household that most needs a restart is the one three hundred miles from the plug, and refusing them leaves
  them with nothing until somebody is home. So rungs 1–3 are available away, on the same terms. Rung 4 — the
  machine — asks once more, in the away phone's words: *Nobody is home to unplug it. If it doesn't come back,
  the house stays like this until somebody's there.* Then it does it. The host's watchdog is what makes that
  defensible, and rung 4 should not ship away-from-home until the watchdog does.
- **The code is asked fresh when away.** Whatever grace the code has in the house, it does not apply on the
  relay path, for this route. It is one row of digits against the one action that cannot be undone remotely.
- **One at a time, and not all night.** One restart in flight; a second tap is the button already saying
  *Restarting…* and nothing else. Beyond three in an hour the sheet stops offering the same rung and says what
  it now knows: *The hub has restarted three times in the past hour. Something is wrong that restarting isn't
  fixing.* — with the next rung, and with whatever `health.py` can name, underneath.

## Piece 7: restarting the screen is not restarting the house

The wall tablet can be the broken thing: Android wedged, a white panel, a browser that has lost its way. That
restart is about *this box*, not about the house, and conflating the two is how somebody trying to fix a frozen
screen takes the heating schedule down with it.

So the words stay apart. The panel never says *this screen*; the kiosk sheet never says *the hub*. The hidden
corner already opens a sheet with the hub's address, *Reload* and *Leave kiosk* — it grows the same ladder for
the glass: **Reload the panel → Restart the wall app → Restart the tablet.** It stays in the hidden corner
rather than moving onto the panel, for the reason it is hidden in the first place: a guest does not find it,
and nobody finds it by accident.

The one place the two meet is the failure above: when the hub cannot be reached at all, the panel's restart
button is asking a hub that is not listening. That screen must not offer it. It offers *Try again*, and the
sentence about the plug.

## Piece 8: what the host is asked, and how narrowly

The brain does not run Docker and does not restart anything itself — that rule is `updates.py`'s and it is
worth keeping exactly as strict, because it is the rule that stops anything able to write into the data volume
from choosing what runs on the machine.

- **Rung 2 needs no privilege at all.** The brain restarts itself by finishing the response, flushing the
  event log, and exiting. `restart: unless-stopped` brings it back within a second or two. No host script, no
  new escalation, no file — and the rung a household reaches for most is the one that costs the least to build.
- **Rungs 3 and 4 follow the update path.** `restart.request` in `brain-data`, a `PathExists` unit
  (`home-hub-restart.path` → `home-hub-restart.service` → `restart.sh`), by exact copy of what is already
  there and already reviewed.
- **The request names a rung, never a command.** One word from a fixed set — `stack`, `machine` — validated
  against a whitelist in the script, which then chooses what to run. A request file that could carry a command,
  or a unit name, or a container name, would turn "can write the data volume" into "can run anything as root".
  `update.sh` makes this same point about the version it is handed; keep the shape identical so a reader of one
  recognizes the other.
- **A part is not the host's business.** Rung 1 restarts a driver part, and the brain already has a route to
  the engine for exactly that (`retry_part` in `provision.py`). It stays there.
- **Every restart is written down.** `hub.log.add("home", "restart", …)` with the rung, the reason offered, and
  who asked — the phone's name, or *the wall*. It shows up in the house's own history like everything else. A
  household should be able to see that the hub restarted at 3:14 and that nobody asked it to; that is how a
  failing radio gets noticed, and it is also how a household would notice somebody else's phone doing it.
- **Self-healing says so.** If the watchdog ever restarts the stack by itself, it is not silent: it becomes a
  *Needs a look* line naming what did not come back. Silent self-healing is how a household runs on a dying SD
  card for a year.

## Piece 9: two things to fix before the button exists

Both are live today and both get worse the moment restarting is one tap on a phone.

1. **The wrong-code lockout does not survive a restart.** `Lock._fails` is a dictionary in memory
   (`lock.py`): five wrong codes make an address wait a minute, and the counter is gone the instant the brain
   does. Today that needs somebody at the plug. With a restart route it would need a phone — and while the
   route itself is gated by the code, a household that reuses the code elsewhere, or a phone left signed in,
   makes "restart, then five more guesses" a real loop. The counter belongs on disk, with the window kept
   across a restart. It is a small change and it is a prerequisite, not a follow-up.
2. **A restart during an update or a restore must be impossible, not merely discouraged.** The panel hiding
   the button is not enough: a phone with a stale page can still post. The route refuses while
   `update.json` says `running` or a restore is in flight, in the same words the row shows.

## Order

1. **The lockout on disk, and the refusal during an update.** Piece 9. Nothing else ships before these.
2. **Rung 2, from *This hub*.** The brain exiting on purpose, the gate (`needs_code` + `holds_keys`), the
   measured timing, the countdown overlay, coming back where it was. This alone covers most of what households
   actually mean, and it needs no host change at all.
3. **The restart as an act on a job.** `health.py` offers it at the rung that fits the fault, named. This is
   the version of the feature people should meet first, and it only exists once rung 2 does.
4. **Rung 1's better word.** *Try again* becomes *Restart the Zigbee radio* where that is what it is.
5. **The wall's ladder and its sentence about the plug.** Kiosk-side, independent of everything above.
6. **The host watchdog, then rungs 3 and 4.** In that order — a rung that can strand a household should not
   exist before the thing that catches it does.
7. **Rung 4 away from home.** Last, with its own question.
