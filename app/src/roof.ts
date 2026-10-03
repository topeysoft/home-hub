// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * The roof, drawn: what the Roofline's own pane puts across its floor (design/roofline/DrawnC.dc.html,
 * chosen 1 October 2026).
 *
 * It is not a picture of the gable. Nobody has told the house the shape of the roof -- only the order the
 * runs go round in, how many lights each has, and which way each one leaves its box. That is the same
 * description each box is sent (brain/hub/roofline.py `layout`), drawn, so it cannot disagree with the
 * roof: a run as long as its lights, a box where it is, an arrow for the way the run goes, and a part that
 * is dark drawn dark where it is, ringed, with the one next step under it. Until the way round is known
 * the runs can only be drawn apart, each box with its own, which is the board's own caveat.
 *
 * Positions come out as a fraction of the lights plus a fixed number of pixels, so the drawing is one
 * calc() per item and the same arithmetic holds on a 1440 wall and a 390 phone.
 */
import type { Device, RoofBox, Roofline } from './api'
import { LED } from './controller'

type Roof = Extract<Roofline, { exists: true }>

/** Where something sits along the line: `f` of the width the lights get, plus `px` of fixed width. */
export type Pos = { f: number; px: number }
export type RoofRun = { kind: 'run'; chip: string; run: number; n: number; dir: 1 | -1; dark: boolean; group: number; at: Pos; w: number }
export type RoofBoxAt = { kind: 'box'; chip: string; place: string; state: RoofBox['state']; align: 'start' | 'center' | 'end'; group: number; at: Pos }
export type RoofItem = RoofRun | RoofBoxAt
export type RoofRing = { chip: string; from: Pos; to: Pos; align: 'start' | 'end' }
export type RoofSpan = { from: Pos; to: Pos }
export type RoofDrawing = { joined: boolean; groups: number; fixed: number; items: RoofItem[]; rings: RoofRing[]; apart: RoofSpan[] }

/* The board's measures: a box is 22 wide with 8 either side of it, two runs that meet end to end leave a
   10px seam, and boxes drawn apart are 56 from each other. The ring stands 14 off what it holds. */
export const BOX = 22
const BESIDE = 8, SEAM = 10, APART = 56, RING = 14

const isDark = (b: RoofBox | undefined, run: number) =>
  !!b && b.state !== 'Fine' && (!b.dark_runs?.length || b.dark_runs.includes(run))

/** How many lights each run has. A hub from before this pane says only the total, so the runs share it. */
function countsOf(r: Roof): Map<string, number> {
  const out = new Map<string, number>()
  if (r.parts?.length) { for (const p of r.parts) out.set(`${p.chip}${p.run}`, p.count); return out }
  const each = Math.round(r.lights / Math.max(1, r.runs))
  for (const b of r.boxes) for (let k = 1; k <= b.runs; k++) out.set(`${b.chip}${k}`, each)
  return out
}

type Step = { kind: 'run'; chip: string; run: number; dir: 1 | -1; group: number } | { kind: 'box'; chip: string; group: number }

