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
from hub.bridge import Bridges
from hub.settings import Settings


class FakeCable:
    """Scripted answers: what `hello` says per port, whether a silent port is an ESP, what write returns."""
    def __init__(self):
        self.hello_says = {}         # port -> dict | None
        self.esp = set()
        self.flashed, self.written = [], []
        self.write_says = {"chip": "c8ebba", "fw": "0.2.0", "state": "set"}
        self.write_fails = None

    async def hello(self, port): return self.hello_says.get(port)
    async def is_esp(self, port): return port in self.esp
    async def flash(self, port): self.flashed.append(port); self.hello_says[port] = {"chip": "c8ebba", "fw": "0.2.0", "state": "blank"}
    async def write(self, port, cfg):
        self.written.append((port, cfg))
        if self.write_fails: raise RuntimeError(self.write_fails)
        return self.write_says


class FakeHA:
    def __init__(self): self.cb = None; self.published = []; self.answer = None
    async def subscribe(self, type_, cb, **kw): self.cb = cb; return 1
    async def call(self, domain, service, target, **kw):
        self.published.append((kw.get("topic"), kw.get("payload")))
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

    def test_nothing_at_boot_is_a_knock(self):
        """A puck that was already there when the brain started did not just arrive."""
        p = self.plug("usb-bridge-1"); self.cable.hello_says[p] = {"chip": "aa", "fw": "0.2.0", "state": "blank"}
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
        self.assertEqual(self.cable.flashed, [p])
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
