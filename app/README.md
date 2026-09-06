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
clock and the home's location. Until a location is known the Home screen carries one soft
"Where is home?" card; it opens a sheet that can use the device's own location (only on https or
localhost, where browsers allow it), find the hub's rough position from its internet address, or
search for a town by name, and it also accepts typed coordinates. Saving sends the location to the
brain, which remembers it in `brain/settings.json`, writes it into Home Assistant (so `sun.sun`
becomes correct) and sets up the free Met.no integration if no weather entity exists yet. The
footer of Home shows the current place with a Change link. `HOME_LAT`/`HOME_LON` in
`driver-layer/.env` still work as a headless fallback. Preview any moment with `?at=19:30`, any
condition with `?wx=rainy` (Home Assistant's condition names), the resting screen with `?rest=1`
and the sheet with `?sheet=location`.

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
