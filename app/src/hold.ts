/*
 * Press and hold a card to open it.
 *
 * A tap on a tile already means something — a light goes on, a film pauses — so
 * opening cannot also be a tap. Holding is the way out that keeps the one-tap
 * control everyone already has: the same gesture a phone uses for the same
 * thing, on a panel where the fastest action must stay the shortest one.
 *
 * Held long enough, the card opens and the tap is swallowed, so a light never
 * toggles on the way into its own detail. Move a finger and it is a scroll
 * instead, never an open — the rail scrolls sideways under exactly this gesture.
 */
import type { Directive } from 'vue'

const HOLD = 420          // long enough not to fire while tapping, short enough not to feel stuck
const SLOP = 10           // past this the finger is scrolling, not holding

type State = { t?: number; x: number; y: number; fired: boolean }
const state = new WeakMap<HTMLElement, State>()

export const vHold: Directive<HTMLElement, (() => void) | undefined> = {
  /* created, not mounted: at the target element listeners run in the order they
     were registered, and `created` is the one hook that runs before Vue attaches
     the tile's own. That ordering is the whole trick — a light tile toggles on
     pointerup, so the release that ends a hold has to be stopped before the
     tile ever sees it, or opening a lamp would also switch it off. */
  created(el, binding) {
    const open = () => binding.value?.()
    const s: State = { x: 0, y: 0, fired: false }
    state.set(el, s)

    const cancel = () => { clearTimeout(s.t); s.t = undefined }
    const down = (e: PointerEvent) => {
      if (e.button !== undefined && e.button !== 0) return
      s.x = e.clientX; s.y = e.clientY; s.fired = false
      cancel()
      /* capture the pointer for the duration: a finger that drifts a pixel or two
         off the card's edge, or a trackpad that wanders, must not read as leaving */
      try { el.setPointerCapture(e.pointerId) } catch {}
      s.t = window.setTimeout(() => {
        s.fired = true
        el.setAttribute('data-held', '')                       // the card acknowledges the hold before it opens
        navigator.vibrate?.(8)
        open()
        setTimeout(() => el.removeAttribute('data-held'), 220)
      }, HOLD)
    }
    const move = (e: PointerEvent) => {
      if (s.t && (Math.abs(e.clientX - s.x) > SLOP || Math.abs(e.clientY - s.y) > SLOP)) cancel()
    }
    /* the release and the click that end a fired hold are both swallowed, so the
       tile's own handler never runs: no light toggles on its way into its detail */
    const up = (e: PointerEvent) => {
      cancel()
      if (s.fired) { e.stopImmediatePropagation(); e.preventDefault() }
    }
    const click = (e: MouseEvent) => {
      if (s.fired) { e.stopImmediatePropagation(); e.preventDefault(); s.fired = false }
    }
    /* on a touch screen a long press is also the browser's own gesture — a
       context menu on Android, a callout on iOS — and that arrives right when
       the hold does. It is ours here, not the browser's. */
    const menu = (e: Event) => { if (s.t || s.fired) e.preventDefault() }

    el.addEventListener('pointerdown', down)
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointercancel', cancel)
    el.addEventListener('pointerleave', cancel)
    el.addEventListener('click', click)
    el.addEventListener('contextmenu', menu)
    ;(el as any).__hold = { down, move, up, cancel, click, menu }
  },
  unmounted(el) {
    const h = (el as any).__hold
    if (!h) return
    clearTimeout(state.get(el)?.t)
    el.removeEventListener('pointerdown', h.down)
    el.removeEventListener('pointermove', h.move)
    el.removeEventListener('pointerup', h.up)
    el.removeEventListener('pointercancel', h.cancel)
    el.removeEventListener('pointerleave', h.cancel)
    el.removeEventListener('click', h.click)
    el.removeEventListener('contextmenu', h.menu)
  },
}
