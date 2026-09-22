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
    press     our own door, and the only thing it ever asks: press the button on the thing. The
              session is already open and the credentials are still here, because the gate is on
              the STRIP. A tap on "it has no button I can reach" drops a rung, to:
    rhythm    the strip mints four counts of one to six and flashes them, and somebody taps what
              they count. Reached only from `press`, never on its own
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
import asyncio, json, logging, time

log = logging.getLogger("hub.strip")

BASE = "strip"
# ONE STEP, BECAUSE ONE THING HAPPENS. It used to be two -- "putting it on your Wi-Fi", then
# "introducing it to the hub" -- back when the hub carried the credentials itself and then waited for
# the strip to appear on the broker. Commissioning does both at once and neither of them is ours, so
# a second line would be a progress bar with nothing behind it.
STEPS = ("letting",)

# How long to wait on a strip for each kind of question. Named so the tests can shrink them: a suite
# that waits out a real timeout teaches people to skip it.
JOIN_WAIT = 60
ANSWER_WAIT = 10
# How long to keep looking for the light in the house's own device list after somebody has chosen a
# room for it. The strip announces itself over MQTT discovery and Home Assistant makes the device a
# moment later, so the room can be chosen before there is anything to put in it.
PLACE_WAIT = 20
# ...AND HOW LONG TO GO ON CARING AFTER THAT. Twenty seconds was not enough in a real house on
# 22 September: the device had not appeared, the placing was given up on, and the wall said "It's in"
# anyway with only a log line to say otherwise. The household did the only sensible thing and reset
# the strip -- and the second run worked, because the device the first run had waited for existed by
# then. A room somebody chose is a fact this brain holds, not a request that expires while Home
# Assistant catches up; so it is remembered and applied whenever the device turns up.
PLACE_KEEP = 600

# HOW OFTEN TO GO LOOKING WHEN NOBODY ASKED, AND HOW HARD WHEN SOMEBODY DID (design/knock/).
#
# A knock used to be a sheet that took the whole screen, so being slow was a fault: a household
# measured about two minutes between plugging a strip in and the wall saying anything, and read it
# as the strip and the hub failing to talk to each other. It is a line in the band now, and a line
# that arrives a minute late is a line -- so the background loop is no longer the thing that has to
# be fast, and it costs the house's radio less than it did.
#
# WHAT HAS TO BE FAST IS ADD, and only Add: somebody standing on that page has asked, is waiting,
# and is the only moment when spending the radio is free. `looking()` is the panel saying so, and
# the loop then scans back to back for as long as it keeps saying it.
LOOK_EVERY = 60.0
# How long one `looking()` is good for. The panel says it again every few seconds while the page is
# open; a wall that is closed, asleep or unplugged simply stops saying it and the loop goes quiet on
# its own, which is why this is a hold rather than a switch somebody could leave on.
LOOK_HOLD = 12.0

# A strip nobody has told how long it is. The controller writes this many lights every frame and the
# surplus falls off the end of the wire, so a strip shorter than this is simply right -- which is
# what makes direction C on the canvas a real argument rather than a shortcut. We ask anyway, because
# anything that needs to know where the MIDDLE is comes out wrong without it.
ASSUMED = 300
MOST = 1200

# HOW FAINT IS TOO FAINT, MEASURED RATHER THAN GUESSED (docs/strip.md item 15). From a real hub a
# session establishes first try at -51 dBm and the link dies three to five seconds in at -64, every
# time. So anything heard below this is a strip we may well fail to set up, and the reason will be
# the distance rather than anything the household did.
FAINT = -60


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


# The service a commissionable Matter device advertises under, and how to read what it says.
MATTER_SVC = "0000fff6-0000-1000-8000-00805f9b34fb"
# Our own, until there is a real Vendor ID to replace it. docs/strip.md item 2b.
TEST_VID = 0xFFF1

# THE CODE EVERY DEVICE WE BUILD TODAY HAS, AND WHY IT IS SAFE TO WRITE DOWN.
#
# Our firmware is built with CONFIG_ENABLE_TEST_SETUP_PARAMS, so its passcode is CHIP's own
# 20202021 and its discriminator 3840 -- compiled in, printed on the serial console at every boot,
# and published in connectedhomeip's source. It is not a secret and cannot be treated as one, which
# is precisely why a unit with it cannot be sold.
#
# So while there is no box and no label, a strip that says it is a TEST vendor is a development
# board, and the hub may as well use the code everybody already knows rather than asking somebody to
# copy it off a terminal. THE MOMENT A REAL VENDOR ID EXISTS THIS STOPS APPLYING BY ITSELF: a unit
# with its own passcode in `fctry` will not advertise TEST_VID, so this never fires for it, and the
# code has to come from the label as design/strip/CodeBox.dc.html says. That self-limiting is the
# whole reason it is written this way rather than as a setting somebody could leave switched on.
DEV_CODE = "34970112332"


def commissionable(data: bytes) -> dict | None:
    """What a commissionable advertisement means, or None if it is not one.

    Eight bytes: an opcode, then the discriminator with a version in its top nibble, then the vendor
    and product ids, then flags. Checked against a real device rather than a spec page -- an S3
    running our firmware advertises 00000ff1ff008000, and its own log says discriminator=3840/15
    vendorID=65521 productID=32768, which is what this reads out of it."""
    if len(data) < 7 or data[0] != 0x00:
        return None
    return {"discriminator": int.from_bytes(data[1:3], "little") & 0x0FFF,
            "vendor": int.from_bytes(data[3:5], "little"),
            "product": int.from_bytes(data[5:7], "little")}


def _no_matter(e: Exception) -> bool:
    """Is this Home Assistant saying it has never heard of Matter, rather than Matter saying no?

    The distinction is the difference between "add the integration" and "check the code", and those
    send a household to opposite ends of the house. It was got right in one call and wrong in the one
    beside it a commit later, which is what a shared answer is for."""
    said = str(e).lower()
    return "unknown" in said or "not found" in said or "no matter" in said


# WHAT THE WALL SAYS WHEN THE ENGINE CANNOT DO IT, and it says nothing about the engine. This used
# to read "the matter-server is running, but nothing in Home Assistant is using it", which is two
# pieces of somebody else's vocabulary on a household's wall and is what
# `product-direction-out-of-the-box` exists to forbid -- a sentence nobody in the house can act on,
# about a product they did not buy. Nor does it tell them to go and fix it: the hub drives its own
# engine's setup elsewhere (api.py does it for the weather) and has simply never been taught this
# one, which is ours to do and not theirs. docs/strip.md, the related note under item 2-mac.
NO_MATTER = ("This hub cannot let that kind of light in yet \u2014 a part of it has never been set up. "
             "That is ours to fix rather than yours, and it is nothing you have done wrong.")


