#!/usr/bin/env python3
"""First-run bootstrap for a fresh Home Assistant: owner account, long-lived token, core integrations.

Idempotent-ish: if onboarding is already done it only (re)uses the token in driver-layer/.env.
Usage: python3 tools/ha_bootstrap.py [--url http://localhost:8123]
"""
import argparse, json, secrets, sys, urllib.request, urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / "driver-layer" / ".env"


def env_read():
    d = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1); d[k.strip()] = v.strip()
    return d


def env_write(updates):
    d = env_read(); d.update(updates)
    ENV.write_text("".join(f"{k}={v}\n" for k, v in d.items()))


def req(url, data=None, token=None, method=None):
    body = json.dumps(data).encode() if data is not None else None
    r = urllib.request.Request(url, data=body, method=method or ("POST" if body else "GET"))
    r.add_header("Content-Type", "application/json")
    if token: r.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(r, timeout=30) as resp:
            t = resp.read().decode()
            return resp.status, (json.loads(t) if t else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def onboard(url):
    """Create the owner, finish onboarding, return a long-lived access token."""
    code, steps = req(f"{url}/api/onboarding")
    done = {s["step"]: s["done"] for s in (steps or [])}
    env = env_read()
    if all(done.values()) and env.get("HA_TOKEN"):
        return env["HA_TOKEN"]
    if done.get("user"):
        sys.exit("Onboarding already started but no HA_TOKEN in .env. Create a long-lived token in HA (profile page) and put it in driver-layer/.env as HA_TOKEN.")

    client_id = f"{url}/"
    password = secrets.token_urlsafe(16)
    code, r = req(f"{url}/api/onboarding/users", {
        "client_id": client_id, "name": "Temi", "username": "temi",
        "password": password, "language": "en"})
    if code != 200: sys.exit(f"user step failed: {code} {r}")
    auth_code = r["auth_code"]

    # exchange auth code for a bearer token
    form = urllib.parse.urlencode({"client_id": client_id, "grant_type": "authorization_code", "code": auth_code}).encode()
    rq = urllib.request.Request(f"{url}/auth/token", data=form)
    with urllib.request.urlopen(rq) as resp: tok = json.loads(resp.read())
    access = tok["access_token"]; refresh = tok["refresh_token"]

    req(f"{url}/api/onboarding/core_config", {}, access)
    req(f"{url}/api/onboarding/analytics", {}, access)
    req(f"{url}/api/onboarding/integration", {"client_id": client_id, "redirect_uri": client_id}, access)

    # long-lived token via websocket
    import websocket_min as ws  # noqa  (tiny helper below)
    llt = ws.long_lived_token(url, access, "home-hub brain")
    env_write({"HA_URL": url, "HA_USER": "temi", "HA_PASSWORD": password, "HA_TOKEN": llt, "HA_REFRESH_TOKEN": refresh})
    print(f"owner 'temi' created; credentials and token saved to {ENV}")
    return llt


def flow(url, token, domain, steps):
    """Drive a config flow: steps is a list of dicts of user input per step."""
    code, r = req(f"{url}/api/config/config_entries/flow", {"handler": domain, "show_advanced_options": True}, token)
    if code != 200: return f"{domain}: start failed {code} {r}"
    for data in steps:
        if r.get("type") in ("create_entry", "abort"): break
        code, r = req(f"{url}/api/config/config_entries/flow/{r['flow_id']}", data, token)
        if code != 200: return f"{domain}: step failed {code} {r}"
    return f"{domain}: {r.get('type')} {r.get('reason') or r.get('title') or r.get('errors') or ''}"


def main():
    import urllib.parse  # noqa
    ap = argparse.ArgumentParser(); ap.add_argument("--url", default="http://localhost:8123")
    ap.add_argument("--mqtt-host", default="mosquitto")
    ap.add_argument("--roku", default="192.168.86.64")
    ap.add_argument("--cast", default="", help="comma-separated Cast IPs (empty = rely on discovery)")
    a = ap.parse_args()
    token = onboard(a.url)
    print(flow(a.url, token, "mqtt", [{"broker": a.mqtt_host, "port": 1883, "other_settings": {"set_client_cert": False, "set_ca_cert": "off"}}]))
    print(flow(a.url, token, "roku", [{"host": a.roku}]))
    if a.cast:
        print(flow(a.url, token, "cast", [{"known_hosts": a.cast.split(",")}]))
    else:
        print(flow(a.url, token, "cast", [{}]))


if __name__ == "__main__":
    import urllib.parse
    main()
