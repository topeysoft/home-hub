# home-hub

A smart home hub built on the principle **own the experience and the intelligence, rent the drivers**.
Plan of record: https://claude.ai/code/artifact/cc81890a-a928-4c6f-a65d-7844fe67fbcb

## Layout

- `docs/inventory.md` — Phase 1 device inventory. `inventory.draft.md` and `discovery.json` are generated.
- `tools/discover.py` — mDNS + SSDP scan of the LAN from a Mac. Seeds the inventory.
- `driver-layer/` — Phase 2. Docker Compose for the rented layer: Home Assistant Core (headless),
  Mosquitto, Zigbee2MQTT, Z-Wave JS UI, python-matter-server. Runs on the hub host.
- `brain/` — Phase 3. Python/FastAPI service on :8300: semantic home model, room-state intent
  engine, event log, websocket stream. Talks only to HA's websocket. Serves `app/dist`.
- `app/` — Phase 3. Vue PWA for the wall kiosk and phone (`npm run build` → served by the brain).

## Temporary driver layer on the Mac (until the Pi arrives)

Running now: `driver-layer/docker-compose.mac.yml` (Home Assistant + Mosquitto, no radios, no host
networking so devices are added by IP). Owner login and the brain's long-lived token are in
`driver-layer/.env` (gitignored). HA UI: http://localhost:8123 or http://192.168.86.59:8123 on the LAN.
Bootstrap was `python3 tools/ha_bootstrap.py --cast <ips>`; rerun on the Pi with a fresh config dir.
HACS is installed manually from its release zip into `homeassistant/custom_components/hacs`.

HA still has no home location (0°,0°, which is why `sun.sun` is wrong) and no weather. The panel
asks for the location once on its Home screen and, on save, writes it into HA and adds the Met.no
integration itself. Until then it assumes sunrise 6:45 and sunset 19:45, or reads
`HOME_LAT`/`HOME_LON` from `driver-layer/.env`.

### HTTPS for the panel

`caddy` in both compose files fronts the brain with TLS from its own local certificate authority:
`https://<mac>:8443/` today, `https://hub.local/` on the Pi. Browsers need a secure origin for
device location, web push and a clean Add to Home Screen. One-time step per tablet or phone: send it
`driver-layer/caddy/data/caddy/pki/authorities/local/root.crt`, install it, and on iOS also switch on
full trust for it under Settings → General → About → Certificate Trust Settings.

## Phase 2 quick start (on the hub host)

```sh
sudo apt install -y docker.io docker-compose-plugin
cp driver-layer/.env.example driver-layer/.env   # set ZIGBEE_SERIAL, ZWAVE_SERIAL from ls -l /dev/serial/by-id/
cd driver-layer && docker compose up -d
```

Then: HA at `http://<host>:8123` (create the owner account, add a long-lived token for the brain),
Zigbee2MQTT at `:8080`, Z-Wave JS UI at `:8091` (set the websocket server on, and add the
`zwave_js` integration in HA pointing at `ws://<host>:3000`), Matter via the `matter` integration
pointing at `ws://<host>:5580/ws`.

### Brilliant

Brilliant has no official API. Do not use the HomeKit path (pairings drop, entities stick in
setup_retry). Use the community `brilliant-mqtt` bridge instead: an MIT-licensed agent that runs on
each Control panel over the panel's own **Root SSH Login** setting and publishes every wired load,
BLE-mesh dimmer switch, plug, motion and power reading to Mosquitto. One panel is elected to bridge
the whole mesh, with failover.

1. On each Control panel: Settings → enable *Root SSH Login*, set a root password.
2. Install HACS into the HA container: `docker exec -it homeassistant bash -c "wget -O - https://get.hacs.xyz | bash -"`, restart HA, add the HACS integration.
3. HACS → custom repository `joyfulhouse/brilliant-mqtt` → install → add the integration with each panel's IP and root password.
4. Add the `mqtt` integration in HA pointing at `mosquitto:1883` if not already done.

Phase 2 is done when every row in `docs/inventory.md` marked *keep* is visible over the HA websocket.

## Hardware to order

- Pi 5 8 GB + NVMe HAT + SSD (hub host)
- Home Assistant Connect ZBT-1 (Zigbee + Thread border router)
- Zooz ZST39 (Z-Wave 800)
- ratgdo32 (garage door, Security+ 2.0 only)

## Rules that do not change

- Works with the internet down.
- HA is touched only through its websocket API; its UI is the Advanced door, never the product.
- The assistant model writes and explains rules. It never executes one.
