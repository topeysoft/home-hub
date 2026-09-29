/*
 * The shared half of every backdrop board: the evening home screen in front, the
 * chips underneath, and the arithmetic that turns a lamp into a background color.
 *
 * A board supplies only its backdrop, as window.Backdrop = { mount(el), update(s),
 * frame(t) }. Everything a backdrop may react to arrives in s: the hour's own sky
 * colors, and the colored things the house has on, each already tamed for a screen.
 *
 * Taming is the rule this whole collection leans on. A lamp's color is an emitter
 * color, chosen to be seen in a room; put it on a screen at full strength and a
 * red bulb paints the wall like an alarm. So a source keeps only its hue: its
 * lightness is set a fixed distance above the hour's field and its chroma is
 * capped, the way tone.ts holds cards at a distance from the sky.
 */
(function () {
  /* app/src/sky.ts KEYS, at the three elevations the chips choose: [top, middle, horizon] */
  const HOURS = {
    night: { sky: [[4, 5, 10], [7, 9, 16], [12, 14, 26]], L: 0.15, clock: '11:40 PM', tab: 'Your night', hill: [14, 14, 18] },
    dusk: { sky: [[10, 14, 34], [38, 34, 74], [158, 84, 60]], L: 0.25, clock: '7:12 PM', tab: 'Your evening', hill: [24, 22, 28] },
    noon: { sky: [[26, 78, 136], [70, 148, 202], [170, 200, 218]], L: 0.49, clock: '12:30 PM', tab: 'Your afternoon', hill: [74, 92, 66] },
  }
  /* what the bulb is asked to emit, not what the card shows */
  const LAMPS = {
    off: null,
    warm: { rgb: [255, 186, 112], name: 'Warm white' },
    pink: { rgb: [236, 64, 196], name: 'Pink' },
    red: { rgb: [255, 36, 24], name: 'Red' },
  }
  const STRIPS = { off: null, teal: { rgb: [24, 222, 196], name: 'Teal' } }
  const ART = [168, 74, 44]    // The Bear's key art, as the media tile samples it

  // ---- color: sRGB <-> OKLCH, so a hue survives having its lightness moved ----
  const lin = (c) => (c /= 255) <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  const gam = (c) => 255 * Math.min(1, Math.max(0, c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055))
  function oklch([R, G, B]) {
    const r = lin(R), g = lin(G), b = lin(B)
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
    const L = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s
    const A = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
    const Bb = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
    return [L, Math.hypot(A, Bb), Math.atan2(Bb, A)]
  }
  function rgbOf([L, C, h]) {
    const A = C * Math.cos(h), Bb = C * Math.sin(h)
    const l = (L + 0.3963377774 * A + 0.2158037573 * Bb) ** 3
    const m = (L - 0.1055613458 * A - 0.0638541728 * Bb) ** 3
    const s = (L - 0.0894841775 * A - 1.2914855480 * Bb) ** 3
    return [gam(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s),
            gam(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s),
            gam(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)]
  }
  /* keep the hue, set the lightness, cap the chroma */
  function tame(rgb, L, Cmax) { const [, C, h] = oklch(rgb); return rgbOf([L, Math.min(C, Cmax), h]) }
  const css = (c, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`

  // ---- state and the chips that set it ----
  const s = { hour: 'dusk', lamp: 'pink', strip: 'off', tv: 'playing', speed: 6 }
  const GROUPS = {
    hour: ['Time', [['night', 'Night'], ['dusk', 'Dusk'], ['noon', 'Noon']]],
    lamp: ['Light', [['off', 'Off'], ['warm', 'Warm'], ['pink', 'Pink'], ['red', 'Red']]],
    strip: ['Strip', [['off', 'Off'], ['teal', 'Teal']]],
    tv: ['TV', [['paused', 'Paused'], ['playing', 'Playing']]],
    speed: ['Motion', [[0, 'Still'], [1, 'Real'], [6, '6×']]],
  }

  /* Everything a backdrop may react to. `where` is the source's card on screen, for a
     backdrop that glows from behind the thing itself; strength is how much it counts. */
  function sources() {
    const h = HOURS[s.hour], out = []
    if (LAMPS[s.lamp]) out.push({ id: 'lamp', rgb: LAMPS[s.lamp].rgb, strength: 1, where: [1229, 442] })
    if (STRIPS[s.strip]) out.push({ id: 'strip', rgb: STRIPS[s.strip].rgb, strength: 0.9, where: [1470, 440] })
    if (s.tv === 'playing') out.push({ id: 'tv', rgb: ART, strength: 0.6, where: [641, 300] })
    for (const o of out) {
      o.glow = tame(o.rgb, h.L + 0.22, 0.13)     // for a backdrop: a wash, never the bulb
      o.card = tame(o.rgb, 0.52, 0.12)           // for the lamp's own card: ink on a dark field
    }
    return out
  }

  function paintFg() {
    const h = HOURS[s.hour]
    q('.clock b').textContent = h.clock
    q('.tabs .on span').textContent = h.tab
    q('.wx-art .moon').style.display = s.hour === 'noon' ? 'none' : ''
    q('.wx-art .sun').style.display = s.hour === 'noon' ? '' : 'none'
    const lamp = LAMPS[s.lamp], src = sources().find((o) => o.id === 'lamp')
    const card = q('.lamp')
    if (lamp) {
      card.style.background = `linear-gradient(170deg, ${css(src.card, .78)}, ${css(src.card, .42)})`
      card.style.borderColor = css(tame(lamp.rgb, .72, .1), .45)
      q('.lamp .ic').style.background = css(tame(lamp.rgb, .62, .2))
      q('.lamp .beam').style.opacity = 1
      q('.lamp .beam').style.background = `linear-gradient(180deg, ${css(tame(lamp.rgb, .75, .16), .7)}, transparent)`
      q('.lamp .val').textContent = `On, 35% · ${lamp.name}`
      q('.lamp .lvl i').style.background = css(tame(lamp.rgb, .75, .16))
    } else {
      card.style.background = ''; card.style.borderColor = ''
      q('.lamp .ic').style.background = 'rgba(255,255,255,.12)'
      q('.lamp .beam').style.opacity = 0
      q('.lamp .val').textContent = 'Off'
      q('.lamp .lvl i').style.background = 'transparent'
    }
    const st = STRIPS[s.strip]
    q('.strip .sw').style.background = st ? css(tame(st.rgb, .72, .13)) : 'rgba(255,255,255,.12)'
    q('.strip .sw').style.boxShadow = st ? `0 0 18px ${css(tame(st.rgb, .72, .13), .6)}` : 'none'
    q('.tv').classList.toggle('paused', s.tv !== 'playing')
    q('.play').innerHTML = s.tv === 'playing' ? PAUSE : PLAY
  }

  const q = (sel) => document.querySelector(sel)
  const PAUSE = '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>'
  const PLAY = '<svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5l11 7-11 7z"/></svg>'

  const FG = `
  <div class="clock"><b>7:12 PM</b><span>Saturday, September 26</span></div>
  <div class="tabs glass"><div class="on"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 11.2L12 4.5l8 6.7M6.2 12.6V19h11.6v-6.4"/></svg><span>Your evening</span></div><div>Rooms</div><div>Cameras</div></div>
  <div class="status"><i></i>CONNECTED</div>
  <div class="round glass" style="right:94px"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 5.5v13M5.5 12h13"/></svg></div>
  <div class="round glass" style="right:40px"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 8h12M6 12h12M6 16h8"/></svg></div>
  <div class="band glass" style="left:40px;width:266px"><span class="ic">✦</span><span><b>Found 2 new things nearby</b><small>Sonos Roam, Chromecast (Den)</small></span></div>
  <div class="band glass" style="left:317px;width:420px"><span class="ic"><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="10.5" width="14" height="9.5" rx="2.4"/><path d="M8.2 10.5V7.6a3.8 3.8 0 0 1 7.6 0v2.9"/></svg></span><span><b>Lock the settings</b><small>Anyone on the Wi-Fi can change the house right now. A…</small></span></div>
  <svg class="wx-art" viewBox="0 0 230 170"><g class="moon"><circle cx="165" cy="48" r="42" fill="#6b6a70"/><circle cx="184" cy="40" r="37" fill="#2a2a33"/></g><circle class="sun" cx="165" cy="48" r="40" fill="#f3d27a"/>
    <g fill="#c9c9d2"><ellipse cx="75" cy="115" rx="72" ry="44"/><circle cx="130" cy="85" r="52"/><ellipse cx="165" cy="130" rx="55" ry="34"/></g>
    <ellipse cx="130" cy="140" rx="75" ry="22" fill="#a9a9b4"/></svg>
  <div class="loz glass"><b>78°</b><span class="c">Partly cloudy</span><small>Sunrise 7:00 AM<br>Humidity 48%</small></div>
  <div class="card tv glass"><div class="art"><span class="chip" style="left:16px;top:16px">TV</span></div>
    <div class="media"><b>The Bear</b><small>Season 3, Episode 4 · Disney+</small><div class="bar"><i></i></div><div class="play"></div></div></div>
  <div class="card door"><div class="ground"></div><span class="chip" style="right:12px;top:14px">16S AGO</span>
    <div class="lab"><i><svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="3" y="7" width="18" height="13" rx="3"/><circle cx="12" cy="13.5" r="3.4"/></svg></i>Doorbell</div></div>
  <div class="card thermo glass"><div class="dial">71<sup style="font-size:14px;margin-left:2px">°F</sup></div>
    <div class="pm" style="left:16px">−</div><div class="pm" style="right:16px">+</div><small>Currently 74°F · Cooling · 48% humi…</small></div>
  <div class="card lamp glass"><span class="ic"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8"><circle cx="12" cy="9.5" r="5"/><path d="M9.5 16h5M10.5 19h3"/></svg></span>
    <span class="brand">PHILIPS HUE</span><div class="rod"></div><div class="beam"></div><div class="shade"></div>
    <div class="name">Ceiling light</div><div class="val">On, 35%</div><div class="lvl"><i></i></div></div>
  <div class="card strip glass"><div class="sw"></div></div>
  <div class="orb"></div>
  <div class="family">Temi and Ade are home <b>Family</b><span class="av"><i style="background:#8a7560">T</i><i style="background:#6a5448">S</i><i style="background:#5f7f72">A</i><i style="background:rgba(255,255,255,.14)">+</i></span></div>`

  /* Today's sky, simplified from Sky.vue to what a board needs to compare against: the
     hour's three bands, stars after dark, the low sun at dusk, and the ground. */
  const rnd = ((seed) => () => (seed = (seed * 16807) % 2147483647) / 2147483647)(7)
  const STARS = Array.from({ length: 140 }, () => ({ x: rnd() * 1440, y: rnd() * 560, r: .5 + rnd() * 1.2, p: rnd() * 6.28 }))
  const HILL = new Path2D('M0 668 C160 650 330 700 520 704 C700 708 860 716 1010 706 C1150 696 1260 684 1440 690 L1440 900 L0 900 Z')
  const TREES = [[18, 690, 8], [40, 680, 12], [66, 677, 8], [96, 674, 13], [180, 684, 13], [340, 700, 13], [388, 708, 7], [480, 716, 10], [766, 710, 10], [818, 710, 8], [884, 708, 12], [1138, 688, 10], [1166, 686, 8], [1200, 680, 9], [1304, 682, 8]]
  function sky(ctx, hour, t) {
    const [a, b, c] = hour.sky
    const g = ctx.createLinearGradient(0, 0, 0, 720)
    g.addColorStop(0, css(a)); g.addColorStop(.55, css(b)); g.addColorStop(.9, css(c)); g.addColorStop(1, css(c))
    ctx.fillStyle = g; ctx.fillRect(0, 0, 1440, 900)
    const starA = hour === HOURS.night ? 1 : hour === HOURS.dusk ? .35 : 0
    if (starA) for (const st of STARS) { ctx.fillStyle = `rgba(255,255,255,${starA * (.45 + .35 * Math.sin(t * .8 + st.p))})`; ctx.beginPath(); ctx.arc(st.x, st.y, st.r, 0, 7); ctx.fill() }
    if (hour === HOURS.dusk) { const s = ctx.createRadialGradient(1195, 648, 0, 1195, 648, 140); s.addColorStop(0, 'rgba(255,200,150,.55)'); s.addColorStop(.25, 'rgba(240,150,100,.25)'); s.addColorStop(1, 'rgba(240,150,100,0)'); ctx.fillStyle = s; ctx.fillRect(1000, 480, 400, 340) }
    if (hour === HOURS.noon) { const s = ctx.createRadialGradient(1120, 120, 0, 1120, 120, 220); s.addColorStop(0, 'rgba(255,250,235,.8)'); s.addColorStop(.12, 'rgba(255,245,220,.35)'); s.addColorStop(1, 'rgba(255,245,220,0)'); ctx.fillStyle = s; ctx.fillRect(880, 0, 480, 360) }
    ctx.fillStyle = css(hour.hill); ctx.fill(HILL)
    for (const [x, y, r] of TREES) { ctx.beginPath(); ctx.arc(x, y - r * .6, r, Math.PI, 0); ctx.lineTo(x + r, y + 4); ctx.lineTo(x - r, y + 4); ctx.fill() }
  }

  window.Scene = {
    s, css, tame, oklch, rgbOf, HOURS, sky,
    /* start the board: which chip groups it shows and what it is called at the right of the strip */
    init({ groups, tag, defaults = {} }) {
      Object.assign(s, defaults)
      const root = document.querySelector('.board')
      root.innerHTML = `<div class="screen"><div class="bg"></div><div class="veil"></div><div class="over"></div><div class="fg">${FG}</div></div><div class="ctl"></div>`
      const ctl = root.querySelector('.ctl')
      ctl.innerHTML = groups.map((g) => `<div class="g" data-k="${g}"><span>${GROUPS[g][0]}</span>${GROUPS[g][1].map(([v, t]) => `<button data-v="${v}">${t}</button>`).join('')}</div>`).join('') + `<span class="tag">${tag}</span>`
      ctl.addEventListener('click', (e) => {
        const b = e.target.closest('button'); if (!b) return
        const k = b.parentElement.dataset.k, v = b.dataset.v
        s[k] = k === 'speed' ? +v : v
        refresh()
      })
      const B = window.Backdrop
      B.mount(root.querySelector('.bg'), root.querySelector('.over'))
      function refresh() {
        for (const g of ctl.querySelectorAll('.g')) for (const b of g.querySelectorAll('button')) b.classList.toggle('on', String(s[g.dataset.k]) === b.dataset.v)
        paintFg()
        B.update({ hour: HOURS[s.hour], sources: sources(), s })
      }
      refresh()
      if (B.frame) {
        let clock = 0, last = performance.now()
        const tick = (now) => { clock += (now - last) / 1000 * s.speed; last = now; B.frame(clock); requestAnimationFrame(tick) }
        requestAnimationFrame(tick)
      }
    },
  }
})()
