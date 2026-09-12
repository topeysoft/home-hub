/*
 * Draws design/Devices.dc.html from src/art.ts.
 *
 * The sheet and the panel were the same sixteen drawings kept by hand in two
 * places, which lasted exactly as long as the first fix: the blades on the
 * sheet's fan are still 56 long, three pixels over the edge, because that was
 * corrected in art.ts and nowhere else. This removes the second copy.
 *
 *   node mock/art-sheet.mjs          writes ../design/Devices.dc.html
 *   node mock/art-sheet.mjs --check  fails if the file on disk is out of date
 *
 * The trick that makes it work: art.ts takes its flat colours from a Materials
 * object, so handing it one whose values are the literal text "{{mat.metalLo}}"
 * produces marks whose fills are canvas holes. Geometry comes out literal and in
 * order, gradients keep relighting through the defs, and the Sky chip still
 * moves the whole shelf -- with no drawing data duplicated anywhere.
 */
import { createServer } from 'vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(HERE, '..', '..', 'design', 'Devices.dc.html')

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
const art = await server.ssrLoadModule('/src/art.ts')
await server.close()

/* every material, as the hole that will stand for it on the canvas */
const HOLES = Object.fromEntries(
  ['metalLo', 'metalMid', 'matteHi', 'matteLo', 'darkHi', 'darkLo', 'shadeHi', 'shadeLo', 'fabricHi', 'fabricLo', 'screenHi', 'screenLo']
    .map((k) => [k, `{{mat.${k}}}`]))

const marksOf = (kind, state) => art.device(kind, state, HOLES).marks
const svg = (marks, indent) => marks
  .map((m) => `${indent}<${m.el} ${Object.entries(m.at).map(([k, v]) => `${k}="${v}"`).join(' ')}/>`)
  .join('\n')

/* ---------- what the shelf holds ---------- */

const ICON = {
  light: 'M9.5 18h5M10.5 21h3M12 3a6 6 0 0 0-3.7 10.7c.7.6 1.1 1.4 1.2 2.3h5c.1-.9.5-1.7 1.2-2.3A6 6 0 0 0 12 3z',
  camera: 'M3.5 8.5h17v10h-17zM12 16.5a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM8.5 8.5l1.5-3h4l1.5 3',
  climate: 'M10 4.5a2 2 0 0 1 4 0v8.8a4 4 0 1 1-4 0zM12 9.5v8',
  media: 'M6.5 3.5h11a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1v-15a1 1 0 0 1 1-1zM12 17a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4zM12 8h.01',
  lock: 'M6 11h12v9.5H6zM9 11V8a3 3 0 0 1 6 0v3M12 15v2',
  switch: 'M12 3.5v8.5M6.6 6.6a7.6 7.6 0 1 0 10.8 0',
  fan: 'M12 13.8a1.8 1.8 0 1 0 0-3.6 1.8 1.8 0 0 0 0 3.6zM12 10.2c0-3.2 1.4-5.2 3.6-5.2 1.8 0 2.4 1.6 1 3.2-1.2 1.4-2.8 2-4.6 2zM12 13.8c0 3.2-1.4 5.2-3.6 5.2-1.8 0-2.4-1.6-1-3.2 1.2-1.4 2.8-2 4.6-2zM10.2 12c-3.2 0-5.2-1.4-5.2-3.6 0-1.8 1.6-2.4 3.2-1 1.4 1.2 2 2.8 2 4.6zM13.8 12c3.2 0 5.2 1.4 5.2 3.6 0 1.8-1.6 2.4-3.2 1-1.4-1.2-2-2.8-2-4.6z',
  cover: 'M4.5 4.5h15v15h-15zM4.5 9h15M4.5 13.5h15',
  vacuum: 'M12 20.5a8.5 8.5 0 1 0 0-17 8.5 8.5 0 0 0 0 17zM12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z',
  motion: 'M12 13.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3zM7.5 7.5a6.5 6.5 0 0 0 0 9M16.5 7.5a6.5 6.5 0 0 1 0 9M4.5 4.5a10.5 10.5 0 0 0 0 15M19.5 4.5a10.5 10.5 0 0 1 0 15',
}

