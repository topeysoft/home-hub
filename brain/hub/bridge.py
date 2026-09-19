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

    async def esp_chip(self, port: str) -> str | None:
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
                "d = esptool.detect_chip(sys.argv[1], connect_attempts=2)\n"
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
        except asyncio.TimeoutError:
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

    async def flash(self, port: str, chip: str = "esp32s3"):
        image = self.image_for(chip)
        if not image:
            raise RuntimeError(f"no {chip} image")
        def go():
            import esptool
            esptool.main(["--chip", chip, "--port", port, "--baud", "460800", "--before", "default-reset", "--after", "hard-reset",
                          "write-flash", "-z", "--flash-mode", "dio", "--flash-freq", "80m", "--flash-size", "16MB", "0x0", str(image)])
        await self._in_thread(go)

    async def write(self, port: str, cfg: dict) -> dict:
        """Everything in cfg, then apply, then wait for it back. Returns its hello afterwards."""
        def go():
            m = _puck(); Puck, hx = m.Puck, m.hx
            p = Puck(port); p.hello(patience=10.0)
            p.set("wifi", hx(cfg["ssid"]), hx(cfg["pass"]))
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
            raise RuntimeError(f"it did not come back on the cable ({last})")
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
        self._task: asyncio.Task | None = None
        self._quiet: asyncio.Task | None = None   # the placing watch; see _placing_went_quiet
        self._sub: int | None = None
        # what the broker says: chip -> {"online", "net", "rssi"}; (net, addr) -> state
        self.pucks: dict[str, dict] = {}
        self.switches: dict[tuple, str] = {}
        self._heard: dict[str, dict] = {}       # the last answer to a claim command, per leaf
        self._woke: asyncio.Event | None = None  # made per question, inside the loop asking it
        self._first = True

    # ---- what the panel sees ----
    def status(self) -> dict:
        base = {"bridges": sum(1 for p in self.pucks.values() if p.get("online")), "waiting": 0}
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
        return out

    def _set(self, state, **more):
        if not self.job: return
        self.job.update(state=state, **more)
        self.hub._broadcast(json.dumps({"type": "bridge", "bridge": self.status()}))

    # ---- the cable: noticing a puck ----
    async def listen(self):
        """The broker's view of every bridge, through the engine's own MQTT link."""
        try:
            self._sub = await self.hub.ha.subscribe("mqtt/subscribe", self._on_mqtt, topic=f"{BASE}/#")
        except Exception as e:
            log.info("bridge: no broker view yet (%s)", e)

    async def watch(self):
        """Every few seconds: what is on the USB now that was not before. Runs for the life of the brain."""
        await self.listen()
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
            self._first = False; return       # what was there at boot is not something that just arrived
        for port in sorted(new):
            # `self.job` is not set until a probe FINISHES, so it cannot stop a second probe
            # of the port already being probed -- and probing is exactly what makes a port
            # churn, because it resets the board and its USB re-enumerates. The returning
            # port reads as a fresh arrival, a second probe starts on it, and the two fight:
            # "device reports readiness to read but returned no data (multiple access on
            # port?)". That is a probe losing a race with itself.
            if RADIO.search(port) or port in self._dismissed or port in self._probing or self.job:
                continue
            asyncio.create_task(self._arrived(port))

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
        ssid, password = ssid.strip(), password
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

    async def placed(self) -> dict:
        if not self.job or self.job["state"] != "placing": raise ValueError("Nothing is being placed.")
        self._stop_quiet_watch()
        self._set("ready", unplaced=self._unplaced(self.job.get("net")))
        return self.status()

    # ---- the job itself ----
    async def _setup(self):
        j = self.job
        try:
            self._set("working", step="software")
            if j["bare"]:
                await self.cable.flash(j["port"], j.get("silicon") or "esp32s3")
                who = await self.cable.hello(j["port"])
                if not who: raise RuntimeError("It took the software but did not answer afterwards.")
                j["chip"], j["fw"] = who["chip"], who["fw"]
            cfg = self.config()
            if not cfg.get("ssid"):
                self._set("failed", needs="wifi", text="The hub does not know the house's Wi‑Fi yet — it is on a cable itself. Tell it once, under This hub, and every bridge after this one just works.")
                return
            self._set("working", step="wifi")
            await asyncio.sleep(0)            # the step is drawn before the write starts
            self._set("working", step="keys")
            who = await self.cable.write(j["port"], cfg)
            if who["state"] != "set": raise RuntimeError("It restarted without keeping what it was told.")
            j["chip"] = who["chip"]; j["net"] = None
            self.hub.settings.set(bridges={**(self.hub.settings.get("bridges") or {}), who["chip"]: {"since": time.time(), "fw": who["fw"]}})
            self.hub.log.add("bridge", who["chip"], None, "set up", source="user")
            self._set("placing")
            self._quiet = asyncio.create_task(self._placing_went_quiet())
        except Exception as e:
            log.warning("bridge setup failed: %s", e)
            self._set("failed", text=f"{e}")

    def config(self) -> dict:
        """Everything a puck is told. The Wi‑Fi is the one thing the hub might not have (it may be on a cable)."""
        wifi = self.hub.settings.get("wifi") or {}
        env = getattr(self.hub, "env", {}) or {}
        keys = self.keys()
        return {
            "ssid": wifi.get("ssid") or env.get("PUCK_WIFI_SSID") or "", "pass": wifi.get("pass") or env.get("PUCK_WIFI_PASS") or "",
            "host": lan_ip(), "port": 1883, "user": env.get("MQTT_USER") or os.environ.get("MQTT_USER", ""),
            "mqtt_pass": env.get("MQTT_PASSWORD") or os.environ.get("MQTT_PASSWORD", ""),
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
            if leaf == "status": p["online"] = payload == "online"
            elif leaf == "net": p["net"] = payload
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
            except asyncio.TimeoutError: break
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
