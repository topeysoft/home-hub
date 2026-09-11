<script setup lang="ts">
/**
 * The sky behind the panel. One canvas, a few hundred cheap draws a frame: a gradient that follows the
 * sun's elevation, sun or moon with its phase, stars, drifting clouds, rain, snow, fog, the odd flash
 * of lightning, and a landscape the interface sits on: rolling ground in the colours of the season, lit by the sun,
 * grey under cloud, white under snow, and a dark silhouette at night. Weather comes from the house; the sun from
 * the clock. Everything is deterministic from `store.sky`, so it looks the same on every screen.
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { store } from './store'
import { clamp, lerp, mix, palette, rgb, wxOf, type RGB, type Wx } from './sky'

/* quiet: the interface is up, so the sun and moon stay softer and the moon keeps to the open sky above the stage,
   clear of the rail and the headline; at rest and during setup they have the whole screen */
const props = defineProps<{ quiet?: boolean }>()

const canvas = ref<HTMLCanvasElement | null>(null)

/* the sky's tables live in sky.ts, so tone.ts colours the panel from the very
   same numbers this canvas paints with — see the note at the top of tone.ts */
/* scene state, generated once and reused */
type Cloud = { x: number; y: number; s: number; v: number; puffs: { dx: number; dy: number; r: number }[] }
type Drop = { x: number; y: number; l: number; v: number }
const rnd = mulberry(7)
function mulberry(seed: number) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296 } }
const stars = Array.from({ length: 170 }, () => ({ x: rnd(), y: rnd() * .72, r: .6 + rnd() * 1.4, p: rnd() * 6.28, w: .6 + rnd() * 1.6 }))
const clouds: Cloud[] = []
function makeCloud(x = rnd()): Cloud {
  const n = 4 + Math.floor(rnd() * 3)
  const puffs = Array.from({ length: n }, (_, i) => ({ dx: (i / (n - 1) - .5) * 1.6, dy: (rnd() - .5) * .35, r: .45 + rnd() * .4 }))
  return { x, y: .08 + rnd() * .42, s: .09 + rnd() * .12, v: .004 + rnd() * .006, puffs }
}
const drops: Drop[] = Array.from({ length: 160 }, () => ({ x: rnd(), y: rnd(), l: .02 + rnd() * .03, v: .9 + rnd() * .6 }))
const flakes = Array.from({ length: 110 }, () => ({ x: rnd(), y: rnd(), r: 1 + rnd() * 1.8, v: .05 + rnd() * .06, p: rnd() * 6.28 }))
/* a treeline on the middle ridge: a few stands of round and pointed trees, placed once */
const trees = Array.from({ length: 34 }, (_, i) => {
  const stand = [.08, .3, .58, .86][i % 4]
  return { x: stand + (rnd() - .5) * .16, h: .014 + rnd() * .016, w: .55 + rnd() * .35, pine: rnd() < .35 }
})
let flash = 0, nextFlash = 6
let meteor: { x: number; y: number; vx: number; vy: number; life: number } | null = null

let ctx: CanvasRenderingContext2D | null = null, W = 0, H = 0, raf = 0, last = 0, ro: ResizeObserver | undefined
const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')

function resize() {
  const c = canvas.value; if (!c) return
  const dpr = Math.min(window.devicePixelRatio || 1, 1.5)
  W = c.clientWidth; H = c.clientHeight
  c.width = Math.round(W * dpr); c.height = Math.round(H * dpr)
  ctx = c.getContext('2d'); ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)
}

