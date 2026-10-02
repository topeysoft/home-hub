# Wording: the words on screen, read by somebody who was not here

*Opened 1 October 2026, from a note on the away boards. The switch that lets a phone use the house when
it is not at home was labeled **From outside** — clear to everyone who had spent a month calling it that,
and a riddle to anyone who had not. Outside of what? The yard? The roofline is a light outside. The note
was not about that one label: the panel's headings and descriptions have been written by the people
building it, in the words the building used, and a whole pass is owed.*

## The rule, from now on

**Every label, heading and description is read as a new household member would read it: someone who
did not watch it being made, holding a phone, glancing.** If the meaning depends on knowing how the
thing was built or what it was called in a design note, it is the wrong word.

This binds every change from 1 October 2026 on, whatever else it is about: a new screen, a new board,
a new sentence from the brain. New work does not add to the backlog below while waiting for the pass
to clean it up.

- **Say what the person gets, in the words they would use for it.** "Use this phone when you're away
  from home" rather than "From outside"; "remotely" is closer than "outside", and plainer still is
  saying the situation itself.
- **Our working names are not product words.** Door, let out, the brain, the band, rest, promotion,
  the relay — useful in `design/` and `docs/`, never on the panel unless a stranger would already say
  them that way. This extends AGENTS.md §5's ban on Home Assistant vocabulary to our own.
- **Prose in comments and design notes can stay idiomatic.** This file is about what reaches the
  screen, not how the code talks to itself.
- **A word that is ambiguous in this house is ambiguous everywhere in it.** "Outside" already means
  the yard and the roofline, so it cannot also mean "away from home".
- **The words come from the brain** where they already do (`docs/messages.md`), so a fix there is a
  fix on every screen.

## Areas

| Area | Status | Boards |
| --- | --- | --- |
| People and phones | **Done, 2 October 2026.** C chosen: a phone is *Home only* or *Anywhere* | `design/words-people/` |
| Setup | Not started | |
| Rooms and devices | Not started | |
| Settings (This hub, Accounts, Share, the passcode) | Not started | |
| The band and its messages | Not started | |
| The brain's sentences outside the areas above | Not started | |

### The words People and phones settled, for every area after it

- A phone that works when you are not at home is set to **Anywhere**; the other answer is **Home only**.
  Never *from outside*, *let out*, *reach the house*.
- The screen on the wall is the **wall screen** when it is named to a person. Never bare *the wall*,
  which also means plaster, and the switches in it.
- **Someone with the passcode** is who can change phones. Never *keeps the house*, *holds the keys*.
- A phone **can use the house**, is **added**, **allowed**, or **removed**. Never *belongs*, *let in*,
  *is out*, *runs it*.
- The house has a **web address**, or a **link**; a phone **switches** to it. Never bare *address*, never
  *move this phone*.
- The phone's own words for its own things: **Home Screen**, not *first screen*.

## Known so far, outside the areas done

| Where | Says | Problem |
| --- | --- | --- |
| `brain/hub/happened.py`, `app/src/ChangesPage.vue` — who did something | "Someone at the wall" | Bare *the wall* |
| `app/src/HubPage.vue`, `brain/hub/api.py` — Restart | "for the screens that keep it. Someone at the wall can do it." | *keep it*, *the wall* |
| `BridgeSheet.vue`, `StripSheet.vue`, `NetworkSheet.vue` | "You can walk away; the wall will say when it is done." | *the wall* as the thing that talks |
| `StripSheet.vue` | "It is being let in now, over Bluetooth" | *let in* for a light being added |
| `HousePanel.vue` and many sheets | "This hub" as a page name | The person bought a box; is *hub* their word? |
| `HousePanel.vue` | "Lock the settings" beside "Change the passcode" | Two names for one thing |
| `AccountsPage.vue` | "Sam's Nest is out." | *is out* for removed |

Add to this table whenever a word stops you, rather than fixing it in passing. Each area's pass starts
from this list and then reads every screen and every sentence the brain says in it, since most of what
it will change has not been noticed yet.

## How the pass is done

**The pass is its own piece of work, a full UI/UX pass over every screen, not something folded into
other changes.** There is a lot of this wording across the panel, so expect it to take more than one
session. Split it by area (setup, rooms, people and phones, settings, the band and its messages, the
brain's sentences), and finish one area before starting the next, so that one screen never speaks
two vocabularies.

It changes what the panel says, which is what the panel looks like, so it follows AGENTS.md §1: the
affected screens are drawn with the new words beside the old, the user picks, and tests that pin a
string are updated with the board, not after it.
