# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The network the house runs on, without a network.

These hold the two bugs docs/network.md was written for, so that neither can come back quietly:

  * the hub handing out a password it was told once, long after it stopped being the right one, and
    finishing with a green tick;
  * a bridge being written with a DHCP lease instead of a name.

And the property the whole design rests on: a bridge is only counted as having followed when it says
so from the broker, because that is the only thing a puck cannot say from the wrong network.
"""
import asyncio, json, tempfile, unittest
from pathlib import Path

from hub.bridge import Bridges
from hub.network import Network, words
from hub.settings import Settings


class FakeHA:
    def __init__(self): self.cb = None; self.published = []
    async def subscribe(self, type_, cb, **kw): self.cb = cb; return 1
    async def call(self, domain, service, target, **kw):
        self.published.append((kw.get("topic"), kw.get("payload"), kw.get("retain")))


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, *a, **k): self.rows.append((a, k))


class FakeHub:
    def __init__(self, tmp):
        self.settings = Settings(Path(tmp) / "settings.json")
        self.env = {"MQTT_USER": "hub", "MQTT_PASSWORD": "pw"}
        self.ha, self.log, self.pushed = FakeHA(), FakeLog(), []
        self.home = None
        self.net = None
    def _broadcast(self, msg): self.pushed.append(json.loads(msg))


def run(coro): return asyncio.run(coro)


class ReadingItsOwn(unittest.TestCase):
    """What the hub can say about its own connection, including 'nothing'."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "network.json"
        self.req = Path(self.tmp.name) / "network.request"
        self.hub = FakeHub(self.tmp.name)
        self.net = Network(self.hub, state=self.state, request=self.req)

    def tearDown(self): self.tmp.cleanup()

    def write(self, **kw): self.state.write_text(json.dumps({"at": 9e9, "hostname": "hub", **kw}))

    def test_no_host_script_is_unknown_and_says_so(self):
        """A brain on a laptop must not offer a button that writes into the void."""
        s = self.net.state()
        self.assertEqual(s["how"], "unknown")
        self.assertFalse(s["can_change"])
        self.assertFalse(s["managed"])

    def test_a_cable_is_a_cable(self):
        self.write(links=[{"kind": "ethernet", "device": "eth0", "up": True, "ip": "192.168.1.9"}])
        s = self.net.state()
        self.assertEqual((s["how"], s["ip"]), ("cable", "192.168.1.9"))
        # No radio on this machine: there is nothing to change to, so nothing is offered.
        self.assertFalse(s["can_change"])

    def test_the_cable_wins_over_the_wifi_behind_it(self):
        """Adding Wi-Fi to a wired hub must not read as having moved it."""
        self.write(links=[{"kind": "ethernet", "device": "eth0", "up": True, "ip": "192.168.1.9"},
                          {"kind": "wifi", "device": "wlan0", "up": False, "ssid": "Upstairs"}])
        s = self.net.state()
        self.assertEqual(s["how"], "cable")
        self.assertEqual(s["spare"], "Upstairs")
        self.assertTrue(s["can_change"])        # there IS a radio, so the button means something

    def test_wifi_reports_its_name_in_words(self):
        self.write(links=[{"kind": "wifi", "device": "wlan0", "up": True, "ssid": "Upstairs",
                           "signal": 78, "ip": "192.168.1.30", "band": "5"}])
        s = self.net.state()
        self.assertEqual((s["how"], s["ssid"], s["signal"]), ("wifi", "Upstairs", "strong"))

    def test_signal_is_three_words_and_never_a_number(self):
        self.assertEqual([words(90), words(50), words(12), words(None)], ["strong", "ok", "faint", None])

    def test_a_request_names_a_verb_from_a_list(self):
        """The script checks this too. Here it is a stack trace rather than a silent no-op."""
        self.write(links=[{"kind": "wifi", "device": "wlan0", "up": True, "ssid": "Up"}])
        with self.assertRaises(ValueError):
            self.net._ask("rm -rf /")
        self.assertFalse(self.req.exists())

    def test_joining_writes_a_request_and_nothing_else(self):
        self.write(links=[{"kind": "wifi", "device": "wlan0", "up": True, "ssid": "Up", "signal": 60}])
        self.net.join("Downstairs", "hunter2 with space")
        asked = json.loads(self.req.read_text())
        self.assertEqual((asked["do"], asked["ssid"], asked["password"]), ("join", "Downstairs", "hunter2 with space"))
        self.assertEqual(self.hub.log.rows[0][0][:2], ("home", "network"))

    def test_an_unmanaged_hub_refuses_in_words(self):
        with self.assertRaises(ValueError):
            self.net.join("Downstairs", "x")


