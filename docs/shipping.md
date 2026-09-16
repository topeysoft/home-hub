# Shipping it: the hardware, and what changes before a stranger pays

*Written 16 September 2026, when the question was asked directly: this is starting to look like a product, so what
should change, what is missing, and what does the box actually become? The short answers are below; the sections
after them are the reasoning, so a session picking this up cold can disagree with a specific line rather than with
a feeling. `docs/updates.md`, `docs/away.md` and `docs/settings.md` each own their piece; this document does not
repeat them, it points at them and says what sits between.*

## The short answers

| Question | Answer |
|---|---|
| **Change direction?** | No. The three rules that make this sellable are already the ones the code keeps: the house works without the maker, the panel never needs Home Assistant's UI, and the driver layer is pinned. What is thin is the appliance under the product, not the product. |
| **Is the Pi still first?** | Yes. Raspberry Pi has committed to keep both the Pi 5 and the Compute Module 5 in production until at least January 2036, and the whole image, first-boot and NVMe path already exists for it. |
| **Pi 5 or Compute Module?** | Sell a CM5, not a Pi 5. The reasons are storage, supply and radios, and none of them is about speed. A Pi 5 stays the developer and early-adopter kit. |
| **x86?** | Bring-your-own, as today. It is the right box for local speech and the wrong box to put a name on before an ODM run makes sense. |

## Rules that do not change

- **The house never depends on the maker.** Not for a tap, not for a lock, not for the panel coming up. A maker
  service (relay, manifest, backups) adds something; its absence removes only that thing. `docs/away.md`.
- **Nothing on the panel, the box, or the notes mentions Home Assistant.** It is Apache-2.0 and may be shipped; its
  name is a trademark of the Open Home Foundation and may not be used to sell this.
- **The host is whatever runs the house.** A Pi 5 is the floor, not the design point. Anything sized for a NUC must
  degrade to the Pi rather than exclude it. `docs/voice.md` has the host-class table.
- **Size the compliance burden to the volume.** A pre-certified module, a partner carrier and a certified supply keep
  a first run to an unintentional-radiator test. A custom radio on a custom board is a different business.

## The hardware

### Why a Compute Module and not a Pi 5

Longevity is not the difference; both have the same published production commitment. The differences that matter
for a unit that leaves the building:

- **Storage.** A Pi 5 boots from a microSD card or from an NVMe somebody assembled onto a HAT. Home Assistant's
  recorder and the brain's event log write all day, and card wear is the classic way a Home Assistant box dies at
  month eight, with a family and no ssh. The CM5 carries eMMC on the module: no card, no HAT, no drive to fit.
- **Supply.** One part number with one supplier and one end-of-life date, instead of a board, a HAT, a drive, a
  cooler, a case and a supply from five vendors that each change without telling anyone.
- **Radios, later.** Home Assistant Yellow is the precedent: a Compute Module on a carrier with a pre-certified
  Silicon Labs Zigbee/Thread module soldered on. Modular approval on the radio is what keeps the carrier out of
  intentional-radiator testing. That is the v2 board, once the numbers say so, and the CM is what makes it possible
  without changing the software at all.

### The staged path

Each step pays for the next only if the previous one sold. Nothing here has non-recurring cost before the volume
that justifies it.

| Stage | Unit | What it needs | What it is honest as |
|---|---|---|---|
| **Now, tens** | Pi 5, 4 GB minimum, NVMe in an Argon ONE V3 style case or the official case plus M.2 HAT+, official 27 W supply, active cooler, RTC battery | Nothing new: the image and `firstboot.sh` already copy to an empty NVMe | An early-adopter kit, assembled by hand, and nothing more |
| **v1, hundreds** | CM5 with 4 or 8 GB and 32 GB eMMC on a partner carrier and enclosure (Waveshare, EDATEC, Seeed and others sell CM5 boxes with RTC, metal case, often PoE) | The image built for eMMC rather than SD; the *Powered by Raspberry Pi* programme for the logo; a Part 15B test on the assembled unit | A product with a serial on it |
| **v2, if it takes off** | Custom carrier with an integrated Zigbee/Thread module | Board design, tooling, and the compliance that comes with a radio | Not before the numbers |
| **Bring-your-own** | An Intel N100-class mini PC or NUC, as `install.sh` supports today | Nothing | The voice tier: faster-whisper *small* or *medium* on the hub itself |