class Radio:
    """Finding a strip that wants letting in, and handing it to the commissioner the house runs.

    THIS USED TO BE OUR OWN BLE PROTOCOL, TWICE, AND BOTH WERE WRONG. First a hand-rolled
    characteristic taking key=value lines, which put the household's Wi-Fi password on an open link.
    Then WiFiProv, which was at least encrypted but only existed because the Arduino framework
    compiles Matter-over-BLE out. On ESP-IDF it is compiled in, so Matter carries the credentials and
    the commissioning together and neither of ours is needed (docs/strip.md).

    So this has two small jobs. NOTICE one -- a commissionable Matter device advertises over BLE and
    says its discriminator, which is enough to know that something is knocking. And HAND IT OVER to
    `matter-server`, which the house already runs (docs/matter.md), through Home Assistant's own
    websocket command. It carries no credentials of its own and must never be given a route that does.

    WHAT IT CANNOT DO, and this is the open question rather than a missing function: an advertisement
    carries the discriminator and NOT the passcode, and commissioning needs the passcode. So the hub
    cannot silently adopt a strip the way design/puck/Knock.dc.html argues for. Where the code comes
    from -- printed on the box like every other Matter device, derived at manufacture from something
    the hub can look up, or read off an NFC tag -- has not been decided. docs/strip.md item 1a."""

    def __init__(self, hub=None, adapter: str | None = None):
        self.hub = hub
        self.adapter = adapter

    async def _bleak(self):
        try:
            import bleak
        except ModuleNotFoundError:
            raise StripError("This hub has no Bluetooth to look for a light strip with.")
        return bleak

    async def scan(self, seconds: float = 6.0) -> list[dict]:
        """Every Matter device advertising that it has never been commissioned.

        A device that HAS been commissioned stops advertising, which is the whole of the answer to
        "what happens when the router reboots": it keeps the light the household asked for and stays
        quiet. Nothing here opens a window; only a person holding the thing can do that."""
        bleak = await self._bleak()
        found = []
        for d, adv in (await bleak.BleakScanner.discover(timeout=seconds, return_adv=True)).values():
            for uuid, data in (adv.service_data or {}).items():
                if uuid.lower() != MATTER_SVC:
                    continue
                what = commissionable(bytes(data))
                if not what:
                    continue
                found.append({**what, "addr": d.address, "rssi": adv.rssi,
                              "ours": what["vendor"] == TEST_VID})
        return sorted(found, key=lambda s: -(s["rssi"] or -127))

    async def set_wifi(self, ssid: str, password: str) -> None:
        """Give the Matter controller the house Wi-Fi, which it needs before it can commission onto it.

        THE HUB DOES TOUCH THE PASSWORD, and an earlier version of this file claimed it never would
        again. It does -- once, to matter-server, which then hands it to a device inside the
        commissioning session. That is a different thing from what was removed: the old code put it on
        an unauthenticated BLE link where anything in range could read it. This puts it on the local
        engine link and lets a reviewed stack deliver it encrypted. Worth stating plainly rather than
        keeping a tidier sentence that was not true."""
        ha = getattr(self.hub, "ha", None)
        if ha is None:
            raise StripError("This hub is not talking to its engine just now.")
        try:
            await ha.send("matter/set_wifi_credentials", network_name=ssid, password=password)
        except Exception as e:
            log.warning("strip: could not give Matter the Wi-Fi (%s)", e)
            if _no_matter(e):
                raise StripError(NO_MATTER)
            raise StripError("The hub could not pass your Wi‑Fi on. Try again in a moment.")

    async def commission(self, code: str) -> dict:
        """Hand it to matter-server, through Home Assistant's own command.

        The code is the one thing this cannot discover, and asking for it here rather than pretending
        otherwise is the honest shape until somebody decides where it comes from."""
        if not code:
            raise StripError("That light strip needs its setup code.")
        # Checked rather than caught. This used to be `except AttributeError`, which is a net wide
        # enough to catch a bug of ours -- the radio was being built without a hub, so `self.hub.ha`
        # raised, and the net turned a wiring mistake into a confident sentence on the wall saying
        # this hub could not do Matter. It could. A household would have believed the screen.
        ha = getattr(self.hub, "ha", None)
        if ha is None:
            raise StripError("This hub is not talking to its engine just now.")
        try:
            return await ha.send("matter/commission", code=code) or {}
        except Exception as e:
            # Whatever the engine said was written for a log. The wall gets a sentence -- but WHICH
            # sentence matters, and the first version of this had only one. It told a household to
            # check the code and the strip when the real answer was that the house had no Matter
            # controller running at all, which is not a thing anybody finds by looking at a strip.
            log.warning("strip: commissioning failed (%s)", e)
            if _no_matter(e):
                raise StripError(NO_MATTER)
            raise StripError("The strip did not take the code. Check it, and that the strip is still lit.")

    # ---- our own door (design/strip/Ours.dc.html, docs/strip.md items 13 and 15) ----
    #
    # A strip we make offers two ways in and the household is never asked which. Everything above
    # this line is Matter's door, which is for anybody. Below it is ours, which is the only one that
    # can ask the two questions Matter has no words for and the only one that can say where we are.
    # The protocol is protocomm with SRP6a, in brain/vendor/esp_prov; hub/strip_door.py is the part
    # that is ours.

    async def scan_ours(self, seconds: float = 8.0) -> list[dict]:
        """Every strip knocking at OUR door, by service UUID rather than by name.

        The address is not an identity: a strip rotates it between advertisements, which was seen on
        21 September when two scans minutes apart returned different ones for the same board. It is
        good only for connecting to right now."""
        from . import strip_door
        found = await strip_door.find(seconds)
        return [{"addr": s["address"], "rssi": s["rssi"], "name": s.get("name"),
                 "door": "ours", "ours": True} for s in found]

    async def adopt_ours(self, addr: str, ssid: str, password: str, hub: dict | None = None,
                         rhythm: str = "", on_pressed=None,
                         out_of_reach: "asyncio.Event | None" = None) -> str:
        """Wait for the press, hand over the Wi-Fi, then say where we are -- one session, no phone.

        THE WI-FI DOES GO THROUGH US HERE, and unlike Matter's door there is no controller in the
        middle: it goes straight to the strip inside a session the strip itself gated on somebody
        touching it. That is the handshake the first firmware should have had, and the reason this
        door exists. Returns 'done', or 'rhythm' when the household said they cannot reach it."""
        from . import strip_door
        try:
            return await strip_door.adopt(addr, ssid, password, hub=hub, rhythm=rhythm,
                                          on_pressed=on_pressed, out_of_reach=out_of_reach)
        except strip_door.NotPressed:
            # NOT A RADIO FAILURE, and it must never be dressed as one. Somebody is standing in the
            # right room; they have simply not touched the thing yet.
            raise StripError("Nobody pressed the button on it. The button is on the controller, at "
                             "the end it plugs in at \u2014 say it is yours again to start over.")
        except Exception as e:
            # THE TYPE AS WELL AS THE MESSAGE, and the type FIRST, because the most common failure
            # out here has no message at all. A BLE connect that times out on BlueZ arrives as a
            # bare asyncio.TimeoutError whose str() is the empty string, so this line used to log
            # "our own door did not open ()" -- which told the next person nothing -- and the
            # matching below fell through every timeout test and sent the household to unplug a
            # strip whose only problem was the distance to the hub. Seen on a real hub, 21 September.
            log.warning("strip: our own door did not open (%s: %s)", type(e).__name__, e or "no message")
            # THREE FAILURES THAT ARE NOT THE SAME, and telling a household to recount when the radio
            # dropped is telling them to fix something they did not break. The strip refuses a wrong
            # rhythm inside SRP6a and the refusal comes back as an ATT error; a link that died comes
            # back as a disconnect; a link that never formed comes back as nothing at all. The first
            # two both used to say "check the flashes", which sent somebody to count again and again
            # at the far end of a room where the real answer was to move.
            said = f"{type(e).__name__} {e}".lower()
            # "notfound" as well as "not found": a class name has no spaces in it, and
            # BleakDeviceNotFoundError is exactly the case this branch exists for.
            if any(k in said for k in ("disconnect", "not found", "notfound", "timeout", "unreachable")):
                raise StripError("The strip stopped answering part way through. "
                                 "Try again a little nearer the hub.")
            if not rhythm:
                raise StripError("The strip would not finish letting us in. Unplug it and try again.")
            raise StripError("Those were not the flashes it is showing. Count them again \u2014 "
                             "and note it shows a new set every time it is plugged in.")


