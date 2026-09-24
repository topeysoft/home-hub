# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fix that reaches a bridge -- or a light strip -- where it is, rather than where the cable is.

A bridge is on a charger behind a sofa, and the only way it used to get new software was somebody
carrying it to the hub. docs/puck-updates.md is the design; this is the hub's half of it. The puck's
half is brilliant/esp32-bridge/src/fwupdate.h, and the contract between them is there.

THE TRUST IS THE HUB'S OWN. The image is the one this brain's container carries (releases/bridge/),
and that container was checked against the maker's key before it was allowed to run. So there is no
second signing path for firmware: the key that covers the hub covers what the hub hands a puck. The
puck checks the SHA-256 it was told over the broker, whose credentials only the hub gave it.

WHEN. The bridges take their fixes in the hub's own part of the night, with nobody up, and only in a
house that lets the hub update itself -- a household that turned that off is not overruled for a
puck. ONE AT A TIME: a bad image that strands one puck is a dark corner, and the same image on all
of them is a dead mesh. An offer the puck has not finished with in OFFER_FOR is taken back, and a
version that has come back TRIES times is not offered to that puck again; the puck refuses it too,
on its own count, so the two cannot disagree into a loop.

What the house writes down: a bridge updated, a bridge that went back to what it had, and a bridge
that refused an image because the bytes were not the ones it was told about. Nothing else -- a puck
that was asleep all night is not news.

