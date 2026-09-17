"""Two switches, one light: the hub carries the press across.

A two-way switch is two switches wired to one light. In a Brilliant house the wiring is not in the
walls -- the companion switch has no load at all, it is a radio node that reports its own touch, and
something has to hear that and drive the switch the light is actually wired to. The Brilliant console
was that something. When the console goes, every companion in the house becomes a button that does
nothing, so the hub takes the job: a link says "when this one is touched, do the same to that one".

The two ends need not be on the same mesh. The stairway is the case that made this: the companion
sits on the house's own network behind one puck, the load is still on the panel's network behind
another, and the only place the two meet is the broker. So a link is nothing but a rule about topics:

    mesh/<from-net>/<from-addr>/state       ->   mesh/<to-net>/<to-addr>/set
    mesh/<from-net>/<from-addr>/brightness  ->   mesh/<to-net>/<to-addr>/brightness/set

A link says how to listen, and for a companion the answer is NOT its state. Watching a real pair
settled it: a companion announces a press as a vendor message addressed to its partner (`0403` on
0xc12008, three presses out of three), while its OWN on/off position drifts free of the light -- the
companion said ON while the load said OFF on the same sweep. So mirroring a companion's state would
drive the light to whatever arbitrary position the companion happened to be holding. What a companion
means is "somebody pressed me", and the honest answer to that is to TOGGLE the load.

    on: "press"   a vendor press from this switch toggles the load. Two switches, one light.
    on: "state"   the load is made to match this switch. One light following another.

Four things keep it honest, and each one is a bug that was reasoned out before it could happen:

  * a retained message is not a press. Every puck republishes all of its state, retained, on every
    reconnect to the broker. Retained messages only ever set the baseline here; they never act.
  * a message is not a press either -- a CHANGE is. The puck resyncs every switch on link-up and
    again every ten minutes, so the same value arrives over and over. A link fires when the value
    differs from the last one we had, which is also, correctly, how a press made while the hub was
    away still gets carried when it is next heard.
  * what we send comes back. The puck publishes the state of everything it hears, including the
    result of our own command; without a guard a pair of links pointed at each other would volley
    forever. Anything we just sent is ignored on the way back for a few seconds.
  * a command can be dropped. The link is BLE mesh and the answer is the load's own Status, so a
    send is confirmed by the load's state arriving as asked, and retried a couple of times if it
    does not. Below about -80 dBm no amount of retrying helps; that is a job for where the puck sits.

Links live in the data directory, made by hand today (POST /bridge/links). Pairing in the product --
the phone scanning both codes at setup, the extra press on the wall -- writes the same rows.
"""
import asyncio, json, logging, os, time
from pathlib import Path

from .settings import DATA

log = logging.getLogger("hub.relay")
LINKS = DATA / "switch-links.json"
BASE = "mesh"
SETTLE = 0.2      # a press publishes state and brightness together; send once, not twice
CONFIRM = 2.0     # the load answers with its own Status well inside this when the link is good
TRIES = 3
ECHO = 3.0        # how long our own command is ignored coming back
PRESS = 0.4       # a mesh message can arrive twice; two presses by hand are never this close
VENDOR = "0xc12008"   # the model a Brilliant switch says everything of its own on
PRESSED = "04"        # ...and the command byte that means a finger, `0403` being press-and-argument


def _addr(s: str) -> str:
    """0x0011, 0011, 11 -> 0011. One spelling in the file, whatever a person types."""
    s = str(s).strip().lower().removeprefix("0x")
    if not s or len(s) > 4 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError(f"not a switch address: {s!r}")
    return s.rjust(4, "0")


def _net(s: str) -> str:
    s = str(s).strip().lower()
    if len(s) != 16 or any(c not in "0123456789abcdef" for c in s):
        raise ValueError(f"not a network id: {s!r}")
    return s


def pressed(payload: str) -> str | None:
    """The partner a vendor press names, or None if this message is not a press.

    A companion press is `0403` on the vendor model, addressed to the switch it works with -- which is
    why a press names its pair outright. Anything else on that model is configuration or a heartbeat."""
    try:
        e = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if e.get("kind") != "vendor" or e.get("opcode") != VENDOR:
        return None
    if not str(e.get("params") or "").startswith(PRESSED):
        return None
    return str(e.get("dst") or "")


