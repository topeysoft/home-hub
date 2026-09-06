# app

The wall panel and the phone view, one progressive web app. Room-first: pick a room, see its
devices in the product vocabulary, set a room intent. Live over the brain's websocket.

```sh
npm install
npm run dev      # Vite on :5173, proxies /home /devices /rooms /events /stream to the brain on :8300
npm run build    # writes dist/, which the brain serves at http://<host>:8300/
```

Kiosk: open http://<hub>:8300/ full-screen on the wall tablet (Add to Home Screen on iOS/Android).
