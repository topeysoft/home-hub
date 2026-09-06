"""Finding and adding devices, in the product's words.

Home Assistant discovers things on the network and offers "config flows" for them: short forms.
This module lists what was found, starts flows for things the user asks for, and turns each step
of a flow into a plain form the panel can draw, with the integration's own English labels.
"""
import asyncio, json, logging, re, urllib.error, urllib.request

log = logging.getLogger("hub.add")

# integration kinds that are devices or hubs for devices, not helpers, not virtual aliases, not internals
KINDS = {"hub", "device", "service"}
HIDE = {"hassio", "mqtt", "matter", "zwave_js", "zha", "homeassistant_hardware", "homeassistant_sky_connect", "homeassistant_yellow",
        "thread", "otbr", "bluetooth", "usb", "zeroconf", "ssdp", "dhcp", "cloud", "mobile_app", "sun", "met", "backup", "analytics",
        "google_translate", "radio_browser", "shopping_list", "go2rtc", "hacs", "esphome_hardware"}


class Onboarding:
    def __init__(self, hub):
        self.hub = hub
        self._names: dict[str, str] = {}
        self._catalog: list[dict] | None = None
        self._strings: dict[str, dict] = {}

    # ---- plumbing ----
    def _rest(self, method, path, data=None):
        url, token = self.hub.ha.url, self.hub.ha.token
        body = json.dumps(data).encode() if data is not None else None
        r = urllib.request.Request(f"{url}{path}", data=body, method=method, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(r, timeout=60) as resp:
                t = resp.read().decode(); return json.loads(t) if t else {}
        except urllib.error.HTTPError as e:
            t = e.read().decode()
            try: msg = json.loads(t).get("message") or t
            except Exception: msg = t or e.reason
            raise RuntimeError(f"{msg}")

    async def strings(self, handler: str) -> dict:
        if handler not in self._strings:
            try:
                r = await self.hub.ha.send("frontend/get_translations", language="en", category="config", integration=[handler])
                self._strings[handler] = r.get("resources", {})
            except Exception as e:
                log.warning("no strings for %s: %s", handler, e); self._strings[handler] = {}
        return self._strings[handler]

    async def name_of(self, handler: str) -> str:
        if handler not in self._names:
            try: self._names[handler] = (await self.hub.ha.send("manifest/get", integration=handler)).get("name") or handler
            except Exception: self._names[handler] = handler.replace("_", " ").title()
        return self._names[handler]

    # ---- what is around ----
    async def discovered(self) -> list[dict]:
        """Things HA noticed on the network that are not set up yet."""
        try: flows = await self.hub.ha.send("config_entries/flow/progress")
        except Exception as e:
            log.warning("could not list discoveries: %s", e); return []
        out = []
        for f in flows:
            ctx = f.get("context") or {}
            if ctx.get("source") in (None, "user", "reauth", "reconfigure", "import"): continue
            handler = f["handler"]
            strings = await self.strings(handler)
            ph = ctx.get("title_placeholders") or {}
            title = _fill(strings.get(f"component.{handler}.config.flow_title", ""), ph) or ph.get("name") or await self.name_of(handler)
            out.append({"flow_id": f["flow_id"], "handler": handler, "kind": await self.name_of(handler), "title": title, "source": ctx.get("source")})
        return out

    async def catalog(self) -> list[dict]:
        """Everything that can be added by hand, for the search box."""
        if self._catalog is None:
            r = await self.hub.ha.send("integration/descriptions")
            core = (r.get("core") or {}).get("integration") or {}
            items = []
            for domain, d in core.items():
                if not d.get("config_flow") or d.get("integration_type") not in KINDS or domain in HIDE: continue
                items.append({"domain": domain, "name": d.get("name") or domain, "local": (d.get("iot_class") or "").startswith("local")})
            items.sort(key=lambda x: x["name"].lower())
            self._catalog = items
        return self._catalog

    # ---- running a flow ----
    async def start(self, handler: str) -> dict:
        step = await asyncio.to_thread(self._rest, "POST", "/api/config/config_entries/flow", {"handler": handler, "show_advanced_options": False})
        return await self.describe(step)

    async def step(self, flow_id: str) -> dict:
        return await self.describe(await asyncio.to_thread(self._rest, "GET", f"/api/config/config_entries/flow/{flow_id}"))

    async def submit(self, flow_id: str, data: dict) -> dict:
        return await self.describe(await asyncio.to_thread(self._rest, "POST", f"/api/config/config_entries/flow/{flow_id}", data))

    async def cancel(self, flow_id: str):
        try: await asyncio.to_thread(self._rest, "DELETE", f"/api/config/config_entries/flow/{flow_id}")
        except Exception: pass

    async def describe(self, step: dict) -> dict:
        """HA's step, rewritten as a form the panel can draw without knowing the integration."""
        h, sid = step.get("handler", ""), step.get("step_id", "")
        S = await self.strings(h)
        ph = step.get("description_placeholders") or {}
        key = f"component.{h}.config"
        out = {"flow_id": step.get("flow_id"), "handler": h, "kind": await self.name_of(h), "type": step.get("type"), "step_id": sid,
               "title": _fill(S.get(f"{key}.step.{sid}.title", ""), ph), "description": _fill(S.get(f"{key}.step.{sid}.description", ""), ph),
               "last_step": step.get("last_step")}
        if step.get("type") == "form":
            errs = step.get("errors") or {}
            out["errors"] = {k: _fill(S.get(f"{key}.error.{v}", v), ph) for k, v in errs.items()}
            out["fields"] = [_field(f, S, key, sid, ph) for f in (step.get("data_schema") or [])]
        elif step.get("type") == "menu":
            out["options"] = [{"id": o, "label": _fill(S.get(f"{key}.step.{sid}.menu_options.{o}", o.replace("_", " ").title()), ph)} for o in (step.get("menu_options") or [])]
        elif step.get("type") == "abort":
            out["reason"] = _fill(S.get(f"{key}.abort.{step.get('reason')}", (step.get("reason") or "stopped").replace("_", " ")), ph)
        elif step.get("type") == "create_entry":
            out["entry_title"] = step.get("title")
        elif step.get("type") == "progress":
            out["progress"] = _fill(S.get(f"{key}.progress.{step.get('progress_action')}", "Working…"), ph)
        elif step.get("type") == "external":
            out["url"] = step.get("url")
        return out


def _fill(s: str, ph: dict) -> str:
    if not s: return s
    s = re.sub(r"\{(\w+)\}", lambda m: str(ph.get(m.group(1), m.group(0))), s)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def _field(f: dict, S: dict, key: str, sid: str, ph: dict) -> dict:
    name = f["name"]
    sel = f.get("selector") or {}
    kind, options = "text", None
    t = f.get("type")
    if "select" in sel:
        kind = "select"
        options = [{"value": o["value"], "label": _fill(S.get(f"{key}.selector.{name}.options.{o['value']}", o.get("label", str(o["value"]))), ph)}
                   if isinstance(o, dict) else {"value": o, "label": _fill(S.get(f"{key}.selector.{name}.options.{o}", str(o)), ph)} for o in sel["select"].get("options") or []]
    elif "boolean" in sel or t == "boolean": kind = "boolean"
    elif "number" in sel or t in ("integer", "float"): kind = "number"
    elif "text" in sel and sel["text"].get("type") == "password": kind = "password"
    elif t == "select" and f.get("options"):
        kind = "select"; options = [{"value": o, "label": _fill(S.get(f"{key}.step.{sid}.data.{name}.{o}", str(o)), ph)} if not isinstance(o, list) else {"value": o[0], "label": str(o[1])} for o in f["options"]]
    elif name in ("password", "pin", "token", "api_key", "access_token", "code") and t == "string": kind = "password" if name in ("password", "token", "api_key", "access_token") else "text"
    lbl = S.get(f"{key}.step.{sid}.data.{name}") or name.replace("_", " ").capitalize()
    hint = S.get(f"{key}.step.{sid}.data_description.{name}", "")
    out = {"name": name, "kind": kind, "label": _fill(lbl, ph), "hint": _fill(hint, ph), "required": bool(f.get("required")), "default": f.get("default")}
    if options is not None: out["options"] = options
    return out
