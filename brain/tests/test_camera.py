import asyncio, json, unittest
from hub import camera
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


if __name__ == "__main__": unittest.main()


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
