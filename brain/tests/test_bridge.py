"""A bridge on the cable, without a bridge or a cable.

The machine is what the panel draws (app/src/BridgeSheet.vue), so what these hold is the sequence
of states a person would see: a puck appears and knocks, nothing of the house's moves until they
say yes, the three steps in order, then the walk, then the count. And the ways it goes wrong that
have a sentence for the wall: unplugged halfway, a hub with no Wi‑Fi to give.
"""
import asyncio, json, tempfile, unittest
from pathlib import Path

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
    def __init__(self): self.cb = None
    async def subscribe(self, type_, cb, **kw): self.cb = cb; return 1


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
