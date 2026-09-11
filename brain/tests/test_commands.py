"""The command grammar: plain words become the same moves a tap makes, with no model in the way.
Run from brain/: .venv/bin/python -m unittest -v"""
import unittest
from hub.commands import Commands, NotUnderstood, find_room
from hub.model import Device, Room
from tests.test_rules import FakeHub


class Catalog:
    def __init__(self): self.sessions = {}
    def catalog(self): return [{"id": "white", "name": "White noise", "ready": True}, {"id": "rain", "name": "Rain", "ready": True}, {"id": "rain-with-thunder", "name": "Rain with thunder", "ready": True}]
    def path(self, sid): return sid if sid in ("white", "rain", "rain-with-thunder") else None


class Assistant:
    def __init__(self, configured=False): self.configured, self.asked = configured, []
    def status(self): return {"configured": self.configured}
    async def draft(self, said): self.asked.append(("draft", said)); return {"kind": "action", "device": "light.hall", "device_name": "Hall light", "action": "on", "data": {}, "name": "Hall light on"}
    async def explain(self, room_id, q): self.asked.append(("explain", room_id, q)); return {"question": q, "answer": "Because the evening routine ran."}


class Hub(FakeHub):
    def __init__(self):
        super().__init__()
        self.home.rooms["kitchen"] = Room("kitchen", "Kitchen"); self.home.rooms["garage"] = Room("garage", "Garage"); self.home.rooms["kids"] = Room("kids", "Kids' room")
        self.home.rooms["unassigned"] = Room("unassigned", "New devices")
        add = lambda r, d: (self.home.rooms[r].devices.append(d), self.home.devices.__setitem__(d.id, d))
        add("kitchen", Device("light.kitchen_ceiling", "Kitchen ceiling", "kitchen", "light", "on", {"brightness": 200}))
        add("kitchen", Device("light.kitchen_counter", "Kitchen counter", "kitchen", "light", "off"))
        add("kitchen", Device("sensor.kitchen_temp", "Kitchen temperature", "kitchen", "sensor.temperature", "71.6"))
        add("kitchen", Device("media_player.kitchen_speaker", "Kitchen speaker", "kitchen", "media", "idle", {"volume_level": 0.3}))
        add("den", Device("media_player.den_tv", "Den TV", "den", "media", "playing"))
        add("den", Device("media_player.den_speaker", "Den speaker", "den", "media", "idle"))
        add("den", Device("climate.den", "Den thermostat", "den", "climate", "heat", {"temperature": 70, "current_temperature": 68, "hvac_modes": ["heat", "cool", "off"]}))
        add("hall", Device("lock.front_door", "Front door", "hall", "lock", "locked"))
        add("garage", Device("cover.garage_door", "Garage door", "garage", "cover", "closed"))
        add("garage", Device("lock.side_door", "Side door", "garage", "lock", "unlocked"))
        add("unassigned", Device("light.new_bulb", "Kasa KL125 Bulb", "unassigned", "light", "off"))
        self.sounds, self.assistant, self.weather = Catalog(), Assistant(), {"temperature": 61.2, "unit": "°F", "condition": "partlycloudy"}
        self.acts, self.intents = [], []
        self.commands = Commands(self)
    async def act(self, dev, action, data=None, source="user", said=None):
        if dev.id == "lock.side_door" and action == "unlock": raise RuntimeError("jammed")
        self.acts.append((dev.id, action, dict(data or {})))
    async def set_intent(self, room, state, source="user", detail=None, depth=0):
        room.intent = state.value; self.intents.append((room.id, state.value, source, detail))
    async def set_home_intent(self, state, source="user", detail=None, depth=0):
        self.home.intent = state.value; self.intents.append(("home", state.value, source, detail))


