"""Updates that explain themselves.

The brain knows which build it is (baked into its image by CI), asks GitHub now and then whether
there is a newer one, and tells the panel when there is. Installing is the host's job: the panel's
tap writes a request file into the data volume, a systemd path unit on the host sees it and runs
install.sh, which brings the code to the newest release, pulls the images and restarts everything;
update.json in the same volume says how it went. The brain never runs docker itself and never
restarts anything on its own.

Two channels, because a hub in someone's house and the hub on the developer's desk want different
things. `release` (the default, and what every hub ships as) follows version tags: nothing reaches a
family until it is tagged. `main` follows the branch, commit by commit, which is what a hub being
worked on wants. install.sh writes HUB_CHANNEL into the compose environment; nothing else chooses.
"""
import asyncio, json, logging, os, re, time, urllib.request
from .settings import DATA

log = logging.getLogger("hub.updates")
REPO = os.environ.get("HUB_REPO") or "topeysoft/home-hub"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
MAIN_API = f"https://api.github.com/repos/{REPO}/commits/main"
EVERY = 6 * 3600
REQUEST = DATA / "update.request"     # the panel asked; the host's home-hub-update.path is watching for this file
STATE = DATA / "update.json"          # written by the host's update.sh: running, done or failed
RELEASE = re.compile(r"^v?\d+\.\d+")  # what a version tag looks like, next to "dev" and "main-1a2b3c4"


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "home-hub"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


class Updates:
    def __init__(self, hub):
        self.hub = hub
        self.version = os.environ.get("HUB_VERSION") or "dev"   # a tag, or main-<short sha>
        self.commit = os.environ.get("HUB_COMMIT") or ""
        self.channel = "main" if (os.environ.get("HUB_CHANNEL") or "release").lower() == "main" else "release"
        self.latest, self.checked, self.error = None, None, None

    @property
    def available(self):
        """True when there is a newer build than this one, False when not, None while nobody can tell.

        None is the honest answer more often than it looks: a hub built from a working copy has no
        version to compare, and a hub following releases cannot say anything until it has been asked
        for one. A panel showing "up to date" when it does not know would be a lie a person acts on.
        """
        if not self.latest: return None
        if self.channel == "main":
            return self.latest["sha"] != self.commit if self.commit else None
        if not RELEASE.match(self.version): return None     # this build is not on the release channel at all
        return self._norm(self.latest["version"]) != self._norm(self.version)

    @staticmethod
    def _norm(v: str) -> str:
        """`v0.2.0` and `0.2.0` are the same release. CI tags the image without the v; git carries it."""
        return (v or "").lstrip("vV")

    def state(self):
        try: return json.loads(STATE.read_text())
        except (OSError, ValueError): return None

    def summary(self) -> dict:
        return {"version": self.version, "commit": self.commit[:12], "channel": self.channel, "latest": self.latest,
                "available": self.available, "checked": self.checked, "requested": REQUEST.exists(),
                "state": self.state(), "error": self.error}

    def fetch(self) -> dict:
        if self.channel == "main":
            d = _get(MAIN_API)
            return {"version": f"main-{d['sha'][:7]}", "sha": d["sha"], "when": d["commit"]["committer"]["date"],
                    "title": d["commit"]["message"].splitlines()[0][:120]}
        d = _get(RELEASE_API)
        # A release with no title of its own is named by its tag; the panel puts this in a sentence.
        return {"version": d["tag_name"], "sha": d.get("target_commitish") or "",
                "when": d.get("published_at") or "", "title": (d.get("name") or d["tag_name"])[:120]}

    async def check(self) -> dict:
        was = self.available
        try: self.latest, self.error = await asyncio.to_thread(self.fetch), None
        except Exception as e:
            self.error = str(e); log.info("update check: %s", e)
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
        want = (self.latest or {}).get("version") or ""
        REQUEST.parent.mkdir(parents=True, exist_ok=True)
        REQUEST.write_text(json.dumps({"at": time.time(), "channel": self.channel, "from": self.version, "to": want,
                                       "from_commit": self.commit, "to_commit": (self.latest or {}).get("sha") or ""}))
        self.hub.log.add("home", "update", self.version, want, source="user")
        self._tell(); return self.summary()

    def _tell(self):
        self.hub._broadcast(json.dumps({"type": "status", "status": self.hub.status()}))