**Memory.** 4 GB is the floor: Home Assistant Core, Zigbee2MQTT, Z-Wave JS UI, the Matter server, Mosquitto, Caddy and
the brain fit with room; 2 GB does not. 8 GB is what the small voice tier in `docs/voice.md` wants.

**What the unit must have, whichever stage.** eMMC or NVMe, never a card. An RTC with a battery, because a box that
boots in 1970 cannot verify a certificate and the relay's certificate is the first thing it will need. A hardware
watchdog, enabled, because an unattended box must reboot itself out of a hang. Active cooling inside a sealed
enclosure, because a throttled Pi 5 looks like a slow panel. A certified supply. Ethernet. PoE as an option, because
one cable is the whole install. A way to factory-reset without a screen. A status LED that a support call can ask
about.

### Radios: on the network, not on the USB port

The hub already takes a Zigbee or Z-Wave coordinator over the network (`ZIGBEE_NET` / `ZWAVE_NET` in `.env`). Make
that the shipped shape. A PoE Zigbee coordinator (an SMLIGHT SLZB-06 or similar) sits wherever the radio should sit,
which is never next to an NVMe and a USB 3 port, and the instruction about the extension cable disappears with it. It
also means a hub with no USB at all, which is what a CM5 box or a mini PC wants to be.

Z-Wave stays an add-on rather than a bundle: it needs a regional radio per market (US, EU, ANZ and more), which is a
SKU per region for a feature not every house uses.

**Thread is a decision, not a default.** Matter over Wi-Fi works with what is here. Matter over Thread needs a border
router radio of its own; the multiprotocol firmware that let one stick do Zigbee and Thread at once is deprecated
upstream, so it is two radios or no Thread. Decide it for v1 rather than discovering it in a house.

### What was considered and set aside

- **Selling an x86 box.** An N100 mini PC is the right host for local speech and costs less than the Pi kit above,
  but selling one means a white-label box with somebody else's sticker or an ODM order with a minimum quantity and a
  BIOS nobody controls. It stays the supported bring-your-own tier.
- **A Rockchip board** like the one in Home Assistant Green: cheaper per unit, and it comes with the kernel and
  bootloader as your problem. Nabu Casa needed a hardware partner for that, and this is not the stage for it.
- **Selling the wall tablet.** Consumer tablets churn faster than they can be stocked. The kiosk is an Android
  launcher; publish a tested-models list and let the tablet be bought, and revisit only if a PoE wall panel from an
  ODM turns out to be what customers ask for. `docs/apps.md`.

## Before a stranger pays

Checked against the tree on 16 September 2026, not assumed. Where another document owns the piece, it says so.

### Landed, or owned elsewhere

- **Undo for an update that does not come back** landed today (`docs/updates.md`, piece 1), with the signature,
  overnight updates, notes for a house and the rollout hold as the next four. Nothing here repeats it.
- **The relay, the certificate per hub and the public name** are `docs/away.md`. A hub identifier is needed by both
  that and the updates plan; it is small and is in the list below because nothing else provides it.
- **The Pi image already ships as an appliance should**: no password, SSH off, first-boot with no terminal step.
- **The settings code as a required setup step** rather than a nudge is called for at the end of `docs/updates.md`
  and is not repeated here. Everything below that says *behind the code* assumes it.

### Open on the LAN, and should not be

This was the finding of the day, and the first thing done. *(Closed 16 September 2026, except where a line below
says otherwise.)* `driver-layer/mqtt-auth.sh` makes the broker's password once into `.env`, writes the broker's password file, and
renders Ring's `config.json` from a tracked template (in Docker, ring-mqtt reads only that file); compose hands it to
Zigbee2MQTT; the brain gives it to the engine through HA's own reconfigure flow, so an existing Messages
entry keeps every device it brought in (`brain/hub/provision.py`, `mqtt_auth` in settings is the fingerprint of what
the engine was last told). Zigbee2MQTT's and Z-Wave JS UI's consoles and the Matter server's websocket bind to
loopback in `docker-compose.yml`. **Still on the Wi-Fi, on purpose for now:** Messages on `:1883`, because
`brilliant/esp32-bridge` publishes to it from the network, and it now takes a password; Home Assistant on `:8123`,
because it has a sign-in of its own with a password the brain made up, and because binding it to loopback needs a
door of its own through Caddy (the open decision below); and Ring's sign-in form on `:55123`, which can only ever
replace the house's Ring token with a different Ring account's, and which the panel does not link to. The list as it
was found:

