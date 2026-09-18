# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The house answering out loud.

Four separate things, and they are worth keeping apart: which SENTENCE a reply is worth out loud, WHEN
the house is allowed to say it, the WIRE to Piper, and the route that hands the panel a clip. Only the
third needs anything to exist outside this file, and it gets a Piper of its own rather than a real one.

Run from brain/: .venv/bin/python -m unittest -v
"""
import asyncio, json, socket, struct, time, unittest, wave, io
from unittest import mock

from hub import voice
from hub.commands import NotUnderstood, aloud, spoken_line
from tests.apptest import ApiTest
from tests.test_commands import Hub as CommandHub


class Room:
    def __init__(self, intent="occupied"): self.intent = intent


# ---------- what a reply is worth out loud ----------
class SpokenTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self): self.hub = CommandHub()

    async def say(self, text, room=None, spoken=True):
        return await self.hub.commands.say(text, room, spoken)

    async def test_a_scene_is_a_sentence_rather_than_a_label(self):
        out = await self.say("movie in the den")
        self.assertEqual(out["text"], "Den · Movie")          # the glass keeps its label
        self.assertEqual(out["spoken"], "Den, movie.")             # the air gets a sentence

    async def test_a_split_set_is_counted_rather_than_listed(self):
        """docs/voice.md's own worked example, and the reason this half is not just text-to-speech."""
        out = await self.say("are the kitchen lights on?")
        self.assertEqual(out["text"], "Kitchen ceiling is on. Kitchen counter is off.")
        self.assertEqual(out["spoken"], "One of the two kitchen lights is on.")

    async def test_a_set_that_agrees_with_itself_is_read_as_it_is(self):
        out = await self.say("is the front door locked?")
        self.assertEqual(out["spoken"], out["text"])
        self.assertEqual(out["spoken"], "Front door is locked.")

    async def test_typography_a_voice_cannot_pronounce_becomes_words(self):
        self.assertEqual(aloud("72° and partly cloudy outside."), "72 degrees and partly cloudy outside.")
        self.assertEqual(aloud("Kitchen light to 50%."), "Kitchen light to 50 percent.")
        self.assertEqual(aloud('Try "kitchen lights off".'), "Try kitchen lights off.")
        out = await self.say("what's the temperature in the kitchen?")
        self.assertIn("degrees", out["spoken"])
        self.assertNotIn("°", out["spoken"])

    async def test_the_three_kinds_that_must_not_be_read_get_a_pointer(self):
        """A proposal is a card to look at and an explanation is a paragraph to read -- but silence
        leaves somebody standing there hearing nothing, which is worse than either."""
        self.hub.assistant.configured = True
        made = await self.say("put something nice on in the hall")
        self.assertEqual(made["kind"], "action")
        self.assertEqual(made["spoken"], "There's something to confirm on the screen.")
        why = await self.say("why did the hall light come on?")
        self.assertEqual(why["kind"], "explain")
        self.assertEqual(why["spoken"], "There's an answer on the screen.")
        self.assertNotIn("evening routine", why["spoken"])          # the paragraph itself, never
        self.assertEqual(spoken_line({"kind": "rule", "text": "x"}), "I've written that up; it's waiting under Routines.")

    async def test_not_understood_says_so_and_never_reads_a_list_of_things_to_type(self):
        short = NotUnderstood("There is no lock in the house yet.")
        self.assertEqual(short.spoken, "There is no lock in the house yet.")
        long = NotUnderstood('The house didn\'t catch that. Try "kitchen lights off", "movie in the den" or '
                             '"is the front door locked?". Connect the assistant under Routines to ask in your own words.')
        self.assertEqual(long.spoken, "I didn't catch that.")

    async def test_how_it_arrived_is_kept_with_the_sentence(self):
        """The log is what the grammar grows from, and people do not type the sentences they say."""
        await self.say("kitchen lights off", spoken=True)
        await self.say("kitchen lights off", spoken=False)
        rows = [r for r in self.hub.log.rows if r["kind"] == "said"]
        self.assertEqual([r["detail"]["spoken"] for r in rows], [True, False])


