import asyncio, http.server, json, threading, unittest
from hub import camera
from hub.model import Device
from tests.apptest import ApiTest
from tests.test_pairing import FakeHA


class FakeWS:
    """The panel's end: a queue of what it says, a list of what it hears."""
    def __init__(self, *says):
        self.inbox = asyncio.Queue(); self.heard = []
        for s in says: self.inbox.put_nowait(json.dumps(s))
    async def send_text(self, t): self.heard.append(json.loads(t))
    async def receive_text(self):
        m = await self.inbox.get()
        if m is None: raise ConnectionError("hung up")
        return m
    def hang_up(self): self.inbox.put_nowait(None)


def run(coro): return asyncio.run(coro)


class RelayTest(unittest.TestCase):
    def test_offer_answer_and_candidates_cross(self):
        ha = FakeHA(); ha.results["camera/webrtc/get_client_config"] = {"configuration": {"iceServers": [{"urls": "stun:x"}]}}
        ws = FakeWS({"type": "offer", "offer": "v=0 offer"}, {"type": "candidate", "candidate": {"candidate": "a", "sdpMid": "0"}})

        async def go():
            task = asyncio.create_task(camera.relay(ha, "camera.door", ws))
            for _ in range(50):
                if ha.subs: break
                await asyncio.sleep(0.01)
            (i, (type_, cb, kw)), = ha.subs.items()
            self.assertEqual((type_, kw), ("camera/webrtc/offer", {"entity_id": "camera.door", "offer": "v=0 offer"}))
            cb({"type": "session", "session_id": "s1"}); cb({"type": "answer", "answer": "v=0 answer"})
            cb({"type": "candidate", "candidate": {"candidate": "b", "sdpMLineIndex": 0}})
            await asyncio.sleep(0.05)
            ws.hang_up()
            with self.assertRaises(ConnectionError): await task    # the route turns the panel's hang-up into a quiet end
            return i
        i = run(go())
        self.assertEqual(ws.heard[0], {"type": "config", "configuration": {"iceServers": [{"urls": "stun:x"}]}})
        self.assertEqual([m["type"] for m in ws.heard[1:]], ["session", "answer", "candidate"])
        self.assertIn(("camera/webrtc/candidate", {"entity_id": "camera.door", "session_id": "s1", "candidate": {"candidate": "a", "sdpMid": "0"}}), ha.sent)
        self.assertEqual(ha.unsubs, [i], "hanging up ends HA's session")

    def test_camera_without_webrtc_says_so(self):
        ha = FakeHA(); ha.fail.add("camera/webrtc/get_client_config")
        ws = FakeWS({"type": "offer", "offer": "x"})
        run(camera.relay(ha, "camera.old", ws))
        self.assertEqual(ws.heard[0]["type"], "error"); self.assertEqual(ws.heard[0]["code"], "no_webrtc")
        self.assertEqual(ha.subs, {})

    def test_refused_offer_is_reported_and_ends(self):
        ha = FakeHA(); ha.results["camera/webrtc/get_client_config"] = {"configuration": {}}; ha.fail.add("camera/webrtc/offer")
        ws = FakeWS({"type": "offer", "offer": "x"})
        run(camera.relay(ha, "camera.old", ws))
        self.assertEqual([m["type"] for m in ws.heard], ["config", "error"])
        self.assertEqual(ws.heard[1]["code"], "webrtc_offer_failed")

    def test_candidate_before_session_waits_for_it(self):
        ha = FakeHA(); ha.results["camera/webrtc/get_client_config"] = {"configuration": {}}
        ws = FakeWS({"type": "offer", "offer": "x"}, {"type": "candidate", "candidate": {"candidate": "early"}})

        async def go():
            task = asyncio.create_task(camera.relay(ha, "camera.door", ws))
            for _ in range(50):
                if ha.subs: break
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.05)
            self.assertFalse([s for s in ha.sent if s[0] == "camera/webrtc/candidate"], "nothing sent until HA names the session")
            (_, cb, _), = ha.subs.values()
            cb({"type": "session", "session_id": "s9"})
            await asyncio.sleep(0.05)
            ws.hang_up()
            with self.assertRaises(ConnectionError): await task
        run(go())
        self.assertEqual([s[1]["session_id"] for s in ha.sent if s[0] == "camera/webrtc/candidate"], ["s9"])


