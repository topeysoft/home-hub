"""Finding and adding devices, in the product's words.

Home Assistant discovers things on the network and offers "config flows" for them: short forms.
This module lists what was found, starts flows for things the user asks for, and turns each step
of a flow into a plain form the panel can draw, with the integration's own English labels.
"""
import asyncio, html, json, logging, os, re, urllib.error, urllib.request

log = logging.getLogger("hub.add")

# Accounts that make every home bring its own key (OAuth "application credentials"): what to do, in
# the house's words. HA supplies the URLs as placeholders; {redirect_url} is the one to paste into the
# maker's site, {ha_url} is what to type if a page asks for the Home Assistant address.
GUIDES = {
    "nest": """Google asks each home to bring its own key. It takes about ten minutes, and Google charges a one-time US $5 for Nest access.

1. Open the [Google Cloud credentials page]({oauth_creds_url}) and, if asked, create a project.
1. On the [consent screen]({oauth_consent_url}) choose **External**, add your own Google account as a test user, and save.
1. Back on the credentials page choose **Create credentials**, then **OAuth client ID**, type **Web application**, and add this redirect: **{redirect_url}**
1. Copy the client ID and client secret into the boxes below.

The next screens walk through the Nest side, one step at a time. If a page asks for your Home Assistant address, it is **{ha_url}**.""",
    "google": """Google asks each home to bring its own key. It takes a few minutes and costs nothing.

1. Open the [Google Cloud credentials page]({oauth_creds_url}) and, if asked, create a project.
1. On the [consent screen]({oauth_consent_url}) choose **External**, add your own Google account as a test user, and save.
1. Back on the credentials page choose **Create credentials**, then **OAuth client ID**, type **Web application**, and add this redirect: **{redirect_url}**
1. Copy the client ID and client secret into the boxes below.

If a page asks for your Home Assistant address, it is **{ha_url}**.""",
}
GENERIC_GUIDE = """{kind} asks each home to bring its own key, made on its developer site ([how]({more_info_url})).

1. Create an app there.
1. Set its redirect address to **{redirect_url}**
1. Copy the client ID and client secret into the boxes below.

If a page asks for your Home Assistant address, it is **{ha_url}**."""

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
        self._creds_cfg: dict | None = None
        self._hints: dict[str, dict] = {}     # handler -> {field: value} learned earlier (a key file's project ID) to prefill later steps

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
            self._catalog = catalog_from(((r.get("core") or {}).get("integration") or {}))
        return self._catalog

    # ---- accounts that need a key of their own ----
    async def _creds_config(self) -> dict:
        if self._creds_cfg is None:
            try: self._creds_cfg = await self.hub.ha.send("application_credentials/config") or {}
            except Exception as e: log.warning("no application credentials support: %s", e); self._creds_cfg = {}
        return self._creds_cfg

    async def needs_credentials(self, handler: str) -> dict | None:
        """The step to show before this integration can start, or None when it can start now."""
        cfg = await self._creds_config()
        if handler not in (cfg.get("domains") or []): return None
        try: existing = await self.hub.ha.send("application_credentials/list")
        except Exception: existing = []
        if any(c.get("domain") == handler for c in existing): return None
        return await self.credentials_step(handler)

    async def credentials_step(self, handler: str) -> dict:
        cfg = await self._creds_config()
        ph = dict(((cfg.get("integrations") or {}).get(handler) or {}).get("description_placeholders") or {})
        kind = await self.name_of(handler)
        ph.setdefault("redirect_url", "https://my.home-assistant.io/redirect/oauth")
        ph.setdefault("more_info_url", f"https://www.home-assistant.io/integrations/{handler}/")
        ph.update(kind=kind, ha_url=f"http://{self.hub.env.get('HUB_HOST') or os.environ.get('HUB_HOST') or 'hub.local'}:8123")
        guide = GUIDES.get(handler) or GUIDES.get(handler.split("_")[0]) or GENERIC_GUIDE
        return {"flow_id": None, "handler": handler, "kind": kind, "type": "credentials", "step_id": "credentials",
                "title": f"{kind} needs a key of its own", "description": _md(guide, ph), "last_step": None,
                "redirect_url": ph["redirect_url"], "fields": [
                    {"name": "client_id", "kind": "text", "label": "Client ID", "hint": "", "required": True, "default": None},
                    {"name": "client_secret", "kind": "password", "label": "Client secret", "hint": "", "required": True, "default": None}]}

    async def set_credentials(self, handler: str, client_id: str, client_secret: str, hints: dict | None = None) -> dict:
        """Keep the key in HA, then start the integration's flow as if nothing had been in the way. `hints` are
        answers the key file already held (Google's carries the Cloud project ID) for fields that come later."""
        await self.hub.ha.send("application_credentials/create", domain=handler, client_id=client_id, client_secret=client_secret, name="home-hub")
        self.hub.log.add("home", "credentials", None, handler, source="user")
        if hints: self._hints[handler] = {k: v for k, v in hints.items() if isinstance(v, str) and v.strip()}
        return await self.start(handler)

    # ---- running a flow ----
    async def start(self, handler: str) -> dict:
        need = await self.needs_credentials(handler)
        if need: return need
        step = await asyncio.to_thread(self._rest, "POST", "/api/config/config_entries/flow", {"handler": handler, "show_advanced_options": False})
        if step.get("type") == "abort" and step.get("reason") == "missing_credentials":
            return await self.credentials_step(handler)
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
               "title": _fill(S.get(f"{key}.step.{sid}.title", ""), ph), "description": _md(S.get(f"{key}.step.{sid}.description", ""), ph),
               "last_step": step.get("last_step")}
        if step.get("type") == "form":
            errs = step.get("errors") or {}
            out["errors"] = {k: _fill(S.get(f"{key}.error.{v}", v), ph) for k, v in errs.items()}
            out["fields"] = [_field(f, S, key, sid, ph) for f in (step.get("data_schema") or [])]
            for f in out["fields"]:
                if f["name"] in self._hints.get(h, {}) and f["default"] in (None, ""): f["default"] = self._hints[h][f["name"]]
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


