<!-- SPDX-FileCopyrightText: 2026 Temitope Adeyeri -->
<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->

# The boards

*What every physical thing we make has to be, whoever lays it out and whatever it does. One
directory per board below; `puck-revA` is the only one so far. This page is not about any of them —
it is the short list of claims the rest of the product has already spent itself on, so that a board
cannot quietly fail one and be found out after the panels are ordered.*

---

## 1. A button, reachable, on the outside

**Every product we make carries a button a person can press without tools, without taking anything
apart, and without being told where to look.**

This is not a feature and not a preference. It is what the whole of our own door rests on.

**Why.** A hub in a house can hear things it does not own. So before anything of the household's
moves, the thing being adopted has to prove that whoever is answering on the wall is actually in the
room with it — and on 21 September that proof became **a press on the button**
(`design/door/PressIt.dc.html`, `docs/strip.md` item 23). Holding the object is the proof. There is
nothing to read, nothing to count, nothing printed on a label to leak, and nothing derived from the
chip.

**The gate is on the device, and that is the point.** Four lines of the strip's firmware refuse the
household's Wi-Fi until the button has been pressed; a gate the hub released would be a gate whoever
spoke first released, which is the unauthenticated link the firmware was rewritten to remove. A hub
cannot press a button, and neither can a bridge puck running an errand on its behalf
(`design/ears/`), which is exactly why a proxy adds no trust surface.

**And the answer that does not need a button does not generalize.** The rung below the press is the
device making itself known with its own light (`design/door/PopLight.dc.html`), and a proof made of
light only works on something two meters long. A puck has one LED. A sensor has none. An answer that
needs a strip is not an answer for our door, so a board without a button drops to a rung that is
worse for the household and, for some products, does not exist at all.

**What "reachable" means, so it can be checked rather than argued:**

- From **outside the assembled shell**, with a fingertip, no tools, nothing removed.
- **In the state the product ships in** — not with a lid off, not through a hole meant for a probe.
- **Before it is placed.** The order is unboxed, plugged in, set up, *then* mounted, and the press
  happens at "set up". A button that is reachable on a desk and not behind a television still passes;
  one that needs the shell open does not. `design/strip/KnockAsked.dc.html` had this backwards once
  and nearly ruled the press out entirely.
- **Never on a strapping pin.** A finger resting on the button at power-up must not be able to change
  how the chip boots. On an ESP32-S3 that rules out GPIO0, 3, 45 and 46.

**What it costs:** one GPIO, one tact switch, one hole, and — where the switch is side-actuated at a
board edge — a printed plunger. The puck already carries three of that same switch, so on that board
the button is the cheapest thing on this page.

**It is free now and impossible later.** A board that reaches fabrication without it cannot be given
one by a firmware change, and the product it becomes cannot be adopted through our own door.

### Where each board stands

| | |
|---|---|
| **`puck-revA`** | **Passes.** `SW3` on **GPIO4** — not a strapping pin — with the internal pull-up (module pin 4, `pinfunction "IO4_4"` in `puck-revA.net`). A C&K KMR2 side tact at the board edge at 180°, the face a person would tap, reached through a 3.6 mm hole cut through both the base wall and the skirt, with a printed plunger whose head stops it falling in (`enclosure/puck.scad`, `show = "plunger"`). `docs/puck-hardware.md` has the reasoning. |
| **The strip's controller** | **No board yet, and there is one thing to get right when there is.** The firmware's `BUTTON_PIN` defaults to **0**, which is BOOT on every devkit — a strapping pin, and the same line the USB bridge's auto-reset pulls from DTR. That is a convenience on a bench, where it is how the press has been tested with nobody in the room, and it is wrong on a product: a finger on it at power-up can drop the chip into download mode. `BUTTON_PIN` is a `#ifndef`, so the board defines it. **Define it.** |

---

## 2. Anything else that belongs here

Nothing yet. A claim earns a place on this page when a board could fail it silently and the failure
would only be found after tooling — the way the button would have been. Everything else about a
board belongs with that board.
