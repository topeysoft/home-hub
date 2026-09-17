"""Two switches, one light, with no mesh and no broker.

What these hold is the behaviour a person at the bottom of the stairs would notice, and the four
ways a naive relay would misbehave: replaying every press when the broker reconnects, treating a
ten-minute resync as a touch, volleying with itself, and calling a dropped command a success.

Two kinds of link, because watching a real pair showed they are not the same thing. A COMPANION
announces a press addressed to its partner and holds an on/off position of its own that has nothing
to do with the light -- so its press toggles the load, and its state is ignored. A MIRROR link makes
one light follow another's state. The payloads in the press tests are the real ones, off the wire.
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


def press_to(partner: str) -> str:
    """A real companion press, as the puck publishes it: vendor 0403 addressed to the partner."""
    return json.dumps({"src": "0x0006", "dst": partner, "opcode": "0xc12008",
                       "kind": "vendor", "params": "0403"})


class RelayTest(unittest.IsolatedAsyncioTestCase):
    """Mirror links: the load is made to match the switch that leads."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.hub = FakeHub()
        self.relay = Relay(self.hub, path=Path(self.dir.name) / "switch-links.json")
        self.relay.add({"net": OURS, "addr": "0x0004"}, {"net": PANEL, "addr": "0011"}, "Stairway", on="state")
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

    async def test_the_load_is_made_to_match_the_switch(self):
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
        self.relay.add({"net": PANEL, "addr": "0011"}, {"net": OURS, "addr": "0004"}, "Stairway back", on="state")
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
        self.relay.add({"net": PANEL, "addr": "0011"}, {"net": PANEL, "addr": "0010"}, "not a loop", on="state")
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
        self.relay.add({"net": OURS, "addr": "0004"}, {"net": PANEL, "addr": "0011"}, "Stairs", on="state")
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
        self.relay.add({"net": OURS, "addr": "0004"}, {"net": PANEL, "addr": "0011"}, "Stairway", enabled=False, on="state")
        self.press("OFF", retain=True)
        self.press("ON")
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    def test_removing_a_link_says_whether_there_was_one(self):
        self.assertTrue(self.relay.remove(self.relay.links[0]["id"]))
        self.assertFalse(self.relay.remove("nothing"))


class PressTest(unittest.IsolatedAsyncioTestCase):
    """Companion links: a press toggles the load, and the companion's own state is ignored.

    The payloads are the real ones, captured off a working two-way pair on 17 September 2026.
    """

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.hub = FakeHub()
        self.relay = Relay(self.hub, path=Path(self.dir.name) / "switch-links.json")
        self.relay.add({"net": PANEL, "addr": "0006"}, {"net": PANEL, "addr": "0005"}, "Landing", on="press")
        self.hub.ha.answers = self.relay
        self.relay.settle, self.relay.confirm = 0.01, 0.05

    def tearDown(self):
        self.dir.cleanup()

    def load_is(self, state):
        self.relay.on_message(PANEL, "0005", "state", state, True)

    def press(self, partner="0x0005", addr="0006"):
        self.relay.on_message(PANEL, addr, "event", press_to(partner), False)

    async def settle(self):
        for _ in range(60):
            await asyncio.sleep(0.01)
            if not any(not t.done() for t in list(self.relay._tasks)):
                break

    async def test_a_press_turns_the_load_the_other_way(self):
        self.load_is("OFF")
        self.press()
        await self.settle()
        self.assertEqual(self.hub.ha.published, [(f"mesh/{PANEL}/0005/set", "ON")])

    async def test_and_back_again(self):
        self.load_is("ON")
        self.press()
        await self.settle()
        self.assertEqual(self.hub.ha.published, [(f"mesh/{PANEL}/0005/set", "OFF")])

    async def test_three_presses_are_three_toggles(self):
        """The user pressed a real companion three times and the light answered every time."""
        self.load_is("OFF")
        for _ in range(3):
            self.press()
            await self.settle()
            self.relay._pressed.clear()       # a hand, not a retransmission
        self.assertEqual([p for _t, p in self.hub.ha.published], ["ON", "OFF", "ON"])

    async def test_the_same_message_twice_is_one_press(self):
        """The mesh can deliver a message twice; a finger cannot press twice in a tenth of a second."""
        self.load_is("OFF")
        self.press(); self.press()
        await self.settle()
        self.assertEqual(len(self.hub.ha.published), 1)

    async def test_the_companions_own_state_is_ignored(self):
        """It holds a position of its own: on a real pair it said ON while the light was OFF."""
        self.load_is("ON")
        self.relay.on_message(PANEL, "0006", "state", "OFF", True)
        self.relay.on_message(PANEL, "0006", "state", "ON", False)
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    async def test_a_load_we_have_never_heard_from_is_not_guessed_at(self):
        """A light that comes on when somebody meant to turn it off is worse than one that does nothing."""
        self.press()
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])
        self.assertTrue(self.hub.log.rows)

    async def test_configuration_on_the_same_model_is_not_a_press(self):
        """Vendor 0xc12008 carries the config store and the heartbeat too; only 04 is a finger."""
        self.load_is("OFF")
        for params in ("130c0100", "1103", "1304e80300", "12481e00"):
            self.relay.on_message(PANEL, "0006", "event", json.dumps(
                {"src": "0x0006", "dst": "0x0005", "opcode": "0xc12008", "kind": "vendor",
                 "params": params}), False)
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    async def test_a_retained_event_is_not_a_press(self):
        self.load_is("OFF")
        self.relay.on_message(PANEL, "0006", "event", press_to("0x0005"), True)
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    async def test_a_sig_status_on_the_wire_is_not_a_press(self):
        """A main press is a broadcast Status -- real, but not this link's business."""
        self.load_is("OFF")
        self.relay.on_message(PANEL, "0005", "event", json.dumps(
            {"src": "0x0005", "dst": "0xffff", "opcode": "0x008204", "kind": "sig",
             "params": "01"}), False)
        await self.settle()
        self.assertEqual(self.hub.ha.published, [])

    def test_a_link_from_before_there_was_a_choice_is_a_mirror(self):
        """The stairway link was written by hand when state was the only thing a link could watch."""
        self.relay.path.write_text(json.dumps({"links": [
            {"id": "old", "from": {"net": OURS, "addr": "0004"}, "to": {"net": PANEL, "addr": "0011"}},
        ]}))
        again = Relay(self.hub, path=self.relay.path)
        self.assertEqual(again.links[0]["on"], "state")

    def test_nonsense_in_the_how_is_refused(self):
        with self.assertRaises(ValueError):
            self.relay.add({"net": OURS, "addr": "0004"}, {"net": PANEL, "addr": "0011"}, on="sometimes")


if __name__ == "__main__":
    unittest.main()
