# Device inventory (Phase 1)

One row per physical device. "Done" means no row has a `?` left. Seed from `inventory.draft.md`
(regenerate with `python3 tools/discover.py`), then add the Z-Wave, Zigbee and cloud devices by hand.

Control path legend: **local** = works with the internet down, **cloud** = vendor API,
**bridge** = local through a vendor bridge (Hue), **none** = no known integration.

| Device | Room | Vendor / model | Protocol | Control path | HA integration | Decision | Notes |
|---|---|---|---|---|---|---|---|
| Hue bridge | ? | Philips Hue | Wi-Fi + Zigbee | bridge (local API) | `hue` | deferred | unplugged; not needed for v1 |
| Main Bedroom speaker (Home Mini) | Bedroom | Google | Wi-Fi | local (cast) | `cast` | in HA | 192.168.86.33/36/37 are the three Minis |
| Nadine's room speaker (Home Mini) | Nadine's room | Google | Wi-Fi | local (cast) | `cast` | in HA |  |
| Theater speaker (Home Mini) | Theater | Google | Wi-Fi | local (cast) | `cast` | in HA |  |
| Bedroom TV (Cast) | Bedroom | Android TV | Wi-Fi | local | `cast` | in HA | 192.168.86.65; also `androidtv_remote` for power/input, needs on-screen PIN |
| Roku TV | Nadine's room | Roku | Wi-Fi | local | `roku` | in HA | 192.168.86.64 |
| Matter device 3425BEC06C79 | ? | ? | Matter | local | `matter` | identify | one operational Matter node on the LAN |
| Tesla Wall Connector Gen 3 | garage | Tesla | Wi-Fi | local (vitals API) | `tesla_wall_connector` | in HA | 192.168.86.23; a car was plugged in at setup |
| Ring (cameras/doorbell) | ? | Ring | Wi-Fi | cloud | `ring` | keep | list each device |
| Brilliant Control panels (each) | ? | Brilliant NextGen | Wi-Fi | local via brilliant-mqtt agent on panel | HACS `joyfulhouse/brilliant-mqtt` | keep | enable Root SSH Login in panel settings; one panel is elected to bridge all mesh devices |
| Brilliant Smart Dimmer Switches (each) | ? | Brilliant NextGen | BLE mesh via a Control | local via elected panel | brilliant-mqtt (mesh) | keep | list every switch with its room and the load it drives |
| Brilliant Smart Plugs (each) | ? | Brilliant NextGen | BLE mesh via a Control | local via elected panel | brilliant-mqtt (mesh) | keep |  |
| GE (Z-Wave switches?) | ? | GE / Jasco | Z-Wave | local once on Z-Wave stick | `zwave_js` | keep, re-pair | list each device |
| Wink hub + devices | ? | Wink | Zigbee / Z-Wave | none | `-` | drop hub, re-pair devices |  |
| LiftMaster/Chamberlain garage opener (myQ) | garage | Chamberlain | myQ cloud (blocked) | none; add ratgdo board | `esphome` via ratgdo | keep, needs ratgdo | check learn button: yellow/purple works, white (Security+ 3.0) does not |
| Apple HomeKit accessories (each) | ? | ? | Wi-Fi/Thread HAP | local via HomeKit Device | `homekit_controller` | list them | pair after the Pi (needs mDNS); remove from Apple Home first |
| Anycubic Kobra 3 Max | workshop | Anycubic | Wi-Fi | cloud (LAN partial) | custom | out of scope | 192.168.86.62 |
| obi1 / r2d2 / c3po printers | workshop | Klipper | Ethernet | local | `moonraker` (HACS) | out of scope for v1 |  |
