# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The house, answering out loud.

docs/voice.md settled on 14 September 2026 where a spoken answer comes out: the brain synthesizes the
sentence and the PANEL plays it, as audio in the page, from a URL on the hub's own LAN address. That is
the arrangement `sounds.py` already has with a Cast speaker -- the hub hosts the audio, the thing with
the loudspeaker fetches it from the hub -- so *works with the internet down* is inherited rather than
argued for again. Not natively in the kiosk, and not on the room's speaker: an answer has to come from
where the hand was.

This module is the whole of that half, and it is deliberately small:

  * one Wyoming client, speaking to Piper in its own container (the radios' pattern: a Compose profile);
  * the rules about WHEN the house speaks, which are docs/voice.md's and not this file's to invent;
  * a clip store that lives in memory and dies in a minute.

**The trap this file exists to avoid.** The clip must never land in the sounds folder. That folder is a
person's own library -- `sounds.py`'s first paragraph is *drop in rain.mp3 and "Rain" appears on every
speaker's tile* -- and minted speech there would turn up as something to play in a bedroom at night. So
nothing here touches `DATA / "sounds"`, nothing here reaches `catalog()`, and a clip is bytes in a dict
with a timer on it. The most reliable way not to leave a file behind is not to write one.

What is NOT here yet, and is deliberate: announcing. Everything in this file answers a person who spoke
first. A house that volunteers a sentence -- *the front door has been unlocked for three hours* -- is
the alert class reaching a new channel, and `docs/messages.md` has to exist before that can route.
"""
import asyncio, io, json, logging, os, secrets, time, wave

log = logging.getLogger("hub.voice")

# Where Piper listens. The container is `wyoming-piper` on the hub itself, so the default is loopback;
# the brain runs with network_mode: host, which is what makes that the same machine.
HOST = os.environ.get("VOICE_TTS_HOST") or "127.0.0.1"
PORT = int(os.environ.get("VOICE_TTS_PORT") or 10200)
# Which engine, if any. Empty is off, and off is what every house is today: no container has ever been
# started, so the panel gets no clip and answers on the glass exactly as it does now. `install.sh` will
# write this beside the radio profiles when shape 2 lands.
ENGINE = (os.environ.get("VOICE_TTS") or "").strip().lower()
# The voice itself. docs/voice.md's tier table picks a quality per host class; WHICH voice a household
# hears is still open, so this is a name passed straight through and not a choice made here.
VOICE = (os.environ.get("VOICE_TTS_VOICE") or "").strip()

# A sentence is a second or three. Past this the house has stopped being an answer and become a wait,
# and the panel has already shown the words anyway -- so give up rather than hold the turn open.
TIMEOUT = float(os.environ.get("VOICE_TTS_TIMEOUT") or 6.0)
# How long a minted clip is worth keeping, and how many. Both are small on purpose: a clip is fetched
# within a second of being made, by the panel that just asked for it. The cap is the only thing
# standing between a chatty afternoon and a Pi's memory, so it is a cap and not a hope.
CLIP_TTL = 60.0
CLIP_MAX = 8
# Longer than this is not an answer to read out. Nothing in the grammar comes close; the guard is for
# the day something else calls speak().
MAX_CHARS = 400


class VoiceError(Exception):
    """The engine could not say it. Never raised at a person: the panel has the words on the glass."""


# ---------- when the house speaks at all ----------
def should_speak(reply: dict, room, home_intent: str | None, spoken: bool) -> bool:
    """docs/voice.md, *When the house speaks, and when it stays quiet*.

    **The house speaks when it was spoken to.** The route decides, not the kind: a sentence that
    arrived as speech is answered as speech, and a sentence that was typed is answered on the glass in
    silence, exactly as it is today. Nobody types at a wall and wants it to talk back.

    **And never in a room that is asleep.** `RoomState.asleep` is real state, set by "good night"
    through this very grammar, so the house already knows -- one condition, no clock, no quiet hours
    and no setting. The sentence that puts the house to bed is the last thing it says aloud, which
    falls out of this for free: the reply is built before the intent lands.

    (The one thing this rule does not cover is a sentence the house volunteers rather than answers.
    That is announcing, it is a household's switch rather than a rule, and it is not built yet.)
    """
    if not spoken: return False
    if not (reply.get("spoken") or "").strip(): return False
    # asleep is per room AND house-wide, and either one is enough. "Good night" sets both, so the
    # second test is for a single room put to bed on its own while the rest of the house is up.
    if home_intent == "asleep": return False
    if room is not None and getattr(room, "intent", None) == "asleep": return False
    return True


# ---------- the Wyoming wire ----------
async def _write_event(writer, kind: str, data: dict | None = None):
    body = json.dumps(data or {}, ensure_ascii=False).encode()
    head = json.dumps({"type": kind, "data_length": len(body)}, ensure_ascii=False).encode()
    writer.write(head + b"\n" + body)
    await writer.drain()


async def _read_event(reader):
    """One event, or None at the end of the stream. Wyoming writes a JSON header line, then the data
    it declared, then the payload it declared; older peers put the data inline in the header instead,
    so both are read."""
    line = await reader.readline()
    if not line: return None
    head = json.loads(line)
    n = head.get("data_length")
    data = json.loads(await reader.readexactly(n)) if n else (head.get("data") or {})
    m = head.get("payload_length")
    payload = await reader.readexactly(m) if m else None
    return head.get("type"), data, payload


def _wav(pcm: bytes, rate: int, width: int, channels: int) -> bytes:
    """Piper hands back raw PCM. A browser wants a container around it, and WAV is the one that costs
    nothing to write and nothing to decode -- an answer is seconds long, so the size never matters."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def synthesize(text: str, host: str | None = None, port: int | None = None, voice: str | None = None) -> bytes:
    """One sentence to Piper, one WAV back.

    The three settings are read HERE and not bound as defaults on this line: a default argument is
    evaluated once, when the module is imported, which would make the env the process started with the
    only env it could ever have -- and would quietly make a test that points this at its own Piper talk
    to port 10200 instead, passing for the wrong reason."""
    host, port = host or HOST, port or PORT
    if voice is None: voice = VOICE
    try:
        reader, writer = await asyncio.open_connection(host, port)
    except OSError as e:
        raise VoiceError(f"no voice at {host}:{port}: {e}") from e
    try:
        data: dict = {"text": text}
        if voice: data["voice"] = {"name": voice}
        await _write_event(writer, "synthesize", data)
        rate, width, channels, chunks = 22050, 2, 1, []
        while True:
            ev = await _read_event(reader)
            if ev is None: raise VoiceError("the voice closed the connection mid-sentence")
            kind, d, payload = ev
            if kind in ("audio-start", "audio-chunk"):
                rate = int(d.get("rate") or rate)
                width = int(d.get("width") or width)
                channels = int(d.get("channels") or channels)
                if kind == "audio-chunk" and payload: chunks.append(payload)
            elif kind == "audio-stop":
                break
            elif kind == "error":
                raise VoiceError(str(d.get("text") or "the voice refused the sentence"))
    except OSError as e:
        # The engine went away mid-sentence: still starting up (Piper listens before its voice has
        # finished downloading, and resets until it is Ready), restarting, or out of memory. One
        # failure type out of this function, so a caller has one thing to catch and not a list.
        raise VoiceError(f"the voice at {host}:{port} dropped the connection: {e}") from e
    finally:
        writer.close()
        # Closing a connection we have finished with must never be the thing that fails the call, and
        # `wait_closed()` re-raises a reset peer as readily as the read above does. Anything worth
        # reporting has been reported by here, so this is the one place a bare catch is right.
        try: await writer.wait_closed()
        except Exception: pass
    if not chunks: raise VoiceError("the voice returned no audio")
    return _wav(b"".join(chunks), rate, width, channels)


class Voice:
    """The hub's speaking half. One instance, held by the Hub, holding the clips it has minted."""

    def __init__(self, hub):
        self.hub = hub
        self._clips: dict[str, tuple[float, bytes]] = {}

    @property
    def engine(self) -> str:
        return ENGINE

    @property
    def enabled(self) -> bool:
        """Whether anything on this hub can speak. False in every house today: no container has been
        started, so this half is inert and the panel answers on the glass, which is what it does now."""
        return bool(ENGINE)

    def status(self) -> dict:
        return {"enabled": self.enabled, "engine": ENGINE or None, "voice": VOICE or None,
                "where": f"{HOST}:{PORT}" if self.enabled else None}

    # ---- the clips ----
    def _sweep(self, now: float):
        for tok in [t for t, (at, _) in self._clips.items() if now - at > CLIP_TTL]:
            self._clips.pop(tok, None)

    def _keep(self, wav: bytes) -> str:
        now = time.time()
        self._sweep(now)
        while len(self._clips) >= CLIP_MAX:
            self._clips.pop(min(self._clips, key=lambda t: self._clips[t][0]), None)
        tok = secrets.token_urlsafe(16)
        self._clips[tok] = (now, wav)
        return tok

    def take(self, token: str) -> bytes | None:
        """The bytes behind a token, while it is still worth having. Left in place rather than taken:
        a browser that fetches an `Audio` src twice -- a range request, a retry -- should get the
        answer both times, and the minute on the clock is what actually ends it."""
        self._sweep(time.time())
        got = self._clips.get(token)
        return got[1] if got else None

    async def speak(self, text: str) -> str | None:
        """Mint a clip for one sentence and answer its token, or None where nothing can speak."""
        line = " ".join((text or "").split())[:MAX_CHARS]
        if not line or not self.enabled: return None
        try:
            wav = await asyncio.wait_for(synthesize(line), TIMEOUT)
        except (VoiceError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as e:
            # Never raised at the person: they can read the answer, and a house that fails a request
            # because its voice is down has turned a loudspeaker into a dependency.
            log.warning("could not say %r: %s", line[:60], e)
            return None
        return self._keep(wav)

    async def answer(self, reply: dict, room, spoken: bool) -> dict | None:
        """The whole of the answering half, for one reply. `{"url", "text"}` or None for silence."""
        if not self.enabled: return None
        if not should_speak(reply, room, getattr(self.hub.home, "intent", None), spoken): return None
        token = await self.speak(reply["spoken"])
        return {"url": f"/say/clip/{token}", "text": reply["spoken"]} if token else None
