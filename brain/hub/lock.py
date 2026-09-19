# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A code on the settings.

Controlling the house never needs it: lights, scenes, doors work from the wall for anyone. Changing
the house does: adding devices, renaming, moving rooms, the location, the rules, and the engine's
own sign-in behind the Advanced door. No code set means nothing is locked, which is how a hub
starts; setup offers one, and Home nudges until there is one.
"""
import hashlib, hmac, json, os, time

ROUNDS = 200_000
TRIES, WINDOW = 5, 60.0     # five wrong codes in a minute and that address waits the minute out


def needs_code(method: str, path: str) -> bool:
    """Which requests change the house rather than drive it."""
    m = method.upper()
    if path == "/setup/advanced": return True
    if path.startswith("/setup/") and m == "POST": return path != "/setup/status"
    if path == "/rooms" and m == "POST": return True
    if path.startswith("/rooms/") and (m == "DELETE" or path.endswith("/rename")): return True
    if path.startswith("/devices/") and path.endswith(("/move", "/rename", "/share")): return True   # what leaves the house is a change to it
    if path.startswith("/devices/") and m == "DELETE": return True           # forgetting one is a change to the house, not a tap
    if path.startswith(("/flows", "/credentials")): return True
    if path.startswith("/accounts") and m == "DELETE": return True   # everything it brought goes with it
    if path in ("/location", "/home/entry") and m == "POST": return True
    if path.startswith("/rules") and m in ("PUT", "POST", "DELETE"): return True
    if path == "/drafts/suggest": return False                                   # looking for habits changes nothing
    if path.startswith("/drafts/") and m in ("POST", "DELETE"): return True   # approving or discarding a suggestion; asking for one stays open
    if path == "/assistant/key": return True
    if path in ("/update", "/update/auto") and m == "POST": return True   # changing how the house updates itself is a setting
    if path == "/backup" or (path == "/restore" and m == "POST"): return True   # the archive carries the house's keys
    # Taking the house down for a minute is a change to it, not a tap on it -- and it is the one change
    # whose whole effect is that nothing works. Asking what a restart would cost is not: a sheet that
    # demanded the code before it would tell you what the button does is a sheet nobody reads.
    if path == "/restart" and m == "POST": return True
    if path.startswith("/pair") and m != "GET": return True
    # Adopting a bridge hands a thing somebody just plugged in the house's Wi-Fi, the broker and the
    # keys to the switches. That is the largest single giveaway on this list -- larger than renaming
    # a room, which is gated -- and /bridge/wifi is where those Wi-Fi credentials are typed in the
    # first place. Saying "not mine" and "leave it here" are not here on purpose: refusing a thing
    # and reporting where it ended up give nothing away, and a code to wave a knock off would leave
    # one stuck on the screen for whoever could not remember it.
    if path in ("/bridge/adopt", "/bridge/wifi") and m == "POST": return True
    # Sharing the house with Apple Home, Google Home or Alexa is a change to the house, not a tap on
    # it. The bridge's own routes are not here: they never reach this function, because the service
    # token answered for them before the gate. docs/matter.md.
    if path.startswith("/share") and m == "POST": return True   # turning it on, and letting one more app in
    if path.startswith("/phones") and m != "GET": return path not in ("/phones/ask", "/phones/code")   # letting a phone in, or out, is a setting; asking is not
    return False


class Lock:
    """The code, and the short memory of who has been getting it wrong.

    That memory is on disk, and it is on disk because of the restart button. Five wrong codes make an
    address wait the minute out, and while the count lived only in this process anybody who could make
    the brain start again got five fresh guesses -- which used to mean somebody at the plug, and now
    means one tap on a phone (docs/restart.md, piece 9). The file is written only when a code is
    wrong, so a house where nobody is guessing never touches it.
    """
    def __init__(self, settings):
        self.settings = settings
        self.tries = settings.path.parent / "tries.json"
        self._fails: dict[str, list[float]] = {}
        self._load()

    def _load(self):
        try: kept = json.loads(self.tries.read_text())
        except (OSError, ValueError): return
        now = time.time()
        # Anything already outside the window is not worth carrying, and a clock that went backwards
        # over the restart (a Pi with no battery, reading the epoch until NTP answers) would otherwise
        # leave a wait nothing could run down.
        self._fails = {who: [t for t in ts if 0 < now - t < WINDOW] for who, ts in (kept or {}).items() if isinstance(ts, list)}
        self._fails = {who: ts for who, ts in self._fails.items() if ts}

    def _save(self):
        try:
            self.tries.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.tries.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._fails))
            os.replace(tmp, self.tries)
        except OSError: pass     # a full or read-only disk must not turn into a house that cannot be typed into

    @property
    def locked(self) -> bool:
        return bool(self.settings.get("pin"))

    @staticmethod
    def _digest(pin: str, salt: bytes) -> str:
        return hashlib.pbkdf2_hmac("sha256", pin.encode(), salt, ROUNDS).hex()

    def set(self, pin: str):
        if not pin:
            self.settings.set(pin=None); return
        if not (pin.isdigit() and 4 <= len(pin) <= 8): raise ValueError("A code is 4 to 8 digits.")
        salt = os.urandom(16)
        self.settings.set(pin={"salt": salt.hex(), "hash": self._digest(pin, salt)})

    def waiting(self, who: str) -> float:
        """Seconds this address still has to wait, or 0."""
        now = time.time()
        fails = [t for t in self._fails.get(who, []) if now - t < WINDOW]
        # Kept only while there is something to keep. An empty list left behind here would make every
        # correct code look like a state change and write the file on the ordinary path.
        if fails: self._fails[who] = fails
        else: self._fails.pop(who, None)
        return (fails[0] + WINDOW - now) if len(fails) >= TRIES else 0.0

    def check(self, code: str | None, who: str = "") -> bool:
        if not self.locked: return True
        if self.waiting(who) > 0: return False
        p = self.settings.get("pin")
        ok = bool(code) and hmac.compare_digest(self._digest(code, bytes.fromhex(p["salt"])), p["hash"])
        if not ok: self._fails.setdefault(who, []).append(time.time())
        elif who not in self._fails: return ok      # the ordinary path writes nothing
        else: self._fails.pop(who, None)
        self._save()
        return ok
