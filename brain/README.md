# brain

The product's core. Builds a semantic home from the driver layer, executes room intents
deterministically, logs every event, and streams changes to the app.

```sh
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py          # reads HA_URL / HA_TOKEN from ../driver-layer/.env
curl localhost:8300/home
curl -X POST localhost:8300/devices/media_player.nadine_s_room_roku_tv/off
curl -X POST localhost:8300/rooms/<room_id>/intent/asleep
```

- `hub/ha_adapter.py` — the only file that knows Home Assistant exists.
- `hub/model.py` — home → rooms → devices → one capability each. Small vocabulary on purpose.
- `hub/intents.py` — room states and the deterministic plan for each. Rules will move to data.
- `hub/events.py` — append-only SQLite log; the assistant explains from it.
- `hub/api.py` — REST + websocket for the app.