class WhatThePucksAreGiven(unittest.TestCase):
    """The original bug: a password typed once, handed out for ever."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "network.json"
        self.hub = FakeHub(self.tmp.name)
        self.hub.net = Network(self.hub, state=self.state, request=Path(self.tmp.name) / "network.request")
        self.b = Bridges(self.hub, cable=None, devdir=Path(self.tmp.name))
        self.hub.settings.set(wifi={"ssid": "Upstairs", "pass": "hunter2"})

    def tearDown(self): self.tmp.cleanup()

    def wifi(self, **link): self.state.write_text(json.dumps({"at": 9e9, "hostname": "hub", "links": [
        {"kind": "wifi", "device": "wlan0", "up": True, **link}]}))

    def test_a_cabled_hub_hands_out_what_it_was_told_and_admits_it(self):
        cfg = self.b.wifi_for_pucks()
        self.assertEqual((cfg["ssid"], cfg["pass"]), ("Upstairs", "hunter2"))
        self.assertFalse(cfg["checked"])        # nobody verified this and the panel must say so
        self.assertTrue(cfg["known"])

    def test_a_hub_on_wifi_hands_out_what_it_is_using(self):
        self.wifi(ssid="Upstairs", signal=80)
        cfg = self.b.wifi_for_pucks()
        self.assertTrue(cfg["checked"])
        self.assertEqual(cfg["pass"], "hunter2")

    def test_the_hub_having_moved_stops_the_old_password_dead(self):
        """THE BUG. The hub is on Downstairs; the only password it holds is Upstairs's.

        It used to write that password into every new puck and finish with a green tick. Now the
        name comes off the live connection, the password is not one for that name, and `known` goes
        false -- which is the existing `needs: wifi` path the panel already draws."""
        self.wifi(ssid="Downstairs", signal=70)
        cfg = self.b.wifi_for_pucks()
        self.assertEqual(cfg["ssid"], "Downstairs")
        self.assertEqual(cfg["pass"], "")
        self.assertFalse(cfg["known"])
        # ...and nothing downstream is handed a blank-but-plausible network to write.
        self.assertEqual(self.b.config()["ssid"], "")

    def test_a_puck_is_given_a_name_as_well_as_a_number(self):
        """A DHCP reshuffle used to strand every puck without anybody touching the Wi-Fi."""
        cfg = self.b.config()
        self.assertTrue(cfg["name"])
        self.assertNotEqual(cfg["name"], cfg["host"])


class MovingThemOver(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.hub.net = Network(self.hub, state=Path(self.tmp.name) / "none.json",
                               request=Path(self.tmp.name) / "network.request")
        self.b = Bridges(self.hub, cable=None, devdir=Path(self.tmp.name))
        self.b.pucks = {"aa": {"online": True, "net": "n1"}, "bb": {"online": True, "net": "n2"},
                        "cc": {"online": False, "net": "n3"}}

    def tearDown(self): self.tmp.cleanup()

    def test_everyone_is_told_and_only_the_listening_are_counted(self):
        """cc is switched off. It is still told -- the command is retained and waits on its topic --
        but it is not counted, because nothing can expect it back while somebody stands at the wall."""
        m = run(self.b.move("Downstairs", "sekrit"))
        self.assertEqual(m["total"], 2)
        topics = sorted(t for t, _, _ in self.hub.ha.published)
        self.assertEqual(topics, ["mesh/bridge/aa/cfg", "mesh/bridge/bb/cfg", "mesh/bridge/cc/cfg"])
        self.assertTrue(all(r for _, _, r in self.hub.ha.published))   # every one of them retained

    def test_the_command_is_words_and_retained(self):
        """Hex-encoded, so a network called "Flat 3 guest" needs no quoting rules; retained, so a
        puck that was switched off gets it when it comes back."""
        run(self.b.move("Flat 3 guest", "two words"))
        _, payload, retain = self.hub.ha.published[0]
        self.assertTrue(retain)
        w = payload.split()
        self.assertEqual(w[0], "wifi")
        self.assertEqual(bytes.fromhex(w[2]).decode(), "Flat 3 guest")
        self.assertEqual(bytes.fromhex(w[3]).decode(), "two words")

    def test_following_is_only_believed_from_the_broker(self):
        """An ack is proof: a puck cannot publish one from a network it never joined."""
        run(self.b.move("Downstairs", "sekrit"))
        at = int(self.b.moving["at"])
        self.b._on_mqtt({"topic": "mesh/bridge/aa/cfgack",
                         "payload": json.dumps({"at": at, "ssid": "Downstairs", "spare": "Upstairs"})})
        self.assertEqual(self.b.move_status()["followed"], [self.b.where("aa")])
        self.assertEqual(len(self.b.move_status()["waiting"]), 1)

    def test_an_ack_for_a_previous_move_is_not_this_one(self):
        run(self.b.move("Downstairs", "sekrit"))
        self.b._on_mqtt({"topic": "mesh/bridge/aa/cfgack", "payload": json.dumps({"at": 1, "ssid": "Upstairs"})})
        self.assertEqual(self.b.move_status()["followed"], [])

    def test_the_new_wifi_is_written_down_before_anybody_is_told(self):
        """A move interrupted halfway must leave the hub agreeing with the pucks it already told."""
        run(self.b.move("Downstairs", "sekrit"))
        self.assertEqual(self.hub.settings.get("wifi"), {"ssid": "Downstairs", "pass": "sekrit"})

    def test_a_house_with_nothing_listening_is_done_not_pending(self):
        self.b.pucks = {}
        m = run(self.b.move("Downstairs", "sekrit"))
        self.assertEqual((m["state"], m["total"]), ("done", 0))

    def test_a_bridge_nobody_named_is_not_given_an_invented_name(self):
        """Two pucks on one mesh cannot be told apart by the rooms they serve, so they are not."""
        self.assertEqual(self.b.where("aa"), "A bridge")

    def test_which_wifi_is_asked_for(self):
        with self.assertRaises(ValueError):
            run(self.b.move("   ", "sekrit"))


if __name__ == "__main__":
    unittest.main()
