# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A bridge puck on the hub's cable, and the bridges the house already has.

A bridge is a small thing on a USB charger that brings in devices the hub has no radio of its own
for -- today the wall switches on the Brilliant mesh (brilliant/esp32-bridge). Setting one up is
design/puck/Cable.dc.html: plug it into the hub once, the hub gives it everything -- its software if
it has none, the Wi-Fi, the broker, the keys to the switches -- and then says where to put it. The
panel draws the state this module hands it (app/src/BridgeSheet.vue) and sends back the two answers
a person can give: yes that one is mine, and leave it here.

One job at a time, because it is a person holding a thing.

    none      nothing to say
    knocking  a puck is on the cable and nobody has said it is theirs. Nothing of the house's has
              gone anywhere: the code gate on /bridge/adopt (hub/lock.py) is what "nothing has been
              let in" means. Saying it is not yours needs no code -- refusing gives nothing away
    working   `step` is software | wifi | keys, in that order; everything before it is done
    placing   written and restarted; unplugged now, in somebody's hand, looking for a socket. What
              it hears comes back over the broker, which is the only link left
    ready     placed. `switches` came in with it; `unplaced` of them have no room yet
    failed    `text` says why, in words for the wall

The serial side (pyserial, esptool) is behind `Cable`, so the machine is tested with a fake one
and nothing here needs a puck to run.

Bridges the house already has are learned from the broker, not from the cable: every puck publishes
`<base>/bridge/<chip>/status` (retained, online|offline), `.../net` (the mesh it carries) and
`.../proxy` (the switch it is linked to, and how strongly); the switches under `<base>/<net>/<addr>/`
are counted per net. This subscribes through the engine's own MQTT link, the way pairing.py does.
"""
import asyncio, contextlib, json, logging, os, re, secrets, signal, socket, sys, time
from pathlib import Path

log = logging.getLogger("hub.bridge")

SHIP = Path(os.environ.get("HUB_NOTES") or Path(__file__).resolve().parent.parent.parent / "releases") / "bridge"
DEV = Path("/dev/serial/by-id")
SCAN_EVERY = 3
# Long enough for two connect attempts on a sleepy board, short enough that a board which
# will never answer does not hold the one job slot for a minute.
PROBE_SECONDS = 45
# A freshly enumerated board can answer badly once; by hand it answers every time. Waiting
# a moment and asking again costs nothing and is the difference between a board being seen
# and a board being written off.
PROBE_RETRY = 2
# Fast first, then a speed that holds on hardware where the fast one does not. A minute
# longer on a job somebody does once is a fair price for it finishing.
FLASH_BAUDS = (460800, 115200)
FLASH_SECONDS = 300
# Probing a board resets it, and a board being reset drops off the USB and comes back a
# moment later. That is OUR doing, not a person's, and must not be read as an unplug --
# otherwise a dismissal never sticks: the board vanishes, is forgiven, reappears as a fresh
# arrival, and knocks again faster than anybody can dismiss it. Observed on a bare C3:
# knock, refuse, dismiss, knock again, for as long as somebody kept pressing OK.
# How long to wait on a puck for each kind of question. A survey is one BLE scan;
# a claim is a whole handshake over a link that may be weak. Named so the tests
# can shrink them -- a suite that waits out a real timeout teaches people to skip it.
SURVEY_WAIT = 20
CLAIM_WAIT = 90
# a radio stick is never a bridge, and must never be probed: esptool's sync toggles DTR/RTS, which
# resets it. The same names driver-layer/radios.sh recognizes.
RADIO = re.compile(r"skyconnect|zbt-|zbdongle|sonoff|mg24|cc2652|zigbee|efr32|nabu|zooz|z-wave|zwave|aeotec|pzg23|hubz", re.I)
STEPS = ("software", "wifi", "keys")
BASE = "mesh"


def network_id(netkey: bytes) -> str:
    """k3(netkey): the eight bytes a puck publishes to say which mesh it carries.

    Mesh Profile 1.0.1 section 3.8.2.6. The hub needs it for one question only -- is that
    puck out there on MY network or somebody else's -- and the answer decides whether a
    working bridge gets adopted or offered a rebuild it does not need."""
    from cryptography.hazmat.primitives.cmac import CMAC
    from cryptography.hazmat.primitives.ciphers import algorithms

    def cmac(key: bytes, msg: bytes) -> bytes:
        c = CMAC(algorithms.AES(key)); c.update(msg); return c.finalize()

    salt = cmac(b"\x00" * 16, b"smk3")          # s1("smk3")
    t = cmac(salt, netkey)
    return cmac(t, b"id64" + b"\x01")[-8:].hex()


def _hx(s: str) -> str:
    """A free-text argument as hex, the way the cable protocol already sends one (config.h)."""
    return (s or "").encode("utf-8").hex()


def _hostname() -> str:
    """The name this hub answers to, for a puck to resolve instead of remembering a number.

    Read rather than assumed: install.sh sets `hub`, but a second hub on the same LAN becomes
    `hub-2`, and a puck told the wrong name eventually resolves somebody else's machine."""
    try:
        n = socket.gethostname().split(".")[0].strip()
        return n or "hub"
    except Exception:
        return "hub"


def lan_ip() -> str:
    """The address the puck should talk to: this hub's, on the house's network. No packet is sent."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]; s.close(); return ip
    except OSError:
        return "127.0.0.1"


# ---------------------------------------------------------------- the cable

def _puck():
    """The protocol client, brilliant/tools/puck_cable.py: one source of truth, used from the bench
    and from here. The brain's image copies it in as tools_puck.py; a dev checkout finds it in place."""
    import importlib, importlib.util
    try: return importlib.import_module("tools_puck")
    except ModuleNotFoundError: pass
    src = Path(__file__).resolve().parent.parent.parent / "brilliant" / "tools" / "puck_cable.py"
    spec = importlib.util.spec_from_file_location("tools_puck", src)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


class BridgeError(RuntimeError):
    """A failure whose message was written for the person standing in front of the panel.

    Everything else that can be raised in here was written for a log -- "no esp32s3 image", a
    serial port's own words, or whatever a library felt like saying. Those must not reach a screen:
    a bridge once failed with "database is locked" on it, which tells the person nothing and is not
    even true about their bridge. So the catch-all says a house sentence, and only these come
    through as themselves.
    """


