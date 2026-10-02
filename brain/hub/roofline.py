# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The roofline: a light outside the house, made of several boxes, that keeps evenings and does holidays.

From a household on 30 September 2026: an addressable strip along their roofline, set every Christmas,
Halloween, Easter and July 4th to colors and effects -- "red and green chasing each other on Christmas"
-- on a Bluetooth controller they are replacing with ours. design/roofline/ drew the three questions
that raised, and the household decided all three on 1 October:

    moves     A WITH C. The occasion owns its motion: Christmas chases red and green, Halloween is
              unsteady like embers, Easter drifts, July 4th twinkles. Nobody ever picks a motion from a
              list; the one control is Hold it still, and strips inside stay still. A look can be SAID in
              the command box -- colors, one of five words of motion, slowly or quickly, read by a fixed
              grammar with no model (hub/commands.py) -- and it plays on the roof before it is kept.
    evenings  B. The roofline keeps evenings of its own, like a porch light: asked once, at the end of
              setting up a light that is outside, "Most rooflines are on from dusk until bedtime. Shall
              this one?" -- Every evening, Only in an occasion, Not by itself -- and changeable on its
              pane. An occasion decides only how it LOOKS; dates decide which occasion is showing; and
              an occasion still turns nothing on. The roof turns on because it was asked to keep
              evenings, by the household, once.
    one       C THEN A. Several controllers are ONE Roofline on the wall: one tile, one pane, boxes named
              by where they are, and "Is this more of the Roofline?" at the end of a box's own setup. The
              order of the runs is never asked until a chase is first wanted -- only a chase shows the
              seams -- and then it is asked in the yard: each run lit its own color with a white light
              running the way it goes, tapped in order on a phone, twice to turn one round, pre-filled
              with a guess from the order the boxes were set up.

