"""Live video for the viewer.

Two ways, best first. WebRTC: the panel's offer and HA's answer cross here, then the browser and
HA's go2rtc talk to each other directly; the brain never sees a frame. Motion JPEG: HA's
`camera_proxy_stream` passed through one chunk at a time, for cameras HA cannot hand to go2rtc and
browsers that cannot do WebRTC. Stills (`/devices/{id}/image`) remain the floor under both.
"""
import asyncio, json, logging, urllib.request

log = logging.getLogger(__name__)
CONNECT_TIMEOUT = 15      # seconds to wait for HA to start an MJPEG stream
SESSION_WAIT = 10         # seconds a candidate waits for HA to name the session before it is dropped
CHUNK = 64 * 1024


async def relay(ha, entity_id: str, ws):
    """One viewer's WebRTC signalling, panel on one side and HA on the other. Returns when the panel hangs up.

    Panel → brain: {"type": "offer", "offer": sdp} once, then {"type": "candidate", "candidate": {…}} as ICE finds routes.
    Brain → panel: {"type": "config", "configuration": {"iceServers": […]}} first, then HA's own messages as
    they come: session, answer, candidate, error. `ws` needs send_text() and receive_text().
    """
    try:
        cfg = await ha.send("camera/webrtc/get_client_config", entity_id=entity_id)
    except Exception as e:
        await ws.send_text(json.dumps({"type": "error", "code": "no_webrtc", "message": str(e)})); return
    await ws.send_text(json.dumps({"type": "config", **(cfg or {})}))
    loop = asyncio.get_running_loop()
    session: asyncio.Future = loop.create_future()
    sub = None

    def on_event(ev):
        if ev.get("type") == "session" and not session.done(): session.set_result(ev.get("session_id"))
        loop.create_task(ws.send_text(json.dumps(ev)))

    try:
        while True:
            m = json.loads(await ws.receive_text())
            t = m.get("type")
            if t == "offer" and sub is None:
                try:
                    sub = await ha.subscribe("camera/webrtc/offer", on_event, entity_id=entity_id, offer=m.get("offer") or "")
                except Exception as e:
                    await ws.send_text(json.dumps({"type": "error", "code": "webrtc_offer_failed", "message": str(e)})); return
            elif t == "candidate" and sub is not None and m.get("candidate"):
                # The browser starts finding routes as soon as it has an offer, often before HA has named the session.
                try: sid = await asyncio.wait_for(asyncio.shield(session), SESSION_WAIT)
                except asyncio.TimeoutError: continue
                try: await ha.send("camera/webrtc/candidate", entity_id=entity_id, session_id=sid, candidate=m["candidate"])
                except Exception as e: log.info("candidate for %s refused: %s", entity_id, e)
    finally:
        if sub is not None: await ha.unsubscribe(sub)    # HA closes the go2rtc session on unsubscribe


def mjpeg(url: str, token: str, entity_id: str):
    """Opens HA's motion-JPEG stream for a camera. Returns (content type, chunk iterator); raises if HA will not start it."""
    r = urllib.request.Request(f"{url}/api/camera_proxy_stream/{entity_id}", headers={"Authorization": f"Bearer {token}"})
    resp = urllib.request.urlopen(r, timeout=CONNECT_TIMEOUT)
    ctype = resp.headers.get("Content-Type") or "multipart/x-mixed-replace"

    def chunks():
        with resp:
            while True:
                b = resp.read1(CHUNK)      # read1: whatever has arrived, not a wait for a full chunk
                if not b: return
                yield b
    return ctype, chunks()
