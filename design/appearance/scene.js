/*
 * The shared half of every board in this collection: the home screen, the chips under it, and a
 * sky that can be drawn at any lightness. A board supplies only window.Look(s), which returns the
 * variables the screen is painted with and the sky behind it (or none), for the hour and state the
 * chips have chosen. Nothing else differs between the boards.
 */
(function () {
  /* app/src/sky.ts KEYS at the three elevations the chips choose, as design/backdrop/ reads them */
  const HOURS = {
    night: { sky: ['rgb(4,5,10)', 'rgb(7,9,16)', 'rgb(12,14,26)'], hill: 'rgb(14,14,18)', L: 0.15, clock: '11:40 PM', tab: 'Your night', rest: '11:40' },
    dusk: { sky: ['rgb(10,14,34)', 'rgb(38,34,74)', 'rgb(158,84,60)'], hill: 'rgb(24,22,28)', L: 0.25, clock: '7:12 PM', tab: 'Your evening', rest: '7:12' },
    noon: { sky: ['rgb(26,78,136)', 'rgb(70,148,202)', 'rgb(170,200,218)'], hill: 'rgb(74,92,66)', L: 0.49, clock: '12:30 PM', tab: 'Your afternoon', rest: '12:30' },
  }
  const s = { hour: 'night', lamp: 'on', screen: 'awake' }
  const GROUPS = {
    hour: ['Time', [['night', 'Night'], ['dusk', 'Dusk'], ['noon', 'Noon']]],
    lamp: ['Ceiling light', [['off', 'Off'], ['on', 'On']]],
    screen: ['Screen', [['awake', 'In use'], ['rest', 'Resting']]],
  }

  let uid = 0
  const rnd = ((seed) => () => (seed = (seed * 16807) % 2147483647) / 2147483647)(7)
  const STARS = Array.from({ length: 140 }, () => [rnd() * 1440, rnd() * 560, 0.5 + rnd() * 1.2, 0.35 + rnd() * 0.5])
  const HILL = 'M0 668 C160 650 330 700 520 704 C700 708 860 716 1010 706 C1150 696 1260 684 1440 690 L1440 900 L0 900 Z'
  const TREES = [[18, 690, 8], [40, 680, 12], [66, 677, 8], [96, 674, 13], [180, 684, 13], [340, 700, 13], [388, 708, 7], [480, 716, 10], [766, 710, 10], [818, 710, 8], [884, 708, 12], [1138, 688, 10], [1166, 686, 8], [1200, 680, 9], [1304, 682, 8]]
  const tree = ([x, y, r]) => `M${x - r} ${y + 4} L${x - r} ${y - r * 0.6} A${r} ${r} 0 0 1 ${x + r} ${y - r * 0.6} L${x + r} ${y + 4} Z`

  /*
   * A sky, at whatever lightness the caller asks for. `stops` is top, middle and horizon; `stars`
   * is how visible they are, in `starInk`; `glow` is the low sun at dusk or the high one at noon;
   * `veil` is today's .sky-veil or nothing. `fit` is 'wall' for the whole screen, 'window' to fill a
   * smaller frame with the hills along its foot.
   */
  function sky({ stops, hill, stars = 0, starInk = '255,255,255', glow = null, veil = null, moon = null, fit = 'wall' }) {
    const [a, b, c] = stops, id = 'g' + (++uid)
    const par = fit === 'wall' ? 'none' : 'xMidYMax slice'
    const dots = stars ? STARS.map(([x, y, r, o]) => `<circle cx="${x.toFixed(0)}" cy="${y.toFixed(0)}" r="${r.toFixed(2)}" fill="rgba(${starInk},${(o * stars).toFixed(2)})"/>`).join('') : ''
    const glows = {
      dusk: `<radialGradient id="${id}" cx="1195" cy="648" r="150" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="rgb(255,200,150)" stop-opacity=".55"/><stop offset=".25" stop-color="rgb(240,150,100)" stop-opacity=".25"/><stop offset="1" stop-color="rgb(240,150,100)" stop-opacity="0"/></radialGradient><rect x="980" y="460" width="440" height="380" fill="url(#${id})"/>`,
      noon: `<radialGradient id="${id}" cx="1120" cy="120" r="230" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="rgb(255,250,235)" stop-opacity=".85"/><stop offset=".12" stop-color="rgb(255,245,220)" stop-opacity=".35"/><stop offset="1" stop-color="rgb(255,245,220)" stop-opacity="0"/></radialGradient><rect x="860" y="0" width="520" height="380" fill="url(#${id})"/>`,
    }
    const moonSvg = moon ? `<circle cx="300" cy="150" r="34" fill="${moon[0]}"/><circle cx="316" cy="142" r="30" fill="${moon[1]}"/>` : ''
    return `<div class="sky-l" style="inset:0;background:linear-gradient(180deg, ${a} 0%, ${b} 55%, ${c} 90%, ${c} 100%)"></div>`
      + `<svg class="sky-hills" style="inset:0;width:100%;height:100%" viewBox="0 0 1440 900" preserveAspectRatio="${par}"><defs></defs>${dots}${moonSvg}${glow ? glows[glow] : ''}`
      + `<g fill="${hill}"><path d="${HILL}"/>${TREES.map((t) => `<path d="${tree(t)}"/>`).join('')}</g></svg>`
      + (veil ? `<div class="sky-l" style="inset:0;background:${veil}"></div>` : '')
  }
  const VEIL = 'linear-gradient(180deg, rgba(12,13,16,.30) 0%, rgba(12,13,16,.52) 45%, rgba(12,13,16,.80) 100%)'

  /* the hour's own sky, unchanged: what Today draws behind everything, and what A and C keep in a window */
  const real = (hour, opts = {}) => sky({ stops: HOURS[hour].sky, hill: HOURS[hour].hill, stars: hour === 'night' ? 1 : hour === 'dusk' ? 0.35 : 0, glow: hour === 'night' ? null : hour, ...opts })
  const REST_VEIL = 'linear-gradient(180deg, rgba(12,13,16,.08), rgba(12,13,16,.22) 60%, rgba(12,13,16,.55))'

  /* The two inks every board starts from. DARK is panel.css as it ships; LIGHT is the paper page,
     with the signal colors taken down to where they read on white -- the pastels were chosen to be
     ink on a dark field and wash out on a light one. */
  const DARK = {
    '--page-ink': '#f1eee8', '--page-ink-2': '#b9b5ad',
    '--chrome': 'rgba(26,28,34,.68)', '--chrome-edge': 'rgba(255,255,255,.10)', '--chrome-ink': '#f1eee8', '--chrome-ink-2': '#b9b5ad',
    '--chrome-shadow': '0 24px 60px -30px rgba(0,0,0,.7)', '--tab-on': 'rgba(255,255,255,.12)', '--tab-on-ink': '#fff',
    '--mark': '#e9b872', '--mark-ink': '#2a1c07', '--live': '#74c69d',
    '--card': 'rgba(26,28,34,.68)', '--card-edge': 'rgba(255,255,255,.10)', '--card-shadow': '0 24px 60px -30px rgba(0,0,0,.7)', '--card-blur': 'none',
    '--card-ink': '#f1eee8', '--card-ink-2': '#b9b5ad', '--well': 'rgba(255,255,255,.06)', '--track': 'rgba(255,255,255,.18)', '--chip': 'rgba(255,255,255,.12)', '--play-ink': '#111',
    '--beam': 'rgba(255,214,150,.55)', '--strip': 'oklch(.72 .13 180)',
    '--loz': 'rgba(26,28,34,.45)', '--loz-edge': 'rgba(255,255,255,.12)', '--loz-ink': '#f1eee8', '--loz-ink-2': '#c9c5bd',
    '--moon': '#6b6a70', '--moon-cut': '#2a2a33', '--cloud': '#c9c9d2', '--cloud-2': '#a9a9b4',
    '--orb-shadow': '0 10px 30px rgba(0,0,0,.6)', '--av-edge': '#1a1a1f',
    '--rest-ink': '#f1eee8', '--rest-ink-2': '#d6d2ca', '--rest-mark': '#e9b872', '--rest-shadow': '0 2px 24px rgba(0,0,0,.5)',
  }
  const LIGHT = {
    '--page-ink': '#1e1b24', '--page-ink-2': '#6e6a73',
    '--chrome': '#ffffff', '--chrome-edge': 'rgba(30,27,36,.08)', '--chrome-ink': '#1e1b24', '--chrome-ink-2': '#6e6a73',
    '--chrome-shadow': '0 1px 2px rgba(30,27,36,.05), 0 10px 26px -16px rgba(30,27,36,.22)', '--tab-on': '#1e1b24', '--tab-on-ink': '#f6f3ee',
    '--mark': '#e9b872', '--mark-ink': '#2a1c07', '--live': '#2e8a5c',
    '--card': '#ffffff', '--card-edge': 'rgba(30,27,36,.07)', '--card-shadow': '0 1px 2px rgba(30,27,36,.05), 0 16px 36px -20px rgba(30,27,36,.26)', '--card-blur': 'none',
    '--card-ink': '#1e1b24', '--card-ink-2': '#6e6a73', '--well': '#f4f1ec', '--track': 'rgba(30,27,36,.12)', '--chip': 'rgba(30,27,36,.07)', '--play-ink': '#fff',
    '--cool': 'linear-gradient(155deg, oklch(.86 .065 245), oklch(.79 .085 250))', '--cool-ink': '#14233a', '--cool-ink-2': 'rgba(20,35,58,.72)', '--cool-chip': 'rgba(255,255,255,.5)',
    '--lamp-on': 'linear-gradient(160deg, oklch(.90 .095 82), oklch(.82 .12 70))', '--lamp-on-ink': '#2a1c07', '--lamp-on-ink-2': 'rgba(42,28,7,.72)',
    '--lamp-on-chip': 'rgba(255,255,255,.45)', '--lamp-on-edge': 'transparent', '--lamp-on-mark': '#2a1c07', '--lamp-on-mark-ink': '#f3d9a6',
    '--beam': 'rgba(255,244,214,.85)', '--strip': 'oklch(.66 .13 180)',
    '--loz': '#ffffff', '--loz-edge': 'rgba(30,27,36,.07)', '--loz-ink': '#1e1b24', '--loz-ink-2': '#6e6a73',
    '--moon': '#fbfaf6', '--moon-cut': '#c9cde0', '--cloud': '#ffffff', '--cloud-2': 'rgba(255,255,255,.75)',
    '--orb-shadow': '0 10px 24px rgba(60,40,120,.25)', '--av-edge': '#f3f0ea',
    '--rest-ink': '#1e1b24', '--rest-ink-2': '#5f5b66', '--rest-mark': '#a8701c', '--rest-shadow': 'none',
  }

  const q = (sel) => document.querySelector(sel)
  const BULB = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="9.5" r="5"/><path d="M9.5 16h5M10.5 19h3"/></svg>'
  const PAUSE = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>'
  const CLOUD = '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M7 18h10a4 4 0 0 0 0-8 5.5 5.5 0 0 0-10.6 1.4A3.4 3.4 0 0 0 7 18z"/></svg>'

  const FG = `
  <div class="clock"><b></b><span>Saturday, September 26</span></div>
  <div class="tabs chrome"><div class="on"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 11.2L12 4.5l8 6.7M6.2 12.6V19h11.6v-6.4"/></svg><span></span></div><div>Rooms</div><div>Cameras</div></div>
  <div class="status"><i></i>CONNECTED</div>
  <div class="round chrome" style="right:94px"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 5.5v13M5.5 12h13"/></svg></div>
  <div class="round chrome" style="right:40px"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 8h12M6 12h12M6 16h8"/></svg></div>
  <div class="band chrome" style="left:40px;width:266px"><span class="ic">✦</span><span><b>Found 2 new things nearby</b><small>Sonos Roam, Chromecast (Den)</small></span></div>
  <div class="band chrome" style="left:317px;width:420px"><span class="ic"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="10.5" width="14" height="9.5" rx="2.4"/><path d="M8.2 10.5V7.6a3.8 3.8 0 0 1 7.6 0v2.9"/></svg></span><span><b>Lock the settings</b><small>Anyone on the Wi-Fi can change the house right now. A…</small></span></div>
  <svg class="wx-art" viewBox="0 0 230 170"><mask id="crescent"><rect width="230" height="170" fill="#fff"/><circle cx="184" cy="40" r="37" fill="#000"/></mask><g class="moon"><circle cx="165" cy="48" r="42" fill="var(--moon)" mask="url(#crescent)"/></g><circle class="sun" cx="165" cy="48" r="40" fill="#f3d27a"/>
    <g fill="var(--cloud)"><ellipse cx="75" cy="115" rx="72" ry="44"/><circle cx="130" cy="85" r="52"/><ellipse cx="165" cy="130" rx="55" ry="34"/></g>
    <ellipse cx="130" cy="140" rx="75" ry="22" fill="var(--cloud-2)"/></svg>
  <div class="loz"><b>78°</b><span class="c">Partly cloudy</span><small>Sunrise 7:00 AM<br>Humidity 48%</small></div>
  <div class="win"><div class="win-sky"></div><svg class="win-art" viewBox="0 0 230 170"><mask id="crescent-w"><rect width="230" height="170" fill="#fff"/><circle cx="184" cy="40" r="37" fill="#000"/></mask><g class="moon"><circle cx="165" cy="48" r="42" fill="#d8d6dc" mask="url(#crescent-w)"/></g><circle class="sun" cx="165" cy="48" r="40" fill="#f3d27a"/>
    <g fill="var(--win-cloud)"><ellipse cx="75" cy="115" rx="72" ry="44"/><circle cx="130" cy="85" r="52"/><ellipse cx="165" cy="130" rx="55" ry="34"/></g>
    <ellipse cx="130" cy="140" rx="75" ry="22" fill="var(--win-cloud-2)"/></svg><div class="txt"><b>78°</b><span class="c">Partly cloudy</span><small>Sunrise 7:00 AM · Humidity 48%</small></div></div>
  <div class="card tv"><div class="art"><span class="chip" style="left:16px;top:16px">TV</span></div>
    <div class="media"><b>The Bear</b><small>Season 3, Episode 4 · Disney+</small><div class="bar"><i></i></div><div class="play">${PAUSE}</div></div></div>
  <div class="card door"><div class="ground"></div><span class="chip" style="right:12px;top:14px">16S AGO</span>
    <div class="lab"><i><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="7" width="18" height="13" rx="3"/><circle cx="12" cy="13.5" r="3.4"/></svg></i>Doorbell</div></div>
  <div class="card thermo"><div class="dial">71<sup style="font-size:14px;margin-left:2px">°F</sup></div>
    <div class="pm" style="left:16px">−</div><div class="pm" style="right:16px">+</div><small>Currently 74°F · Cooling · 48% humi…</small></div>
  <div class="card lamp"><span class="ic">${BULB}</span>
    <span class="brand">PHILIPS HUE</span><div class="rod"></div><div class="beam"></div><div class="shade"></div>
    <div class="name">Ceiling light</div><div class="val"></div><div class="lvl"><i></i></div></div>
  <div class="card strip"><div class="sw"></div></div>
  <div class="orb"></div>
  <div class="family">Temi and Ade are home <b>Family</b><span class="av"><i style="background:#8a7560">T</i><i style="background:#6a5448">S</i><i style="background:#5f7f72">A</i><i style="background:var(--chip);color:var(--page-ink)">+</i></span></div>`

  const REST = `<div class="time"></div><div class="day">Saturday, September 26</div>
    <div class="wx"><span>${CLOUD}</span>78° · Partly cloudy</div>
    <div class="on">Something is on in 2 rooms.</div><div class="next">Next: Porch light off, 11:00 PM</div>`

  window.Scene = {
    s, HOURS, sky, real, VEIL, REST_VEIL, DARK, LIGHT,
    init({ tag, groups = ['hour', 'lamp', 'screen'], defaults = {} }) {
      Object.assign(s, defaults)
      const root = q('.board')
      root.innerHTML = `<div class="screen"><div class="bg"></div><div class="fg">${FG}</div><div class="rest">${REST}</div></div><div class="ctl"></div>`
      const ctl = root.querySelector('.ctl')
      ctl.innerHTML = groups.map((g) => `<div class="g" data-k="${g}"><span>${GROUPS[g][0]}</span>${GROUPS[g][1].map(([v, t]) => `<button data-v="${v}">${t}</button>`).join('')}</div>`).join('') + `<span class="tag">${tag}</span>`
      ctl.addEventListener('click', (e) => {
        const b = e.target.closest('button'); if (!b) return
        s[b.parentElement.dataset.k] = b.dataset.v
        refresh()
      })
      const screen = root.querySelector('.screen')
      function refresh() {
        for (const g of ctl.querySelectorAll('.g')) for (const b of g.querySelectorAll('button')) b.classList.toggle('on', s[g.dataset.k] === b.dataset.v)
        const h = HOURS[s.hour], look = window.Look(s)
        screen.removeAttribute('style')
        for (const [k, v] of Object.entries(look.vars)) screen.style.setProperty(k, v)
        screen.dataset.weather = look.weather || 'open'
        screen.classList.toggle('resting', s.screen === 'rest')
        root.querySelector('.bg').innerHTML = look.sky || ''
        root.querySelector('.bg').style.background = look.page || ''
        root.querySelector('.win-sky').innerHTML = look.weather === 'window' ? real(s.hour, { fit: 'window' }) : ''
        q('.clock b').textContent = h.clock
        q('.tabs .on span').textContent = h.tab
        q('.rest .time').textContent = h.rest
        for (const m of document.querySelectorAll('.moon')) m.style.display = s.hour === 'noon' ? 'none' : ''
        for (const m of document.querySelectorAll('.sun')) m.style.display = s.hour === 'noon' ? '' : 'none'
        screen.style.setProperty('--win-cloud', s.hour === 'noon' ? '#ffffff' : s.hour === 'dusk' ? '#b9a9c4' : '#5d5f70')
        screen.style.setProperty('--win-cloud-2', s.hour === 'noon' ? 'rgba(255,255,255,.75)' : s.hour === 'dusk' ? '#9a8aa8' : '#474857')
        q('.lamp').classList.toggle('on', s.lamp === 'on')
        q('.lamp .val').textContent = s.lamp === 'on' ? 'On, 35% · Warm white' : 'Off'
      }
      refresh()
    },
  }
})()