/* Ordered as the shelf reads: lights first because a house is mostly lights,
   then the things that watch and warm and play, then the rest -- and rung four
   last, on purpose. */
const SHELF = [
  { kind: 'floor-lamp', name: 'Floor lamp', state: 'On, low', lit: true, icon: 'light', tone: 'light', s: { on: true, brightness: 0.3 } },
  { kind: 'table-lamp', name: 'Bedside lamp', state: 'On, warm', lit: true, icon: 'light', tone: 'light', s: { on: true, brightness: 0.55 } },
  { kind: 'ceiling', name: 'Kitchen ceiling', state: 'On, full', lit: true, icon: 'light', tone: 'light', s: { on: true, brightness: 1 } },
  { kind: 'strip', name: 'Under-cabinet strip', state: 'Off', icon: 'light', tone: 'light', s: { on: false } },
  { kind: 'bulb', name: 'Porch bulb', state: 'On', lit: true, icon: 'light', tone: 'light', s: { on: true } },
  { kind: 'pendant', name: 'Dining pendant', state: 'On, low', lit: true, icon: 'light', tone: 'light', s: { on: true, brightness: 0.35 } },

  { kind: 'camera', name: 'Side gate', state: 'All quiet', icon: 'camera', tone: 'cam', live: true, s: { live: true } },
  { kind: 'thermostat', name: 'Hallway', state: 'Cooling to 21&deg;', icon: 'climate', tone: 'clim', s: { cooling: true } },
  { kind: 'speaker', name: 'Kitchen speaker', state: 'Nothing playing', icon: 'media', tone: 'plain', s: {} },
  { kind: 'tv', name: 'Living room TV', state: 'Standby', icon: 'media', tone: 'plain', s: { playing: false } },
  { kind: 'lock', name: 'Back door', state: 'Unlocked', danger: true, icon: 'lock', tone: 'lock', s: { locked: false } },
  { kind: 'plug', name: 'Hallway plug', state: 'Off', icon: 'switch', tone: 'plain', s: { on: false } },

  { kind: 'fan', name: 'Ceiling fan', state: 'On, low', lit: true, icon: 'fan', tone: 'plain', s: { on: true } },
  { kind: 'blind', name: 'Bedroom blinds', state: 'Half open', icon: 'cover', tone: 'plain', s: { position: 0.5 } },
  { kind: 'doorbell', name: 'Front doorbell', state: 'All quiet', icon: 'camera', tone: 'cam', s: { live: true } },
  { kind: 'vacuum', name: 'Vacuum', state: 'Docked', icon: 'vacuum', tone: 'plain', s: { on: false } },
]

/* the floor the ladder stands on: no drawing, and it still has to look deliberate */
const RUNG_FOUR = [
  { name: 'Desk plug', state: 'Off', icon: 'switch', maker: 'Aqara' },
  { name: 'Hall motion', state: 'Still for 40 min', icon: 'motion' },
]

const LAMP_STATES = [
  { label: 'Off', s: { on: false } },
  { label: 'On, 20%', s: { on: true, brightness: 0.2 }, lit: true },
  { label: 'On, 60%', s: { on: true, brightness: 0.6 }, lit: true },
  { label: 'On, full', s: { on: true, brightness: 1 }, lit: true },
]
const BLIND_STATES = [
  { label: 'Shut', s: { position: 0 } },
  { label: 'Half open', s: { position: 0.5 } },
  { label: 'Open', s: { position: 1 } },
]

/* ---------- the page ---------- */

