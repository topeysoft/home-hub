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
clock over the sky; a touch brings it back to Home.

## The sky

Behind everything is a live sky: the sun and moon where they really are, stars, clouds, rain, snow,
fog and lightning, with a landscape the interface sits on. The sun is computed in the app from the
clock and the home's location (`/ambient` from the brain: Home Assistant's location, or
`HOME_LAT`/`HOME_LON` in `driver-layer/.env`); without a location it assumes a plausible day.
Weather comes from the first `weather.*` entity in Home Assistant, so add the free Met.no
integration once the location is set and it appears on its own. Preview any moment with
`?at=19:30`, any condition with `?wx=rainy` (Home Assistant's condition names), and the resting
screen with `?rest=1`.

## How it is put together

- `src/store.ts` — the one place that knows the house: rooms, live link, scenes and what each one
  will do, optimistic actions with a toast when the house refuses, activity lines and the plain-
  English "Recently" list built from the brain's event log.
- `src/views/HomeView.vue`, `src/views/RoomView.vue` — the two screens.
- `src/SceneBar.vue` — scene buttons; each shows its effect for the room it is in.
- `src/tiles/` — one tile per capability. The light tile is the dimmer (tap toggles, drag dims).
  Media shows artwork, transport and volume. Cameras open full screen in `src/Viewer.vue`.
- `src/Sky.vue`, `src/sun.ts` — the sky canvas and the solar maths behind it.
- `src/panel.css` — the whole look: tokens, the veil over the sky, layouts down to phone width.

Nothing in the app names a Home Assistant entity or shows a setting; that is the Advanced door.
