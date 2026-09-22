<!-- SPDX-FileCopyrightText: 2026 Temitope Adeyeri -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# Working in this repository

For coding agents, and for anyone configuring one. [`CONTRIBUTING.md`](CONTRIBUTING.md) is the
contract — the rules that do not change, what CI checks, how commits are written — and this file
does not repeat it. What follows is the part that is learned rather than documented: the order of
work, the instruments that lie, and the decisions already made that should not be reopened.

Run `tools/dev.sh` first, in any session. It prints where this checkout was left, what is
installed, and what is still listening on a port from yesterday.

---

## 1. A screen is drawn before it is built

**Anything that changes what the panel looks like starts as an artboard, and the artboard is
reviewed before a line of `app/src/` is touched.** Not a description of a screen, not a plan for a
screen — a drawing you can open, at the size of the real display.

This is the rule with the most history behind it. Work that skipped it has been rejected for
looking "basic" while having every part correct, because composition is not a list of parts and
cannot be reviewed as one. Work that followed it has been settled in a single message.

**How it is done here.** The boards live in `design/`, one directory per area, each with a
`canvas.json` that places every board and every note on a canvas:

```sh
tools/dev.sh design        # every collection, on the canvas it was drawn on
```

A board is a `.dc.html` file: the markup carries the design's real values — colors, sizes, spacing,
radii, shadows — and `canvas.json` gives it an `x`, a `y`, a `title`, and an annotation beside it
saying what it argues. Boards that need state extend `DCLogic` in a `<script data-dc-script>` and
interpolate `{{ dotted.paths }}`; `data-props` turns a value into a chip you can flip while looking
at it, which is how one board covers fifteen weather conditions instead of fifteen boards.

The wall is **1440×900**. The phone is **390×844**. A board that argues about another screen says so
by being that size.

**The shape of a design change.** Every collection in `design/` follows it:

1. **`Today.dc.html`** — what the screen looks like *now*, drawn from the shipped panel. Without it
   there is nothing to compare against and every later board is an assertion.
2. **The directions** — two or three boards, each a whole answer, named for what they argue
   (`CapA`, `DemoteB`, `LeadC`). Never one proposal. If a visual note has to be repeated, that is
   the signal to stop re-reading the words and draw the variants instead: three pictures have
   settled in one message what two rounds of careful measurement got wrong, because measuring the
   wrong edge precisely is the failure mode, not sloppiness.
3. **The note beside each board** — the case for it, in prose, in `canvas.json`. A board with no
   argument is decoration.
4. **The user picks one.** Offer "something else — I'll describe it" as a real option; the intended
   answer has been outside the candidate set before.
5. **Then build it**, and pin the arrangement with a test that fails on purpose if it drifts
   (`app/tests/rooms.test.ts` is the model). The picture the user chose is the spec.
6. **Leave the rejected boards in place**, on their own canvas page, with their cases intact. They
   are the record of why the shipped thing is the shipped thing.

**Changing a screen that already has boards means changing the artboard first, then the test, then
the code** — in that order. The alternative is a test that pins the panel to a drawing nobody
updated.

**When it is done, compare.** Screenshot the built panel at the board's exact size against the
board, and judge the composition, not the checklist: cards edge to edge, mixed sizes composed as
drawn, no dead space where something was removed, the whole thing one screen on a wall with nothing
to scroll.

Two design sheets are generated from code rather than drawn, and CI enforces it:
`design/Devices.dc.html` from `app/src/art.ts`, `design/Weather.dc.html` from `app/src/sky.ts`.
Change the drawing code and run `npm run art-sheet` / `npm run weather-sheet`.

---

## 2. Reach for the instrument that observes the real thing

A green from the wrong instrument is worse than no green, because it gets reported as verification.
Every one of these has already shipped a bug.

- **Typecheck the panel with `npx vue-tsc --noEmit -p tsconfig.app.json`**, or just `npm run build`.
  `-p tsconfig.json` exits 0 having checked nothing under `src/` — the root config is a solution
  file that only references the real projects. A fast, silent pass over a large source tree is the
  tell.
- **The e2e suite grades `app/dist`, not your working tree.** `playwright.config.ts` serves
  `../dist` on :8399. Rebuild first, or run with `BASE=http://localhost:<your vite port>`. A
  regression test has passed here with its fix deliberately removed.
