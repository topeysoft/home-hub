<script setup lang="ts">
/**
 * The sky behind the panel. One canvas, a few hundred cheap draws a frame: a gradient that follows the
 * sun's elevation, sun or moon with its phase, stars, drifting clouds, rain, snow, fog, the odd flash
 * of lightning, and a dark landscape the interface sits on. Weather comes from the house; the sun from
 * the clock. Everything is deterministic from `store.sky`, so it looks the same on every screen.
 */
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { store } from './store'

/* quiet: the interface is up, so the sun and moon stay softer and the moon keeps to the open sky above the stage,
   clear of the rail and the headline; at rest and during setup they have the whole screen */
const props = defineProps<{ quiet?: boolean }>()

type RGB = [number, number, number]
const canvas = ref<HTMLCanvasElement | null>(null)

/* palette keyframes by sun elevation: [top, middle, horizon] */
const KEYS: [number, RGB[]][] = [
  [-18, [[4, 5, 10], [7, 9, 16], [12, 14, 26]]],
  [-9, [[6, 7, 16], [14, 16, 34], [44, 32, 56]]],
  [-3, [[10, 14, 34], [38, 34, 74], [158, 84, 60]]],
  [0, [[14, 24, 52], [56, 62, 106], [220, 134, 74]]],
  [6, [[18, 40, 80], [54, 98, 142], [222, 170, 108]]],
  [15, [[22, 60, 108], [58, 124, 174], [184, 184, 172]]],
  [40, [[26, 78, 136], [70, 148, 202], [170, 200, 218]]],
  [90, [[26, 78, 136], [70, 148, 202], [170, 200, 218]]],
]
type Wx = { clouds: number; rain: number; snow: number; fog: number; lightning: boolean; wind: number }
const COND: Record<string, Partial<Wx>> = {
  sunny: { clouds: .06 }, 'clear-night': { clouds: .06 }, partlycloudy: { clouds: .42 }, cloudy: { clouds: .9 },
  fog: { clouds: .5, fog: 1 }, rainy: { clouds: .9, rain: .6 }, pouring: { clouds: 1, rain: 1 }, hail: { clouds: 1, rain: .8 },
  lightning: { clouds: 1, lightning: true }, 'lightning-rainy': { clouds: 1, rain: .8, lightning: true },
  snowy: { clouds: .9, snow: .7 }, 'snowy-rainy': { clouds: 1, snow: .5, rain: .4 }, windy: { clouds: .3, wind: 3 }, 'windy-variant': { clouds: .7, wind: 3 },
  exceptional: { clouds: .5 },
}
const wxOf = (c: string): Wx => ({ clouds: 0, rain: 0, snow: 0, fog: 0, lightning: false, wind: 1, ...COND[c] })

const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const mix = (a: RGB, b: RGB, t: number): RGB => [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)]
const rgb = (c: RGB, a = 1) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${a})`
const clamp = (v: number, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))
function palette(el: number, wx: Wx): RGB[] {
  let i = 0; while (i < KEYS.length - 2 && el > KEYS[i + 1][0]) i++
  const [e0, a] = KEYS[i], [e1, b] = KEYS[i + 1]
  const t = clamp((el - e0) / (e1 - e0))
  return a.map((c, k) => {
    let out = mix(c, b[k], t)
    out = mix(out, [58, 64, 72], wx.clouds * .55)             // overcast greys the sky
    out = mix(out, [22, 24, 30], wx.rain * .3)                // rain darkens it
    out = mix(out, [116, 122, 128], wx.fog * .3)              // fog flattens it
    return out
  })
}

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
  const { elevation: el, azimuth: az, phase, hour, condition } = store.sky
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
  if (el > -9) {
    const sx = W * lerp(.06, .94, clamp((az - 70) / 220)), sy = horizon - (clamp(el, -9, 75) / 75) * (horizon - m * .1)
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
    const mx = W * lerp(q ? .32 : .12, q ? .9 : .88, f), my = horizon - Math.sin(Math.PI * f) * (horizon - m * (q ? .3 : .12)) - m * .02
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
  hills(horizon - H * .012, [16, 18, 24], .08, .3)
  hills(horizon + H * .008, [9, 10, 13], .045, 1.9)
  ctx.fillStyle = rgb([9, 10, 13]); ctx.fillRect(0, horizon + H * .05, W, H)
}
function hills(base: number, col: RGB, amp: number, k: number) {
  if (!ctx) return
  ctx.fillStyle = rgb(col); ctx.beginPath(); ctx.moveTo(0, H)
  for (let x = 0; x <= W; x += 16) ctx.lineTo(x, base - (Math.sin(x / W * 6.3 * k + 1.7) * .6 + Math.sin(x / W * 15 * k) * .4) * amp * H)
  ctx.lineTo(W, H); ctx.closePath(); ctx.fill()
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
