# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Updates that explain themselves.

The brain knows which build it is (baked into its image by CI), asks GitHub now and then whether
there is a newer one, and tells the panel when there is. Installing is the host's job: the panel's
tap writes a request file into the data volume, a systemd path unit on the host sees it and runs
install.sh, which brings the code to the newest release, pulls the images and restarts everything;
update.json in the same volume says how it went. The brain never runs docker itself and never
restarts anything on its own.

The host also undoes an update that does not come back: it records where the hub was, waits for the
brain to answer on the loopback and keep answering, and otherwise puts the old commit and the old
image back. What arrives here is a fourth state, `reverted`, naming the version that did it -- which
is the one thing this module has to act on, because a rollback followed six hours later by the same
install is a loop rather than a safety net. See docs/updates.md, piece 1.

Two channels, because a hub in someone's house and the hub on the developer's desk want different
things. `release` (the default, and what every hub ships as) follows version tags: nothing reaches a
family until it is tagged. `main` follows the branch, commit by commit, which is what a hub being
worked on wants. install.sh writes HUB_CHANNEL into the compose environment; nothing else chooses.
"""
import asyncio, hashlib, json, logging, os, re, time, urllib.request
from datetime import datetime

from . import notes
from .settings import DATA

log = logging.getLogger("hub.updates")
REPO = os.environ.get("HUB_REPO") or "topeysoft/home-hub"
RELEASE_API = f"https://api.github.com/repos/{REPO}/releases/latest"
MAIN_API = f"https://api.github.com/repos/{REPO}/commits/main"
EVERY = 6 * 3600
RECHECK = 5 * 60                      # how soon opening This hub can make the hub ask GitHub again
TICK = 300                            # how often the loop looks at the clock, as against at GitHub
WINDOW = (2, 5)                       # the local hours a house is most likely to be asleep
QUIET = 30 * 60                       # ...and how long since anybody asked the house for anything
RETRY = 12 * 3600                     # one go a night, so a failing update does not run all night
REQUEST = DATA / "update.request"     # the panel asked; the host's home-hub-update.path is watching for this file
STATE = DATA / "update.json"          # written by the host's update.sh: running, done or failed
CHANNEL = DATA / "channel.json"       # written by the host's channel.sh, after it checked the signature
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
        # Whether the host holds release keys, written into the compose environment by install.sh.
        # It decides the default below and nothing else; the checking itself is the host's, and this
        # being wrong would make the hub shy rather than reckless.
        self.verified = (os.environ.get("HUB_VERIFIED") or "") == "1"
        self.latest, self.checked, self.error = None, None, None
        self.asked_at = 0.0               # when this hub last installed something without being asked
        # A hub that has only ever run this version has nothing to announce: somebody who has just
        # plugged one in is being set up, not caught up. So the first version a hub sees is marked
        # read, and the card is for the ones after it.
        if self.hub.settings.get("notes_seen") is None: self.hub.settings.set(notes_seen=self.version)

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

    @property
    def auto(self) -> bool:
        """Whether this hub installs updates without being asked.

        On by default, because the alternative is what actually happens otherwise: nobody walks to
        the wall, nobody types the code, and the house sits three releases behind for a year running
        the bug that was fixed in March. Every appliance a household already owns does this.

        On by default *only where the hub can check what it is installing*, though. Updating by
        itself from a source nothing verifies is the supply-chain problem with the person taken out
        of it, so a hub with no release keys waits to be asked. A household's own answer, once given,
        outranks both.
        """
        v = self.hub.settings.get("auto_update")
        return self.verified if v is None else bool(v)

    def set_auto(self, on: bool) -> dict:
        self.hub.settings.set(auto_update=bool(on))
        self.hub.log.add("home", "update", None, f"automatic {'on' if on else 'off'}", source="user")
        self._tell(); return self.summary()

    def minute_of_the_night(self) -> int:
        """Which minute of the window this hub uses: the same every night, different per house.

        Ten thousand hubs waking at two o'clock exactly would arrive at the maker's releases together
        and, worse, would all take a bad release in the same minute. The hub's own id spreads them,
        and being stable rather than random means a household that notices the hub restarts at twenty
        past two is not wrong tomorrow.
        """
        h = hashlib.sha256(self.hub.settings.hub_id().encode()).hexdigest()
        return int(h[:8], 16) % ((WINDOW[1] - WINDOW[0]) * 60)

    def busy(self, now: float) -> bool:
        """Somebody is up. The window is the small hours, but a house is not a clock."""
        return now - (self.hub.log.last_user() or 0) < QUIET

    def due(self, now: float | None = None) -> bool:
        """Should this hub install, by itself, right now?"""
        now = now or time.time()
        if not (self.auto and self.offer): return False
        # A staged release slows the hub down and never a person: somebody standing at the wall with
        # Install in front of them has decided, and being in the second nine tenths is not a reason
        # to refuse them. This is the only place it applies.
        if not self.reached_us(): return False
        if now - self.asked_at < RETRY: return False                     # it has had its go tonight
        if REQUEST.exists() or (self.state() or {}).get("state") == "running": return False
        here = datetime.fromtimestamp(now, self.hub.tz)
        minute = (here.hour - WINDOW[0]) * 60 + here.minute
        # Anywhere from this hub's minute to the end of the window: one that was busy at its own
        # minute tries again later the same night rather than waiting a whole day.
        if not self.minute_of_the_night() <= minute < (WINDOW[1] - WINDOW[0]) * 60: return False
        return not self.busy(now)

    def notes(self) -> dict | None:
        """What changed in the version this hub is running, or None if it carries no notes."""
        return notes.read(self.version)

    @property
    def whats_new(self) -> dict | None:
        """The notes to put on the wall, or None. Cleared by reading them, and never shown twice.

        This is where piece 4 pays for pieces 1 to 3: with the hub updating itself overnight, nobody
        is ever standing in front of a release note before it installs, so the notes belong here --
        the morning after, once, on the screen somebody walks past anyway.
        """
        if self.hub.settings.get("notes_seen") == self.version: return None
        n = self.notes()
        return n if n and n["what"] else None

    def read_notes(self) -> dict:
        """Somebody has seen what is new. It does not come back."""
        self.hub.settings.set(notes_seen=self.version)
        self._tell(); return self.summary()

    def state(self):
        try: return json.loads(STATE.read_text())
        except (OSError, ValueError): return None

    def channel_says(self) -> dict:
        """What the maker is saying about releases right now, as against what a release is.

        The host fetched this and checked it against the same keys as a release (host/channel.sh);
        the brain could not have, having no ed25519 anywhere in its dependencies. No file is the
        answer "nothing is held and everything is fully out", which is the direction this is allowed
        to fail in: the alternative hands anybody who can block a network the power to freeze every
        hub on the version it is on.
        """
        try: return json.loads(CHANNEL.read_text())
        except (OSError, ValueError): return {}

    def held(self, version: str | None = None) -> bool:
        """Has the maker pulled this release since signing it? Nothing installs it, asked or not."""
        v = self._norm(version or (self.latest or {}).get("version") or "")
        return bool(v) and v in {self._norm(x) for x in (self.channel_says().get("hold") or [])}

    def reached_us(self, version: str | None = None) -> bool:
        """Has this release been let out as far as this house yet?

        A release goes to a tenth of hubs first, then the rest. The hub's own id decides which, and
        the version is mixed into the hash on purpose: hashing the id alone would make the same
        unlucky houses the first to take every release forever, which is a thing to do to a test
        fleet and not to somebody's home.
        """
        v = (version or (self.latest or {}).get("version") or "")
        share = (self.channel_says().get("rollout") or {})
        want = next((x for k, x in share.items() if self._norm(k) == self._norm(v)), 1.0)
        try: want = max(0.0, min(1.0, float(want)))
        except (TypeError, ValueError): return True                  # a number nobody can read is not a hold
        if want >= 1.0: return True
        h = hashlib.sha256(f"{self.hub.settings.hub_id()}|{self._norm(v)}".encode()).hexdigest()
        return (int(h[:8], 16) % 1000) < want * 1000

    def rejected(self) -> str:
        """A version this hub will not walk into again on its own. host/update.sh names it.

        Two ways a version gets here, and they are not the same thing. It was installed, would not
        come back, and was put back -- a rollback followed six hours later by the same install is a
        loop, not a safety net. Or the host would not vouch for it at all: no signed record of what
        it is, or one this hub's key does not recognize (docs/updates.md, piece 2), in which case
        nothing moved and nothing about the house is different.
        """
        st = self.state() or {}
        return self._norm(st.get("bad") or "") if st.get("state") in ("reverted", "failed", "refused") else ""

    @property
    def offer(self):
        """Whether the hub should raise this update by itself, as against whether one exists.

        `available` stays the honest answer about the world -- there *is* a newer build -- and this is
        the answer about what the house should do with that. They come apart in exactly one place: a
        version that was tried and put back. Home stops nudging for it; the button under *This hub*
        keeps working, because a person choosing to try again is a different act from a hub deciding
        to, and trying it twice is often what fixes it.
        """
        if not self.available: return self.available          # False and None pass through unchanged
        if self.held(): return False                          # the maker has pulled it since signing it
        return self._norm((self.latest or {}).get("version") or "") != self.rejected()

    def summary(self) -> dict:
        return {"version": self.version, "commit": self.commit[:12], "channel": self.channel, "latest": self.latest,
                "available": self.available, "offer": self.offer, "rejected": self.rejected() or None,
                "auto": self.auto, "verified": self.verified, "whats_new": self.whats_new,
                "held": self.held(), "reached_us": self.reached_us(),
                "checked": self.checked, "requested": REQUEST.exists(),
                "state": self.state(), "error": self.error}

    def fetch(self) -> dict:
        if self.channel == "main":
            d = _get(MAIN_API)
            return {"version": f"main-{d['sha'][:7]}", "sha": d["sha"], "when": d["commit"]["committer"]["date"],
                    "title": d["commit"]["message"].splitlines()[0][:120]}
        d = _get(RELEASE_API)
        # A release with no title of its own is named by its tag; the panel puts this in a sentence.
        # `what` is the same lines that ship inside the next image, taken here from the release body
        # so a household can read what is waiting rather than a commit subject. It describes and
        # never decides -- nothing here is signed, and what actually installs is the host's business.
        return {"version": d["tag_name"], "sha": d.get("target_commitish") or "",
                "when": d.get("published_at") or "", "title": (d.get("name") or d["tag_name"])[:120],
                "what": [line[:160] for line in notes.parse(d.get("body") or "")["what"][:4]]}

    async def check(self) -> dict:
        was = self.offer
        try: self.latest, self.error = await asyncio.to_thread(self.fetch), None
        except Exception as e:
            self.error = str(e); log.info("update check: %s", e)
        self.checked = time.time()
        if self.offer != was: self._tell()
        return self.summary()

    async def check_now(self) -> dict:
        """Somebody opened This hub. Ask again now, unless the hub asked a few minutes ago.

        The page is the affordance: opening it is the check, the "checked" time under the version
        is the answer, and the Install button appears on its own if there is something. There is
        deliberately no "Check for updates" button to explain -- a hub that needs one is a hub
        confessing it might be lying about "Up to date". The throttle is for GitHub's rate limit
        and for a wall that is tapped in and out of settings ten times in a minute; a failed check
        counts as a look too, so a house with no internet is not asked to wait twenty seconds on
        every open.
        """
        if self.checked and time.time() - self.checked < RECHECK: return self.summary()
        return await self.check()

    async def run(self):
        await asyncio.sleep(90)            # let the house come up first
        while True:
            try:
                if not self.checked or time.time() - self.checked > EVERY: await self.check()
                if self.due():
                    log.info("installing %s without being asked: the house has been quiet and it is this hub's minute",
                             (self.latest or {}).get("version"))
                    self.request(source="hub")
            except Exception: log.exception("update tick")
            await asyncio.sleep(TICK)

    def request(self, source: str = "user") -> dict:
        """A tap on the panel, or the hub's own small hours. Writes the file the host watches.

        `source` is what tells the two apart in the log and under Recent, and it is worth the word:
        a household that finds the hub on a new version in the morning should be able to see that
        nobody in the house did it.
        """
        want = (self.latest or {}).get("version") or ""
        # The host refuses a held release too, and its copy of the channel is the fresher one. This
        # is here so the panel gets a sentence instead of a restart that ends in "not installed".
        if self.held(want): raise ValueError("That update has been paused by the people who make the hub.")
        REQUEST.parent.mkdir(parents=True, exist_ok=True)
        REQUEST.write_text(json.dumps({"at": time.time(), "channel": self.channel, "from": self.version, "to": want,
                                       "from_commit": self.commit, "to_commit": (self.latest or {}).get("sha") or ""}))
        if source == "hub": self.asked_at = time.time()
        self.hub.log.add("home", "update", self.version, want, source=source)
        self._tell(); return self.summary()

    def _tell(self):
        self.hub._broadcast(json.dumps({"type": "status", "status": self.hub.status()}))
