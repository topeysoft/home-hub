/*
 * Draws design/Weather.dc.html from src/sky.ts.
 *
 * The same removal art-sheet.mjs did for the devices, for the same reason. This
 * sheet used to re-implement the illustration in its own JS -- the condition
 * table, the cloud body, the precipitation colours, the starfield -- and a copy
 * kept by hand is a copy that drifts. It had: rain at night was rgb(105,133,165)
 * on the sheet and rgb(110,140,176) in the panel, and the starfield came out at
 * 0.851 against the panel's 0.946, because those were corrected in sky.ts and
 * nowhere else. The header in sky.ts already claimed this file was generated
 * from it. Now it is.
 *
 *   node mock/weather-sheet.mjs          writes ../design/Weather.dc.html
 *   node mock/weather-sheet.mjs --check  fails if the file on disk is out of date
 *
 * Every number below comes out of illustration() and palette(); the markup is
 * RailView.vue's own, so what the sheet shows is what the wall draws.
 */
import { createServer } from 'vite'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = path.dirname(fileURLToPath(import.meta.url))
const OUT = path.join(HERE, '..', '..', 'design', 'Weather.dc.html')

const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', logLevel: 'error' })
const sky = await server.ssrLoadModule('/src/sky.ts')
await server.close()

/* The two lights every condition is drawn in. Not "a boolean night" -- these are
   sun elevations, the same input the panel has, chosen at the ends of the ramp
   so the pair reads as the two extremes rather than as two arbitrary times. */
const DAY = 40, NIGHT = -20

/* the only two names in COND that are a light rather than a weather; everything
   else is one condition drawn twice */
const PAIRS = [['sunny', 'clear-night', 'sunny · clear-night']].concat(
  Object.keys(sky.COND).filter((k) => k !== 'sunny' && k !== 'clear-night').map((k) => [k, k, k]))

const n2 = (v) => Number(v).toFixed(2).replace(/\.?0+$/, '') || '0'

/* The sky behind the drawing, by palette()'s own three bands -- which is what
   Sky.vue paints on the canvas, so an overcast night here is exactly as dark as
   an overcast night on the wall. */
const backdrop = (el, cond) => {
  const [top, band, horizon] = sky.palette(el, sky.wxOf(cond))
  return `linear-gradient(180deg, ${sky.rgb(top)} 0%, ${sky.rgb(band)} 58%, ${sky.rgb(horizon)} 100%)`
}

/* one side of a pair: the panel's own illustration, flattened to the keys the
   template reads. Nothing is computed here that sky.ts does not compute. */
function side(el, cond, key) {
  const p = sky.illustration(el, cond)
  const o = {}
  o[key + 'Id'] = `${cond}-${key}`
  o[key + 'Bg'] = backdrop(el, cond)
  o[key + 'C0'] = p.cloud.fill[0]
  o[key + 'C1'] = p.cloud.fill[1]
  o[key + 'C2'] = p.cloud.fill[2]
  o[key + 'Cloud'] = n2(p.cloud.opacity)
  o[key + 'CloudT'] = p.cloud.transform
  o[key + 'SunCol'] = p.sun.col
  o[key + 'Sun'] = n2(p.sun.opacity)
  o[key + 'MoonCol'] = p.moon.col
  o[key + 'Moon'] = n2(p.moon.opacity)
  o[key + 'BiteX'] = p.moon.biteX
  o[key + 'StarD'] = p.stars.opacity > 0.02 ? p.stars.d : ''
  o[key + 'Star'] = n2(p.stars.opacity)
  o[key + 'RainD'] = p.rain.d
  o[key + 'RainCol'] = p.rain.col
  o[key + 'Rain'] = n2(p.rain.opacity)
  o[key + 'SnowD'] = p.snow.d
  o[key + 'SnowCol'] = p.snow.col
  o[key + 'Snow'] = n2(p.snow.opacity)
  o[key + 'FogD'] = p.fog.d
  o[key + 'FogCol'] = p.fog.col
  o[key + 'Fog'] = n2(p.fog.opacity)
  o[key + 'WindD'] = p.wind.d
  o[key + 'WindCol'] = p.wind.col
  o[key + 'Wind'] = n2(p.wind.opacity)
  o[key + 'BoltD'] = p.bolt.d
  o[key + 'Bolt'] = n2(p.bolt.opacity)
  return o
}

