# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A light strip arriving, and the two questions only a strip has to be asked.

A strip is the first thing this house adopts that is neither a bridge nor already in a wall. It
comes in a box, gets taped behind a television or under a shelf, and is plugged into a socket
nowhere near the hub -- so it is never carried to the cable. It leaves the factory flashed and
knocks over Bluetooth the moment it has power, which is design/strip/ direction A and the shape
design/puck/Knock.dc.html argued for and lost on one line: "it only works on a bridge that already
has firmware on it". A product we ship is flashed. That objection is gone.

The machine is what the panel draws, so what it holds is the sequence a person sees:

    none      nothing to say
    knocking  a strip is advertising and nobody has said it is theirs. Nothing of the house's has
              gone anywhere -- saying it is not yours needs no code, because refusing gives nothing
              away. The identity check is the object: it is lit, and no serial number is shown
    working   `step` is wifi | hub, in that order. Two steps, not the bridge's three: the software
              is already on it, which is the whole reason it could knock
    order     which color comes out first (below). The strip is lit and the household names it
    length    it fills from the plug end and somebody taps when the far end lights
    room      the ordinary room chips every new device gets
    ready     it is an ordinary light from here: the tile, the colors, the schedules, "everything off"
    failed    `text` says why, in words for the wall

Two things a bridge has that a strip does not, and both are absences worth keeping in mind. There
is no mesh, so no keys step. And there is no walk to find it a socket, so the placing instrument --
blinking amber, steady green, breathing red -- has nothing to answer here. That matters for more
than setup: docs/puck-light.md puts a fault ABOVE a puck's light because a puck that glows while its
bridge is down is furniture that lies. A strip is the opposite case. The household is watching a
film, and a strip that turns amber mid-scene because the broker blinked is the product breaking,
not reporting. So a strip keeps whatever the household set it to, and the panel carries the fault.

