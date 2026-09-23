# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Setting a strip up through a bridge, without a bridge or a strip.

When the hub cannot hear a strip well and a bridge can, setup runs as an errand (hub/errand.py,
docs/strip.md item 45). These hold the words the brain says to a bridge -- the same ones the firmware
answers in, brilliant/esp32-bridge/src/errand.h -- and the three rules around it: which ear is used,
what a hub with no Bluetooth of its own can still find, and what the wall says when a bridge fails.
"""
import asyncio, base64, tempfile, unittest

from hub import errand as errand_mod
from hub.ears import Ears
from hub.errand import Errand, ErrandFailed
from hub.strip import Strips, StripError
from tests.test_strip import FakeHA, FakeHub, FakeRadio, run, turn

CHIP = "08388e"


class BridgeHA(FakeHA):
    """Home Assistant with a bridge on the far side of it, answering `errand/ask` in the firmware's own
    words and handing them back the way hub/bridge.py does: to whichever errand is running."""
    def __init__(self, hub, fails: str | None = None):
        super().__init__()
        self.hub, self.fails, self.asked = hub, fails, []

    async def call(self, domain, service, target, **kw):
        topic, line = kw.get("topic", ""), kw.get("payload", "")
        if not topic.endswith("/errand/ask"):
            return await super().call(domain, service, target, **kw)
        self.asked.append((topic, line))
        words = line.split(" ")
        verb, id_ = words[0], words[1]
        tell = lambda said: asyncio.get_running_loop().call_soon(
            lambda: self.hub.errand and self.hub.errand.on_tell(said))
        if verb == "open":
            tell(f"fail {id_} - {self.fails}" if self.fails else f"open {id_} ring")
        elif verb == "send":
            tell(f"ok {id_} {words[2]} {words[4]}")          # an echo is as good as a strip here


class TheWordsABridgeIsSent(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.hub.ha = BridgeHA(self.hub)

    def tearDown(self): self.tmp.cleanup()

    def test_open_names_the_strip_with_its_address_type(self):
        """A strip's address is random, and opened as public it is nobody's (item 42)."""
        async def go():
            e = Errand(self.hub, CHIP); self.hub.errand = e
            can_ring = await e.open("E7:38:84:E2:89:0A", "random")
            return e, can_ring
        e, can_ring = run(go())
        topic, line = self.hub.ha.asked[0]
        self.assertEqual(topic, f"mesh/bridge/{CHIP}/errand/ask")
        self.assertEqual(line, f"open {e.id} e7:38:84:e2:89:0a random")
        self.assertTrue(can_ring)

    def test_a_request_goes_as_base64_to_protocomms_own_endpoint_id(self):
        async def go():
            e = Errand(self.hub, CHIP); self.hub.errand = e
            await e.open("aa:bb:cc:dd:ee:ff")
            back = await e.send_data("prov-session", "\x00\x01\xffbytes nobody here can read")
            return e, back
        e, back = run(go())
        _, line = self.hub.ha.asked[1]
        verb, id_, n, ep, body = line.split(" ")
        self.assertEqual((verb, id_, n, ep), ("send", e.id, "1", "0xff51"))
        self.assertEqual(base64.b64decode(body), b"\x00\x01\xffbytes nobody here can read")
        self.assertEqual(back, "\x00\x01\xffbytes nobody here can read")

    def test_an_answer_for_another_errand_is_never_taken_for_this_one(self):
        saved = errand_mod.SEND_WAIT
        errand_mod.SEND_WAIT = 0.2
        try:
            async def go():
                e = Errand(self.hub, CHIP)          # not handed to the bridge, so nothing answers
                task = asyncio.ensure_future(e.send_data("press", "?"))
                await turn()
                e.on_tell("ok deadbeef 1 " + base64.b64encode(b"pressed").decode())
                with self.assertRaises(ErrandFailed):
                    await task
            run(go())
        finally:
            errand_mod.SEND_WAIT = saved

    def test_a_refused_write_is_the_strip_saying_no_and_is_carried_as_one(self):
        async def go():
            e = Errand(self.hub, CHIP)
            task = asyncio.ensure_future(e.send_data("prov-config", "creds"))
            await turn()
            e.on_tell(f"fail {e.id} 1 write")
            with self.assertRaises(ErrandFailed) as caught:
                await task
            return caught.exception.why
        self.assertEqual(run(go()), "write")

    def test_a_bridge_that_loses_the_strip_says_so_and_nobody_waits_out_a_timeout(self):
        async def go():
            e = Errand(self.hub, CHIP)
            task = asyncio.ensure_future(e.send_data("press", "?"))
            await turn()
            e.on_tell(f"closed {e.id} lost")
            with self.assertRaises(ErrandFailed) as caught:
                await asyncio.wait_for(task, 1.0)
            return caught.exception.why
        self.assertEqual(run(go()), "lost")

    def test_the_ring_is_heard(self):
        async def go():
            e = Errand(self.hub, CHIP)
            e.on_tell(f"ring {e.id}")
            await asyncio.wait_for(e.wait_for_ring(), 1.0)
        run(go())

    def test_lines_exactly_as_the_firmware_prints_them(self):
        """errand.cpp's own format strings, filled in: `ok %s %s %s`, `fail %s %s %s`, `open %s %s`."""
        async def go():
            e = Errand(self.hub, CHIP)
            opened = asyncio.ensure_future(e.open("aa:bb:cc:dd:ee:ff"))
            await turn()
            e.on_tell(f"open {e.id} quiet")
            self.assertFalse(await opened)
            sent = asyncio.ensure_future(e.send_data("proto-ver", "v"))
            await turn()
            e.on_tell(f"ok {e.id} 1 " + base64.b64encode(b'{"prov":{"ver":"v1.1"}}').decode())
            self.assertIn("prov", await sent)
        run(go())