class MjpegTest(unittest.TestCase):
    """HA's stream arrives a frame at a time; the proxy must hand each on as it comes, not wait for a full buffer."""
    def test_chunks_arrive_as_sent(self):
        import http.server, threading, time
        frames = [b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + bytes([n]) * 300 + b"\r\n" for n in range(3)]
        seen_auth = []

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen_auth.append(self.headers.get("Authorization")); assert self.path == "/api/camera_proxy_stream/camera.door"
                self.send_response(200); self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame"); self.end_headers()
                for f in frames: self.wfile.write(f); self.wfile.flush(); time.sleep(0.05)
            def log_message(self, *a): pass
        srv = http.server.HTTPServer(("127.0.0.1", 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            ctype, chunks = camera.mjpeg(f"http://127.0.0.1:{srv.server_port}", "tok", "camera.door")
            self.assertTrue(ctype.startswith("multipart/x-mixed-replace"))
            self.assertEqual(seen_auth, ["Bearer tok"])
            got, stamps = [], []
            for b in chunks: got.append(b); stamps.append(time.monotonic())
            self.assertEqual(b"".join(got), b"".join(frames))
            self.assertGreaterEqual(len(got), 3, "each frame came through on its own")
            self.assertGreater(stamps[-1] - stamps[0], 0.05, "frames were handed on as they arrived, not buffered to the end")
        finally: srv.shutdown(); srv.server_close()

    def test_refused_stream_raises(self):
        with self.assertRaises(OSError): camera.mjpeg("http://127.0.0.1:1", "tok", "camera.door")


class FramesTest(unittest.TestCase):
    """The age the panel puts on a picture. HA hands back whatever the integration is holding -- Ring
    cuts its still out of the last recorded video and keeps it until the next event -- so the only
    honest thing to say is how long these exact bytes have been the answer."""
    def test_the_same_frame_keeps_the_time_it_first_arrived(self):
        f = camera.Frames()
        tag, age = f.stamp("camera.door", b"night")
        self.assertEqual(age, 0)
        f._seen["camera.door"] = (tag, f._seen["camera.door"][1] - 4 * 3600)   # four hours of nothing happening
        again, age = f.stamp("camera.door", b"night")
        self.assertEqual(again, tag, "the same bytes are the same frame")
        self.assertEqual(age, 4 * 3600, "and are four hours old, however often they were fetched")

    def test_a_new_frame_starts_the_clock_again(self):
        f = camera.Frames()
        tag, _ = f.stamp("camera.door", b"night")
        f._seen["camera.door"] = (tag, f._seen["camera.door"][1] - 4 * 3600)
        moved, age = f.stamp("camera.door", b"morning")
        self.assertNotEqual(moved, tag)
        self.assertEqual(age, 0)

    def test_cameras_are_dated_apart(self):
        f = camera.Frames()
        a, _ = f.stamp("camera.door", b"one")
        b, _ = f.stamp("camera.drive", b"two")
        self.assertNotEqual(a, b)
        self.assertEqual(f.stamp("camera.door", b"one")[0], a, "the door's frame is not the drive's")

    def test_a_house_of_cameras_does_not_grow_without_end(self):
        f = camera.Frames()
        for n in range(camera.Frames.LIMIT + 10): f.stamp(f"camera.{n}", b"x")
        self.assertLessEqual(len(f._seen), camera.Frames.LIMIT)


class StillRouteTest(ApiTest):
    """/devices/{id}/image, end to end against something standing in for HA."""
    def setUp(self):
        super().setUp()
        self.frames = [b"night-frame"]
        served = self.frames

        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                assert self.path == "/api/camera_proxy/camera.door", self.path
                body = served[0]
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg"); self.send_header("Content-Length", str(len(body)))
                self.end_headers(); self.wfile.write(body)
            def log_message(self, *a): pass

        self.ha_server = http.server.HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.ha_server.serve_forever, daemon=True).start()
        self.addCleanup(self.ha_server.server_close)
        self.addCleanup(self.ha_server.shutdown)
        self.hub.ha.url = f"http://127.0.0.1:{self.ha_server.server_port}"
        self.hub.ha.token = "tok"
        self.hub.home.devices["camera.door"] = Device("camera.door", "Front door camera", "front", "camera", "idle")

    def test_the_still_is_dated_so_the_panel_need_not_guess(self):
        r = self.client.get("/devices/camera.door/image")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content, b"night-frame")
        self.assertTrue(r.headers["etag"])
        self.assertEqual(r.headers["x-frame-age"], "0")
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_a_panel_that_already_holds_the_frame_is_told_so_and_told_its_age(self):
        first = self.client.get("/devices/camera.door/image")
        tag = first.headers["etag"]
        self.hub.frames._seen["camera.door"] = (tag.strip('"'), self.hub.frames._seen["camera.door"][1] - 4 * 3600)
        again = self.client.get("/devices/camera.door/image", headers={"If-None-Match": tag})
        self.assertEqual(again.status_code, 304)
        self.assertEqual(again.content, b"")                     # the bytes stay on the LAN
        self.assertEqual(again.headers["x-frame-age"], str(4 * 3600), "and the panel learns the picture is old")

    def test_a_frame_that_changes_is_sent_and_dated_afresh(self):
        first = self.client.get("/devices/camera.door/image")
        self.frames[0] = b"morning-frame"
        second = self.client.get("/devices/camera.door/image", headers={"If-None-Match": first.headers["etag"]})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.content, b"morning-frame")
        self.assertNotEqual(second.headers["etag"], first.headers["etag"])
        self.assertEqual(second.headers["x-frame-age"], "0")


if __name__ == "__main__": unittest.main()
