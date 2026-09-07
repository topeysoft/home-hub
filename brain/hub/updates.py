"""Updates that explain themselves.

The brain knows which commit it is (baked into its image by CI), asks GitHub now and then what main is at,
and tells the panel when the two differ. Installing is the host's job: the panel's tap writes a request
file into the data volume, a systemd path unit on the host sees it and runs install.sh, which brings the
code to origin/main, pulls the images and restarts everything; update.json in the same volume says how it
went. The brain never runs docker itself and never restarts anything on its own.
"""
import asyncio, json, logging, os, time, urllib.request
from .settings import DATA

log = logging.getLogger("hub.updates")
REPO = os.environ.get("HUB_REPO") or "topeysoft/home-hub"
API = f"https://api.github.com/repos/{REPO}/commits/main"
EVERY = 6 * 3600
REQUEST = DATA / "update.request"     # the panel asked; the host's home-hub-update.path is watching for this file
STATE = DATA / "update.json"          # written by the host's update.sh: running, done or failed


class Updates:
    def __init__(self, hub):
        self.hub = hub
        self.version = os.environ.get("HUB_VERSION") or "dev"   # a tag, or main-<short sha>
        self.commit = os.environ.get("HUB_COMMIT") or ""
        self.latest, self.checked, self.error = None, None, None

    @property
    def available(self):
        """True when main has moved on from this build, False when not, None while nobody can tell."""
        if not self.commit or not self.latest: return None
        return self.latest["sha"] != self.commit

    def state(self):
        try: return json.loads(STATE.read_text())
        except (OSError, ValueError): return None

    def summary(self) -> dict:
        return {"version": self.version, "commit": self.commit[:12], "latest": self.latest, "available": self.available,
                "checked": self.checked, "requested": REQUEST.exists(), "state": self.state(), "error": self.error}

    def fetch(self) -> dict:
        req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "home-hub"})
        with urllib.request.urlopen(req, timeout=20) as r: d = json.loads(r.read())
        return {"sha": d["sha"], "when": d["commit"]["committer"]["date"], "title": d["commit"]["message"].splitlines()[0][:120]}

    async def check(self) -> dict:
        was = self.available
        try: self.latest, self.error = await asyncio.to_thread(self.fetch), None
        except Exception as e: self.error = str(e); log.info("update check: %s", e)
        self.checked = time.time()
        if self.available != was: self._tell()
        return self.summary()

    async def run(self):
        await asyncio.sleep(90)            # let the house come up first
        while True:
            try: await self.check()
            except Exception: log.exception("update check")
            await asyncio.sleep(EVERY)

    def request(self) -> dict:
        """The panel's tap. Writes the file the host watches; nothing happens in here."""
        REQUEST.parent.mkdir(parents=True, exist_ok=True)
        REQUEST.write_text(json.dumps({"at": time.time(), "from": self.commit, "to": (self.latest or {}).get("sha")}))
        self.hub.log.add("home", "update", self.commit[:12], ((self.latest or {}).get("sha") or "")[:12], source="user")
        self._tell(); return self.summary()

    def _tell(self):
        self.hub._broadcast(json.dumps({"type": "status", "status": self.hub.status()}))