class WhichRadioSetsItUp(unittest.TestCase):
    """The rules around the errand, on the real setup path, with our door's press held open."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.hub.ears = Ears()
        self.hub.errand = None
        self.radio = FakeRadio()
        self.strips = Strips(self.hub, self.radio)
        self.hub.settings.set(wifi={"ssid": "House", "pass": "secret"})

    def tearDown(self): self.tmp.cleanup()

    async def begin(self, hub_rssi: int, bridge_rssi: int | None, fails: str | None = None):
        self.hub.ha = BridgeHA(self.hub, fails)
        self.radio.hold = True
        self.radio.ours = [{"address": "AA:BB:CC:DD:EE:FF", "rssi": hub_rssi, "name": "PROV_2e425"}]
        if bridge_rssi is not None:
            self.hub.ears.heard(CHIP, "AA:BB:CC:DD:EE:FF", bridge_rssi, "random")
        await self.strips.look()
        await self.strips.adopt()
        for _ in range(5): await turn()
        return self.strips.status()

    def test_a_strip_the_hub_hears_well_is_set_up_on_the_hubs_own_radio(self):
        async def go():
            await self.begin(hub_rssi=-45, bridge_rssi=-35)
        run(go())
        self.assertEqual(self.radio.transports, [None])
        self.assertEqual(self.hub.ha.asked, [])

    def test_a_strip_behind_the_television_is_set_up_through_the_bridge_that_hears_it(self):
        """The whole of design/ears/: the hub in the garage hears it at -75, a bridge at -45."""
        async def go():
            st = await self.begin(hub_rssi=-75, bridge_rssi=-45)
            return st
        st = run(go())
        self.assertIsInstance(self.radio.transports[-1], Errand)
        self.assertEqual(self.radio.transports[-1].chip, CHIP)
        topic, line = self.hub.ha.asked[0]
        self.assertEqual(topic, f"mesh/bridge/{CHIP}/errand/ask")
        self.assertTrue(line.startswith("open ") and line.endswith(" aa:bb:cc:dd:ee:ff random"))
        self.assertEqual(st["state"], "press")        # and the press is still asked of the strip

    def test_a_bridge_that_cannot_reach_it_is_said_as_a_bridge_and_never_as_the_hub(self):
        async def go():
            return await self.begin(hub_rssi=-75, bridge_rssi=-45, fails="connect")
        st = run(go())
        self.assertEqual(st["state"], "failed")
        self.assertIn("bridge", st["text"])
        self.assertNotIn("nearer the hub", st["text"])


class AHubWithNoBluetoothOfItsOwn(unittest.TestCase):
    """The mini PC the product is sized for may have no radio at all. Its bridges are its ears."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.hub = FakeHub(self.tmp.name)
        self.hub.ears = Ears()
        self.radio = FakeRadio()

        async def deaf(*a, **k): raise StripError("This hub has no Bluetooth to look for a light strip with.")
        self.radio.scan_ours = deaf
        self.radio.scan = deaf
        self.strips = Strips(self.hub, self.radio)

    def tearDown(self): self.tmp.cleanup()

    def test_still_hears_a_strip_knocking_through_a_bridge(self):
        self.hub.ears.heard(CHIP, "e7:38:84:e2:89:0a", -52, "random", {"discriminator": 3840, "vendor": 0xFFF1})
        st = run(self.strips.look())
        self.assertEqual(st["state"], "knocking")
        self.assertEqual(self.strips.job["heard_by"], CHIP)
        self.assertEqual(self.strips.job["door"], "ours")

    def test_and_says_it_has_no_bluetooth_only_when_nobody_heard_anything(self):
        st = run(self.strips.look())
        self.assertEqual(st["state"], "none")
        self.assertIn("no Bluetooth", st.get("text", ""))


if __name__ == '__main__':
    unittest.main()
