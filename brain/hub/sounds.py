"""Sounds on a speaker: white noise, rain, whatever is in the sounds folder, on any speaker the driver layer can
hand a URL to (Google and other Cast speakers first of all). The hub hosts the file and asks the speaker to fetch
it from the hub's LAN address, so it works with the internet down. A speaker plays a file once; the brain sees the
speaker go idle and asks again, which is the loop. A sleep timer stops it, like the thermostat's fan timer.

Files: the sounds folder in the data volume (brain-data/sounds on a hub). Drop in rain.mp3 and "Rain" appears on
every speaker's tile. White, pink and brown noise are made here, once, so they need no file at all.

Any file is prepared once before it plays, when ffmpeg is on the hub (it is in the image): its last seconds are
crossfaded into its first so the join is seamless, and the loop is repeated out to ten minutes so the speaker's
own restart gap comes round rarely. The prepared copy lives in sounds/prepared; the original is never touched.
Without ffmpeg the original plays as it is.
"""
import array, asyncio, json, logging, math, os, random, re, shutil, socket, subprocess, tempfile, time, wave
from pathlib import Path
from urllib.parse import quote
from .settings import DATA, ROOT

log = logging.getLogger("hub.sounds")
DIR = DATA / "sounds"
LIBRARY = Path(os.environ.get("HUB_SOUNDS_LIBRARY") or ROOT.parent / "sounds")   # the repo's recordings; copied in when missing
GENERATED = {"white": "White noise", "pink": "Pink noise", "brown": "Brown noise"}
RATE, SECONDS = 22050, 180                       # three minutes per generated file: the seam comes round rarely
EXT = (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac")
MIME = {".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg", ".m4a": "audio/mp4", ".flac": "audio/flac", ".aac": "audio/aac"}
REPLAY_GAP = 3.0                                 # seconds; a speaker that keeps failing is not hammered
FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
PREPARED = "prepared"                            # subfolder of the sounds folder
CROSSFADE, TARGET = 3.0, 600                     # seconds: the seam, and how long a prepared file runs before it restarts


def duration(path: Path) -> float:
    out = subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def plan(d: float, crossfade: float = CROSSFADE, target: float = TARGET) -> dict:
    """How to loop a file of d seconds: the seam length (shorter for short files) and how many repeats reach the target."""
    c = round(min(crossfade, d / 4), 3)
    loops = max(0, math.ceil(target / d) - 1)
    fc = (f"[0:a]atrim=start={c},asetpts=N/SR/TB[main];[0:a]atrim=0:{c},asetpts=N/SR/TB[head];"
          f"[0:a]atrim=start={round(d - c, 3)},asetpts=N/SR/TB[tail];[tail][head]acrossfade=d={c}:c1=tri:c2=tri[x];"
          f"[main][x]concat=n=2:v=0:a=1[out]")
    return {"crossfade": c, "loops": loops, "filter": fc}


def prepare(src: Path, dst: Path, crossfade: float = CROSSFADE, target: float = TARGET):
    """Write dst: src with its tail crossfaded into its head, repeated to about target seconds, as a small MP3."""
    d = duration(src)
    if d <= 0.5: raise ValueError("too short to loop")
    p = plan(d, crossfade, target)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        loop = Path(tmp) / "loop.wav"
        subprocess.run([FFMPEG, "-y", "-v", "error", "-i", str(src), "-filter_complex", p["filter"], "-map", "[out]", str(loop)], check=True, capture_output=True, text=True)
        out = dst.with_name(dst.name + ".tmp.mp3")
        subprocess.run([FFMPEG, "-y", "-v", "error", "-stream_loop", str(p["loops"]), "-i", str(loop), "-t", str(target),
                        "-codec:a", "libmp3lame", "-b:a", "96k", str(out)], check=True, capture_output=True, text=True)
        out.replace(dst)
    dst.with_suffix(".json").write_text(json.dumps({"src_mtime": src.stat().st_mtime, "crossfade": crossfade, "target": target, "source_seconds": d}))


def pretty(stem: str) -> str:
    return re.sub(r"[-_]+", " ", stem).strip().capitalize()


def synthesize(kind: str, path: Path, seconds: int = SECONDS):
    """Write a mono 16-bit WAV of noise. Pure Python on purpose: no numpy in the image; it runs once, in a thread."""
    n, out, g = RATE * seconds, array.array("h"), random.gauss
    clip = lambda x: int(max(-1.0, min(1.0, x)) * 32767)
    if kind == "white":
        for _ in range(n): out.append(clip(g(0, 0.25)))
    elif kind == "brown":
        v = 0.0
        for _ in range(n):
            v = 0.998 * v + g(0, 0.02)             # leaky integration of white noise
            out.append(clip(v * 6))
    else:                                          # pink, Paul Kellet's economy filter
        b0 = b1 = b2 = b3 = b4 = b5 = b6 = 0.0
        for _ in range(n):
            w = g(0, 0.25)
            b0 = 0.99886 * b0 + w * 0.0555179; b1 = 0.99332 * b1 + w * 0.0750759; b2 = 0.96900 * b2 + w * 0.1538520
            b3 = 0.86650 * b3 + w * 0.3104856; b4 = 0.55000 * b4 + w * 0.5329522; b5 = -0.7616 * b5 - w * 0.0168980
            out.append(clip((b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11)); b6 = w * 0.115926
    fade = RATE // 20                              # a 50 ms fade at both ends: the loop seam is a soft dip, not a click
    for i in range(min(fade, len(out) // 2)):
        k = i / fade; out[i] = int(out[i] * k); out[-1 - i] = int(out[-1 - i] * k)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(out.tobytes())
    tmp.replace(path)


class Sounds:
    def __init__(self, hub):
        self.hub = hub
        self.sessions: dict[str, dict] = {}       # device id -> {"sound", "url", "title", "until", "started"}
        self._timers: dict[str, asyncio.Task] = {}
        self._replayed: dict[str, float] = {}

        self._prep_task = None

    # ---- what there is ----
    def catalog(self) -> list:
        out = [{"id": k, "name": v} for k, v in GENERATED.items()]
        if DIR.exists():
            for p in sorted(DIR.iterdir()):
                if p.is_file() and p.suffix.lower() in EXT and p.stem not in GENERATED:
                    out.append({"id": p.stem, "name": pretty(p.stem)})
        for s in out:
            src = self.path(s["id"])
            s["ready"] = bool(src and src.exists() and (not FFMPEG or self.fresh(src)))
            s["prepared"] = bool(src and self.fresh(src))
        return out

    # ---- the prepared copy: seamless loop, ten minutes long ----
    def prepared_path(self, src: Path) -> Path:
        return DIR / PREPARED / f"{src.stem}.mp3"

    def fresh(self, src: Path) -> bool:
        dst = self.prepared_path(src)
        try: meta = json.loads(dst.with_suffix(".json").read_text())
        except (OSError, ValueError): return False
        return dst.exists() and meta.get("src_mtime") == src.stat().st_mtime and meta.get("crossfade") == CROSSFADE and meta.get("target") == TARGET

    def play_path(self, sid: str):
        """What the speaker is given: the prepared loop when it is current, else the file as it is."""
        src = self.path(sid)
        if not src: return None
        return self.prepared_path(src) if FFMPEG and self.fresh(src) else src

    async def prepare_all(self):
        """Prepare every sound that has no current prepared copy, one at a time, off the loop."""
        if not FFMPEG: return
        for s in self.catalog():
            src = self.path(s["id"])
            if not src or not src.exists() or self.fresh(src): continue
            try: await asyncio.to_thread(prepare, src, self.prepared_path(src)); log.info("prepared %s", src.name)
            except Exception as e: log.warning("could not prepare %s: %s", src.name, e)

    def prepare_soon(self):
        """Kick off preparing anything new, unless a pass is already running."""
        if not FFMPEG: return
        if self._prep_task is None or self._prep_task.done():
            self._prep_task = asyncio.get_running_loop().create_task(self.prepare_all())

    def path(self, sid: str):
        if sid in GENERATED: return DIR / f"{sid}.wav"
        if not DIR.exists() or "/" in sid or sid.startswith("."): return None
        return next((p for p in DIR.iterdir() if p.is_file() and p.stem == sid and p.suffix.lower() in EXT), None)

    def name(self, sid: str) -> str:
        return GENERATED.get(sid) or pretty(sid)

    @staticmethod
    def seed() -> list:
        """Copy the repo's recordings into the sounds folder where they are missing. A hub's own file of the same name wins."""
        DIR.mkdir(parents=True, exist_ok=True)
        added = []
        if LIBRARY.exists() and LIBRARY.resolve() != DIR.resolve():
            for p in sorted(LIBRARY.iterdir()):
                if p.is_file() and p.suffix.lower() in EXT and not (DIR / p.name).exists():
                    shutil.copy2(p, DIR / p.name); added.append(p.name)
        if added: log.info("sounds added from the library: %s", ", ".join(added))
        return added

    async def ensure(self):
        """Seed from the library and make the generated noises once, off the loop, then prepare everything that needs it."""
        self.seed()
        for kind in GENERATED:
            p = DIR / f"{kind}.wav"
            if not p.exists():
                try: await asyncio.to_thread(synthesize, kind, p); log.info("made %s", p.name)
                except Exception as e: log.warning("could not make %s: %s", kind, e)
        await self.prepare_all()

    # ---- where the speaker fetches from ----
    def base_url(self) -> str:
        ip = self.hub.env.get("HUB_IP") or self._lan_ip()
        return f"http://{ip}:{os.environ.get('HUB_PORT', '8300')}"

    @staticmethod
    def _lan_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1))   # no packet is sent
            ip = s.getsockname()[0]; s.close(); return ip
        except OSError: return "127.0.0.1"

    def url(self, sid: str) -> str:
        p = self.play_path(sid)
        rel = p.relative_to(DIR).as_posix()
        return f"{self.base_url()}/sounds/{quote(rel)}"

    # ---- doing it ----
    async def play(self, dev, sid: str, minutes=None, volume=None, source="user"):
        if dev.capability != "media": raise ValueError("Only a speaker can play a sound.")
        p = self.path(sid)
        if not p: raise ValueError(f"There is no sound called {sid!r}.")
        if not p.exists() and sid in GENERATED: await asyncio.to_thread(synthesize, sid, p)
        if FFMPEG and not self.fresh(p):
            try: await asyncio.to_thread(prepare, p, self.prepared_path(p))
            except Exception as e: log.warning("playing %s unprepared: %s", p.name, e)
        minutes = int(minutes) if minutes else None
        self._cancel(dev.id)
        title = self.name(sid)
        if volume is not None:
            await self.hub.ha.call("media_player", "volume_set", dev.id, volume_level=max(0.0, min(1.0, float(volume))))
        url = self.url(sid)
        await self._cast(dev, url, title, self.play_path(sid).suffix.lower())
        until = time.time() + minutes * 60 if minutes else None
        self.sessions[dev.id] = {"sound": sid, "url": url, "title": title, "until": until, "started": time.time()}
        if minutes: self._timers[dev.id] = asyncio.create_task(self._stop_later(dev.id, minutes * 60))
        self._mark(dev)
        self.hub.log.add("action", dev.id, None, f"sound {sid}" + (f" {minutes} min" if minutes else ""), source=source, detail={"sound": sid, "minutes": minutes, "url": url})
        return self.describe(dev.id)

    async def _cast(self, dev, url, title, suffix):
        await self.hub.ha.call("media_player", "play_media", dev.id, media_content_id=url, media_content_type=MIME.get(suffix, "music"),
                               extra={"title": title, "metadata": {"metadataType": 3, "title": title, "artist": "home-hub"}})

    async def stop(self, dev, source="user"):
        self._cancel(dev.id)
        had = self.sessions.pop(dev.id, None)
        self.hub.home.extras.pop(dev.id, None)
        if had:
            try: await self.hub.ha.call("media_player", "media_stop", dev.id)
            except Exception as e: log.warning("could not stop %s: %s", dev.id, e)
            self.hub.log.add("action", dev.id, None, "sound off", source=source)
        self._mark(dev)

    def _cancel(self, did):
        if t := self._timers.pop(did, None): t.cancel()

    async def _stop_later(self, did, seconds):
        await asyncio.sleep(seconds)
        self._timers.pop(did, None)
        dev = self.hub.home.devices.get(did)
        if dev: await self.stop(dev, source="timer")

    def _mark(self, dev):
        s = self.sessions.get(dev.id)
        extra = {"sound": s["sound"], "sound_until": s["until"], "sound_name": s["title"]} if s else {}
        if s: self.hub.home.extras[dev.id] = extra
        dev.attrs = {**{k: v for k, v in dev.attrs.items() if k not in ("sound", "sound_until", "sound_name")}, **extra}
        self.hub._broadcast(__import__("json").dumps({"type": "device", "device": dev.__dict__}))

    def describe(self, did) -> dict | None:
        s = self.sessions.get(did)
        return {"sound": s["sound"], "name": s["title"], "until": s["until"]} if s else None

    # ---- the loop: the speaker finished, ask again ----
    def on_state(self, dev, old):
        s = self.sessions.get(dev.id)
        if not s: return
        now = time.time()
        if s["until"] and now > s["until"]: return                      # the timer is about to stop it
        if dev.state == "playing" and dev.attrs.get("media_title") not in (None, "", s["title"]):
            self.sessions.pop(dev.id, None); self._cancel(dev.id); self.hub.home.extras.pop(dev.id, None); self._mark(dev)
            return                                                     # someone put something else on; theirs now
        if dev.state == "paused":
            self.sessions.pop(dev.id, None); self._cancel(dev.id); self.hub.home.extras.pop(dev.id, None); self._mark(dev)
            return                                                     # a hand paused it: that is a stop
        if dev.state in ("idle", "off") and old == "playing" and now - self._replayed.get(dev.id, 0) > REPLAY_GAP:
            self._replayed[dev.id] = now
            asyncio.get_running_loop().create_task(self._replay(dev, s))

    async def _replay(self, dev, s):
        try: await self._cast(dev, s["url"], s["title"], Path(s["url"]).suffix.lower())
        except Exception as e:
            log.warning("could not keep %s playing: %s", dev.id, e)
            self.sessions.pop(dev.id, None); self._cancel(dev.id); self.hub.home.extras.pop(dev.id, None); self._mark(dev)
