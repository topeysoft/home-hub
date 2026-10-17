// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Draws the boot splash's images from sequence.mjs and writes the theme beside them, into
// startup/plymouth/elyir/. Run after changing sequence.mjs:
//
//   node startup/render.mjs
//
// It borrows the panel's Playwright (app/node_modules) to draw; PLAYWRIGHT=<path to the package's
// index.mjs> points it at another copy.
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { COLOR, NAME, HOUSE, TIME, SLOW } from './sequence.mjs'
import { THEME, K, NAME_FRAMES, fingerprint, themeFile, timingSh, script } from './plymouth.mjs'

const OUT = new URL(`plymouth/${THEME}/`, import.meta.url)
const from = process.env.PLAYWRIGHT ?? new URL('../app/node_modules/playwright/index.mjs', import.meta.url).href
const { chromium } = await import(from)

const rgb = (c, a = 1) => `rgba(${c.join(',')},${a})`
const ease = (x) => x * x * (3 - 2 * x)
const LINE = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 2000, height: 1400 } })
await page.setContent(`<!doctype html><html><head>
  <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400&display=swap">
  <style>html,body{margin:0;background:transparent} #c{position:absolute;left:0;top:0}</style></head><body><div id="c"></div></body></html>`)
await page.evaluate(() => document.fonts.ready)

async function shoot(file, w, h, html) {
  await page.evaluate(([w, h, html]) => {
    const c = document.getElementById('c')
    Object.assign(c.style, { width: w + 'px', height: h + 'px' })
    c.innerHTML = html
  }, [Math.round(w), Math.round(h), html])
  await page.locator('#c').screenshot({ path: new URL(file, OUT).pathname, omitBackground: true })
}

rmSync(OUT, { recursive: true, force: true })
mkdirSync(OUT, { recursive: true })

// The name, frame by frame as the pen goes, without its dot: the dot is a lamp of its own.
const nw = NAME.width * K, nh = NAME.height * K
const total = await page.evaluate((d) => {
  const p = document.createElementNS('http://www.w3.org/2000/svg', 'path')
  p.setAttribute('d', d)
  return p.getTotalLength()
}, NAME.d)
for (let i = 0; i < NAME_FRAMES; i++) {
  const shown = total * ease(i / (NAME_FRAMES - 1))
  await shoot(`name-${String(i).padStart(2, '0')}.png`, nw, nh, `<svg width="${nw}" height="${nh}" viewBox="${NAME.viewBox.join(' ')}">
    <path d="${NAME.d}" stroke="${COLOR.ink}" stroke-width="${NAME.stroke}" ${LINE}
      stroke-dasharray="${total} ${total}" stroke-dashoffset="${total - shown}" ${shown === 0 ? 'opacity="0"' : ''}/></svg>`)
}

// The lamp, lit and unlit, drawn large; the splash scales it to whatever size the moment wants.
const disc = (c) => `<div style="width:128px;height:128px;border-radius:50%;background:${rgb(c)}"></div>`
await shoot('dot.png', 128, 128, disc(COLOR.lamp))
await shoot('dot-unlit.png', 128, 128, disc(COLOR.unlit))

// The dot's own glow, drawn around a dot 32 px across and scaled with the dot. A shadow
// is not painted under its own box, so the box is filled too; otherwise a smaller dot shows a dark ring.
const g = (32 + 180) * K, d = 32 * K
await shoot('dot-glow.png', g, g, `<div style="position:absolute;left:${(g - d) / 2}px;top:${(g - d) / 2}px;width:${d}px;height:${d}px;border-radius:50%;
  background:${rgb(COLOR.lamp, 0.45)};box-shadow:0 0 ${60 * K}px ${18 * K}px ${rgb(COLOR.lamp, 0.45)}"></div>`)

// The house's outline, without its lamp, and the wide warm glow the lamp throws in it.
const hs = HOUSE.size * K
await shoot('house.png', hs, hs, `<svg width="${hs}" height="${hs}" viewBox="0 0 512 512">
  <path d="${HOUSE.roof}" stroke="${COLOR.ink}" stroke-width="${HOUSE.stroke}" ${LINE}/>
  <path d="${HOUSE.walls}" stroke="${COLOR.ink}" stroke-width="${HOUSE.stroke}" ${LINE}/></svg>`)
const hg = HOUSE.size * 1.1 * K
await shoot('house-glow.png', hg, hg, `<div style="width:100%;height:100%;border-radius:50%;
  background:radial-gradient(circle, ${rgb(COLOR.lamp, 0.55)}, ${rgb(COLOR.lamp, 0)} 68%)"></div>`)

// The one sentence a slow start shows.
const sw = 1100 * K, sh = 80 * K
await shoot('slow.png', sw, sh, `<div style="width:${sw}px;text-align:center;font:400 ${24 * K}px/1.35 'Instrument Sans',sans-serif;color:#b9b5ad">${SLOW}</div>`)

await browser.close()

writeFileSync(new URL(`${THEME}.plymouth`, OUT), themeFile())
writeFileSync(new URL(`${THEME}.script`, OUT), script())
writeFileSync(new URL('timing.sh', OUT), timingSh())
writeFileSync(new URL('fingerprint', OUT), fingerprint() + '\n')
console.log(`drew ${NAME_FRAMES} frames of the name and the splash's lamp, house and sentence into ${OUT.pathname}`)