The radio is behind `Radio` for the same reason bridge.py hides pyserial behind `Cable`: the machine
is tested with a fake one, and nothing in here needs a strip on a desk to run.
"""
import asyncio, json, logging, re, time

log = logging.getLogger("hub.strip")

BASE = "strip"
STEPS = ("wifi", "hub")

# How long to wait on a strip for each kind of question. Named so the tests can shrink them: a suite
# that waits out a real timeout teaches people to skip it.
JOIN_WAIT = 60
ANSWER_WAIT = 10

# A strip nobody has told how long it is. The controller writes this many lights every frame and the
# surplus falls off the end of the wire, so a strip shorter than this is simply right -- which is
# what makes direction C on the canvas a real argument rather than a shortcut. We ask anyway, because
# anything that needs to know where the MIDDLE is comes out wrong without it.
ASSUMED = 300
MOST = 1200


# ---------------------------------------------------------------- the order the colors come in

# The six orderings in circulation, written as the order the three bytes go out on the wire. WS2812B
# is "grb" and is most of what anybody owns; WS2811 and APA106 are "rgb"; the rest are clones.
ORDERS = ("rgb", "rbg", "grb", "gbr", "brg", "bgr")
ASSUME = "grb"
NAMES = {"r": "red", "g": "green", "b": "blue"}


def probe(assume: str = ASSUME) -> tuple[int, int, int]:
    """The three bytes that are RED on a strip that really is `assume`.

    Not (255, 0, 0). We are asking "is my guess right", so we send what red WOULD be under the guess
    and let the household tell us what came out. On a strip that is what we assumed, they see red and
    there is one tap in the whole business."""
    i = assume.index("r")
    return tuple(255 if k == i else 0 for k in range(3))


def lit_index(assume: str = ASSUME) -> int:
    """Which byte of `probe()` is the loud one -- and so which channel position the answer names."""
    return assume.index("r")


def narrow(seen: str, at: int, among=ORDERS) -> list[str]:
    """The orderings still possible once somebody has named the color they can see.

    `seen` is 'r', 'g' or 'b' and `at` is the byte we made loud. The channel they named IS the one
    that byte drives, so every ordering that puts a different channel there is out. Two of these
    settle all six, because the first answer leaves a pair and the second splits it."""
    return [o for o in among if o[at] == seen]


def resolve(first: str, second: str | None = None) -> str | None:
    """The ordering, from one answer or two. None while it is still ambiguous.

    ONE TAP IS A PRIOR, NOT A PROOF, and this is the one place in the file where that is true.
    Answering "yes, red" to the first question leaves "grb" and "brg" both possible -- the second
    byte drives red in each -- and we take "grb", because it is what almost every 5 V strip on sale
    actually is. A household with the other one sees wrong colors and has a row on the light's own
    pane that asks the question again (design/strip/Later.dc.html). That row is not a nicety; it is
    the other half of this shortcut, and the shortcut is not honest without it."""
    left = narrow(first, lit_index())
    if len(left) == 1: return left[0]
    if first == "r" and second is None: return ASSUME        # the common strip, taken on its odds
    if second is None: return None
    # The second question makes red the FIRST byte, which splits whichever pair is left.
    left = narrow(second, 0, among=left)
    return left[0] if len(left) == 1 else None


class StripError(RuntimeError):
    """A failure whose message was written for the person standing in front of the panel.

    Everything else in here was written for a log -- a library's words, a timeout, whatever bleak felt
    like saying. Those must not reach a screen. bridge.py learned this the expensive way: a bridge
    once failed with "database is locked" on the wall, which tells nobody anything and was not even
    true about their bridge."""


class Radio:
    """Getting a strip onto the house's Wi-Fi. It is Matter commissioning, and that is the point.

    THIS USED TO BE OUR OWN BLE PROTOCOL AND THAT WAS A MISTAKE. It took the household's Wi-Fi
    password over an unauthenticated link, where anything in radio range during setup could read it.
    Matter's commissioning is PASE with SPAKE2+ and then CASE, in a stack a great many people have
    looked at -- so the firmware moved to it (strip/firmware/), and the side effect is that every
    strip we make also works with Apple Home, Google Home and Alexa with no hub of ours in the house
    at all.

    So this class has one job and it is a small one: notice a commissionable strip, and hand it to
    the commissioner the house already runs (matter-server, in the compose file -- docs/matter.md).
    It does NOT carry Wi-Fi credentials any more, and must never be given a route that does.

    Once a strip is commissioned it is a Matter light and the ecosystem drives it. Everything else in
    this file -- the color question, the fill -- goes over the broker, because the Enhanced Color
    Light cluster is one color for the whole fitting and has no concept of a pixel.

    NOTHING IN THIS CLASS HAS RUN AGAINST HARDWARE, and the commissioning half is not written at all:
    see docs/strip.md, which also has the one question Matter forces and nobody has answered yet."""

    def __init__(self, adapter: str | None = None):
        self.adapter = adapter

    async def _bleak(self):
        try:
            import bleak
        except ModuleNotFoundError:
            raise StripError("This hub has no Bluetooth to set a light strip up with.")
        return bleak

    async def scan(self, seconds: float = 4.0) -> list[dict]:
        """Every strip advertising that it has never been commissioned: [{"id", "addr", "rssi"}].

        TWO NAMES FOR ONE THING, and they are not interchangeable. `addr` is the Bluetooth address,
        which is how you connect to it and nothing else -- on a Mac it is not even a MAC, and on any
        host it can change. `id` is the chip, which the strip puts in its advertised name and then
        uses for every one of its MQTT topics for the rest of its life. Using the address as the id
        would work right up until the first strip was set up, and then the hub would be listening on
        a topic the strip never publishes to.

        A strip that HAS been set up does not advertise at all, which is the whole of the answer to
        "what happens when the router reboots". It keeps the light the household asked for, cycles
        the two Wi-Fi keys it holds, and stays quiet. Opening a pairing window on an event that
        happens several times a year, with nobody present and nobody told, would be a security
        posture set by somebody else's firmware updates."""
        bleak = await self._bleak()
        found = []
        for d, adv in (await bleak.BleakScanner.discover(timeout=seconds, return_adv=True)).values():
            name = adv.local_name or ""
            if not name.startswith("hub-strip-"): continue
            found.append({"id": name[len("hub-strip-"):], "addr": d.address, "rssi": adv.rssi})
        # A commissionable Matter device also advertises service 0xFFF6 with its discriminator, which
        # is how this should find one rather than by our name prefix. What that advertisement does NOT
        # carry is the passcode, and commissioning cannot happen without it -- which is the open
        # question at the foot of docs/strip.md and the reason this is still matching on a name.
        return sorted(found, key=lambda s: -(s["rssi"] or -127))

    async def join(self, addr: str, cfg: dict) -> dict:
        """Commission it onto the house's fabric. `cfg` no longer carries Wi-Fi: the commissioner
        does that over a channel that is encrypted, which is the whole reason this changed."""
        raise StripError("Commissioning a light strip is not built yet.")

    async def forget(self, id: str) -> None:
        return None