const tile = (c) => `      <div class="tile" style="background: {{t.${c.tone}}}; border: 1px solid ${
  c.tone === 'light' && c.lit ? 'rgba(233,184,114,.34)' : c.danger ? 'rgba(224,138,138,.34)' : '{{t.edge}}'
}; color: {{t.ink}};">
${c.lit && c.tone === 'light' ? '        <div style="position: absolute; inset: 0; background: radial-gradient(84% 66% at 76% 16%, rgba(233,184,114,.26), transparent 62%);"></div>\n' : ''}        <svg class="art" width="164" height="142" viewBox="0 0 150 130">
${svg(marksOf(c.kind, c.s), '          ')}
        </svg>
        <div class="chip" style="background: ${c.lit && c.tone === 'light' ? '#e9b872; color: #2a1c07' : '{{t.chipOff}}'};">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="${ICON[c.icon]}"/></svg>
        </div>
${c.live ? '        <div style="position: absolute; top: 14px; right: 14px; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; padding: 4px 8px; border-radius: 999px; background: #74c69d; color: #0b2216; font-weight: 600;">Live</div>\n' : ''}        <div class="nm">${c.name}<span class="st" style="color: ${c.danger ? '#e08a8a' : c.lit ? '{{t.lampInk}}' : '{{t.sub}}'};">${c.state}</span></div>
      </div>`

const rungFour = (c) => `      <div class="tile" style="background: {{t.plain}}; border: 1px solid {{t.edge}}; color: {{t.ink}};">
        <svg width="150" height="150" viewBox="0 0 24 24" fill="none" stroke="{{t.art}}" stroke-width="1.05" stroke-linecap="round" stroke-linejoin="round" style="position: absolute; right: -28px; bottom: -30px;"><path d="${ICON[c.icon]}"/></svg>
        <div class="chip" style="background: {{t.chipOff}};">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="${ICON[c.icon]}"/></svg>
        </div>
${c.maker ? `        <div style="position: absolute; top: 15px; right: 14px; font-size: 12.5px; letter-spacing: .04em; color: {{t.sub}};">${c.maker}</div>\n` : ''}        <div class="nm">${c.name}<span class="st" style="color: {{t.sub}};">${c.state}</span></div>
      </div>`

const strip = (kind, states, left) => states.map((st) => `      <div style="position: relative; flex: 0 0 auto; width: 170px; height: 150px; border-radius: 18px; overflow: hidden; background: {{t.${kind === 'floor-lamp' ? 'light' : 'plain'}}}; border: 1px solid {{t.edge}}; color: {{t.ink}};">
${st.lit ? '        <div style="position: absolute; inset: 0; background: radial-gradient(84% 66% at 56% 24%, rgba(233,184,114,.30), transparent 62%);"></div>\n' : ''}        <svg width="170" height="132" viewBox="0 0 150 130" style="position: absolute; left: ${left}px; bottom: -6px;">
${svg(marksOf(kind, st.s), '          ')}
        </svg>
        <div style="position: absolute; left: 14px; bottom: 12px; font-size: 14px; font-weight: 500; color: ${st.lit ? '{{t.lampInk}}' : '{{t.sub}}'};">${st.label}</div>
      </div>`).join('\n')

