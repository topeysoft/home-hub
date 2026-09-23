# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Taking a strip through a puck, when the hub cannot hear it.

A hub goes where the Ethernet is and a strip goes where the light is wanted (docs/strip.md item 15).
When the ears table says a puck hears a strip better than the hub does (hub/ears.py), setup runs as
an ERRAND: this hands each protocomm request to that puck over MQTT, the puck writes it to the strip
and hands back what came out (brilliant/esp32-bridge/src/errand.h). It is a `Transport` like
strip_door's own, so `strip_door.adopt()` runs unchanged above it -- the SRP6a session is still
opened here and closed at the strip, the puck carries ciphertext it has no key for, and the press is
still checked on the strip (items 38, 39 and 44).

THE WORDS ARE THE PUCK'S, and they are text because this is the only way in: the brain publishes
through Home Assistant's `mqtt.publish` and hears through its websocket, both of which carry
strings. Opaque bytes travel as base64.

    mesh/bridge/<chip>/errand/ask    open <id> <addr> <random|public>
                                     send <id> <n> <ep> <base64>
                                     close <id>
    mesh/bridge/<chip>/errand/tell   open <id> ring|quiet     ok <id> <n> <base64>
                                     fail <id> <n|-> <why>    ring <id>    closed <id> <why>

Answers arrive through the subscription the bridge already holds (`mesh/#`), which hands every
`errand/tell` line to `hub.errand` -- the one errand running, because strips are set up one at a time.
"""
import asyncio, base64, logging, secrets

from .strip_door import Transport   # strip_door is the one module that puts brain/vendor on the path

log = logging.getLogger("hub")

BASE = "mesh"
OPEN_WAIT = 30.0      # a connect is ten seconds at most on the puck; this is its answer getting back
SEND_WAIT = 20.0      # the slowest exchange measured through a puck was under seven seconds (item 40)

# What a puck says when it cannot, in the sentence strip.py will say to a household. Every one of them
# is the radio's side of things, never the strip's: the strip refusing is a `fail ... write` below,
# and strip_door decides what that means just as it would on the hub's own radio.
WHY = {
    "busy": "the bridge is already setting something else up",
    "connect": "the bridge could not reach the strip",
    "nodoor": "that strip did not offer our door",
    "gone": "the bridge lost the strip",
    "idle": "the bridge gave up waiting",
    "lost": "the bridge lost the strip",
}


class ErrandFailed(Exception):
    """The puck could not do what it was asked. `why` is its own word for it."""
    def __init__(self, why: str):
        self.why = why
        super().__init__(WHY.get(why, f"the bridge said {why}"))


class Errand(Transport):
    def __init__(self, hub, chip: str):
        self.hub, self.chip = hub, chip
        self.id = secrets.token_hex(4)
        self.n = 0
        self.waiting: dict[str, asyncio.Future] = {}
        self.can_ring = False
        self._rung = asyncio.Event()
        self.closed: str | None = None

    async def _ask(self, line: str) -> None:
        await self.hub.ha.call("mqtt", "publish", None,
                               topic=f"{BASE}/bridge/{self.chip}/errand/ask", payload=line, retain=False)

    def _await(self, key: str) -> asyncio.Future:
        fut = asyncio.get_running_loop().create_future()
        self.waiting[key] = fut
        return fut

    def on_tell(self, line: str) -> None:
        """One line off `errand/tell`. Anything carrying another id is somebody else's -- or an old
        errand of ours whose answer arrived late -- and is not taken for this one's."""
        words = str(line).split(" ")
        if len(words) < 2 or words[1] != self.id:
            return
        verb = words[0]
        if verb == "open":
            self._settle("open", ("open", words[2] if len(words) > 2 else "quiet"))
        elif verb == "ok" and len(words) >= 3:
            self._settle(words[2], ("ok", words[3] if len(words) > 3 else ""))
        elif verb == "fail" and len(words) >= 4:
            self._settle("open" if words[2] == "-" else words[2], ("fail", words[3]))
        elif verb == "ring":
            self._rung.set()
        elif verb == "closed":
            self.closed = words[2] if len(words) > 2 else "?"
            # Whatever is waiting will not be answered now; say so rather than let it time out.
            for key in list(self.waiting):
                self._settle(key, ("fail", self.closed))

    def _settle(self, key: str, value) -> None:
        fut = self.waiting.pop(key, None)
        if fut and not fut.done():
            fut.set_result(value)

    async def open(self, addr: str, kind: str = "random") -> bool:
        """Have the puck link to the strip. Returns whether the strip can ring."""
        fut = self._await("open")
        await self._ask(f"open {self.id} {addr.lower()} {kind or 'random'}")
        try:
            verb, said = await asyncio.wait_for(fut, OPEN_WAIT)
        except TimeoutError:
            self.waiting.pop("open", None)
            raise ErrandFailed("silent")
        if verb != "open":
            raise ErrandFailed(said)
        self.can_ring = said == "ring"
        log.info("errand %s: %s linked to %s, %s", self.id, self.chip, addr,
                 "and it can ring" if self.can_ring else "and it cannot ring")
        return self.can_ring

    async def send_data(self, ep_name: str, data: str) -> str:
        from .strip_door import ENDPOINTS
        self.n += 1
        n = str(self.n)
        fut = self._await(n)
        body = base64.b64encode(data.encode("latin-1")).decode()
        await self._ask(f"send {self.id} {n} 0x{ENDPOINTS[ep_name]:04x} {body}")
        try:
            verb, said = await asyncio.wait_for(fut, SEND_WAIT)
        except TimeoutError:
            self.waiting.pop(n, None)
            raise ErrandFailed("silent")
        if verb != "ok":
            # A refused write is the strip saying no, carried faithfully: strip_door reads it the way
            # it reads an ATT error on its own radio, which is what it is.
            raise ErrandFailed(said)
        return base64.b64decode(said).decode("latin-1") if said else ""

    async def send_session_data(self, data):
        return await self.send_data("prov-session", data)

    async def send_config_data(self, data):
        return await self.send_data("prov-config", data)

    async def listen_for_ring(self) -> bool:
        return self.can_ring

    async def wait_for_ring(self):
        await self._rung.wait()
        self._rung.clear()

    async def close(self) -> None:
        if self.closed is None:
            self.closed = "asked"
            try: await self._ask(f"close {self.id}")
            except Exception as e: log.info("errand %s: close did not go (%s)", self.id, e)

    async def disconnect(self):
        await self.close()