- **`test-results/` is shared.** Two sessions running playwright in this checkout delete each
  other's traces, which surface as `ENOENT .playwright-artifacts-N/traces/...` and read exactly like
  real failures. Pass `--trace=off --output=<a private dir>`, and `--workers=1` if anyone else is
  running.
- **For motion and layout, trace frames — do not judge from screenshots.** A screenshot takes
  150–250 ms in playwright, longer than most of this panel's transitions, so it routinely misses
  what it is being asked about. Inject a rAF sampler with `page.addInitScript` that records computed
  styles, `getBoundingClientRect()` and `scrollLeft` each frame, and read it back. Then take one
  slowed-down screenshot to judge how it looks. Report the distinct positions you saw, not "it
  works".
- **Check the brain is not older than the code** before debugging a "the panel looks wrong" report:
  `ps -eo pid,lstart,command | grep [m]ain.py` against the mtime of the hub file involved. A hub
  started this morning serves the older shape of `/home` and the panel renders it without
  complaint, so a missing field reads as a missing feature. `tools/dev.sh` prints the age of
  everything listening.
- **Never start a second brain against a real house** to test something. It reads their live Home
  Assistant and will attempt driver provisioning. Use `HUB_PORT` and `HUB_DATA`, and say that you
  did.
- **To see a screen against real rooms, borrow a house's brain rather than standing one up.**
  `tools/dev.sh live [host]` serves the panel from this tree, hot reloaded, and hands every path the
  brain owns to a hub that is already running — nothing is started here and nothing is pushed there.
  It is the answer to the rule above, and it inverts the stale-brain trap: that hub follows released
  code, so a route you wrote this morning comes back 404 and draws as a missing feature. The mode
  prints how far this tree is past that brain before Vite starts, and you are expected to read it.
  Two things it cannot do: every tap is that house — their lights, their names, their Restart button
  — and the Advanced door and driver links point at your own machine, because they are built from
  `location.hostname`.

---

## 3. This checkout is shared

More than one session works in this tree at a time, and the git index is shared both ways.

- **Always `git commit -m "..." -- <paths>`.** Never bare. A bare commit ships whatever the other
  session has in flight under your message.
- A new file is untracked, so `commit -- path` refuses it. `git add` **only your own** new files
  first, then commit with the full path list.
- **A sweep can land half a change, and that reaches houses.** A commit once took an `api.py` edit
  without the `updates.py` edit it called into; the hub follows `main`, updated itself overnight,
  and every tap on Install answered 500. The update's own safety net passed it, because a build that
  is wrong on one route still answers `/alive`.
- After a change spanning files, prove each half landed: `git show HEAD:<file> | grep -c <marker>`
  for every file. A caller in `HEAD` with its callee still in your working tree is the dangerous
  shape.
- Diff a file you did not create before committing it, and re-read any file before editing if
  minutes have passed. If someone else's lines ride along, say so rather than letting it pass.
- Expect your own uncommitted work to disappear into their commits. Check `git log` before assuming
  an edit was lost.

Branch off `development`; pull requests target `development`, not `main`.

---

## 4. Panel rules that nothing catches for you

- **`app/src/panel.css` is one flat global sheet with no scoping.** A class name that already exists
  does not conflict loudly — the later block silently wins and restyles the *other* component. Before
  adding a block, `grep -n "^\.name" src/panel.css` for every class in it. Afterwards, open one
  unrelated screen with a similar vocabulary and look at it. `npm run lint:css` now catches the
  duplicate itself, which tsc, eslint and e2e never did — both screens still render — but it cannot
  tell you which of the two blocks was the one you meant, so the looking still matters.
- **Colors the tokens have named are spelled with their name.** `--lamp`, `--live`, `--danger` and
  `--lamp-ink` each carry a `-rgb` companion, so a wash of one at any strength is
  `rgba(var(--lamp-rgb), .3)` rather than the channels written out. This is not tidiness: the accent
  had been spelled out by hand 71 times, and retuning it would have recolored some of the house and
  left the rest behind. `lint:css` fails on a literal from the palette. A shade the palette does not
  have is still yours to write — and the radius scale is three steps, so an off-scale radius is
  allowed too. Snapping either to a scale changes how the panel looks, which means an artboard
  first, per §1, not a lint fix.
