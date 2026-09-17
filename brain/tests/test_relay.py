"""Two switches, one light, with no mesh and no broker.

What these hold is the behaviour a person at the bottom of the stairs would notice, and the four
ways a naive relay would misbehave: replaying every press when the broker reconnects, treating a
ten-minute resync as a touch, volleying with itself, and calling a dropped command a success.
"""
import asyncio, json, tempfile, unittest
from pathlib import Path

from hub.relay import Relay


class FakeHA:
    """Records publishes, and can answer them the way a load switch's Status would."""
    def __init__(self):
        self.published = []
        self.answers = None          # set to a Relay to echo commands back as state

    async def call(self, domain, service, entity_id, **data):
        self.published.append((data["topic"], data["payload"]))
        if self.answers is not None:
            _base, net, addr, *leaf = data["topic"].split("/")
            if leaf == ["set"]:
                self.answers.on_message(net, addr, "state", data["payload"], False)
            elif leaf == ["brightness", "set"]:
                self.answers.on_message(net, addr, "brightness", data["payload"], False)


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, *a, **k): self.rows.append((a, k))


class FakeHub:
    def __init__(self):
        self.ha = FakeHA()
        self.log = FakeLog()


OURS, PANEL = "7dcdd6f322c30af4", "3deef9825e444955"


class RelayTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.hub = FakeHub()
        self.relay = Relay(self.hub, path=Path(self.dir.name) / "switch-links.json")
        self.relay.add({"net": OURS, "addr": "0x0004"}, {"net": PANEL, "addr": "0011"}, "Stairway")
        self.hub.ha.answers = self.relay      # the load answers, unless a test says otherwise
        self.relay.settle, self.relay.confirm = 0.01, 0.05   # the same waits, at test speed

    def tearDown(self):
        self.dir.cleanup()

    def press(self, state, brightness=None, net=OURS, addr="0004", retain=False):
        self.relay.on_message(net, addr, "state", state, retain)
        if brightness is not None:
            self.relay.on_message(net, addr, "brightness", brightness, retain)

    async def settle(self):
        for _ in range(60):
            await asyncio.sleep(0.01)
            if not any(not t.done() for t in list(self.relay._tasks)):
                break

    # ---- what a person sees ----

    async def test_a_press_on_the_companion_drives_the_load(self):
        self.press("OFF", "0", retain=True)         # where things stood when the hub joined
        self.press("ON", "255")
        await self.settle()
        self.assertIn((f"mesh/{PANEL}/0011/set", "ON"), self.hub.ha.published)
        self.assertEqual(self.relay.carried, 1)

    async def test_off_is_carried_too(self):
        self.press("ON", retain=True)
        self.press("OFF")
        await self.settle()
        self.assertEqual(self.hub.ha.published, [(f"mesh/{PANEL}/0011/set", "OFF")])

    async def test_a_dim_level_goes_with_it(self):
        self.press("OFF", "0", retain=True)
        self.press("ON", "120")
        await self.settle()
        self.assertEqual(self.hub.ha.published,
                         [(f"mesh/{PANEL}/0011/set", "ON"), (f"mesh/{PANEL}/0011/brightness/set", "120")])

    async def test_state_and_brightness_together_are_one_command(self):
        """A press publishes both a moment apart; the light should not be told twice."""
        self.press("OFF", "0", retain=True)
        self.relay.on_message(OURS, "0004", "state", "ON", False)
        await asyncio.sleep(0.005)
        self.relay.on_message(OURS, "0004", "brightness", "200", False)
        await self.settle()
        self.assertEqual([t for t, _ in self.hub.ha.published].count(f"mesh/{PANEL}/0011/set"), 1)

    # ---- the four ways it would go wrong ----

    async def test_retained_state_never_acts(self):
        """Every puck republishes everything, retained, on each reconnect to the broker."""
        self.press("OFF", "0", retain=True)
        self.press("ON", "255", retain=True)
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    async def test_the_same_value_again_is_a_resync_not_a_press(self):
        self.press("ON", retain=True)
        self.press("ON")             # the puck's ten-minute Get, or its link-up sweep
        self.press("ON")
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    async def test_the_first_value_ever_heard_is_a_baseline_not_a_press(self):
        self.press("ON", "255")      # nothing retained: the brain has no idea what came before
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    async def test_two_links_facing_each_other_do_not_volley(self):
        self.relay.add({"net": PANEL, "addr": "0011"}, {"net": OURS, "addr": "0004"}, "Stairway back")
        self.press("OFF", retain=True)
        self.relay.on_message(PANEL, "0011", "state", "OFF", True)
        self.press("ON")
        await self.settle()
        self.assertEqual([p for t, p in self.hub.ha.published if t.endswith("/set")], ["ON"])

    async def test_a_dropped_command_is_retried_and_then_said_plainly(self):
        self.hub.ha.answers = None   # the load never answers: a weak link
        self.press("OFF", retain=True)
        self.press("ON")
        await self.settle()
        self.assertEqual(len(self.hub.ha.published), self.relay.tries)
        self.assertEqual(self.relay.carried, 0)
        self.assertTrue(self.hub.log.rows)

    async def test_our_own_command_coming_back_is_not_a_press(self):
        """The puck publishes the state of everything it hears, our commands included."""
        self.relay.add({"net": PANEL, "addr": "0011"}, {"net": PANEL, "addr": "0010"}, "not a loop")
        self.relay.on_message(PANEL, "0011", "state", "OFF", True)
        self.relay.on_message(PANEL, "0010", "state", "OFF", True)
        self.press("OFF", retain=True)
        self.press("ON")
        await self.settle()
        self.assertNotIn(f"mesh/{PANEL}/0010/set", [t for t, _ in self.hub.ha.published])

    # ---- the links themselves ----

    def test_an_address_is_written_one_way_however_it_is_typed(self):
        l = self.relay.add({"net": OURS, "addr": "0x4"}, {"net": PANEL, "addr": "11"})
        self.assertEqual((l["from"]["addr"], l["to"]["addr"]), ("0004", "0011"))

    def test_the_same_pair_twice_is_one_link(self):
        self.relay.add({"net": OURS, "addr": "0004"}, {"net": PANEL, "addr": "0011"}, "Stairs")
        self.assertEqual(len(self.relay.links), 1)
        self.assertEqual(self.relay.links[0]["name"], "Stairs")

    def test_a_switch_cannot_be_its_own_companion(self):
        with self.assertRaises(ValueError):
            self.relay.add({"net": OURS, "addr": "0004"}, {"net": OURS, "addr": "0004"})

    def test_nonsense_is_refused_rather_than_stored(self):
        for bad in ({"net": "short", "addr": "0004"}, {"net": OURS, "addr": "zzzz"}, {"net": OURS, "addr": "00011"}):
            with self.assertRaises(ValueError):
                self.relay.add(bad, {"net": PANEL, "addr": "0011"})

    def test_links_survive_a_restart(self):
        again = Relay(self.hub, path=self.relay.path)
        self.assertEqual(again.links, self.relay.links)

    def test_a_damaged_file_loses_the_bad_row_not_the_house(self):
        self.relay.path.write_text(json.dumps({"links": [
            {"from": {"net": OURS, "addr": "0004"}, "to": {"net": PANEL, "addr": "0011"}, "id": "keep"},
            {"from": {"net": OURS}, "to": {}},
        ]}))
        again = Relay(self.hub, path=self.relay.path)
        self.assertEqual([l.get("id") for l in again.links], ["keep"])

    async def test_a_disabled_link_carries_nothing(self):
        self.relay.add({"net": OURS, "addr": "0004"}, {"net": PANEL, "addr": "0011"}, "Stairway", enabled=False)
        self.press("OFF", retain=True)
        self.press("ON")
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    def test_removing_a_link_says_whether_there_was_one(self):
        self.assertTrue(self.relay.remove(self.relay.links[0]["id"]))
        self.assertFalse(self.relay.remove("nothing"))


if __name__ == "__main__":
    unittest.main()
