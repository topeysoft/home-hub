"""Backup and restore: the house's settings and the driver layer's state as one file the panel can hand you,
and take back.

The archive holds `data/` (the brain's settings, event log and rule files) and `driver/` (the engine's
config, the radios' network keys, Ring's sign-in, the front door's certificate authority), leaving out what
is rebuilt or merely big: the engine's history database, logs, downloaded dependencies. Restoring is the
host's job, like updating: the upload is parked in the data volume with a request file, and
home-hub-restore.path on the host stops the house, unpacks, and starts it again. The file holds secrets
(the engine's key, the settings code's hash, the assistant's key), so it is behind the settings code.
"""
import fnmatch, io, json, os, re, sqlite3, tarfile, tempfile, time
from pathlib import Path
from .settings import DATA, ROOT

DRIVER = Path(os.environ.get("HUB_DRIVER") or ROOT.parent / "driver-layer")
DATA_FILES = ("settings.json", "events.db", "rules.json", "scenes.json", "phones.json")
# what to take from the driver layer, and what to leave behind inside each part
PARTS = [
    (".env", ()),
    ("homeassistant", ("home-assistant_v2.db", "home-assistant_v2.db-shm", "home-assistant_v2.db-wal", "*.log", "*.log.*", "deps", "tts", "__pycache__", ".cache")),
    ("zigbee2mqtt", ("log",)),
    ("zwave-js-ui", ("logs", "backups")),
    ("ring-mqtt", ("logs", "*.log")),
    ("matter-server", ()),
    ("caddy/data", ()),
]
REQUEST, STATE, ARCHIVE = DATA / "restore.request", DATA / "restore.json", DATA / "restore.tar.gz"


def _skipper(prefix, patterns):
    def keep(ti):
        rel = ti.name[len(prefix):].lstrip("/")
        parts = rel.split("/") if rel else []
        if any(fnmatch.fnmatch(p, pat) for p in parts for pat in patterns): return None
        return ti
    return keep


class Backup:
    def __init__(self, hub): self.hub = hub

    def name(self) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", (self.hub.settings.get("home_name") or "home").lower()).strip("-") or "home"
        return f"home-hub-{slug}-{time.strftime('%Y%m%d-%H%M')}.tar.gz"

    def make(self) -> Path:
        """Write the archive to a fresh temp directory and return its path. The caller deletes it after sending."""
        out = Path(tempfile.mkdtemp(prefix="hub-backup-")) / self.name()
        taken = {"data": [], "driver": []}
        with tarfile.open(out, "w:gz") as tar, tempfile.TemporaryDirectory() as tmp:
            for name in DATA_FILES:
                p = DATA / name
                if not p.exists(): continue
                if name == "events.db":                      # a consistent copy, whatever is being written right now
                    copy = Path(tmp) / name
                    src, dst = sqlite3.connect(p), sqlite3.connect(copy)
                    with dst: src.backup(dst)
                    src.close(); dst.close(); p = copy
                tar.add(p, arcname=f"data/{name}"); taken["data"].append(name)
            for rel, skip in PARTS:
                src = DRIVER / rel
                if not src.exists(): continue
                tar.add(src, arcname=f"driver/{rel}", filter=_skipper(f"driver/{rel}", skip)); taken["driver"].append(rel)
            manifest = {"made": time.time(), "version": self.hub.updates.version, "home": self.hub.settings.get("home_name"),
                        "owner": (self.hub.settings.get("owner") or {}).get("name"), **taken}
            body = json.dumps(manifest, indent=1).encode()
            ti = tarfile.TarInfo("manifest.json"); ti.size, ti.mtime = len(body), int(time.time())
            tar.addfile(ti, io.BytesIO(body))
        self.hub.log.add("home", "backup", None, out.name, source="user", detail=taken)
        return out

    def receive(self, body: bytes) -> dict:
        """An uploaded archive. Checked, parked in the data volume, and asked of the host. Nothing is unpacked here."""
        try:
            if len(body) < 64: raise ValueError
            with tarfile.open(fileobj=io.BytesIO(body), mode="r:gz") as tar:
                names = tar.getnames()
                if "manifest.json" not in names: raise ValueError
                for n in names:
                    if n.startswith("/") or ".." in n.split("/"): raise ValueError
                manifest = json.loads(tar.extractfile("manifest.json").read())
        except (tarfile.TarError, ValueError, KeyError, OSError, AttributeError):
            raise ValueError("That is not a backup this hub can read.")
        ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
        ARCHIVE.write_bytes(body)
        REQUEST.write_text(json.dumps({"at": time.time(), "manifest": manifest}))
        self.hub.log.add("home", "restore", None, "requested", source="user", detail=manifest)
        return {"ok": True, "manifest": manifest}

    def state(self):
        try: return json.loads(STATE.read_text())
        except (OSError, ValueError): return None
