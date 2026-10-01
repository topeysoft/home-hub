# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a strip controller says about itself, and the words the wall says it in.

The strip controller (home-hub-hardware, strip/strip-revA/; docs/strip.md item 51) tells the hub more
than any strip before it. Every ten seconds, and the moment anything changes, it says on
`strip/<chip>/power`, retained: the supply's volts and kind, the board's temperature, and for each
run whether it is on, the kind of supply it was set up on, its amps and ceiling, how far it is
dimmed, its two fault lines, its trips, and the reason it is held dark, if it is.

Until 1 October the hub filed all of that where nothing read it, so a strip could be dark for a good
reason while the wall said it was on. design/controller-panel/, page "held", decided A with B's row:
a strip held dark says so on its tile -- Staying off, and the reason in a few words -- the room gets a
Why?, a tap opens the light's pane with the sentence and the one next step, and Needs a look carries
a row for it to Home. The words are Reasons.dc.html's, one sentence and one next step per reason.

TWO THINGS IT REPORTS ARE NOT FAULTS, and must never be said as one: the board running hot and easing
its ceiling down (never to dark), and a long strip at full white held just under one socket's 5 A.
Both are the household's light behaving. They get one quiet line on the pane and nothing on the tile.

And `starting` -- the second at power-up while the supply reads the same twice -- is never said.

Pure functions, so the words can be held to the board without a broker.
"""
import json

# The reasons that keep a run dark, as the firmware spells them (strip/firmware/main/guard.h, held_word).
HELD = ("supply", "range", "trips", "wiring")
# Above this the board eases its ceiling (guard.h, HOT_FROM_C). Said, quietly, never as a fault.
HOT_FROM_C = 85
# A RUN DRAWING MORE THAN THIS HAS A STRIP ON IT. A WS2812B is about a milliamp dark, so even thirty
# lights resting read above it, and a socket with nothing in it reads the monitor's own noise.
# UNMEASURED on a real rev A board: the monitor is about 0.23 V an amp, and this is the number a bench
# has to confirm before "there's a second strip" is ever said on its strength alone.
PRESENT_A = 0.05


def read(payload) -> dict | None:
    """The `power` report as a dict, or None for anything that is not one.

    An empty payload is the retained topic being cleared -- a strip that was forgotten -- and is
    "nothing to say", not a fault."""
    if isinstance(payload, dict): got = payload
    else:
        try: got = json.loads(str(payload or ""))
        except ValueError: return None
    if not isinstance(got, dict) or not isinstance(got.get("runs"), list): return None
    return got


def volts(v) -> str:
    """A supply as its label prints it: 12 V, not 12.1 V. The label on the brick is the one thing a
    household can check without knowing anything, so the wall says what the brick says."""
    try: f = float(v)
    except (TypeError, ValueError): return ""
    return f"{round(f)} V" if f >= 4 else f"{f:.1f} V"


def runs(power: dict | None) -> list[dict]:
    """Each run, as the wall needs it: its number from 1, whether there is a strip on it, and why it
    is dark if it is."""
    if not power: return []
    out = []
    for i, r in enumerate(power.get("runs") or []):
        if not isinstance(r, dict): continue
        held = str(r.get("held") or "")
        try: amps = float(r.get("a") or 0)
        except (TypeError, ValueError): amps = 0.0
        try: dim = int(r.get("dim", 100))
        except (TypeError, ValueError): dim = 100
        out.append({"run": i + 1, "on": bool(r.get("on")), "held": held if held in HELD else None,
                    "set_up_on": int(r.get("class") or 0) or None, "a": amps, "dim": dim,
                    "strip": amps > PRESENT_A, "trips": int(r.get("trips") or 0)})
    return out


def _supply_words(set_up: int | None, now: int | None, v) -> tuple[str, str, str]:
    """The sentence for a run set up on one kind of supply and given another. The burn is only true
    one way: a 12 V strip on 24 V is a strip on fire; a 24 V strip on 12 V is merely dark and dim."""
    a, b = f"{set_up} V" if set_up else "another", f"{now} V" if now else volts(v)
    if set_up and now and now > set_up:
        why = f"A {a} strip would burn on {b}, so the controller is keeping it off."
    else:
        why = f"A {a} strip won’t light properly on {b}, so the controller is keeping it off."
    text = f"It was set up on a {a} power supply, and it’s on a {b} one now. {why}"
    row = (f"It was set up on a {a} power supply and it’s on a {b} one now, so the controller is "
           f"keeping it off to protect it.")
    return text, row, a


def _range_words(v, both: bool) -> str:
    try: f = float(v)
    except (TypeError, ValueError): f = 0.0
    said = volts(v)
    if f > 30: first = f"Its power supply gives {said}, more than any strip is made for."
    elif f < 4.3: first = f"Its power supply gives only {said}, too little for any strip."
    else:
        n = said.replace(" V", "")
        first = f"Its power supply gives {said}. Strips are made for 5, 12 or 24 V, and {n} is none of them"
        # 19 V is a laptop brick, and that is the commonest wrong supply anybody has in a drawer.
        first += " — it may be a laptop charger." if 15.5 < f < 21 else "."
    return first + (" Both strips on this controller are off." if both else "")


def held(reason: str, power: dict | None = None, run: int = 1, name: str = "") -> dict | None:
    """Everything the wall says about a run held dark, or None when it is not.

    `state` is the tile's big word and `tile` the few words under it; `text` and `next` are the pane's
    sentence and its one next step; `row` is the Needs a look sentence, which carries the name; `chip`
    is the room's line. The four held reasons each end in something a person can do, and two of them
    in "unplug the controller and plug it back in", because trips and wiring hold until the board is
    next powered on -- the controller's rule, said in the only words that matter."""
    if reason not in HELD: return None
    power = power or {}
    rs = runs(power)
    me = next((r for r in rs if r["run"] == run), {})
    now = int(power.get("class") or 0) or None
    name = name or "The strip"
    if reason == "supply":
        text, row, was = _supply_words(me.get("set_up_on"), now, power.get("v"))
        out = {"state": "Staying off", "tile": "on a different power supply", "text": text,
               "next": f"Plug the {was} supply back in", "after": "It comes on by itself as soon as it has the right one.",
               "row": f"{name} is staying off. {row} Plug the {was} supply back in and it comes on by itself.",
               "set_up_on": f"{me['set_up_on']} V" if me.get("set_up_on") else None,
               "now_on": volts(power.get("v")) if power.get("v") is not None else None,
               "chip": "The strip is staying off to protect itself"}
    elif reason == "range":
        both = sum(1 for r in rs if r["held"] == "range") > 1
        text = _range_words(power.get("v"), both)
        out = {"state": "Staying off", "tile": "wrong kind of power supply", "text": text,
               "next": "Use the power supply that came with the strip", "after": "It comes on by itself once it has one.",
               "row": f"{name} is staying off. {text} Use the power supply that came with the strip.",
               "set_up_on": f"{me['set_up_on']} V" if me.get("set_up_on") else None,
               "now_on": volts(power.get("v")) if power.get("v") is not None else None,
               "chip": "The strip is staying off to protect itself"}
    elif reason == "trips":
        text = ("It cut out five times in a minute, so the controller stopped trying. Something is drawing "
                "more than it should — a pinched or wet cable, or a fault in the strip.")
        out = {"state": "Switched off", "tile": "it kept cutting out", "text": text,
               "next": "Check the cable, then unplug the controller and plug it back in", "after": "",
               "row": f"{name} has switched off. {text} Check the cable, then unplug the controller and plug it back in.",
               "chip": "The strip switched itself off to protect itself"}
    else:
        text = ("Power was reaching the wire that carries the colors — usually two wires swapped where the "
                "strip joins its cable. It was caught in time, and nothing is damaged.")
        out = {"state": "Switched off", "tile": "a wire in the wrong place", "text": text,
               "next": "Swap them back, then unplug the controller and plug it back in", "after": "",
               "row": f"{name} has switched off. {text} Swap them back, then unplug the controller and plug it back in.",
               "chip": "The strip switched itself off to protect itself"}
    return {"held": reason, **out}


