"""A code on the settings.

Controlling the house never needs it: lights, scenes, doors work from the wall for anyone. Changing
the house does: adding devices, renaming, moving rooms, the location, the rules, and the engine's
own sign-in behind the Advanced door. No code set means nothing is locked, which is how a hub
starts; setup offers one, and Home nudges until there is one.
"""
import hashlib, hmac, os, time

ROUNDS = 200_000
TRIES, WINDOW = 5, 60.0     # five wrong codes in a minute and that address waits the minute out


def needs_code(method: str, path: str) -> bool:
    """Which requests change the house rather than drive it."""
    m = method.upper()
    if path == "/setup/advanced": return True
    if path.startswith("/setup/") and m == "POST": return path != "/setup/status"
    if path == "/rooms" and m == "POST": return True
    if path.startswith("/rooms/") and (m == "DELETE" or path.endswith("/rename")): return True
    if path.startswith("/devices/") and path.endswith(("/move", "/rename")): return True
    if path.startswith(("/flows", "/credentials")): return True
    if path == "/location" and m == "POST": return True
    if path.startswith("/rules") and m in ("PUT", "POST", "DELETE"): return True
    return False


class Lock:
    def __init__(self, settings):
        self.settings = settings
        self._fails: dict[str, list[float]] = {}

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
        self._fails[who] = fails
        return (fails[0] + WINDOW - now) if len(fails) >= TRIES else 0.0

    def check(self, code: str | None, who: str = "") -> bool:
        if not self.locked: return True
        if self.waiting(who) > 0: return False
        p = self.settings.get("pin")
        ok = bool(code) and hmac.compare_digest(self._digest(code, bytes.fromhex(p["salt"])), p["hash"])
        if not ok: self._fails.setdefault(who, []).append(time.time())
        else: self._fails.pop(who, None)
        return ok