class Cable:
    """What the brain does to a puck over its USB port. Every call blocks on serial and runs in a thread."""

    def __init__(self, image: Path = SHIP / "esp32s3-ship.bin"):
        self.image = image

    async def _in_thread(self, fn, *a):
        return await asyncio.get_running_loop().run_in_executor(None, fn, *a)

    async def hello(self, port: str) -> dict | None:
        """{"chip", "fw", "state"} if a bridge answers within its boot; None if nothing does."""
        def go():
            Puck = _puck().Puck
            try:
                p = Puck(port)
                try: return p.hello(patience=10.0)
                finally: p.s.close()
            except Exception as e:
                log.debug("%s: no hello (%s)", port, e); return None
        return await self._in_thread(go)

    async def is_esp(self, port: str) -> bool:
        return await self.esp_chip(port) is not None

    async def esp_chip(self, port: str, tries: int = 2) -> str | None:
        """Ask more than once. A board that has just enumerated answers badly now and again
        -- "Unexpected chip magic value 0x00000009" is a half-synced connection, not a
        verdict -- and by hand the same board on the same hub answers every time. One bad
        sync used to be the end of it, and the board was never seen again."""
        for attempt in range(tries):
            chip = await self._esp_chip_once(port)
            if chip:
                return chip
            if attempt + 1 < tries:
                await asyncio.sleep(PROBE_RETRY)
        return None

    async def _esp_chip_once(self, port: str) -> str | None:
        """Which ESP this is -- "esp32s3", "esp32c3" -- or None if it is not one at all.

        Two things had to be got right here and both were got wrong first.

        ASK ESPTOOL, DO NOT READ ITS SCREEN. Running esptool.main() and looking for "Chip is
        ..." in captured stdout fails silently on esptool 5.x, which prints through rich --
        rich binds the real stdout when it is imported, so redirect_stdout sees nothing.
        detect_chip() hands back the loader and the loader knows its own name.

        AND RUN IT WHERE ITS CHILDREN CANNOT OUTLIVE IT. esptool spawns a multiprocessing
        helper, and that helper can be left holding the serial port after the call returns.
        In a brain that never restarts, one probe then poisons every probe after it: the
        first board is identified, and every board after it -- for days -- comes back "the
        port is busy" and never knocks. That is exactly what a hub did, and from a hallway it
        looks like the feature simply does not work. A subprocess we wait on takes its whole
        family with it when it goes.
        """
        # The marker goes on a line of its OWN: esptool's progress ("Detecting chip type...")
        # is printed by rich without a trailing newline, so a bare print lands glued to the
        # end of it. Starting with a newline, and matching anywhere below rather than at the
        # start of a line, are belt and braces for the same mistake -- which cost an evening
        # once already, with the answer sitting in the log being thrown away.
        code = ("import sys, esptool\n"
                "d = esptool.detect_chip(sys.argv[1], connect_attempts=3)\n"
                "print('\\nCHIP=' + d.CHIP_NAME, flush=True)\n")
        try:
            # Its own session, so the whole family can be killed by group. Reaping the child
            # alone is not enough: esptool's multiprocessing helpers are GRANDchildren and
            # they outlive it holding the port, which is the bug this is here to stop.
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-c", code, port,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                start_new_session=True)
        except Exception as e:
            log.warning("bridge: could not probe %s (%s)", port, e)
            return None
        timed_out = False
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=PROBE_SECONDS)
        except TimeoutError:
            timed_out, out = True, b""
        finally:
            # Always, not only on timeout: a probe that answered perfectly well can still
            # have left a helper behind, and one of those poisons every probe after it.
            try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError): pass
            with contextlib.suppress(Exception): await proc.wait()
        if timed_out:
            log.info("bridge: %s did not answer as an ESP (gave up after %ss)", port, PROBE_SECONDS)
            return None
        said = out.decode(errors="replace")
        if (m := re.search(r"CHIP=([\w-]+)", said)):
            # "ESP32-S3" -> esp32s3, the name esptool wants back as --chip
            return m.group(1).strip().lower().replace("-", "").replace(" ", "")
        tail = " / ".join(l.strip() for l in said.splitlines() if l.strip())[-300:]
        log.info("bridge: %s did not answer as an ESP -- %s", port, tail or "(it said nothing)")
        return None

    def image_for(self, chip: str | None) -> Path | None:
        """The shipped image for this chip, if the house has one.

        Releases are named per chip (esp32s3-ship.bin). A board the house has no image for is
        not a failure of the board, and saying so is the difference between "that did not work"
        and a sentence somebody can act on."""
        if not chip:
            return None
        want = self.image.parent / f"{chip}-ship.bin"
        return want if want.exists() else None

    @staticmethod
    def _why(out: str, rc: int) -> str:
        """What a write that did not finish means to somebody holding the board.

        esptool's own sentence on a wall panel is a bug this file has already fixed once, for the
        wrong chip (tests/test_bridge.py, ABoardTheHouseCannotUse). This is the same leak on the
        write: a household got "No more data to read from the serial port" and a link to somebody's
        developer documentation. The raw text stays in the log for whoever is debugging; what reaches
        the screen is the thing they can actually do about it.
        """
        s = (out or "").lower()
        if rc == -1:
            return "Writing its software took too long and stopped. Unplug it, plug it back in, and try again."
        if "no more data to read" in s or "serial data stream stopped" in s:
            # Both speeds have already been tried by the time this is raised, so the line itself is
            # the suspect rather than how fast it was being driven.
            return ("Writing its software kept stopping part way. A different cable usually fixes it, "
                    "or plugging it straight into the hub rather than through anything in between.")
        if "failed to connect" in s or "wrong boot mode" in s or "no serial data received" in s:
            return "It stopped answering while the hub was writing to it. Unplug it, plug it back in, and try again."
        if "permission denied" in s or "could not open" in s:
            return "The hub could not reach it over the cable."
        return "Its software could not be written. Unplug it, plug it back in, and try again."

    async def flash(self, port: str, chip: str = "esp32s3"):
        """Write the image, dropping to a slower line if a fast one does not hold.

        460800 is fine over a Mac's USB and marginal over a Pi's: a real write got to 65% of
        634kB and then "No more data to read from the serial port", which is what a line that
        cannot keep up looks like. Falling back costs a minute on a job somebody does once,
        and the alternative is a bridge that cannot be set up on the hardware it ships on.

        In a subprocess for the same reason the probe is: esptool leaves multiprocessing
        helpers behind, and one of those holding the port poisons everything after it."""
        image = self.image_for(chip)
        if not image:
            log.warning("bridge: no image for %s", chip)
            raise BridgeError("This is a kind of board the hub has no software for.")
        last = ""
        for baud in FLASH_BAUDS:
            log.info("bridge: writing %s to %s at %s baud", image.name, port, baud)
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "esptool", "--chip", chip, "--port", port,
                "--baud", str(baud), "--before", "default-reset", "--after", "hard-reset",
                "write-flash", "-z", "--flash-mode", "dio", "--flash-freq", "80m",
                "--flash-size", "16MB", "0x0", str(image),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                start_new_session=True)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=FLASH_SECONDS)
                rc = proc.returncode
            except TimeoutError:
                out, rc = b"", -1
            finally:
                try: os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError): pass
                with contextlib.suppress(Exception): await proc.wait()
            if rc == 0:
                return
            last = " / ".join(l.strip() for l in out.decode(errors="replace").splitlines()
                              if l.strip() and "Writing at" not in l)[-300:]
            log.info("bridge: %s baud did not hold (%s)", baud, last or f"exit {rc}")
        log.warning("bridge: the write did not finish on %s: %s", port, last or f"exit {rc}")
        raise BridgeError(self._why(last, rc))

    async def write(self, port: str, cfg: dict) -> dict:
        """Everything in cfg, then apply, then wait for it back. Returns its hello afterwards."""
        def go():
            m = _puck(); Puck, hx = m.Puck, m.hx
            p = Puck(port); p.hello(patience=10.0)
            p.set("wifi", hx(cfg["ssid"]), hx(cfg["pass"]))
            # The hub's NAME as well as its address, so this puck survives the house's DHCP pool
            # being reshuffled -- which used to strand every puck without anybody touching the
            # Wi-Fi at all. docs/network.md, piece 1.
            #
            # OPTIONAL, because a puck is always older than the hub setting it up. `set name` arrived
            # in firmware 0.4.0 and the hub does not reflash a puck that still answers, so every puck
            # already in a house refuses this verb -- and refusing one field must not fail an
            # adoption that is otherwise fine. Without the name it uses the address, exactly as it
            # did before any of this existed.
            if not p.set("name", hx(cfg["name"]), required=False):
                log.info("bridge: %s is too old for a hub name; it will use the address", port)
            p.set("mqtt", hx(cfg["host"]), str(cfg["port"]), hx(cfg["user"]), hx(cfg["mqtt_pass"]))
            p.set("keys", cfg["netkey"], cfg["appkey"], str(cfg["iv"]))
            p.set("base", hx(cfg["base"]))
            p.set("label", hx(cfg["label"]))
            p.apply()
            time.sleep(2)
            last = None
            for _ in range(30):
                try:
                    q = Puck(port); who = q.hello(patience=4.0); q.s.close(); return who
                except Exception as e:
                    last = e; time.sleep(1)
            log.warning("bridge: it did not come back on the cable (%s)", last)
            raise BridgeError("It did not come back on the cable after it was written to. Unplug it, "
                              "plug it back into the hub, and it will pick up where it left off.")
        return await self._in_thread(go)


# ---------------------------------------------------------------- the house's bridges

