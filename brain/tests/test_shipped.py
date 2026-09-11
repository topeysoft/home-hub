"""The files the product ships, checked as product rather than as code.

rules.json and scenes.json are copied into a new hub's data volume on first run and are what a family
gets before they have changed anything. A rule that cannot run is not an error anyone will see — the
engine drops it and logs a line nobody reads — so the only place it can be caught is here.

Run from brain/: .venv/bin/python -m unittest -v
"""
import json, unittest

from hub import intents, rules
from hub.intents import SERVICE, RoomState

SHIPPED = json.loads(rules.SEED.read_text())
# The rooms a rule may name without the house having one: "home" is the whole house and "entry" is
# whichever rooms the family picked on the panel. Anything else has to exist in that particular house.
ANY_HOUSE = {"home", rules.ENTRY}


class ShippedRulesTests(unittest.TestCase):
    def test_the_file_is_readable_and_has_rules_in_it(self):
        self.assertIsInstance(SHIPPED.get("rules"), list)
        self.assertTrue(SHIPPED["rules"])

    def test_every_rule_is_well_formed_enough_to_run_somewhere(self):
        # Validated against a house that happens to have every room the file names, so what this catches
        # is a malformed rule rather than a missing room. The room question is the test below.
        named = {r.get("room") for r in SHIPPED["rules"] if isinstance(r, dict)} - ANY_HOUSE
        good, errors = rules.validate(SHIPPED, named)
        self.assertEqual(errors, [])
        self.assertEqual(len(good), len(SHIPPED["rules"]))

    def test_no_two_rules_share_an_id(self):
        ids = [r["id"] for r in SHIPPED["rules"]]
        self.assertEqual(sorted(ids), sorted(set(ids)))

    def test_every_rule_a_new_house_starts_with_can_run_in_that_house(self):
        """A rule naming a room only one house has is dropped on every other hub, silently.

        The rules shipped in the box have to work for a family that has just plugged theirs in, which
        means they may only name "home" or "entry" — the rooms every house has by definition.
        """
        elsewhere = {r["id"]: r["room"] for r in SHIPPED["rules"] if r.get("room") not in ANY_HOUSE}
        self.assertEqual(elsewhere, {}, f"these would not run in anyone else's house: {elsewhere}")

    def test_every_rule_says_what_it_is_for_in_words_a_person_could_read(self):
        for r in SHIPPED["rules"]:
            with self.subTest(rule=r["id"]):
                self.assertTrue((r.get("name") or "").strip(), "a rule with no name is a blank row on the panel")

    def test_a_rule_that_ships_switched_off_would_be_a_puzzle_so_none_do(self):
        for r in SHIPPED["rules"]:
            with self.subTest(rule=r["id"]):
                self.assertTrue(r.get("enabled", True))


class ShippedScenesTests(unittest.TestCase):
    SCENES = json.loads(intents.SEED.read_text())

    def test_there_is_a_scene_for_every_state_a_room_can_be_in(self):
        named = {k for k in self.SCENES if not k.startswith("_")}
        self.assertEqual(named, {s.value for s in RoomState})

    def test_every_action_in_it_is_one_the_house_can_carry_out(self):
        for state, actions in self.SCENES.items():
            if state.startswith("_"): continue
            for cap, action, _data in actions:
                with self.subTest(state=state, cap=cap, action=action):
                    self.assertIn((cap, action), SERVICE)

    def test_how_long_a_hand_set_room_holds_is_given_for_every_state(self):
        self.assertEqual(set(self.SCENES["_hold"]), {s.value for s in RoomState})


if __name__ == "__main__":
    unittest.main()
