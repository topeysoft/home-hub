# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Finishing the driver layer without anyone opening Home Assistant.

docker-compose.yml puts each rented part at a fixed address. When a part answers, the brain adds its
integration to HA itself: it walks the same config flow the panel would draw, with the answers filled
in. This runs on connect and then every half minute, so a radio plugged in later is picked up too, and
the panel is told what was found in plain words (`drivers` in /setup/status).
"""
import asyncio, hashlib, json, logging, os, time

log = logging.getLogger("hub.drivers")
RETRY_AFTER = 300     # seconds before a part that failed to connect is tried again
DONE = {"already_configured", "reconfigure_successful"}   # an abort that means the flow got where it was going

# id, name, port the brain probes, HA integration to add (None: nothing to add), answers for its flow.
# {host} is where HA reaches the other containers: localhost with host networking (the Pi), a
# container name on a bridge network (the Mac). HUB_DRIVER_HOST in .env overrides it.
PARTS = [
    ("mqtt",   "Messages",     1883,  "mqtt",     {"broker": "{host}", "port": 1883, "other_settings": {"set_client_cert": False, "set_ca_cert": "off"}}),   # HA 2026.9 requires other_settings
    ("zwave",  "Z-Wave radio", 3000,  "zwave_js", {"url": "ws://{host}:3000"}),
    ("zigbee", "Zigbee radio", 8080,  None,       {}),
    ("matter", "Matter",       5580,  "matter",   {"url": "ws://{host}:5580/ws"}),
    ("ring",   "Ring",         55123, None,       {}),
]
WORDS = {
    ("mqtt", "off"): "Not running yet", ("matter", "off"): "Not running yet",
    ("zwave", "off"): "No Z-Wave stick found. Plug one in and it starts on its own.",
    ("zigbee", "off"): "No Zigbee stick found. Plug one in and it starts on its own.",
    ("zigbee", "waiting"): "Running, waiting for Messages",
    ("ring", "off"): "Not running",
    ("ring", "sign-in"): "Sign in once to bring in the alarm, cameras and sensors.",
    ("ring", "ready"): "Signed in",
}


def fill(fields: list, answers: dict) -> dict:
    """Answers for a form: ours where we have them, the integration's defaults otherwise, and for the rest of the
    required fields the quietest choice (off, the first option). A section nests its own answers under its name."""
    data = {}
    for f in fields:
        n = f["name"]
        if f.get("kind") == "section":
            data[n] = fill(f.get("fields") or [], answers.get(n) if isinstance(answers.get(n), dict) else {})
        elif n in answers: data[n] = answers[n]
        elif f.get("default") is not None: data[n] = f["default"]
        elif f.get("required"):
            if f.get("kind") == "boolean": data[n] = False
            elif f.get("kind") == "select" and f.get("options"): data[n] = f["options"][0]["value"]
    return data


async def probe(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        _, w = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except Exception:
        return False
    w.close()
    try: await w.wait_closed()
    except Exception: pass
    return True


class Provision:
    def __init__(self, hub):
        self.hub = hub
        self.host = hub.env.get("HUB_DRIVER_HOST") or os.environ.get("HUB_DRIVER_HOST") or "localhost"
        self.probe_host = hub.env.get("HUB_PROBE_HOST") or os.environ.get("HUB_PROBE_HOST") or "localhost"
        self.parts = {pid: {"id": pid, "name": name, "state": "unknown", "text": "Looking…", "port": port} for pid, name, port, _, _ in PARTS}
        self._failed_at: dict[str, float] = {}
        self.problems: list[dict] = []     # integrations HA has but could not set up, with HA's reason
        self.domains: dict[str, str] = {}  # config entry -> what integration it is. A device carries its entry (model.Device.entry); this is how health.py turns that into "the Z-Wave radio" and gathers everything that went quiet with it
        self.sign_ins: list[dict] = []     # accounts whose sign-in ran out, each with the flow that finishes it

    def summary(self) -> list[dict]:
        return list(self.parts.values())

    def mqtt_auth(self) -> tuple[str, str] | None:
        """The broker's password, if this hub has one: MQTT_USER / MQTT_PASSWORD from .env (the Mac) or the
        container's environment (the hub, where compose hands them in). None means the broker is open."""
        env = self.hub.env
        u = env.get("MQTT_USER") or os.environ.get("MQTT_USER")
        p = env.get("MQTT_PASSWORD") or os.environ.get("MQTT_PASSWORD")
        return (u, p) if u and p else None

    def answers(self, pid: str, answers: dict) -> dict:
        """A part's answers with this hub filled in: where HA reaches it, and for Messages the password."""
        out = {k: (v.format(host=self.host) if isinstance(v, str) else v) for k, v in answers.items()}
        if pid == "mqtt" and (auth := self.mqtt_auth()):
            out["username"], out["password"] = auth
        return out

    def _mqtt_fp(self) -> str | None:
        """What the engine was last told the broker's password is, as a fingerprint kept in settings; the
        password itself stays in .env. Differs from the current one on a hub that just gained a password, or
        on a house restored onto a hub that made a different one -- both times the engine needs telling."""
        auth = self.mqtt_auth()
        return hashlib.sha256(f"{auth[0]}:{auth[1]}".encode()).hexdigest()[:16] if auth else None

    def _set(self, pid, state, text=None):
        p = self.parts[pid]
        text = text if text is not None else WORDS.get((pid, state), {"ready": "Running", "adding": "Connecting…"}.get(state, ""))
        changed = (p["state"], p["text"]) != (state, text)
        p["state"], p["text"] = state, text
        return changed

    async def run(self):
        while True:
            try:
                if self.hub.driver == "ready": await self.refresh()
            except Exception:
                log.exception("drivers")
            await asyncio.sleep(30)

    async def refresh(self):
        """Look at every part once: probe, add what is missing in HA, and tell the panel if anything changed."""
        changed = False
        rows = await self._entries()
        entries = {e["domain"] for e in rows}
        self.domains = {e["entry_id"]: e["domain"] for e in rows}
        sign_ins = await self.hub.add.sign_ins()
        if sign_ins != self.sign_ins:
            self.sign_ins = sign_ins; changed = True
        # an account whose token died usually stops working *and* gets a sign-in flow; the flow is the one worth
        # offering, so it stands in for the complaint rather than the house saying the same thing twice.
        again = {w["handler"] for w in sign_ins}
        problems = [{"entry_id": e["entry_id"], "domain": e["domain"], "title": e.get("title") or e["domain"], "state": e["state"], "reason": e.get("reason") or ""}
                    for e in rows if e.get("state") in ("setup_error", "setup_retry", "migration_error", "failed_unload") and e["domain"] not in again]
        if problems != self.problems:
            self.problems = problems; changed = True
        for pid, name, port, domain, answers in PARTS:
            if not await probe(self.probe_host, port):
                changed |= self._set(pid, "off"); continue
            if domain:
                if domain in entries:
                    fp = self._mqtt_fp() if pid == "mqtt" else None
                    if fp and self.hub.settings.get("mqtt_auth") != fp:
                        # The engine has Messages, but not with this password: a hub that just gained one, or a
                        # house restored onto a different hub. Tell it, through HA's own reconfigure flow.
                        if time.time() - self._failed_at.get(pid, 0) < RETRY_AFTER: continue
                        entry = next((e["entry_id"] for e in rows if e["domain"] == domain), None)
                        if self._set(pid, "adding"): self._tell()
                        try:
                            await self.reconfigure(domain, entry, self.answers(pid, answers))
                            self.hub.settings.set(mqtt_auth=fp)
                            self.hub.log.add("home", "driver", None, f"{name} signed in", source="system", detail={"integration": domain})
                            log.info("%s: gave HA the broker's password", name)
                        except Exception as e:
                            self._failed_at[pid] = time.time()
                            log.warning("%s: could not give HA the password: %s", name, e)
                            changed |= self._set(pid, "failed", f"Could not sign in: {e}"); continue
                    changed |= self._set(pid, "ready"); continue
                if time.time() - self._failed_at.get(pid, 0) < RETRY_AFTER: continue
                if self._set(pid, "adding"): self._tell()
                try:
                    await self.add(domain, self.answers(pid, answers))
                    entries.add(domain)
                    if pid == "mqtt" and (fp := self._mqtt_fp()): self.hub.settings.set(mqtt_auth=fp)
                    self.hub.log.add("home", "driver", None, f"{name} connected", source="system", detail={"integration": domain})
                    log.info("%s: added %s to HA", name, domain)
                    changed |= self._set(pid, "ready")
                except Exception as e:
                    self._failed_at[pid] = time.time()
                    log.warning("%s: could not add %s: %s", name, domain, e)
                    changed |= self._set(pid, "failed", f"Could not connect: {e}")
            elif pid == "zigbee":
                changed |= self._set(pid, "ready" if "mqtt" in entries else "waiting")
            elif pid == "ring":
                changed |= self._set(pid, "ready" if await self._ring_seen() else "sign-in")
        if changed: self._tell()

    def _tell(self):
        self.hub._broadcast(json.dumps({"type": "status", "status": self.hub.status()}))

    async def _entries(self) -> list:
        try: return list(await self.hub.ha.send("config_entries/get"))
        except Exception as e:
            log.warning("could not list HA's integrations: %s", e); return []

    async def retry_part(self, pid: str):
        """Try a part the hub runs itself again, now rather than when the backoff runs out.

        A part that failed to connect is left alone for RETRY_AFTER so a stick that is genuinely not there is
        not hammered every half minute. That is right for the loop and wrong for a person who has just plugged
        the stick back in, so Needs a look offers this and it forgets the backoff."""
        if pid not in self.parts: raise KeyError(pid)
        self._failed_at.pop(pid, None)
        await self.refresh()

    async def retry(self, entry_id: str):
        """Ask HA to set an integration up again, after the person fixed what it complained about."""
        await asyncio.to_thread(self.hub.add._rest, "POST", f"/api/config/config_entries/entry/{entry_id}/reload")   # REST only; no websocket command for this
        await asyncio.sleep(3)
        await self.refresh()

    async def _ring_seen(self) -> bool:
        """Ring's things arrive over MQTT once someone has signed in; their devices say Ring made them."""
        try: devs = await self.hub.ha.send("config/device_registry/list")
        except Exception: return False
        return any((d.get("manufacturer") or "").strip().lower() == "ring" for d in devs)

    async def add(self, domain: str, answers: dict):
        """Walk a config flow to the end with these answers. Forms get their fields filled from `answers` or
        the integration's defaults; a menu takes the manual/custom path; 'already configured' counts as done."""
        await self._walk(await self.hub.add.start(domain), answers)

    async def reconfigure(self, domain: str, entry_id: str, answers: dict):
        """The same walk over an entry HA already has, so its answers change in place and nothing that hangs
        off it -- every device Messages brought in -- is forgotten and found again."""
        await self._walk(await self.hub.add.reconfigure(domain, entry_id), answers)

    async def _walk(self, step: dict, answers: dict):
        add = self.hub.add
        try:
            for _ in range(8):
                t = step.get("type")
                if t == "create_entry": return
                if t == "abort":
                    if step.get("reason_id") in DONE or "already" in (step.get("reason") or "").lower(): return
                    raise RuntimeError(step.get("reason") or "stopped")
                if t == "menu":
                    ids = [o["id"] for o in step.get("options") or []]
                    pick = next((o for o in ids if any(k in o for k in ("manual", "custom", "broker"))), ids[0] if ids else None)
                    if not pick: raise RuntimeError("no way forward")
                    step = await add.submit(step["flow_id"], {"next_step_id": pick}); continue
                if t == "form":
                    if step.get("errors"): raise RuntimeError("; ".join(step["errors"].values()))
                    step = await add.submit(step["flow_id"], fill(step.get("fields") or [], answers)); continue
                if t == "progress":
                    await asyncio.sleep(2); step = await add.step(step["flow_id"]); continue
                raise RuntimeError(f"unexpected step {t!r}")
            raise RuntimeError("the flow did not finish")
        except Exception:
            if step.get("flow_id"): await add.cancel(step["flow_id"])
            raise
