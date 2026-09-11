# brain

The product's core. Builds a semantic home from the driver layer, executes room intents
deterministically, logs every event, streams changes to the app, and runs first-time setup so
nobody has to open Home Assistant.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py          # finds HA at http://localhost:8123 (HA_URL / HA_TOKEN in ../driver-layer/.env override)
curl localhost:8300/setup/status  # {"driver": "ready", "setup_done": true, ...}
curl localhost:8300/home
curl -X POST localhost:8300/devices/media_player.nadine_s_room_roku_tv/off
curl -X POST localhost:8300/rooms/<room_id>/intent/asleep
curl -X POST localhost:8300/home/intent/away          # the same intent in every room; a device that refuses is skipped
curl localhost:8300/rules                             # the rules and whether the file is usable
curl localhost:8300/rules/welcome-home/dry-run        # what a rule would do this instant, every condition with its value
curl localhost:8300/rooms/<room_id>/why               # the last few times the room was set, held or shadowed, and by what
```

## Tests

```sh
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q                   # all of them, in about four seconds
.venv/bin/python -m unittest tests.test_rules -v      # one file, and `python -m unittest` still works on any of them
.venv/bin/python -m pytest tests -q --cov=hub         # with coverage, which CI holds to a floor
.venv/bin/ruff check .                                # the linter CI runs
```

`tests/apptest.py` is the harness for anything that makes a request: it builds a Hub whose settings,
event log, phones and rules all live in a temp directory, puts it where `hub/api.py`'s module-level
one sits, and hands the test a `TestClient` and a fake driver layer. A test never touches the
developer's own house.

`tests/sun-positions.json` is one table of sun positions that both `hub/sun.py` and the panel's
`app/src/sun.ts` are checked against, because they are the same calculation written twice and
nothing else would notice them drifting apart. Regenerate it with `tests/make_sun_positions.py`
only when the maths is meant to change.

Docker: `docker build -f brain/Dockerfile -t home-hub/brain .` from the repo root builds the panel
in. CI (`.github/workflows/brain-image.yml`) publishes the same image for amd64 and arm64 as
`ghcr.io/topeysoft/home-hub-brain` on every push to main and every `v*` tag; the compose file pulls
that and builds locally only as a fallback. `HUB_DATA` is where settings and the event log live
(`/data` in the image), `HUB_PORT` the port.

## Life of the hub

`Hub.run()` is a loop that never gives up. The driver state it exposes on `/setup/status` and over
the stream is one of: `down` (HA not answering), `fresh` (HA has no owner yet), `needs-login`
(HA is set up but we hold no key), `connecting`, `ready`. It retries on its own; the setup
endpoints just nudge it along.

- On a **fresh** engine, `POST /setup/owner {name, home}` creates the owner account with a
  generated password, finishes HA's onboarding, mints a long-lived token, and saves all of it to
  `settings.json`. About a second.
- On an engine someone set up by hand, `POST /setup/login {username, password}` signs in and
  mints the token the same way.
- `POST /setup/done` marks the walkthrough finished. Delete `settings.json` to run it again.
- `POST /setup/pin {pin}` sets, changes or (empty) removes the code on the settings. With a code set,
  every request that changes the house (adding, renaming, moving, rooms, location, rules, `/setup/*`,
  and `GET /setup/advanced`, the engine's own sign-in) needs an `X-Hub-Code` header; the panel asks
  once per tab. Driving the house never does. Five wrong codes from one address wait a minute.
  `hub/lock.py` decides which paths count and keeps only a salted hash.

## Files

- `hub/api.py` — the Hub lifecycle and every route.
- `hub/ha_adapter.py` — the only file that speaks HA's websocket. One adapter per connection.
- `hub/ha_setup.py` — HA's onboarding and auth endpoints, used once.
- `hub/provision.py` — the driver layer finishes itself: probes MQTT, Z-Wave JS UI, Zigbee2MQTT,
  Matter and ring-mqtt at their compose addresses, adds the missing integrations to HA by walking
  their config flows, and reports each part in `drivers` on `/setup/status` for the panel.
  `POST /setup/drivers` looks now instead of at the next half-minute. `HUB_DRIVER_HOST` in `.env`
  is where HA reaches the other containers (`localhost` with host networking, a container name on the Mac).
- `hub/comfort.py` — a thermostat sensing its room from another sensor (`POST /devices/{id}/sense`).
- `hub/camera.py` — live video for the viewer: WebRTC signalling relayed to HA over the
  `/devices/{id}/webrtc` socket (the frames never touch the brain), and HA's motion JPEG passed
  through at `/devices/{id}/stream` for cameras or browsers that cannot do WebRTC.
  The number on the card becomes what that room should reach; the brain keeps the thermostat's
  setpoint offset by the difference between the two readings, one correction every 90 s at most,
  in heat or cool only, logged with `source=comfort`. Kept in `settings.json` under `comfort`.
  Nest's own remote sensors never reach HA, so this is how the house does what the Nest app does.
- `hub/pairing.py` — pairing over the hub's own radios, one session at a time (`/pair`): Zigbee opens
  Zigbee2MQTT's join window over MQTT and listens to its bridge events; Z-Wave runs Z-Wave JS
  inclusion, grants the security classes a device asks for and asks the person for an S2 PIN when
  one is needed; Matter commissions with the code printed on the device. The adapter's `subscribe()`
  carries these streams. Whatever joins lands in New devices.
- `hub/onboarding.py` — finding and adding devices: what HA discovered (`/discovered`), the
  catalog, config flows as plain forms, and accounts that need a key of their own: when HA wants
  application credentials (Nest, Google, Tesla, SmartThings…), `/flows` returns a `credentials` step
  with a guide in the house's words; `POST /credentials` keeps the key in HA and starts the flow.
  Step descriptions arrive as small HTML (bold, links, numbered steps) from HA's own text.
  catalog of things addable by brand (`/catalog`), and config flows rewritten as plain forms with
  the integration's own English labels (`/flows`).
- `hub/model.py` — home → rooms → devices → one capability each. Small vocabulary on purpose.
  Devices without a room sit in "New devices"; `/devices/{id}/move` and `/rename` place and name them.
- `hub/intents.py` — room states and the deterministic plan for each. The plans live in `scenes.json`,
  with `_hold`: how long a state set by hand keeps rules off the room.
- `hub/rules.py` — signals in, room intents out. `rules.json` holds the rules (`when … if … then …`);
  the Engine fires them on state changes and a one-second tick, through the same path as a tap, and
  logs every firing with `source=rule` and the reasons. `hub/sun.py` is the sun math it uses.
  Design and vocabulary: `../docs/phase4-intelligence.md`.
- `hub/events.py` — append-only SQLite log; the assistant explains from it.
- `hub/settings.py` — `settings.json`: engine login, names, location, setup flag. Gitignored.