/** The runs in the order they go round, or each box's runs apart; then where each one sits. */
export function roofDrawing(r: Roof): RoofDrawing {
  const count = countsOf(r)
  const box = new Map(r.boxes.map(b => [b.chip, b]))
  const joined = !!r.order?.length
  const steps: Step[] = []
  if (joined) {
    /* A run leaves its box, so its box is at the end it starts from: the left for a run going the way
       round, the right for one turned against it. Two runs leaving one box share it. */
    for (const o of r.order!) {
      if (!count.has(`${o.chip}${o.run}`)) continue
      const dir: 1 | -1 = o.dir < 0 ? -1 : 1
      const last = steps[steps.length - 1]
      if (dir > 0 && !(last?.kind === 'box' && last.chip === o.chip)) steps.push({ kind: 'box', chip: o.chip, group: 0 })
      steps.push({ kind: 'run', chip: o.chip, run: o.run, dir, group: 0 })
      if (dir < 0) steps.push({ kind: 'box', chip: o.chip, group: 0 })
    }
  } else {
    /* Apart: every run's first light is at its board, which the house knows without being shown. A box
       with two sends one each way; which is which is the very thing still to be asked. */
    r.boxes.forEach((b, g) => {
      if (b.runs > 1 && count.has(`${b.chip}2`)) steps.push({ kind: 'run', chip: b.chip, run: 2, dir: -1, group: g })
      steps.push({ kind: 'box', chip: b.chip, group: g })
      steps.push({ kind: 'run', chip: b.chip, run: 1, dir: 1, group: g })
    })
  }
  const lights = steps.reduce((s, x) => s + (x.kind === 'run' ? count.get(`${x.chip}${x.run}`) ?? 0 : 0), 0) || 1
  const items: RoofItem[] = []
  let f = 0, px = 0
  steps.forEach((s, i) => {
    const prev = steps[i - 1]
    if (prev) px += prev.group !== s.group ? APART : prev.kind === 'run' && s.kind === 'run' ? SEAM : BESIDE
    if (s.kind === 'box') {
      const b = box.get(s.chip)
      const align = i === 0 ? 'start' : i === steps.length - 1 ? 'end' : 'center'
      items.push({ kind: 'box', chip: s.chip, place: b?.place ?? '', state: b?.state ?? 'Fine', align, group: s.group, at: { f, px } })
      px += BOX
    } else {
      const n = count.get(`${s.chip}${s.run}`) ?? 0
      items.push({ kind: 'run', chip: s.chip, run: s.run, n, dir: s.dir, dark: isDark(box.get(s.chip), s.run), group: s.group, at: { f, px }, w: n / lights })
      f += n / lights
    }
  })
  /* A ring round each dark box's dark runs, and the box itself: the stretch to go and look at. */
  const rings: RoofRing[] = []
  for (const b of r.boxes) {
    const idx = items.map((it, i) => ((it.kind === 'run' && it.dark && it.chip === b.chip) || (it.kind === 'box' && it.chip === b.chip) ? i : -1)).filter(i => i >= 0)
    if (!idx.some(i => items[i].kind === 'run')) continue
    const first = items[idx[0]], end = endOf(items[idx[idx.length - 1]])
    /* Against a seam the ring keeps to its own half of it, so it never takes in the neighbor's last light. */
    const pad = (inner: number, near: number) => {
      const a = steps[inner], b = steps[near]
      if (!b || a.group !== b.group) return RING
      return (a.kind === 'run' && b.kind === 'run' ? SEAM : BESIDE) / 2
    }
    const lo = idx[0], hi = idx[idx.length - 1]
    rings.push({ chip: b.chip, from: { f: first.at.f, px: first.at.px - pad(lo, lo - 1) }, to: { f: end.f, px: end.px + pad(hi, hi + 1) },
                 align: (idx[0] + idx[idx.length - 1]) / 2 >= (items.length - 1) / 2 ? 'end' : 'start' })
  }
  /* Drawn apart, each box and its runs is a stretch of its own, with a gap the width of a step between. */
  const apart: RoofSpan[] = []
  if (!joined) for (let g = 0; g < r.boxes.length; g++) {
    const its = items.filter(it => it.group === g)
    if (its.length) apart.push({ from: its[0].at, to: endOf(its[its.length - 1]) })
  }
  return { joined, groups: joined ? 1 : r.boxes.length, fixed: px, items, rings, apart }
}

/** Where an item ends along the line. */
export const endOf = (it: RoofItem): Pos => it.kind === 'run' ? { f: it.at.f + it.w, px: it.at.px } : { f: it.at.f, px: it.at.px + BOX }

/** The calc() a position becomes, on a line whose fixed parts add up to `fixed`. */
export const calcOf = (p: Pos, fixed: number) => `calc((100% - ${fixed}px) * ${+p.f.toFixed(6)} + ${p.px}px)`
export const widthOf = (w: number, fixed: number) => `calc((100% - ${fixed}px) * ${+w.toFixed(6)})`

/* ---------- the lights on it ---------- */

/** How many lights each drawn dot stands for, on a line with `room` pixels for lights: never fewer than
 *  two (the board draws one in two), and never closer than 4.8px a dot, where a 4.4px dot stops being one. */
export const dotPitch = (lights: number, room: number) => Math.max(2, Math.ceil((lights * 4.8) / Math.max(1, room)))

export type RoofDot = { c1: string; c2: string; off: boolean; motion: 'still' | 'chase' | 'flicker'; delay: number; dur: number }
const css = (c: number[]) => `rgb(${c.join(',')})`