class Strips:
    """One job at a time, because it is a person standing in front of a thing."""

    def __init__(self, hub, radio: Radio | None = None):
        self.hub = hub
        self.radio = radio or Radio()
        self.job: dict | None = None
        self._sub: int | None = None
        self._dismissed: set[str] = set()      # "not mine": left alone until it is power-cycled
        self.strips: dict[str, dict] = {}      # what the broker says: id -> {"online", "count", "order"}
        self._heard: dict[str, dict] = {}      # the last retained value per (id, leaf)
        self._woke: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    # ---- what the panel sees ----
    def status(self) -> dict:
        base = {"strips": sum(1 for s in self.strips.values() if s.get("online"))}
        if not self.job: return {**base, "state": "none"}
        j = self.job
        out = {**base, "state": j["state"], "name": j.get("label") or "A light strip"}
        if j["state"] == "working": out["step"] = j["step"]
        if j["state"] == "order":
            # Which question is on screen: the first is a yes/no, the second is the three primaries.
            out["asking"] = "red" if j.get("first") is None else "which"
        if j["state"] == "length": out["lit"] = j.get("lit", 0)
        if j["state"] in ("room", "ready"):
            out["count"] = j.get("count", ASSUMED); out["order"] = j.get("order", ASSUME)
            out["white"] = bool(j.get("white"))
        if j["state"] == "room": out["rooms"] = self._rooms()
        if j.get("text"): out["text"] = j["text"]
        if j.get("needs"): out["needs"] = j["needs"]
        return out

    def _rooms(self) -> list:
        home = getattr(self.hub, "home", None)
        rooms = getattr(home, "rooms", None) or []
        return [{"id": getattr(r, "id", None) or r["id"], "name": getattr(r, "name", None) or r["name"]}
                for r in rooms]

    def _set(self, state, **more):
        if not self.job: return
        self.job.update(state=state, **more)
        self.hub._broadcast(json.dumps({"type": "strip", "strip": self.status()}))

    def _fail(self, text: str) -> dict:
        self._set("failed", text=text)
        return self.status()

    # ---- the broker: strips the house already has ----
    async def listen(self):
        try:
            self._sub = await self.hub.ha.subscribe("mqtt/subscribe", self._on_mqtt, topic=f"{BASE}/#")
        except Exception as e:
            log.info("strip: no broker view yet (%s)", e)

    def _on_mqtt(self, ev):
        topic = (ev or {}).get("topic") or ""
        payload = (ev or {}).get("payload")
        parts = topic.split("/")
        if len(parts) < 3 or parts[0] != BASE: return
        id_, leaf = parts[1], "/".join(parts[2:])
        self._heard[f"{id_}/{leaf}"] = payload
        s = self.strips.setdefault(id_, {})
        if leaf == "status": s["online"] = str(payload).strip() == "online"
        elif leaf == "count":
            try: s["count"] = int(str(payload).strip())
            except ValueError: pass
        elif leaf == "order": s["order"] = str(payload).strip()
        # A fill that has reached the end says so itself, so the panel can stop asking somebody to
        # watch a thing that has finished happening.
        if self.job and self.job.get("id") == id_ and leaf == "fill":
            try: self._set("length", lit=int(str(payload).strip()))
            except ValueError: pass
        if self._woke and not self._woke.is_set(): self._woke.set()

    async def _tell(self, id_: str, leaf: str, payload: str, retain: bool = False) -> None:
        try:
            await self.hub.ha.call("mqtt", "publish", {},
                                   topic=f"{BASE}/{id_}/{leaf}", payload=payload, retain=retain)
        except Exception as e:
            log.info("strip %s: could not say %s (%s)", id_, leaf, e)

    async def _ask(self, id_: str, leaf: str, payload: str, want: str, timeout: float) -> str | None:
        """Say something and wait for the strip's own answer on `want`. None if it never came."""
        self._heard.pop(f"{id_}/{want}", None)
        self._woke = asyncio.Event()
        await self._tell(id_, leaf, payload)
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            got = self._heard.get(f"{id_}/{want}")
            if got is not None: return str(got)
            try: await asyncio.wait_for(self._woke.wait(), timeout=max(0.01, end - time.monotonic()))
            except asyncio.TimeoutError: break
            self._woke.clear()
        return self._heard.get(f"{id_}/{want}")

    # ---- the knock ----
    async def watch(self, every: float = 20.0):
        """Look for a strip that is knocking, for as long as the brain is up.

        Not often, and never while a job is running. A BLE scan is a radio going quiet for other
        things, and the hub is also the Bluetooth end of every OTHER device the house has; a scan
        loop tight enough to feel instant is a scan loop that costs the house something all day, to
        catch an event that happens when somebody plugs a thing in and is standing right there."""
        while True:
            try:
                if not self.job: await self.look()
            except Exception as e:
                log.info("strip: look failed (%s)", e)
            await asyncio.sleep(every)

    async def look(self) -> dict:
        """One scan. A strip that is advertising has never been set up, so anything found is a knock."""
        if self.job: return self.status()
        try: found = await self.radio.scan()
        except StripError as e: return {**self.status(), "text": str(e)}
        except Exception as e:
            log.info("strip: scan failed (%s)", e); return self.status()
        for s in found:
            if s["id"] in self._dismissed: continue
            self.job = {"state": "knocking", "id": s["id"], "addr": s.get("addr") or s["id"],
                        "label": self._label(s), "first": None}
            self._set("knocking")
            break
        return self.status()

    @staticmethod
    def _label(s: dict) -> str:
        """What to call it before anybody has named it. Never the address: a household that is shown
        a MAC has been handed the inside of the product, and there is nothing to disambiguate anyway
        -- the thing is two meters of light and it is the only one lit."""
        return "A light strip"

    async def dismiss(self) -> dict:
        """Not mine. Needs no code: refusing gives nothing away, and nothing was ever sent."""
        if self.job: self._dismissed.add(self.job["id"])
        self.job = None
        self.hub._broadcast(json.dumps({"type": "strip", "strip": self.status()}))
        return self.status()

    async def adopt(self) -> dict:
        """Yes, that's mine. The first moment anything of the house's moves."""
        if not self.job or self.job["state"] != "knocking":
            raise StripError("There is no light strip waiting to be let in.")
        wifi = (self.hub.settings.get("wifi") or {}) if hasattr(self.hub, "settings") else {}
        if not wifi.get("ssid"):
            return self._needs_wifi()
        self._set("working", step="wifi")
        self._task = asyncio.create_task(self._setup(dict(wifi)))
        return self.status()

    def _needs_wifi(self) -> dict:
        self._set("working", step="wifi", needs="wifi")
        return self.status()

    async def wifi(self, ssid: str, password: str) -> dict:
        """The one thing a hub cannot know for a strip it has never met: asked once, and kept."""
        if not ssid: raise StripError("Which Wi‑Fi? The name is needed.")
        self.hub.settings.set(wifi={"ssid": ssid, "pass": password})
        if not self.job: return self.status()
        self._set("working", step="wifi", needs=None)
        self._task = asyncio.create_task(self._setup({"ssid": ssid, "pass": password}))
        return self.status()

    async def _setup(self, wifi: dict):
        j = self.job
        if not j: return
        try:
            cfg = {"ssid": wifi.get("ssid"), "pass": wifi.get("pass"),
                   "host": getattr(self.hub, "hostname", None) or "hub",
                   "user": (getattr(self.hub, "env", {}) or {}).get("MQTT_USER") or "hub",
                   "mqtt_pass": (getattr(self.hub, "env", {}) or {}).get("MQTT_PASSWORD") or "",
                   "base": BASE}
            await self.radio.join(j["addr"], cfg)
            self._set("working", step="hub")
            # It is on the Wi-Fi now, so everything after this goes over the broker. Wait for it to
            # say so itself rather than assuming: a strip that joined and cannot find the hub is a
            # different failure from one that never joined, and the household can fix only one of them.
            got = await self._ask(j["id"], "hello", "1", want="status", timeout=JOIN_WAIT)
            if str(got or "").strip() != "online":
                return self._fail("It joined your Wi‑Fi but never found the hub. Try it nearer the router.")
            await self._show_red()
        except StripError as e:
            self._fail(str(e))
        except Exception as e:
            log.exception("strip setup failed")
            self._fail("Setting that light strip up did not work. Unplug it and try again.")

    # ---- the order the colors come in ----
    async def _show_red(self):
        j = self.job
        r, g, b = probe()
        # `raw`, not a color: these three bytes go out exactly as given. Putting them through the
        # strip's mapping would be applying the very guess the question exists to test, and the
        # firmware refuses to do it for that reason (strip/firmware/src/pixels.h, raw3).
        await self._tell(j["id"], "show/set", f"raw {r} {g} {b}")
        self._set("order", first=None)

    async def saw(self, what: str) -> dict:
        """What the household can see on the strip right now.

        'red' | 'green' | 'blue' answer the color question. 'stripes' is the fourth choice on the
        board and answers a completely different question: a three-byte frame sent to a strip that
        carries a separate white channel misaligns by a byte a pixel and comes out as a candy-stripe
        rather than one color. Nobody has to be taught to give that answer, and it is not a fault.
        'nothing' is a fault, and goes somewhere else."""
        if not self.job or self.job["state"] != "order":
            raise StripError("Nothing is asking about colors just now.")
        j = self.job
        what = (what or "").strip().lower()
        if what == "nothing":
            return self._fail("Nothing lit up. Check the strip is plugged in at both ends.")
        if what == "stripes":
            # Four channels per pixel. Say so, keep the order question open, and ask it again with
            # frames the strip's own width so the colors mean something.
            j["white"] = True
            await self._tell(j["id"], "white/set", "1")
            await self._show_red()
            return self.status()
        seen = {"red": "r", "green": "g", "blue": "b"}.get(what)
        if not seen: raise StripError("That is not one of the colors it can be showing.")
        if j.get("first") is None:
            order = resolve(seen)
            j["first"] = seen
            if order: return await self._settled(order)
            # Still two possible. Make red the FIRST byte this time, which splits whichever pair it is.
            await self._tell(j["id"], "show/set", "raw 255 0 0")
            self._set("order")
            return self.status()
        order = resolve(j["first"], seen)
        if not order:
            return self._fail("That strip is not one this hub knows how to drive.")
        return await self._settled(order)

    async def _settled(self, order: str) -> dict:
        j = self.job
        j["order"] = order
        await self._tell(j["id"], "order/set", order, retain=True)
        return await self._fill()

    # ---- how long it is ----
    async def _fill(self) -> dict:
        j = self.job
        await self._tell(j["id"], "show/set", "fill")
        self._set("length", lit=0)
        return self.status()

    async def ends(self) -> dict:
        """That's the whole of it.

        The firmware latches where the fill had got to the instant it hears this, not when the brain
        gets round to reading a number back. A person's reaction time is the error that matters here
        and it is already in the answer; adding a round trip's worth of network on top of it would
        make a strip measure short by however busy the Wi-Fi was."""
        if not self.job or self.job["state"] != "length":
            raise StripError("Nothing is being measured just now.")
        j = self.job
        got = await self._ask(j["id"], "fill/stop", "1", want="count", timeout=ANSWER_WAIT)
        try: n = int(str(got).strip())
        except (TypeError, ValueError):
            return self._fail("The strip did not say how long it is. Try that again.")
        n = max(1, min(MOST, n))
        j["count"] = n
        await self._tell(j["id"], "count/set", str(n), retain=True)
        self._set("room")
        return self.status()

    async def again(self) -> dict:
        """Start again -- the fill empties and runs once more. Missing it costs nothing."""
        if not self.job or self.job["state"] != "length":
            raise StripError("Nothing is being measured just now.")
        return await self._fill()

    # ---- where it is ----
    async def put(self, room_id: str) -> dict:
        if not self.job or self.job["state"] != "room":
            raise StripError("There is no light strip waiting for a room.")
        j = self.job
        j["room"] = room_id
        await self._tell(j["id"], "room/set", room_id, retain=True)
        try:
            await self.hub.strip_placed(j["id"], room_id)
        except AttributeError:
            pass
        self._set("ready")
        return self.status()

    async def done(self) -> dict:
        """The sheet has been read. A finished job has nothing left to say, and until the brain is
        told so it keeps reporting it -- which is somebody pressing OK at a dialog that will not die."""
        self.job = None
        self.hub._broadcast(json.dumps({"type": "strip", "strip": self.status()}))
        return self.status()
