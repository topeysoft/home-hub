# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How this hub is connected, and what it hands to the things it sets up.

The hub was designed on a cable, and the cable hid a bug: the Wi-Fi it writes into a bridge puck is
a copy somebody typed once (`Bridges.wifi`), and nothing ever re-checks it. Change the house's
password and the hub goes on confidently writing the old one into every puck it ever sets up.

The rule this module adds is docs/network.md's: **the hub gives out what the hub is using.** A hub
on Wi-Fi reads its own connection and hands that out; a hub on a cable is the one case that still
has to be told, and then the panel says so in those words rather than stating it as a fact.

WHAT THIS DOES NOT DO IS CONFIGURE THE HOST. The brain does not run nmcli any more than it runs
docker: it reads `network.json`, which the host's network.sh writes, and it writes
`network.request`, which the host's home-hub-network.path is watching for. The request names a verb
from a fixed list and carries data as data -- never a command, an interface name or an argument
list. That is updates.py's rule and restart.sh's shape, and keeping the three alike is what stops
"can write the data volume" from becoming "can run anything as root".

A hub with no host script at all -- a developer's laptop, a container on somebody's NAS -- still
answers here. It reports what it can see for itself and says plainly that it cannot change it,
which is better than a panel that offers a button that does nothing.
"""
import json, logging, os, socket, time
from pathlib import Path

from .settings import DATA

log = logging.getLogger("hub.network")

STATE = DATA / "network.json"        # the host's network.sh writes this; we only read it
REQUEST = DATA / "network.request"   # we write this; home-hub-network.path is watching for it
# How stale the host's picture may be before the panel stops calling it current. The timer refreshes
# every minute, so two minutes is one missed tick and not a judgment about the network.
STALE = 150
SCAN_WAIT = 25                       # how long a scan may take before we answer with what we have
# What the signal numbers mean in words. Nobody has ever made a decision from "-61 dBm", and a bar
# chart of five bars is the same number wearing a costume.
STRONG, OK = 65, 40


def lan_ip() -> str:
    """The address this hub answers on, worked out without sending a packet."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def hostname() -> str:
    """The name this hub actually answers to, for the pucks to resolve.

    Not a guess: install.sh sets `hub`, but a second hub on the same LAN becomes `hub-2`, and a puck
    told the wrong name falls back to an address that will one day be somebody else's."""
    try:
        n = socket.gethostname().split(".")[0].strip()
        return n or "hub"
    except Exception:
        return "hub"


def words(signal) -> str | None:
    """A percentage into the three words a person can act on."""
    if signal is None:
        return None
    try: n = int(signal)
    except (TypeError, ValueError): return None
    return "strong" if n >= STRONG else "ok" if n >= OK else "faint"


