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
import asyncio, json, logging, os, re, secrets, socket, time
from pathlib import Path

log = logging.getLogger("hub.bridge")

SHIP = Path(os.environ.get("HUB_NOTES") or Path(__file__).resolve().parent.parent.parent / "releases") / "bridge"
DEV = Path("/dev/serial/by-id")
SCAN_EVERY = 3
# a radio stick is never a bridge, and must never be probed: esptool's sync toggles DTR/RTS, which
# resets it. The same names driver-layer/radios.sh recognises.
RADIO = re.compile(r"skyconnect|zbt-|zbdongle|sonoff|mg24|cc2652|zigbee|efr32|nabu|zooz|z-wave|zwave|aeotec|pzg23|hubz", re.I)
STEPS = ("software", "wifi", "keys")
BASE = "mesh"


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
        """A board with no firmware answers nothing, but esptool can still tell it is an ESP32."""
        def go():
            try:
                import esptool
                esptool.main(["--port", port, "--connect-attempts", "2", "chip-id"])   # raises on anything that is not an ESP
                return True
            except SystemExit as e:
                return e.code in (0, None)
            except BaseException as e:      # esptool.FatalError, or a port that vanished
                log.debug("%s: not an ESP (%s)", port, e); return False
        return await self._in_thread(go)

    async def flash(self, port: str):
        def go():
            import esptool
            esptool.main(["--chip", "esp32s3", "--port", port, "--baud", "460800", "--before", "default-reset", "--after", "hard-reset",
                          "write-flash", "-z", "--flash-mode", "dio", "--flash-freq", "80m", "--flash-size", "16MB", "0x0", str(self.image)])
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
        self._dismissed: set[str] = set()     # "not mine": left alone until unplugged
        self._task: asyncio.Task | None = None
        self._sub: int | None = None
        # what the broker says: chip -> {"online", "net", "rssi"}; (net, addr) -> state
        self.pucks: dict[str, dict] = {}
        self.switches: dict[tuple, str] = {}
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
        self._dismissed -= gone
        if self.job and self.job.get("port") in gone and self.job["state"] in ("knocking", "working"):
            # unplugged under us. Knocking: the offer is withdrawn. Working: that is a failure worth a sentence.
            if self.job["state"] == "knocking": self.job = None; self.hub._broadcast(json.dumps({"type": "bridge", "bridge": self.status()}))
            else: self._set("failed", text="The bridge was unplugged before the hub had finished. Plug it back into the hub and it starts again from the beginning.")
        if self._first:
            self._first = False; return       # what was there at boot is not something that just arrived
        for port in sorted(new):
            if RADIO.search(port) or port in self._dismissed or self.job: continue
            asyncio.create_task(self._arrived(port))

    async def _arrived(self, port: str):
        who = await self.cable.hello(port)
        if who:
            if who["state"] == "set" and who["chip"] in self.pucks: return    # one of ours, visiting; nothing to do
            self.job = {"state": "knocking", "port": port, "bare": False, "chip": who["chip"], "fw": who["fw"]}
        elif await self.cable.is_esp(port):
            self.job = {"state": "knocking", "port": port, "bare": True, "chip": None}
        else:
            return
        if self.job: self._set("knocking")

    # ---- the person's two answers ----
    async def adopt(self) -> dict:
        if not self.job or self.job["state"] != "knocking": raise ValueError("Nothing is knocking.")
        self._task = asyncio.create_task(self._setup())
        return self.status()

    async def dismiss(self) -> dict:
        if self.job and self.job["state"] in ("knocking", "failed", "ready"):
            if self.job.get("port"): self._dismissed.add(self.job["port"])
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

    async def placed(self) -> dict:
        if not self.job or self.job["state"] != "placing": raise ValueError("Nothing is being placed.")
        self._set("ready", unplaced=self._unplaced(self.job.get("net")))
        return self.status()

    # ---- the job itself ----
    async def _setup(self):
        j = self.job
        try:
            self._set("working", step="software")
            if j["bare"]:
                await self.cable.flash(j["port"])
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
            if leaf == "status": p["online"] = payload == "online"
            elif leaf == "net": p["net"] = payload
            elif leaf == "proxy":
                mm = re.search(r"rssi (-?\d+)", payload); p["rssi"] = int(mm.group(1)) if mm else None
            if self.job and self.job.get("chip") == chip and self.job["state"] in ("placing", "ready") and p.get("net"):
                self.job["net"] = p["net"]
        elif len(parts) == 4 and parts[1] != "bridge":
            if parts[3] == "state":
                self.switches[(parts[1], parts[2])] = payload
            # Two switches on one light: the same stream is where a companion's press is heard.
            # One subscription for both, because there is only one thing to listen to (hub/relay.py).
            if (relay := getattr(self.hub, "relay", None)):
                relay.on_message(parts[1], parts[2], parts[3], payload, bool(m.get("retain")))

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