- **Mosquitto accepts anyone.** `driver-layer/mosquitto/config/mosquitto.conf` has `allow_anonymous true` on
  `1883`, published to the Wi-Fi. Anyone on the network can publish to `zigbee2mqtt/<device>/set` and unlock a
  Zigbee lock, or open `permit_join` and pair a device of their own. The code in `lock.py` guards the panel; it does
  not guard this door, and a guest's laptop is behind it.
- **The admin consoles are open too.** Zigbee2MQTT's UI on `8080`, Z-Wave JS UI on `8091` and its websocket on
  `3000`, the Matter server on `55123`, and Home Assistant itself on `8123` because it runs on the host network. Each
  can pair, remove or drive a device with no code. They are the *Advanced* door, and the Advanced door has no lock.
- **Locks, garage and alarm need no phone at home.** `needs_code()` in `brain/hub/lock.py` is the whole list of what
  is guarded, and it is about changing the house, which is right for a light. It is not right for a deadbolt once
  money changes hands. Now that phones pair, the kinds `lock`, `cover` where it is a garage, and `alarm` can require
  a paired phone even on the Wi-Fi, which is one more line in the same middleware.

### The appliance layer

- **Watchdog, log caps, journal cap** *(landed 16 September 2026)*: `driver-layer/host/harden.sh`, run by
  `install.sh` on every install and update. systemd pets the hardware watchdog every 30 s and the Pi's is switched
  on in `config.txt` when it is off; Docker's `json-file` logs are capped at 10 MB x 3 per container through
  `/etc/docker/daemon.json` (merged, not replaced, and the containers are made again once to take it); the journal
  at 200 MB. Mosquitto now logs to its container rather than to a file that only grew. **No firewall still**: the
  loopback binds do that work, and a firewall written by an installer onto a box somebody set up by hand is how
  that person gets locked out of it.
- **The recorder is at Home Assistant's defaults.** Ten days of history and a commit every second. Fine on NVMe,
  unkind to eMMC; a longer commit interval and the exclusion of chatty sensors is configuration, not code.
- **Wi-Fi onboarding.** Wi-Fi is set at flash time. A customer whose router has no free port needs the hub to raise
  a setup network of its own and take the home Wi-Fi from a phone. Ethernet first, access point as the fallback.
  This one needs hardware in hand and is not a today item.
- **Per-unit identity.** A serial, a claim code printed on the box, a hub identifier that rides the backup. Two hubs
  on one Wi-Fi collide on `hub.local` today: avahi renames the second one and nothing tells the panel, so the code
  on the wall points at the wrong house. *This hub* should show the name the hub actually answers to.
- **Factory reset.** From the panel, behind the code, today: the mirror of `restore.sh`, a path unit that stops the
  house, empties `brain-data/` and the driver layer's state, and starts setup again. A physical hold waits for the
  enclosure, because it is a button.
- **A diagnostics bundle** from *This hub*, distinct from the backup: versions, health lines, the last hour of logs,
  the update log, no keys. What a support conversation asks for first.
- **Remote support.** Owner-started, time-boxed, over the relay connection once it exists. Not before the relay.
- **Fleet check-in.** The one line of telemetry in `docs/updates.md` piece 5, and nothing more about the house.

### The paper

- **Supported integrations, in tiers.** Ring goes through an unofficial API that Ring can close on a Tuesday. Nest
  makes every household create its own Google project. Publish a short list tested on every release and call the
  rest best-effort, or the support load is the product.