class Say(unittest.IsolatedAsyncioTestCase):
    def setUp(self): self.hub = Hub()

    async def say(self, text, room=None): return await self.hub.commands.say(text, room)

    async def test_room_and_kind(self):
        out = await self.say("Please turn the kitchen lights off")
        self.assertEqual(out["kind"], "done"); self.assertEqual(out["text"], "Kitchen lights off.")
        self.assertEqual(sorted(a[0] for a in self.hub.acts), ["light.kitchen_ceiling", "light.kitchen_counter"])
        self.assertTrue(all(a[1] == "off" for a in self.hub.acts))
        self.assertEqual(self.hub.log.of("said")[-1]["new"], "Please turn the kitchen lights off")
        self.assertTrue(self.hub.log.of("said")[-1]["detail"]["understood"])

    async def test_a_device_by_name_and_a_short_name_inside_its_room(self):
        await self.say("kitchen counter on")
        self.assertEqual(self.hub.acts, [("light.kitchen_counter", "on", {})])
        self.hub.acts.clear()
        await self.say("turn on the counter in the kitchen")
        self.assertEqual(self.hub.acts, [("light.kitchen_counter", "on", {})])

    async def test_brightness_and_dimming(self):
        await self.say("kitchen lights to 40%")
        self.assertEqual(self.hub.acts[0][2], {"brightness_pct": 40})
        self.hub.acts.clear(); await self.say("dim the kitchen ceiling")
        self.assertEqual(self.hub.acts, [("light.kitchen_ceiling", "on", {"brightness_pct": 30})])

    async def test_scenes_for_a_room_and_the_house(self):
        self.assertEqual((await self.say("movie in the den"))["text"], "Den · Movie")
        self.assertEqual(self.hub.intents[-1][:3], ("den", "movie", "user"))
        self.assertEqual(self.hub.intents[-1][3], {"said": "movie in the den"})
        await self.say("kitchen off"); self.assertEqual(self.hub.intents[-1][:2], ("kitchen", "empty"))
        await self.say("Good night"); self.assertEqual(self.hub.intents[-1][:2], ("home", "asleep"))
        await self.say("everything off"); self.assertEqual(self.hub.intents[-1][:2], ("home", "away"))
        await self.say("we're leaving"); self.assertEqual(self.hub.intents[-1][:2], ("home", "away"))
        with self.assertRaises(NotUnderstood) as c: await self.say("movie")
        self.assertIn("which room", str(c.exception))

    async def test_the_room_the_panel_shows_is_the_default(self):
        await self.say("lights off", room="kitchen")
        self.assertEqual(len(self.hub.acts), 2)
        self.hub.acts.clear(); await self.say("lights off")           # no room anywhere: every light in the house
        self.assertEqual(len(self.hub.acts), 3)

    async def test_room_aliases_and_apostrophes(self):
        r, rest = find_room("turn on the hall light", self.hub.home.rooms)
        self.assertEqual((r.id, rest), ("hall", "turn on light"))
        r, rest = find_room("kids room lights off", self.hub.home.rooms)
        self.assertEqual((r.id, rest), ("kids", "lights off"))
        r, _ = find_room("the nursery", self.hub.home.rooms)
        self.assertEqual(r.id, "kids")

    async def test_locks_and_covers(self):
        await self.say("lock the front door"); self.assertEqual(self.hub.acts[-1], ("lock.front_door", "lock", {}))
        await self.say("open the garage"); self.assertEqual(self.hub.acts[-1], ("cover.garage_door", "open", {}))
        await self.say("close the garage door"); self.assertEqual(self.hub.acts[-1], ("cover.garage_door", "close", {}))
        out = await self.say("lock up")
        self.assertEqual({a[0] for a in self.hub.acts[-2:]}, {"lock.front_door", "lock.side_door"})
        self.assertEqual(out["text"], "All doors locked.")

    async def test_a_device_that_refuses_is_named(self):
        out = await self.say("unlock the doors")
        self.assertIn("Side door didn't respond", out["text"]); self.assertEqual(out["count"], 1)
        with self.assertRaises(NotUnderstood) as c: await self.say("unlock the side door")
        self.assertEqual(str(c.exception), "Side door didn't respond.")

    async def test_media(self):
        await self.say("pause the den tv"); self.assertEqual(self.hub.acts[-1], ("media_player.den_tv", "pause", {}))
        await self.say("turn the tv off in the den"); self.assertEqual(self.hub.acts[-1], ("media_player.den_tv", "off", {}))
        await self.say("kitchen speaker louder"); self.assertEqual(self.hub.acts[-1], ("media_player.kitchen_speaker", "volume", {"volume_level": 0.4}))
        await self.say("volume 50% on the kitchen speaker"); self.assertEqual(self.hub.acts[-1][2], {"volume_level": 0.5})
        await self.say("mute the den speaker"); self.assertEqual(self.hub.acts[-1][2], {"volume_level": 0.0})

    async def test_thermostat(self):
        await self.say("set the den thermostat to 72"); self.assertEqual(self.hub.acts[-1], ("climate.den", "set", {"temperature": 72.0}))
        await self.say("make the den warmer"); self.assertEqual(self.hub.acts[-1][2], {"temperature": 72.0})
        await self.say("den thermostat to cool"); self.assertEqual(self.hub.acts[-1], ("climate.den", "mode", {"hvac_mode": "cool"}))
        await self.say("heating off in the den"); self.assertEqual(self.hub.acts[-1], ("climate.den", "off", {}))

    async def test_sounds(self):
        out = await self.say("play rain in the kitchen for an hour")
        self.assertEqual(self.hub.acts[-1], ("media_player.kitchen_speaker", "sound", {"sound": "rain", "minutes": 60}))
        self.assertEqual(out["text"], "Rain in the Kitchen for 1 hour.")
        await self.say("white noise on the den speaker for 20 minutes")
        self.assertEqual(self.hub.acts[-1], ("media_player.den_speaker", "sound", {"sound": "white", "minutes": 20}))
        await self.say("rain with thunder in the den")
        self.assertEqual(self.hub.acts[-1], ("media_player.den_speaker", "sound", {"sound": "rain-with-thunder"}))   # the speaker, not the TV
        with self.assertRaises(NotUnderstood) as c: await self.say("play some rain")
        self.assertIn("Which speaker", str(c.exception))
        self.hub.sounds.sessions = {"media_player.den_speaker": object()}
        await self.say("stop the noise"); self.assertEqual(self.hub.acts[-1], ("media_player.den_speaker", "sound_off", {}))

    async def test_questions_from_state(self):
        self.assertEqual((await self.say("is the front door locked?"))["text"], "Front door is locked.")
        self.assertEqual((await self.say("is the garage open"))["text"], "Garage door is closed.")
        self.assertEqual((await self.say("are the kitchen lights on?"))["text"], "Kitchen ceiling is on. Kitchen counter is off.")
        self.assertEqual((await self.say("what's on in the kitchen"))["text"], "Kitchen ceiling.")
        self.assertEqual((await self.say("what's the temperature in the kitchen"))["text"], "72° in the Kitchen.")
        self.assertEqual((await self.say("how cold is it outside?"))["text"], "61° and partlycloudy outside.")
        self.assertEqual((await self.say("what's playing"))["text"], "Den TV.")
        self.assertEqual(self.hub.acts, [])

    async def test_who_is_home(self):
        self.hub.presence.somebody = None
        self.assertIn("can't tell", (await self.say("is anyone home?"))["text"])

    async def test_without_the_assistant_the_grammar_says_so(self):
        with self.assertRaises(NotUnderstood) as c: await self.say("make it cosy in here")
        self.assertIn("Connect the assistant", str(c.exception))
        self.assertFalse(self.hub.log.of("said")[-1]["detail"]["understood"])

    async def test_with_the_assistant_the_rest_is_a_proposal_or_an_explanation(self):
        self.hub.assistant.configured = True
        out = await self.say("make it cosy in here")
        self.assertEqual((out["kind"], out["said"]), ("action", "make it cosy in here"))
        self.assertEqual(self.hub.assistant.asked[-1], ("draft", "make it cosy in here"))
        self.assertEqual(self.hub.acts, [])                                  # a proposal runs nothing
        out = await self.say("why did the hall light come on?")
        self.assertEqual((out["kind"], out["answer"]), ("explain", "Because the evening routine ran."))
        self.assertEqual(self.hub.assistant.asked[-1][1], "hall")

    async def test_unplaced_things_are_not_reachable(self):
        with self.assertRaises(NotUnderstood): await self.say("turn on the kasa kl125 bulb")

    async def test_nonsense_and_empty(self):
        with self.assertRaises(NotUnderstood): await self.say("")
        with self.assertRaises(NotUnderstood) as c: await self.say("kitchen")
        self.assertIn("What should the Kitchen do", str(c.exception))
        with self.assertRaises(NotUnderstood) as c: await self.say("turn on the fan in the kitchen")
        self.assertEqual(str(c.exception), "There is no fan in the Kitchen.")


if __name__ == "__main__":
    unittest.main()
