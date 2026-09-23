# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What this house has: the one door, and the arrangement it was drawn with.

design/forget/ThingsDoor.dc.html is the spec, chosen on 22 September with the row on a thing's own
pane as its shortcut. These fail on purpose if the picture drifts: the groups, the order they come
in, which rows are allowed a way out of their own, and the fact that every word on the page is
written here rather than in the panel.
"""
import unittest

from .apptest import ApiTest, hardware


class TheDoor(ApiTest):
    def registry(self, *rows): self.ha.answers["config/device_registry/list"] = list(rows)
    def entries(self, *rows): self.ha.answers["config_entries/get"] = list(rows)

    def things(self) -> dict:
        r = self.client.get("/things")
        self.assertEqual(r.status_code, 200)
        return r.json()

    def group(self, kind: str, body=None) -> dict | None:
        body = body or self.things()
        return next((g for g in body["groups"] if g["kind"] == kind), None)

    def row(self, name: str, body=None) -> dict | None:
        body = body or self.things()
        return next((t for g in body["groups"] for t in g["things"] if t["name"] == name), None)

    # ---- one row is one thing somebody owns ----

    def test_a_unit_is_one_row_with_its_parts_under_it(self):
        """A pathlight arrives as a light and a motion sensor on one piece of hardware. Three rows
        for one object is how a list of what a house HAS becomes a list of what the engine knows."""
        self.hub.home.devices["light.ceiling"].hw_name = "Walkway Pathlight"
        self.hub.home.devices["light.ceiling"].name = "Walkway Pathlight Light"
        self.hub.home.devices["binary_sensor.kitchen_motion"].hw = "hw-ceiling"
        self.hub.home.devices["binary_sensor.kitchen_motion"].hw_name = "Walkway Pathlight"
        self.hub.home.devices["binary_sensor.kitchen_motion"].name = "Walkway Pathlight Motion"
        t = self.row("Walkway Pathlight")
        self.assertIsNotNone(t)
        self.assertEqual(t["sub"], "its light · its motion")

    def test_a_part_called_what_the_whole_thing_is_called_is_not_listed_as_one_of_its_parts(self):
        """"Bedroom Fan · its bedroom fan · its light" is the object saying its own name back. The
        fan IS the thing; only what is left over is a part."""
        self.hub.home.devices["fan.ceiling_fan"].hw_name = "Bedroom Fan"
        self.hub.home.devices["fan.ceiling_fan"].name = "Bedroom Fan"
        self.hub.home.devices["light.ceiling"].hw = "hw-fan"
        self.hub.home.devices["light.ceiling"].hw_name = "Bedroom Fan"
        self.hub.home.devices["light.ceiling"].name = "Bedroom Fan Light"
        self.assertEqual(self.row("Bedroom Fan")["sub"], "its light")

    # ---- grouped by what brought it, which is the whole argument ----

    def test_a_thing_an_account_brought_has_no_way_out_of_its_own_and_says_why(self):
        self.entries({"entry_id": "entry-hw-tv", "domain": "ring", "title": "Ring"})
        t = self.row("TV")
        self.assertIsNone(t["out"])
        self.assertEqual(t["why"], "Goes with Ring")

    def test_and_the_account_above_it_carries_the_bigger_hammer_with_the_count_in_it(self):
        self.entries({"entry_id": "entry-hw-tv", "domain": "ring", "title": "Ring"})
        g = self.group("account")
        self.assertEqual(g["name"], "Ring · signed in")
        self.assertEqual(g["act"]["do"], "Remove Ring, and the one thing with it")
        self.assertEqual(g["act"]["act"], "account")
        self.assertEqual(g["act"]["to"], "entry-hw-tv")
        self.assertIn("TV", g["act"]["ask"])

    def test_the_count_reads_when_more_than_one_came_in_with_it(self):
        """"and all one with it" does not read, and a door's words are read far more often than
        they are written."""
        self.hub.home.devices["media_player.tv"].entry = "e"
        self.hub.home.devices["climate.nest"].entry = "e"
        self.entries({"entry_id": "e", "domain": "ring", "title": "Ring"})
        self.assertEqual(self.group("account")["act"]["do"], "Remove Ring, and all 2 with it")

    def test_the_engine_is_not_somebodys_account_and_a_thing_on_it_was_set_up_here(self):
        """The brain added mqtt, zwave_js and matter itself. Nobody signed into them, so a light on
        the Z-Wave stick belongs under Set up here and may leave on its own."""
        self.hub.home.devices["light.ceiling"].entry = "e-zwave"
        self.entries({"entry_id": "e-zwave", "domain": "zwave_js", "title": "Z-Wave JS"})
        self.assertIsNone(self.group("account"))
        self.assertIsNotNone(self.row("Ceiling light")["out"])

    # ---- the two kinds of our own, which do not go through the registry ----

    def test_a_wall_switch_is_under_its_bridge_and_not_under_set_up_here(self):
        self.registry(hardware("hw-ceiling", identifiers=[["mqtt", "mesh_0123456789abcdef_0021"]]))
        g = self.group("bridge")
        self.assertIsNotNone(g)
        self.assertEqual([t["name"] for t in g["things"]], ["Ceiling light"])
        self.assertNotIn("Ceiling light", [t["name"] for t in self.group("here")["things"]])

    def test_and_says_the_one_thing_a_household_would_otherwise_fear(self):
        """The switch on the wall keeps working. Nothing else on this page has to say that, and a
        person about to take a light switch out of their house does."""
        self.registry(hardware("hw-ceiling", identifiers=[["mqtt", "mesh_0123456789abcdef_0021"]]))
        self.assertIn("The wall switch itself keeps working",
                      self.group("bridge")["things"][0]["out"]["ask"])

    def test_a_light_strip_goes_through_its_own_way_out(self):
        self.registry(hardware("hw-ceiling", identifiers=[["mqtt", "strip_c8ebba"]]))
        t = self.row("Ceiling light")
        self.assertEqual(t["out"]["act"], "strip")
        self.assertEqual(t["out"]["to"], "c8ebba")
        self.assertIn("forget the house too", t["out"]["ask"])

    # ---- and the shape of the page ----

    def test_the_order_is_accounts_then_what_was_set_up_here_then_the_bridges(self):
        """What somebody came for is at the top: the accounts are the things that leave in a lump,
        and the bridge is the one a household looks for last."""
        self.entries({"entry_id": "entry-hw-tv", "domain": "ring", "title": "Ring"})
        self.registry(hardware("hw-ceiling", identifiers=[["mqtt", "mesh_0123456789abcdef_0021"]]))
        self.assertEqual([g["kind"] for g in self.things()["groups"]], ["account", "here", "bridge"])

    def test_every_row_carries_its_own_words_and_the_panel_invents_none(self):
        for g in self.things()["groups"]:
            for t in g["things"]:
                if not t["out"]: self.assertTrue(t.get("why"), t["name"])
                else:
                    for k in ("do", "act", "to", "ask", "yes", "no"): self.assertIn(k, t["out"])
                    self.assertIn(t["name"], t["out"]["ask"])
                    self.assertIn(t["name"], t["out"]["yes"])

    def test_the_question_names_the_thing_before_the_one_act_with_no_undo(self):
        t = self.row("Ceiling light")
        self.assertEqual(t["out"]["do"], "Take it out")
        self.assertEqual(t["out"]["yes"], "Yes, take Ceiling light out")
        self.assertEqual(t["out"]["no"], "Keep it")

    def test_the_count_is_things_a_household_owns(self):
        body = self.things()
        self.assertEqual(body["count"],
                         sum(len(g["things"]) for g in body["groups"] if g["kind"] != "engine"))

    def test_it_needs_the_passcode_like_every_other_way_of_changing_the_house(self):
        """Reading it is open -- somebody should be able to see what they own. The ways out of it
        are DELETE /devices, DELETE /strip and the account door, and lock.py gates all three."""
        from hub.lock import needs_code
        self.assertFalse(needs_code("GET", "/things"))
        self.assertTrue(needs_code("DELETE", "/devices/light.ceiling"))
        self.assertTrue(needs_code("DELETE", "/strip/c8ebba"))
        self.assertTrue(needs_code("DELETE", "/accounts/entry-hw-tv"))


if __name__ == "__main__":
    unittest.main()