- **Nothing vanishes under the finger that touched it.** A card or chip the person just acted on
  keeps its place, drained, saying what it now is and when — and doubles as the undo. It may only be
  taken away at a moment nobody is watching: the wall going to rest, the app going behind another,
  or a long backstop. Even a one-second fade is wrong; the trigger is not duration, it is that the
  person is still looking. This is the `done` map in `app/src/store.ts`, swept by `App.vue` — extend
  it rather than inventing a second per-screen timer. A scene ("Everything off") is the exception:
  the row emptying is its confirmation.
- **Emitter colors are not screen colors.** Never drive an LED with the panel's palette tokens.
  `--lamp`, `--live` and `--danger` are pastels chosen to read as ink on a dark field; an LED gives
  the eye no reference, so a pastel emitter reads as white. Indicator colors want the off-channels
  near zero. And write a WS2812 **only when the color changes** — it latches, and on the bridge
  puck's marginal data line, rewriting a steady color at 25 Hz turned one misread frame into
  twenty-five a second.
- **Preview panel states with query params** rather than clicking through: `?setup=1&page=rooms`,
  `?sheet=add`.

---

## 5. Product decisions already made

Do not reopen these, and do not propose around them.

- **Out of the box.** The box is for a non-technical person: plug it in, open `hub.local`, answer a
  few questions on screen. **No household should ever need to open Home Assistant's UI** — the
  Advanced door is a last-resort curiosity, not a path any task depends on. Home Assistant stays the
  rented engine; independence is from its UI, not its APIs. Prefer a conversation on screen over a
  config file, and never surface entity, YAML or Home Assistant vocabulary in the panel.
- **The host is not only a Pi.** A NUC or mini PC is the likely customer box; the Pi 5 is the floor,
  not the design point. Size heavy work (speech, models) to the detected host class, say which tier
  is running, design for the large tier and keep the small one working.
- **Away from home is pairing plus a maker-run relay plus a real certificate per hub on
  `elyir.app`.** Do not propose Tailscale, a VPN, or a cloud tunnel again — a second app and a
  vendor login make the hub feel inauthentic, and one app is the product. The LAN stays open when no
  code is set.
- **Maker-run infrastructure is Terraform, always.** Never propose a Cloudflare dashboard click, a
  hand-made DNS record, or a manually created API token as a step. Runtime work (a house
  registering a name) belongs in a service that calls an API, not in Terraform state. Prefer the
  design that needs no per-house DNS write at all.
- **A typed command box came before voice, and the three-household field test is deferred
  indefinitely.** Do not schedule it. Simple commands stay deterministic — a fixed grammar, no model
  — and the model handles only the rest.
- **An arrival announces itself quietly, and takes a screen only where it was asked for**
  (22 September, `design/knock/`, direction C with A). A knock is one line in the band and a dot on the
  `+` door, exactly as a thing found on the network already is; it fills the page only when somebody is
  already on Add. The line is its own for an hour, then folds in with anything else waiting, and goes
  when the thing stops knocking; the dot stays. **Add is not a tab and must not become one** — the tab
  row is three (the time of day, Rooms, Cameras) and Add is its own round door in the bar, beside This
  house. And **Add is a thing you do**: it scans while it is open, which is the one moment when spending
  the radio is free, and is what lets the background scan be quietened. Built 22 September; the two
  rules are `stripSheetOpen()` and `waitingBand()` in `app/src/adding.ts`, pinned by
  `app/tests/adding.test.ts`, and the two speeds are `LOOK_EVERY`/`LOOK_HOLD` in `brain/hub/strip.py`.
- **The Rooms tab is the ranked bento**, direction A, with quiet rooms as an index of rows and the
  bento (not the index) ending flush. `RoomGrid.vue` still serves the Stack home, Rail home and Wall
  view unchanged.

---

## 6. Prose and spelling

Match the file you are editing. This codebase opens most files with a short prose comment saying
what the thing is *for* and why it exists, in plain words rather than API terms. Comments explain
the reason, not the mechanism. Write commit subjects as what the change does for the person using
the hub.

**American spelling everywhere** — code, comments, tests, docs, design notes, commit messages,
replies: color, behavior, center, recognize, gray, license, canceled, catalog, artifact, neighbor.
Fix British spellings in lines you touch. Two exceptions stay as they are: words the house has to
*match* rather than write (the device vocabulary in `brain/hub/suggest.py`, the room aliases in
`brain/hub/commands.py`, the mock's `/cosy|cozy/`), and spellings owned by somebody else's API
(`aria-labelledby`, `asyncio.CancelledError`, GitHub Actions' `cancelled`, the AGPL text in
`LICENSE`).
