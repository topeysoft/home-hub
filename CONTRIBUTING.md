# Contributing to home-hub

home-hub is a smart home hub built on one principle: **own the experience and the intelligence, rent
the drivers.** The product is the panel and the brain. Home Assistant, Zigbee2MQTT and Z-Wave JS are
plumbing, reached only through their APIs, and never shown to the household.

Contributions are welcome. The most useful ones are usually new device support, a driver that was
missing, or a bug you hit in your own house.

## Before you start

- **Sign the [CLA](CLA.md).** One comment on your first pull request, once, forever. It keeps the
  project AGPL for the people running it and keeps commercial licensing possible for the maintainer.
- **Open an issue first for anything large.** A refactor or a new subsystem is worth agreeing on
  before you spend a weekend on it.
- **Read [`README.md`](README.md#layout)'s Layout section.** It explains which directory does what,
  and it will save you guessing.
- **Read [`AGENTS.md`](AGENTS.md) if you are working with a coding agent** — or are one. It carries
  the things this file does not: that a screen is drawn as an artboard before it is built, which
  verification commands answer about the wrong thing, and which product decisions are already
  settled.

## The rules that do not change

These are in [`README.md`](README.md#rules-that-do-not-change) too, and a change that breaks one will
not be merged however good it is otherwise:

- Works with the internet down.
- Home Assistant is touched only through its APIs; its UI is the Advanced door, never the product.
- The assistant model writes and explains rules. It never executes one.
- Setup is a conversation on the screen, never a file to edit.
- Nothing on the panel ever mentions Home Assistant, entities, or YAML.

That last one matters more than it looks. If your change surfaces a Home Assistant concept to
somebody's grandmother, it is not finished yet.

## Running it

A Mac or Linux box is enough to develop against; you do not need a Pi, a hub, or any account. You
need node 22+ and python 3.13+, and then one command from the clone:

```sh
tools/dev.sh          # what this is and what to run, or where you left it. Changes nothing.
tools/dev.sh up       # installs both halves, then the panel on a mock house at the address it prints
```

The mock house has eight rooms, lights at half, a film on the TV and three cameras, and every change
to `app/src/` is on the screen as you save it. [`README.md`](README.md#starting-and-starting-again)
has the rest, including how to point the panel at a real brain.

## What CI will check

Run these before you push — they are exactly what [`ci.yml`](.github/workflows/ci.yml) runs, and
every one of them has to pass.

**The brain** (Python 3.13):

```sh
cd brain && ruff check .
cd brain && python -m pytest tests -q --cov=hub
```

**The panel** (Node 22):

```sh
cd app && npm run lint
cd app && npm run lint:css
cd app && npm run typecheck
cd app && npm run test:coverage
cd app && npm run build
cd app && npm run art-sheet:check && npm run weather-sheet:check
```

The two sheet checks exist because the design sheets are generated from `src/art.ts` and `src/sky.ts`
— a drawing changed in one and not the other is the drift they are there to catch.

`lint:css` holds the styles to two rules. A color the tokens at the top of `panel.css` have already
named has to be spelled with its name: write `rgba(var(--lamp-rgb), .3)`, never the channels. And a
selector may not be defined twice — in one flat global sheet a repeated class name does not conflict
loudly, it silently restyles the *other* component, which neither the typecheck nor the browser
tests will ever report. The sheet arrived at that rule with 22 such pairs, read through once and
found to be 21 harmless ones — blocks that set different properties and compose — plus one that was
genuinely dead, now removed. The run is capped at what remains: fixing one keeps passing, adding one
does not. Off-scale radii and one-off shades are
deliberately still allowed — this panel is hand-tuned, and snapping a value to a scale is a design
decision, which means an artboard rather than a lint fix.

**The Matter bridge** (Node 22): `cd matter-bridge && npm run check && npm test`. Its bugs land in
somebody else's app rather than yours, so the unit conversions are tested hard — three are
inversions, and none of them shows up in a typecheck.

**Coverage may not go down.** Both the brain and the panel enforce a floor. Adding code without
tests will fail the build.

## Commits and branches

Conventional commits, matching what is already in the log:

```
feat(panel): ...    fix(brain): ...    docs(matter): ...
```

Write the subject as what the change does for the person using the hub, not what it does to the
code. Branch off `development`, and open your pull request against `development` rather than `main`.

## Style

Look at the file you are editing and match it. This codebase has a habit worth keeping: most files
open with a short prose comment explaining what the thing is *for* and why it exists, in plain words
rather than in API terms. Comments explain the reason, not the mechanism. Follow that and your change
will look like it belongs.

**American spelling**, in code, comments, tests, docs and commit messages alike: color, behavior,
center, recognize, gray, license, canceled, catalog, artifact. Two things keep the British form on
purpose and should be left alone: words the house has to *match* rather than write — the device-name
vocabulary in `brain/hub/suggest.py`, the room aliases in `brain/hub/commands.py`, the mock's
`/cosy|cozy/` — and spellings that belong to somebody else's API, such as `aria-labelledby`,
`asyncio.CancelledError`, GitHub Actions' `cancelled`, and the AGPL text in `LICENSE`.

## Reporting a security problem

Do not open a public issue. See [`SECURITY.md`](SECURITY.md) if it exists, or email the maintainer
directly. This software runs on boxes inside people's homes; give it the discretion that deserves.
