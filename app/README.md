# app

The wall panel and the phone view, one progressive web app. Home first, then rooms: the Home
screen says what is on, offers the two house-wide scenes, and shows every camera; a room shows
its scenes and its devices in the product vocabulary. Live over the brain's websocket.

```sh
npm install
npm run dev      # Vite on :5173, proxies /home /devices /rooms /events /stream to the brain on :8300
npm run build    # writes dist/, which the brain serves at http://<host>:8300/
```

Kiosk: open http://<hub>:8300/ full-screen on the wall tablet (Add to Home Screen on iOS/Android).
`?room=<id>` opens straight into a room. After three minutes without a touch the panel rests on a
clock; a touch brings it back to Home.

## How it is put together

- `src/store.ts` — the one place that knows the house: rooms, live link, scenes and what each one
  will do, optimistic actions with a toast when the house refuses, activity lines and the plain-
  English "Recently" list built from the brain's event log.
- `src/views/HomeView.vue`, `src/views/RoomView.vue` — the two screens.
- `src/SceneBar.vue` — scene buttons; each shows its effect for the room it is in.
- `src/tiles/` — one tile per capability. The light tile is the dimmer (tap toggles, drag dims).
  Media shows artwork, transport and volume. Cameras open full screen in `src/Viewer.vue`.
- `src/panel.css` — the whole look: tokens, ambient time-of-day glow, layouts down to phone width.

Nothing in the app names a Home Assistant entity or shows a setting; that is the Advanced door.
