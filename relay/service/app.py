# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The registration service: names for houses, and the relay's yes or no.

Two audiences on one port. Hubs, from anywhere, at https://api.elyir.app: is this name free, take it,
how is it doing, let it go. And frps, on this same box, asking before it carries a house (docs/service.md,
Where the check goes) -- which must never be reachable from outside, because whoever could answer it
could open the relay to anybody. The api name reaches this service the way a house reaches its own
door, through frps and a local Caddy (relay/terraform), so every request from outside arrives with
X-Forwarded-For on it and the plugin route turns away anything that has one.

The house never depends on this. With it down, frps refuses new tunnels and every house carries on at
home exactly as it does now.
"""
import base64, os, time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from home import Home, serve
from registry import Registry

CLAIMS_PER_DAY = 5               # per address: enough for a household changing its mind, not for a script


def make(registry: Registry, now=time.time, relay: dict | None = None, offer: dict | None = None, home: Home | None = None,
         nearby_origins: tuple = ()) -> FastAPI:
    """`relay` is how a carried house reaches frps -- its address and the shared token, which is not the gate
    (the house's own secret is) but which frps wants, so the hub is handed it rather than anybody typing it.
    `offer` is what a household is shown: whether the service is open to them, at what price, and where to pay."""
    app = FastAPI(title="home-hub relay registration", docs_url=None, redoc_url=None, openapi_url=None)
    claims: dict[str, list[float]] = {}
    relay = relay or {"addr": f"relay.{registry.zone}", "token": ""}
    offer = offer or {"open": False, "price": None, "pay": None}
    home = home or Home(registry, now=now)

    def owner(name: str, authorization: str | None):
        secret = (authorization or "").removeprefix("Bearer ").strip()
        if not registry.holder(name, secret): raise HTTPException(404, "No house by that name holds that key.")

    @app.get("/alive")
    def alive(): return {"ok": True}

    @app.get("/offer")
    def what_is_offered():
        """Whether the panel may offer this at all. Closed until a household can actually pay: the panel never
        shows a promise the house cannot keep, and an address nobody can pay for is one."""
        return offer

    @app.get("/nearby")
    def nearby(request: Request, origin: str | None = Header(default=None)):
        """Which names have their tunnel at the same public address as the asker: what a phone or laptop on a
        house's Wi-Fi sees as "on this Wi-Fi". Served on nearby.<zone>, which has no IPv6 record, so the
        browser comes in over IPv4 like the printers' tunnels do and the two addresses can match."""
        who = request.client.host if request.client else ""
        r = JSONResponse({"names": registry.nearby(who)}, headers={"Cache-Control": "no-store", "Vary": "Origin"})
        if origin and origin in nearby_origins:
            r.headers["Access-Control-Allow-Origin"] = origin
        return r

    @app.get("/names/{name}")
    def look(name: str, also: list[str] = Query(default=[])):
        """As somebody types: free, or why not and three that are. `also` carries the hub's own hints -- its town, a surname."""
        return registry.look(name, also[:4])

    class Claim(BaseModel):
        name: str

    @app.post("/houses", status_code=201)
    def claim(body: Claim, request: Request):
        who = request.client.host if request.client else ""
        recent = [t for t in claims.get(who, []) if now() - t < 24 * 3600]
        if len(recent) >= CLAIMS_PER_DAY: raise HTTPException(429, "Too many names from here today. Try again tomorrow.")
        try: out = registry.claim(body.name)
        except ValueError as e: raise HTTPException(422, str(e)) from None
        except LookupError: raise HTTPException(409, {"why": "taken", "suggestions": registry.suggest(body.name)}) from None
        claims[who] = recent + [now()]
        return out | {"relay": relay}

    @app.get("/houses/{name}")
    def status(name: str, authorization: str | None = Header(default=None)):
        owner(name, authorization)
        return {"name": name, "address": f"{name}.{registry.zone}", **registry.status(name), "relay": relay}

    @app.delete("/houses/{name}", status_code=204)
    def release(name: str, authorization: str | None = Header(default=None)):
        owner(name, authorization)
        registry.release(name)

    # ---- the house's LAN name: its certificate, proved over DNS-01 (home.py) ----
    # Shaped exactly like lego's `httpreq` DNS provider, so the hub needs a stock ACME client and nothing
    # of ours: POST {fqdn, value} with the house's name and secret as HTTP basic auth.
    def house_from_basic(authorization: str | None) -> str:
        try:
            kind, _, raw = (authorization or "").partition(" ")
            house, _, secret = base64.b64decode(raw).decode().partition(":")
            if kind.lower() == "basic" and registry.holder(house, secret): return house
        except Exception: pass
        raise HTTPException(401, "No house by that name holds that key.", headers={"WWW-Authenticate": "Basic"})

    class Challenge(BaseModel):
        fqdn: str
        value: str

    @app.post("/acme/present")
    def present(body: Challenge, authorization: str | None = Header(default=None)):
        why = home.present(house_from_basic(authorization), body.fqdn, body.value)
        if why: raise HTTPException(403, why)
        return {"ok": True}

    @app.post("/acme/cleanup")
    def cleanup(body: Challenge, authorization: str | None = Header(default=None)):
        home.cleanup(house_from_basic(authorization), body.fqdn)
        return {"ok": True}

    @app.post("/frps")
    async def plugin(request: Request):
        """frps's server plugin. Loopback only, and never anything that came through the public name."""
        host = request.client.host if request.client else ""
        if host not in ("127.0.0.1", "::1") or request.headers.get("x-forwarded-for"): raise HTTPException(404)
        body = await request.json()
        why = registry.judge(str(body.get("op") or ""), body.get("content") or {})
        return {"reject": True, "reject_reason": why} if why else {"reject": False, "unchange": True}

    return app


def main():
    import uvicorn
    data = Path(os.environ.get("RELAY_DATA", "/data"))
    data.mkdir(parents=True, exist_ok=True)
    registry = Registry(data / "houses.db", zone=os.environ.get("RELAY_ZONE", "elyir.app"))
    if os.environ.get("RELAY_SELF_SECRET"):
        registry.seed("api", os.environ["RELAY_SELF_SECRET"])
    # The printer app's static files, served from this box like api is (cloud-init): always carried.
    if os.environ.get("RELAY_PRINTERS_SECRET"):
        registry.seed("printers", os.environ["RELAY_PRINTERS_SECRET"], note="the printer app")
    if os.environ.get("RELAY_NEARBY_SECRET"):
        registry.seed("nearby", os.environ["RELAY_NEARBY_SECRET"], note="on this Wi-Fi")
    relay = {"addr": os.environ.get("RELAY_ADDR", f"relay.{registry.zone}"), "token": os.environ.get("RELAY_FRPS_TOKEN", "")}
    # The price is words, not a number: what it costs and how often, as the panel will say it.
    offer = {"open": os.environ.get("RELAY_OFFER_OPEN") == "1", "price": os.environ.get("RELAY_PRICE") or None, "pay": os.environ.get("RELAY_PAY_URL") or None}
    # proxy_headers from loopback only: Caddy is on this box and says who is really asking, so the
    # claims limit counts households rather than Caddy, and the plugin route can tell the two apart.
    home = Home(registry)
    # The address in the name (home.py): authoritative for home.<zone>, on 53 when RELAY_DNS_PORT says so.
    if os.environ.get("RELAY_DNS_PORT"):
        serve(home, ns=os.environ.get("RELAY_NS", f"ns1.{registry.zone}"), port=int(os.environ["RELAY_DNS_PORT"]))
    # Who may read /nearby from a page: the printer app, and its developer's own machine.
    origins = tuple(o.strip() for o in os.environ.get("RELAY_NEARBY_ORIGINS", f"https://printers.{registry.zone},http://localhost:5173").split(",") if o.strip())
    uvicorn.run(make(registry, relay=relay, offer=offer, home=home, nearby_origins=origins), host="127.0.0.1", port=int(os.environ.get("RELAY_PORT", "7100")),
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")


if __name__ == "__main__":
    main()
