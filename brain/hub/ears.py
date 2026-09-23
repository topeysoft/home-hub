# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who can hear a strip knocking.

A hub goes where the Ethernet is and a strip goes where the light is wanted, and Bluetooth does not
cross that (docs/strip.md item 15). So the hub is not the only ear any more: every bridge puck listens,
passively and all day, for a strip's commissionable advertisement, and says what it heard. This keeps
the table -- which strip, heard by which ear, how loud, how recently -- and answers the one question
the rest of the brain asks of it: WHO CAN HEAR THIS, loudest first. The hub's own radio is one ear
among them, named "hub", which is why one puck today and every powered thing of ours later is the
same code rather than a second design (design/ears/, direction A built so that B is a longer list).

WHAT A PUCK SAYS, and it is deliberately dumb. On `mesh/bridge/<chip>/heard`, not retained:

    {"addr": "e7:38:84:e2:89:0a", "type": "random", "rssi": -37, "svc": "00000ff1ff008000"}

`svc` is the raw service data of the 0xFFF6 advertisement it heard, as hex. The puck does not decode
it: the hub already has one decoder it trusts (`strip.commissionable`, checked against a real device),
and two decoders that disagree is how a strip gets called somebody else's. `type` travels with the
address because the address is useless without it -- a strip's is random, and opening it as public
is six right bytes nobody answers, which cost a morning on 23 September (docs/strip.md item 42).

HOW OFTEN. A puck hears a knocking strip about twice a second, and that is not worth a message
each: it says so when it first hears an address, again at most every REPORT_EVERY seconds, and sooner
if the loudness has moved by LOUDER dB. Anything not heard again within FRESH is forgotten, which is
also how a strip that has been taken leaves the table: it stops knocking, and nothing has to say so.

A knock that only a bridge heard is announced like any other (`knocking`, read by strip.look), and
setup then runs as an errand on the bridge `choose` names (hub/errand.py, docs/strip.md item 45).
"""
import json, time

from .strip import FAINT, TEST_VID, commissionable

REPORT_EVERY = 10.0
LOUDER = 6
FRESH = 30.0
# How much louder a puck has to be before it is worth a courier. The hub's own radio has no hop, no
# second link and no buffers to fill, so a puck that is merely as loud is not better -- only one that
# is clearly louder while the hub is past the edge item 15 measured.
MARGIN = 6
# NOT A READING: NimBLE on an ESP32 hands back -8 dBm for some adverts from a strip that reads -37
# either side of them, and that loud is only possible with the antennas touching. A puck discards
# these itself (ear.cpp); this is the same rule on the side that ranks, for any puck that does not.
LOUDEST_REAL = -15


def _addr(a: str) -> str:
    return (a or "").strip().upper()


class Ears:
    def __init__(self):
        # addr -> ear -> {"rssi", "at", "type", "what"}
        self._heard: dict[str, dict[str, dict]] = {}

    def heard(self, ear: str, addr: str, rssi: int | None, kind: str = "random",
              what: dict | None = None, now: float | None = None) -> None:
        """One ear heard one strip. `what` is the decoded advertisement, when there was one."""
        a = _addr(addr)
        if not a or not ear:
            return
        self._heard.setdefault(a, {})[ear] = {
            "rssi": rssi, "at": time.time() if now is None else now,
            "type": kind or "random", "what": what or {}}

    def from_puck(self, chip: str, payload: str, now: float | None = None) -> bool:
        """A puck's report, as it arrives off the broker. False for anything that is not a knock of
        ours -- somebody's plug in pairing mode is a Matter advertisement too, and is not our business."""
        try:
            body = json.loads(payload)
            what = commissionable(bytes.fromhex(body["svc"]))
            rssi = int(body["rssi"])
        except Exception:
            return False
        if not what or what["vendor"] != TEST_VID or rssi >= LOUDEST_REAL:
            return False
        self.heard(chip, body.get("addr", ""), rssi, body.get("type") or "random", what, now)
        return True

    def who_can_hear(self, addr: str, now: float | None = None) -> list[dict]:
        """Every ear that has heard this strip lately, loudest first."""
        now = time.time() if now is None else now
        ears = self._heard.get(_addr(addr), {})
        fresh = [{"ear": e, "rssi": h["rssi"], "type": h["type"], "age": now - h["at"]}
                 for e, h in ears.items() if now - h["at"] <= FRESH]
        return sorted(fresh, key=lambda h: -(h["rssi"] if h["rssi"] is not None else -127))

    def choose(self, addr: str, now: float | None = None) -> str | None:
        """Which ear should talk to this strip: "hub", a puck's chip, or None if nobody can hear it.

        THE HUB'S OWN RADIO WHEREVER IT IS GOOD ENOUGH. Inside FAINT a session through it establishes
        first time (item 15), and it needs no courier, so it wins however loud a puck is. Past FAINT, a
        puck that is louder by MARGIN is worth the hop; anything less is not, because the hop has a
        cost of its own (items 38 and 40) and a puck that is barely louder is barely better."""
        heard = self.who_can_hear(addr, now)
        if not heard:
            return None
        hub = next((h for h in heard if h["ear"] == "hub"), None)
        hub_rssi = hub["rssi"] if hub and hub["rssi"] is not None else None
        if hub_rssi is not None and hub_rssi >= FAINT:
            return "hub"
        pucks = [h for h in heard if h["ear"] != "hub" and h["rssi"] is not None]
        if pucks and (hub_rssi is None or pucks[0]["rssi"] >= hub_rssi + MARGIN):
            return pucks[0]["ear"]
        return "hub" if hub else (pucks[0]["ear"] if pucks else None)

    def knocking(self, now: float | None = None) -> list[dict]:
        """Every strip a BRIDGE has heard lately, at the loudest bridge that heard it -- the knocks the
        hub's own radio may never reach. The hub's own sightings are left out: it announces those itself."""
        now = time.time() if now is None else now
        out = []
        for a, ears in self._heard.items():
            best = None
            for e, h in ears.items():
                if e == "hub" or now - h["at"] > FRESH:
                    continue
                if best is None or (h["rssi"] if h["rssi"] is not None else -127) > \
                        (best[1]["rssi"] if best[1]["rssi"] is not None else -127):
                    best = (e, h)
            if best:
                out.append({"addr": a, "ear": best[0], "rssi": best[1]["rssi"],
                            "type": best[1]["type"], "what": best[1]["what"]})
        return out

    def forget_stale(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        for a in list(self._heard):
            ears = {e: h for e, h in self._heard[a].items() if now - h["at"] <= FRESH}
            if ears: self._heard[a] = ears
            else: del self._heard[a]
