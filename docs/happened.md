# What happened: the catch-up, the audit trail, and keeping the diary a diary

*Written 20 September 2026, from three questions asked together: should the hub keep a dashboard of
history and patterns; can somebody see what happened while they were away without opening every device
in turn; and who changed what. The answer to the first is no and the reason is worth keeping. The other
two are built. `design/happened/` holds the artboards this was drawn from.*

## The finding: the pattern-finding was already there, and a dashboard is the wrong shape for it

The hub already noticed things. `assistant.habits()` has looked for the same scene chosen by hand in the
same half hour on four of the last fourteen days since Phase 4, and it delivers what it finds as **a draft
routine with an Approve button and a sentence** — *"You chose Bedtime for the whole house around 10:30pm on
6 of the last 14 days."* That is a report where the finding and the act arrive together, and it is the
house's existing grammar for this: `health.py` carries the same rule in `acts`, that every line says what
can be done about it.

A chart does the opposite. It hands somebody a line and makes them derive the action. On a wall panel
that a household walks past, it asks them to be an analyst about their own house. The Home tab decision
of 6 September — lead with *now*, no stat tiles, no charts — stands, and this page does not weaken it: it
is a page of This house, reached deliberately, not a tile on the way to the light switch.

So the question was never "should there be a dashboard". It was **which findings are worth noticing**,
each one landing as a sentence with its act.

## Rules that do not change

- **A finding is a span, not an event.** "The porch light has been on for ten hours" is the news. The log
  holds transitions, so that fact is the *distance* between two rows that may be ten hours and forty rows
  apart. This is why the page is not a timeline: on a timeline the finding is invisible by construction —
  you get *Kitchen light turned on, 9:10am* and there is no row at all for the ten hours that followed.
- **What is still true leads, and carries the only buttons.** What is over reads quietly under it with
  none. A door that locked itself at 6:40am is not a job, and a button against it would offer to do
  something that has already happened.
- **The brain writes the words, including the headings.** *"Still on"* is right over two lights and wrong
  over a door that is still unlocked. The panel does not know which it is holding, so `happened.py` names
  the group from what is in it — *"Still on, and still unlocked"* — and the panel draws what it is handed.
  The line under the door is written there too, for the same reason.
- **Nothing is offered that cannot be done.** Nothing shuts a door over the network, so a contact sensor
  gets *Show me* and not *Close*. Offering an act that cannot work is worse than offering none.
- **Nothing is claimed that cannot be known.** A house with no people set up has no idea when anybody
  left, so the page says how far back it looked rather than inventing a window. A house with no code
  cannot tell its phones apart, so the audit says *Someone at the wall* and states the date the code was
  set. In an audit trail a plausible guess is worse than a blank, because a blank cannot be believed by
  mistake.
- **Nothing vanishes under a tap.** Turning the porch light off leaves its row where it was, gains
  *Turned off.* and disables the button. The row is the undo. Re-reading the page from the brain would
  take the finding away mid-tap and carry the heading and everything under it up the screen.

## The event log is bounded now, and that came first

`brain/hub/events.py` was append-only with nothing that ever deleted. A hub that had run a year held a
year of every motion sensor in the house in one file, on eMMC, and the file rode every backup. Everything
on this page reads more of that log than anything before it did, so the bound had to land first.

**What is kept.**

| Kind | Kept | Why |
|---|---|---|
| `state`, `action` | 30 days | Device chatter. The overwhelming majority of the rows, and nothing reads it after a month. |
| `intent`, `held`, `shadowed`, `failed`, `presence`, `comfort`, `said`, `ask`, `notify`, `proposal` | 180 days | The house's own reasoning. `habits()` looks back 14 days; this is an order of margin. |
| `home`, `phone`, `share`, `bridge`, `draft`, and anything unlisted | 365 days | The audit trail. A year is the least that answers *when did that phone get in?* |

An unlisted kind keeps the long time on purpose: a kind added next year is far likelier to be house news
than chatter, and keeping too much is the smaller mistake. `CAP` (500,000 rows) is a backstop, not the
plan — a house that reaches it inside one keeping window is writing something it should not be.

**The rule that makes it safe.** For `state` and `presence`, the newest row for each `(kind, subject,
new)` is never deleted, at any age. That is exactly the row `last_by_subject` returns, and two things
read it to answer *since when*: `health.py` for how long a thing has been offline, and `rules.seed` for
when a room last saw motion. Without the rule a prune silently resets those clocks, and a device that
went quiet in March starts claiming it went quiet today.

The rule is **not** applied to every kind, and the reason is `said`: its `new` is the sentence somebody
spoke, so sparing the newest row per value there would keep one row for every distinct sentence ever said
in the house, for good. The rule buys a clock nothing else can reconstruct, so it is spent only where a
clock is actually read.

**No VACUUM.** It rewrites the whole file under an exclusive lock, which on eMMC is precisely the wear
this exists to avoid. A pruned file plateaus rather than growing, because SQLite reuses freed pages — and
a plateau is what was wanted. New databases are born with `auto_vacuum=INCREMENTAL` so they also give the
space back; an existing one cannot be given it without the rewrite, so it is not.

## Who asked

`who` is a column on the log. `request.state.phone` had identified the phone on every request since the
code landed and never reached the diary; a `ContextVar` set in the middleware now carries it, so that 75
call sites did not have to grow an argument they would forget.

It is written for `source="user"` and nothing else. A rule firing has no who, and neither does a
background job that a request happened to start — and that second case is why this is a rule rather than
a nicety: a task spawned mid-request inherits the request's context and outlives it, so a blanket read
would put a person's name on work they did not do.

## What a household sees

- **What happened**, a page of This house, always present. The lede says when they were out. *Still on*
  leads with a button each; *While you were out* reads under it; *People and phones* says who joined.
  Two folds at the foot: the whole log, and the audit.
- **Who changed what**, behind the code. Its contents are exactly what `lock.needs_code()` gates — if a
  route needed the code to do the thing, the record of it belongs on the same side of the door. Turning a
  light on is not a change to the house and is not in it, which is also what keeps it short enough to be
  read rather than scrolled past. It is the one `GET` on that list.

## Where this stands

*20 September 2026: built. Retention, the `who` column, both pages, the mock and the tests
(`brain/tests/test_happened.py`, `brain/tests/test_events.py`, `app/tests/happened.test.ts`).*

## Open decisions

- **Which findings come next.** The shape takes more without becoming a dashboard: a device that dropped
  off four nights running, a room nobody has used in three weeks that is still being heated. Each one is a
  sentence and an act, added one at a time, and each should have to earn its line.
- **A device's own history.** `recent()` takes a window now, so *what happened at the front door last
  Tuesday* is finally answerable. It belongs on the thing you already opened — the device pane, the room —
  rather than as a fourth place to look.
- **Notifying.** Nothing here reaches out. *The back door has been unlocked for seven hours* is a strong
  candidate for the first thing a house says without being asked, and that is a decision about
  interruption, not about history, so it is not made here.
- **The whole-house intents in `While you were out`.** Routines that ran are in the log and are not on the
  page; the fold carries them. Whether *Bedtime ran* is news or noise wants a real house to answer.