TWO KINDS, ONE QUEUE. A light strip takes its fixes exactly as a puck does (docs/strip.md, "Updates,
the puck's way"; its half is strip/firmware/main/fwupdate.h), so it is a second Kind here rather than a
copy of this file. Each kind says where its image is, where its offer goes, and what it knows about
each of its devices; everything else -- the window, the tries, the tool -- is shared. And ONE AT A TIME
IS ACROSS THE HOUSE: a strip and a puck dark at once is still two things dark.

A BUILD FROM A WORKING TREE, NOW. On a hub that follows a branch -- a hub being worked on -- a
developer can hand one puck a build straight from their checkout (tools/dev.sh puck) and have it
offered at once rather than at three in the morning. It arrives over ssh, not over HTTP: the tool
parks the image and a request in PUSH, and whoever can do that is already root on this machine, so
it adds no way in that was not there. A hub on releases refuses it, whoever asks. Everything the
puck does with it is unchanged -- hash, trial, rollback, floor -- and the hub writes where it has
got to in PUSH/state.json for the tool to read back.
"""
import asyncio, contextlib, hashlib, json, logging, os, re, time

from .settings import DATA

log = logging.getLogger("hub.bridge")

PATH = "/bridge/firmware/"
OFFER_FOR = 15 * 60          # fetch, write, restart and prove itself take about four minutes
TRIES = 2                    # the puck's GIVE_UP_AFTER, the same number
RETRY = 12 * 3600            # a try a night, as the hub gives itself
PUSH = DATA / "bridge-push"   # request.json + image.bin from tools/dev.sh puck|strip; state.json back
PUSH_EVERY = 2
DEV_VERSION = re.compile(r"^\d+\.\d+\.\d+(-d\d+)?$")
PART_TABLE, PART_MAGIC = 0x8000, b"\xaa\x50"
IMAGE_MAGIC = 0xE9


def app_image(merged: bytes) -> bytes | None:
    """The application out of a merged image, which is what a slot takes.

    releases/bridge/ carries the image a bare board is flashed with from 0x0 -- bootloader, table and
    app together. An update writes only the app, into the slot the puck is not running. Read where
    the app starts from the partition table inside the image itself rather than from a number here,
    so the two cannot drift apart."""
    for at in range(PART_TABLE, PART_TABLE + 0xC00, 32):
        e = merged[at:at + 32]
        if len(e) < 32 or e[:2] != PART_MAGIC: break
        kind, sub, off = e[2], e[3], int.from_bytes(e[4:8], "little")
        if kind == 0 and sub in (0x00, 0x10):          # factory, or ota_0: the first app slot
            app = merged[off:]
            return app if app[:1] == bytes([IMAGE_MAGIC]) else None
    return None


class Kind:
    """What the updater needs to know about one kind of device. Records are the updater's own
    bookkeeping per device: `fw` (what it last said it runs), `offer` and `tries`."""
    key = noun = ""
    tool_list = ""

    def __init__(self, fw: "Firmware"): self.fw = fw
    @property
    def hub(self): return self.fw.hub
    def image_path(self): raise NotImplementedError
    def topic(self, id_: str) -> str: raise NotImplementedError
    def records(self) -> dict: raise NotImplementedError
    def save(self, id_: str, rec: dict) -> None: raise NotImplementedError
    def known(self, id_: str) -> bool: return id_ in self.records()
    def online(self, id_: str) -> bool: raise NotImplementedError
    def behind(self, img: dict) -> list[str]: raise NotImplementedError
    def listing(self) -> list[dict]: raise NotImplementedError
    def where(self, id_: str) -> str | None: return None


class BridgeKind(Kind):
    """Pucks. Their records are the bridges the hub set up, in settings, beside everything else the
    cable wrote about them."""
    key, noun, tool_list = "bridge", "bridge", "bridges.json"

    def image_path(self): return self.fw.b.cable.image
    def topic(self, id_): return f"mesh/bridge/{id_}/offer"
    def records(self): return self.hub.settings.get("bridges") or {}

    def save(self, id_, rec):
        known = self.records()
        if id_ in known: self.hub.settings.set(bridges={**known, id_: rec})

    def online(self, id_): return bool((self.fw.b.pucks.get(id_) or {}).get("online"))

    def behind(self, img):
        return [b["chip"] for b in self.fw.b.behind() if b["online"] and b["latest"] == img["fw"]]

    def listing(self):
        return [{k: b.get(k) for k in ("chip", "room", "fw", "online")} for b in self.fw.b.each()]


class StripKind(Kind):
    """Light strips. The hub knows a strip from the broker rather than from settings, so the updater
    keeps its own small record per strip, begun the first time one says what it runs -- which a strip
    from before updates never does, and that is right: it has nothing that could take one."""
    key, noun, tool_list = "strip", "light strip", "strips.json"

    def image_path(self):
        from .bridge import SHIP
        return SHIP.parent / "strip" / "esp32s3-ship.bin"

    def topic(self, id_):
        from .strip import BASE
        return f"{BASE}/{id_}/offer"

    def records(self): return self.hub.settings.get("strip_fw") or {}

    def save(self, id_, rec):
        self.hub.settings.set(strip_fw={**self.records(), id_: rec})

    def _strips(self) -> dict:
        s = getattr(self.hub, "strip", None)
        return getattr(s, "strips", None) or {}

    def known(self, id_): return id_ in self._strips()
    def online(self, id_): return bool((self._strips().get(id_) or {}).get("online"))

    def behind(self, img):
        from .bridge import Bridges
        return sorted(i for i, r in self.records().items()
                      if self.online(i) and Bridges._older(str(r.get("fw") or ""), img["fw"]))

    def where(self, id_: str) -> str | None:
        """The room it is in, through the house's own device for it -- known once the panel has
        asked (Strips.each), which is soon after any strip is set up."""
        hw = (getattr(getattr(self.hub, "strip", None), "_devices", None) or {}).get(id_)
        home = getattr(self.hub, "home", None)
        if not (hw and home): return None
        for d in home.devices.values():
            if d.hw == hw:
                room = home.rooms.get(d.room_id)
                return room.name if room else None
        return None

    def listing(self):
        return [{"chip": i, "room": self.where(i), "fw": (self.records().get(i) or {}).get("fw"),
                 "online": self.online(i)} for i in sorted(self._strips())]


class Firmware:
    def __init__(self, bridges):
        self.b = bridges
        self.kinds = {k.key: k for k in (BridgeKind(self), StripKind(self))}
        self._cache: dict[str, tuple] = {}      # kind -> (stamp, image): a MB file is not re-read every tick
        self.dev: dict | None = None            # a working-tree build being offered to one device

    @property
    def hub(self): return self.b.hub

    # ---- the image ----
    def image(self, kind: str = "bridge") -> dict | None:
        """{"fw", "sha256", "size", "body"} of the app this house would give a device, or None."""
        path = self.kinds[kind].image_path()
        try:
            st = path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
            if kind in self._cache and self._cache[kind][0] == stamp: return self._cache[kind][1]
            fw = str(json.loads(path.with_suffix(".json").read_text()).get("fw") or "")
            body = app_image(path.read_bytes())
        except (OSError, ValueError):
            return None
        img = {"fw": fw, "sha256": hashlib.sha256(body).hexdigest(), "size": len(body), "body": body} \
            if fw and body else None
        self._cache[kind] = (stamp, img)
        return img

    def served(self, name: str) -> bytes | None:
        """The bytes at PATH<sha>.bin -- today's images and no others, so a device can only ever be
        handed what the hub is offering."""
        for img in (*(self.image(k) for k in self.kinds), self.dev):
            if img and name == f"{img['sha256']}.bin": return img["body"]
        return None

    # ---- what the devices say ----
    def heard_fw(self, id_: str, fw: str, kind: str = "bridge") -> None:
        """What a device runs, from its own mouth. The cable used to be the only way the hub learned
        this, so a puck updated anywhere else would have been counted as behind for ever."""
        k = self.kinds[kind]
        if not fw or not k.known(id_): return
        rec = k.records().get(id_) or {}
        if rec.get("fw") != fw: k.save(id_, {**rec, "fw": fw})

    async def heard(self, id_: str, payload: str, now: float | None = None, kind: str = "bridge") -> None:
        try: said = json.loads(payload)
        except ValueError: return
        k = self.kinds[kind]
        state, fw = str(said.get("state") or ""), str(said.get("fw") or "")
        rec = k.records().get(id_)
        if rec is None: return
        offer = rec.get("offer") or {}
        if offer.get("dev"): self._tell_tool(id_, fw, state, str(said.get("why") or ""))
        detail = {"fw": fw, **({"room": r} if (r := k.where(id_)) else {})}
        if state == "installed":
            self.hub.log.add(kind, id_, None, "updated", source="hub", detail=detail)
            if offer.get("fw") == fw: await self.withdraw(id_, kind=kind)
            return
        if state == "rolledback":
            self.hub.log.add(kind, id_, None, "went back", source="hub", detail=detail)
        elif state == "refused" and said.get("why") == "hash":
            # A refusal is not a failure: the device did its job. It is written down because the
            # house was handed bytes it did not mean to hand out, and somebody may want to know.
            self.hub.log.add(kind, id_, None, "refused an update", source="hub", detail=detail)
        # Whatever the reason, this offer is done with, and it counts: a device that will not take a
        # version tonight is not asked again tonight.
        if offer and state in ("rolledback", "failed", "refused"):
            await self.withdraw(id_, failed=not offer.get("dev"), now=now, kind=kind)

    # ---- offering ----
    def _may(self, now: float) -> bool:
        u = getattr(self.hub, "updates", None)
        return bool(u and u.auto and u.quiet_hours(now))

    async def _say(self, kind: str, id_: str, payload: str) -> None:
        with contextlib.suppress(Exception):
            await self.hub.ha.call("mqtt", "publish", None,
                                   topic=self.kinds[kind].topic(id_), payload=payload, retain=True)

    async def offer(self, id_: str, img: dict, now: float | None = None, dev: bool = False,
                    kind: str = "bridge") -> None:
        port = os.environ.get("HUB_PORT", "8300")
        await self._say(kind, id_, f"{img['fw']} {img['size']} {img['sha256']} {port} {PATH}{img['sha256']}.bin")
        k = self.kinds[kind]
        o = {"fw": img["fw"], "at": now or time.time(), **({"dev": True} if dev else {})}
        k.save(id_, {**(k.records().get(id_) or {}), "offer": o})
        log.info("%s: offered %s to %s", kind, img["fw"], id_)

    async def withdraw(self, id_: str, failed: bool = False, now: float | None = None,
                       kind: str = "bridge") -> None:
        """Take the retained offer off the broker, so a device that reconnects at noon does not take
        it then. `failed` counts a try against the version."""
        await self._say(kind, id_, "")
        k = self.kinds[kind]
        if id_ not in k.records(): return
        rec = dict(k.records()[id_])
        fw = (rec.pop("offer", None) or {}).get("fw")
        if failed and fw:
            t = rec.get("tries") or {}
            rec["tries"] = {"fw": fw, "n": (t.get("n", 0) if t.get("fw") == fw else 0) + 1, "at": now or time.time()}
        k.save(id_, rec)

    async def tick(self, now: float | None = None) -> None:
        """Every few minutes, from the hub's own update loop."""
        now = now or time.time()
        may = self._may(now)
        busy = False
        for key, k in self.kinds.items():
            img = self.image(key)
            for id_, rec in list(k.records().items()):
                o = rec.get("offer")
                if not o: continue
                # A working-tree build is not the shipped image and does not wait for the night:
                # only silence ends it, and silence is not held against the version.
                if o.get("dev"):
                    if now - o.get("at", 0) > OFFER_FOR:
                        self._tell_tool(id_, o.get("fw", ""), "failed", "no answer")
                        await self.withdraw(id_, now=now, kind=key)
                    else: busy = True
                    continue
                if not img or o.get("fw") != img["fw"]: await self.withdraw(id_, now=now, kind=key)
                elif now - o.get("at", 0) > OFFER_FOR: await self.withdraw(id_, failed=True, now=now, kind=key)
                # Past the window it is taken back, uncounted: the device was not given its chance.
                elif not may: await self.withdraw(id_, now=now, kind=key)
                else: busy = True
        if busy or not may: return
        for key, k in self.kinds.items():
            img = self.image(key)
            if not img: continue
            for id_ in k.behind(img):
                t = (k.records().get(id_) or {}).get("tries") or {}
                if t.get("fw") == img["fw"] and (t.get("n", 0) >= TRIES or now - t.get("at", 0) < RETRY): continue
                await self.offer(id_, img, now, kind=key)
                return

    # ---- a build from a working tree, now ----
    def _tell_tool(self, id_: str, fw: str, state: str, why: str = "") -> None:
        with contextlib.suppress(OSError):
            PUSH.mkdir(parents=True, exist_ok=True)
            (PUSH / "state.json").write_text(json.dumps(
                {"chip": id_, "fw": fw, "state": state, "why": why, "at": time.time()}))

    async def watch(self) -> None:
        """Look for a parked build every couple of seconds. Started once, with the rest of the house."""
        listed: dict[str, str] = {}
        while True:
            try:
                if (PUSH / "request.json").exists(): await self.take_push()
                for key in self.kinds: listed[key] = self.list_for_tool(listed.get(key), kind=key)
            except Exception: log.exception("bridge: taking a pushed build")
            await asyncio.sleep(PUSH_EVERY)

    def list_for_tool(self, was: str | None = None, kind: str = "bridge") -> str:
        """The devices as the tool needs them -- which chip is in which room, what it runs, whether it
        is on the broker -- so a developer can say "hallway" and never has to know a chip id. Written
        only when it changes: the room is the brain's to work out, and nothing outside it can."""
        k = self.kinds[kind]
        now = json.dumps(k.listing())
        if now != was:
            with contextlib.suppress(OSError):
                PUSH.mkdir(parents=True, exist_ok=True)
                (PUSH / k.tool_list).write_text(now)
        return now

    async def take_push(self, now: float | None = None) -> None:
        req_file, body_file = PUSH / "request.json", PUSH / "image.bin"
        try:
            req = json.loads(req_file.read_text())
            body = body_file.read_bytes()
        except (OSError, ValueError):
            req, body = {}, b""
        # Taken once, whatever happens next: a request left lying about is one somebody forgot.
        for f in (req_file, body_file):
            with contextlib.suppress(OSError): f.unlink()
        id_, fw, kind = str(req.get("chip") or ""), str(req.get("fw") or ""), str(req.get("kind") or "bridge")
        k = self.kinds.get(kind)
        u = getattr(self.hub, "updates", None)
        from .updates import BRANCHES
        why = ("this hub follows releases, and a release hub takes only released firmware"
               if not (u and u.channel in BRANCHES) else
               f"{kind!r} is not something this hub updates" if k is None else
               f"{id_ or 'that'} is not a {k.noun} this hub knows" if not k.known(id_) else
               f"{id_} is not on the broker right now" if not k.online(id_) else
               f"{fw!r} is not a version (0.6.1, or 0.6.1-d<n>)" if not DEV_VERSION.match(fw) else
               "that is not an ESP32 app image" if body[:1] != bytes([IMAGE_MAGIC]) else "")
        if why:
            log.info("%s: refused a pushed build for %s: %s", kind, id_, why)
            self._tell_tool(id_, fw, "refused", why)
            return
        if (k.records().get(id_) or {}).get("offer"):
            await self.withdraw(id_, now=now, kind=kind)             # tonight's can wait; this was asked for
        self.dev = {"fw": fw, "sha256": hashlib.sha256(body).hexdigest(), "size": len(body), "body": body}
        await self.offer(id_, self.dev, now, dev=True, kind=kind)
        self._tell_tool(id_, fw, "offered")
        self.hub.log.add(kind, id_, None, "sent a test build", source="hub", detail={"fw": fw})
