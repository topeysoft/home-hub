# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The hub's own memory: a small JSON file the panel is allowed to fill in during setup.

Lives in the data directory (HUB_DATA, or the brain folder), next to the event log. Holds the
driver's address and token, the owner's and the home's names, the location, how the panel looks,
and whether setup finished.

What belongs here is anything the HOUSE decides once and every screen then agrees on. What does
not is per-screen preference: which room a kiosk opens into, whether a phone has been offered the
home-screen install. Those stay in the browser, because two screens are allowed to differ on them.
"""
import json, os, secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("HUB_DATA") or ROOT)


class Settings:
    def __init__(self, path: Path = DATA / "settings.json"):
        self.path = path
        try: self.data = json.loads(path.read_text()) if path.exists() else {}
        except Exception: self.data = {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def hub_id(self) -> str:
        """This hub's own name for itself. Made once, at random, and kept.

        Not derived from the hardware. A MAC address or a machine-id would leak something about the
        house to anything the id is ever shown to, and would change under a household that moved the
        hub onto a new box -- which is the one moment it most wants to still be the same hub. It
        lives here, so it rides the backup and a restore keeps it.

        Nothing about the house can be read out of it, and nothing should ever be hung on it that a
        household would mind a stranger knowing. Today it decides which minute of the night this hub
        installs an update in, so that ten thousand houses do not all move at once.
        """
        v = self.get("hub_id")
        if not v:
            v = secrets.token_hex(8); self.set(hub_id=v)
        return v

    def set(self, **updates):
        self.data.update(updates)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1))
        os.replace(tmp, self.path)


def env_file() -> dict:
    """driver-layer/.env plus HA_*/HOME_* from the process: the developer's way in, and the fallback."""
    env = {}
    p = ROOT.parent / "driver-layer" / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith(("HA_", "HOME_"))})
    return env