class Strips:
    """One job at a time, because it is a person standing in front of a thing."""

    def __init__(self, hub, radio: Radio | None = None):
        self.hub = hub
        self.radio = radio or Radio(hub)
        self.job: dict | None = None
        self._sub: int | None = None
        self._dismissed: set[str] = set()      # "not mine": left alone until it is power-cycled
        self.strips: dict[str, dict] = {}      # what the broker says: id -> {"online", "count", "order"}
        self._heard: dict[str, dict] = {}      # the last retained value per (id, leaf)
        self._arrived: set[str] = set()        # said "online" since we last started listening
        self._devices: dict[str, str] = {}     # our id for a strip -> the house's id for its hardware
        self._woke: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        # Set when the household says they cannot reach the button. The session waiting for a press
        # is holding a BLE link open, so this is how it is told to stop waiting and drop a rung.
        self._out_of_reach: asyncio.Event | None = None
        # Until when somebody is standing on Add. Monotonic, because it is a duration and not a time
        # of day, and a hub whose clock steps must not start scanning for an hour.
        self._looking_until = 0.0
        # Rooms somebody chose that Home Assistant had not made a device for yet: strip id -> room.
        # Emptied as each one lands. See _place_later().
        self._owed: dict[str, str] = {}
        self._placer: asyncio.Task | None = None

    # ---- what the panel sees ----
    def status(self) -> dict:
        base = {"strips": sum(1 for s in self.strips.values() if s.get("online"))}
        if not self.job: return {**base, "state": "none"}
        j = self.job
        out = {**base, "state": j["state"], "name": j.get("label") or "A light strip"}
        # The panel says a different sentence for a question being asked again than for one being
        # asked the first time: somebody who came back already knows what the thing does.
        if j.get("revisit"): out["revisit"] = j["revisit"]
        if j["state"] == "working": out["step"] = j["step"]
        if j["state"] == "order":
            # Which question is on screen: the first is a yes/no, the second is the three primaries.
            out["asking"] = "red" if j.get("first") is None else "which"
        if j["state"] == "length": out["lit"] = j.get("lit", 0)
        # Four counts of one to six, read off the light itself. The panel draws four steppers and
        # sends back what somebody counted; nothing here is typed and nothing is printed on the
        # strip. The rung below the press, and reached only from it
        # (design/strip/ReachRhythm.dc.html).
        if j["state"] == "rhythm": out["groups"] = 4; out["most"] = 6
        if j["state"] in ("room", "ready"):
            out["count"] = j.get("count", ASSUMED); out["order"] = j.get("order", ASSUME)
            out["white"] = bool(j.get("white"))
        if j["state"] == "room": out["rooms"] = self._rooms()
        # THE ROOM IS CHOSEN AND THE HOUSE HAS NOT CAUGHT UP. The last beat used to say "It is a
        # light in the house now -- ... in the room it lives in", which was not true whenever the
        # placing had not landed, and a household reading it went and did the whole setup again.
        # Named rather than flagged, because the sentence on the wall wants the room's own name.
        if j.get("id") in self._owed:
            out["placing"] = self._room_name(self._owed[j["id"]])
        if j.get("text"): out["text"] = j["text"]
        if j.get("needs"): out["needs"] = j["needs"]
        # WHEN IT STARTED KNOCKING, in seconds since the epoch rather than "how long ago", because a
        # wall reloads and a poll is a minute apart: an age computed here is stale by the time it is
        # drawn, and a moment is not. The panel folds its line away after an hour of this.
        if j.get("at"): out["since"] = j["at"]
        return out

    def _room_name(self, room_id: str) -> str:
        """What the household calls that room, for a sentence on the wall. Its id is not a name."""
        rooms = getattr(getattr(self.hub, "home", None), "rooms", None) or {}
        got = rooms.get(room_id) if hasattr(rooms, "get") else None
        return getattr(got, "name", None) or "the room you chose"

    def _where_we_are(self) -> dict:
        """What a strip needs to find us again after it reboots, in the shape the `hub` endpoint
        reads. Only sent through our own door, and only inside a session the strip authenticated.

        THE SAME THING A PUCK IS TOLD, FROM THE SAME PLACE. This used to read a `broker` key in the
        settings that nothing in this hub has ever written, so it handed over the literal name "hub"
        and no credentials at all -- and every strip we have ever set up joined the house, reached
        the broker and was refused: `mqtt_client: Connection refused, not authorized`. On the wall
        that read as "It joined your Wi-Fi but never found the hub. Try it nearer the router", which
        sent somebody to move a strip that was already on their network. Seen on a real hub on
        21 September, and it had been true since the day our own door was written."""
        try:
            mq = self.hub.bridge.broker()
        except Exception as e:
            log.warning("strip: no broker details to hand over (%s)", e)
            mq = {}
        where = {"mhost": mq.get("name") or mq.get("host") or "hub", "base": BASE}
        if mq.get("user"): where["muser"] = mq["user"]
        if mq.get("pass"): where["mpass"] = mq["pass"]
        return where

    def _rooms(self) -> list:
        """The rooms to offer, in the shape the panel draws as chips.

        `home.rooms` IS A DICT of id -> Room, and iterating a dict gives you its keys -- which is how
        this came to call `r["id"]` on a string and answer 500 to every request, including the poll
        the sheet lives on. It had been that way since it was written and no test caught it because
        the fake house is a list. Everywhere else in the brain says `.rooms.values()`. Seen on a real
        house on 21 September, at the one beat that reaches this: "Where is it?".

        `unassigned` is a real room in the dict and is never a place to put something; every other
        caller skips it and so does this."""
        rooms = getattr(getattr(self.hub, "home", None), "rooms", None) or []
        if isinstance(rooms, dict): rooms = list(rooms.values())
        out = []
        for r in rooms:
            got = r if isinstance(r, dict) else {}
            rid = getattr(r, "id", None) or got.get("id")
            name = getattr(r, "name", None) or got.get("name")
            if not rid or rid == "unassigned": continue
            out.append({"id": rid, "name": name or rid})
        return out

    def _set(self, state, **more):
        if not self.job: return
        self.job.update(state=state, **more)
        self.hub._broadcast(json.dumps({"type": "strip", "strip": self.status()}))

    def _fail(self, text: str) -> dict:
        """Why it did not work, in words for the wall.

        AND WHEN THE REAL ANSWER IS THE DISTANCE, THAT IS THE ONLY ANSWER WORTH GIVING. A strip at
        the far end of a house fails in whatever way the radio happens to fail that minute -- the
        setup code is refused, a link dies in the middle, a device that answered a scan cannot be
        connected to a moment later -- and every one of those sentences sends somebody to check a
        thing that is not wrong. The hub heard how faint it was when it knocked and has known all
        along. Seen on a real hub on 21 September: a strip the hub could not hear at all on a
        twenty-second scan, and the wall said "the strip did not take the code"."""
        if self._faint():
            text = ("That strip is a long way from the hub \u2014 it was only just audible when it "
                    "knocked. Set it up in the same room as the hub, then put it where you want it.")
        self._set("failed", text=text)
        return self.status()

    def _faint(self) -> bool:
        heard = (self.job or {}).get("rssi")
        return heard is not None and heard < FAINT

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
        if leaf == "status":
            s["online"] = str(payload).strip() == "online"
            # THE ARRIVAL, NOT THE STATE. A strip that goes away does not say so: the broker says it
            # for it, from the last will, and only once the keepalive has run out. A factory reset,
            # a reboot, a knock and a press all happen well inside that, so the hub can still believe
            # the old connection is alive while the household stands over the strip that replaced it.
            # A message ARRIVING is a fact with a time on it; "online" is only a guess about now.
            if s["online"]: self._arrived.add(id_)
        elif leaf == "count":
            try: s["count"] = int(str(payload).strip())
            except ValueError: pass
        elif leaf == "order": s["order"] = str(payload).strip()
        # A fill that has reached the end says so itself, so the panel can stop asking somebody to
        # watch a thing that has finished happening.
        #
        # ONLY WHILE THE FILL IS THE THING ON SCREEN. The strip publishes its progress as it goes and
        # the last of those can land AFTER the household has said "that's the whole of it" -- and this
        # then dragged the job back to `length` from whatever beat it had moved on to. What that looks
        # like from the wall: you are asked for a room, you tap one, you are told there is no light
        # waiting for a room, and you are back watching the fill. Reported from a real house on
        # 21 September, three times in a row, which is exactly how often a late message lands.
        if (self.job and self.job.get("id") == id_ and leaf == "fill"
                and self.job.get("state") == "length"):
            try: self._set("length", lit=int(str(payload).strip()))
            except ValueError: pass
        if self._woke and not self._woke.is_set(): self._woke.set()

    async def _tell(self, id_: str, leaf: str, payload: str, retain: bool = False) -> None:
        """Say something to one strip. Nothing a strip is TOLD is retained -- see below."""
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
            except TimeoutError: break
            self._woke.clear()
        return self._heard.get(f"{id_}/{want}")

    # ---- the knock ----
    async def watch(self, every: float = LOOK_EVERY):
        """Look for a strip that is knocking, for as long as the brain is up.

        TWO SPEEDS, AND THE FAST ONE IS BORROWED RATHER THAN KEPT. A BLE scan is the radio going
        quiet for every other device in the house, so a loop tight enough to feel instant costs the
        house all day to catch an event that happens when somebody plugs a thing in and is standing
        right there -- which is exactly when the panel calls `looking()`. So: back to back while
        somebody is on Add, and once a minute otherwise.

        The slow speed is deliberately not slower than that. A knock is a line in the band now and a
        late line is forgivable, but a household that plugs a strip in and sees nothing for five
        minutes has been told the same lie in a quieter voice."""
        while True:
            try:
                if not self.job: await self.look()
            except Exception as e:
                log.info("strip: look failed (%s)", e)
            # `look()` is fourteen seconds of scanning on its own, so "back to back" needs no delay
            # of its own -- only long enough to notice a job appearing or the watcher going away.
            await asyncio.sleep(0.5 if self.being_watched() else every)

    def being_watched(self) -> bool:
        """Is somebody standing on Add right now? See LOOK_HOLD."""
        return time.monotonic() < self._looking_until

    async def looking(self) -> dict:
        """The panel saying somebody is on Add and waiting. Holds the loop at its fast speed.

        It is a HOLD and not a switch: it lapses by itself, so a wall that goes to rest, gets closed
        or is unplugged mid-look cannot leave the hub scanning for ever. The panel says it again
        every few seconds for as long as the page is open, and Add is also the one place a scan is
        free, because the person it costs is the person who asked for it."""
        was = self.being_watched()
        self._looking_until = time.monotonic() + LOOK_HOLD
        if not was:
            log.info("strip: somebody is on Add; looking properly")
            # Do not wait out whatever is left of the slow sleep -- that is up to a minute of
            # somebody standing in front of a page that says it is listening and is not.
            if self._woke and not self._woke.is_set(): self._woke.set()
        return self.status()

    async def look(self) -> dict:
        """One scan. A strip that is advertising has never been set up, so anything found is a knock."""
        if self.job: return self.status()
        found: list[dict] = []
        # OUR DOOR FIRST, because a strip that offers it can be asked more, and a strip offers both
        # until somebody takes it (design/strip/Both.dc.html).
        try: ours = await self.radio.scan_ours()
        except StripError as e: return {**self.status(), "text": str(e)}
        except Exception as e:
            log.info("strip: our door found nothing (%s)", e); ours = []
        theirs: list[dict] = []
        try: theirs = await self.radio.scan()
        except StripError as e:
            if not ours: return {**self.status(), "text": str(e)}
        except Exception as e:
            log.info("strip: scan failed (%s)", e)
            if not ours: return self.status()

        # THE TWO DOORS ARE NOT EQUALLY EASY TO SEE, and that asymmetry sent a household down the
        # wrong one on 21 September. Matter's identity is in the ADVERTISEMENT; ours is in the SCAN
        # RESPONSE, because Matter's payload had already filled the advertisement and 31 bytes will
        # not hold both (docs/strip.md item 12). A scan response only arrives if the scanner asked
        # for one and the answer got back, so at the far end of a room the advertisement lands and
        # the scan response sometimes does not -- and the same strip appears at Matter's door only.
        # The household was then asked for a setup code, and the commissioner failed, for a strip
        # that had a perfectly good door of ours open the whole time.
        #
        # So: if nothing turned up at our door but something turned up at Matter's that could be
        # ours, ask again, once, for longer. A retry rather than a guess -- the alternative is
        # treating a test vendor id as proof, and item 6 already established that identifies
        # nobody.
        if not ours and any(t.get("ours") for t in theirs):
            log.info("strip: something that might be ours is at Matter's door; asking ours again")
            try: ours = await self.radio.scan_ours(14.0)
            except Exception as e: log.info("strip: our door still found nothing (%s)", e)

        # One strip, two advertisements: if an address answered at both, it is the same board and
        # our door is the one worth having.
        at_ours = {o["addr"] for o in ours}
        # NEAREST FIRST, WITHIN EACH DOOR. Our door still wins over Matter's however faint it is,
        # because it is the only one that can ask the two questions and hand over the broker -- but
        # WHICH strip at our door was whichever happened to advertise first, and two strips knocking
        # is an ordinary evening: somebody unpacks a pair. A household standing over one of them
        # pressing its button, while the hub waits on the other in a different room, is timed out
        # and then told the strip is a long way from the hub -- perfectly accurate, about the wrong
        # strip. Matter's side has sorted by signal since it was written; this side never did.
        loud = lambda s: -(s.get("rssi") if s.get("rssi") is not None else -127)
        found = sorted(ours, key=loud) + sorted(
            (t for t in theirs if t["addr"] not in at_ours), key=loud)
        for s in found:
            if s["addr"] in self._dismissed: continue
            # No chip here: a Matter advertisement carries a discriminator and not an id of ours.
            # `id` arrives later, from the broker, if the strip ever finds it (item 2a).
            self.job = {"state": "knocking", "id": None, "addr": s["addr"],
                        "discriminator": s.get("discriminator"), "vendor": s.get("vendor"),
                        "door": s.get("door", "matter"), "rssi": s.get("rssi"),
                        "label": self._label(s), "first": None, "at": time.time()}
            # WHICH ONE, AND HOW WELL WE CAN HEAR IT. Without this the only record of why a setup
            # was later called "a long way from the hub" is the sentence itself, and there is no way
            # to tell a faint strip from a bug in the reading. It is one line and it has already
            # been wanted three times in one evening.
            log.info("strip: knocking at %s door, heard at %s dBm%s",
                     "our own" if s.get("door") == "ours" else "Matter's", s.get("rssi"),
                     "" if len(found) == 1 else f" ({len(found)} are knocking)")
            self._set("knocking")
            break
        return self.status()

    @staticmethod
    def _label(s: dict | None) -> str:
        """What to call it before anybody has named it. Never the address: a household that is shown
        a MAC has been handed the inside of the product, and there is nothing to disambiguate anyway
        -- the thing is two meters of light and it is the only one lit."""
        return "A light strip"

    async def dismiss(self) -> dict:
        """Not mine. Needs no code: refusing gives nothing away, and nothing was ever sent."""
        if self.job: self._dismissed.add(self.job["addr"])
        self.job = None
        self.hub._broadcast(json.dumps({"type": "strip", "strip": self.status()}))
        return self.status()

    async def adopt(self, code: str = "") -> dict:
        """Yes, that's mine. The first moment anything of the house's moves.

        THE WI-FI IS NOT OURS TO HAND OVER ANY MORE, and that is the whole point of the move to
        Matter: commissioning carries the credentials itself, encrypted, so the hub never holds them
        on a strip's behalf and there is no step here that could leak one.

        It does need the setup code, which an advertisement does not carry -- see Radio. Where a
        household's code comes from is docs/strip.md item 1a and is not decided."""
        if not self.job or self.job["state"] != "knocking":
            raise StripError("There is no light strip waiting to be let in.")
        # OUR DOOR ASKS ONE MORE THING, and it is the only thing it ever asks: press the button on
        # the thing. The session opens straight away and gets as far as the Wi-Fi question, where the
        # STRIP refuses it until somebody in the room has touched it -- so nothing of the house's has
        # moved while this beat is on screen. Matter's door skips it and wants a code instead.
        #
        # The controller cannot commission onto a network it has not been told about, and it is the
        # house's own Wi-Fi rather than this strip's -- so it is asked once, on the wall, exactly the
        # way bridge.py asks it, and no strip after this one asks again.
        wifi = (self.hub.settings.get("wifi") or {}) if hasattr(self.hub, "settings") else {}
        if not wifi.get("ssid"):
            self._set("working", step="letting", needs="wifi")
            return self.status()
        if self.job.get("door") == "ours":
            self._begin()
            return self.status()
        # A development board's code is public, so nobody should have to read it off a terminal.
        if not code and self.job.get("vendor") == TEST_VID:
            code = DEV_CODE
        self.job["code"] = code
        self._set("working", step="letting")
        self._task = asyncio.create_task(self._setup())
        return self.status()

    def _pressed(self):
        """The strip says somebody touched it, and it is the strip saying so rather than a timer here.

        Nothing of the house's had moved until this instant: the session was open, the strip was lit,
        and the credentials were still on the hub."""
        if self.job and self.job["state"] == "press":
            self._set("working", step="letting")

    def _begin(self):
        """The Wi-Fi is known, so start the session. ONE PLACE, because there are three ways in --
        saying yes, answering the Wi-Fi question, and counting the flashes -- and the beat they land
        on is a fact about the door rather than about which of the three it was."""
        j = self.job
        j["needs"] = None
        if j.get("door") == "ours" and not j.get("rhythm"):
            self._out_of_reach = asyncio.Event()
            self._set("press")
        else:
            self._set("working", step="letting")
        self._task = asyncio.create_task(self._setup())

    async def reach(self) -> dict:
        """It has no button anybody can reach.

        THE ONLY WAY TO THE RUNG BELOW, and it is a real button because it will be pressed: a strip
        already taped behind a television is exactly the thing whose controller cannot be got at. The
        session that is waiting for a press asks the strip for a rhythm instead, the strip shuts its
        door and reopens it with a verifier made from four fresh counts, and this beat waits for
        somebody to read them off the light. design/strip/ReachRhythm.dc.html."""
        if not self.job or self.job["state"] != "press":
            raise StripError("Nothing is waiting to be pressed just now.")
        if self._out_of_reach: self._out_of_reach.set()
        self._set("rhythm")
        return self.status()

    async def counted(self, rhythm: str) -> dict:
        """What somebody counted off the light. Four digits, one to six each.

        A wrong count fails inside SRP6a and ends the session, so there is no guessing at this: the
        strip mints a new rhythm every time it is asked for one, and the wall says so."""
        if not self.job or self.job["state"] != "rhythm":
            raise StripError("Nothing is asking to be counted just now.")
        digits = "".join(ch for ch in (rhythm or "") if ch.isdigit())
        if len(digits) != 4 or any(ch not in "123456" for ch in digits):
            raise StripError("Four groups, and each one is between one and six flashes.")
        self.job["rhythm"] = digits
        self._begin()
        return self.status()

    async def wifi(self, ssid: str, password: str) -> dict:
        """The house's Wi-Fi, for the Matter controller: asked once, on the wall, and kept.

        Not handed to a strip. Handed to matter-server, which passes it to a device inside the
        commissioning session. Every strip after this one is set up without anybody being asked."""
        if not ssid:
            raise StripError("Which Wi‑Fi? The name is needed.")
        self.hub.settings.set(wifi={"ssid": ssid, "pass": password})
        if not self.job:
            return self.status()
        self._begin()
        return self.status()

    async def _setup(self):
        j = self.job
        if not j: return
        try:
            wifi = (self.hub.settings.get("wifi") or {}) if hasattr(self.hub, "settings") else {}
            # Every strip that is ON THE BROKER RIGHT NOW, so the one that comes online next is
            # this one. NOT every strip the broker has heard of: it keeps what a strip said last,
            # retained, and the brain reads all of it the moment it subscribes -- so a strip being
            # set up for the second time is already in this dict, marked offline, and "an id that
            # was not there before" can never match it again. Which is a strip somebody factory
            # reset and is standing over, watching the wall say it never reached the hub. 21 Sep.
            known = {id_ for id_, s in self.strips.items() if s.get("online")}
            if j.get("door") == "ours":
                # OUR DOOR CARRIES EVERYTHING IN ONE SESSION, which is the whole difference. The
                # Wi-Fi and where we are go together, so the strip comes out of setup already able
                # to reach the broker -- and the two questions Matter has no words for can be asked
                # at all. That was item 2a, and it was an empty string from the day Matter came in.
                #
                # The session opens at once and then holds, because the strip will not take the
                # credentials until somebody presses the button on it. `pressed` is what moves the
                # wall off that beat, and it comes from the strip rather than from a timer here.
                went = await self.radio.adopt_ours(j["addr"], wifi.get("ssid", ""),
                                                   wifi.get("pass") or "",
                                                   hub=self._where_we_are(),
                                                   rhythm=j.get("rhythm", ""),
                                                   on_pressed=self._pressed,
                                                   out_of_reach=self._out_of_reach)
                # They could not reach it, so `reach()` has already moved the wall to the flashes and
                # the strip is minting them. Nothing failed and nothing should be said.
                if went == "rhythm":
                    return
            else:
                if wifi.get("ssid"):
                    await self.radio.set_wifi(wifi["ssid"], wifi.get("pass") or "")
                await self.radio.commission(j.get("code", ""))
            # AND HERE THE SETUP STOPS FOR A STRIP THAT CAME THROUGH MATTER'S DOOR, and it is worth
            # saying why rather than quietly doing less. Everything after this -- which color comes
            # out first, how far it goes -- is ours and goes over the broker, and needs the strip's
            # chip to address it by. A Matter advertisement does not carry one, and a commissioned
            # strip only tells us when it finds our broker, which nothing has told it where to find.
            #
            # A strip that gets here is a working Matter light in whatever app commissioned it. It
            # is our extra half that is missing, not its own. A strip that came through OUR door was
            # handed the broker in the same session and does not stop here.
            if j.get("door") != "ours":
                self._set("ready")
                return
            # It is on the Wi-Fi now, so everything after this goes over the broker. Wait for it to
            # say so itself rather than assuming: a strip that joined and cannot find the hub is a
            # different failure from one that never joined, and the household can fix only one of them.
            # WHO IS IT, ON THE BROKER? A strip that came through our door has told us nothing we
            # can address it by -- a Matter advertisement carries a discriminator and not an id of
            # ours -- so `id` is None here and has been since the day this was written. It used to
            # ask `strip/None/hello`, a topic nothing has ever subscribed to, so EVERY strip adopted
            # through our own door failed at this line however close it was standing.
            #
            # It says who it is the moment it reaches the broker, retained. So the answer is to wait
            # for the one that was not there before rather than to ask for a name we do not have.
            # One job at a time is what makes that unambiguous, and it is the rule this class opens
            # with. Seen on a real hub on 21 September, where it read as "it never found the hub".
            j["id"] = await self._whoever_just_arrived(known, timeout=JOIN_WAIT)
            if not j["id"]:
                return self._fail("It joined your Wi‑Fi but never reached the hub. "
                                  "Try it nearer the router.")
            await self._show_red()
        except StripError as e:
            self._fail(str(e))
        except Exception:
            log.exception("strip setup failed")
            self._fail("Setting that light strip up did not work. Unplug it and try again.")

    async def _whoever_just_arrived(self, known: set, timeout: float) -> str | None:
        """The id of the first strip to COME ONLINE that was not online before.

        It announces itself -- `strip/<id>/status` is published retained the moment it connects --
        so there is nothing to ask and nothing to poll. `known` is the set of strips already online
        when the session began, because a house may have strips in it and every one of them is also
        online. It is deliberately not "every strip the broker has heard of": those are retained and
        include every strip that has ever connected, which is exactly the strip being set up again."""
        self._arrived.clear()
        self._woke = asyncio.Event()
        end = time.monotonic() + timeout
        log.info("strip: waiting for it on the broker; %d already online", len(known))
        while True:
            # Either is good enough, and they fail in different weather: one that says hello while
            # we are listening, or one that is online now and was not when we started.
            for id_ in list(self._arrived): return id_
            for id_, s in list(self.strips.items()):
                if s.get("online") and id_ not in known: return id_
            left = end - time.monotonic()
            if left <= 0: break
            try: await asyncio.wait_for(self._woke.wait(), timeout=max(0.01, left))
            except TimeoutError: break
            self._woke.clear()
        log.warning("strip: nothing arrived on the broker in %ss. Known: %s", timeout,
                    {i: bool(v.get("online")) for i, v in self.strips.items()})
        return None

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
        # NOT RETAINED, and none of the three setup commands is (item 31, decided 22 September).
        # The strip writes each of these into its own NVS, so a retained copy on the broker is a
        # second source of truth that is replayed at every reconnect and silently wins when it is
        # stale. These are only ever said to a strip that is online and standing in front of
        # somebody, so there is nothing for a retain to rescue.
        await self._tell(j["id"], "order/set", order)
        # Somebody who came back to fix the colors did not ask to be walked through the length again.
        if j.get("revisit"):
            self._set("ready")
            return self.status()
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
        # Not retained: the strip remembers its own length. See order/set above.
        await self._tell(j["id"], "count/set", str(n))
        # A strip that is already in a room keeps it. Asking again would be the panel forgetting
        # something the household told it once.
        self._set("ready" if j.get("revisit") else "room")
        return self.status()

    async def again(self) -> dict:
        """Start again -- the fill empties and runs once more. Missing it costs nothing."""
        if not self.job or self.job["state"] != "length":
            raise StripError("Nothing is being measured just now.")
        return await self._fill()

    # ---- afterwards ----
    async def each(self) -> list[dict]:
        """Every strip the house has, for the pane that offers to ask one something again.

        `device` is the whole reason this is worth asking for: it is the house's own id for the
        hardware, which every device the panel draws already carries, and it is how a light pane
        knows that the light it is drawing IS one of these. Without it the panel would be guessing
        from a model string."""
        out = []
        for i, v in sorted(self.strips.items()):
            out.append({"id": i, "online": bool(v.get("online")), "count": v.get("count"),
                        "order": v.get("order"), "device": await self._device_for(i)})
        return out

    async def _device_for(self, id_: str) -> str | None:
        """The house's id for this strip's hardware, or None if it has not made one yet.

        Cached once found and never cached when not: discovery is a moment behind everything else,
        and remembering that a thing did not exist is how a panel comes to be permanently sure."""
        known = self._devices.get(id_)
        if known: return known
        want = f"{BASE}_{id_}"
        try:
            rows = await self.hub.ha.send("config/device_registry/list") or []
        except Exception as e:
            log.info("strip: could not read the house's devices (%s)", e)
            return None
        for d in rows:
            names = [str(x) for ident in (d.get("identifiers") or [])
                     for x in (ident if isinstance(ident, (list, tuple)) else [ident])]
            if want in names and d.get("id"):
                self._devices[id_] = d["id"]
                return d["id"]
        return None

    async def forget(self, id_: str) -> dict:
        """Done with a strip: it goes from the house, and is told to forget the house with it.

        THE SECOND HALF IS THE POINT, and it is the half a device registry cannot do. Dropping a
        strip's light out of the house leaves the STRIP still holding our broker, our credentials
        and its own answers -- adopted by a household that no longer has it. Plug it in and it
        announces itself again, into a house that has just been told it is gone, and nobody has a
        word for what is happening. So it is asked to let go too, which is exactly what the ten
        second hold on its own button does; what is left is a strip anybody can set up again, here
        or in whoever's house it was sold into.

        WHAT IS SAID IS NOT RETAINED, so a strip that is unplugged never hears it. The house lets it
        go anyway -- somebody is standing over a thing that is already in a box, and refusing would
        be the panel arguing with them -- and `heard` comes back false so the panel can say the one
        true thing left: the strip still believes it is ours, and its button is the only way to
        settle that. The strip clears its own retained topics when it hears; this clears them from
        this end for the strip that did not, because a retained `status` outlives the thing it was
        about and would put a forgotten strip back in the house at the next broker restart.
        """
        known = self.strips.get(id_)
        if not known:
            raise StripError("That light strip is not one this hub knows about.")
        if self.job and self.job.get("id") == id_:
            raise StripError("That light strip is in the middle of being set up. Finish that first.")
        heard = bool(known.get("online"))
        label = self._label(known)
        if heard:
            await self._tell(id_, "forget", "1")
            await asyncio.sleep(0.8)      # long enough for it to empty its own topics before we empty them
        for leaf in ("status", "count", "order", "light", "fill", "white", "room"):
            try:
                await self.hub.ha.call("mqtt", "publish", {},
                                       topic=f"{BASE}/{id_}/{leaf}", payload="", retain=True)
            except Exception as e:
                log.info("strip %s: could not clear %s (%s)", id_, leaf, e)
        try:
            await self.hub.ha.call("mqtt", "publish", {},
                                   topic=f"homeassistant/light/{BASE}_{id_}/config", payload="", retain=True)
        except Exception as e:
            log.info("strip %s: could not clear its light (%s)", id_, e)
        self.strips.pop(id_, None)
        self._devices.pop(id_, None)
        self._dismissed.discard(id_)
        self._arrived.discard(id_)
        for key in [k for k in self._heard if k.startswith(f"{id_}/")]:
            self._heard.pop(key, None)
        self.hub.log.add("strip", id_, None, "forgotten", source="user", detail={"name": label})
        return {"forgotten": label, "heard": heard}

    # ---- moving the end afterwards ----
    #
    # THE FILL IS A MEASUREMENT AND A MEASUREMENT HAS AN ERROR. A person's reaction time is the only
    # one in it (see fill/stop in the firmware), so it lands a few lights either side: long, which is
    # invisible because the surplus falls off the wire, or short, which leaves the far end of the
    # strip dark for ever and is the one a household reports. This is the other half of the decision
    # taken on 20 September -- "A at setup, B afterwards" -- and it lives on the strip's own pane
    # rather than in setup, so setup stays one tap. design/strip/Nudge.dc.html.
    #
    # It is deliberately NOT a job. A job is the setup conversation, one at a time, on the wall; this
    # is a control on a pane, on a strip that is already in the house, and a household turning a lamp
    # up in another room must not be told a light strip is being set up.
    async def tune(self, id_: str) -> dict:
        """Light it at the length it believes, with a cool tail on the last few. See Nudge."""
        known = self._for_tuning(id_)
        await self._tell(id_, "show/set", "tune")
        return {"id": id_, "count": known.get("count", ASSUMED), "tuning": True}

    async def tune_by(self, id_: str, by: int) -> dict:
        """Move the end by a few lights. Not written down until `tune_done`.

        The strip answers with what it actually took -- it clamps to one at the bottom and to the
        most it can drive at the top -- and that answer is what the wall shows, so a household
        holding the button at either end sees it stop rather than a number that goes on moving."""
        known = self._for_tuning(id_)
        want = max(1, min(MOST, int(known.get("count", ASSUMED)) + int(by)))
        got = await self._ask(id_, "tune/set", str(want), want="count", timeout=ANSWER_WAIT)
        try: now = int(str(got).strip())
        except (TypeError, ValueError): now = want
        self.strips.setdefault(id_, {})["count"] = now
        return {"id": id_, "count": now, "tuning": True}

    async def tune_done(self, id_: str, keep: bool = True) -> dict:
        """Put the strip back to being a light. `keep` writes the new length down."""
        known = self.strips.get(id_) or {}
        if keep: await self._tell(id_, "count/set", str(known.get("count", ASSUMED)))
        await self._tell(id_, "show/set", "off")
        return {"id": id_, "count": known.get("count", ASSUMED), "tuning": False}

    def _for_tuning(self, id_: str) -> dict:
        if self.job:
            raise StripError("Something else is being set up just now. One at a time.")
        known = self.strips.get(id_)
        if not known:
            raise StripError("That light strip is not one this hub knows about.")
        if not known.get("online"):
            raise StripError("That light strip is not answering just now.")
        return known

    REVISIT = ("colors", "length")

    async def revisit(self, id_: str, what: str) -> dict:
        """Ask one of the setup questions again about a strip that is already in.

        BOTH ANSWERS GO STALE, and none of the ways are unusual. A strip gets cut down to fit a shelf.
        Another gets soldered on to reach round a corner. One fails and is replaced by whatever was in
        stock, which is very often not the same make and therefore not the same channel order. None of
        that should mean setting the thing up again from the beginning, so this is the same
        conversation restarted at the question that has gone wrong, and it ends there rather than
        marching on through the rest of setup. design/strip/Later.dc.html.

        THE COLOR ONE IS NOT A CONVENIENCE. resolve() takes "yes, red" as grb on its odds, which is
        right almost always and silently wrong on a brg strip -- the household sees colors that are
        not the ones they asked for and has no word for what is happening. This is the other half of
        that shortcut. Without it the shortcut is not a shortcut, it is a bug we decided not to fix.
        """
        if what not in self.REVISIT:
            raise StripError("That is not something a light strip can be asked again.")
        if self.job:
            raise StripError("Something else is being set up just now. One at a time.")
        known = self.strips.get(id_)
        if not known:
            raise StripError("That light strip is not one this hub knows about.")
        if not known.get("online"):
            # Every one of these questions works by lighting the thing up, so there is nothing to
            # ask and nothing to look at. Saying so is better than opening a sheet that cannot move.
            raise StripError("That light strip is not answering just now.")
        self.job = {"state": "none", "id": id_, "label": self._label(known),
                    "first": None, "revisit": what, "count": known.get("count", ASSUMED)}
        if what == "colors":
            await self._show_red()
        else:
            await self._fill()
        return self.status()

    # ---- where it is ----
    async def put(self, room_id: str) -> dict:
        if not self.job or self.job["state"] != "room":
            raise StripError("There is no light strip waiting for a room.")
        j = self.job
        j["room"] = room_id
        # Not retained: the strip remembers its own room. See order/set above.
        await self._tell(j["id"], "room/set", room_id)
        if not await self._put_in_room(j["id"], room_id):
            # IT IS NOT GIVEN UP ON, AND THE WALL IS TOLD. This used to log a warning and say "It's
            # in" -- the panel claiming something it knows to be untrue to somebody standing in
            # front of it. The choice is kept and applied the moment the house has a device to apply
            # it to, and until then the last beat says so in words.
            log.info("strip %s: %s is chosen and the house has no device for it yet; holding on to it",
                     j["id"], room_id)
            self._owed[j["id"]] = room_id
            self._keep_placing()
        self._set("ready")
        return self.status()

    def _keep_placing(self) -> None:
        """One task, for as long as any room is still owed."""
        if self._placer and not self._placer.done(): return
        self._placer = asyncio.create_task(self._place_later())

    async def _place_later(self):
        """Go on trying to put strips in the rooms somebody chose, until they land or time is up.

        Discovery is a moment behind everything else and sometimes a long moment: in a house with a
        hundred devices it took more than the twenty seconds `put()` waits. Nothing here is asked of
        the household -- they answered the question once and the answer is kept."""
        end = time.monotonic() + PLACE_KEEP
        while self._owed and time.monotonic() < end:
            await asyncio.sleep(3.0)
            for id_, room_id in list(self._owed.items()):
                if await self._put_in_room(id_, room_id, tries_for=0):
                    self._owed.pop(id_, None)
                    # The wall is saying "it will be in X once the house notices it"; this is the
                    # moment that stops being true, so it is told rather than left to a poll.
                    if self.job and self.job.get("id") == id_: self._set(self.job["state"])
        for id_, room_id in self._owed.items():
            log.warning("strip %s: gave up putting it in %s; it is in the house but unplaced",
                        id_, room_id)
        self._owed.clear()

    async def _put_in_room(self, id_: str, room_id: str, tries_for: float | None = None) -> bool:
        """Move the light we announced into the room somebody chose.

        THIS USED TO BE `self.hub.strip_placed(...)`, A METHOD NO HUB HAS EVER HAD, inside a
        `try/except AttributeError: pass`. So every strip ever set up was left wherever Home Assistant
        first put it, the wall said "It's in", and the household went and did it again by hand.

        It is worth more than one try: the strip announces itself over MQTT discovery and Home
        Assistant makes the device a moment later, so the room can be chosen before there is anything
        to put in it."""
        # PLACE_WAIT is read here rather than taken as a default, because a default is bound when
        # this file is imported and the suite shrinks the constant to keep itself quick.
        end = time.monotonic() + (PLACE_WAIT if tries_for is None else tries_for)
        while True:
            dev = await self._device_for(id_)
            if dev:
                try:
                    await self.hub.ha.send("config/device_registry/update",
                                           device_id=dev, area_id=room_id)
                    log.info("strip %s: put in %s", id_, room_id)
                    return True
                except Exception as e:
                    log.warning("strip %s: the house would not move it (%s)", id_, e)
                    return False
            if time.monotonic() >= end: return False
            await asyncio.sleep(1.0)

    async def done(self) -> dict:
        """The sheet has been read. A finished job has nothing left to say, and until the brain is
        told so it keeps reporting it -- which is somebody pressing OK at a dialog that will not die."""
        self.job = None
        self.hub._broadcast(json.dumps({"type": "strip", "strip": self.status()}))
        return self.status()
