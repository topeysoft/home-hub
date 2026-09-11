/* How Home is arranged. The house keeps one answer; a screen running an older panel must not be
   able to put the house into an arrangement it has never heard of. */
import { describe, expect, it } from 'vitest'
import { isLayout, LAYOUTS } from '../src/layout'

describe('the arrangements a house can pick', () => {
  it('accepts the ones that exist and refuses everything else', () => {
    for (const l of LAYOUTS) expect(isLayout(l.id)).toBe(true)
    for (const bad of ['grid', '', null, undefined, 0, {}, 'STACK']) expect(isLayout(bad)).toBe(false)
  })

  it('gives every arrangement a name and a line saying who it is for', () => {
    for (const l of LAYOUTS) {
      expect(l.label.trim()).toBeTruthy()
      expect(l.hint.trim()).toBeTruthy()
      expect(isLayout(l.id)).toBe(true)
    }
  })

  it('has no two arrangements under the same id', () => {
    expect(new Set(LAYOUTS.map(l => l.id)).size).toBe(LAYOUTS.length)
  })
})
