# home-hub

A smart home hub built on the principle **own the experience and the intelligence, rent the drivers**.
Plan of record: https://claude.ai/code/artifact/cc81890a-a928-4c6f-a65d-7844fe67fbcb

## For the person receiving one

1. Plug the hub into power and the router (or its Wi‑Fi). Wait two minutes.
2. On a phone or tablet on the same Wi‑Fi, open **http://hub.local**.
3. Answer the questions on the screen: your name, where home is, which rooms, what to add.

That is the whole setup. Devices already on the Wi‑Fi (TVs, speakers, bridges) are noticed on
their own and offered under *Found nearby*; anything else is added by brand from the same screen.
Things that live behind an account (Nest, Ring, Tesla) sign in from that screen too. A few, Google's
Nest first among them, make every home bring its own key; the screen walks through getting one, with
the exact address to paste and a copy button, and the maker's own steps follow one at a time. The key
file Google hands out can be dropped or pasted straight onto that screen instead of copying its parts.
Things that don't know their room wait under *New devices* until you place them. Nothing on the
panel ever mentions Home Assistant, entities, or YAML.

## For the person building one

Any Linux box with systemd is a hub host: a Raspberry Pi 5, an Intel NUC, a mini PC, a VM under
Proxmox, running Debian, Ubuntu, Raspberry Pi OS or Fedora. One line:

```sh
curl -fsSL https://raw.githubusercontent.com/topeysoft/home-hub/main/install.sh | sudo bash
```

`install.sh` installs Docker, names the machine `hub` (so it answers at `hub.local`), writes
`driver-layer/.env`, pulls the brain image (CI publishes it for amd64 and arm64; it is built locally
only if the pull fails), and starts everything with Docker Compose. Radio sticks can be plugged in
before or after: `driver-layer/radios.sh` finds them, and a udev rule reruns it whenever one is
plugged in or pulled. Radios on the network (an Ethernet Zigbee coordinator, a PoE Z-Wave dongle)
go in `.env` as `ZIGBEE_NET` / `ZWAVE_NET` and the host needs no USB at all. The brain creates its
own login to the driver layer during the on-screen setup and adds MQTT, Z-Wave and Matter to it by
itself, so there is no token to copy and no Home Assistant UI to visit.

A flashed image rather than an install runs `driver-layer/host/firstboot.sh` once through
`home-hub-firstboot.service`: everything Pi-specific (bootloader, PCIe for an NVMe base, copying
itself from SD to an empty NVMe) happens there, then the install script. The Pi image that ships
with that unit enabled is the next piece of work; until then the steps below get a Pi to the same place.

macOS is for developing, not for running the house: Docker Desktop cannot hand USB sticks to
containers, cannot pass multicast (so no mDNS discovery), and needs someone logged in. See
*Developing on the Mac* below.

### Getting a Pi 5 to that point

1. In Raspberry Pi Imager pick Raspberry Pi OS Lite (64-bit). In its settings set the hostname to
   `hub`, your user and SSH key, the timezone, and Wi‑Fi only as a fallback; Ethernet is what a hub wants.
2. Flash the NVMe SSD directly if you have a USB enclosure, otherwise the SD card. A third-party NVMe
   base needs `dtparam=pciex1` in `config.txt` on the boot partition; the official M.2 HAT+ does not.
3. Boot with no SD card inserted to boot from NVMe. If it does not, boot the SD card once, run
   `sudo rpi-eeprom-update -a`, set NVMe first under Advanced Options → Boot Order in `raspi-config`,
   and clone the card to the SSD with `rpi-clone`.
4. `sudo apt update && sudo apt full-upgrade -y && sudo rpi-eeprom-update -a && sudo reboot`, then
   the one line above.

Sticks go in the USB 2 ports on a short extension cable; USB 3 and the NVMe are noisy neighbours for
Zigbee in particular. Moving from a Mac that ran the stack: copy `driver-layer/ring-mqtt/` across
first to skip Ring's sign-in, do not copy `driver-layer/homeassistant/`, and stop the Mac's ring-mqtt
container before the Pi's first start so the two do not fight over Ring's token.