const page = `<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600&family=Instrument+Serif:ital@0;1&display=swap">
  <style>
    *, *::before, *::after { box-sizing: border-box; }
    body { margin: 0; font-family: "Instrument Sans", -apple-system, "SF Pro Text", system-ui, sans-serif; }
    a { color: #e9b872; } a:hover { color: #b8863e; }
    .dsp { font-family: "Instrument Serif", "Iowan Old Style", Palatino, Georgia, serif; font-weight: 400; letter-spacing: -0.01em; }
    .cap { font-size: 13px; letter-spacing: .07em; text-transform: uppercase; color: #7f7d77; }
    .tile { position: relative; height: 190px; border-radius: 22px; overflow: hidden; }
    .art { position: absolute; right: -4px; bottom: -2px; }
    .chip { position: relative; width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center; margin: 16px 0 0 16px; }
    .nm { position: absolute; left: 16px; bottom: 13px; font-size: 15px; font-weight: 500; }
    .st { display: block; margin-top: 2px; font-size: 13.5px; font-weight: 400; }
  </style>
</helmet>

<!-- GENERATED by app/mock/art-sheet.mjs from app/src/art.ts. Do not edit by
     hand: every drawing below is the panel's own geometry, and an edit here
     would put the two back out of step, which is the thing this file exists to
     stop. Change a drawing in art.ts and run the script again. -->

<div style="position: relative; width: 1612px; height: 1160px; overflow: hidden; background: #0c0d10; color: #f1eee8; font-size: 17px; line-height: 1.4;">
  <div style="position: absolute; inset: 0; background: {{f.sky}};"></div>
  <div style="position: absolute; inset: 0; background: {{f.veil}};"></div>
  <div style="position: absolute; inset: 0; opacity: .5; pointer-events: none; background-image: url(&quot;data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .035 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E&quot;);"></div>

  <!-- the same defs the panel mounts once, in ArtDefs.vue -->
  <svg width="0" height="0" style="position: absolute;">
    <defs>
      <linearGradient id="mMetal" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="{{mat.metalLo}}"/><stop offset="45%" stop-color="{{mat.metalMid}}"/><stop offset="100%" stop-color="{{mat.metalLo}}"/>
      </linearGradient>
      <linearGradient id="mPlate" x1="0" y1="0" x2="0.3" y2="1">
        <stop offset="0" stop-color="{{mat.metalMid}}"/><stop offset="100%" stop-color="{{mat.metalLo}}"/>
      </linearGradient>
      <linearGradient id="mMatte" x1="0" y1="0" x2="0.25" y2="1">
        <stop offset="0" stop-color="{{mat.matteHi}}"/><stop offset="100%" stop-color="{{mat.matteLo}}"/>
      </linearGradient>
      <linearGradient id="mShade" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="{{mat.shadeHi}}"/><stop offset="100%" stop-color="{{mat.shadeLo}}"/>
      </linearGradient>
      <linearGradient id="mDark" x1="0" y1="0" x2="0.4" y2="1">
        <stop offset="0" stop-color="{{mat.darkHi}}"/><stop offset="100%" stop-color="{{mat.darkLo}}"/>
      </linearGradient>
      <linearGradient id="mScreen" x1="0.1" y1="0" x2="0.9" y2="1">
        <stop offset="0" stop-color="{{mat.screenHi}}"/><stop offset="58%" stop-color="{{mat.screenLo}}"/><stop offset="100%" stop-color="{{mat.screenHi}}"/>
      </linearGradient>
      <linearGradient id="mFabric" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="{{mat.fabricLo}}"/><stop offset="42%" stop-color="{{mat.fabricHi}}"/><stop offset="100%" stop-color="{{mat.fabricLo}}"/>
      </linearGradient>
      <!-- emitted light, which never takes the ambient: a lamp is warm because it is a lamp -->
      <radialGradient id="mPool" cx="50%" cy="34%" r="64%">
        <stop offset="0" stop-color="#f6dcae" stop-opacity=".62"/><stop offset="54%" stop-color="#e9b872" stop-opacity=".22"/><stop offset="100%" stop-color="#e9b872" stop-opacity="0"/>
      </radialGradient>
      <linearGradient id="mCone" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="#f6dcae" stop-opacity=".46"/><stop offset="100%" stop-color="#e9b872" stop-opacity="0"/>
      </linearGradient>
      <radialGradient id="mGlass" cx="38%" cy="32%" r="76%">
        <stop offset="0" stop-color="#fbeed6" stop-opacity=".95"/><stop offset="62%" stop-color="#f6dcae" stop-opacity=".62"/><stop offset="100%" stop-color="#e9b872" stop-opacity=".22"/>
      </radialGradient>
    </defs>
  </svg>

  <div style="position: absolute; top: 44px; left: 48px; right: 48px;">
    <h1 class="dsp" style="margin: 0; font-size: 38px;">A library, not a shelf of icons</h1>
    <p style="margin: 10px 0 0; font-size: 17px; color: #b9b5ad; max-width: 104ch;">Rung two of <i>When there is no artwork</i>, and the panel&rsquo;s own drawings rather than a picture of them &mdash; every mark below comes out of <code>src/art.ts</code>. One vocabulary holds all of it: a cylinder is a three-stop gradient, anything round seen at an angle is an ellipse, thickness is two ellipses offset, and light a thing emits is a radial that never takes the ambient. What a device is <i>made of</i> does take it, which is why the shelf cools at midday and warms at dusk.</p>
  </div>

  <div class="cap" style="position: absolute; top: 208px; left: 48px;">At tile size &mdash; where they actually live</div>

  <div style="position: absolute; top: 240px; left: 48px; width: 1516px; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 20px;">
${SHELF.map(tile).join('\n')}
${RUNG_FOUR.map(rungFour).join('\n')}
  </div>

  <div class="cap" style="position: absolute; top: 906px; left: 48px;">One drawing, not one per state</div>
  <p style="position: absolute; top: 930px; left: 48px; width: 1030px; margin: 0; font-size: 15px; color: #b9b5ad;">The same handful of marks every time; only the numbers move. The render <i>is</i> the readout &mdash; which is what a progress bar under a name was standing in for.</p>

  <div style="position: absolute; top: 982px; left: 48px; width: 1516px; display: flex; gap: 16px;">
${strip('floor-lamp', LAMP_STATES, -26)}
      <div style="flex: 0 0 auto; width: 20px;"></div>
${strip('blind', BLIND_STATES, 10)}
  </div>
</div>
</x-dc>

<script data-dc-script data-props='{"field":{"editor":"enum","options":["Dusk","Night","Midday"],"default":"Dusk","section":"Sky"},"tone":{"editor":"enum","options":["Warm","Cool","Pastel","Follow the light"],"default":"Follow the light","section":"Tiles"}}'>
/*
 * Only the colours live here. Every shape on this sheet was written out by
 * app/mock/art-sheet.mjs straight from the panel's own art.ts, so the two
 * cannot disagree: there is nothing left to keep in step by hand.
 *
 * What a device is MADE OF takes the ambient; what it EMITS does not. That is
 * why the materials below are holes the sheet fills in per sky, and the pool,
 * cone and glass gradients above are hard-coded.
 */
class Component extends DCLogic {
  renderVals() {
    const lerp = (a, b, t) => a + (b - a) * t;
    const mix = (a, b, t) => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
    const css = (c) => 'rgb(' + c.map((v) => Math.round(v)).join(',') + ')';

    const lin = (c) => (c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
    function oklch(r, g, b) {
      const R = lin(r / 255), G = lin(g / 255), B = lin(b / 255);
      const l = Math.cbrt(0.4122214708 * R + 0.5363325363 * G + 0.0514459929 * B);
      const m = Math.cbrt(0.2119034982 * R + 0.6806995451 * G + 0.1073969566 * B);
      const s = Math.cbrt(0.0883024619 * R + 0.2817188376 * G + 0.6299787005 * B);
      const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s;
      const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
      const Bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
      let H = Math.atan2(Bb, A) * 180 / Math.PI; if (H < 0) H += 360;
      return { L: L, C: Math.hypot(A, Bb), H: H };
    }

    const w0 = { clouds: 0.42, rain: 0, snow: 0, fog: 0 };
    const weather = (c) => {
      let o = mix(c, [58, 64, 72], w0.clouds * 0.55);
      o = mix(o, [22, 24, 30], w0.rain * 0.3);
      return mix(o, [116, 122, 128], w0.fog * 0.3);
    };

    const FIELDS = {
      'Dusk':   { stops: [[10, 14, 34], [38, 34, 74], [158, 84, 60]], at: 44, a: 0.52,
                  veil: 'linear-gradient(180deg, rgba(12,13,16,.30) 0%, rgba(12,13,16,.52) 45%, rgba(12,13,16,.80) 100%)', day: false },
      'Night':  { stops: [[4, 5, 10], [7, 9, 16], [12, 14, 26]], at: 55, a: 0.36,
                  veil: 'linear-gradient(180deg, rgba(12,13,16,.20) 0%, rgba(12,13,16,.36) 45%, rgba(12,13,16,.66) 100%)', day: false },
      'Midday': { stops: [[26, 78, 136], [70, 148, 202], [170, 200, 218]], at: 55, a: 0.34,
                  veil: 'linear-gradient(180deg, rgba(12,13,16,.22) 0%, rgba(12,13,16,.34) 45%, rgba(12,13,16,.58) 100%)', day: true },
    };
    const fd = FIELDS[this.props.field] || FIELDS['Dusk'];
    const st = fd.stops.map(weather);
    const f = {
      day: fd.day, veil: fd.veil,
      sky: 'linear-gradient(180deg, ' + css(st[0]) + ' 0%, ' + css(st[1]) + ' ' + fd.at + '%, ' +
           css(st[2]) + ' 84%, ' + css(mix(st[2], [8, 9, 14], 0.35)) + ' 100%)',
    };
    const veilRGB = [12, 13, 16];
    const ground = oklch(
      st[1][0] * (1 - fd.a) + veilRGB[0] * fd.a,
      st[1][1] * (1 - fd.a) + veilRGB[1] * fd.a,
      st[1][2] * (1 - fd.a) + veilRGB[2] * fd.a
    );

    /* the same BASE table and the same 0.22 as src/art.ts */
    const BASE = {
      metalLo: [74, 70, 64], metalMid: [179, 170, 156],
      matteHi: [242, 239, 232], matteLo: [201, 196, 184],
      darkHi: [58, 61, 68], darkLo: [21, 23, 27],
      shadeHi: [247, 230, 198], shadeLo: [224, 185, 129],
      fabricHi: [122, 116, 104], fabricLo: [78, 74, 66],
      screenHi: [42, 45, 51], screenLo: [15, 17, 20],
    };
    const room = [st[1][0] * (1 - fd.a) + 12 * fd.a, st[1][1] * (1 - fd.a) + 13 * fd.a, st[1][2] * (1 - fd.a) + 16 * fd.a];
    const mat = {};
    for (const k in BASE) mat[k] = css(mix(BASE[k], room, 0.22));

    const WARM = { cam: 92,  clim: 44,  light: 76,  lock: 66  };
    const COOL = { cam: 175, clim: 300, light: 210, lock: 245 };
    const TONES = {
      'Warm':   { dL: 0.135, C: 0.050, h: WARM },
      'Cool':   { dL: 0.135, C: 0.058, h: COOL },
      'Pastel': { dL: 0.335, C: 0.058, h: { cam: 175, clim: 300, light: 82, lock: 245 } },
      'Follow the light': f.day ? { dL: 0.335, C: 0.058, h: COOL } : { dL: 0.135, C: 0.050, h: WARM },
    };
    const tn = TONES[this.props.tone] || TONES['Warm'];
    const C = tn.C * (1 - 0.35 * Math.min(ground.C / 0.09, 1));
    const L = Math.min(0.92, Math.max(0.16, ground.L + tn.dL));
    const tile = (h, c) => 'linear-gradient(155deg, oklch(' + (L + 0.055).toFixed(3) + ' ' + c.toFixed(3) + ' ' + h +
                           '), oklch(' + L.toFixed(3) + ' ' + c.toFixed(3) + ' ' + (h + 6) + '))';
    const lightInk = L > 0.62;
    const t = {
      light: tile(tn.h.light, C), cam: tile(tn.h.cam, C), clim: tile(tn.h.clim, C),
      lock: tile(tn.h.lock, C), plain: tile(tn.h.lock, C * 0.22),
      ink: lightInk ? '#1e1b24' : '#f1eee8',
      sub: lightInk ? 'rgba(30,27,36,.62)' : '#b9b5ad',
      lampInk: lightInk ? '#7a4a10' : '#e9b872',
      edge: lightInk ? 'rgba(30,27,36,.14)' : 'rgba(255,255,255,.10)',
      chipOff: lightInk ? 'rgba(30,27,36,.13)' : 'rgba(255,255,255,.12)',
      art: lightInk ? 'rgba(30,27,36,.13)' : 'rgba(255,255,255,.13)',
    };

    return { f: f, mat: mat, t: t };
  }
}
</script>
</body>
</html>
`

const check = process.argv.includes('--check')
const old = fs.existsSync(OUT) ? fs.readFileSync(OUT, 'utf8') : ''
if (check) {
  if (old === page) { console.log('Devices.dc.html is up to date with art.ts'); process.exit(0) }
  console.error('Devices.dc.html is STALE: art.ts has moved on. Run `node mock/art-sheet.mjs`.')
  process.exit(1)
}
fs.writeFileSync(OUT, page)
console.log(`wrote ${path.relative(process.cwd(), OUT)} — ${SHELF.length} drawings, ${RUNG_FOUR.length} at rung four, ${LAMP_STATES.length + BLIND_STATES.length} states`)
