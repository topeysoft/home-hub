"""Pairing a radio device from the panel.

One session at a time. Zigbee opens Zigbee2MQTT's join window over MQTT and listens to its bridge
events; Z-Wave asks Z-Wave JS to include a node and answers its questions (security classes are
granted as asked, an S2 PIN is asked of the person); Matter commissions with the code on the
device. Whatever joins lands in Home Assistant, then in the house under New devices.
"""
import asyncio, json, logging, time

log = logging.getLogger("hub.pair")
WINDOW = 240        # seconds a join window stays open
TOPIC_EVENT, TOPIC_JOIN = "zigbee2mqtt/bridge/event", "zigbee2mqtt/bridge/request/permit_join"
KINDS = {"zigbee": "Zigbee", "zwave": "Z-Wave", "matter": "Matter"}


class Pairing:
    def __init__(self, hub):
        self.hub = hub
        self.session: dict | None = None
        self._sub: int | None = None
        self._timer: asyncio.Task | None = None
        self._entry: str | None = None      # zwave_js config entry, needed by every Z-Wave command

    # ---- what the panel sees ----
    def status(self) -> dict:
        if not self.session: return {"state": "idle"}
        s = dict(self.session)
        s["seconds_left"] = max(0, int(s.get("until", 0) - time.time())) if s.get("until") else None
        s.pop("until", None)
        return s

    def _set(self, state, text, **more):
        if not self.session: return
        self.session.update(state=state, text=text, **more)
        self.hub._broadcast(json.dumps({"type": "pair", "pair": self.status()}))

    # ---- starting and stopping ----
    async def start(self, kind: str, code: str | None = None) -> dict:
        if kind not in KINDS: raise ValueError("Zigbee, Z-Wave or Matter.")
        if self.session and self.session["state"] in ("listening", "found", "pin", "working"): await self.stop()
        self.session = {"kind": kind, "state": "working", "text": "Opening the door…", "device": None, "needs": None, "until": None}
        try:
            if kind == "zigbee": await self._start_zigbee()
            elif kind == "zwave": await self._start_zwave()
            else: await self._start_matter(code or "")
        except Exception as e:
            log.warning("%s pairing could not start: %s", kind, e)
            self._set("failed", f"Could not start: {e}")
        return self.status()

    async def stop(self) -> dict:
        s = self.session
        if self._timer: self._timer.cancel(); self._timer = None
        if self._sub is not None:
            try: await self.hub.ha.unsubscribe(self._sub)
            except Exception: pass
            self._sub = None
        if s and s["kind"] == "zigbee":
            try: await self.hub.ha.call("mqtt", "publish", None, topic=TOPIC_JOIN, payload=json.dumps({"time": 0}))
            except Exception: pass
        if s and s["kind"] == "zwave" and self._entry:
            try: await self.hub.ha.send("zwave_js/stop_inclusion", entry_id=self._entry)
            except Exception: pass
        if s and s["state"] in ("listening", "found", "pin", "working"):
            self._set("closed", "Stopped.")
        return self.status()

    def _arm(self, seconds=WINDOW):
        self.session["until"] = time.time() + seconds
        if self._timer: self._timer.cancel()
        self._timer = asyncio.create_task(self._expire(seconds))

    async def _expire(self, seconds):
        await asyncio.sleep(seconds)
        if self.session and self.session["state"] in ("listening", "found"):
            await self.stop()
            self._set("closed", "Nothing joined. Put the device in pairing mode and try again; a factory reset usually does it.")

    # ---- Zigbee, through Zigbee2MQTT over MQTT ----
    async def _start_zigbee(self):
        self._sub = await self.hub.ha.subscribe("mqtt/subscribe", self._on_zigbee, topic=TOPIC_EVENT)
        await self.hub.ha.call("mqtt", "publish", None, topic=TOPIC_JOIN, payload=json.dumps({"time": WINDOW}))
        self._arm()
        self._set("listening", "Listening. Put the device in pairing mode: for most, hold its button until the light blinks, or switch it off and on a few times.")

    def _on_zigbee(self, ev):
        try: m = json.loads(ev.get("payload") or "{}")
        except Exception: return
        t, d = m.get("type"), m.get("data") or {}
        name = d.get("friendly_name") or d.get("ieee_address") or "a device"
        if t in ("device_joined", "device_announce"):
            self._set("found", f"Something is joining… ({name})", device={"id": d.get("ieee_address"), "name": name})
        elif t == "device_interview":
            st = d.get("status")
            if st == "started": self._set("found", "Found it. Asking what it is…", device={"id": d.get("ieee_address"), "name": name})
            elif st == "successful":
                defn = d.get("definition") or {}
                what = " ".join(x for x in (defn.get("vendor"), defn.get("description") or defn.get("model")) if x) or name
                supported = d.get("supported", True)
                asyncio.create_task(self._finish_zigbee(what, supported, d.get("ieee_address")))
            elif st == "failed":
                self._set("failed", "It joined but would not say what it is. Move it closer to the hub and try again.")

    async def _finish_zigbee(self, what, supported, ieee):
        self._set("done" if supported else "failed",
                  f"{what} joined the house. Find it under New devices to name it and pick its room." if supported
                  else f"{what} joined, but this kind is not supported yet. It will show up with whatever it can do.",
                  device={"id": ieee, "name": what})
        self.hub.log.add("home", "device", None, what, source="user", detail={"paired": "zigbee", "id": ieee})
        await self.stop()

    # ---- Z-Wave, through Z-Wave JS ----
    async def _zwave_entry(self) -> str:
        rows = await self.hub.ha.send("config_entries/get")
        for e in rows:
            if e.get("domain") == "zwave_js" and e.get("state") == "loaded": return e["entry_id"]
        raise RuntimeError("the Z-Wave radio is not connected")

    async def _start_zwave(self):
        self._entry = await self._zwave_entry()
        self._sub = await self.hub.ha.subscribe("zwave_js/add_node", self._on_zwave, entry_id=self._entry, inclusion_strategy=0)
        self._arm()
        self._set("listening", "Listening. Press the device's button (often three times quickly) or follow its own pairing steps.")

    def _on_zwave(self, ev):
        e = ev.get("event")
        if e == "node found": self._set("found", "Found it. Bringing it in…")
        elif e == "grant security classes":
            req = (ev.get("requested_grant") or {})
            classes = req.get("securityClasses") or req.get("security_classes") or []
            asyncio.create_task(self._grant(classes, bool(req.get("clientSideAuth") or req.get("client_side_auth"))))
        elif e == "validate dsk and enter pin":
            self._set("pin", "This one is secured. Type the 5-digit code printed on it (the first five digits of its DSK, on a sticker or the box).", needs="pin", dsk=ev.get("dsk"))
        elif e == "node added":
            node = ev.get("node") or {}
            self._set("found", "It's in. Asking what it is…" + (" It joined without security." if ev.get("low_security") else ""), device={"id": node.get("node_id"), "name": None})
        elif e == "interview stage completed":
            self._set("found", f"Getting to know it… ({ev.get('stage')})")
        elif e == "device registered":
            dev = ev.get("device") or {}
            name = dev.get("name_by_user") or dev.get("name") or " ".join(x for x in (dev.get("manufacturer"), dev.get("model")) if x) or "The device"
            self.session["device"] = {"id": dev.get("id"), "name": name}
        elif e == "interview completed":
            name = (self.session.get("device") or {}).get("name") or "The device"
            self._set("done", f"{name} joined the house. Find it under New devices to name it and pick its room.")
            self.hub.log.add("home", "device", None, name, source="user", detail={"paired": "zwave"})
            asyncio.create_task(self.stop())
        elif e == "interview failed":
            self._set("failed", "It joined but the hub could not finish learning about it. Wake it (press its button) and try again.")
        elif e in ("inclusion failed", "inclusion aborted"):
            self._set("failed", "Pairing did not complete. Factory-reset the device and try again.")
        elif e == "inclusion stopped" and self.session and self.session["state"] == "listening":
            self._set("closed", "Stopped.")

    async def _grant(self, classes, csa):
        try: await self.hub.ha.send("zwave_js/grant_security_classes", entry_id=self._entry, securityClasses=classes, clientSideAuth=csa)
        except Exception as e: log.warning("grant failed: %s", e)

    async def pin(self, pin: str) -> dict:
        if not self.session or self.session.get("needs") != "pin": raise ValueError("Nothing is asking for a code right now.")
        if not (pin.isdigit() and len(pin) == 5): raise ValueError("The code is 5 digits.")
        await self.hub.ha.send("zwave_js/validate_dsk_and_enter_pin", entry_id=self._entry, pin=pin)
        self._set("found", "Checking the code…", needs=None)
        return self.status()

    # ---- Matter, with the code on the device ----
    async def _start_matter(self, code: str):
        code = code.strip()
        if not code: raise ValueError("The pairing code on the device is needed.")
        self._set("working", "Talking to it. This takes up to a minute.")
        self._timer = asyncio.create_task(self._commission(code))

    async def _commission(self, code):
        try:
            await self.hub.ha.send("matter/commission", code=code, network_only=False)
            self._set("done", "It joined the house. Find it under New devices to name it and pick its room.")
            self.hub.log.add("home", "device", None, "Matter device", source="user", detail={"paired": "matter"})
        except Exception as e:
            msg = str(e)
            hint = "Check the code, make sure the device is in pairing mode and on the same Wi‑Fi (or in range of the hub's Thread radio), and try again."
            self._set("failed", f"Could not bring it in. {hint}" + (f" ({msg})" if msg else ""))