WHERE A CHASE IS DRAWN. On the boxes, never streamed (the signals rule, docs/strip.md item 50: a Wi-Fi
hiccup mid-chase reads as a broken light). The hub sends each box one description -- colors, motion,
pace, and where each of its runs sits along the whole roof and which way it goes -- and keeps every box
on its own clock (`now`, and `clock/set`). Each box draws its frames as a function of where a light
is along the roof and what time it is, so two boxes agree without ever talking to each other
(strip/firmware/main/look.h). The colors are EMITTER colors, saturated, never the panel's pastels.
"""
import logging, time
from datetime import date, datetime, timedelta, time as dtime

from . import sun

log = logging.getLogger("hub.roofline")

# ---------------------------------------------------------------- what the roof is asked for

# AGENTS.md section 4: an LED gives the eye no reference, so a pastel reads as white. These are the
# boards' own (design/roofline/OwnsA.dc.html, `LED`): what the strip is asked for, not what a screen
# shows. A color word in a said look is one of these names and nothing else.
LED = {"red": (255, 45, 36), "green": (20, 216, 96), "orange": (255, 116, 16), "purple": (154, 69, 255),
       "white": (255, 241, 220), "blue": (42, 99, 255), "warm": (255, 199, 117), "pink": (255, 127, 192),
       "mint": (95, 240, 184), "lilac": (169, 140, 255), "gold": (255, 178, 30)}

# THE FIVE WORDS OF MOTION, and nothing else (design/roofline/SaidC.dc.html). The three ambient motions
# under plainer names, plus chasing and twinkling. Asked for "meteor" or "rainbow", the house answers
# with these five rather than guessing -- so the vocabulary cannot grow from the screen.
MOTIONS = {"still": "still", "drifting": "drift", "flickering": "flicker", "chasing": "chase", "twinkling": "twinkle"}
MOTION_WORD = {v: k for k, v in MOTIONS.items()}
# How long one turn of each motion takes at its own pace, in ms -- the boards' `dur`. "Quickly" halves it.
PACE = {"still": 0, "drift": 14000, "flicker": 1600, "chase": 2800, "twinkle": 2400}

# THE FOUR OCCASIONS, each drawn once by us. `block` is how many lights in a row share a color.
OCCASIONS = {
    "christmas": {"name": "Christmas", "colors": ["red", "green"], "motion": "chase", "block": 4, "ms": 2800,
                  "words": "Red and green, chasing each other slowly"},
    "halloween": {"name": "Halloween", "colors": ["orange", "orange", "purple"], "motion": "flicker", "block": 1, "ms": 1600,
                  "words": "Orange and purple, unsteady like embers"},
    "easter": {"name": "Easter", "colors": ["pink", "mint", "lilac"], "motion": "drift", "block": 1, "ms": 14000,
               "words": "Spring colors, drifting slowly"},
    "july4": {"name": "July 4th", "colors": ["red", "white", "blue"], "motion": "twinkle", "block": 5, "ms": 2400,
              "words": "Red, white and blue, twinkling"},
}
# What a household might call each one, for the command box. Matched, not written (AGENTS.md section 6).
OCCASION_WORDS = {"christmas": ("christmas", "xmas", "the holidays"), "halloween": ("halloween",),
                  "easter": ("easter",), "july4": ("july 4th", "july fourth", "july 4", "the fourth of july",
                                                   "fourth of july", "4th of july", "the fourth", "independence day")}


def easter(year: int) -> date:
    """Easter Sunday, by the anonymous Gregorian computus."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    el = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * el) // 451
    month = (h + el - 7 * m + 114) // 31
    day = ((h + el - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def occasion_on(day: date) -> str | None:
    """Which occasion is showing on this day, or None. DATES DECIDE, which is A's best part kept without
    A's exception (design/roofline, "evenings-decided"): Halloween's colors from Oct 24 to Nov 1 with
    nobody touching anything. They decide how the roof LOOKS, and nothing else -- an occasion still
    turns nothing on."""
    m, d = day.month, day.day
    if (m == 12) or (m == 1 and d <= 6): return "christmas"
    if (m == 10 and d >= 24) or (m == 11 and d == 1): return "halloween"
    if m == 7 and 3 <= d <= 5: return "july4"
    e = easter(day.year)
    # Easter weekend: the Saturday before to the Monday after, three evenings.
    if e - timedelta(days=1) <= day <= e + timedelta(days=1): return "easter"
    return None


def dates_of(occasion: str | None, year: int) -> str | None:
    """When an occasion runs, as the look card on the Roofline's pane says it (design/roofline/DrawnC):
    "Dec 1 – Jan 6". The same dates `occasion_on` decides by, so the card cannot disagree with the roof."""
    if occasion == "christmas": return "Dec 1 – Jan 6"
    if occasion == "halloween": return "Oct 24 – Nov 1"
    if occasion == "july4": return "Jul 3 – 5"
    if occasion == "easter":
        a, b = easter(year) - timedelta(days=1), easter(year) + timedelta(days=1)
        end = f"{b:%b} {b.day}" if a.month != b.month else str(b.day)
        return f"{a:%b} {a.day} – {end}"
    return None


def look_of(occasion: str | None, kept: dict | None = None, still: bool = False, outside: bool = True) -> dict:
    """The look a light is given: its colors as emitter bytes, its motion, its block and its pace.

    `kept` is a look the household SAID for this occasion and kept (C), which replaces ours. `still`
    is Hold it still. And a strip that is not outside is always still: a chase is for the street, not
    the sofa (OwnsA, "Strips inside")."""
    if not occasion and not kept: return {"motion": "off"}
    base = dict(OCCASIONS.get(occasion or "", {}))
    if kept:
        base.update({k: v for k, v in kept.items() if k in ("colors", "motion", "block", "ms", "words")})
    motion = base.get("motion") or "still"
    block = int(base.get("block") or 1)
    if still or not outside:
        # Held still, the colors sit in blocks of at least three so they read as colors, not a speckle.
        motion, block = "still", max(block, 3)
    return {"id": occasion or "said", "motion": motion, "colors": [list(LED[c]) for c in base.get("colors") or ["warm"]],
            "block": block, "ms": int(base.get("ms") or PACE.get(motion) or 0)}


def said_look(colors: list[str], motion: str, quick: bool = False) -> dict:
    """A look in the household's own words: color names from LED, one of the five motions."""
    n = len(colors)
    if motion == "drift" and n == 2: colors = [colors[0], colors[1], colors[0]]
    block = (3 if n >= 3 else 4) if motion in ("chase", "still", "twinkle") else 1
    ms = PACE.get(motion, 0)
    if quick: ms //= 2
    words = f"{_and(colors)}, {MOTION_WORD.get(motion, motion)}{' quickly' if quick else (' slowly' if motion != 'still' else '')}"
    return {"colors": list(colors), "motion": motion, "block": block, "ms": ms, "words": words[0].upper() + words[1:]}


def _and(words: list[str]) -> str:
    w = list(dict.fromkeys(words))
    return w[0] if len(w) == 1 else ", ".join(w[:-1]) + " and " + w[-1]


# ---------------------------------------------------------------- where each run sits along the roof

def layout(parts: list[dict], order: list[dict] | None) -> dict[str, list[dict]]:
    """For each box, where each of its runs sits along the whole roof and which way it goes.

    `parts` are {"chip", "run", "count"}. With an ORDER, runs are laid end to end in it, and a run
    going against the way round starts at its far end: p = at + dir * k is the roof position of the
    k-th light out from its box. WITHOUT one (C), every run starts at 0 and goes away from its own box,
    which is a fact the house has rather than a guess -- every run's first light is at its board -- and
    for every motion but a chase it looks exactly the same as the order being known."""
    out: dict[str, list[dict]] = {}
    count = {(p["chip"], int(p["run"])): int(p.get("count") or 0) for p in parts}
    for p in parts: out.setdefault(p["chip"], [{"at": 0, "dir": 1}, {"at": 0, "dir": 1}])
    if not order: return out
    at = 0
    for o in order:
        key = (o["chip"], int(o["run"]))
        if key not in count: continue
        n, d = count[key], -1 if int(o.get("dir") or 1) < 0 else 1
        out[o["chip"]][int(o["run"]) - 1] = {"at": at if d > 0 else at + max(n, 1) - 1, "dir": d}
        at += n
    return out


def guess(parts: list[dict]) -> list[dict]:
    """B's guess, which A starts from: a box carries on from the one set up before it, each run in turn,
    each going away from its box. Right whenever a person put the roof up in order."""
    return [{"chip": p["chip"], "run": int(p["run"]), "dir": 1} for p in parts]


# The colors the yard flow lights each run in, and calls it by. Named, never numbered; saturated,
# because they are on an LED in the dusk and somebody has to tell them apart from the street.
RUN_COLORS = (("Red", "red"), ("Blue", "blue"), ("Green", "green"), ("Pink", "pink"), ("Orange", "orange"),
              ("Purple", "purple"), ("Gold", "gold"), ("Mint", "mint"))


# ---------------------------------------------------------------- evenings

EVENINGS = ("every", "occasion", "never")
EVENING_WORDS = {"every": "Every evening", "occasion": "Only in an occasion", "never": "Not by itself"}
UNTIL = "23:00"
# DUSK IS THE HOUSE'S OWN, a little after sunset, so the roof does not light in daylight: the sun four
# degrees under the horizon, about twenty minutes after it sets. The boards drew 6:41 PM on Oct 24 in
# Holts Summit, Missouri, and this gives within a few minutes of it.
DUSK = -4.0

# What a light's room has to be called for the light to count as outside. Matched against the
# household's own room names, so these are words people use, not a list anybody chose from.
OUTSIDE = ("outside", "outdoor", "outdoors", "roof", "roofline", "porch", "yard", "garden", "patio", "deck",
           "driveway", "eaves", "exterior", "balcony", "terrace", "veranda", "front of the house")


def is_outside(room_name: str | None) -> bool:
    words = " " + "".join(c if c.isalnum() else " " for c in (room_name or "").lower()) + " "
    return any(f" {w} " in words for w in OUTSIDE)


def _hhmm(s: str) -> dtime:
    try:
        h, m = (int(x) for x in str(s).split(":")[:2])
        return dtime(max(0, min(23, h)), max(0, min(59, m)))
    except (TypeError, ValueError):
        return dtime(23, 0)


def said_time(t: dtime) -> str:
    """11:00, the way the boards write it; 12:30 AM past midnight, where a bare number would be noon."""
    if t.hour < 12 and t.hour >= 1 and t.hour < 5: return t.strftime("%-I:%M AM")
    if t.hour == 0: return t.strftime("12:%M AM")
    return t.strftime("%-I:%M")


class Roofline:
    """The house's one roofline: its boxes, the way round, its evenings, and the look it is showing.

    Kept in settings under `roofline`, so a restore brings it back with the rest of the house. A house
    has at most one; a second outside strip is asked whether it is more of it."""

    def __init__(self, hub):
        self.hub = hub
        self._draft: dict | None = None         # a look said in the command box, playing, not yet kept
        self._draft_until = 0.0
        self._yard: dict | None = None          # the way-round flow, while somebody is in the yard
        self._sent: dict[str, tuple] = {}       # chip -> the last look sent, so it is said only on change
        self._sent_at: dict[str, float] = {}

    # ---- what is kept ----
    @property
    def data(self) -> dict:
        return dict(self.hub.settings.get("roofline") or {})

    def _keep(self, **changes):
        d = self.data
        d.update(changes)
        self.hub.settings.set(roofline=d)

    def exists(self) -> bool:
        return bool(self.data.get("boxes"))

    def boxes(self) -> list[dict]:
        return list(self.data.get("boxes") or [])

    def chips(self) -> list[str]:
        return [b["chip"] for b in self.boxes()]

    def begin(self, chip: str, hw: str | None, place: str = "") -> dict:
        """The first outside strip becomes the roofline."""
        if self.exists(): return self.join(chip, hw, place)
        self._keep(boxes=[{"chip": chip, "hw": hw, "place": place or "The first box", "at": time.time()}],
                   order=None, evenings=None, until=UNTIL, still=False, looks={})
        self.hub.log.add("roofline", chip, None, "begun", source="user")
        self._fold()
        return self.status()

    def join(self, chip: str, hw: str | None, place: str = "") -> dict:
        """More of the Roofline. Its own setup was unchanged; only this last beat was new.

        THE WAY ROUND GOES BACK TO UNKNOWN. A new box is a new run somewhere along the roof, and an order
        that does not name it would put it at the end by accident. It is re-asked only when a chase is
        next wanted, from the guess -- which now includes this box last, the order it was set up in."""
        boxes = [b for b in self.boxes() if b["chip"] != chip]
        if not boxes: return self.begin(chip, hw, place)
        n = len(boxes) + 1
        word = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth")
        boxes.append({"chip": chip, "hw": hw, "place": place or f"The {word[min(n, 8) - 1]} box", "at": time.time()})
        self._keep(boxes=boxes, order=None)
        self.hub.log.add("roofline", chip, None, "joined", source="user", detail={"place": place})
        self._fold()
        return self.status()

    def leave(self, chip: str) -> None:
        """Forgetting a box takes it out of the Roofline and nothing else."""
        boxes = [b for b in self.boxes() if b["chip"] != chip]
        if len(boxes) == len(self.boxes()): return
        order = self.data.get("order")
        if order: order = [o for o in order if o["chip"] != chip] or None
        if boxes: self._keep(boxes=boxes, order=order)
        else: self.hub.settings.set(roofline={})
        self._sent.pop(chip, None)
        self._fold()

    def rename(self, chip: str, place: str) -> dict:
        place = " ".join(str(place or "").split())[:40]
        if not place: raise ValueError("Say where it is.")
        boxes = self.boxes()
        for b in boxes:
            if b["chip"] == chip: b["place"] = place
        self._keep(boxes=boxes)
        return self.status()

    # ---- one light on the wall ----
    def _fold(self) -> None:
        """Tell the house which lights are folded into the roofline's one tile, and rebuild."""
        home = getattr(self.hub, "home", None)
        if home is None or not hasattr(home, "folded"): return
        boxes = self.boxes()
        home.folded = {b["hw"]: boxes[0]["hw"] for b in boxes[1:] if b.get("hw")} if boxes else {}
        rebuild = getattr(self.hub, "rebuild_soon", None)
        if rebuild: rebuild()

    def lead(self):
        """The device the roofline's one tile is: the first box's light."""
        boxes = self.boxes()
        home = getattr(self.hub, "home", None)
        if not boxes or home is None: return None
        hw = boxes[0].get("hw")
        for d in home.devices.values():
            if d.hw == hw and d.capability == "light": return d
        return None

    def members(self, lead_id: str) -> list:
        """The other boxes' lights, which a tap on the roofline reaches as well."""
        lead = self.lead()
        if lead is None or lead.id != lead_id: return []
        hws = {b.get("hw") for b in self.boxes()[1:]}
        return [d for d in self.hub.home.devices.values() if d.hw in hws and d.capability == "light"]

    def parts(self) -> list[dict]:
        """Every run on the roof, box by box in the order they were set up: run 1, and run 2 where the
        controller has a strip on it."""
        strips = getattr(getattr(self.hub, "strip", None), "strips", {}) or {}
        out = []
        for b in self.boxes():
            s = strips.get(b["chip"], {})
            out.append({"chip": b["chip"], "run": 1, "count": s.get("count") or 0, "place": b["place"]})
            r2 = s.get("run2") or {}
            if r2.get("count"):
                out.append({"chip": b["chip"], "run": 2, "count": r2.get("count") or 0, "place": b["place"]})
        return out

    # ---- the way round (A, asked only when a chase is wanted) ----
    def wants_order(self) -> bool:
        """True when a chase is wanted and the house does not know the way round yet. Only a chase shows
        the seams; every other motion looks the same either way (design/roofline/NoneC.dc.html)."""
        return (self.exists() and not self.data.get("order") and len(self.parts()) > 1
                and self.look().get("motion") == "chase")

    async def yard_begin(self) -> dict:
        parts = self.parts()
        if len(parts) < 2: raise ValueError("A roofline of one run already goes the only way it can.")
        known = self.data.get("order")
        pre = known or guess(parts)
        self._yard = {"tapped": [dict(o) for o in pre], "step": "tapping"}
        await self._show_yard()
        return self.yard()

    def yard(self) -> dict | None:
        if not self._yard: return None
        parts = self.parts()
        colors = {(p["chip"], p["run"]): RUN_COLORS[i % len(RUN_COLORS)] for i, p in enumerate(parts)}
        tapped = self._yard["tapped"]
        pos = {(o["chip"], int(o["run"])): (i, o) for i, o in enumerate(tapped)}
        rows = []
        for p in parts:
            key = (p["chip"], p["run"])
            i, o = pos.get(key, (None, None))
            rows.append({"chip": p["chip"], "run": p["run"], "name": colors[key][0], "led": list(LED[colors[key][1]]),
                         "place": p["place"], "nth": i, "turned": bool(o and o.get("dir", 1) < 0)})
        return {"step": self._yard["step"], "rows": rows, "all": len(tapped) == len(parts)}

    async def yard_tap(self, chip: str, run: int) -> dict:
        """Tapped in the order they go round; tapped again, turned round."""
        if not self._yard: raise ValueError("Nobody is showing the roof which way round just now.")
        run = int(run)
        tapped = self._yard["tapped"]
        hit = next((o for o in tapped if o["chip"] == chip and int(o["run"]) == run), None)
        if hit: hit["dir"] = -int(hit.get("dir") or 1)
        elif any(p["chip"] == chip and p["run"] == run for p in self.parts()):
            tapped.append({"chip": chip, "run": run, "dir": 1})
        else: raise ValueError("That is not a part of this roofline.")
        self._yard["step"] = "tapping"
        await self._show_yard()
        return self.yard()

    async def yard_again(self) -> dict:
        if not self._yard: raise ValueError("Nobody is showing the roof which way round just now.")
        self._yard = {"tapped": [], "step": "tapping"}
        await self._show_yard()
        return self.yard()

    async def yard_done(self) -> dict:
        """That's all of them: one white light goes round the whole roof the way they said."""
        if not self._yard or len(self._yard["tapped"]) != len(self.parts()):
            raise ValueError("Tap every color first, in the order they go round.")
        self._yard["step"] = "done"
        await self._show_yard()
        return self.yard()

    def yard_keep(self) -> dict:
        if not self._yard or self._yard["step"] != "done": raise ValueError("Watch it go round first.")
        self._keep(order=[{"chip": o["chip"], "run": int(o["run"]), "dir": int(o.get("dir") or 1)} for o in self._yard["tapped"]])
        self._yard = None
        self.hub.log.add("roofline", "order", None, "kept", source="user")
        self._sent.clear()
        return self.status()

    def yard_leave(self) -> dict:
        self._yard = None
        self._sent.clear()
        return self.status()

    async def _show_yard(self):
        """What the roof shows while somebody is in the yard. While tapping, every run its own color with a
        white light running the way it goes; once done, one white light round the whole roof."""
        if not self._yard: return
        parts = self.parts()
        if self._yard["step"] == "done":
            lay = layout(parts, self._yard["tapped"])
            for chip in {p["chip"] for p in parts}:
                await self._send_async(chip, {"id": "round", "motion": "head", "colors": [list(LED["warm"])], "block": 1, "ms": 5400,
                                  "runs": lay[chip]}, force=True)
            return
        by_chip: dict[str, list] = {}
        colors = {(p["chip"], p["run"]): RUN_COLORS[i % len(RUN_COLORS)][1] for i, p in enumerate(parts)}
        dirs = {(o["chip"], int(o["run"])): int(o.get("dir") or 1) for o in self._yard["tapped"]}
        for p in parts:
            runs = by_chip.setdefault(p["chip"], [{"at": 0, "dir": 1}, {"at": 0, "dir": 1}])
            d = dirs.get((p["chip"], p["run"]), 1)
            n = int(p.get("count") or 1)
            runs[p["run"] - 1] = {"at": 0 if d > 0 else n - 1, "dir": d, "rgb": list(LED[colors[(p["chip"], p["run"])]])}
        for chip, runs in by_chip.items():
            await self._send_async(chip, {"id": "which-way", "motion": "head", "colors": [list(LED["white"])], "block": 1, "ms": 2600,
                              "runs": runs}, force=True)

    # ---- how it looks ----
    def showing(self, today: date | None = None) -> str | None:
        return occasion_on(today or datetime.now(self.hub.tz).date())

    def look(self, today: date | None = None) -> dict:
        """What the roof looks like now: a said draft while one is playing, else the occasion's, as kept or
        as drawn, held still if asked. On an ordinary evening, the household's own light (`off`)."""
        if self._draft and time.time() < self._draft_until:
            return look_of(self._draft.get("occasion"), self._draft, False)
        occ = self.showing(today)
        kept = (self.data.get("looks") or {}).get(occ or "") if occ else None
        return look_of(occ, kept, bool(self.data.get("still")))

    def hold_still(self, still: bool) -> dict:
        self._keep(still=bool(still))
        self._sent.clear()
        return self.status()

    # ---- C: a look, said ----
    def draft(self, occasion: str | None, look: dict, minutes: float = 5.0) -> dict:
        """Play a said look on the roof now. Kept only when told; walking away puts the roof back."""
        if not self.exists(): raise ValueError("There's no roofline to show it on.")
        occasion = occasion or self.showing()
        self._draft = {**look, "occasion": occasion}
        self._draft_until = time.time() + minutes * 60
        self._sent.clear()
        return {"occasion": occasion, "name": OCCASIONS.get(occasion or "", {}).get("name"), "look": look}

    def keep_draft(self) -> dict:
        if not self._draft: raise ValueError("Nothing is playing on the roof to keep.")
        occ = self._draft.get("occasion")
        if not occ: raise ValueError("Which occasion is it for? Say “Christmas: red and white, twinkling”.")
        looks = dict(self.data.get("looks") or {})
        looks[occ] = {k: self._draft[k] for k in ("colors", "motion", "block", "ms", "words") if k in self._draft}
        self._keep(looks=looks)
        self.hub.log.add("roofline", occ, None, "look kept", source="user", detail={"words": self._draft.get("words")})
        self._draft = None
        self._sent.clear()
        return self.status()

    def drop_draft(self) -> dict:
        self._draft = None
        self._sent.clear()
        return self.status()

    def forget_look(self, occasion: str) -> dict:
        """Back to ours for that occasion."""
        looks = dict(self.data.get("looks") or {})
        looks.pop(occasion, None)
        self._keep(looks=looks)
        self._sent.clear()
        return self.status()

    # ---- B: evenings ----
    def set_evenings(self, mode: str, until: str | None = None) -> dict:
        if mode not in EVENINGS: raise ValueError("Every evening, only in an occasion, or not by itself.")
        self._keep(evenings=mode, **({"until": _hhmm(until).strftime("%H:%M")} if until else {}))
        self.hub.log.add("roofline", "evenings", None, mode, source="user")
        return self.status()

    def dusk(self, day: date) -> datetime | None:
        loc = getattr(self.hub, "location", None)
        if not loc: return None
        start = datetime.combine(day, dtime(0, 0), tzinfo=self.hub.tz)
        _, set_ = sun.crossings(start, loc["lat"], loc["lon"], horizon=DUSK)
        return set_

    def evening(self, now: datetime) -> tuple[datetime, datetime] | None:
        """The latest evening to have begun -- last night's until tonight's dusk, so an end past midnight
        is still last night's -- as (dusk, end); tonight's if none has begun."""
        until = _hhmm(self.data.get("until") or UNTIL)
        found = []
        for day in (now.date() - timedelta(days=1), now.date()):
            d = self.dusk(day)
            if not d: continue
            end = datetime.combine(day, until, tzinfo=self.hub.tz)
            if end <= d: end += timedelta(days=1)       # "until 1:00" is after midnight, not before dusk
            found.append((d, end))
        begun = [e for e in found if e[0] <= now]
        return begun[-1] if begun else (found[-1] if found else None)

    def keeps_tonight(self, now: datetime) -> bool:
        mode = self.data.get("evenings")
        if mode == "every": return True
        if mode == "occasion": return occasion_on(now.date()) is not None
        return False

    def why(self, now: datetime, on: bool) -> str:
        """Why the roof is on or off right now, in one sentence. The wall can always answer this."""
        mode = self.data.get("evenings")
        if mode in (None, "never"):
            return "Its evenings are off, so it is a light like any other: on when somebody turns it on."
        ev = self.evening(now)
        occ = occasion_on(now.date())
        name = OCCASIONS.get(occ or "", {}).get("name")
        end = said_time(_hhmm(self.data.get("until") or UNTIL))
        if on and ev and ev[0] <= now < ev[1]:
            if name: return f"On at dusk because it keeps evenings. {name} is on in the house, so that is how it looks."
            return "On at dusk because it keeps evenings, in its everyday warm white. No occasion, no colors."
        if mode == "occasion" and not occ: return "No occasion tonight, and its evenings are only for occasions."
        if ev and now >= ev[1]: return f"Off at {end}, the end of its evenings."
        return f"It comes on at dusk and goes off at {end}."

    async def tick(self, now: datetime | None = None) -> str | None:
        """Every half minute: come on at dusk and go off at the end, if it keeps evenings; and keep each
        box's look and clock current. Returns what it did, for the tests.

        EDGES, NOT A STATE. It turns the roof on once each evening and off once, and in between leaves it
        alone -- so a household that switches it off at nine has switched it off, as with any porch light.
        The edges are written down by date, so a brain that restarts mid-evening neither lights a roof
        somebody put out nor forgets to put one out at eleven."""
        if not self.exists(): return None
        now = now or datetime.now(self.hub.tz)
        did = None
        lead = self.lead()
        ev = self.evening(now)
        if lead is not None and ev and self.keeps_tonight(ev[0]):
            dusk, end = ev
            tag = dusk.date().isoformat()
            d = self.data
            if dusk <= now < end and d.get("came_on") != tag:
                self._keep(came_on=tag, came_on_at=time.time())
                if lead.state != "on":
                    await self._switch(lead, "on")
                    did = "on"
                    self.hub.log.add("roofline", lead.id, "off", "on", source="evenings",
                                     detail={"why": self.why(now, True)})
            elif now >= end and d.get("came_on") == tag and d.get("went_off") != tag:
                self._keep(went_off=tag)
                if lead.state == "on":
                    await self._switch(lead, "off")
                    did = "off"
                    self.hub.log.add("roofline", lead.id, "on", "off", source="evenings")
        await self.send_looks()
        return did

    async def _switch(self, lead, action: str):
        act = getattr(self.hub, "act", None)
        if act: await act(lead, action, source="evenings")

    def came_on(self) -> dict | None:
        """The band's line for the roof coming on by itself, for an hour. The line is the undo."""
        d = self.data
        at = d.get("came_on_at")
        if not at or time.time() - at > 3600 or d.get("went_off") == d.get("came_on"): return None
        return {"at": at, "text": "The roofline came on at dusk"}

    # ---- telling the boxes ----
    async def send_looks(self, force: bool = False) -> None:
        """Each box its look and its place along the roof, said only when it changes -- and once a minute
        while something moves, which is also what keeps every box on the hub's clock."""
        if self._yard: return
        if self._draft and time.time() >= self._draft_until:
            self._draft = None            # walked away: the roof goes back to how it was
        look = self.look()
        lay = layout(self.parts(), self.data.get("order"))
        for chip in self.chips():
            body = {**look, "runs": lay.get(chip, [])}
            await self._send_async(chip, body, force)

    async def _send_async(self, chip: str, body: dict, force: bool = False):
        key = tuple(sorted((k, str(v)) for k, v in body.items()))
        moving = body.get("motion") not in ("off", "still")
        if not force and self._sent.get(chip) == key and (not moving or time.time() - self._sent_at.get(chip, 0) < 60):
            return
        self._sent[chip], self._sent_at[chip] = key, time.time()
        strip = getattr(self.hub, "strip", None)
        if strip is None: return
        now_ms = int(time.time() * 1000)
        import json
        await strip._tell(chip, "look/set", json.dumps({**body, "now": now_ms, "t0": 0}, separators=(",", ":")))

    def heard_online(self, chip: str) -> None:
        """A box that just arrived has forgotten its look: it is kept in memory, never in its storage."""
        self._sent.pop(chip, None)
        import asyncio
        try: asyncio.get_running_loop().create_task(self.send_looks())
        except RuntimeError: pass

    # ---- what the panel sees ----
    def status(self) -> dict:
        d = self.data
        if not d.get("boxes"): return {"exists": False}
        now = datetime.now(self.hub.tz)
        lead = self.lead()
        parts = self.parts()
        occ = self.showing()
        look = self.look()
        strips = getattr(getattr(self.hub, "strip", None), "strips", {}) or {}
        boxes = []
        for b in d["boxes"]:
            s = strips.get(b["chip"], {})
            runs = 2 if (s.get("run2") or {}).get("count") else 1
            boxes.append({"chip": b["chip"], "place": b["place"], "runs": runs, "online": bool(s.get("online")),
                          **(self.hub.strip.box_health(b["chip"]) if getattr(self.hub, "strip", None) else {})})
        ev = self.evening(now)
        lights = sum(int(p.get("count") or 0) for p in parts)
        order = d.get("order")
        return {
            "exists": True, "light": lead.id if lead else None, "boxes": boxes, "runs": len(parts), "lights": lights,
            "order": order, "turned": sum(1 for o in (order or []) if int(o.get("dir") or 1) < 0),
            # each run's lights, which the pane draws its length from (design/roofline/DrawnC.dc.html)
            "parts": [{"chip": p["chip"], "run": int(p["run"]), "count": int(p.get("count") or 0)} for p in parts],
            "ask_order": self.wants_order(), "yard": self.yard(),
            "evenings": d.get("evenings"), "evenings_words": EVENING_WORDS.get(d.get("evenings") or "", None),
            "until": d.get("until") or UNTIL, "until_words": said_time(_hhmm(d.get("until") or UNTIL)),
            "dusk": ev[0].isoformat(timespec="minutes") if ev else None,
            "still": bool(d.get("still")), "occasion": occ, "occasion_name": OCCASIONS.get(occ or "", {}).get("name"),
            "occasion_dates": dates_of(occ, now.year),
            "look": look, "words": self.words(occ, look),
            "kept": sorted((d.get("looks") or {}).keys()),
            "draft": ({"occasion": self._draft.get("occasion"), "words": self._draft.get("words")}
                      if self._draft and time.time() < self._draft_until else None),
            "why": self.why(now, bool(lead and lead.state == "on")), "came_on": self.came_on(),
        }

    def words(self, occ: str | None, look: dict) -> str | None:
        if not occ: return None
        kept = (self.data.get("looks") or {}).get(occ)
        base = (kept or OCCASIONS[occ]).get("words") or OCCASIONS[occ]["words"]
        return base.split(",")[0] + ", held still" if self.data.get("still") else base
