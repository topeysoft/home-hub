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
import os, time
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request
from pydantic import BaseModel

from registry import Registry

CLAIMS_PER_DAY = 5               # per address: enough for a household changing its mind, not for a script


def make(registry: Registry, now=time.time) -> FastAPI:
    app = FastAPI(title="home-hub relay registration", docs_url=None, redoc_url=None, openapi_url=None)
    claims: dict[str, list[float]] = {}

    def owner(name: str, authorization: str | None):
        secret = (authorization or "").removeprefix("Bearer ").strip()
        if not registry.holder(name, secret): raise HTTPException(404, "No house by that name holds that key.")

    @app.get("/alive")
    def alive(): return {"ok": True}

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
        return out

    @app.get("/houses/{name}")
    def status(name: str, authorization: str | None = Header(default=None)):
        owner(name, authorization)
        return {"name": name, "address": f"{name}.{registry.zone}", **registry.status(name)}

    @app.delete("/houses/{name}", status_code=204)
    def release(name: str, authorization: str | None = Header(default=None)):
        owner(name, authorization)
        registry.release(name)

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
    # proxy_headers from loopback only: Caddy is on this box and says who is really asking, so the
    # claims limit counts households rather than Caddy, and the plugin route can tell the two apart.
    uvicorn.run(make(registry), host="127.0.0.1", port=int(os.environ.get("RELAY_PORT", "7100")),
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")


if __name__ == "__main__":
    main()
