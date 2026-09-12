/*
 * How Home is arranged. A house picks one; adding another means adding an entry
 * here and a component for it, not editing the ones that already work.
 *
 * The arrangement is the only thing a layout decides. What Home must always
 * carry, in any layout, is fixed and not negotiable per-layout:
 *
 *   - the command box, so the house can be told things
 *   - anything asking to be let in, which is the only way a new phone joins
 *   - the nudges, which is where an update, a found device or an unlocked
 *     settings code gets offered
 *   - "Needs a look", which carries the only Sign in again a person has
 *
 * A layout that drops one of those strands somebody: no way to approve a phone
 * except from a phone already paired, or no way to re-authenticate an expired
 * account without opening Home Assistant. Arrange them differently by all means.
 */

export type LayoutName = 'stack' | 'rail' | 'wall'

export const LAYOUTS: { id: LayoutName; label: string; hint: string }[] = [
  { id: 'stack', label: 'Stack', hint: 'Everything in a column, newest first. Reads well on a phone.' },
  { id: 'rail', label: 'Rail', hint: 'What is on now in one row you sweep through. Made for a wall.' },
  { id: 'wall', label: 'Wall', hint: 'The weather large on the left, and what is on beside it. Made to be read from across a room.' },
]

export function isLayout(v: unknown): v is LayoutName {
  return v === 'stack' || v === 'rail' || v === 'wall'
}

/*
 * Where the way around the house lives. Side is the list down the left the
 * panel has always had: every room in view, its activity under its name. Top
 * is tabs across the top and, along the bottom, the command box and the household, which gives the
 * whole width to what is on. Both reach every room; they differ in what is
 * always in view and what is a tap away.
 */
export type NavName = 'side' | 'top'

export const NAVS: { id: NavName; label: string; hint: string }[] = [
  { id: 'side', label: 'Side', hint: 'Every room listed down the left, always in view.' },
  { id: 'top', label: 'Top', hint: 'Tabs across the top, the command box and the household along the bottom. Room for what is on.' },
]

export function isNav(v: unknown): v is NavName {
  return v === 'side' || v === 'top'
}

/*
 * What the panel is MADE OF, as opposed to what is on it or how it is arranged.
 * Paper is what the house has always been: cards with a tone, laid on the sky.
 * Glass is the same house behind frosted panes -- see design/nightfall.
 *
 * A face decides material and motion and nothing else. It does not get to move
 * a card, rename a room or hide a strand: the things Home must always carry are
 * listed at the top of this file and they are not negotiable per-face either.
 * Nor does a face get an absolute palette. Like a tone, it is specified as a
 * distance from the sky, so it holds at every hour -- tone.ts says why.
 */
export type FaceName = 'paper' | 'glass'

export const FACES: { id: FaceName; label: string; hint: string }[] = [
  { id: 'paper', label: 'Paper', hint: 'Cards with a tone, laid flat on the sky. What the house has always looked like.' },
  { id: 'glass', label: 'Glass', hint: 'The same house behind frosted panes, with the sky moving through them. Wants a screen that can blur.' },
]

export function isFace(v: unknown): v is FaceName {
  return v === 'paper' || v === 'glass'
}
