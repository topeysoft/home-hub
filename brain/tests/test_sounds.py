"""Run from brain/: .venv/bin/python -m unittest -v"""
import asyncio, tempfile, unittest, unittest.mock, wave
from pathlib import Path
from hub import sounds, rules
from hub.model import Device
from tests.test_rules import FakeHub, use, rule


class FakeHA:
    def __init__(self): self.calls = []
    async def call(self, domain, service, eid, **data): self.calls.append((domain, service, eid, data))


REAL_FFMPEG = sounds.FFMPEG   # the fake rain.mp3 below is junk bytes: most tests run as if ffmpeg were absent


def make():
    hub = FakeHub(); hub.ha, hub.env = FakeHA(), {"HUB_IP": "192.168.1.9"}
    hub.speaker = Device("media_player.nadines_room_speaker", "Nadine's Room speaker", "den", "media", "idle")
    hub.home.rooms["den"].devices.append(hub.speaker); hub.home.devices[hub.speaker.id] = hub.speaker
    hub.sounds = sounds.Sounds(hub)
    return hub


class SoundTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.keep = sounds.DIR
        sounds.DIR = Path(self.dir.name) / "sounds"; sounds.DIR.mkdir()
        (sounds.DIR / "rain.mp3").write_bytes(b"\xff\xfb" * 100); (sounds.DIR / "notes.txt").write_text("not audio")
        self._noff = unittest.mock.patch.object(sounds, "FFMPEG", None); self._noff.start()

    def tearDown(self): self._noff.stop(); sounds.DIR = self.keep; self.dir.cleanup()

    async def settle(self):
        for _ in range(3): await asyncio.sleep(0)

    def test_synthesize_makes_a_real_wav(self):
        p = sounds.DIR / "white.wav"; sounds.synthesize("white", p, seconds=1)
        with wave.open(str(p)) as w: self.assertEqual((w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()), (1, 2, sounds.RATE, sounds.RATE))
        sounds.synthesize("pink", sounds.DIR / "pink.wav", seconds=1); sounds.synthesize("brown", sounds.DIR / "brown.wav", seconds=1)

    def test_catalog_lists_noises_and_files_only(self):
        hub = make()
        self.assertEqual([s["id"] for s in hub.sounds.catalog()], ["white", "pink", "brown", "rain"])
        rain = next(s for s in hub.sounds.catalog() if s["id"] == "rain")
        self.assertEqual((rain["name"], rain["prepared"]), ("Rain", False))
        self.assertFalse(next(s for s in hub.sounds.catalog() if s["id"] == "white")["ready"])
        self.assertIsNone(hub.sounds.path("../etc/passwd")); self.assertIsNone(hub.sounds.path("notes"))

    def test_the_library_seeds_missing_files_and_never_overwrites(self):
        lib = Path(self.dir.name) / "library"; lib.mkdir()
        (lib / "ocean.mp3").write_bytes(b"lib ocean"); (lib / "rain.mp3").write_bytes(b"lib rain"); (lib / "notes.txt").write_text("x")
        with unittest.mock.patch.object(sounds, "LIBRARY", lib):
            self.assertEqual(sounds.Sounds.seed(), ["ocean.mp3"])
            self.assertEqual((sounds.DIR / "ocean.mp3").read_bytes(), b"lib ocean")
            self.assertNotEqual((sounds.DIR / "rain.mp3").read_bytes(), b"lib rain")      # the hub's own rain stays
            self.assertEqual(sounds.Sounds.seed(), [])
        self.assertIn("ocean", [s["id"] for s in make().sounds.catalog()])

    def test_the_loop_plan(self):
        p = sounds.plan(120)
        self.assertEqual((p["crossfade"], p["loops"]), (3.0, 4))
        self.assertIn("acrossfade=d=3.0", p["filter"]); self.assertIn("atrim=start=117.0", p["filter"])
        self.assertEqual(sounds.plan(8)["crossfade"], 2.0)                       # a short file gets a shorter seam
        self.assertEqual(sounds.plan(700)["loops"], 0)                          # already longer than the target

    def test_without_ffmpeg_the_file_plays_as_it_is(self):
        hub = make()
        with unittest.mock.patch.object(sounds, "FFMPEG", None):
            self.assertEqual(hub.sounds.play_path("rain"), sounds.DIR / "rain.mp3")
            self.assertTrue(next(s for s in hub.sounds.catalog() if s["id"] == "rain")["ready"])
            self.assertTrue(hub.sounds.url("rain").endswith("/sounds/rain.mp3"))

    @unittest.skipUnless(REAL_FFMPEG and sounds.FFPROBE, "ffmpeg not installed here")
    def test_prepare_makes_a_seamless_ten_second_loop_from_a_two_second_file(self):
        hub = make()
        src = sounds.DIR / "hum.wav"; sounds.synthesize("brown", src, seconds=2)
        with unittest.mock.patch.object(sounds, "FFMPEG", REAL_FFMPEG), unittest.mock.patch.object(sounds, "TARGET", 10), unittest.mock.patch.object(sounds, "CROSSFADE", 0.5):
            self.assertFalse(hub.sounds.fresh(src))
            sounds.prepare(src, hub.sounds.prepared_path(src), crossfade=0.5, target=10)
            self.assertTrue(hub.sounds.fresh(src))
            dst = hub.sounds.play_path("hum")
            self.assertEqual(dst, sounds.DIR / "prepared" / "hum.mp3")
            self.assertAlmostEqual(sounds.duration(dst), 10, delta=0.3)
            self.assertTrue(hub.sounds.url("hum").endswith("/sounds/prepared/hum.mp3"))
            self.assertTrue(next(s for s in hub.sounds.catalog() if s["id"] == "hum")["prepared"])
            src.touch()                                                          # the recording was replaced: prepare again
            self.assertFalse(hub.sounds.fresh(src))

    async def test_play_casts_the_hub_url_and_marks_the_speaker(self):
        hub = make()
        out = await hub.sounds.play(hub.speaker, "rain", minutes=45, volume=0.3)
        vol, play = hub.ha.calls
        self.assertEqual(vol[:3], ("media_player", "volume_set", hub.speaker.id)); self.assertEqual(vol[3], {"volume_level": 0.3})
        self.assertEqual(play[:3], ("media_player", "play_media", hub.speaker.id))
        self.assertTrue(play[3]["media_content_id"].startswith("http://192.168.1.9:8300/sounds/")); self.assertEqual(play[3]["media_content_type"], "audio/mpeg")
        self.assertEqual((hub.speaker.attrs["sound"], hub.speaker.attrs["sound_name"]), ("rain", "Rain")); self.assertIsNotNone(hub.speaker.attrs["sound_until"])
        self.assertEqual(out["sound"], "rain"); self.assertEqual(hub.log.rows[-1]["new"], "sound rain 45 min")
        with self.assertRaises(ValueError): await hub.sounds.play(hub.speaker, "thunder")
        with self.assertRaises(ValueError): await hub.sounds.play(hub.light, "rain")
        hub.sounds._cancel(hub.speaker.id)

    async def test_it_loops_when_the_speaker_goes_idle_and_lets_go_when_someone_else_plays(self):
        hub = make(); await hub.sounds.play(hub.speaker, "rain")
        hub.speaker.state, hub.speaker.attrs = "playing", {**hub.speaker.attrs, "media_title": "Rain"}
        hub.sounds.on_state(hub.speaker, "idle")
        hub.speaker.state = "idle"; hub.sounds.on_state(hub.speaker, "playing"); await self.settle()
        self.assertEqual([c[1] for c in hub.ha.calls], ["play_media", "play_media"])
        hub.speaker.state, hub.speaker.attrs = "playing", {**hub.speaker.attrs, "media_title": "Some podcast"}
        hub.sounds.on_state(hub.speaker, "idle")
        self.assertNotIn(hub.speaker.id, hub.sounds.sessions); self.assertNotIn("sound", hub.speaker.attrs)

    async def test_pause_ends_it_stop_stops_it_and_the_timer_stops_it(self):
        hub = make(); await hub.sounds.play(hub.speaker, "rain")
        hub.speaker.state = "paused"; hub.sounds.on_state(hub.speaker, "playing")
        self.assertEqual(hub.sounds.sessions, {})
        await hub.sounds.play(hub.speaker, "rain"); await hub.sounds.stop(hub.speaker)
        self.assertEqual(hub.ha.calls[-1][1], "media_stop"); self.assertNotIn(hub.speaker.id, hub.home.extras)
        await hub.sounds.play(hub.speaker, "rain", minutes=30); hub.sounds._cancel(hub.speaker.id)
        await hub.sounds._stop_later(hub.speaker.id, 0)
        self.assertEqual(hub.sounds.sessions, {}); self.assertEqual(hub.log.rows[-1]["source"], "timer")

    async def test_a_rule_can_put_a_sound_on(self):
        hub = make()
        use(hub, rule("sleep-rain", room="den", when={"intent": "asleep", "in": "den"}, then={"device": hub.speaker.id, "action": "sound", "data": {"sound": "rain", "minutes": 60}}))
        from hub.intents import RoomState
        await hub.set_intent(hub.home.rooms["den"], RoomState.asleep, source="user", detail={"rule": None}); await self.settle(); await self.settle()
        self.assertEqual([c[1] for c in hub.ha.calls], ["play_media"]); self.assertEqual(hub.sounds.sessions[hub.speaker.id]["sound"], "rain")
        hub.sounds._cancel(hub.speaker.id)


if __name__ == "__main__":
    unittest.main()
