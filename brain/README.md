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
```

Docker: `docker build -f brain/Dockerfile -t home-hub/brain .` from the repo root builds the panel
in. `HUB_DATA` is where settings and the event log live (`/data` in the image), `HUB_PORT` the port.

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

## Files

- `hub/api.py` — the Hub lifecycle and every route.
- `hub/ha_adapter.py` — the only file that speaks HA's websocket. One adapter per connection.
- `hub/ha_setup.py` — HA's onboarding and auth endpoints, used once.
- `hub/onboarding.py` — finding and adding devices: what HA discovered (`/discovered`), the
  catalog of things addable by brand (`/catalog`), and config flows rewritten as plain forms with
  the integration's own English labels (`/flows`).
- `hub/model.py` — home → rooms → devices → one capability each. Small vocabulary on purpose.
  Devices without a room sit in "New devices"; `/devices/{id}/move` and `/rename` place and name them.
- `hub/intents.py` — room states and the deterministic plan for each. The plans live in `scenes.json`.
- `hub/events.py` — append-only SQLite log; the assistant explains from it.
- `hub/settings.py` — `settings.json`: engine login, names, location, setup flag. Gitignored.
