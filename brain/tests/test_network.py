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
import asyncio, json, pathlib, tempfile, time, unittest
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


class APuckIsAlwaysOlderThanTheHub(unittest.TestCase):
    """The hub updates itself overnight; a puck is flashed once and lives behind a sofa, and the hub
    deliberately does not reflash one that still answers. So every verb added after a puck was made is
    one that puck will refuse, and the hub has to carry on.

    This is not hypothetical: `set name` shipped in firmware 0.4.0, and every 0.3.1 puck in the house
    answered `err what` and failed the whole adoption over a field it does not need."""

    class Old:
        """A 0.3.1 puck: it knows wifi, mqtt, keys, base and label, and nothing added since."""
        KNOWS = {"wifi", "mqtt", "keys", "base", "label"}

        def __init__(self): self.port, self.told = "/dev/fake", []

        def ask(self, line, wait=2.0):
            verb = line.split()[1]
            if verb not in self.KNOWS: return "err what"
            self.told.append(verb)
            return f"ok {verb}"

    def puck(self):
        import importlib.util
        src = pathlib.Path(__file__).resolve().parent.parent.parent / "brilliant" / "tools" / "puck_cable.py"
        spec = importlib.util.spec_from_file_location("tools_puck_test", src)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        old = self.Old()
        old.set = mod.Puck.set.__get__(old)      # the real method, on a puck that only knows the old verbs
        return old

    def test_an_old_puck_refusing_a_new_verb_is_not_a_failure(self):
        p = self.puck()
        self.assertFalse(p.set("name", "687562", required=False))
        self.assertEqual(p.told, [])

    def test_the_verbs_it_does_know_still_have_to_work(self):
        p = self.puck()
        self.assertTrue(p.set("wifi", "6162", "6364"))
        self.assertEqual(p.told, ["wifi"])

    def test_a_verb_it_must_understand_still_fails_loudly(self):
        """Tolerance is for version gaps, never for the Wi-Fi not going on."""
        p = self.puck()
        with self.assertRaises(RuntimeError):
            p.set("name", "687562")              # required, which is the default

    def test_a_bad_argument_is_a_fault_at_any_version(self):
        """`err what` is "never heard of it"; `err bad` is "I know it and you are wrong". Only the
        first is a version gap, and tolerating the second would hide a real misconfiguration."""
        p = self.puck()
        p.ask = lambda line, wait=2.0: "err bad"
        with self.assertRaises(RuntimeError):
            p.set("wifi", "6162", "6364", required=False)


class TheOnesThatNeverCameBack(unittest.TestCase):
    """docs/network.md, piece 6: the move's screen is read once, and the house has to remember."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.hub.net = Network(self.hub, state=Path(self.tmp.name) / "none.json",
                               request=Path(self.tmp.name) / "network.request")
        self.b = Bridges(self.hub, cable=None, devdir=Path(self.tmp.name))
        self.hub.settings.set(bridges={"aa": {"since": 1, "fw": "0.4.0"}})
        self.b.pucks = {"aa": {"online": True, "net": "n1"}}

    def tearDown(self): self.tmp.cleanup()

    def status(self, chip, payload):
        self.b._on_mqtt({"topic": f"mesh/bridge/{chip}/status", "payload": payload})

    def rec(self, chip="aa"):
        return (self.hub.settings.get("bridges") or {}).get(chip) or {}

    def test_going_quiet_is_written_down_and_coming_back_rubs_it_out(self):
        self.status("aa", "offline")
        self.assertTrue(self.rec()["gone"])
        self.status("aa", "online")
        self.assertNotIn("gone", self.rec())

    def test_the_moment_it_went_is_not_reset_by_hearing_it_again(self):
        """A brain that restarts nightly must not keep forgetting that something is missing."""
        self.status("aa", "offline")
        first = self.rec()["gone"]
        self.b.pucks["aa"]["online"] = None          # as if the brain had just started
        self.status("aa", "offline")
        self.assertEqual(self.rec()["gone"], first)

    def test_nothing_is_written_down_about_somebody_elses_puck(self):
        self.b.pucks["zz"] = {"online": True, "net": "n9"}
        self.status("zz", "offline")
        self.assertNotIn("zz", self.hub.settings.get("bridges"))

    def test_a_bridge_gone_an_hour_is_not_yet_a_job(self):
        self.status("aa", "offline")
        self.assertEqual(self.b.quiet(), [])

    def test_a_bridge_gone_a_day_is(self):
        self.status("aa", "offline")
        self.hub.settings.set(bridges={"aa": {**self.rec(), "gone": time.time() - self.b.QUIET - 1}})
        self.b.pucks["aa"]["online"] = False
        gone = self.b.quiet()
        self.assertEqual([g["chip"] for g in gone], ["aa"])
        self.assertIsNone(gone[0]["missed"])

    def test_one_that_missed_a_move_is_a_job_much_sooner(self):
        """The cause is known, so the only wait worth having is the one the self-healing needs."""
        self.b.pucks["aa"]["online"] = False
        self.hub.settings.set(bridges={"aa": {"gone": time.time() - self.b.MISSED - 1,
                                              "missed": {"ssid": "Downstairs", "at": 1}}})
        gone = self.b.quiet()
        self.assertEqual(gone[0]["missed"], "Downstairs")
        # ...and the same age with no missed move is still too soon to say anything.
        self.hub.settings.set(bridges={"aa": {"gone": time.time() - self.b.MISSED - 1}})
        self.assertEqual(self.b.quiet(), [])

    def test_a_bridge_that_is_online_is_never_a_job(self):
        self.hub.settings.set(bridges={"aa": {"gone": 1}})
        self.b.pucks["aa"]["online"] = True
        self.assertEqual(self.b.quiet(), [])

    def test_the_ones_that_did_not_follow_are_remembered(self):
        """Without this the house forgets by morning that it moved without two of its bridges."""
        self.b.pucks = {"aa": {"online": True, "net": "n1"}}
        run(self.b.move("Downstairs", "sekrit"))
        self.b.MOVE_WAIT, self.b.MOVE_SETTLE = 0, 0
        run(self.b._move_watch(self.b.moving["at"]))
        self.assertEqual(self.rec()["missed"]["ssid"], "Downstairs")

    def test_forgetting_one_clears_the_topics_that_would_bring_it_back(self):
        """Retained topics outlive the puck by design. Left behind, a bridge forgotten on Monday is
        back in the list on Tuesday with nothing a household could do about it."""
        run(self.b.forget("aa"))
        self.assertNotIn("aa", self.hub.settings.get("bridges"))
        self.assertNotIn("aa", self.b.pucks)
        cleared = {t.split("/")[-1] for t, pay, retain in self.hub.ha.published if pay == "" and retain}
        self.assertTrue({"status", "cfg", "cfgack"} <= cleared)

    def test_forgetting_one_the_hub_never_knew_says_so(self):
        with self.assertRaises(ValueError):
            run(self.b.forget("zz"))

    def test_a_room_is_only_claimed_when_one_puck_carries_that_mesh(self):
        self.b.pucks["bb"] = {"online": True, "net": "n1"}
        self.assertIsNone(self.b.room_of("aa"))
        self.assertEqual(self.b.where("aa"), "A bridge")


if __name__ == "__main__":
    unittest.main()
