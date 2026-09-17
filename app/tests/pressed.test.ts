/* Naming eleven identical switches by pressing them.

   The rule is small and the ways it can go wrong are not: lighting a row nobody touched sends a
   person down a corridor to name the wrong light, and that is worse than lighting nothing. These
   hold it to that. */
import { describe, expect, it } from 'vitest'
import { pressedIn, snapshot, type Pressable } from '../src/pressed'

const list = (...states: string[]): Pressable[] => states.map((state, i) => ({ id: `s${i}`, state }))

describe('which one was pressed', () => {
  it('names the one that moved', () => {
    const was = snapshot(list('off', 'off', 'off'))
    expect(pressedIn(was, list('off', 'on', 'off'))).toBe('s1')
  })

  it('says nothing when nothing moved', () => {
    const was = snapshot(list('off', 'on'))
    expect(pressedIn(was, list('off', 'on'))).toBe(null)
  })

  /* a scene, a routine, the power coming back: there is no honest answer, so there is no answer */
  it('says nothing when two move at once', () => {
    const was = snapshot(list('off', 'off', 'off'))
    expect(pressedIn(was, list('on', 'on', 'off'))).toBe(null)
  })

  /* a switch that has only just been discovered has not been touched: it has arrived */
  it('ignores something that was not there before', () => {
    const was = snapshot([{ id: 'a', state: 'off' }])
    expect(pressedIn(was, [{ id: 'a', state: 'off' }, { id: 'b', state: 'on' }])).toBe(null)
  })

  /* a row this screen is mid-change on is this screen's doing, not a person's */
  it('ignores a row the screen is busy with', () => {
    const was = snapshot(list('off', 'off'))
    expect(pressedIn(was, list('off', 'on'), id => id === 's1')).toBe(null)
  })

  /* the first look has no snapshot to compare against, and must not light the whole list */
  it('lights nothing on the first look', () => {
    expect(pressedIn({}, list('on', 'off', 'on'))).toBe(null)
  })

  /* pressing the same switch again is a second press, not the same one: off, then on again */
  it('follows a switch that is pressed twice', () => {
    let was = snapshot(list('off'))
    const on = list('on')
    expect(pressedIn(was, on)).toBe('s0')
    was = snapshot(on)
    expect(pressedIn(was, list('off'))).toBe('s0')
  })
})
