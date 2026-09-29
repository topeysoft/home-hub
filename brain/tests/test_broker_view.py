# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The brain's view of the broker survives a deploy.

A deploy restarts Home Assistant and the brain together, and the brain is ready first: until HA's
MQTT integration has loaded, `mqtt/subscribe` answers "Unknown command". The brain used to ask once,
so after a deploy it heard no strip and no bridge until somebody restarted it -- reported on 23
September as a strip that reached the broker in five seconds and "failed right before the colour
check" three times running.
"""
import asyncio, tempfile, unittest

from hub import strip as strip_mod
from hub.strip import Strips
from tests.test_strip import FakeHA, FakeHub, FakeRadio, run


class HAStillLoading(FakeHA):
    """Home Assistant whose MQTT integration has not loaded for the first `slow` asks."""
    def __init__(self, slow: int):
        super().__init__()
        self.slow, self.asked = slow, 0

    async def subscribe(self, type_, cb, **kw):
        self.asked += 1
        if self.asked <= self.slow:
            raise RuntimeError("mqtt/subscribe: Unknown command.")
        return await super().subscribe(type_, cb, **kw)


class AfterADeploy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = strip_mod.RETRY_FIRST
        strip_mod.RETRY_FIRST = 0.01

    def tearDown(self):
        strip_mod.RETRY_FIRST = self.saved
        self.tmp.cleanup()

    def test_the_brain_keeps_asking_until_the_broker_answers_and_then_hears_the_strip(self):
        hub = FakeHub(self.tmp.name)
        hub.ha = HAStillLoading(slow=2)
        strips = Strips(hub, FakeRadio())

        async def go():
            await asyncio.wait_for(strips.listen(), 2.0)
            hub.ha.cb({"topic": "strip/2e4258/status", "payload": "online"})
        run(go())
        self.assertEqual(hub.ha.asked, 3)
        self.assertTrue(strips.strips["2e4258"].get("online"))

    def test_the_bridges_view_comes_back_the_same_way(self):
        from hub.bridge import Bridges
        from pathlib import Path
        from tests.test_bridge import FakeCable, FakeHub as BridgeHub
        hub = BridgeHub(self.tmp.name)
        hub.ha = HAStillLoading(slow=2)
        dev = Path(self.tmp.name) / "by-id"; dev.mkdir()
        b = Bridges(hub, cable=FakeCable(), devdir=dev)
        run(asyncio.wait_for(b.listen(), 2.0))
        self.assertEqual(hub.ha.asked, 3)
        self.assertIsNotNone(b._sub)


if __name__ == '__main__':
    unittest.main()
