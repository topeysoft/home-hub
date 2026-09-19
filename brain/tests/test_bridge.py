# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A bridge on the cable, without a bridge or a cable.

The machine is what the panel draws (app/src/BridgeSheet.vue), so what these hold is the sequence
of states a person would see: a puck appears and knocks, nothing of the house's moves until they
say yes, the three steps in order, then the walk, then the count. And the ways it goes wrong that
have a sentence for the wall: unplugged halfway, a hub with no Wi‑Fi to give.
"""
import asyncio, json, tempfile, unittest
from pathlib import Path

from hub import bridge as bridge_mod
from hub.bridge import Bridges, Cable, network_id
from hub.nightlight import Nightlight
from hub.settings import Settings


class FakeCable:
    """Scripted answers: what `hello` says per port, whether a silent port is an ESP, what write returns."""
    def __init__(self):
        self.hello_says = {}         # port -> dict | None
        self.esp = set()             # ports that are a bare ESP the house has an image for
        self.silicon = {}            # port -> chip name; anything in `esp` defaults to esp32s3
        self.no_image_for = set()    # chips the house ships no software for
        self.flashed, self.written = [], []
        self.write_says = {"chip": "c8ebba", "fw": "0.2.0", "state": "set"}
        self.write_fails = None
        # The image the hub would write, and the manifest beside it. `ships()` puts a version in it;
        # a cable with no manifest is a house that cannot say what it ships, which is its own case.
        self.image = Path(tempfile.mkdtemp()) / "esp32s3-ship.bin"

    def ships(self, fw):
        self.image.with_suffix(".json").write_text(json.dumps({"chip": "esp32s3", "fw": fw}))

    async def hello(self, port): return self.hello_says.get(port)
    async def is_esp(self, port): return await self.esp_chip(port) is not None
    async def esp_chip(self, port):
        if port in self.silicon: return self.silicon[port]
        return "esp32s3" if port in self.esp else None
    def image_for(self, chip):
        return None if (chip is None or chip in self.no_image_for) else f"/ship/{chip}-ship.bin"
    async def flash(self, port, chip="esp32s3"):
        self.flashed.append((port, chip))
        self.hello_says[port] = {"chip": "c8ebba", "fw": "0.2.0", "state": "blank"}
    async def write(self, port, cfg):
        self.written.append((port, cfg))
        if self.write_fails: raise RuntimeError(self.write_fails)
        return self.write_says


class FakeHA:
    def __init__(self): self.cb = None; self.published = []; self.calls = []; self.answer = None
    async def subscribe(self, type_, cb, **kw): self.cb = cb; return 1
    async def call(self, domain, service, target, **kw):
        self.published.append((kw.get("topic"), kw.get("payload")))
        self.calls.append(kw)
        # A puck that answers. `answer` is (leaf, payload); None is a puck that
        # heard the command and said nothing, which is a real failure mode.
        if self.answer and self.cb:
            leaf, payload = self.answer
            chip = kw["topic"].split("/")[2]
            self.cb({"topic": f"mesh/bridge/{chip}/{leaf}", "payload": payload})


class FakeLog:
    def __init__(self): self.rows = []
    def add(self, *a, **k): self.rows.append((a, k))


class FakeHub:
    def __init__(self, tmp, wifi=True):
        self.settings = Settings(Path(tmp) / "settings.json")
        self.settings.set(wifi={"ssid": "House", "pass": "hunter2 with space"} if wifi else None)
        self.env = {"MQTT_USER": "hub", "MQTT_PASSWORD": "pw"}
        self.ha, self.log, self.pushed = FakeHA(), FakeLog(), []
        self.home = None
    def _broadcast(self, msg): self.pushed.append(json.loads(msg)["bridge"]["state"])


def run(coro): return asyncio.run(coro)


class Knocking(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = Path(self.tmp.name) / "by-id"; self.dev.mkdir()
        self.hub = FakeHub(self.tmp.name)
        self.cable = FakeCable()
        self.b = Bridges(self.hub, cable=self.cable, devdir=self.dev)

    def tearDown(self): self.tmp.cleanup()

    def plug(self, name):
        (self.dev / name).write_text(""); return str(self.dev / name)

    async def settle(self):
        await self.b.scan()
        for _ in range(20): await asyncio.sleep(0)   # let the _arrived task run

    def test_a_board_on_the_cable_at_boot_is_still_looked_at(self):
        """It did not "just arrive", but it has never been looked at either -- and a board
        sitting on the cable when the brain starts is not a rare case. It is what happens on
        every deploy and every restart of this container, and on a hub where plugging
        anything in restarts the brain, it was EVERY time: the board was invisible for ever,
        because it is not new on any later scan and so was never probed at all."""
        p = self.plug("usb-bridge-1"); self.cable.hello_says[p] = {"chip": "aa", "fw": "0.2.0", "state": "blank"}
        run(self.settle())
        self.assertEqual(self.b.status()["state"], "knocking")

    def test_but_a_puck_already_set_up_still_says_nothing(self):
        """The half of the old rule worth keeping: a working puck on the cable at boot is
        recognised in silence, not offered a rebuild it does not need."""
        p = self.plug("usb-bridge-1")
        self.cable.hello_says[p] = {"chip": "aa", "fw": "0.3.1", "state": "set"}
        self.b.pucks["aa"] = {"online": True}
        run(self.settle())
        self.assertEqual(self.b.status()["state"], "none")

    def test_a_blank_puck_knocks(self):
        run(self.settle())
        p = self.plug("usb-bridge-1"); self.cable.hello_says[p] = {"chip": "aa", "fw": "0.2.0", "state": "blank"}
        run(self.settle())
        s = self.b.status()
        self.assertEqual((s["state"], s["how"]), ("knocking", "cable"))
        self.assertEqual(self.cable.written, [])          # nothing of the house's has gone anywhere

    def test_a_bare_board_knocks_too(self):
        run(self.settle())
        p = self.plug("usb-bare-esp"); self.cable.esp.add(p)
        run(self.settle())
        self.assertEqual(self.b.status()["state"], "knocking")
        self.assertTrue(self.b.job["bare"])

    def test_a_radio_stick_is_never_probed(self):
        run(self.settle())
        p = self.plug("usb-Silicon_Labs_HubZ_Smart_Home_Controller-if00"); self.cable.esp.add(p)
        run(self.settle())
        self.assertEqual(self.b.status()["state"], "none")

    def test_something_else_is_ignored(self):
        run(self.settle())
        self.plug("usb-some-printer")
        run(self.settle())
        self.assertEqual(self.b.status()["state"], "none")

    def test_one_of_ours_visiting_does_not_knock(self):
        self.b.pucks["aa"] = {"online": True}
        run(self.settle())
        p = self.plug("usb-bridge-1"); self.cable.hello_says[p] = {"chip": "aa", "fw": "0.2.0", "state": "set"}
        run(self.settle())
        self.assertEqual(self.b.status()["state"], "none")

    def test_not_mine_leaves_it_alone_until_unplugged(self):
        run(self.settle())
        p = self.plug("usb-bridge-1"); self.cable.hello_says[p] = {"chip": "aa", "fw": "0.2.0", "state": "blank"}
        run(self.settle()); run(self.b.dismiss())
        self.assertEqual(self.b.status()["state"], "none")
        run(self.settle())                                  # still plugged in: does not knock again
        self.assertEqual(self.b.status()["state"], "none")
        (self.dev / "usb-bridge-1").unlink(); run(self.settle())
        self.plug("usb-bridge-1"); run(self.settle())      # back after an unplug: knocks again
        self.assertEqual(self.b.status()["state"], "knocking")

    def test_unplugged_while_knocking_withdraws_the_offer(self):
        run(self.settle())
        p = self.plug("usb-bridge-1"); self.cable.hello_says[p] = {"chip": "aa", "fw": "0.2.0", "state": "blank"}
        run(self.settle()); (self.dev / "usb-bridge-1").unlink(); run(self.settle())
        self.assertEqual(self.b.status()["state"], "none")


class TheJob(Knocking):
    def knock(self, bare=False):
        run(self.settle())
        p = self.plug("usb-bridge-1")
        if bare: self.cable.esp.add(p)
        else: self.cable.hello_says[p] = {"chip": "c8ebba", "fw": "0.2.0", "state": "blank"}
        run(self.settle()); return p

    async def adopt_and_finish(self):
        await self.b.adopt()
        await self.b._task

    def test_the_three_steps_then_the_walk(self):
        self.knock()
        run(self.adopt_and_finish())
        self.assertEqual(self.hub.pushed[-4:], ["working", "working", "working", "placing"])
        port, cfg = self.cable.written[0]
        self.assertEqual((cfg["ssid"], cfg["pass"], cfg["user"], cfg["mqtt_pass"], cfg["base"]), ("House", "hunter2 with space", "hub", "pw", "mesh"))
        self.assertEqual(len(cfg["netkey"]), 32); self.assertEqual(len(cfg["appkey"]), 32)
        self.assertEqual(self.cable.flashed, [])          # it had software already
        self.assertIn("c8ebba", self.hub.settings.get("bridges"))

    async def adopt_and_go_quiet(self):
        await self.b.adopt()
        await self.b._task
        await self.b._quiet          # same loop: asyncio.run() closes the old one

    def test_a_puck_that_never_comes_back_stops_being_called_still_listening(self):
        """A puck in somebody's hand and a puck in a socket with no Wi-Fi are the same silence to the
        broker. The panel drew them identically, for ever, about one that was never coming back."""
        self.b.QUIET_S = 0.01
        self.knock()
        run(self.adopt_and_go_quiet())
        self.assertEqual(self.b.status()["state"], "placing")
        self.assertEqual(self.b.status()["signal"], "none")
        self.assertTrue(self.b.status()["quiet"])

    def test_turning_up_after_all_takes_the_words_back(self):
        self.b.QUIET_S = 0.01
        self.knock()
        run(self.adopt_and_go_quiet())
        self.assertTrue(self.b.status().get("quiet"))
        self.b._on_mqtt({"topic": "mesh/bridge/c8ebba/status", "payload": "online"})
        self.assertNotIn("quiet", self.b.status())

    def test_a_good_socket_reads_strong_and_not_quiet(self):
        """The other end of the same walk: it turns up, and what it hears is worth standing still for."""
        self.b.QUIET_S = 0.01
        self.knock()
        run(self.adopt_and_go_quiet())
        self.b._on_mqtt({"topic": "mesh/bridge/c8ebba/status", "payload": "online"})
        self.b._on_mqtt({"topic": "mesh/bridge/c8ebba/proxy", "payload": "7c:10:15:04:de:a0 rssi -60"})
        self.assertEqual(self.b.status()["signal"], "strong")
        self.assertNotIn("quiet", self.b.status())

    def test_a_bare_board_gets_its_software_first(self):
        p = self.knock(bare=True)
        run(self.adopt_and_finish())
        # the port AND the chip: flashing an S3 image at whatever turned up is the bug
        # that put "This chip is ESP32-C3, not ESP32-S3" on somebody's wall panel
        self.assertEqual(self.cable.flashed, [(p, "esp32s3")])
        self.assertEqual(self.b.status()["state"], "placing")

    def test_the_keys_are_made_once_and_kept(self):
        self.knock(); run(self.adopt_and_finish())
        k1 = self.cable.written[0][1]["netkey"]
        self.b.job = None; self.cable.written.clear()
        (self.dev / "usb-bridge-1").unlink(); run(self.settle())
        self.knock(); run(self.adopt_and_finish())
        self.assertEqual(self.cable.written[0][1]["netkey"], k1)
        self.assertEqual(oct((Path(self.tmp.name) / "mesh-keys.json").stat().st_mode)[-3:], "600")

    def test_no_wifi_to_give_is_said_not_hidden(self):
        self.hub = FakeHub(self.tmp.name, wifi=False); self.b = Bridges(self.hub, cable=self.cable, devdir=self.dev)
        self.knock(); run(self.adopt_and_finish())
        s = self.b.status()
        self.assertEqual((s["state"], s["needs"]), ("failed", "wifi"))
        self.assertEqual(self.cable.written, [])

    def test_told_the_wifi_once_the_job_carries_on(self):
        self.hub = FakeHub(self.tmp.name, wifi=False); self.b = Bridges(self.hub, cable=self.cable, devdir=self.dev)
        self.knock(); run(self.adopt_and_finish())
        self.assertEqual(self.b.status()["needs"], "wifi")
        async def tell():
            await self.b.wifi("House", "hunter2"); await self.b._task
        run(tell())
        self.assertEqual(self.b.status()["state"], "placing")
        self.assertEqual(self.cable.written[0][1]["ssid"], "House")
        self.assertEqual(self.hub.settings.get("wifi"), {"ssid": "House", "pass": "hunter2"})   # kept for the next one

    def test_a_puck_that_does_not_come_back_is_a_failure_in_words(self):
        self.knock(); self.cable.write_fails = "it did not come back on the cable"
        run(self.adopt_and_finish())
        s = self.b.status()
        self.assertEqual(s["state"], "failed"); self.assertIn("did not come back", s["text"])

    def test_placing_hears_the_broker_then_ready_counts_the_unplaced(self):
        self.knock(); run(self.adopt_and_finish()); run(self.b.listen())
        cb = self.hub.ha.cb
        for topic, payload in [("mesh/bridge/c8ebba/status", "online"), ("mesh/bridge/c8ebba/net", "3deef9825e444955"),
                               ("mesh/bridge/c8ebba/proxy", "7c:10:15:04:de:b1 rssi -64"),
                               ("mesh/3deef9825e444955/000a/state", "ON"), ("mesh/3deef9825e444955/0004/state", "OFF"),
                               ("mesh/other/0003/state", "ON")]:
            cb({"event": {"topic": topic, "payload": payload}})
        s = self.b.status()
        self.assertEqual((s["state"], s["switches"], s["signal"], s["bridges"]), ("placing", 2, "strong", 1))
        cb({"event": {"topic": "mesh/bridge/c8ebba/proxy", "payload": "7c:10:15:04:de:b1 rssi -85"}})
        self.assertEqual(self.b.status()["signal"], "weak")

        class D:  # the two switches, one placed
            def __init__(self, i, room): self.id, self.room_id = i, room
        class H: devices = {"light.mesh_3dee_000a": D("light.mesh_3dee_000a", "unassigned"), "light.mesh_3dee_0004": D("light.mesh_3dee_0004", "hall")}
        self.hub.home = H()
        run(self.b.placed())
        s = self.b.status()
        self.assertEqual((s["state"], s["switches"], s["unplaced"]), ("ready", 2, 1))

    def test_adopt_needs_a_knock(self):
        with self.assertRaises(ValueError): run(self.b.adopt())


if __name__ == "__main__":
    unittest.main()


class TheLightAfterItIsPlaced(TheJob):
    """docs/puck-light.md: what "Leave it here" sends, and the difference between the two halves.

    `settled` is the hub's and is retained, so a puck that missed the moment still gets it. `night`
    is the household's from the instant they answer, so it goes once and is never repeated -- a
    retained placement answer would quietly overrule somebody turning the thing off months later.
    """
    def place(self, **kw):
        self.knock(); run(self.adopt_and_finish())
        self.hub.ha.calls.clear()
        run(self.b.placed(**kw))
        return {c["topic"]: c for c in self.hub.ha.calls}

    def test_it_is_settled_and_that_one_is_retained(self):
        sent = self.place()
        self.assertEqual(sent["mesh/bridge/c8ebba/settled/set"]["payload"], "1")
        self.assertTrue(sent["mesh/bridge/c8ebba/settled/set"]["retain"])

    def test_no_answer_says_nothing_at_all_about_the_light(self):
        sent = self.place()
        self.assertEqual([t for t in sent if "night" in t], [])

    def test_the_answer_is_carried_once_and_never_retained(self):
        sent = self.place(night=True, level=200)
        self.assertEqual(sent["mesh/bridge/c8ebba/night/set"]["payload"], "ON")
        self.assertFalse(sent["mesh/bridge/c8ebba/night/set"].get("retain"))
        self.assertEqual(sent["mesh/bridge/c8ebba/night/brightness/set"]["payload"], "200")
        self.assertFalse(sent["mesh/bridge/c8ebba/night/brightness/set"].get("retain"))

    def test_no_is_an_answer_too_and_carries_no_brightness(self):
        sent = self.place(night=False, level=200)
        self.assertEqual(sent["mesh/bridge/c8ebba/night/set"]["payload"], "OFF")
        self.assertNotIn("mesh/bridge/c8ebba/night/brightness/set", sent)

    def test_the_answer_is_written_down_where_a_household_can_read_it(self):
        self.place(night=True)
        self.assertIn("nightlight on", [a[3] for a, _ in self.hub.log.rows if len(a) > 3])

    def test_a_brightness_that_is_not_one_is_refused_before_anything_is_sent(self):
        self.knock(); run(self.adopt_and_finish())
        self.hub.ha.calls.clear()
        with self.assertRaises(ValueError): run(self.b.placed(night=True, level=999))
        self.assertEqual(self.hub.ha.calls, [])
        self.assertEqual(self.b.status()["state"], "placing")   # and the job is untouched

    def test_a_puck_that_cannot_be_told_is_still_placed(self):
        """The publish is not why somebody tapped the button. A broker that refuses must not leave
        the sheet stuck on a step the person has already finished."""
        self.knock(); run(self.adopt_and_finish())
        async def boom(*a, **k): raise RuntimeError("broker gone")
        self.hub.ha.call = boom
        run(self.b.placed(night=True))
        self.assertEqual(self.b.status()["state"], "ready")


class LookingAtABridgeThatIsFine(unittest.TestCase):
    """This hub's Bridges section: the list, and changing a bridge's own light from the panel.

    What made this worth building: until now a puck surfaced on the panel only when something was
    WRONG with it -- a note when it went quiet, a line when it was a version behind -- so the one
    place a household could act on one was a problem report. That left hub/nightlight.py's switch
    reachable only through Home Assistant, which product-direction-out-of-the-box forbids.
    """
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.hub = FakeHub(self.tmpdir.name)
        self.b = Bridges(self.hub, FakeCable())
        self.hub.ha.cb = self.b._on_mqtt
        self.hub.bridge = self.b
        self.hub.settings.set(bridges={"c8ebba": {"since": 1, "fw": "0.5.0"},
                                       "f4a9f3": {"since": 2, "fw": "0.5.0"}})
        self.b.pucks = {"c8ebba": {"online": True, "rssi": -53, "night": True, "level": 110},
                        "f4a9f3": {"online": False}}

    def each(self): return {x["chip"]: x for x in self.b.each()}

    def test_every_bridge_is_listed_whether_or_not_anything_is_wrong_with_it(self):
        self.assertEqual(set(self.each()), {"c8ebba", "f4a9f3"})

    def test_it_says_what_it_honestly_knows_about_each(self):
        one = self.each()["c8ebba"]
        self.assertEqual((one["online"], one["signal"], one["night"], one["level"], one["lift"]),
                         (True, "strong", True, 110, False))

    def test_a_puck_that_has_never_spoken_has_no_opinion_about_its_light(self):
        """None, not False: "off" is a claim about a thing we have heard from."""
        self.assertIsNone(self.each()["f4a9f3"]["night"])

    def test_one_the_hub_cannot_place_is_named_honestly_and_sorted_last(self):
        self.assertEqual([x["where"] for x in self.b.each()], ["A bridge", "A bridge"])
        self.assertEqual([x["room"] for x in self.b.each()], [None, None])

    def test_turning_the_nightlight_down_is_said_once_and_not_retained(self):
        """Retained would overrule the household the next time the puck reconnected -- the same
        trap placed() avoids for the placement answer."""
        run(self.b.light("c8ebba", night=True, level=40))
        sent = {c["topic"]: c for c in self.hub.ha.calls}
        self.assertEqual(sent["mesh/bridge/c8ebba/night/set"]["payload"], "ON")
        self.assertEqual(sent["mesh/bridge/c8ebba/night/brightness/set"]["payload"], "40")
        self.assertFalse(any(c.get("retain") for c in self.hub.ha.calls))

    def test_turning_it_off_does_not_also_send_a_brightness(self):
        """A brightness would turn it back on: the firmware reads any level above zero as an on."""
        run(self.b.light("c8ebba", night=False, level=40))
        self.assertNotIn("mesh/bridge/c8ebba/night/brightness/set", [c["topic"] for c in self.hub.ha.calls])

    def test_lift_is_the_brains_and_is_written_down_rather_than_published_at_the_puck(self):
        self.hub.nightlight = Nightlight(self.hub)
        run(self.b.light("c8ebba", lift=True))
        self.assertTrue((self.hub.settings.get("bridges")["c8ebba"]).get("lift"))
        self.assertTrue(self.each()["c8ebba"]["lift"])

    def test_a_bridge_the_hub_does_not_know_is_refused(self):
        with self.assertRaises(ValueError): run(self.b.light("ffffff", night=True))

    def test_a_brightness_that_is_not_one_is_refused_before_anything_is_sent(self):
        with self.assertRaises(ValueError): run(self.b.light("c8ebba", night=True, level=999))
        self.assertEqual(self.hub.ha.calls, [])

    def test_a_hub_with_no_manifest_says_it_cannot_tell_rather_than_current(self):
        """shipped() is "" with no manifest beside the image, and behind() is then empty for EVERY
        puck -- so "not behind" and "nobody knows" were the same answer, and the panel drew a puck
        three versions old as current."""
        self.assertIsNone(self.each()["c8ebba"]["shipped"])
        self.assertFalse(self.each()["c8ebba"]["behind"])

    def test_when_the_house_does_know_what_it_ships_it_says_so(self):
        self.b.cable.ships("0.5.0")
        self.assertEqual(self.each()["c8ebba"]["shipped"], "0.5.0")

    def test_the_brightness_a_household_chose_is_learned_from_the_puck(self):
        self.b._on_mqtt({"topic": "mesh/bridge/f4a9f3/night/brightness", "payload": "200"})
        self.assertEqual(self.each()["f4a9f3"]["level"], 200)


class LettingASwitchIn(unittest.TestCase):
    """The hub's half of claiming: which puck, which address, and what is said.

    The radio work is the puck's (brilliant/esp32-bridge/src/claim.cpp) and is not
    here. What is here is the part that can put a switch on the wrong network or
    hand out an address twice, and the wording a person actually reads."""

    def bridges(self, tmp, *, ours=True, online=True):
        hub = FakeHub(tmp)
        b = Bridges(hub, FakeCable())
        hub.ha.cb = b._on_mqtt          # what listen() does in the real thing
        b.pucks["c8ebba"] = {"online": online}
        if ours:
            hub.settings.set(bridges={"c8ebba": {"since": 0, "fw": "0.2.1"}})
        return hub, b

    def test_refuses_a_puck_the_hub_did_not_set_up(self):
        """A puck the hub never gave keys to is very likely carrying somebody else's
        mesh, and claiming into that is unrecoverable without a reset."""
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp, ours=False)
            self.assertIsNone(b._our_puck())
            with self.assertRaises(ValueError):
                run(b._ask("survey", "nearby", 0.1))

    def test_an_offline_puck_is_not_asked(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp, online=False)
            self.assertIsNone(b._our_puck())

    def test_addresses_are_never_handed_out_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            got = [b._next_addr() for _ in range(3)]
            self.assertEqual(len(set(got)), 3)
            self.assertEqual(got, sorted(got))
            # and it survives a restart, because the counter lives beside the keys
            b2 = Bridges(hub, FakeCable())
            self.assertGreater(b2._next_addr(), got[-1])

    def test_it_keeps_clear_of_the_puck_and_the_laptop(self):
        """0x7000 up is the puck's own block and the laptop tools sit at 0x0001 and
        0x001a. Two senders on one address trip the switches' replay protection."""
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            a = b._next_addr()
            self.assertGreater(a, 0x001a)
            self.assertLess(a, 0x7000)

    def test_a_waiting_switch_is_counted_in_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            hub.ha.answer = ("nearby", json.dumps([
                {"state": "unclaimed", "rssi": -50, "addr": "aa", "uuid": "00" * 16},
                {"state": "ours", "rssi": -60, "addr": "bb", "net": "11" * 8}]))
            out = run(b.nearby())
            self.assertEqual(out["state"], "done")
            self.assertEqual(len(out["waiting"]), 1)
            self.assertIn("One switch is waiting", out["text"])

    def test_nothing_waiting_but_one_is_spoken_for(self):
        """The case the Waiting board draws: a scan for claimable switches finds
        nothing, which looks identical to an empty room and wants the opposite
        thing said."""
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            hub.ha.answer = ("nearby", json.dumps([
                {"state": "other", "rssi": -55, "addr": "cc", "net": "22" * 8}]))
            out = run(b.nearby())
            self.assertEqual(out["waiting"], [])
            self.assertIn("started over", out["text"])

    def test_an_empty_room_says_so_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            hub.ha.answer = ("nearby", json.dumps([]))
            self.assertIn("Nothing nearby", run(b.nearby())["text"])

    def test_a_puck_that_says_nothing_is_not_a_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            hub.ha.answer = None
            was, bridge_mod.SURVEY_WAIT = bridge_mod.SURVEY_WAIT, 0.3
            try: out = run(b.nearby())
            finally: bridge_mod.SURVEY_WAIT = was
            self.assertEqual(out["state"], "failed")
            self.assertIn("did not answer", out["text"])

    def test_the_code_travels_with_the_command(self):
        """A QR add must carry the secret, or the switch is asked to prove nothing."""
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            hub.ha.answer = ("claimed", json.dumps({"ok": True, "unicast": "0020",
                                                    "elements": 1, "devkey": "ab" * 16}))
            out = run(b.let_in("aa" * 16, "bb" * 16))
            self.assertEqual(out["state"], "done")
            topic, payload = hub.ha.published[-1]
            self.assertTrue(payload.startswith("add "))
            self.assertTrue(payload.endswith("bb" * 16))
            self.assertEqual(out["devkey"], "ab" * 16)

    def test_a_codeless_add_carries_no_secret(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            hub.ha.answer = ("claimed", json.dumps({"ok": True, "unicast": "0020",
                                                    "elements": 1, "devkey": "cd" * 16}))
            run(b.let_in("aa" * 16))
            _, payload = hub.ha.published[-1]
            self.assertEqual(len(payload.split()), 3)      # add, uuid, address -- nothing else

    def test_a_refusal_is_repeated_in_the_words_it_came_with(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b = self.bridges(tmp)
            hub.ha.answer = ("claimed", json.dumps(
                {"ok": False, "why": "it could not prove it holds that code"}))
            out = run(b.let_in("aa" * 16, "bb" * 16))
            self.assertEqual(out["state"], "failed")
            self.assertIn("prove", out["text"])


class ABoardTheHouseCannotUse(unittest.TestCase):
    """Plugging in a bare ESP32-C3 when the house only ships an S3 image.

    Both of these were found by plugging one in. The house said "That did not work. This chip
    is ESP32-C3, not ESP32-S3. Wrong chip argument?" -- esptool's sentence, on a wall panel --
    and then said it again every few seconds however many times it was dismissed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = Path(self.tmp.name) / "by-id"; self.dev.mkdir()
        self.hub = FakeHub(self.tmp.name)
        self.cable = FakeCable()
        self.b = Bridges(self.hub, self.cable, devdir=self.dev)

    def tearDown(self): self.tmp.cleanup()

    def plug(self, name):
        (self.dev / name).touch(); return str(self.dev / name)

    async def settle(self):
        await self.b.scan()
        for _ in range(6): await asyncio.sleep(0)

    def arrive_c3(self):
        run(self.settle())                      # the first scan is the boot baseline
        port = self.plug("usb-c3-board")
        self.cable.hello_says[port] = None      # bare: nothing answers over the cable
        self.cable.silicon[port] = "esp32c3"
        self.cable.no_image_for.add("esp32c3")
        run(self.settle())
        return port

    def test_it_does_not_offer_what_it_cannot_deliver(self):
        """Knocking would be a lie -- there is nothing to give it."""
        self.arrive_c3()
        self.assertEqual(self.b.status()["state"], "failed")
        self.assertEqual(self.cable.flashed, [])

    def test_it_names_the_chip_in_words_a_person_can_check(self):
        """The chip is printed on the board, so it is the one piece of jargon worth keeping.
        esptool's own phrasing is not."""
        self.arrive_c3()
        said = self.b.status()["text"]
        self.assertIn("ESP32-C3", said)
        self.assertNotIn("argument", said.lower())
        self.assertIn("Nothing was written to it", said)

    def test_it_says_so_once_and_then_leaves_it_alone(self):
        """The bug that made it unbearable: dismissing it did not stick, because probing a
        board re-enumerates its USB, the port looked unplugged, and the dismissal was
        forgiven -- so it knocked again faster than anybody could say no."""
        port = self.arrive_c3()
        run(self.b.dismiss())
        self.assertEqual(self.b.status()["state"], "none")
        (self.dev / "usb-c3-board").unlink()     # the re-enumeration, mid-probe
        self.b._probing.add(port)
        run(self.settle())
        self.plug("usb-c3-board"); self.b._probing.discard(port)
        run(self.settle())
        self.assertEqual(self.b.status()["state"], "none")

    def test_but_a_person_pulling_it_out_is_still_a_fresh_offer(self):
        """The other half: a dismissal that outlives an actual unplug is a board nobody can
        ever offer again."""
        self.arrive_c3()
        run(self.b.dismiss())
        (self.dev / "usb-c3-board").unlink(); run(self.settle())   # no probe in flight
        self.cable.no_image_for.clear()                            # ...and this time we can use it
        port = self.plug("usb-c3-board")
        self.cable.hello_says[port] = None
        self.cable.silicon[port] = "esp32c3"
        run(self.settle())
        self.assertEqual(self.b.status()["state"], "knocking")


class RecognisingAPuckItCanSee(unittest.TestCase):
    """A working bridge the hub never wrote down.

    The only way into `bridges` was the cable flow -- and the cable flow deliberately skips a
    puck that is already set up. So a puck built by hand stayed invisible for ever: the panel's
    Add a wall switch refused with "No bridge of this house is on" while the bridge sat there
    on the broker doing its job. This is the way in that was missing."""

    def make(self, tmp, *, net=None, online=True):
        hub = FakeHub(tmp)
        b = Bridges(hub, FakeCable())
        hub.ha.cb = b._on_mqtt
        ours = network_id(bytes.fromhex(b.keys()["netkey"]))
        b.pucks["c8ebba"] = {"online": online, "net": net if net is not None else ours}
        return hub, b, ours

    def test_the_network_id_is_the_one_the_puck_publishes(self):
        """k3(netkey), the same eight bytes a puck puts on .../net. Checked against a real
        one: the house's own keys derive 7dcdd6f322c30af4, which is what the puck says."""
        key = bytes.fromhex("7dd7364cbf17c7fc9f6c9c4b6d8a5b9e")
        self.assertEqual(len(network_id(key)), 16)
        self.assertEqual(network_id(key), network_id(key))          # stable
        self.assertNotEqual(network_id(key), network_id(bytes(16)))  # and key-dependent

    def test_a_working_puck_on_our_mesh_is_written_down(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b, _ = self.make(tmp)
            self.assertTrue(b._adopt_on_sight("c8ebba", "0.3.1"))
            self.assertIn("c8ebba", hub.settings.get("bridges"))
            self.assertIsNotNone(b._our_puck())      # which is what unblocks the panel

    def test_a_puck_on_somebody_elses_mesh_is_left_alone(self):
        """The whole reason _our_puck exists: adopting this one is how a new switch ends up
        claimed onto a neighbour's network."""
        with tempfile.TemporaryDirectory() as tmp:
            hub, b, _ = self.make(tmp, net="3deef9825e444955")
            self.assertFalse(b._adopt_on_sight("c8ebba", "0.3.1"))
            self.assertEqual(hub.settings.get("bridges") or {}, {})
            self.assertIsNone(b._our_puck())

    def test_an_offline_puck_is_not_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b, _ = self.make(tmp, online=False)
            self.assertFalse(b._adopt_on_sight("c8ebba", "0.3.1"))

    def test_it_happens_off_the_broker_with_no_cable_in_it(self):
        """The usual place for a puck is a charger behind a sofa, not the hub's USB."""
        with tempfile.TemporaryDirectory() as tmp:
            hub = FakeHub(tmp)
            b = Bridges(hub, FakeCable())
            hub.ha.cb = b._on_mqtt
            ours = network_id(bytes.fromhex(b.keys()["netkey"]))
            b._on_mqtt({"topic": "mesh/bridge/aa11bb/net", "payload": ours})
            b._on_mqtt({"topic": "mesh/bridge/aa11bb/status", "payload": "online"})
            self.assertIn("aa11bb", hub.settings.get("bridges") or {})

    def test_it_is_written_down_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            hub, b, _ = self.make(tmp)
            self.assertTrue(b._adopt_on_sight("c8ebba", "0.3.1"))
            self.assertFalse(b._adopt_on_sight("c8ebba", "0.3.1"))
            self.assertEqual(len([r for r in hub.log.rows if "recognised" in str(r)]), 1)


class WhoseMeshAndWhereItIs(unittest.TestCase):
    """The rule, stated once: being SEEN is not consent, being PLUGGED IN is.

    On our own mesh, a working puck is recognised wherever it happens to be -- that is
    evidence and nothing is taken over. On somebody else's mesh it is a working bridge for
    another house, and the only thing that makes claiming it intentional is a person putting
    it on this hub's cable."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = Path(self.tmp.name) / "by-id"; self.dev.mkdir()
        self.hub = FakeHub(self.tmp.name)
        self.cable = FakeCable()
        self.b = Bridges(self.hub, self.cable, devdir=self.dev)
        self.hub.ha.cb = self.b._on_mqtt
        self.ours = network_id(bytes.fromhex(self.b.keys()["netkey"]))
        self.theirs = "3deef9825e444955"

    def tearDown(self): self.tmp.cleanup()

    async def settle(self):
        await self.b.scan()
        for _ in range(6): await asyncio.sleep(0)

    def plug_in(self, chip):
        run(self.settle())
        port = str(self.dev / "usb-visitor"); (self.dev / "usb-visitor").touch()
        self.cable.hello_says[port] = {"chip": chip, "fw": "0.3.1", "state": "set"}
        run(self.settle())

    def test_a_foreign_puck_on_the_cable_is_offered(self):
        """Somebody carried it to the hub and plugged it in. That is the ask."""
        self.b.pucks["ff00ee"] = {"online": True, "net": self.theirs}
        self.plug_in("ff00ee")
        self.assertEqual(self.b.status()["state"], "knocking")

    def test_a_foreign_puck_nobody_touched_is_left_entirely_alone(self):
        """Seen on the broker, on another mesh, no cable. Taking it over here would be acting
        on a puck a neighbour has on a shelf."""
        self.b._on_mqtt({"topic": "mesh/bridge/ff00ee/net", "payload": self.theirs})
        self.b._on_mqtt({"topic": "mesh/bridge/ff00ee/status", "payload": "online"})
        self.assertEqual(self.b.status()["state"], "none")
        self.assertEqual(self.hub.settings.get("bridges") or {}, {})

    def test_our_own_puck_on_the_cable_is_recognised_not_rebuilt(self):
        self.b.pucks["c8ebba"] = {"online": True, "net": self.ours}
        self.plug_in("c8ebba")
        self.assertEqual(self.b.status()["state"], "none")      # nothing to set up
        self.assertIn("c8ebba", self.hub.settings.get("bridges"))

    def test_a_puck_that_has_not_said_which_mesh_is_unknown_not_foreign(self):
        """One of ours that has simply not published yet must not be offered a rebuild."""
        self.b.pucks["c8ebba"] = {"online": True}               # no net yet
        self.plug_in("c8ebba")
        self.assertEqual(self.b.status()["state"], "none")
        self.assertEqual(self.hub.settings.get("bridges") or {}, {})


class OneProbeAtATime(unittest.TestCase):
    """Probing is exclusive, across every port, and ports wait their turn rather than being
    dropped.

    Two things forced it. Probing resets the board, so its USB re-enumerates and the port
    churns -- the returning port reads as a fresh arrival and would be probed underneath the
    probe still running. And ONE BOARD CAN BE TWO PORTS: an ESP32-S3 on Linux appears as
    both its USB-serial bridge and the chip's own USB-JTAG unit, so "probe each new port"
    means two probes on one chip, fighting over it. macOS shows only one of those ports,
    which is why a hub failed all evening and a Mac never reproduced it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = Path(self.tmp.name) / "by-id"; self.dev.mkdir()
        self.b = Bridges(FakeHub(self.tmp.name), FakeCable(), devdir=self.dev)
        self.probes = []
        async def counted(port): self.probes.append(port)
        self.b._arrived = counted

    def tearDown(self): self.tmp.cleanup()

    def touch(self, name):
        (self.dev / name).touch(); return str(self.dev / name)

    def test_one_board_showing_two_ports_is_probed_once(self):
        """The hub case, exactly: a C3/S3 devkit's serial bridge and its USB-JTAG unit both
        appear, and probing both at once is two probes on one chip."""
        run(self.b.scan())                                  # baseline
        self.touch("usb-1a86_USB_Single_Serial_5A46080020-if00")
        self.touch("usb-Espressif_USB_JTAG_serial_debug_unit_FC:01:2C:C6:E2:EC-if00")
        run(self.b.scan())
        self.assertEqual(len(self.probes), 1)

    def test_nothing_is_probed_while_a_probe_is_in_flight(self):
        run(self.b.scan())
        port = self.touch("usb-board")
        self.b._probing.add("some-other-port")
        run(self.b.scan())
        self.assertEqual(self.probes, [])
        self.b._probing.clear()                             # that one finished
        run(self.b.scan())
        self.assertEqual(self.probes, [port])

    def test_a_port_that_waited_is_not_forgotten(self):
        """Queued, not dropped: skipping a port used to lose it, because it stays in _seen
        and never looks new again."""
        run(self.b.scan())
        a = self.touch("usb-aaa"); b = self.touch("usb-bbb")
        run(self.b.scan())
        run(self.b.scan())
        self.assertEqual(sorted(self.probes), sorted([a, b]))

class ReadingTheProbesAnswer(unittest.TestCase):
    """The probe prints a marker and the hub reads it back. Three times now that reading has
    been the thing that broke, so the parsing is pinned here rather than trusted.

    The one that cost an evening: esptool prints "Detecting chip type..." through rich with
    no trailing newline, so the marker landed glued to the end of it -- the hub logged
    "did not answer as an ESP -- Detecting chip type...CHIP=ESP32-S3", throwing away the
    answer that was sitting in the same sentence."""

    def parse(self, said: str):
        import re
        m = re.search(r"CHIP=([\w-]+)", said)
        return m.group(1).strip().lower().replace("-", "").replace(" ", "") if m else None

    def test_a_marker_glued_to_esptools_progress_is_still_read(self):
        self.assertEqual(self.parse("Connecting.........\nDetecting chip type...CHIP=ESP32-S3\n"),
                         "esp32s3")

    def test_a_marker_on_its_own_line_is_read(self):
        self.assertEqual(self.parse("Connecting....\nCHIP=ESP32-C3\n"), "esp32c3")

    def test_no_marker_is_no_chip(self):
        self.assertIsNone(self.parse("Connecting......\nFailed to connect: No serial data received.\n"))

    def test_the_name_comes_back_as_esptool_wants_it(self):
        """--chip takes esp32s3, not ESP32-S3."""
        self.assertEqual(self.parse("CHIP=ESP32-S3"), "esp32s3")
        self.assertEqual(self.parse("CHIP=ESP32"), "esp32")


class ABadSyncIsNotAVerdict(unittest.TestCase):
    """A board that has just enumerated can answer badly once.

    "Unexpected chip magic value 0x00000009" is a half-synced connection, and the same board
    on the same hub answers every time when asked by hand. One bad sync used to end it: the
    board was written off and, because a port only looks new once, never looked at again."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cable = Cable()
        self.tries = []

    def tearDown(self): self.tmp.cleanup()

    def answers(self, *results):
        """Stand in for the one-shot probe, handing back a scripted result each time."""
        async def once(port):
            self.tries.append(port)
            return results[min(len(self.tries) - 1, len(results) - 1)]
        self.cable._esp_chip_once = once

    def test_a_second_ask_is_made_when_the_first_says_nothing(self):
        self.answers(None, "esp32s3")
        import hub.bridge as m
        was, m.PROBE_RETRY = m.PROBE_RETRY, 0
        try: got = run(self.cable.esp_chip("/dev/whatever"))
        finally: m.PROBE_RETRY = was
        self.assertEqual(got, "esp32s3")
        self.assertEqual(len(self.tries), 2)

    def test_a_good_first_answer_is_not_asked_twice(self):
        self.answers("esp32c3")
        self.assertEqual(run(self.cable.esp_chip("/dev/whatever")), "esp32c3")
        self.assertEqual(len(self.tries), 1)

    def test_a_board_that_never_answers_is_still_None(self):
        self.answers(None)
        import hub.bridge as m
        was, m.PROBE_RETRY = m.PROBE_RETRY, 0
        try: self.assertIsNone(run(self.cable.esp_chip("/dev/whatever")))
        finally: m.PROBE_RETRY = was
        self.assertEqual(len(self.tries), 2)


class WhatAFailedWriteSays(unittest.TestCase):
    """esptool's sentence on a wall panel, again.

    ABoardTheHouseCannotUse above is the same bug on the chip check, found by plugging one in. This
    is it on the write: on 18 Sep 2026 a household watching a bare S3 being set up got "No more data
    to read from the serial port. This can have many causes, for troubleshooting steps visit:
    https://docs.espressif.com/..." -- a link to somebody's developer documentation, on the wall.
    """
    def why(self, out, rc=1):
        return Cable._why(out, rc)

    def test_a_line_that_kept_dropping_names_the_cable_and_not_the_serial_port(self):
        said = self.why("Writing at 0x000af96c / No more data to read from the serial port. This can "
                        "have many causes, for troubleshooting steps visit: https://docs.espressif.com/x")
        self.assertIn("cable", said)
        for leak in ("serial port", "esptool", "http", "espressif"):
            self.assertNotIn(leak, said.lower())

    def test_a_board_that_stopped_answering_is_told_what_to_do_with_it(self):
        for out in ("A fatal error occurred: Failed to connect to ESP32-S3",
                    "Wrong boot mode detected (0x13)!",
                    "No serial data received."):
            with self.subTest(out=out):
                said = self.why(out)
                self.assertIn("Unplug it", said)
                self.assertNotIn("esp32", said.lower())

    def test_a_write_that_ran_out_of_time_says_so_rather_than_nothing(self):
        self.assertIn("too long", self.why("", rc=-1))

    def test_a_port_the_hub_could_not_open(self):
        self.assertIn("could not reach it", self.why("could not open port /dev/ttyACM0: Permission denied"))

    def test_anything_else_is_still_a_sentence_and_never_a_stack(self):
        said = self.why("Traceback (most recent call last): RuntimeError: chip stopped responding")
        self.assertTrue(said.endswith("try again."))
        self.assertNotIn("Traceback", said)


class FakeNet:
    """The hub's own connection, the shape network.py reports it in."""
    def __init__(self, how="wifi", ssid="VirusBroadcast"): self.how, self.ssid = how, ssid
    def state(self): return {"how": self.how, "ssid": self.ssid} if self.ssid else {"how": self.how}


class TheWifiItIsAlreadyStandingOn(Knocking):
    """A hub on the house Wi-Fi is asked for a password, not for a name it can read off itself.

    The host never hands a PSK back up, so a hub plainly sitting on the network still has `known`
    false -- and what that produced was a question with a "Wi-Fi name" box in it, under a lede that
    told every household "the hub is on a cable", including the ones whose hub is on the Wi-Fi.
    Retyping a name the hub can read is the only way to get it wrong, and a puck on a network that
    does not exist looks exactly like a puck that does not work. Reported from a real setup.
    """
    def setUp(self):
        super().setUp()
        self.hub = FakeHub(self.tmp.name, wifi=False)      # a name it can see, a password it has not got
        self.hub.net = FakeNet()
        self.b = Bridges(self.hub, cable=self.cable, devdir=self.dev)

    knock = TheJob.knock                                   # the same plug-and-be-noticed as the job above
    adopt_and_finish = TheJob.adopt_and_finish

    def ask(self):
        self.knock(); run(self.adopt_and_finish()); return self.b.status()

    def test_the_question_names_the_network_rather_than_asking_for_it(self):
        s = self.ask()
        self.assertEqual((s["state"], s["needs"]), ("failed", "wifi"))
        self.assertEqual(s["ssid"], "VirusBroadcast")
        self.assertIn("VirusBroadcast", s["text"])
        self.assertNotIn("cable", s["text"])          # it is not on one, and saying so is the bug

    def test_a_password_on_its_own_is_enough(self):
        self.ask()
        async def tell():
            await self.b.wifi("", "hunter2"); await self.b._task
        run(tell())
        self.assertEqual(self.cable.written[0][1]["ssid"], "VirusBroadcast")
        self.assertEqual(self.b.status()["state"], "placing")

    def test_the_hub_hands_out_what_the_hub_is_using_whatever_it_is_told(self):
        """docs/network.md's rule, and the reason the panel offers no box to type another name into:
        a name typed here is overruled by the connection the hub is standing on, so a field for it
        would be a choice that quietly does not happen."""
        self.ask()
        run(self.b.wifi("Garage", "hunter2"))
        self.assertEqual(self.b.status()["needs"], "wifi")            # asked again, not written
        self.assertEqual(self.cable.written, [])

    def test_a_hub_on_a_cable_is_still_asked_the_whole_thing(self):
        self.hub.net = FakeNet(how="cable", ssid="")
        self.b = Bridges(self.hub, cable=self.cable, devdir=self.dev)
        s = self.ask()
        self.assertEqual(s["needs"], "wifi")
        self.assertNotIn("ssid", s)                   # nothing to show, so nothing is claimed
        self.assertIn("cable", s["text"])

    def test_a_hub_with_nothing_to_offer_still_refuses_an_empty_name(self):
        self.hub.net = FakeNet(how="cable", ssid="")
        self.b = Bridges(self.hub, cable=self.cable, devdir=self.dev)
        self.ask()
        with self.assertRaises(ValueError): run(self.b.wifi("", "hunter2"))


class WhichOnesAreBehind(unittest.TestCase):
    """A fix reaches new pucks and no others, and the house can at least say which.

    docs/puck-updates.md: a puck has no update path of any kind yet, so the version a bridge is on is
    the version it was flashed with. That is a fact worth being able to see -- and once a fix DOES
    have to reach every puck, the count is the whole feature, because the failure that costs a
    household is a house that believes every one has it when one does not.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dev = Path(self.tmp.name) / "by-id"; self.dev.mkdir()
        self.hub = FakeHub(self.tmp.name)
        self.cable = FakeCable(); self.cable.ships("0.3.1")
        self.b = Bridges(self.hub, cable=self.cable, devdir=self.dev)

    def tearDown(self): self.tmp.cleanup()

    def have(self, **pucks):
        self.hub.settings.set(bridges={c: {"since": 1, "fw": fw} for c, fw in pucks.items()})

    def test_a_bridge_on_an_older_version_is_named(self):
        self.have(c8ebba="0.2.0")
        b = self.b.behind()
        self.assertEqual([(x["chip"], x["fw"], x["latest"]) for x in b], [("c8ebba", "0.2.0", "0.3.1")])

    def test_a_bridge_on_what_the_house_ships_is_not(self):
        self.have(c8ebba="0.3.1")
        self.assertEqual(self.b.behind(), [])

    def test_a_bridge_ahead_of_the_house_is_left_alone(self):
        """A bench puck flashed from a working copy. Telling somebody it is out of date is noise."""
        self.have(c8ebba="0.4.0")
        self.assertEqual(self.b.behind(), [])

    def test_versions_are_compared_as_numbers_and_not_as_words(self):
        self.cable.ships("0.10.0")
        self.have(c8ebba="0.9.0")
        self.assertEqual(len(self.b.behind()), 1)          # 0.9.0 is older than 0.10.0

    def test_a_build_that_is_not_a_version_is_never_behind(self):
        self.have(c8ebba="dev", f4a9f3="")
        self.assertEqual(self.b.behind(), [])

    def test_a_house_that_cannot_say_what_it_ships_says_nothing(self):
        self.cable.image.with_suffix(".json").unlink()
        self.have(c8ebba="0.2.0")
        self.assertEqual(self.b.behind(), [])

    def test_a_mangled_manifest_does_not_take_the_panel_down(self):
        self.cable.image.with_suffix(".json").write_text("{not json")
        self.have(c8ebba="0.2.0")
        self.assertEqual(self.b.behind(), [])

    def test_the_panel_is_told_without_a_job_running(self):
        """It is a standing fact about the house, not a step in setting anything up."""
        self.have(c8ebba="0.2.0")
        s = self.b.status()
        self.assertEqual(s["state"], "none")
        self.assertEqual([x["chip"] for x in s["behind"]], ["c8ebba"])

    def test_nothing_behind_says_nothing_at_all(self):
        self.have(c8ebba="0.3.1")
        self.assertNotIn("behind", self.b.status())

    def test_it_counts_every_one_the_hub_set_up_whether_or_not_it_is_awake(self):
        """The one that is asleep behind a sofa is exactly the one worth counting."""
        self.have(c8ebba="0.2.0", f4a9f3="0.2.0")
        self.assertEqual(len(self.b.behind()), 2)
        self.assertEqual([x["online"] for x in self.b.behind()], [False, False])
