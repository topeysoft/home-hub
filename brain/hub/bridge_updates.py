# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A fix that reaches a bridge where it is, rather than where the cable is.

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
"""
import contextlib, hashlib, json, logging, os, time

log = logging.getLogger("hub.bridge")

PATH = "/bridge/firmware/"
OFFER_FOR = 15 * 60          # fetch, write, restart and prove itself take about four minutes
TRIES = 2                    # the puck's GIVE_UP_AFTER, the same number
RETRY = 12 * 3600            # a try a night, as the hub gives itself
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


class Firmware:
    def __init__(self, bridges):
        self.b = bridges
        self._cache: tuple | None = None       # (stamp, image) so a 1 MB file is not re-read every tick

    @property
    def hub(self): return self.b.hub

    # ---- the image ----
    def image(self) -> dict | None:
        """{"fw", "sha256", "size", "body"} of the app this house would give a puck, or None."""
        path = self.b.cable.image
        try:
            st = path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
            if self._cache and self._cache[0] == stamp: return self._cache[1]
            fw = str(json.loads(path.with_suffix(".json").read_text()).get("fw") or "")
            body = app_image(path.read_bytes())
        except (OSError, ValueError):
            return None
        img = {"fw": fw, "sha256": hashlib.sha256(body).hexdigest(), "size": len(body), "body": body} \
            if fw and body else None
        self._cache = (stamp, img)
        return img

    def served(self, name: str) -> bytes | None:
        """The bytes at PATH<sha>.bin -- the current image and no other, so a puck can only ever be
        handed what the hub is offering today."""
        img = self.image()
        return img["body"] if img and name == f"{img['sha256']}.bin" else None

    # ---- what the pucks say ----
    def heard_fw(self, chip: str, fw: str) -> None:
        """What a puck runs, from its own mouth. The cable used to be the only way the hub learned
        this, so a puck updated anywhere else would have been counted as behind for ever."""
        known = self.hub.settings.get("bridges") or {}
        rec = known.get(chip)
        if rec is None or not fw or rec.get("fw") == fw: return
        self.hub.settings.set(bridges={**known, chip: {**rec, "fw": fw}})

    async def heard(self, chip: str, payload: str, now: float | None = None) -> None:
        try: said = json.loads(payload)
        except ValueError: return
        state, fw = str(said.get("state") or ""), str(said.get("fw") or "")
        known = self.hub.settings.get("bridges") or {}
        rec = known.get(chip)
        if rec is None: return
        offer = rec.get("offer") or {}
        if state == "installed":
            self.hub.log.add("bridge", chip, None, "updated", source="hub", detail={"fw": fw})
            if offer.get("fw") == fw: await self.withdraw(chip)
            return
        if state == "rolledback":
            self.hub.log.add("bridge", chip, None, "went back", source="hub", detail={"fw": fw})
        elif state == "refused" and said.get("why") == "hash":
            # A refusal is not a failure: the puck did its job. It is written down because the
            # house was handed bytes it did not mean to hand out, and somebody may want to know.
            self.hub.log.add("bridge", chip, None, "refused an update", source="hub", detail={"fw": fw})
        # Whatever the reason, this offer is done with, and it counts: a puck that will not take a
        # version tonight is not asked again tonight.
        if offer and state in ("rolledback", "failed", "refused"): await self.withdraw(chip, failed=True, now=now)

    # ---- offering ----
    def _may(self, now: float) -> bool:
        u = getattr(self.hub, "updates", None)
        return bool(u and u.auto and u.quiet_hours(now))

    async def _say(self, chip: str, payload: str) -> None:
        from .bridge import BASE
        with contextlib.suppress(Exception):
            await self.hub.ha.call("mqtt", "publish", None,
                                   topic=f"{BASE}/bridge/{chip}/offer", payload=payload, retain=True)

    async def offer(self, chip: str, img: dict, now: float | None = None) -> None:
        port = os.environ.get("HUB_PORT", "8300")
        await self._say(chip, f"{img['fw']} {img['size']} {img['sha256']} {port} {PATH}{img['sha256']}.bin")
        known = self.hub.settings.get("bridges") or {}
        self.hub.settings.set(bridges={**known, chip: {**known[chip], "offer": {"fw": img["fw"], "at": now or time.time()}}})
        log.info("bridge: offered %s to %s", img["fw"], chip)

    async def withdraw(self, chip: str, failed: bool = False, now: float | None = None) -> None:
        """Take the retained offer off the broker, so a puck that reconnects at noon does not take it
        then. `failed` counts a try against the version."""
        await self._say(chip, "")
        known = self.hub.settings.get("bridges") or {}
        rec = dict(known.get(chip) or {})
        fw = (rec.pop("offer", None) or {}).get("fw")
        if failed and fw:
            t = rec.get("tries") or {}
            rec["tries"] = {"fw": fw, "n": (t.get("n", 0) if t.get("fw") == fw else 0) + 1, "at": now or time.time()}
        if chip in known: self.hub.settings.set(bridges={**known, chip: rec})

    async def tick(self, now: float | None = None) -> None:
        """Every few minutes, from the hub's own update loop."""
        now = now or time.time()
        img = self.image()
        may = self._may(now)
        busy = False
        for chip, rec in (self.hub.settings.get("bridges") or {}).items():
            o = rec.get("offer")
            if not o: continue
            if not img or o.get("fw") != img["fw"]: await self.withdraw(chip, now=now)
            elif now - o.get("at", 0) > OFFER_FOR: await self.withdraw(chip, failed=True, now=now)
            # Past the window it is taken back, uncounted: the puck was not given its chance.
            elif not may: await self.withdraw(chip, now=now)
            else: busy = True
        if busy or not img or not may: return
        for b in self.b.behind():
            if not b["online"] or b["latest"] != img["fw"]: continue
            t = ((self.hub.settings.get("bridges") or {}).get(b["chip"]) or {}).get("tries") or {}
            if t.get("fw") == img["fw"] and (t.get("n", 0) >= TRIES or now - t.get("at", 0) < RETRY): continue
            await self.offer(b["chip"], img, now)
            return
