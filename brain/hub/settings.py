"""The hub's own memory: a small JSON file the panel is allowed to fill in during setup.

Lives in the data directory (HUB_DATA, or the brain folder), next to the event log. Holds the
driver's address and token, the owner's and the home's names, the location, and whether setup
finished. Never holds anything the app would show as a setting.
"""
import json, os
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
