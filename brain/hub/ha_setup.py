"""Bringing a fresh Home Assistant up without anyone seeing it.

Plain HTTP against HA's onboarding and auth endpoints. The brain creates the owner account itself,
with a generated password it keeps in settings, and mints the long-lived token it will use from
then on. If HA was set up by hand, `login` signs in with that account instead.
"""
import asyncio, json, re, secrets, urllib.error, urllib.parse, urllib.request
import websockets


class SetupError(RuntimeError):
    pass


def _req(url, data=None, token=None, method=None, form=False, timeout=30):
    if form: body = urllib.parse.urlencode(data).encode()
    else: body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method=method or ("POST" if body is not None else "GET"))
    r.add_header("Content-Type", "application/x-www-form-urlencoded" if form else "application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            t = resp.read().decode()
            return resp.status, (json.loads(t) if t.strip().startswith(("{", "[")) else t)
    except urllib.error.HTTPError as e:
        t = e.read().decode()
        try: return e.code, json.loads(t)
        except Exception: return e.code, t


def driver_state(url: str) -> str:
    """'fresh' (no owner yet), 'done' (onboarded), or raises if HA is not answering."""
    code, steps = _req(f"{url}/api/onboarding", timeout=6)
    if code == 404: return "done"                       # HA removes the endpoint once onboarding is over
    if code != 200 or not isinstance(steps, list): raise SetupError(f"onboarding status {code}")
    done = {s["step"]: s["done"] for s in steps}
    return "done" if done.get("user") else "fresh"


def username_for(name: str) -> str:
    u = re.sub(r"[^a-z0-9]+", "", name.lower()) or "owner"
    return u[:24]


def create_owner(url: str, name: str) -> dict:
    """Owner account + the rest of onboarding. Returns {username, password, access, refresh}."""
    client_id = f"{url}/"
    username, password = username_for(name), secrets.token_urlsafe(18)
    code, r = _req(f"{url}/api/onboarding/users", {"client_id": client_id, "name": name, "username": username, "password": password, "language": "en"})
    if code != 200: raise SetupError(f"could not create the owner: {r}")
    tok = _exchange(url, client_id, r["auth_code"])
    access = tok["access_token"]
    _req(f"{url}/api/onboarding/core_config", {}, access)
    _req(f"{url}/api/onboarding/analytics", {}, access)
    _req(f"{url}/api/onboarding/integration", {"client_id": client_id, "redirect_uri": client_id}, access)
    return {"username": username, "password": password, "access": access, "refresh": tok.get("refresh_token")}


def login(url: str, username: str, password: str) -> dict:
    """Sign in to an already set-up HA. Returns {access, refresh}."""
    client_id = f"{url}/"
    code, r = _req(f"{url}/auth/login_flow", {"client_id": client_id, "handler": ["homeassistant", None], "redirect_uri": client_id})
    if code != 200: raise SetupError(f"sign-in unavailable: {r}")
    code, r = _req(f"{url}/auth/login_flow/{r['flow_id']}", {"username": username, "password": password, "client_id": client_id})
    if code != 200 or r.get("type") != "create_entry":
        raise SetupError("That name and password did not work." if code == 200 or code == 400 else f"sign-in failed: {r}")
    tok = _exchange(url, client_id, r["result"])
    return {"access": tok["access_token"], "refresh": tok.get("refresh_token")}


def _exchange(url, client_id, auth_code):
    code, tok = _req(f"{url}/auth/token", {"client_id": client_id, "grant_type": "authorization_code", "code": auth_code}, form=True)
    if code != 200: raise SetupError(f"token exchange failed: {tok}")
    return tok


async def long_lived_token(url: str, access: str, client_name="home-hub brain") -> str:
    ws_url = url.replace("http", "ws", 1).rstrip("/") + "/api/websocket"
    async with websockets.connect(ws_url) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": access}))
        if json.loads(await ws.recv())["type"] != "auth_ok": raise SetupError("HA refused the fresh token")
        await ws.send(json.dumps({"id": 1, "type": "auth/long_lived_access_token", "client_name": client_name, "lifespan": 3650}))
        r = json.loads(await ws.recv())
        if not r.get("success"): raise SetupError(f"could not mint a token: {r}")
        return r["result"]


async def onboard(url: str, name: str) -> dict:
    """The whole thing for a fresh HA: owner, onboarding steps, long-lived token."""
    acct = await asyncio.to_thread(create_owner, url, name)
    acct["token"] = await long_lived_token(url, acct.pop("access"))
    return acct


async def sign_in(url: str, username: str, password: str) -> dict:
    tok = await asyncio.to_thread(login, url, username, password)
    return {"username": username, "password": password, "token": await long_lived_token(url, tok["access"])}
