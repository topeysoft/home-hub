# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Who can hear a strip knocking, without a strip or a puck.

The hub's own radio is in the garage and the strip is behind the television, so the hub is one ear
among several (hub/ears.py, docs/strip.md item 42). These hold the contract a puck reports against,
the rule for which ear gets to talk to a strip, and the two places the table is fed.
"""
import tempfile, unittest
from pathlib import Path

from hub.bridge import Bridges
from hub.ears import FRESH, Ears
from tests.test_bridge import FakeCable, FakeHub as BridgeHub
from tests.test_strip import FakeHub as StripHub, FakeRadio, run
from hub.strip import Strips

OURS = "00000ff1ff008000"      # what an S3 running our firmware really advertises: vendor 0xFFF1
PLUG = "00000fe011007000"      # a Matter device of somebody else's, in pairing mode


def report(addr="e7:38:84:e2:89:0a", rssi=-40, svc=OURS, kind="random"):
    return f'{{"addr": "{addr}", "type": "{kind}", "rssi": {rssi}, "svc": "{svc}"}}'


class WhatAPuckSays(unittest.TestCase):

    def test_a_knock_is_decoded_by_the_hubs_own_decoder(self):
        e = Ears()
        self.assertTrue(e.from_puck("08388e", report(), now=100))
        heard = e.who_can_hear("E7:38:84:E2:89:0A", now=101)
        self.assertEqual([h["ear"] for h in heard], ["08388e"])
        self.assertEqual(heard[0]["rssi"], -40)

    def test_somebody_elses_plug_in_pairing_mode_is_not_our_business(self):
        e = Ears()
        self.assertFalse(e.from_puck("08388e", report(svc=PLUG), now=100))
        self.assertEqual(e.who_can_hear("e7:38:84:e2:89:0a", now=100), [])

    def test_nonsense_off_the_broker_is_dropped_and_not_raised(self):
        e = Ears()
        for junk in ("", "{", '{"addr": "x"}', '{"addr": "x", "rssi": "loud", "svc": "00"}'):
            self.assertFalse(e.from_puck("08388e", junk, now=100), junk)

    def test_a_report_exactly_as_a_puck_sent_it_on_the_air(self):
        """Copied off the broker on 23 September, from ear.cpp on a real puck hearing a real strip --
        so the two ends are held to what one of them actually says, not to what this file thinks."""
        e = Ears()
        wire = '{"addr":"d7:e4:af:b4:05:2b","type":"random","rssi":-37,"svc":"00000ff1ff008000"}'
        self.assertTrue(e.from_puck("08388e", wire, now=100))
        self.assertEqual(e.choose("d7:e4:af:b4:05:2b", now=100), "08388e")

    def test_a_loudness_no_real_radio_could_hear_is_not_a_reading(self):
        """-8 dBm from a strip a metre away, which NimBLE really does hand back now and then."""
        e = Ears()
        self.assertFalse(e.from_puck("08388e", report(rssi=-8), now=100))
        self.assertEqual(e.who_can_hear("e7:38:84:e2:89:0a", now=100), [])

    def test_the_address_type_travels_with_the_address(self):
        """A strip's address is random, and one opened as public is six right bytes nobody answers
        -- which is the morning item 42 was written about."""
        e = Ears()
        e.from_puck("08388e", report(), now=100)
        self.assertEqual(e.who_can_hear("e7:38:84:e2:89:0a", now=100)[0]["type"], "random")
        e.from_puck("08388e", report(kind="public"), now=101)
        self.assertEqual(e.who_can_hear("e7:38:84:e2:89:0a", now=101)[0]["type"], "public")

    def test_a_strip_nobody_has_heard_lately_is_forgotten_without_anybody_saying_so(self):
        """Which is also how a strip that has been taken leaves: it stops knocking."""
        e = Ears()
        e.from_puck("08388e", report(), now=100)
        self.assertEqual(e.who_can_hear("e7:38:84:e2:89:0a", now=100 + FRESH + 1), [])
        e.forget_stale(now=100 + FRESH + 1)
        self.assertEqual(e._heard, {})


class WhichEarTalksToIt(unittest.TestCase):
    A = "E7:38:84:E2:89:0A"

    def ears(self, **rssi):
        e = Ears()
        for ear, r in rssi.items():
            e.heard("hub" if ear == "hub" else ear, self.A, r, now=100)
        return e

    def test_the_hubs_own_radio_wins_wherever_it_is_good_enough(self):
        """Inside the edge item 15 measured, a session through the hub's radio establishes first time
        and needs no courier -- so a louder puck is not better, only further away."""
        self.assertEqual(self.ears(hub=-55, p1=-35).choose(self.A, now=101), "hub")

    def test_past_the_edge_a_clearly_louder_puck_runs_the_errand(self):
        self.assertEqual(self.ears(hub=-72, p1=-45).choose(self.A, now=101), "p1")

    def test_a_puck_that_is_barely_louder_is_barely_better_and_is_not_worth_the_hop(self):
        self.assertEqual(self.ears(hub=-72, p1=-70).choose(self.A, now=101), "hub")

    def test_the_loudest_of_several_pucks_is_the_one_asked(self):
        self.assertEqual(self.ears(hub=-80, p1=-60, p2=-44).choose(self.A, now=101), "p2")

    def test_a_hub_with_no_bluetooth_at_all_still_has_ears(self):
        """The mini PC hub the product is sized for may have no radio: that is an ordinary hub now."""
        self.assertEqual(self.ears(p1=-70).choose(self.A, now=101), "p1")

    def test_nobody_can_hear_it(self):
        self.assertIsNone(Ears().choose(self.A, now=101))


class WhereTheTableIsFed(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self): self.tmp.cleanup()

    def test_a_pucks_report_arrives_through_the_subscription_the_bridge_already_has(self):
        hub = BridgeHub(self.tmp.name)
        hub.ears = Ears()
        dev = Path(self.tmp.name) / "by-id"; dev.mkdir()
        b = Bridges(hub, cable=FakeCable(), devdir=dev)
        b._on_mqtt({"topic": "mesh/bridge/08388e/heard", "payload": report(rssi=-38)})
        self.assertEqual([h["ear"] for h in hub.ears.who_can_hear("e7:38:84:e2:89:0a")], ["08388e"])

    def test_what_the_hubs_own_radio_hears_goes_in_the_same_table(self):
        hub = StripHub(self.tmp.name)
        hub.ears = Ears()
        radio = FakeRadio()
        radio.advertising = [{"addr": "AA:BB:CC:DD:EE:FF", "discriminator": 3840, "rssi": -71,
                              "vendor": 0xFFF1, "product": 0x8000, "ours": True}]
        run(Strips(hub, radio=radio).look())
        heard = hub.ears.who_can_hear("aa:bb:cc:dd:ee:ff")
        self.assertEqual([(h["ear"], h["rssi"]) for h in heard], [("hub", -71)])


if __name__ == '__main__':
    unittest.main()
