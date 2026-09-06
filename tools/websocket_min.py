"""Minimal HA websocket client for one call, no third-party packages."""
import base64, json, os, socket, struct, urllib.parse


def _frame(payload: bytes) -> bytes:
    hdr = bytearray([0x81])
    n = len(payload)
    if n < 126: hdr.append(0x80 | n)
    elif n < 65536: hdr += bytes([0x80 | 126]) + struct.pack(">H", n)
    else: hdr += bytes([0x80 | 127]) + struct.pack(">Q", n)
    mask = os.urandom(4); hdr += mask
    return bytes(hdr) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload))


def _recv(sock) -> dict:
    def rd(n):
        buf = b""
        while len(buf) < n:
            c = sock.recv(n - len(buf))
            if not c: raise ConnectionError("closed")
            buf += c
        return buf
    b1, b2 = rd(2); n = b2 & 0x7F
    if n == 126: n = struct.unpack(">H", rd(2))[0]
    elif n == 127: n = struct.unpack(">Q", rd(8))[0]
    return json.loads(rd(n))


def long_lived_token(url, access_token, name):
    u = urllib.parse.urlparse(url)
    sock = socket.create_connection((u.hostname, u.port or 80), timeout=30)
    key = base64.b64encode(os.urandom(16)).decode()
    sock.sendall((f"GET /api/websocket HTTP/1.1\r\nHost: {u.netloc}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                  f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp = b""
    while b"\r\n\r\n" not in resp: resp += sock.recv(1024)
    assert b" 101 " in resp, resp
    assert _recv(sock)["type"] == "auth_required"
    sock.sendall(_frame(json.dumps({"type": "auth", "access_token": access_token}).encode()))
    assert _recv(sock)["type"] == "auth_ok"
    sock.sendall(_frame(json.dumps({"id": 1, "type": "auth/long_lived_access_token", "client_name": name, "lifespan": 3650}).encode()))
    r = _recv(sock); sock.close()
    assert r.get("success"), r
    return r["result"]