/* what the house actually reported, under the drawing, so a cell can be checked
   against the table rather than against an eye */
const params = (cond) => {
  const w = sky.wxOf(cond)
  return [w.clouds ? `cl ${w.clouds}` : '', w.rain ? `rn ${w.rain}` : '', w.snow ? `sn ${w.snow}` : '',
    w.fog ? `fg ${w.fog}` : '', w.lightning ? 'lt' : '', w.wind > 1 ? `wd ${w.wind}` : ''].filter(Boolean).join('  ') || '—'
}

const cells = PAIRS.map(([dayName, niteName, label]) => ({
  nm: label, p: params(niteName),
  ...side(DAY, dayName, 'day'),
  ...side(NIGHT, niteName, 'nite'),
}))

/* The fifteenth cell is not a condition. It is the axis the other fourteen are
   doubled along -- and it happens to close the row the doubling left open. It is
   the clear sky with its one wisp of cloud turned off, so nothing is left in the
   frame but the two discs and the stars: the same illustration, showing less. */
cells.push({
  nm: 'the light, not a condition', p: 'sun up · sun down',
  ...side(DAY, 'sunny', 'day'),
  ...side(NIGHT, 'clear-night', 'nite'),
  dayCloud: 0, niteCloud: 0,
})

/* ---------- the page ---------- */

/* One half of a pair. The element order is RailView.vue's: stars, then the sun
   and the moon as two discs crossfading in the same place, then the wind behind
   the cloud, the cloud, and last the things that fall through it. */