class Bridges:
    def __init__(self, hub, cable: Cable | None = None, devdir: Path = DEV):
        self.hub = hub
        self.cable = cable or Cable()
        self.devdir = devdir
        self.job: dict | None = None
        self._seen: set[str] = set()          # ports present at the last look
        self._dismissed: set[str] = set()     # "not mine": left alone until a person unplugs it
        self._probing: set[str] = set()       # ports we are resetting right now, by asking
        self._pending: list[str] = []         # seen, not yet probed: probing is one at a time
        self._task: asyncio.Task | None = None
        self._quiet: asyncio.Task | None = None   # the placing watch; see _placing_went_quiet
        self._sub: int | None = None
        # what the broker says: chip -> {"online", "net", "rssi"}; (net, addr) -> state
        self.pucks: dict[str, dict] = {}
        self.switches: dict[tuple, str] = {}
        self._heard: dict[str, dict] = {}       # the last answer to a claim command, per leaf
        self.moving: dict | None = None         # every bridge being handed a new Wi-Fi at once
        self._move_task: asyncio.Task | None = None
        self._woke: asyncio.Event | None = None  # made per question, inside the loop asking it
        self._first = True
        from .bridge_updates import Firmware
        self.firmware = Firmware(self)          # a fix that reaches a bridge where it is

    # ---- what the panel sees ----
    def status(self) -> dict:
        base = {"bridges": sum(1 for p in self.pucks.values() if p.get("online")), "waiting": 0}
        if (mv := self.move_status()): base["moving"] = mv
        # Said whether or not a job is running: it is a standing fact about the house, not a step in
        # setting anything up, and This hub is where somebody goes to look at standing facts.
        if (old := self.behind()): base["behind"] = old
        if not self.job: return {**base, "state": "none"}
        j = self.job
        out = {**base, "state": j["state"], "how": "cable"}
        if j["state"] == "working": out["step"] = j["step"]
        if j["state"] in ("placing", "ready"):
            out["switches"] = self._count(j.get("net")); out["signal"] = self._signal(j.get("chip"))
        if j["state"] == "placing" and j.get("quiet"): out["quiet"] = True
        if j["state"] == "ready": out["unplaced"] = j.get("unplaced", 0)
        if j.get("text"): out["text"] = j["text"]
        if j.get("needs"): out["needs"] = j["needs"]
        # The network the hub is standing on, when that is what it is asking the password for. The
        # panel shows it rather than asking for it again.
        if j.get("ssid"): out["ssid"] = j["ssid"]
        return out

    def _set(self, state, **more):
        if not self.job: return
        self.job.update(state=state, **more)
        self.hub._broadcast(json.dumps({"type": "bridge", "bridge": self.status()}))

    # ---- the cable: noticing a puck ----
    async def listen(self):
        """The broker's view of every bridge, through the engine's own MQTT link -- asked for until it
        is given, for the reason hub/strip.py's listen() gives: after a deploy HA's MQTT is not there
        yet, and a brain that asked once saw no bridge, no switch and no errand until restarted."""
        from .strip import subscribe_until_answered
        self._sub = await subscribe_until_answered(self.hub, "bridge", self._on_mqtt, f"{BASE}/#")

    async def watch(self):
        """Every few seconds: what is on the USB now that was not before. Runs for the life of the brain."""
        # Not awaited: the cable is worth watching while the broker is still coming up.
        asyncio.ensure_future(self.listen())
        while True:
            try: await self.scan()
            except Exception as e: log.warning("bridge scan: %s", e)
            await asyncio.sleep(SCAN_EVERY)

    def _ports(self) -> set[str]:
        """USB serial ports, by their stable names. Linux gives them under /dev/serial/by-id; a Mac
        running the brain at a desk has no such thing, so there it is /dev's cu.* devices instead."""
        try: return {str(self.devdir / n) for n in os.listdir(self.devdir)}
        except FileNotFoundError:
            if self.devdir != DEV: return set()
            try: return {f"/dev/{n}" for n in os.listdir("/dev") if re.match(r"cu\.(usb|wchusb)", n)}
            except FileNotFoundError: return set()

    async def scan(self):
        now = self._ports()
        new, gone = now - self._seen, self._seen - now
        self._seen = now
        # A port that went while we were resetting it did not really go: forgive only the
        # ones a person actually pulled out.
        self._dismissed -= (gone - self._probing)
        if self.job and self.job.get("port") in gone and self.job["state"] in ("knocking", "working"):
            # unplugged under us. Knocking: the offer is withdrawn. Working: that is a failure worth a sentence.
            if self.job["state"] == "knocking": self.job = None; self.hub._broadcast(json.dumps({"type": "bridge", "bridge": self.status()}))
            else: self._set("failed", text="The bridge was unplugged before the hub had finished. Plug it back into the hub and it starts again from the beginning.")
        if self._first:
            # What was there at boot did not "just arrive", and treating it as an arrival
            # would have the hub offering to set up things it has offered before. But it has
            # never been LOOKED AT either, and a board sitting on the cable when the brain
            # starts is not a rare case -- it is what happens on every deploy, every reboot,
            # and every time anything restarts this container. That board was invisible for
            # ever: it is not new on any later scan, so it was never probed at all.
            #
            # So it is queued like anything else. A puck already set up answers hello and is
            # recognised in silence; a radio stick is filtered; only a board with nothing to
            # say gets offered, which is the right outcome for a board on the cable.
            self._first = False
            new = now
        for port in sorted(new):
            if RADIO.search(port) or port in self._dismissed: continue
            if port not in self._pending: self._pending.append(port)
        # ONE PROBE AT A TIME, ACROSS ALL PORTS. Two reasons, and the second one is why a
        # hub behaved differently from a Mac all evening:
        #
        #   * probing resets the board, so its USB re-enumerates and the port churns; the
        #     returning port reads as a fresh arrival and would be probed again underneath
        #     the probe still running;
        #   * and ONE BOARD CAN BE TWO PORTS. An ESP32-S3 on Linux shows up as both its
        #     USB-serial bridge and the chip's own USB-JTAG unit. Probing "each port" then
        #     means two probes on one chip, fighting: "device reports readiness to read but
        #     returned no data (multiple access on port?)". macOS shows only the one port,
        #     which is why this never reproduced on a desk.
        #
        # Ports wait their turn rather than being dropped, so nothing is lost by queueing.
        if self._pending and not self._probing and not self.job:
            asyncio.create_task(self._arrived(self._pending.pop(0)))

    async def _arrived(self, port: str):
        self._probing.add(port)               # anything its USB does until we are done is ours
        try:
            await self._probe(port)
        finally:
            self._probing.discard(port)

    async def _probe(self, port: str):
        who = await self.cable.hello(port)
        if who:
            if who["state"] == "set" and who["chip"] in self.pucks:
                # A set-up puck the hub has seen before. Two quite different things wear that
                # shape, and the difference is which mesh it carries.
                #
                # ON OUR OWN MESH it is one of ours, visiting, and there is nothing to set up
                # -- but it may be one this hub never wrote down, which is how a hand-built
                # puck stays invisible: the only way into `bridges` was the cable flow, and
                # the cable flow skips exactly the pucks that do not need it.
                if self._adopt_on_sight(who["chip"], who.get("fw"), plugged=True) \
                        or self._on_our_mesh(who["chip"]) \
                        or not (self.pucks.get(who["chip"]) or {}).get("net"):
                    # ...and a puck that has not said which mesh it carries is UNKNOWN, not
                    # foreign. One of ours that has simply not published yet would otherwise
                    # be offered a rebuild it does not need, which is worse than waiting.
                    return
                # ON SOMEBODY ELSE'S MESH it is a working bridge for another network, and
                # taking it over is not something to do because we can see it -- that would
                # be acting on a puck a neighbour has on a shelf. Being plugged INTO THIS HUB
                # is the one unambiguous way a person says "bring this one over", so that,
                # and only that, is when it is offered.
                log.info("bridge: %s carries another mesh and is on our cable -- offering it", who["chip"])
            self.job = {"state": "knocking", "port": port, "bare": False, "chip": who["chip"], "fw": who["fw"]}
        elif (silicon := await self.cable.esp_chip(port)):
            if not self.cable.image_for(silicon):
                # Knocking would be a lie: there is nothing to give it. Said once, named, and
                # then left alone -- a board the house cannot use should not keep asking.
                # The job exists only to carry the sentence: _set is a no-op without one.
                self._dismiss_port(port)
                self.job = {"state": "failed", "port": port, "bare": True, "chip": None, "silicon": silicon}
                self._set("failed", text=f"That board is an {self._chip_words(silicon)}, and this house only has "
                                         f"software for the bridge it ships. Nothing was written to it.")
                return
            self.job = {"state": "knocking", "port": port, "bare": True, "chip": None, "silicon": silicon}
        else:
            return
        if self.job: self._set("knocking")

    @staticmethod
    def _chip_words(silicon: str) -> str:
        """esp32c3 -> ESP32-C3. The chip is the one piece of jargon worth keeping: it is
        printed on the board, so a person can match it with their eyes."""
        return silicon.upper().replace("ESP32", "ESP32-", 1).rstrip("-")

    def _on_our_mesh(self, chip: str) -> bool:
        p = self.pucks.get(chip) or {}
        try: return bool(p.get("net")) and p["net"] == network_id(bytes.fromhex(self.keys()["netkey"]))
        except Exception: return False

    def _adopt_on_sight(self, chip: str, fw: str | None, plugged: bool = False) -> bool:
        """Write down a working puck the hub can already see on its own network.

        The test is evidence, not trust: it is online on this hub's broker, and the mesh it
        says it carries is this hub's mesh. A puck on somebody ELSE's network fails that and
        is left alone -- adopting one would be how a new switch ends up claimed onto a
        neighbour's mesh, which is the thing _our_puck() exists to prevent."""
        known = self.hub.settings.get("bridges") or {}
        if chip in known:
            return False
        p = self.pucks.get(chip) or {}
        # Online is the usual evidence that it is real and reachable. Sitting on this hub's
        # own USB is stronger evidence than that, so it counts too.
        if not (p.get("online") or plugged):
            return False
        try: ours = network_id(bytes.fromhex(self.keys()["netkey"]))
        except Exception as e:
            log.warning("bridge: cannot work out our own network id (%s)", e); return False
        if p.get("net") != ours:
            log.info("bridge: %s carries %s, not this house's %s -- left alone", chip, p.get("net"), ours)
            return False
        self.hub.settings.set(bridges={**known, chip: {"since": time.time(), "fw": fw, "seen": "broker"}})
        self.hub.log.add("bridge", chip, None, "recognised", source="hub")
        log.info("bridge: %s is on this house's mesh and working -- written down", chip)
        return True

    # ---- the person's two answers ----
    async def adopt(self) -> dict:
        if not self.job or self.job["state"] != "knocking": raise ValueError("Nothing is knocking.")
        self._task = asyncio.create_task(self._setup())
        return self.status()

    def _dismiss_port(self, port: str) -> None:
        self._dismissed.add(port)

    async def dismiss(self) -> dict:
        if self.job and self.job["state"] in ("knocking", "failed", "ready"):
            self._stop_quiet_watch()
            if self.job.get("port"): self._dismiss_port(self.job["port"])
            self.job = None
            self.hub._broadcast(json.dumps({"type": "bridge", "bridge": self.status()}))
        return self.status()

    async def wifi(self, ssid: str, password: str) -> dict:
        """The house's Wi‑Fi, told once. Kept in the settings for every bridge after this one; a job
        that stopped for want of it picks up where it left off, on the same cable."""
        ssid = (ssid or "").strip()
        # Nothing typed means the panel showed the hub's own network and asked only for the password.
        # Its own connection is the name, and that one cannot be stale: a hub that were wrong about it
        # would not be on the network to say so.
        if not ssid:
            mine = self.wifi_for_pucks()
            ssid = mine["ssid"] if mine["checked"] else ""
        if not ssid: raise ValueError("Which Wi‑Fi? The name is needed.")
        self.hub.settings.set(wifi={"ssid": ssid, "pass": password})
        j = self.job
        if j and j["state"] == "failed" and j.get("needs") == "wifi" and j.get("port") in self._seen:
            j.pop("needs", None); j.pop("text", None)
            self._task = asyncio.create_task(self._setup())
        return self.status()

    # How long a puck may say nothing during the placing before the panel stops implying it is a
    # matter of time. Long enough to unplug it, carry it somewhere and let it boot; short enough that
    # somebody is still standing there holding it.
    QUIET_S = 90

    async def _placing_went_quiet(self) -> None:
        """A puck in somebody's hand and a puck in a socket with no Wi-Fi both say nothing at all.

        They are the same silence to the broker, and the panel drew them the same way -- "still
        listening" -- for ever, about a puck that was never coming back. The difference is only how
        long it lasts, so that is what this measures. The light is unaffected: BLE does not need the
        Wi-Fi, so a puck in a mesh-but-no-Wi-Fi socket is still telling the truth locally.
        """
        try:
            await asyncio.sleep(self.QUIET_S)
        except asyncio.CancelledError:
            return
        j = self.job
        if j and j["state"] == "placing" and self._signal(j.get("chip")) == "none":
            self._set("placing", quiet=True)

    def _stop_quiet_watch(self) -> None:
        if self._quiet and not self._quiet.done(): self._quiet.cancel()
        self._quiet = None

    async def _tell(self, chip: str, leaf: str, payload: str, retain: bool = False) -> None:
        """One line to one puck. Failures are logged, never raised: none of these are the reason
        somebody tapped the button, and a puck that missed one is in a safe state by design."""
        with contextlib.suppress(Exception):
            await self.hub.ha.call("mqtt", "publish", None,
                                   topic=f"{BASE}/bridge/{chip}/{leaf}", payload=payload, retain=retain)

    async def placed(self, night: bool | None = None, level: int | None = None) -> dict:
        """"Leave it here" -- and the answer to the one question asked in the same breath.

        Two things go to the puck, and they are NOT sent the same way, which is the whole of this
        method (docs/puck-light.md):

        `settled` is the hub's to own. It says the thing has a home, it never changes afterwards, and
        until the puck has it the light stays an instrument -- green, still asking "is here good?".
        So it goes RETAINED: a puck that was offline at this exact moment, or that is wiped and
        flashed again in the same corner, picks it up on its next connect. Replaying it is harmless
        because it is idempotent, and `forget()` clears it, which is what stops a bridge that was
        sent away coming back believing it is still placed.

        `night` is the HOUSEHOLD's, the moment after they answer. It goes once, NOT retained, and the
        hub never says it again. The puck keeps it in NVS and Home Assistant owns it from here -- so
        somebody turning the nightlight off in February is not overruled by a placement answer from
        September the next time the puck reboots. That failure would be invisible and maddening, and
        not retaining is the whole fix.

        A puck that is offline right now therefore keeps its green and loses only the nightlight,
        which is the right way round: the instrument survives, the decoration does not.
        """
        if not self.job or self.job["state"] != "placing": raise ValueError("Nothing is being placed.")
        if level is not None and not 0 <= int(level) <= 255:
            raise ValueError("A brightness is 0 to 255.")
        chip = self.job.get("chip")
        self._stop_quiet_watch()
        self._set("ready", unplaced=self._unplaced(self.job.get("net")))
        if chip:
            await self._tell(chip, "settled/set", "1", retain=True)
            if night is not None:
                await self._tell(chip, "night/set", "ON" if night else "OFF")
                if night and level is not None:
                    await self._tell(chip, "night/brightness/set", str(int(level)))
                self.hub.log.add("bridge", chip, None,
                                 "nightlight on" if night else "nightlight off", source="user")
            nl = getattr(self.hub, "nightlight", None)
            if nl:
                with contextlib.suppress(Exception): await nl.announce(chip)
        return self.status()

    # ---- the job itself ----
    async def _setup(self):
        j = self.job
        try:
            self._set("working", step="software")
            if j["bare"]:
                await self.cable.flash(j["port"], j.get("silicon") or "esp32s3")
                who = await self.cable.hello(j["port"])
                if not who: raise BridgeError("It took the software but did not answer afterwards.")
                j["chip"], j["fw"] = who["chip"], who["fw"]
            cfg = self.config()
            if not cfg.get("ssid"):
                # It is missing the PASSWORD far more often than the name: the host never hands a PSK
                # back up, so a hub sitting on the house Wi‑Fi knows exactly which network it is on
                # and nothing about how to join it. Asking for both is how somebody types the name
                # wrong and ends up with a puck on a network that does not exist -- which looks
                # exactly like a puck that does not work. So the name goes with the question when the
                # hub is standing on it, and only a hub on a cable is asked the whole thing.
                wifi = self.wifi_for_pucks()
                mine = wifi["ssid"] if wifi["checked"] else ""
                self._set("failed", needs="wifi", ssid=mine or None,
                          text=(f"The hub is on {mine}. It needs the password for it once — then this bridge, "
                                "and every one after it, just works.") if mine else
                               "The hub does not know the house's Wi‑Fi yet — it is on a cable itself. Tell it once, "
                               "under This hub, and every bridge after this one just works.")
                return
            self._set("working", step="wifi")
            await asyncio.sleep(0)            # the step is drawn before the write starts
            self._set("working", step="keys")
            who = await self.cable.write(j["port"], cfg)
            if who["state"] != "set": raise BridgeError("It restarted without keeping what it was told.")
            j["chip"] = who["chip"]; j["net"] = None
            self.hub.settings.set(bridges={**(self.hub.settings.get("bridges") or {}), who["chip"]: {"since": time.time(), "fw": who["fw"]}})
            self.hub.log.add("bridge", who["chip"], None, "set up", source="user")
            self._set("placing")
            self._quiet = asyncio.create_task(self._placing_went_quiet())
        except Exception as e:
            # The whole error goes to the log, with a traceback for anything the house did not
            # phrase itself. The screen gets a sentence and something to do about it.
            told = isinstance(e, BridgeError)
            log.warning("bridge setup failed: %s", e, exc_info=not told)
            self._set("failed", text=str(e) if told else
                      "The hub could not finish setting it up. Unplug it, plug it back into the hub, "
                      "and it will pick up where it left off.")

    # ---- moving every bridge onto another Wi-Fi ----
    #
    # docs/network.md, pieces 3 and 6. The hub hands each online puck a second set of credentials
    # and the puck keeps the one it has as a spare, so the order of the move stops mattering and a
    # mistyped password repairs itself. Nothing here restarts anything or waits on a cable: a puck
    # that is on the broker can be told, and a puck that is not is named for the person instead.
    #
    # The command is RETAINED on purpose. A puck that was switched off during the move gets it the
    # moment it comes back and joins by itself -- which turns most of the "did not follow" list into
    # nothing at all. The `at` on it is what stops a retained command being re-applied for ever: the
    # puck remembers the last one it acted on.

    MOVE_WAIT = 210            # how long a puck has to come back before the panel calls it late
    MOVE_SETTLE = 4            # ...and how often we look while it does

    # How long a bridge may be gone before it is worth a line on Home. Two numbers, because there are
    # two situations and only one of them has a known cause.
    #
    #   QUIET   a bridge that simply is not there. A day: long enough that a household unplugging a
    #           charger to hoover is not reported, short enough to notice before the week is out.
    #   MISSED  one that did not follow a move. The cause IS known, so the wait is only long enough
    #           for the design's own self-healing to have had its go -- two keys on the ring, a
    #           retained command waiting on its topic, and a puck alternating every two minutes.
    QUIET = 24 * 3600
    MISSED = 2 * 3600

    def _remember(self, chip: str, **fields) -> None:
        """Write something down about one bridge, without disturbing the others."""
        mine = dict(self.hub.settings.get("bridges") or {})
        if chip not in mine: return              # not one of ours; nothing here is its business
        rec = {**mine[chip], **fields}
        for k in [k for k, v in rec.items() if v is None]: rec.pop(k)
        mine[chip] = rec
        self.hub.settings.set(bridges=mine)

    def _saw(self, chip: str, online: bool, was: bool | None) -> None:
        """Stamp the moment a bridge went quiet, and rub it out when it comes back.

        On disk rather than in memory, because the question this answers is "how long" and the brain
        restarts. Written only on a change of state -- a puck publishes its status retained and rarely,
        and settings.json is rewritten whole every time this is called.

        A brain that starts up and finds a puck already offline has no idea when that began, so it
        says now and does not correct itself later: "gone since at least this" is the honest claim,
        and overwriting it on every restart would mean a hub that reboots nightly never notices
        anything is missing.
        """
        if online == was: return
        # `heard`, not `seen`: _adopt_on_sight already writes seen="broker" to record HOW a bridge was
        # recognised, and a timestamp written over it makes one key mean two things. Nothing reads it
        # yet, which is exactly when this is cheap to put right -- the settings on the live hub
        # already hold one bridge with seen="broker" and one with a float.
        if online: self._remember(chip, gone=None, missed=None, heard=time.time())
        elif not ((self.hub.settings.get("bridges") or {}).get(chip) or {}).get("gone"):
            self._remember(chip, gone=time.time())

    # ---- which of them are behind the software the house ships now ----
    @staticmethod
    def _older(a: str, b: str) -> bool:
        """Is `a` an earlier version than `b`? Numeric, part by part, so 0.10.0 beats 0.9.0.

        Anything that is not a version at all -- a hand-built puck calling itself "dev" -- is never
        older than anything. A line telling somebody their bench board is out of date is noise.
        """
        def parts(v):
            out = []
            for piece in str(v or "").split("."):
                if not piece.isdigit(): return None
                out.append(int(piece))
            return tuple(out) or None
        pa, pb = parts(a), parts(b)
        return bool(pa and pb and pa < pb)

    def shipped(self) -> str:
        """The version of the image this house would flash a bare board with, or "".

        Read from the manifest beside the image rather than from anything remembered: the two move
        together, and a version kept anywhere else is a version that can disagree with the file.
        """
        try:
            return str(json.loads(self.cable.image.with_suffix(".json").read_text()).get("fw") or "")
        except (OSError, ValueError):
            return ""

    def behind(self) -> list:
        """The bridges this hub set up that are running something older than it ships.

        Nothing about this is urgent and the panel must not draw it as though it were: a bridge a
        version behind is a bridge doing its whole job. It is here because a household that is told
        nothing has no way to find out, and because the count is the thing that matters once a fix
        does need to reach every one of them -- see docs/puck-updates.md.
        """
        latest = self.shipped()
        if not latest: return []
        out = []
        for chip, rec in (self.hub.settings.get("bridges") or {}).items():
            fw = str(rec.get("fw") or "")
            if not self._older(fw, latest): continue
            out.append({"chip": chip, "room": self.room_of(chip), "fw": fw, "latest": latest,
                        "online": bool((self.pucks.get(chip) or {}).get("online"))})
        out.sort(key=lambda b: (b["room"] or "\uffff", b["chip"]))
        return out

    def room_of(self, chip: str) -> str | None:
        """The room a bridge serves, or None when the hub cannot honestly say.

        A puck that is the only one carrying its mesh is fairly described by the room most of its
        switches are in. Two pucks on one mesh cannot be told apart this way, so they are not:
        guessing would put a name on the wrong object, which is worse than having none."""
        mine = (self.hub.settings.get("bridges") or {}).get(chip) or {}
        if mine.get("where"): return str(mine["where"])
        net = (self.pucks.get(chip) or {}).get("net")
        home = getattr(self.hub, "home", None)
        if not (net and home) or sum(1 for c, p in self.pucks.items() if p.get("net") == net) != 1:
            return None
        tag = f"light.{BASE}_{net[:4]}_"
        rooms: dict[str, int] = {}
        for d in home.devices.values():
            if d.id.startswith(tag) and d.room_id and d.room_id != "unassigned":
                rooms[d.room_id] = rooms.get(d.room_id, 0) + 1
        if not rooms: return None
        room = home.rooms.get(max(rooms, key=lambda r: rooms[r]))
        return room.name if room else None

    def quiet(self) -> list:
        """The bridges that have been gone long enough to be worth saying out loud.

        Only ones this hub set up: a neighbour's puck on the same broker is not this house's problem,
        and a line about it would be a line nobody can act on."""
        out, now = [], time.time()
        for chip, rec in (self.hub.settings.get("bridges") or {}).items():
            if (self.pucks.get(chip) or {}).get("online"): continue
            gone = rec.get("gone")
            if not gone: continue
            missed = (rec.get("missed") or {}).get("ssid")
            if now - gone < (self.MISSED if missed else self.QUIET): continue
            out.append({"chip": chip, "room": self.room_of(chip), "since": gone, "missed": missed})
        out.sort(key=lambda b: b["since"])
        return out

    async def forget(self, chip: str) -> dict:
        """Take a bridge off the house. The last thing offered about one that is never coming back.

        Its retained topics go with it. They outlive the puck by design -- that is what makes a
        bridge recognisable after the brain restarts -- so leaving them would mean a bridge that is
        forgotten on Monday and back in the list on Tuesday, with nothing a household could do
        about it."""
        mine = dict(self.hub.settings.get("bridges") or {})
        if chip not in mine: raise ValueError("The hub does not know that bridge.")
        where = self.room_of(chip)
        mine.pop(chip)
        self.hub.settings.set(bridges=mine)
        self.pucks.pop(chip, None)
        with contextlib.suppress(Exception):
            await self.hub.ha.call("mqtt", "publish", None,
                                   topic=f"homeassistant/switch/{BASE}_bridge_{chip}_motion/config",
                                   payload="", retain=True)
        for leaf in ("status", "net", "proxy", "iv", "cfg", "cfgack",
                     "settled", "settled/set", "night", "night/brightness", "light", "motion"):
            with contextlib.suppress(Exception):
                await self.hub.ha.call("mqtt", "publish", None,
                                       topic=f"{BASE}/bridge/{chip}/{leaf}", payload="", retain=True)
        self.hub.log.add("bridge", chip, None, "forgotten", source="user")
        return {"forgotten": where or "The bridge"}

    # The entities a puck publishes for one switch, and the topics it keeps their state on. Both lists
    # are the other half of announce()/publishState() in brilliant/esp32-bridge/src/main.cpp, and
    # forgetting one means emptying every item in both.
    #
    # The last two of each are RETIRED, and stay here on purpose. A puck used to publish a motion
    # sensor fed by vendor field 0x13, which turned out to be the lamp's own draw rather than a PIR
    # (brilliant/STATUS.md). Their discovery is retained, so a household that never updates a puck --
    # or one whose switch is forgotten by a brain newer than its puck -- still has those entities
    # sitting in Home Assistant. Dropping them from this list would strand them there forever.
    SWITCH_CONFIGS = (("light", ""), ("binary_sensor", "_occupancy"), ("sensor", "_load"),
                      ("binary_sensor", "_motion"), ("sensor", "_motion_level"))
    SWITCH_LEAVES = ("state", "brightness", "occupancy", "load", "motion", "motion_level")

    async def forget_switch(self, net: str, addr: str) -> dict:
        """Take one wall switch off the house, and make it stay off.

        A PUCK IS NOT ASKED WHICH SWITCHES IT HAS. It says so, unprompted, every MQTT session, by
        publishing their discovery again (`announced` in the firmware) -- which is what makes a
        bridge recognizable after the brain restarts, and is also why taking a switch out through
        the device registry lasted exactly as long as the puck stayed connected. The row came back
        by morning and the household had no word for what was happening. So the house has to say
        this to the BRIDGE, not to Home Assistant, and say it in a way that survives both of them.

        A retained word on the switch's own address is that way. Every puck on the mesh hears it,
        whether it is the one that announced the switch or the one that will next reconnect; a puck
        that was unplugged during all this hears it when it comes back, which is the case the whole
        bug was made of. The puck writes it down, so its own reboot does not undo it.

        THE WAY BACK IS LETTING THE SWITCH IN AGAIN, and it needs no undo here: the house hands out
        a fresh address every time (`_next_addr`), so a switch that is set up again is not the
        address that was forgotten. let_in() clears this topic for the address it is about to use,
        which covers the one case where an old address is deliberately restored.

        The mesh node itself keeps this house's netkey either way. Nothing over the air can take
        that back -- a factory reset at the wall is the only thing that does -- so this is not
        claimed to be one. It is the house forgetting the switch, said in a way that holds.
        """
        if not net or not addr:
            raise ValueError("The hub does not know that switch.")
        for leaf in self.SWITCH_LEAVES:
            with contextlib.suppress(Exception):
                await self.hub.ha.call("mqtt", "publish", None,
                                       topic=f"{BASE}/{net}/{addr}/{leaf}", payload="", retain=True)
        for kind, tail in self.SWITCH_CONFIGS:
            with contextlib.suppress(Exception):
                await self.hub.ha.call("mqtt", "publish", None,
                                       topic=f"homeassistant/{kind}/{BASE}_{net}_{addr}{tail}/config",
                                       payload="", retain=True)
        # Last, and retained: the standing instruction. After the clears, so a puck that acts on it
        # the instant it lands is not racing the emptying of the topics it is about to stop writing.
        await self.hub.ha.call("mqtt", "publish", None,
                               topic=f"{BASE}/{net}/{addr}/forget", payload="1", retain=True)
        self.switches.pop((net, addr), None)
        self.hub.log.add("bridge", f"{net}/{addr}", None, "switch forgotten", source="user")
        return {"forgotten": addr}

    def where(self, chip: str) -> str:
        """A bridge in the words a household has for it: the room it serves.

        A chip id tells nobody anything, and this is the one list where a panel would be forgiven for
        thinking otherwise. `A bridge` is what honesty looks like when the room cannot be worked out;
        room_of() is the same question where the caller would rather have the None."""
        return self.room_of(chip) or "A bridge"

    def carrying(self, net: str) -> str | None:
        """Which puck's chip carries this mesh, where exactly one does.

        The switches on a mesh belong to whichever bridge is holding it, and that is how "What this
        house has" groups them -- under a room rather than under a network id nobody has a word for.
        Two pucks on one mesh cannot be told apart (see room_of), so this says nothing rather than
        picking one, and the list falls back to saying the switches are simply on a bridge."""
        mine = [c for c, p in self.pucks.items() if p.get("net") == net
                and c in (self.hub.settings.get("bridges") or {})]
        return mine[0] if len(mine) == 1 else None

    def each(self) -> list[dict]:
        """Every bridge this hub set up, in the words a household has for one.

        THE PANEL HAD NOWHERE TO LOOK AT A BRIDGE THAT IS FINE. Until this, a puck surfaced only when
        something was wrong with it -- a note when it went quiet, a line on This hub when it was a
        version behind -- so the one place a household could act on one was a problem report. That is
        the wrong shape for an object that mostly just works, and it is what left the nightlight with
        a switch nobody could reach without Home Assistant (docs/puck-light.md).

        Ordered by the room's name, with the ones the hub cannot place last: a list that reorders
        itself as signal moves would be unreadable on a wall."""
        behind = {b["chip"] for b in self.behind()}
        out = []
        for chip, rec in (self.hub.settings.get("bridges") or {}).items():
            p = self.pucks.get(chip) or {}
            room = self.room_of(chip)
            out.append({
                "chip": chip, "room": room, "where": self.where(chip),
                "online": bool(p.get("online")), "signal": self._signal(chip),
                "switches": self._count(p.get("net")) if p.get("net") else 0,
                # What the house ships, or None when it cannot say -- shipped() returns "" with no
                # manifest beside the image, and behind() is then empty for every puck. Without this
                # the panel cannot tell "not behind" from "nobody knows", and it drew a puck three
                # versions old as "current".
                "fw": rec.get("fw"), "behind": chip in behind, "shipped": self.shipped() or None,
                # None rather than false when the puck has never said: "off" is a claim about a thing
                # we have heard from, and a puck that has not spoken is not a puck with its light off.
                "night": p.get("night"), "level": p.get("level"),
                "lift": bool(rec.get("lift")),
            })
        out.sort(key=lambda b: (b["room"] is None, (b["room"] or "").lower(), b["chip"]))
        return out

    async def light(self, chip: str, night: bool | None = None,
                    level: int | None = None, lift: bool | None = None) -> list[dict]:
        """Change a bridge's own light from the panel.

        The household's, not the placement answer's, so these go once and are not retained -- the
        puck holds them in NVS and says so back on its own topics. `lift` is the brain's and is
        written to settings instead; see hub/nightlight.py."""
        if chip not in (self.hub.settings.get("bridges") or {}):
            raise ValueError("The hub does not know that bridge.")
        if level is not None and not 0 <= int(level) <= 255:
            raise ValueError("A brightness is 0 to 255.")
        if night is not None:
            await self._tell(chip, "night/set", "ON" if night else "OFF")
        if level is not None and (night is None or night):
            await self._tell(chip, "night/brightness/set", str(int(level)))
        if lift is not None:
            nl = getattr(self.hub, "nightlight", None)
            if nl: nl.on_command(chip, "ON" if lift else "OFF")
        self.hub.log.add("bridge", chip, None, "light changed", source="user")
        return self.each()

    def move_status(self) -> dict | None:
        """What the panel draws while a move is on, and after it. None when nothing has happened."""
        j = self.moving
        if not j: return None
        out = {"state": j["state"], "ssid": j["ssid"], "total": len(j["asked"]),
               "followed": [self.where(c) for c in j["followed"]],
               "waiting": [self.where(c) for c in j["asked"] if c not in j["followed"]]}
        if j["state"] == "done":
            out["late"] = out.pop("waiting")
        return out

    async def move(self, ssid: str, password: str) -> dict:
        """Hand every bridge that is listening a new Wi-Fi, and watch them come back on it."""
        ssid = (ssid or "").strip()
        if not ssid: raise ValueError("Which Wi‑Fi? The name is needed.")
        # Written down first. A move that is interrupted halfway must leave the hub agreeing with
        # the pucks it already told, not with the network it is leaving.
        self.hub.settings.set(wifi={"ssid": ssid, "pass": password})
        at = time.time()
        cfg = self.config()
        # Words, hex-encoded, in the same shape as the `claim` topic and the cable's own protocol --
        # so a network called "Flat 3 guest" needs no quoting rules on either side, and the puck
        # needs no JSON parser it does not already have.
        body = f"wifi {int(at)} {_hx(ssid)} {_hx(password)} {_hx(cfg['name'])} {cfg['host']} {cfg['port']}"
        # EVERY puck the house knows is told, not only the ones listening. The command is retained, so
        # one that was switched off during the move collects it the moment it next reaches the broker
        # and joins by itself -- which is most of the "did not follow" list, handled without anybody
        # fetching anything. Only the ones that ARE listening are counted, because only they can be
        # expected back inside the few minutes somebody is standing at the wall for.
        for chip in sorted(self.pucks):
            await self.hub.ha.call("mqtt", "publish", None,
                                   topic=f"{BASE}/bridge/{chip}/cfg", payload=body, retain=True)
        asked = sorted(c for c, p in self.pucks.items() if p.get("online"))
        self.moving = {"state": "moving" if asked else "done", "ssid": ssid, "at": at,
                       "asked": asked, "followed": []}
        self.hub.log.add("home", "network", None, f"bridges moving to {ssid}", source="user")
        if asked:
            self._move_task = asyncio.create_task(self._move_watch(at))
        return self.move_status()

    async def _move_watch(self, at: float) -> None:
        """Wait for them, then stop waiting and say who is missing.

        A watch that never gives up is a screen that never resolves, and the person standing at it
        learns nothing. The deadline is generous enough for a puck to restart twice."""
        try:
            end = time.time() + self.MOVE_WAIT
            while time.time() < end:
                await asyncio.sleep(self.MOVE_SETTLE)
                j = self.moving
                if not j or j["at"] != at: return        # a second move started; this one is history
                if len(j["followed"]) >= len(j["asked"]): break
                self.hub._broadcast(json.dumps({"type": "bridge", "bridge": self.status()}))
        except asyncio.CancelledError:
            return
        j = self.moving
        if j and j["at"] == at:
            j["state"] = "done"
            late = [c for c in j["asked"] if c not in j["followed"]]
            if late:
                log.info("bridge: %d did not follow to %s", len(late), j["ssid"])
                # Kept, because the move's own screen is read once and dismissed. Without this the
                # house forgets by morning that it moved without two of its bridges.
                for chip in late:
                    self._remember(chip, missed={"ssid": j["ssid"], "at": j["at"]})
            # Everybody came: the spare is no longer worth the room it takes on them. Told once,
            # and only now -- a puck that is online cannot tell whether the HUB can see it.
            # Only the ones that followed are told to drop the spare, and only their retained command
            # is overwritten -- a puck that has still not been seen keeps the `wifi` command waiting
            # for it on its own topic.
            if not late:
                for chip in j["asked"]:
                    with contextlib.suppress(Exception):
                        await self.hub.ha.call("mqtt", "publish", None,
                                               topic=f"{BASE}/bridge/{chip}/cfg",
                                               payload=f"spare forget {int(time.time())}",
                                               retain=True)
            self.hub._broadcast(json.dumps({"type": "bridge", "bridge": self.status()}))

    async def clear_move(self) -> dict:
        """The person has read it. Nothing vanishes under a tap until it has been."""
        if self.moving and self.moving["state"] == "done":
            self.moving = None
        return self.status()

    def wifi_for_pucks(self) -> dict:
        """The Wi‑Fi a puck should be given, and how much the hub actually knows about it.

        docs/network.md's rule: the hub hands out what the hub is USING. A hub on Wi‑Fi reads its own
        connection, and that name cannot be stale -- if it were, the hub would not be on the network
        to say it. A hub on a cable is the one case that still has to be told, and the panel then
        says so rather than stating it as a fact.

        The password is a separate question from the name, and conflating them is the original bug.
        The host never hands secrets back up (network.sh keeps the PSK where NetworkManager put it),
        so what the hub holds is whatever was typed here last. If that was typed for a DIFFERENT
        network, it is not a password for this one and must not be written into anything: `known`
        goes false, and the caller asks instead of guessing. Silently writing the old password into
        a new puck and finishing with a green tick is exactly what this module used to do.
        """
        env = getattr(self.hub, "env", {}) or {}
        held = self.hub.settings.get("wifi") or {}
        ssid = held.get("ssid") or env.get("PUCK_WIFI_SSID") or ""
        password = held.get("pass") or env.get("PUCK_WIFI_PASS") or ""
        checked = False
        net = getattr(self.hub, "net", None)
        state = net.state() if net else {}
        if state.get("how") == "wifi" and state.get("ssid"):
            checked = True
            if state["ssid"] != ssid:
                # The hub moved, or was flashed onto a network nobody typed here. Its name is the
                # truth; the password we are holding belongs to somewhere else.
                ssid, password = state["ssid"], ""
        return {"ssid": ssid, "pass": password, "checked": checked, "known": bool(ssid and password)}

    def broker(self) -> dict:
        """Where our own broker is, and how to get into it.

        ONE PLACE, because a puck and a strip are told the same thing and two descriptions of one
        broker is how one of them comes to be wrong. It was: hub/strip.py read a `broker` key in the
        settings that nothing in this hub has ever written, so every strip was handed the literal
        name "hub" and no credentials at all. It joined the house, reached the broker, and was told
        `Connection refused, not authorized` -- which the wall reported as "it never found the hub".
        """
        env = getattr(self.hub, "env", {}) or {}
        return {
            # A name AND a number. The name is tried first, over mDNS, so a DHCP reshuffle stops
            # stranding every device in the house; the number is what answers in a house whose
            # router filters multicast. docs/network.md, piece 1.
            "host": lan_ip(), "name": _hostname(), "port": 1883,
            "user": env.get("MQTT_USER") or os.environ.get("MQTT_USER", ""),
            "pass": env.get("MQTT_PASSWORD") or os.environ.get("MQTT_PASSWORD", ""),
        }

    def config(self) -> dict:
        """Everything a puck is told. The Wi‑Fi is the one thing the hub might not have (it may be on a cable)."""
        keys = self.keys()
        mq = self.broker()
        wifi = self.wifi_for_pucks()
        return {
            "ssid": wifi["ssid"] if wifi["known"] else "", "pass": wifi["pass"],
            "host": mq["host"], "name": mq["name"], "port": mq["port"],
            "user": mq["user"], "mqtt_pass": mq["pass"],
            "netkey": keys["netkey"], "appkey": keys["appkey"], "iv": keys["iv_index"], "base": BASE, "label": "Brilliant",
        }

    def keys(self) -> dict:
        """The house's mesh keys, made once and kept next to the settings. A house with a Brilliant panel
        imports the panel's captured keys instead (python -m hub.bridge import panel-net.json)."""
        p = self.hub.settings.path.parent / "mesh-keys.json"
        try: k = json.loads(p.read_text())
        except Exception: k = None
        if not k or not k.get("netkey") or not k.get("appkey"):
            k = {"netkey": secrets.token_hex(16), "appkey": secrets.token_hex(16), "iv_index": 0, "made": time.time()}
            p.write_text(json.dumps(k, indent=1)); os.chmod(p, 0o600)
            log.info("bridge: made the house's mesh keys")
        return k

    # ---- the broker: what the bridges say from wherever they are ----
    def _on_mqtt(self, ev):
        m = ev.get("event") or ev
        topic, payload = str(m.get("topic", "")), str(m.get("payload", ""))
        parts = topic.split("/")
        if len(parts) == 4 and parts[1] == "bridge":
            chip, leaf = parts[2], parts[3]
            p = self.pucks.setdefault(chip, {})
            if leaf in ("nearby", "claimed"):
                # An answer to something we asked. Keep the newest and wake whoever
                # is waiting; the waiter checks what it got, because a stale reply
                # from a previous question would otherwise look like an answer.
                try: self._heard[leaf] = {"at": time.time(), "body": json.loads(payload), "chip": chip}
                except Exception: self._heard[leaf] = {"at": time.time(), "body": None, "chip": chip}
                if self._woke: self._woke.set()
                return
            if leaf == "heard":
                # A strip knocking near this puck (hub/ears.py). Not a state of the puck's, so it
                # stops here rather than falling through to the puck's own bookkeeping.
                ears = getattr(self.hub, "ears", None)
                if ears: ears.from_puck(chip, payload)
                return
            if leaf == "cfgack":
                # Proof, not a promise. A puck can only publish this from the broker, and it can only
                # reach the broker on a network it actually joined.
                j = self.moving
                try: ack = json.loads(payload)
                except Exception: ack = {}
                if j and j["state"] == "moving" and int(ack.get("at") or 0) == int(j["at"]) and chip not in j["followed"]:
                    j["followed"].append(chip)
                    log.info("bridge: %s followed to %s", chip, j["ssid"])
                    self.hub._broadcast(json.dumps({"type": "bridge", "bridge": self.status()}))
                return
            if leaf == "status":
                was = p.get("online")
                p["online"] = payload == "online"
                self._saw(chip, p["online"], was)
            elif leaf == "net": p["net"] = payload
            elif leaf == "fw": self.firmware.heard_fw(chip, payload)
            elif leaf == "update":
                with contextlib.suppress(RuntimeError): asyncio.get_running_loop().create_task(self.firmware.heard(chip, payload))
                return
            # The nightlight's own setting, retained by the puck. Kept because a bridge whose light
            # is off has nothing to lift, and lifting it would turn it on -- which nobody asked for.
            elif leaf == "night": p["night"] = payload == "ON"
            # A puck does not have to be on the cable to be recognised -- the usual place for
            # one is a charger behind a sofa. Both facts arrive here, so check as each lands.
            if leaf in ("status", "net"): self._adopt_on_sight(chip, p.get("fw"))
            elif leaf == "proxy":
                mm = re.search(r"rssi (-?\d+)", payload); p["rssi"] = int(mm.group(1)) if mm else None
            if self.job and self.job.get("chip") == chip and self.job["state"] in ("placing", "ready") and p.get("net"):
                self.job["net"] = p["net"]
            # It turned up after all: stop saying it did not.
            if self.job and self.job.get("chip") == chip and self.job.get("quiet") and p.get("online"):
                self.job.pop("quiet", None)
                self._set("placing")
        elif len(parts) == 5 and parts[1] == "bridge" and parts[3:] == ["errand", "tell"]:
            # A bridge running an errand for a strip the hub cannot hear (hub/errand.py). Handed to
            # the one errand running, and only if it is this bridge's: strips go one at a time.
            errand = getattr(self.hub, "errand", None)
            if errand and errand.chip == parts[2]: errand.on_tell(payload)
        elif len(parts) == 5 and parts[1] == "bridge" and parts[3:] == ["night", "brightness"]:
            with contextlib.suppress(ValueError):
                self.pucks.setdefault(parts[2], {})["level"] = max(0, min(255, int(payload)))
        elif len(parts) == 5 and parts[1] == "bridge" and parts[3:] == ["motion", "set"]:
            # "Lift on motion" is a switch the BRAIN owns (hub/nightlight.py) -- the puck neither
            # stores it nor reads it -- but it rides the puck's topics so it sits on the puck's own
            # device in Home Assistant, and so this one subscription hears it.
            nl = getattr(self.hub, "nightlight", None)
            if nl: nl.on_command(parts[2], payload)
        elif len(parts) == 4 and parts[1] != "bridge":
            if parts[3] == "state":
                self.switches[(parts[1], parts[2])] = payload
            # Two switches on one light: the same stream is where a companion's press is heard.
            # One subscription for both, because there is only one thing to listen to (hub/relay.py).
            if (relay := getattr(self.hub, "relay", None)):
                relay.on_message(parts[1], parts[2], parts[3], payload, bool(m.get("retain")))

    # ---- letting a switch in ----
    #
    # The puck does the radio work (brilliant/esp32-bridge/src/claim.cpp); this
    # decides WHICH puck, WHICH address, and turns the answers back into words.
    #
    # Which puck matters more than it sounds. A switch is claimed into whatever
    # network the puck it was asked carries, so asking a puck that bridges an old
    # Brilliant panel would put a new switch on the PANEL's mesh -- somebody
    # else's network, and unrecoverable without a reset. The pucks this hub set up
    # are the ones it gave the house's own keys to, and it wrote them down.

    def _our_puck(self) -> str | None:
        mine = self.hub.settings.get("bridges") or {}
        live = [c for c, p in self.pucks.items() if p.get("online")]
        ours = [c for c in live if c in mine]
        if ours: return ours[0]
        # Nothing the hub set up is online. Refusing beats guessing: an unknown
        # puck is very likely carrying somebody else's mesh.
        return None

    def _next_addr(self, elements: int = 1) -> int:
        """The house's own address space, kept beside its keys.

        Nothing else may hand these out. The puck reserves 0x7000 upward for
        itself (0x7000 | chip << 4) and the laptop tools use 0x0001 and 0x001a, so
        this starts above those and stays well clear of both."""
        k = self.keys()
        p = self.hub.settings.path.parent / "mesh-keys.json"
        nxt = int(k.get("next_addr") or 0x0020)
        k["next_addr"] = nxt + max(1, elements)
        p.write_text(json.dumps(k, indent=1)); os.chmod(p, 0o600)
        return nxt

    async def _ask(self, cmd: str, leaf: str, timeout: float) -> dict | None:
        chip = self._our_puck()
        if not chip:
            raise ValueError("No bridge of this house is on. Plug one in, or give it a moment.")
        self._heard.pop(leaf, None)
        # Made here rather than in __init__: an Event belongs to the loop it was
        # created in, and one made outside a running loop never wakes a waiter
        # inside it -- which reads exactly like a puck that did not answer.
        self._woke = asyncio.Event()
        await self.hub.ha.call("mqtt", "publish", None,
                               topic=f"{BASE}/bridge/{chip}/claim", payload=cmd)
        end = time.time() + timeout
        while time.time() < end:
            try: await asyncio.wait_for(self._woke.wait(), timeout=max(0.2, end - time.time()))
            except TimeoutError: break
            self._woke.clear()
            got = self._heard.get(leaf)
            if got and got["chip"] == chip: return got["body"]
        return None

    async def nearby(self) -> dict:
        """What the puck can hear, and whose side each one is on. Read-only."""
        body = await self._ask("survey", "nearby", SURVEY_WAIT)
        if body is None:
            return {"state": "failed", "text": "The bridge did not answer. It may be out of range of the hub."}
        free = [s for s in body if s.get("state") == "unclaimed"]
        spoken = [s for s in body if s.get("state") == "other"]
        return {"state": "done", "waiting": free, "claimed_elsewhere": spoken,
                "text": self._nearby_words(len(free), len(spoken))}

    @staticmethod
    def _nearby_words(free: int, spoken: int) -> str:
        if free == 1: return "One switch is waiting to be let in."
        if free > 1: return f"{free} switches are waiting to be let in."
        if spoken: return "Nothing is asking to be let in, but there is a switch nearby that is on another network. That one has to be started over first."
        return "Nothing nearby is asking to be let in."

    async def blink(self, uuid: str, seconds: int = 5) -> dict:
        """Make one of them announce itself, so a person can say which is which.

        This is the whole identity check when there is no code to scan, so a
        failure here is not cosmetic -- it means the next question cannot be
        asked honestly."""
        body = await self._ask(f"blink {uuid} {int(seconds)}", "claimed", seconds + SURVEY_WAIT)
        if not body or not body.get("ok"):
            return {"state": "failed", "text": (body or {}).get("why") or "The bridge could not reach that switch."}
        return {"state": "done"}

    async def let_in(self, uuid: str, oob: str | None = None) -> dict:
        """Claim it onto the house's own network.

        `oob` is the second half of the QR when there is one. Without it this is
        the codeless route, which the switches accept -- every switch on this
        house's network was claimed that way."""
        addr = self._next_addr()
        # An address the house is about to use must not be carrying an old forget. It normally is
        # not -- _next_addr() never hands the same one out twice -- but a switch restored to its
        # former address by hand would otherwise come up already forgotten, which looks exactly
        # like a switch that will not join.
        if (net := (self.pucks.get(self._our_puck() or "") or {}).get("net")):
            with contextlib.suppress(Exception):
                await self.hub.ha.call("mqtt", "publish", None,
                                       topic=f"{BASE}/{net}/{addr:04x}/forget", payload="", retain=True)
        cmd = f"add {uuid} {addr:04x}" + (f" {oob}" if oob else "")
        body = await self._ask(cmd, "claimed", CLAIM_WAIT)
        if body is None:
            return {"state": "failed", "text": "The bridge stopped answering while it was letting the switch in."}
        if not body.get("ok"):
            return {"state": "failed", "text": body.get("why") or "That switch would not join."}
        return {"state": "done", "unicast": body.get("unicast"), "devkey": body.get("devkey"),
                "elements": body.get("elements", 1),
                "text": "It is on the house now."}

    def _count(self, net: str | None) -> int:
        return sum(1 for (n, _a) in self.switches if net is None or n == net)

    def _signal(self, chip: str | None) -> str:
        p = self.pucks.get(chip or "") or {}
        if not p.get("online") or p.get("rssi") is None: return "none"
        return "strong" if p["rssi"] > -78 else "weak"

    def _unplaced(self, net: str | None) -> int:
        home = getattr(self.hub, "home", None)
        if not home: return 0
        tag = f"light.{BASE}_{net[:4]}_" if net else f"light.{BASE}_"
        return sum(1 for d in home.devices.values() if d.room_id == "unassigned" and d.id.startswith(tag))


if __name__ == "__main__":
    # python -m hub.bridge import ~/.config/brilliant-mesh/panel-net.json
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "import":
        from .settings import DATA
        src = json.loads(Path(sys.argv[2]).expanduser().read_text())
        out = DATA / "mesh-keys.json"
        out.write_text(json.dumps({"netkey": src["netkey"], "appkey": src["appkey"], "iv_index": int(src.get("iv_index", 0)), "imported": time.time()}, indent=1))
        os.chmod(out, 0o600); print(f"mesh keys -> {out}")
    else:
        print(__doc__)
