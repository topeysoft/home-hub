# app

The wall panel and the phone view, one progressive web app. Home first, then rooms: the Home
screen says what is on, offers the two house-wide scenes, and shows every camera; a room shows
its scenes and its devices in the product vocabulary. Live over the brain's websocket.

```sh
npm install
npm run dev      # Vite on :5173, proxies /home /devices /rooms /events /stream to the brain on :8300
npm run build    # writes dist/, which the brain serves at http://<host>:8300/
```

Kiosk: open http://hub.local/ full-screen on the wall tablet (Add to Home Screen on iOS/Android).
`?room=<id>` opens straight into a room. After three minutes without a touch the panel rests on a
clock over the sky; a touch brings it back to Home.

## First run

Until the brain says setup is done, the panel shows `src/Setup.vue` instead of the house: welcome,
your name and the home's name (which creates the engine login behind the scenes), where home is,
which rooms, what to add, done. Every step after the names can be skipped. `?setup=1&page=rooms`
previews any screen. The same pieces live on after setup: `src/AddPanel.vue` (found nearby, add by
brand, and the short form each one needs) sits in the *Add a device* sheet, and `src/SortView.vue`
is the *New devices* room where unplaced things get a name and a room.

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
- `src/Setup.vue`, `src/AddPanel.vue`, `src/SortView.vue`, `src/LocationPicker.vue` — first run and
  the few things a person is ever asked: names, code, place, rooms, devices.
- `src/PairPanel.vue` — the door for a Zigbee, Z‑Wave or Matter device, offered on the Add sheet for
  each radio that is up: what to press, a live line while the hub listens, the S2 code when a lock
  asks, and what joined.
- `src/code.ts`, `src/CodePrompt.vue`, `src/CodeSheet.vue` — the code on the settings. Every request
  goes through `request()`, which attaches the code kept for this tab and, when the hub answers 401
  `code`, asks for it and retries. Controls never ask; changes do. `?sheet=code` previews the sheet.
- `src/tiles/` — one tile per capability. The light tile is the dimmer (tap toggles, drag dims).
  Media shows artwork, transport and volume. Cameras open full screen in `src/Viewer.vue`.
- `src/Sky.vue`, `src/sun.ts` — the sky canvas and the solar maths behind it.
- `src/panel.css` — the whole look: tokens, the veil over the sky, layouts down to phone width.

Nothing in the app names a Home Assistant entity or shows a setting; that is the Advanced door.