def catalog_from(core: dict) -> list[dict]:
    """HA groups some makers as brands (Google holds Nest, Cast, Calendar…; Philips holds Hue). Flatten them
    so every addable thing is one row, and keep the brand so a search for it finds them."""
    items = []
    def take(domain, d, brand=None):
        if not d.get("config_flow") or d.get("integration_type") not in KINDS or domain in HIDE: return
        items.append({"domain": domain, "name": d.get("name") or domain.replace("_", " ").title(), "brand": brand,
                      "local": (d.get("iot_class") or "").startswith("local")})
    for domain, d in core.items():
        kids = d.get("integrations")
        if isinstance(kids, dict):
            for sub, k in kids.items(): take(sub, k, brand=d.get("name") or domain)
        else:
            take(domain, d)
    items.sort(key=lambda x: x["name"].lower())
    return items


def _fill(s: str, ph: dict) -> str:
    if not s: return s
    s = re.sub(r"\{(\w+)\}", lambda m: str(ph.get(m.group(1), m.group(0))), s)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


def _md(s: str, ph: dict) -> str:
    """HA writes its step descriptions in a little markdown: bold, links, numbered steps. Turn that into the
    small HTML the panel shows, with placeholders filled and everything else escaped."""
    if not s: return ""
    s = re.sub(r"\{(\w+)\}", lambda m: str(ph.get(m.group(1), m.group(0))), s)
    s = html.escape(re.sub(r"<[^>]+>", "", s), quote=False)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    out, items = [], []
    def flush():
        if items: out.append("<ol>" + "".join(f"<li>{i}</li>" for i in items) + "</ol>"); items.clear()
    for line in s.split("\n"):
        line = line.strip()
        m = re.match(r"^(?:\d+\.|-|\*)\s+(.*)", line)
        if m: items.append(m.group(1)); continue
        flush()
        if line: out.append(f"<p>{line}</p>")
    flush()
    return "".join(out)


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
