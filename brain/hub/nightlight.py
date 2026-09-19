# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A bridge's own light, lifted when somebody walks past it.

Step 5 of docs/puck-light.md, and the one that makes people like the thing. A puck settled in a
hallway glows warm all night at a level chosen to find a doorway by. The switches it bridges are
already reporting motion -- vendor field 0x13, polled by the puck and published as a binary_sensor
in the room -- so the house can swell that glow to something you can actually walk by as somebody
comes past, and let it settle again once they have gone.

WHY THIS IS NOT TWO RULES IN rules.json. The engine could express it: `motion on -> device on with
brightness`, then `idle 60 -> device on with brightness`. It was nearly built that way. Two rules
can be half-approved, half-edited and half-deleted, and every one of those halves leaves a bedroom
corridor at full brightness until somebody works out why. A swell and its settle are one behaviour
and belong to one object that cannot be taken apart.

WHY A LIFT IS NOT A BRIGHTNESS. It goes out on `night/lift/set`, which the firmware treats as
transient: it moves the light and touches neither NVS nor the retained state. Sent as an ordinary
brightness this would be two flash erases per walk-past for the life of the puck, and -- worse -- it
would drag the household's own brightness up and down in Home Assistant, where what they set is
supposed to be what it says. It also means the puck settles itself: a lift is forgotten on reboot,
so a brain that dies mid-swell cannot leave a light bright all night.

OFF BY DEFAULT, AND ASKED FOR NOWHERE ELSE. This is the part of the feature that can be wrong in a
way that wakes somebody up, so nothing turns it on but a person: it is a `switch` on the puck's own
Home Assistant device, next to its Nightlight, and it stays off until somebody flips it.
"""
import asyncio, json, logging

log = logging.getLogger("hub.nightlight")

BASE = "mesh"
HA_PREFIX = "homeassistant"

LIFT_TO = 255        # what "enough to walk by" is, against a nightlight that rests near 110
HOLD = 60            # seconds of quiet before it settles back. The switch's own motion hold is 20


class Nightlight:
    def __init__(self, hub, base: str = BASE):
        self.hub = hub
        self.base = base
        # Instance attributes, so a test can run a whole swell and settle in milliseconds.
        self.lift_to, self.hold = LIFT_TO, HOLD
        self._lifted: set[str] = set()
        self._settling: dict[str, asyncio.Task] = {}
        self._tasks: set[asyncio.Task] = set()

    # ---- the household's switch -------------------------------------------------

    def wants(self, chip: str) -> bool:
        return bool(((self.hub.settings.get("bridges") or {}).get(chip) or {}).get("lift"))

    def on_command(self, chip: str, payload: str) -> bool:
        """`mesh/bridge/<chip>/motion/set`, from hub.bridge's one subscription.

        Synchronous on purpose: the setting is written here and now, so a hub that is restarted a
        moment later still has it. Only the answer on the broker needs a loop."""
        mine = dict(self.hub.settings.get("bridges") or {})
        if chip not in mine: return False
        on = payload.strip().upper() in ("ON", "1", "TRUE", "YES")
        mine[chip] = {**(mine[chip] or {}), "lift": on}
        self.hub.settings.set(bridges=mine)
        self._try(self._said(chip))
        if not on: self._try(self._settle_now(chip))
        return True

    async def announce(self, chip: str) -> None:
        """One switch, on the device the puck already owns in Home Assistant.

        Published by the brain rather than by the puck because the brain is what does the work: the
        motion sensors, the rooms and the timer are all here, and a flag the firmware would only
        store and never read is a flag in the wrong place."""
        topic = f"{HA_PREFIX}/switch/{self.base}_bridge_{chip}_motion/config"
        await self._pub(topic, json.dumps({
            "name": "Lift on motion",
            "uniq_id": f"{self.base}_bridge_{chip}_motion",
            "obj_id": f"{self.base}_bridge_{chip}_motion",
            "stat_t": f"{self.base}/bridge/{chip}/motion",
            "cmd_t": f"{self.base}/bridge/{chip}/motion/set",
            "avty_t": f"{self.base}/bridge/{chip}/status",
            "ent_cat": "config",
            "ic": "mdi:motion-sensor",
            "dev": {"ids": [f"{self.base}_bridge_{chip}"]},
        }), retain=True)
        await self._said(chip)

    # ---- the behaviour ----------------------------------------------------------

    def on_state(self, dev, old) -> None:
        """A device moved. Only motion turning on, and only in a room a bridge of ours is in."""
        if dev.capability != "motion" or dev.state != "on" or old == dev.state: return
        for chip in self._pucks_in(dev.room_id):
            self._try(self._lift(chip))

    def _pucks_in(self, room_id: str | None) -> list[str]:
        """Which bridges this motion is about. Four things have to be true, and the last two are why
        a house full of pucks does not light up every time somebody crosses the hall."""
        b = getattr(self.hub, "bridge", None)
        if not (room_id and b): return []
        out = []
        for chip, p in b.pucks.items():
            if not p.get("online"): continue          # nothing to talk to
            if not p.get("night"): continue           # its nightlight is off: there is nothing to lift
            if not self.wants(chip): continue         # nobody asked for this
            if b.room_of(chip) != room_id: continue   # and it is not in this room
            out.append(chip)
        return out

    async def _lift(self, chip: str) -> None:
        if chip not in self._lifted:
            self._lifted.add(chip)
            await self._pub(f"{self.base}/bridge/{chip}/night/lift/set", str(self.lift_to))
        # Whether or not it was already up, somebody is still there: the clock starts again.
        old = self._settling.pop(chip, None)
        if old and not old.done(): old.cancel()
        self._settling[chip] = self._spawn(self._after(chip))

    async def _after(self, chip: str) -> None:
        try: await asyncio.sleep(self.hold)
        except asyncio.CancelledError: return
        await self._settle_now(chip)

    async def _settle_now(self, chip: str) -> None:
        t = self._settling.pop(chip, None)
        if t and not t.done(): t.cancel()
        if chip not in self._lifted: return
        self._lifted.discard(chip)
        # 0 is "back to whatever they chose", which the puck holds and we deliberately do not.
        await self._pub(f"{self.base}/bridge/{chip}/night/lift/set", "0")

    # ---- plumbing ---------------------------------------------------------------

    async def _said(self, chip: str) -> None:
        await self._pub(f"{self.base}/bridge/{chip}/motion", "ON" if self.wants(chip) else "OFF", retain=True)

    async def _pub(self, topic: str, payload: str, retain: bool = False) -> None:
        try:
            await self.hub.ha.call("mqtt", "publish", None, topic=topic, payload=payload, retain=retain)
        except Exception as e:
            log.warning("nightlight: %s did not go out: %s", topic, e)

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    def _try(self, coro) -> None:
        """Called from synchronous places that may or may not be inside the loop."""
        try: self._spawn(coro)
        except RuntimeError: coro.close()