## Layout

- `install.sh` — the one-command install for the hub host. `driver-layer/radios.sh` finds the Zigbee and
  Z-Wave sticks and starts their containers; a udev rule runs it again whenever a stick is plugged in or pulled.
- `driver-layer/` — Docker Compose for the whole hub: Home Assistant Core (headless), Mosquitto,
  Zigbee2MQTT and Z‑Wave JS UI (profiles, on only when a stick is found), python-matter-server,
  the brain, and Caddy as the front door (`http://hub.local`, plus `https://` for those who install
  the root certificate).
- `brain/` — Python/FastAPI service on :8300: semantic home model, room-state intent engine, event
  log, websocket stream, first-run setup, device discovery. Talks only to HA's websocket and REST.
  Serves `app/dist`. `brain/Dockerfile` packages it with the panel built in.
- `app/` — Vue PWA for the wall kiosk and phone (`npm run build` → served by the brain).
- `docs/inventory.md` — Phase 1 device inventory. `tools/discover.py` seeds it from a Mac.
- `docs/phase4-intelligence.md` — Phase 4 design: rules as data, the evaluator, holds, presence, the assistant's contract.
- `tools/ha_bootstrap.py` — the old manual bootstrap; the brain's setup screen does this now.

## Developing on the Mac (until the Pi arrives)

`driver-layer/docker-compose.mac.yml` runs Home Assistant, Mosquitto and Caddy in Docker with no
radios and no host networking (Docker Desktop on macOS cannot do mDNS discovery, so devices are
added by IP or by brand). The brain runs from its venv (`cd brain && .venv/bin/python main.py`) and
finds HA at `http://localhost:8123`. Panel: `http://localhost:8300/` (or `:8088` through Caddy).

The brain keeps what it learns in `brain/settings.json` (gitignored): the engine login it created,
the owner's and home's names, the location, whether setup finished. Delete the file to run setup
again. `driver-layer/.env` can still carry `HA_URL`/`HA_TOKEN` as a developer override.

Preview any panel state from the address bar: `?setup=1&page=rooms` (a setup screen), `?rest=1`
(the resting clock), `?sheet=add` (the add-a-device sheet), `?at=19:30`, `?wx=rainy`.

### HTTPS

Caddy fronts the brain on plain `http://hub.local` with nothing to install, and on `https://` from
its own local certificate authority. Browsers need a secure origin for device location, web push and
a clean Add to Home Screen; for that, install
`driver-layer/caddy/data/caddy/pki/authorities/local/root.crt` on the tablet or phone once (iOS
also wants full trust on under Settings → General → About → Certificate Trust Settings). Everything
else works over plain http.

## Radios and the Advanced door

Nothing here needs a visit. The brain watches the driver layer and adds each part to Home Assistant
itself when it answers: MQTT, the Z-Wave radio (Z-Wave JS UI's settings, including its network
keys, are written once by `radios.sh`), and Matter. The panel's *Behind the scenes* list shows each
part's state; Ring is the one that needs a person, once, to sign in. Plugging a stick in later
starts its container and connects it the same way.

For the curious: Zigbee2MQTT admin is on `:8080`, Z‑Wave JS UI on `:8091`, and Home Assistant on
`:8123`, the Advanced door, linked from the bottom of the location and add sheets, never the product.

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

## Hardware to order

- Pi 5 8 GB + NVMe HAT + SSD (hub host)
- Home Assistant Connect ZBT-1 (Zigbee + Thread border router)
- Zooz ZST39 (Z-Wave 800). Optional while the Nortek HUSBZB-1 on hand covers Z-Wave: it is 500-series, fine for the GE/Jasco switches, no Long Range.
- ratgdo32 (garage door, Security+ 2.0 only)

## Rules that do not change

- Works with the internet down.
- HA is touched only through its APIs; its UI is the Advanced door, never the product.
- The assistant model writes and explains rules. It never executes one.
- Setup is a conversation on the screen, never a file to edit.
- Controlling the house never needs a code. Changing it does, once one is set.
