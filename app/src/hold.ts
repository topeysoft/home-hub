// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
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

/*
 * Swallowing the click that ends a hold -- wherever it lands, which is the part the card cannot do
 * for itself.
 *
 * A hold opens a panel UNDER the finger that is still down. The browser then sends the click to
 * whatever is beneath the point WHEN THE FINGER LIFTS, and by then that is the panel, not the card:
 * the card's own click handler is never offered it and has nothing to stop. On an iPad-shaped wall
 * panel the light pane's three presets land almost exactly where the finger was holding, so letting
 * go of a lamp at 35% to open it also set it to 100% -- one press, doing two things, one of which
 * nobody asked for.
 *
 * `pointerup` on the card is still swallowed below, and still has to be: that is the tile's own
 * dimmer. This is the other half, and it sits on the document because the element it has to defend
 * is one nothing here has a reference to.
 *
 * WHAT IT MUST NOT EAT is the next real tap, and a plain timer is not good enough at telling the
 * two apart. A person holds a lamp open in order to touch something in it, and they are quick about
 * it -- `pane.spec.ts` taps a preset within a few hundred milliseconds of the release, which is the
 * ordinary speed, not a fast one. Any window wide enough to be sure of catching the stray click is
 * also wide enough to eat that tap, which would be this same bug pointed the other way.
 *
 * So the rule is about the press, not the clock: the click that belongs to a press cannot arrive
 * after the NEXT press has begun. Arm on the release, drop it on the next pointerdown anywhere,
 * eat at most one, and keep a long timer only so nothing is ever left armed for good.
 */
const NEVER_ARMED_PAST = 1200   // a backstop, not the rule: the pointerdown below is the rule
let releasing: (() => void) | null = null

function swallowClickFrom(release: PointerEvent) {
  releasing?.()   // an earlier hold whose click never came; this release is the live one now
  const eat = (e: MouseEvent) => {
    /* Only the click this release produced. A click that is somehow somewhere else entirely is
       somebody else's, and eating it would be the bug this is here to fix, pointed the other way. */
    if (Math.abs(e.clientX - release.clientX) > 24 || Math.abs(e.clientY - release.clientY) > 24) return
    e.stopImmediatePropagation(); e.preventDefault(); stop()
  }
  const next = () => stop()                       // a new press: whatever was coming is no longer ours
  const timer = window.setTimeout(() => stop(), NEVER_ARMED_PAST)
  function stop() {
    clearTimeout(timer)
    document.removeEventListener('click', eat, true)
    document.removeEventListener('pointerdown', next, true)
    if (releasing === stop) releasing = null
  }
  document.addEventListener('click', eat, true)
  document.addEventListener('pointerdown', next, true)
  releasing = stop
}

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
      /* A control inside the card is the control, and the card stays out of its way.
         Not politeness — the capture below retargets everything that follows the press,
         the click included, at the card, so a thermostat's step buttons and a player's
         transport never heard their own tap. Nothing is lost: the rest of the card is
         still the way in, and holding a button to open the thing it belongs to was
         never the gesture anyone reached for. */
      const hit = (e.target as Element | null)?.closest?.('button, a, input, select, textarea, [role="button"], [role="slider"]')
      if (hit && hit !== el && el.contains(hit)) return
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
      if (s.fired) { e.stopImmediatePropagation(); e.preventDefault(); swallowClickFrom(e) }
    }
    /* Kept, though swallowNextClick above usually gets there first: this one still fires where the
       click lands on the card itself and nothing opened over it, and it is the only one that clears
       `fired` on the element. Cheap, and the two do not fight -- whichever runs first stops the other. */
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