def quiet(power: dict | None, run: int = 1) -> str | None:
    """The one muted line for a run that is lit a little less than asked, or None. Never a fault, and
    never on the tile: running hot eases off and comes back; a long strip at full white holds just under
    what one socket gives."""
    if not power: return None
    me = next((r for r in runs(power) if r["run"] == run), None)
    if not me or me["held"] or me["dim"] >= 100: return None
    try: hot = float(power.get("board_c")) > HOT_FROM_C
    except (TypeError, ValueError): hot = False
    if hot:
        return "A little dimmer than that for now. The controller is warm, and it eases off until it cools. More air around it helps."
    return "At full white this much strip asks a little more than one socket gives, so it holds just under. Nothing needs doing."


def light(power: dict | None, of_runs: list[int], name: str = "") -> dict | None:
    """What one LIGHT says, made of one or more runs on this controller.

    A light all of whose runs are held is held, and says the first reason. A light with one run held
    and another lit is not "Staying off" -- it is on, and the pane says which part is dark and why
    (design/roofline/OneLight.dc.html: "a dark garage end is not a dark house")."""
    rs = [r for r in runs(power) if r["run"] in of_runs]
    if not rs: return None
    dark = [r for r in rs if r["held"]]
    if dark and len(dark) == len(rs):
        return held(dark[0]["held"], power, dark[0]["run"], name)
    out: dict = {}
    if dark:
        part = held(dark[0]["held"], power, dark[0]["run"], name) or {}
        out["dark"] = [{"run": r["run"], **(held(r["held"], power, r["run"], name) or {})} for r in dark]
        out["text"] = part.get("text")
    q = next((x for x in (quiet(power, r["run"]) for r in rs) if x), None)
    if q: out["quiet"] = q
    return out or None