class Network:
    def __init__(self, hub, state: Path = STATE, request: Path = REQUEST):
        self.hub = hub
        self.state_path = state
        self.request_path = request

    # ---- what the host says ----

    def _host(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except Exception:
            return {}

    def managed(self) -> bool:
        """Is there a host script behind this hub at all?

        The file existing is the whole test. A hub where it never appears is a hub nobody can offer
        a Change button to, and saying that out loud beats a button that writes a file into the void.
        """
        return self.state_path.exists()

    def links(self) -> list:
        return [l for l in self._host().get("links") or [] if isinstance(l, dict)]

    def state(self) -> dict:
        """One picture of this hub's connection, in the panel's terms.

        `how` is the only thing most of the panel cares about: cable, wifi, or unknown -- and unknown
        is honest rather than empty. Everything else hangs off it.
        """
        host = self._host()
        links = self.links()
        wired = next((l for l in links if l.get("kind") == "ethernet" and l.get("up")), None)
        wifi = next((l for l in links if l.get("kind") == "wifi" and l.get("up")), None)
        radio = next((l for l in links if l.get("kind") == "wifi"), None)

        out: dict = {
            "how": "cable" if wired else "wifi" if wifi else "unknown" if not self.managed() else "none",
            "ip": (wired or wifi or {}).get("ip") or lan_ip(),
            "name": host.get("hostname") or hostname(),
            # A hub with no radio must never be offered a Wi-Fi it cannot join, and a hub with no
            # host script must never be offered a button that writes into the void.
            "can_change": bool(self.managed() and radio),
            "managed": self.managed(),
        }
        if wifi:
            out["ssid"] = wifi.get("ssid")
            out["signal"] = words(wifi.get("signal"))
            out["band"] = wifi.get("band")
        # A hub on a cable that ALSO has Wi-Fi configured is not a hub in trouble: the cable wins
        # while it is there and the Wi-Fi is the spare. Say so rather than hiding it.
        if wired and radio and radio.get("ssid"):
            out["spare"] = radio.get("ssid")
        if host.get("at") and time.time() - host["at"] > STALE:
            out["stale"] = True
        if host.get("moving"):
            out["moving"] = host["moving"]          # a change is in flight, and the host is watching it
        if host.get("reverted"):
            out["reverted"] = host["reverted"]      # ...and one came back, so say which
        return out

    def seen(self) -> list:
        """The networks the host last saw, strongest first, without the hub's own repeated."""
        host = self._host()
        out = []
        for n in host.get("scan") or []:
            if not isinstance(n, dict) or not n.get("ssid"):
                continue
            out.append({"ssid": n["ssid"], "signal": words(n.get("signal")),
                        "band": n.get("band") or None, "secure": bool(n.get("secure", True))})
        out.sort(key=lambda n: {"strong": 0, "ok": 1, "faint": 2}.get(n["signal"], 3))
        seen, uniq = set(), []
        for n in out:
            if n["ssid"] in seen: continue
            seen.add(n["ssid"]); uniq.append(n)
        return uniq

    def scanned(self) -> float:
        return float(self._host().get("scanned") or 0)

    # ---- what we ask the host for ----

    def _ask(self, do: str, **data) -> None:
        """Write the request, with the verb checked HERE as well as in the script.

        Checked twice on purpose. The script checks because it must -- it is the thing with the root
        -- and this checks because a typo here should be a stack trace in the brain's log rather than
        a silent no-op a household is left staring at."""
        if do not in ("scan", "join", "forget", "off"):
            raise ValueError(f"not a thing this hub knows how to do: {do}")
        self.request_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.request_path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"do": do, "at": time.time(), **data}))
        # A Wi-Fi password sits in here for the second it takes the host to pick it up. Narrow the
        # window that it is readable in, before it is visible at all.
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.request_path)

    async def scan(self) -> dict:
        """Ask the host to look, then answer with what it found.

        Waits, rather than returning immediately and making the panel poll: a scan is a thing a
        person is standing in front of, and two seconds of nothing is what a spinner is for."""
        import asyncio
        if not self.managed():
            return {"networks": [], "can_change": False}
        before = self.scanned()
        self._ask("scan")
        end = time.time() + SCAN_WAIT
        while time.time() < end:
            await asyncio.sleep(0.5)
            if self.scanned() > before:
                break
        return {"networks": self.seen(), "can_change": True, "at": self.scanned()}

    def join(self, ssid: str, password: str) -> dict:
        """Put the hub itself on a Wi-Fi.

        The host applies it, then watches for the brain to be reachable and STAY reachable, and puts
        the old connection back if it is not. That watch is what makes this button safe to offer at
        all -- without it, one wrong password takes the hub off the network with nothing left that
        could tell it so."""
        ssid = (ssid or "").strip()
        if not ssid:
            raise ValueError("Which Wi‑Fi? The name is needed.")
        if not self.managed():
            raise ValueError("This hub's network is looked after by the machine it runs on, so it can't be changed from here.")
        self._ask("join", ssid=ssid, password=password or "")
        self.hub.log.add("home", "network", None, f"joining {ssid}", source="user")
        return {**self.state(), "moving": {"ssid": ssid, "since": time.time()}}