const half = (k) => `            <div class="half" style="background: {{c.${k}Bg}};">
              <svg class="art" viewBox="12 6 186 144" width="112" height="87">
                <defs>
                  <radialGradient id="g{{c.${k}Id}}" cx="34%" cy="28%" r="78%">
                    <stop offset="0" stop-color="{{c.${k}C0}}" stop-opacity=".97"/>
                    <stop offset="62%" stop-color="{{c.${k}C1}}" stop-opacity=".93"/>
                    <stop offset="100%" stop-color="{{c.${k}C2}}" stop-opacity=".85"/>
                  </radialGradient>
                  <mask id="m{{c.${k}Id}}" maskUnits="userSpaceOnUse" x="0" y="0" width="210" height="150">
                    <rect x="0" y="0" width="210" height="150" fill="#fff"/>
                    <circle cx="{{c.${k}BiteX}}" cy="38" r="27" fill="#000"/>
                  </mask>
                </defs>
                <path d="{{c.${k}StarD}}" fill="#eef2fb" opacity="{{c.${k}Star}}"/>
                <circle cx="150" cy="44" r="27" fill="{{c.${k}SunCol}}" opacity="{{c.${k}Sun}}"/>
                <circle cx="150" cy="44" r="27" fill="{{c.${k}MoonCol}}" opacity="{{c.${k}Moon}}" mask="url(#m{{c.${k}Id}})"/>
                <path d="{{c.${k}WindD}}" stroke="{{c.${k}WindCol}}" stroke-width="3.4" stroke-linecap="round" fill="none" opacity="{{c.${k}Wind}}"/>
                <g transform="{{c.${k}CloudT}}" opacity="{{c.${k}Cloud}}" fill="url(#g{{c.${k}Id}})">
                  <ellipse cx="72" cy="86" rx="56" ry="40"/><ellipse cx="118" cy="70" rx="48" ry="44"/><ellipse cx="150" cy="94" rx="42" ry="30"/><rect x="60" y="92" width="104" height="34" rx="17"/>
                </g>
                <path d="{{c.${k}BoltD}}" fill="#f3d18a" opacity="{{c.${k}Bolt}}"/>
                <path d="{{c.${k}RainD}}" stroke="{{c.${k}RainCol}}" stroke-width="4" stroke-linecap="round" fill="none" opacity="{{c.${k}Rain}}"/>
                <path d="{{c.${k}SnowD}}" fill="{{c.${k}SnowCol}}" opacity="{{c.${k}Snow}}"/>
                <path d="{{c.${k}FogD}}" stroke="{{c.${k}FogCol}}" stroke-width="6" stroke-linecap="round" fill="none" opacity="{{c.${k}Fog}}"/>
              </svg>
            </div>`

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
    body { margin: 0; font-family: "Instrument Sans", -apple-system, system-ui, sans-serif; }
    a { color: #e9b872; } a:hover { color: #b8863e; }
    .dsp { font-family: "Instrument Serif", Palatino, Georgia, serif; font-weight: 400; letter-spacing: -0.01em; }
    .cell { display: flex; flex-direction: column; align-items: flex-start; }
    .pair { display: flex; width: 100%; height: 140px; border-radius: 16px; overflow: hidden; border: 1px solid rgba(255,255,255,.09); }
    .half { position: relative; flex: 1 1 0; min-width: 0; }
    .half + .half { border-left: 1px solid rgba(255,255,255,.13); }
    .art { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); }
    .cid { font-size: 14.5px; font-weight: 500; margin-top: 2px; }
    .prm { font-size: 12px; color: #7f7d77; font-variant-numeric: tabular-nums; margin-top: 2px; }
  </style>
</helmet>

<div style="position: relative; width: 1440px; height: 900px; overflow: hidden; background: #0c0d10; color: #f1eee8; font-size: 17px; line-height: 1.4; padding: 40px 48px;">
  <div style="position: absolute; inset: 0; background: linear-gradient(180deg, rgb(10,14,34) 0%, rgb(30,26,58) 58%, rgb(16,16,30) 100%);"></div>
  <div style="position: relative;">

    <h1 class="dsp" style="margin: 0; font-size: 38px;">One cloud, every condition, both lights</h1>
    <p style="margin: 8px 0 0; font-size: 17px; color: #b9b5ad; max-width: 100ch;">Not thirty drawings &mdash; one illustration built from parts, driven by the same <span style="font-variant-numeric: tabular-nums;">{clouds, rain, snow, fog, lightning, wind}</span> that <span style="font-variant-numeric: tabular-nums;">wxOf()</span> already hands the sky. Night is not one of those parts, and it is not a condition: the house reports the weather, the sun&rsquo;s elevation says which light it is in. So every condition has to hold up twice. <b style="color:#e4e0d8; font-weight:500;">Day on the left of each pair, night on the right.</b> Only the clear sky carries two names.</p>
    <p style="margin: 7px 0 0; font-size: 13px; color: #8a877f; max-width: 116ch;">Every mark below is <span style="font-variant-numeric: tabular-nums;">illustration()</span>&rsquo;s, and every sky is <span style="font-variant-numeric: tabular-nums;">palette()</span>&rsquo;s, read out of <span style="font-variant-numeric: tabular-nums;">src/sky.ts</span> at ${DAY}&deg; and ${NIGHT}&deg; of sun &mdash; not drawn again here. What changes between a pair: the sky, greyed by cloud, darkened by rain, flattened by fog, in either light; the disc, a gold sun and a bitten silver moon crossfading in one place; the stars a thin enough sky lets through; and the cloud body, lit white by day, only moonlit by night. Nothing else moves. The bolt is the same colour in both, because lightning brings its own light.</p>

    <div style="display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 24px 18px; margin-top: 24px;">
      <sc-for list="{{cells}}" as="c" hint-placeholder-count="${cells.length}">
        <div class="cell">
          <div class="pair">

${half('day')}

${half('nite')}

          </div>
          <div class="cid">{{c.nm}}</div>
          <div class="prm">{{c.p}}</div>
        </div>
      </sc-for>
    </div>
  </div>
</div>
</x-dc>

<script data-dc-script>
/* Baked by mock/weather-sheet.mjs out of src/sky.ts -- do not edit by hand, and
   do not compute anything here. The moment this file works out a colour of its
   own it is a second implementation again, which is the bug it was written to
   remove. Run \`npm run weather-sheet\` after touching sky.ts; CI checks it. */
class Component extends DCLogic {
  renderVals() {
    return { cells: ${JSON.stringify(cells, null, 6).replace(/\n/g, '\n    ')} };
  }
}
</script>
</body>
</html>
`

const check = process.argv.includes('--check')
const old = fs.existsSync(OUT) ? fs.readFileSync(OUT, 'utf8') : ''
if (check) {
  if (old === page) { console.log('Weather.dc.html is up to date with sky.ts'); process.exit(0) }
  console.error('Weather.dc.html is STALE: sky.ts has moved on. Run `node mock/weather-sheet.mjs`.')
  process.exit(1)
}
fs.writeFileSync(OUT, page)
console.log(`wrote ${path.relative(process.cwd(), OUT)} — ${cells.length} conditions, each at ${DAY}° and ${NIGHT}°`)