function draw(t: number, dt: number) {
  if (!ctx || !W || !H) return
  const { elevation: el, azimuth: az, phase, hour, month, condition } = store.sky
  const wx = wxOf(condition)
  const [top, mid, hor] = palette(el, wx)
  const horizon = H * .8, m = Math.min(W, H)

  /* sky */
  const g = ctx.createLinearGradient(0, 0, 0, horizon)
  g.addColorStop(0, rgb(top)); g.addColorStop(.55, rgb(mid)); g.addColorStop(1, rgb(hor))
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)

  /* stars */
  const starA = clamp((-el - 3) / 8) * (1 - wx.clouds * .9) * (1 - wx.fog * .8)
  if (starA > 0) {
    ctx.fillStyle = '#fff'
    for (const s of stars) {
      ctx.globalAlpha = starA * (.55 + .45 * Math.sin(t * s.w + s.p))
      ctx.fillRect(s.x * W, s.y * H, s.r, s.r)
    }
    ctx.globalAlpha = 1
    /* now and then, on a clear night, a meteor */
    if (!meteor && starA > .6 && Math.random() < dt / 45) meteor = { x: .2 + Math.random() * .6, y: .05 + Math.random() * .3, vx: .5 + Math.random() * .3, vy: .18 + Math.random() * .12, life: 1 }
    if (meteor) {
      const m2 = meteor, len = .06
      const gm = ctx.createLinearGradient((m2.x - m2.vx * len) * W, (m2.y - m2.vy * len) * H, m2.x * W, m2.y * H)
      gm.addColorStop(0, 'rgba(255,255,255,0)'); gm.addColorStop(1, `rgba(255,255,255,${.85 * m2.life * starA})`)
      ctx.strokeStyle = gm; ctx.lineWidth = 1.2; ctx.beginPath()
      ctx.moveTo((m2.x - m2.vx * len) * W, (m2.y - m2.vy * len) * H); ctx.lineTo(m2.x * W, m2.y * H); ctx.stroke()
      m2.x += m2.vx * dt; m2.y += m2.vy * dt; m2.life -= dt * 1.6
      if (m2.life <= 0) meteor = null
    }
  }

  /* sun */
  const sx = W * lerp(.06, .94, clamp((az - 70) / 220))
  if (el > -9) {
    const sy = horizon - (clamp(el, -9, 75) / 75) * (horizon - m * .1)
    const low = clamp(1 - el / 25)
    const col: RGB = mix([255, 236, 200], [255, 160, 84], low)
    const dim = (1 - wx.clouds * .75 - wx.fog * .5) * (1 + .06 * Math.sin(t * .45))   // a slow breath in the glow
    const halo = ctx.createRadialGradient(sx, sy, 0, sx, sy, m * (.45 + low * .25))
    halo.addColorStop(0, rgb(col, .55 * dim)); halo.addColorStop(.25, rgb(col, .18 * dim)); halo.addColorStop(1, rgb(col, 0))
    ctx.fillStyle = halo; ctx.fillRect(0, 0, W, H)
    if (el > -2) {
      const dd = dim * (props.quiet ? .6 : 1)
      const disc = ctx.createRadialGradient(sx, sy, 0, sx, sy, m * .05)
      disc.addColorStop(0, rgb([255, 250, 236], dd)); disc.addColorStop(.6, rgb(col, .9 * dd)); disc.addColorStop(1, rgb(col, 0))
      ctx.fillStyle = disc; ctx.beginPath(); ctx.arc(sx, sy, m * .05, 0, 6.29); ctx.fill()
    }
  }

  /* moon */
  const moonA = clamp((-el - 1) / 7) * (1 - wx.clouds * .6) * (props.quiet ? .6 : 1)
  if (moonA > 0) {
    const f = clamp((((hour + 24 - 19) % 24)) / 11)             // its slow arc across the night
    const q = props.quiet && W > H                              // a wide, awake panel has a rail on the left and a headline at the top
    const mx = W * lerp(q ? .32 : .12, q ? .9 : .88, f), my = horizon - Math.sin(Math.PI * f) * (q ? m * .22 : horizon - m * .12) - m * .02
    const r = m * .028
    const glow = ctx.createRadialGradient(mx, my, r * .5, mx, my, r * 7)
    glow.addColorStop(0, rgb([214, 222, 240], .22 * moonA * (1 + .08 * Math.sin(t * .35)))); glow.addColorStop(1, rgb([214, 222, 240], 0))
    ctx.fillStyle = glow; ctx.fillRect(0, 0, W, H)
    ctx.save(); ctx.globalAlpha = moonA
    ctx.beginPath(); ctx.arc(mx, my, r, 0, 6.29); ctx.clip()                 // the shadow only ever falls on the moon itself
    ctx.fillStyle = rgb([230, 234, 244]); ctx.fillRect(mx - r, my - r, r * 2, r * 2)
    const k = phase < .5 ? phase / .5 : (1 - phase) / .5           // 0 new → 1 full
    ctx.fillStyle = rgb(mix(top, [0, 0, 0], .3)); ctx.beginPath(); ctx.arc(mx + (phase < .5 ? -1 : 1) * r * 2 * k, my, r * 1.02, 0, 6.29); ctx.fill()
    ctx.restore()
  }

  /* clouds */
  const want = Math.max(2, Math.round(wx.clouds * 9))
  const wisp = clamp(wx.clouds * 2.5, .3, 1)                  // clear skies get a couple of faint wisps
  while (clouds.length < want) clouds.push(makeCloud())
  while (clouds.length > want) clouds.pop()
  if (clouds.length) {
    const day = clamp((el + 4) / 14)
    const body = mix(mix(mid, [255, 255, 255], .22 * day + .04), [30, 32, 40], wx.rain * .5)
    for (const c of clouds) {
      c.x += c.v * wx.wind * dt; if (c.x > 1.3) c.x -= 1.6
      const cx = c.x * W, cy = c.y * H, S = c.s * m
      for (const p of c.puffs) {
        const px = cx + p.dx * S, py = cy + p.dy * S, pr = p.r * S
        const cg = ctx.createRadialGradient(px, py, 0, px, py, pr)
        cg.addColorStop(0, rgb(body, .5 * wisp)); cg.addColorStop(.6, rgb(body, .3 * wisp)); cg.addColorStop(1, rgb(body, 0))
        ctx.fillStyle = cg; ctx.beginPath(); ctx.arc(px, py, pr, 0, 6.29); ctx.fill()
      }
    }
  }

  /* haze: two thin bands sliding along the horizon, so the scene is never quite still */
  const hazeCol = mix(hor, [255, 255, 255], .18)
  for (let i = 0; i < 2; i++) {
    const base = horizon - H * (.16 - i * .06), amp = H * (.022 + i * .01), sp = .07 + i * .05
    const hg = ctx.createLinearGradient(0, base - amp - H * .06, 0, horizon)
    hg.addColorStop(0, rgb(hazeCol, 0)); hg.addColorStop(1, rgb(hazeCol, .09 - i * .03))
    ctx.fillStyle = hg; ctx.beginPath(); ctx.moveTo(0, horizon)
    for (let x = 0; x <= W; x += 20) ctx.lineTo(x, base - Math.sin(x / W * 5.5 + t * sp + i * 2) * amp - Math.sin(x / W * 13 - t * sp * .6) * amp * .4)
    ctx.lineTo(W, horizon); ctx.closePath(); ctx.fill()
  }

  /* fog */
  if (wx.fog) {
    const fg = ctx.createLinearGradient(0, horizon * .45, 0, horizon)
    fg.addColorStop(0, rgb([150, 156, 164], 0)); fg.addColorStop(1, rgb([150, 156, 164], .38 * wx.fog))
    ctx.fillStyle = fg; ctx.fillRect(0, 0, W, H)
  }

  /* rain and snow */
  if (wx.rain) {
    ctx.strokeStyle = rgb([200, 214, 232], .28); ctx.lineWidth = 1; ctx.beginPath()
    const n = Math.round(drops.length * wx.rain), slant = .18 * wx.wind
    for (let i = 0; i < n; i++) {
      const d = drops[i]; d.y += d.v * dt * (1 + wx.rain * .6); d.x += slant * dt * .4
      if (d.y > 1) { d.y = -.05; d.x = rnd() }
      if (d.x > 1.05) d.x -= 1.1
      const x = d.x * W, y = d.y * H
      ctx.moveTo(x, y); ctx.lineTo(x - slant * d.l * H, y + d.l * H)
    }
    ctx.stroke()
  }
  if (wx.snow) {
    ctx.fillStyle = rgb([240, 244, 250], .85)
    const n = Math.round(flakes.length * wx.snow)
    for (let i = 0; i < n; i++) {
      const f = flakes[i]; f.y += f.v * dt; f.x += Math.sin(t * .8 + f.p) * .0004 * wx.wind
      if (f.y > 1) { f.y = -.02; f.x = rnd() }
      ctx.beginPath(); ctx.arc(f.x * W, f.y * H, f.r, 0, 6.29); ctx.fill()
    }
  }

  /* lightning */
  if (wx.lightning) {
    nextFlash -= dt
    if (nextFlash <= 0) { flash = 1; nextFlash = 5 + rnd() * 10 }
    if (flash > 0) { ctx.fillStyle = rgb([230, 236, 255], .28 * flash); ctx.fillRect(0, 0, W, H); flash = Math.max(0, flash - dt * 7) }
  }

  /* land */
  land(el, sx, month, wx, hor)
}

