/*
 * Which of these was just pressed.
 *
 * Eleven rows called "Brilliant switch 000a" is the thing this exists to stop. A switch on a wall
 * announces itself the moment a human touches it -- that is how the house reads its state at all --
 * so the way to tell identical rows apart is to go and press one and have the row say so.
 *
 * The press is not read out of the event log. What a person did IS the device changing state, and
 * that already arrives on the stream; reading it twice would mean two sources that can disagree
 * about which row to light. So this compares the list against the list a moment ago, and that is
 * the whole mechanism.
 *
 * Nothing else on the New devices screen changes a state: renaming and moving do not, and a device
 * that is placed leaves the list rather than changing. `busy` covers the one remaining case -- a
 * row this screen is mid-change on -- so an answer here really did come off a wall.
 *
 * design/puck/Naming.dc.html argues why this is the screen; SortView.vue draws it.
 */

/** What the list looked like: id -> state. */
export type Seen = Record<string, string>

export type Pressable = { id: string; state: string }

export const snapshot = (devices: Pressable[]): Seen =>
  Object.fromEntries(devices.map(d => [d.id, d.state]))

/**
 * The one that moved, or null. Only things present in BOTH the snapshot and the list count: a
 * device that has only just appeared has not changed, it has arrived, and lighting it would send
 * somebody to look at a switch nobody touched.
 *
 * Two moving at once is a real case -- a scene, a routine, a power cut coming back -- and there is
 * no honest answer to "which one did you press", so it answers none. Saying nothing is recoverable
 * (press it again); pointing at the wrong switch sends someone to name the wrong light.
 */
export function pressedIn(was: Seen, devices: Pressable[], busy: (id: string) => boolean = () => false): string | null {
  const moved = devices.filter(d => was[d.id] !== undefined && was[d.id] !== d.state && !busy(d.id))
  return moved.length === 1 ? moved[0].id : null
}
