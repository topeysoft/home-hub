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

export type LayoutName = 'stack' | 'rail'

export const LAYOUTS: { id: LayoutName; label: string; hint: string }[] = [
  { id: 'stack', label: 'Stack', hint: 'Everything in a column, newest first. Reads well on a phone.' },
  { id: 'rail', label: 'Rail', hint: 'What is on now in one row you sweep through. Made for a wall.' },
]

export function isLayout(v: unknown): v is LayoutName {
  return v === 'stack' || v === 'rail'
}