/* ---------- the ground ---------- */
const ridgeY = (x: number, base: number, amp: number, k: number, ph: number) =>
  base - (Math.sin(x / W * 6.3 * k + 1.7 + ph) * .55 + Math.sin(x / W * 15 * k + ph * 2) * .3 + Math.sin(x / W * 31 * k + ph) * .15) * amp * H
function ridge(base: number, amp: number, k: number, ph: number) {
  if (!ctx) return
  ctx.beginPath(); ctx.moveTo(0, H)
  for (let x = 0; x <= W + 8; x += 8) ctx.lineTo(x, ridgeY(x, base, amp, k, ph))
  ctx.lineTo(W, H); ctx.closePath()
}
/* what the ground is made of, before the light gets to it */
const GROUND: [number, RGB][] = [                              // keyframes by seasonal month (0.5 is mid-January)
  [.5, [150, 138, 106]],                                       // midwinter: dun, dead grass
  [2.5, [136, 146, 88]],                                       // the first green of March
  [4, [126, 176, 78]],                                         // spring: fresh and bright
  [6.5, [108, 156, 72]],                                       // high summer: deep green
  [8.5, [122, 150, 74]],                                       // late summer: still green, a little dry
  [10, [182, 140, 70]],                                        // autumn: ochre
  [11.5, [154, 136, 100]],                                     // the year closing down
]
function groundColour(month: number, wx: Wx): RGB {
  const m = ((month - .5) % 12 + 12) % 12 + .5                 // wrap so mid-January sits at .5 and December runs into it
  let i = 0; while (i < GROUND.length - 2 && m > GROUND[i + 1][0]) i++
  const [m0, a] = GROUND[i], [m1, b] = GROUND[i + 1]
  let c = m > GROUND[GROUND.length - 1][0] ? mix(GROUND[GROUND.length - 1][1], GROUND[0][1], (m - 11.5)) : mix(a, b, clamp((m - m0) / (m1 - m0)))
  c = mix(c, [232, 236, 242], clamp(wx.snow * 1.3))            // snow cover
  c = mix(c, [118, 122, 118], wx.clouds * .3)                  // overcast leaches the colour out
  c = mix(c, [56, 62, 62], wx.rain * .35)                      // wet ground is dark
  return c
}
function land(el: number, sx: number, month: number, wx: Wx, hor: RGB) {
  if (!ctx) return
  const horizon = H * .8
  const day = clamp((el + 6) / 18)                             // how much daylight reaches the ground
  const night: RGB = [9, 10, 13]
  const warm = clamp(1 - el / 22) * clamp((el + 4) / 6)        // low sun gilds the land
  let base = groundColour(month, wx)
  base = mix(base, [255, 168, 88], warm * .22)
  base = mix(night, base, day)
  const flat = 1 - wx.clouds * .8 - wx.fog * .9                // cloud flattens the light; no lit side, no shadow side
  const hazeCol = mix(hor, [150, 156, 164], wx.fog * .6)
  /* three ridges, far to near: the far ones fade into the sky, the near one is the truest colour */
  const ridges: [number, number, number, number, number, number][] = [
    /* base offset, amplitude, frequency, phase, atmospheric fade, brightness */
    [-.032, .05, .45, .8, .55 * (.35 + day * .65), .92],
    [-.012, .034, 1.05, 0, .26 * (.3 + day * .7), .96],
    [.016, .024, 2.1, 2.4, .06, 1],
  ]
  ridges.forEach(([off, amp, k, ph, fade, bright], n) => {
    const col = mix(base.map(v => v * bright) as RGB, hazeCol, fade)
    const top = horizon + off * H - amp * H
    const g = ctx!.createLinearGradient(0, top, 0, Math.min(H, top + H * .3))
    g.addColorStop(0, rgb(col)); g.addColorStop(1, rgb(mix(col, night, .3 - .2 * day)))   // by day the meadow stays light all the way down
    ridge(horizon + off * H, amp, k, ph)
    ctx!.fillStyle = g; ctx!.fill()
    if (day > 0 && flat > 0) {
      /* the side facing the sun catches it, the other side falls into shade */
      const l = ctx!.createLinearGradient(0, 0, W, 0), a = day * flat * (n === 0 ? .5 : 1)
      const lit = rgb([255, 244, 214], .12 * a), shade = rgb([10, 16, 30], .09 * a)
      l.addColorStop(0, sx < W * .5 ? lit : shade); l.addColorStop(clamp(sx / W, .05, .95), lit); l.addColorStop(1, sx < W * .5 ? shade : lit)
      ctx!.fillStyle = l; ctx!.fill()
    }
    if (n === 1) {
      /* the treeline sits on the middle ridge, a shade darker than the ground it grows from */
      const tc = mix(mix(base.map(v => v * .55) as RGB, hazeCol, fade * .6), [24, 40, 30], day * .3 * (1 - wx.snow))
      ctx!.fillStyle = rgb(mix(tc, [226, 232, 240], wx.snow * .3))
      for (const t of trees) {
        const x = t.x * W, y = ridgeY(x, horizon + off * H, amp, k, ph) + H * .003, h = t.h * H * Math.min(1, W / H / 1.3), w = h * t.w
        ctx!.beginPath()
        if (t.pine) { ctx!.moveTo(x - w * .5, y); ctx!.lineTo(x, y - h); ctx!.lineTo(x + w * .5, y) }
        else { ctx!.moveTo(x - w * .5, y); ctx!.arc(x, y - h * .55, w * .5, Math.PI, 0); ctx!.lineTo(x + w * .5, y) }
        ctx!.closePath(); ctx!.fill()
      }
    }
  })
}

function frame(ts: number) {
  raf = requestAnimationFrame(frame)
  const dt = Math.min(.1, (ts - last) / 1000)
  if (dt < 1 / 30) return                                   // 30 fps is plenty for weather
  last = ts
  if (document.hidden) return
  draw(ts / 1000, dt)
}
onMounted(() => {
  resize()
  ro = new ResizeObserver(resize); ro.observe(canvas.value!)
  if (reduced.matches) { draw(0, 0); watch(() => store.sky, () => draw(0, 0), { deep: true }); return }
  raf = requestAnimationFrame(frame)
})
onUnmounted(() => { cancelAnimationFrame(raf); ro?.disconnect() })
</script>

<template>
  <canvas ref="canvas" class="sky" aria-hidden="true"></canvas>
</template>