- **Licences and notices.** Home Assistant, the Matter server and Caddy are Apache-2.0; Zigbee2MQTT is GPL-3 and runs
  as its own container, which is fine provided its source is offered; Z-Wave JS UI and ring-mqtt are MIT; Mosquitto
  is EPL/EDL. A notices page on *This hub* and a written offer of source is the whole of the obligation, and it is a
  day's work.
- **Privacy and the assistant.** Home data goes to the model's API when a key is set. That needs a sentence of
  consent where the key is pasted, a privacy policy, and eventually the maker's key through the relay with metering
  rather than a customer pasting one. The relay, the assistant and encrypted cloud backup of the existing archive are
  the subscription; the Terraform that `docs/away.md` already requires is where they live.
- **Certification.** A CM5 with wireless carries its own modular approval; a partner carrier carries the vendor's.
  The assembled unit needs Part 15B (US) and the CE/UKCA equivalents, the supply needs to be one that is already
  certified, and a radio on the board changes all of that, which is why it is v2.

## What can be done today, in order

Each of these is code or configuration in this repository, needs no hardware that is not on the bench, and is small
enough to land with a test. The order is by what it closes.

1. **Close the LAN doors.** *(Done, 16 September 2026, as described above.)* What was not done, and why: Home
   Assistant's `8123` stays on the Wi-Fi with its own sign-in, because binding it to loopback needs a door through
   Caddy behind the pairing first, and that door is the open decision below rather than a line in this list.
2. **Locks behind a paired phone at home.** One rule in the middleware next to the phone cookie: a `lock`, `alarm`
   or garage `cover` action needs a paired phone whether the request came from the Wi-Fi or the relay. The wall is
   paired, so the wall is unaffected; a guest's laptop is not.
3. **Watchdog, log caps, journald.** *(Done, 16 September 2026: `driver-layer/host/harden.sh`.)*
4. **The recorder on eMMC terms.** A `recorder:` block with a longer `commit_interval` and shorter
   `purge_keep_days`. Not as simple as it reads: `driver-layer/homeassistant/` is the engine's own directory, made by
   the engine on its first start and not in the repository, so the block has to be seeded by the installer or by the
   brain when the directory is empty, and left alone after. The brain's event log already has its own cap.
5. **A hub identifier.** Random, made once, in `settings.json`, riding the backup. `docs/updates.md` piece 5 and
   `docs/away.md` both need it and neither wants to be the one to invent it.
6. **The name the hub answers to.** The brain asks avahi what it is actually called and *This hub* and the QR code
   say that, so two hubs on one Wi-Fi each point at themselves.
7. **Factory reset from the panel.** `reset.sh` and a path unit shaped like `restore.sh`, behind the code, with the
   wall asking twice.
8. **A diagnostics bundle.** A second archive next to the backup, without the keys.
9. **Notices and the tested list.** A page under *This hub*, and `docs/integrations.md` with the tiers.
10. **A consent sentence where the key is pasted.** One line on the Routines sheet, and the privacy policy it points
    at.

Not today, and why: Wi-Fi onboarding and the physical reset need the unit in hand; remote support and the maker's key
wait on the relay; the hardware-in-the-loop bench in CI needs one hub per tier on a shelf; and everything about
updates is `docs/updates.md`.

## Open decisions

- **Which partner carrier for v1**, chosen by what it certifies and what it costs at a hundred, not by what it
  benchmarks. The software does not care.
- **Thread in v1 or not.** Two radios or none; the answer changes the carrier.
- **Whether the Advanced door survives at all**, now that the other LAN doors are closed. A door behind the code
  that opens the engine's UI is still a door to Home Assistant, which the product says does not exist. It may be that
  the right number of ways to reach the engine from the Wi-Fi is zero and ssh is the Advanced door. If it survives,
  the shape is one Caddy site per console with `forward_auth` to the brain, which answers yes only for a paired phone
  that holds keys: cookies do not care about ports, so `hub.local:8123` sees the same cookie as `hub.local`. That is
  the same mechanism for Ring's form and for the engine, and the reason neither moved today.
- **What a guest may drive from the Wi-Fi without a phone** once locks need one. Lights, yes. Cameras and the front
  door, no. Blinds and the thermostat are the argument.