/** One dot for every `pitch` lights, in the look's own emitter colors (AGENTS.md section 4: what the roof
 *  is asked for, never the panel's palette), in its blocks; a dark run's lights, and all of them while the
 *  roof is off, are unlit. A chase is drawn as the board draws it: each light a little behind the one
 *  before, so the colors travel. */
export function roofDots(d: RoofDrawing, r: Roof, pitch: number, on = true): RoofDot[][] {
  const look = r.look ?? { motion: 'off' }
  const colors = look.colors?.length ? look.colors : [LED.warm]
  const block = Math.max(1, look.block ?? 1)
  const motion: RoofDot['motion'] = look.motion === 'chase' || look.motion === 'drift' ? 'chase'
    : look.motion === 'flicker' || look.motion === 'twinkle' ? 'flicker' : 'still'
  const dur = (look.ms || 2800) / 1000
  const period = Math.max(2, Math.round(16 / pitch))
  let g = 0
  return d.items.map(it => {
    if (it.kind !== 'run') return []
    const k = Math.max(1, Math.round(it.n / pitch))
    return Array.from({ length: k }, () => {
      const at = g++ * pitch, b = Math.floor(at / block)
      const dot: RoofDot = { c1: css(colors[b % colors.length]), c2: css(colors[(b + 1) % colors.length]), off: !on || it.dark, motion, dur, delay: 0 }
      if (motion === 'chase') dot.delay = -(((g - 1) % period) / period) * dur
      else if (motion === 'flicker') dot.delay = -(((g * 7919) % 97) / 97) * dur
      return dot
    })
  })
}

/* ---------- what the pane says about it ---------- */

const WORDS = ['no', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight']
const darkOf = (r: Roof) => r.boxes.find(b => b.state !== 'Fine')
const placeIn = (b: RoofBox) => b.place.replace(/^The /, '').toLowerCase()
export type Said = { text: string; wrong: boolean }

/** The left column's one sentence: what is wrong when something is, else why it is on (or off). */
export function roofSentence(d: Device, r: Roof): Said {
  const dark = darkOf(r)
  if (dark) return d.state === 'on' ? { text: `On, but the ${placeIn(dark)} is dark.`, wrong: true }
    : { text: `Off. The ${placeIn(dark)} would stay dark.`, wrong: true }
  return { text: (r.why.match(/^.*?[.?!](?=\s|$)/)?.[0] ?? r.why), wrong: false }
}

/** The line under the roof: the dark box's own words, the way round still to be asked, or that all is well. */
export function roofNext(r: Roof): Said {
  const dark = darkOf(r)
  if (dark) return { text: dark.sub, wrong: true }
  if (!r.order?.length && r.ask_order) return { text: `${r.occasion_name ?? 'A chase'} goes round the house. Show it which way round?`, wrong: false }
  const n = r.boxes.length
  const who = n === 1 ? 'Its controller' : n === 2 ? 'Both' : `All ${WORDS[n] ?? n}`
  if (r.came_on) {
    const t = new Date(r.came_on.at * 1000).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
    return { text: `${who} ${n === 1 ? 'was' : 'were'} working when it came on, at ${t}.`, wrong: false }
  }
  return { text: `${who} ${n === 1 ? 'is' : 'are'} working.`, wrong: false }
}

/* Dates decide which occasion is showing (brain/hub/roofline.py `occasion_on`). Easter moves, so the
   brain says its dates; these are the three that do not, for a hub from before it did. */
const DATES: Record<string, string> = { christmas: 'Dec 1 – Jan 6', halloween: 'Oct 24 – Nov 1', july4: 'Jul 3 – 5' }
export const lookDates = (r: Roof) => r.occasion_dates ?? (r.occasion ? DATES[r.occasion] ?? '' : '')

/** Its evenings, as the card heads them: when, and how often, like a porch light. */
export function evenOf(r: Roof): { name: string; sub: string } {
  if (!r.evenings || r.evenings === 'never') return { name: 'Not by itself', sub: 'On when somebody turns it on' }
  return { name: `On at dusk, off at ${r.until_words}`,
           sub: r.evenings === 'every' ? 'Every evening, like a porch light' : 'Only for occasions' }
}
