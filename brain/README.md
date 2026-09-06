# brain

The product's core. Builds a semantic home from the driver layer, executes room intents
deterministically, logs every event, and streams changes to the app.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py          # reads HA_URL / HA_TOKEN from ../driver-layer/.env
curl localhost:8300/home
curl -X POST localhost:8300/devices/media_player.nadine_s_room_roku_tv/off
curl -X POST localhost:8300/rooms/<room_id>/intent/asleep
curl -X POST localhost:8300/home/intent/away          # the same intent in every room; a device that refuses is skipped
```

- `hub/ha_adapter.py` — the only file that knows Home Assistant exists.
- `hub/model.py` — home → rooms → devices → one capability each. Small vocabulary on purpose.
- `hub/intents.py` — room states and the deterministic plan for each. The plans live in `scenes.json`
  (edit it and the next scene uses the new rules; `GET /scenes` serves it to the app).
- `hub/events.py` — append-only SQLite log; the assistant explains from it.
- `hub/api.py` — REST + websocket for the app. Also `/ambient` (location + weather for the sky), `/location`
  (saves the home's place, syncs it to HA, sets up Met.no) and `/geo/*` (search, auto-locate, reverse).
- `settings.json` — the few things the panel is allowed to set, today just the location. Gitignored.