# ---------- when the house is allowed to say it ----------
class WhenTests(unittest.TestCase):
    REPLY = {"kind": "done", "spoken": "Kitchen lights off."}

    def test_the_route_decides_and_not_the_kind(self):
        self.assertTrue(voice.should_speak(self.REPLY, Room(), None, spoken=True))
        # nobody types at a wall and wants it to talk back
        self.assertFalse(voice.should_speak(self.REPLY, Room(), None, spoken=False))

    def test_a_room_that_is_asleep_answers_on_the_glass(self):
        self.assertFalse(voice.should_speak(self.REPLY, Room("asleep"), None, spoken=True))
        self.assertFalse(voice.should_speak(self.REPLY, Room(), "asleep", spoken=True))
        self.assertFalse(voice.should_speak(self.REPLY, None, "asleep", spoken=True))

    def test_nothing_to_say_is_not_said(self):
        self.assertFalse(voice.should_speak({"kind": "done", "spoken": "  "}, Room(), None, spoken=True))
        self.assertFalse(voice.should_speak({"kind": "done"}, Room(), None, spoken=True))


# ---------- the clips, which never touch the disk ----------
class ClipTests(unittest.TestCase):
    def setUp(self): self.v = voice.Voice(hub=None)

    def test_a_clip_comes_back_until_it_is_too_old(self):
        tok = self.v._keep(b"wav")
        self.assertEqual(self.v.take(tok), b"wav")
        self.assertEqual(self.v.take(tok), b"wav")          # a browser may fetch an Audio src twice
        self.v._clips[tok] = (time.time() - voice.CLIP_TTL - 1, b"wav")
        self.assertIsNone(self.v.take(tok))
        self.assertIsNone(self.v.take("never-minted"))

    def test_a_chatty_afternoon_cannot_fill_a_pi(self):
        kept = [self.v._keep(bytes([n])) for n in range(voice.CLIP_MAX + 4)]
        self.assertEqual(len(self.v._clips), voice.CLIP_MAX)
        self.assertIsNone(self.v.take(kept[0]))             # the oldest went first
        self.assertIsNotNone(self.v.take(kept[-1]))


# ---------- the wire to Piper ----------
def _event(kind, data, payload=b"") -> bytes:
    """Wyoming's framing, written out by hand here rather than borrowed from the module under test:
    a test that reuses the writer it is checking the reader against proves only that they agree."""
    body = json.dumps(data).encode()
    head = {"type": kind, "data_length": len(body)}
    if payload: head["payload_length"] = len(payload)
    return json.dumps(head).encode() + b"\n" + body + payload


class WireTests(unittest.IsolatedAsyncioTestCase):
    FRAMES = bytes(range(256)) * 4

    async def piper(self, script=None, rate=22050, width=2, channels=1):
        """A Piper of our own on a loopback port. Answers `self.asked` with whatever it was handed."""
        self.asked = None

        async def handle(reader, writer):
            kind, data, _ = await voice._read_event(reader)
            self.asked = (kind, data)
            audio = {"rate": rate, "width": width, "channels": channels}
            for chunk in (script or [_event("audio-start", audio),
                                     _event("audio-chunk", audio, self.FRAMES),
                                     _event("audio-stop", {})]):
                writer.write(chunk)
            await writer.drain()
            writer.close()

        server = await asyncio.start_server(handle, "127.0.0.1", 0)
        self.addAsyncCleanup(self._shut, server)
        return server.sockets[0].getsockname()[1]

    async def _shut(self, server):
        server.close()
        await server.wait_closed()

    async def test_a_sentence_goes_out_and_a_playable_wav_comes_back(self):
        port = await self.piper()
        wav = await voice.synthesize("Front door is locked.", "127.0.0.1", port, "en_GB-alba-medium")
        self.assertEqual(self.asked[0], "synthesize")
        self.assertEqual(self.asked[1]["text"], "Front door is locked.")
        self.assertEqual(self.asked[1]["voice"], {"name": "en_GB-alba-medium"})
        with wave.open(io.BytesIO(wav)) as w:
            self.assertEqual((w.getframerate(), w.getsampwidth(), w.getnchannels()), (22050, 2, 1))
            self.assertEqual(w.readframes(w.getnframes()), self.FRAMES)

    async def test_a_voice_nobody_chose_is_left_to_piper(self):
        port = await self.piper()
        await voice.synthesize("Hello.", "127.0.0.1", port, "")
        self.assertNotIn("voice", self.asked[1])

    async def test_the_engine_failing_is_never_the_persons_problem(self):
        """Every one of these has to come back as silence rather than as an error: the words are
        already on the glass, and a house that refuses a request because its loudspeaker is down has
        turned a loudspeaker into a dependency."""
        with mock.patch.object(voice, "ENGINE", "piper"):
            v = voice.Voice(hub=None)
            with mock.patch.object(voice, "PORT", 1):                       # nothing listening
                self.assertIsNone(await v.speak("Front door is locked."))
            for script in ([_event("error", {"text": "no such voice"})],    # Piper says no
                           [_event("audio-start", {}), _event("audio-stop", {})],   # no audio at all
                           [b'{"type": "audio-start"']):                    # a half-written line
                port = await self.piper(script=script)
                with mock.patch.object(voice, "PORT", port):
                    self.assertIsNone(await v.speak("Front door is locked."))

    async def test_an_engine_that_is_still_starting_up_is_one_failure_like_any_other(self):
        """Real Piper listens on its port BEFORE its voice has finished downloading, and resets every
        connection until it says Ready -- so this is the first thing a new hub does, not an edge case.
        `synthesize` answers one exception type whatever went wrong, so a caller catches one thing."""
        async def reset(reader, writer):
            writer.get_extra_info("socket").setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            writer.close()
        server = await asyncio.start_server(reset, "127.0.0.1", 0)
        self.addAsyncCleanup(self._shut, server)
        port = server.sockets[0].getsockname()[1]
        with self.assertRaises(voice.VoiceError):
            await voice.synthesize("Front door is locked.", "127.0.0.1", port, "")

    async def test_an_engine_that_hangs_gives_up_rather_than_holding_the_turn(self):
        async def forever(*a, **kw):
            await asyncio.sleep(30)
        with mock.patch.object(voice, "ENGINE", "piper"), mock.patch.object(voice, "TIMEOUT", 0.05), \
             mock.patch.object(voice, "synthesize", forever):
            self.assertIsNone(await voice.Voice(hub=None).speak("Front door is locked."))


