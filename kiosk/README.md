# The wall

An Android home screen that is the panel.

A tablet on a wall with a browser open is still a tablet: chrome across the top, a screen that sleeps
on its own schedule, a swipe that escapes to somebody's home screen, and nothing that brings it back
after a power cut. This is the small piece of native code that closes that gap, and it is the only
native code in the repo. `docs/apps.md` says why it comes before any phone app.

It draws nothing of its own except the screen it shows while it is looking for the house. **The panel
comes from the hub**, so a wall is never a version behind the box it is hanging next to, and a panel
change lands on the wall the moment the hub updates — no store, no second client, nothing to sign.

## What it actually does

- **Is the home screen.** `MAIN` + `HOME`, so the tablet boots into the house and the home button
  leads back to it rather than out of it. A power cut ends on the panel with nobody touching anything.
- **Stays awake and full screen.** No status bar, no navigation bar, no address bar, no sleep.
- **Finds the house by itself.** See below — this is most of the reason it is native code.
- **Comes back on its own.** Two minutes of the hub not answering and the wall says so and starts
  looking again; when the house returns it reloads, so a hub that restarted on a new build hands over
  a new panel. Shorter drops are left alone: the panel already repairs its own stream.
- **Opens nothing but the house.** A link anywhere but this box does nothing; there is no internet on
  the wall. The Advanced door — Home Assistant's own UI on :8123 — is this box, so it still opens.
- **Has one way out:** the top left corner — the clock's corner, where the panel has no control —
  held for three seconds. That opens a small sheet: the hub's address, *Reload*, and *Leave kiosk*.
  Nobody finds it by accident and a guest does not find it at all.

The corner is watched, never taken: a tap there still reaches the panel underneath. A kiosk that
swallowed a corner would swallow whatever the panel later puts in it.

## Finding the house

A browser on a tablet often cannot resolve `hub.local` at all — Android's own resolver only learned
mDNS recently, and wall tablets are usually older than that. So the wall asks in this order:

1. an address someone typed on the sheet, if there is one,
2. the address that worked last time,
3. `hub.local`, for the tablets that can,
4. the network itself: `_home-hub._tcp` over mDNS, then any `_http._tcp` whose name looks like a hub.

Whatever answers `/phones/me` the way the brain does is the house. That route and not `/health`:
a house with a code on it turns away every route but a handful, and a wall that has not joined yet is
a stranger like any other. Nothing else on the Wi-Fi can pretend to be it by accident, and a hub that
moved to a new address on a new lease is found again without anybody typing anything.

`install.sh` publishes the `_home-hub._tcp` record on the hub. A hub installed before that lands is
found by the other three ways, or by typing its address once.

## Building it

Needs a JDK and the Android SDK (platform 34); nothing else.

```sh
cd kiosk
./gradlew :app:assembleDebug          # app/build/outputs/apk/debug/app-debug.apk
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Then hang it on the wall:

```sh
adb shell cmd package set-home-activity app.elyir.kiosk/.Wall
```

On the tablet itself: open it once, press home, and choose *Elyir* and *Always*.

### The tablet that is a wall panel for good

With the app made device owner, the wall pins itself properly: no status bar, no keyguard, and no
way out but the corner. On a tablet with **no account signed in** (a factory reset one, which is what
a wall panel should be):

```sh
adb shell dpm set-device-owner app.elyir.kiosk/.Admin
```

It is optional. Everything above works without it; the pinning is the only difference.

## What it does not do, on purpose

- **No second panel.** It has no idea what a room or a light is. If it ever grows one, the rule in
  `docs/apps.md` has been broken and the plan is wrong.
- **No certificate, no relay, no store.** The wall is a device the hub's owner controls, on plain
  `http` on their own Wi-Fi. None of `docs/away.md` applies to it.
- **No microphone yet — and when it grows one it will recognise nothing.** A WebView has no Web
  Speech API — `SpeechRecognition` simply does not exist in it — so `docs/voice.md`'s shape 1 cannot
  run on this wall as written. Settled 14 September 2026: the wall does **not** get Android's own
  recogniser. On-device recognition arrived in API 31 and still waits on a model the tablet has to
  fetch; anything older is a round trip to a cloud; and a recogniser of any kind wants a recognition
  service on the device, which in practice means Play services. `minSdk` here is 23, and a wall
  tablet is usually the oldest thing in the house. It gets `AudioRecord` and a bridge that hands the
  panel an audio stream, and the hub does the listening — `docs/voice.md`, *The wall's microphone is
  the hub's ear*. Capturing natively also sidesteps the secure context `getUserMedia` would have
  wanted and a WebView cannot be given. None of it exists yet, down to the `RECORD_AUDIO` this
  manifest does not ask for: the wall stays deaf until shape 2 exists on the hub, and the panel's own
  path in a phone browser is unaffected either way.
