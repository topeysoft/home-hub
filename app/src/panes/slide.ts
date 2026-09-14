/*
 * Dragging a level with a finger, for the instruments that are a level: a lamp's brightness, its
 * warmth, a blind's height, a speaker's volume.
 *
 * Two rules, both learned from the tiles. The pointer is CAPTURED on the way down, so a thumb that
 * wanders off the edge of a 168px column keeps dragging instead of stopping dead. And the house is
 * only told on the way UP: a drag down a column is forty pointermoves, and forty service calls to a
 * Zigbee lamp is how a bulb falls off a mesh. What moves while the finger is down is the drawing.
 */
import { ref } from 'vue'

/** Where along an element a pointer is, 0-100. Vertical columns fill from the bottom. */
export function levelFrom(e: PointerEvent, el: HTMLElement, vertical = true): number {
  const r = el.getBoundingClientRect()
  const v = vertical ? 1 - (e.clientY - r.top) / r.height : (e.clientX - r.left) / r.width
  return Math.round(Math.min(1, Math.max(0, v)) * 100)
}

export function useSlide(opts: { vertical?: boolean | (() => boolean); live: (pct: number) => void; settle: (pct: number) => void; step?: number }) {
  const held = ref(false)
  /* A function, not a boolean, because the same control is a column on a wall and a bar on a phone
     and the axis has to be asked for at the moment the finger lands. */
  const vertical = () => typeof opts.vertical === 'function' ? opts.vertical() : opts.vertical ?? true
  const step = opts.step ?? 5
  function down(e: PointerEvent) {
    if (e.button !== undefined && e.button !== 0) return
    const el = e.currentTarget as HTMLElement
    try { el.setPointerCapture(e.pointerId) } catch { /* a mouse in a test has no capture */ }
    held.value = true
    opts.live(levelFrom(e, el, vertical()))
  }
  function move(e: PointerEvent) { if (held.value) opts.live(levelFrom(e, e.currentTarget as HTMLElement, vertical())) }
  function up(e: PointerEvent) {
    if (!held.value) return
    held.value = false
    opts.settle(levelFrom(e, e.currentTarget as HTMLElement, vertical()))
  }
  function cancel() { held.value = false }
  /* A wall panel is touched, but the same control has to be reachable from a keyboard: the arrows
     step it, and only the key-up tells the house, exactly as a finger does. */
  function key(e: KeyboardEvent, now: number) {
    const d = e.key === 'ArrowUp' || e.key === 'ArrowRight' ? step : e.key === 'ArrowDown' || e.key === 'ArrowLeft' ? -step
      : e.key === 'Home' ? -100 : e.key === 'End' ? 100 : 0
    if (!d) return
    e.preventDefault()
    opts.settle(Math.min(100, Math.max(0, now + d)))
  }
  return { held, down, move, up, cancel, key }
}

/* A wall panel drags a column; a phone drags a bar. The axis has to be a fact the component knows,
   not only something CSS turns on its side, or the finger and the fill disagree. */
export function useNarrow(query = '(max-width: 860px)') {
  const narrow = ref(typeof matchMedia === 'function' ? matchMedia(query).matches : false)
  if (typeof matchMedia === 'function') {
    const mq = matchMedia(query)
    const on = () => (narrow.value = mq.matches)
    mq.addEventListener?.('change', on)
  }
  return narrow
}