# ---------- the route, and the clip the panel plays ----------
class RouteTests(ApiTest):
    def enable(self):
        """A hub with a voice, and a Piper that answers instantly."""
        async def fake(text, *a, **kw): return b"RIFF" + text.encode()
        return mock.patch.object(voice, "ENGINE", "piper"), mock.patch.object(voice, "synthesize", fake)

    def test_a_typed_sentence_is_answered_on_the_glass_in_silence(self):
        engine, synth = self.enable()
        with engine, synth:
            r = self.client.post("/say", json={"text": "kitchen lights off"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("speak", r.json())
        self.assertEqual(r.json()["spoken"], "Kitchen lights off.")   # the sentence is there either way

    def test_a_spoken_sentence_comes_back_with_a_clip_the_panel_can_play(self):
        engine, synth = self.enable()
        with engine, synth:
            r = self.client.post("/say", json={"text": "kitchen lights off", "spoken": True})
            said = r.json()
            self.assertEqual(said["speak"]["text"], "Kitchen lights off.")
            clip = self.client.get(said["speak"]["url"])
        self.assertEqual(clip.status_code, 200)
        self.assertEqual(clip.headers["content-type"], "audio/wav")
        self.assertEqual(clip.content, b"RIFFKitchen lights off.")
        self.assertEqual(clip.headers["cache-control"], "no-store")

    def test_a_clip_is_not_a_sound_in_anybodys_library(self):
        """The one trap docs/voice.md names: minted speech in the sounds folder would turn up as
        something to play in a bedroom."""
        engine, synth = self.enable()
        with engine, synth:
            self.client.post("/say", json={"text": "kitchen lights off", "spoken": True})
        names = [s["id"] for s in self.client.get("/sounds").json()["sounds"]]
        self.assertEqual([n for n in names if "kitchen" in n.lower()], [])
        self.assertEqual(self.client.get("/say/clip/made-up").status_code, 404)

    def test_the_house_says_it_did_not_catch_that(self):
        engine, synth = self.enable()
        with engine, synth:
            r = self.client.post("/say", json={"text": "flumble the widget", "spoken": True})
            self.assertEqual(r.status_code, 422)
            self.assertTrue(r.json()["detail"])
            clip = self.client.get(r.json()["speak"]["url"])
        self.assertEqual(clip.status_code, 200)

    def test_a_house_with_no_voice_is_the_house_we_have_today(self):
        r = self.client.post("/say", json={"text": "kitchen lights off", "spoken": True})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("speak", r.json())


if __name__ == "__main__":
    unittest.main()