class Relay:
    """The links, and the press being carried. Publishing goes through the engine, like everything else."""

    def __init__(self, hub, path: Path = LINKS, base: str = BASE):
        self.hub = hub
        self.path = path
        self.base = base
        self.settle, self.confirm, self.tries = SETTLE, CONFIRM, TRIES
        self.links: list[dict] = []
        self._value: dict[tuple, str] = {}    # (net, addr, leaf) -> the last value we were told
        self._sent: dict[tuple, float] = {}   # (net, addr) -> when we last drove it ourselves
        self._pressed: dict[tuple, float] = {}  # (net, addr) -> when a press from it last counted
        self._pending: dict[str, asyncio.Task] = {}
        self._tasks: set[asyncio.Task] = set()
        self.carried = 0                      # presses carried since the brain started, for the log
        self.load()

    # ---------------------------------------------------------------- the file

    def load(self):
        try:
            raw = json.loads(self.path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            raw = {}
        self.links = [l for l in (raw.get("links") or []) if self._ok(l)]

    def _ok(self, l) -> bool:
        """Also fills in how to listen, so a link written by hand is not silently half a rule. A row
        from before there was a choice means "state": that is what it was doing when it was written."""
        try:
            ok = bool(_net(l["from"]["net"]) and _addr(l["from"]["addr"])
                      and _net(l["to"]["net"]) and _addr(l["to"]["addr"]))
        except (KeyError, TypeError, ValueError):
            log.warning("relay: ignoring a link that does not name two switches: %r", l)
            return False
        if l.get("on") not in ("press", "state"):
            if l.get("on") is not None:
                log.warning("relay: %r is not a way to listen; taking %s as a mirror", l.get("on"), l.get("id"))
            l["on"] = "state"
        return ok

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"links": self.links}, indent=1))
        os.replace(tmp, self.path)

    def as_data(self) -> dict:
        return {"links": self.links, "carried": self.carried}

    def add(self, frm: dict, to: dict, name: str = "", enabled: bool = True, on: str = "press") -> dict:
        """One companion, one load. Adding the same pair twice updates it rather than doubling it.

        `on` is what to listen to: "press" (a companion -- toggle the load) or "state" (mirror)."""
        if on not in ("press", "state"):
            raise ValueError(f"a link listens for a press or a state, not {on!r}")
        link = {"id": f"{_net(frm['net'])[:4]}{_addr(frm['addr'])}-{_net(to['net'])[:4]}{_addr(to['addr'])}",
                "name": str(name or "").strip(),
                "from": {"net": _net(frm["net"]), "addr": _addr(frm["addr"])},
                "to": {"net": _net(to["net"]), "addr": _addr(to["addr"])},
                "on": on,
                "enabled": bool(enabled)}
        if link["from"] == link["to"]:
            raise ValueError("a switch cannot be its own companion")
        self.links = [l for l in self.links if l["id"] != link["id"]] + [link]
        self.save()
        return link

    def remove(self, link_id: str) -> bool:
        before = len(self.links)
        self.links = [l for l in self.links if l["id"] != link_id]
        if len(self.links) == before:
            return False
        self.save()
        return True

    # ---------------------------------------------------------------- the broker

    def on_message(self, net: str, addr: str, leaf: str, payload: str, retain: bool):
        """Every `mesh/<net>/<addr>/<leaf>` the brain hears, from hub.bridge's one subscription.

        Retained sets the baseline and stops there. Live decides whether anything moved."""
        if leaf == "event":
            if not retain and pressed(payload) is not None:
                self._press(net, addr)
            return
        if leaf not in ("state", "brightness"):
            return
        key = (net, addr, leaf)
        was, self._value[key] = self._value.get(key), payload
        if retain or was is None or was == payload:
            return
        if time.monotonic() - self._sent.get((net, addr), 0) < ECHO:
            return                    # this is our own command coming back
        for link in self._for(net, addr, "state"):
            self._soon(link)

    def _for(self, net: str, addr: str, on: str):
        """The enabled links listening to this switch, in this way. A press link is deaf to state and
        a state link is deaf to presses: a companion does both and would otherwise act twice."""
        return [l for l in self.links
                if l.get("enabled", True) and l.get("on", "state") == on
                and l["from"]["net"] == net and l["from"]["addr"] == addr]

    def _press(self, net: str, addr: str):
        """Somebody pressed this switch. The mesh can deliver the same message twice; a hand cannot."""
        now = time.monotonic()
        if now - self._pressed.get((net, addr), 0) < PRESS:
            return
        self._pressed[(net, addr)] = now
        for link in self._for(net, addr, "press"):
            self._spawn(self._toggle(link))

    async def _toggle(self, link: dict):
        """A press says a person wants the other thing, so the load goes to the opposite of where it is.

        If we have never heard the load's state we do not guess: a light that comes on when somebody
        meant to turn it off is worse than one that does nothing and says why."""
        to = link["to"]
        what = link.get("name") or f"{link['from']['addr']} \u2192 {to['addr']}"
        now = (self._value.get((to["net"], to["addr"], "state")) or "").upper()
        if now not in ("ON", "OFF"):
            log.warning("relay: %s pressed, but %s has never said whether it is on", what, to["addr"])
            self._say(what, to, "toggle")
            return
        want = "OFF" if now == "ON" else "ON"
        if await self._drive(to, want):
            self.carried += 1
            log.info("relay: %s pressed -- %s turned %s", what, to["addr"], want.lower())
        else:
            log.warning("relay: %s pressed, but %s did not answer -- asked %d times", what, to["addr"], self.tries)
            self._say(what, to, want)

    def _soon(self, link: dict):
        """Coalesce: a press lands as state and brightness a moment apart, and is one command."""
        old = self._pending.get(link["id"])
        if old and not old.done():
            old.cancel()
        self._pending[link["id"]] = self._spawn(self._carry(link))

    def _spawn(self, coro) -> asyncio.Task:
        t = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(t)
        t.add_done_callback(self._tasks.discard)
        return t

    async def _carry(self, link: dict):
        try:
            await asyncio.sleep(self.settle)
            f, to = link["from"], link["to"]
            state = self._value.get((f["net"], f["addr"], "state"))
            bright = self._value.get((f["net"], f["addr"], "brightness"))
            if state is None:
                return
            want = "OFF" if state.upper() == "OFF" else "ON"
            ok = await self._drive(to, want)
            # A dimmer press is a level, and the level is the point; only worth sending with the light on.
            if want == "ON" and bright is not None and bright.isdigit() and 0 < int(bright) < 255:
                self._sent[(to["net"], to["addr"])] = time.monotonic()
                await self._publish(f"{self.base}/{to['net']}/{to['addr']}/brightness/set", bright)
            what = link.get("name") or f"{f['addr']} → {to['addr']}"
            if ok:
                self.carried += 1
                log.info("relay: %s carried to %s (%s)", what, to["addr"], want)
            else:
                log.warning("relay: %s did not answer -- %s asked %d times, no Status back", what, to["addr"], self.tries)
                self._say(what, to, want)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("relay: %s: %s", link.get("id"), e)

    async def _drive(self, to: dict, want: str) -> bool:
        """Say it, then wait for the load's own Status to say it back. Retry while nothing comes."""
        key, topic = (to["net"], to["addr"]), f"{self.base}/{to['net']}/{to['addr']}/set"
        for _ in range(self.tries):
            self._sent[key] = time.monotonic()
            await self._publish(topic, want)
            end = asyncio.get_running_loop().time() + self.confirm
            while asyncio.get_running_loop().time() < end:
                await asyncio.sleep(0.05)
                if (self._value.get((to["net"], to["addr"], "state")) or "").upper() == want:
                    return True
        return False

    async def _publish(self, topic: str, payload: str):
        await self.hub.ha.call("mqtt", "publish", None, topic=topic, payload=payload)

    def _say(self, what: str, to: dict, want: str):
        log_ = getattr(self.hub, "log", None)
        if log_:
            log_.add("bridge", to["addr"], None, "did not answer", source="rule",
                     detail={"relay": what, "asked": want})
