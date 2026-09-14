"""The controls a device's own pane needs, which the room's tiles never asked for: a blind put where
you want it and stopped on the way, a fan at a speed, a mower sent out and called back, and a plug
that switches itself off again.

Run from brain/: .venv/bin/python -m unittest -v
"""
import time

from tests.apptest import ApiTest, house, hardware, entity, state


def house_with_a_blind_and_a_mower():
    """The test house plus the two kinds it has never had: something that moves to a position, and
    something whose whole vocabulary is out and back."""
    areas, devices, entities, states = house()
    devices += [hardware("hw-blind", "living", "Blinds", manufacturer="IKEA"),
                hardware("hw-mower", "kitchen", "Robot mower")]
    entities += [entity("cover.blinds", "hw-blind"), entity("vacuum.mower", "hw-mower")]
    states += [state("cover.blinds", "open", friendly_name="Blinds", current_position=70),
               state("vacuum.mower", "docked", friendly_name="Robot mower")]
    return areas, devices, entities, states


class PaneControlTests(ApiTest):
    def setUp(self):
        super().setUp()
        self.hub.home.build(*house_with_a_blind_and_a_mower())

    def test_a_blind_goes_where_it_is_put_and_stops_when_it_is_told(self):
        self.assertEqual(self.client.post("/devices/cover.blinds/set", json={"position": 40}).status_code, 200)
        self.assertEqual(self.ha.called("cover", "set_cover_position")[0][3], {"position": 40})
        self.assertEqual(self.client.post("/devices/cover.blinds/stop").status_code, 200)
        self.assertEqual(len(self.ha.called("cover", "stop_cover", "cover.blinds")), 1)

    def test_a_fan_runs_at_a_speed_rather_than_only_on(self):
        self.assertEqual(self.client.post("/devices/fan.ceiling_fan/set", json={"percentage": 40}).status_code, 200)
        self.assertEqual(self.ha.called("fan", "set_percentage")[0][3], {"percentage": 40})

    def test_a_mower_is_sent_out_and_called_back(self):
        self.assertEqual(self.client.post("/devices/vacuum.mower/start").status_code, 200)
        self.assertEqual(self.client.post("/devices/vacuum.mower/return").status_code, 200)
        self.assertEqual([c[1] for c in self.ha.called("vacuum")], ["start", "return_to_base"])

    def test_a_mower_still_cannot_be_turned_on_because_there_is_no_such_thing(self):
        r = self.client.post("/devices/vacuum.mower/on")
        self.assertEqual(r.status_code, 400)
        self.assertIn("cannot on", r.json()["detail"])
        self.assertEqual(self.ha.calls, [])

    def test_a_plug_on_a_timer_goes_on_now_and_carries_when_it_goes_off(self):
        r = self.client.post("/devices/switch.kettle/timer", json={"minutes": 30})
        self.assertEqual(r.status_code, 200)
        self.assertAlmostEqual(r.json()["off_at"], time.time() + 30 * 60, delta=5)
        self.assertEqual(len(self.ha.called("switch", "turn_on", "switch.kettle")), 1)
        # every screen hears about it, and the thing itself carries the time
        self.assertEqual(self.sent("device")[-1]["device"]["attrs"]["off_at"], r.json()["off_at"])

    def test_cancelling_a_timer_leaves_the_thing_on(self):
        self.client.post("/devices/switch.kettle/timer", json={"minutes": 30})
        self.ha.calls.clear()
        r = self.client.post("/devices/switch.kettle/timer", json={"minutes": 0})
        self.assertEqual(r.json()["off_at"], None)
        self.assertEqual(self.ha.calls, [])                      # nothing was switched off: only the timer went
        self.assertNotIn("off_at", self.sent("device")[-1]["device"]["attrs"])

    def test_a_timer_is_clamped_and_refused_on_something_with_no_off(self):
        r = self.client.post("/devices/switch.kettle/timer", json={"minutes": 99999})
        self.assertLessEqual(r.json()["off_at"], time.time() + 720 * 60 + 1)
        self.assertEqual(self.client.post("/devices/sensor.kitchen_temp/timer", json={"minutes": 5}).status_code, 400)
        self.assertEqual(self.client.post("/devices/switch.nowhere/timer", json={"minutes": 5}).status_code, 404)

    def test_what_one_thing_did_is_asked_for_by_that_thing(self):
        """The foot of every pane: /events, narrowed to one device. The log already keeps it; this is
        the query the pane makes."""
        self.client.post("/devices/light.ceiling/off")
        self.client.post("/devices/switch.kettle/on")
        mine = self.client.get("/events?subject=light.ceiling").json()
        self.assertEqual([(e["kind"], e["new"]) for e in mine], [("action", "off")])
