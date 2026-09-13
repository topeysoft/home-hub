/* How Home is arranged. The house keeps one answer; a screen running an older panel must not be
   able to put the house into an arrangement it has never heard of. */
import { describe, expect, it } from 'vitest'
import { FACES, isFace, isLayout, LAYOUTS } from '../src/layout'

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

/* A face decides what the panel is made of. Same contract as an arrangement: a screen running an
   older panel must not be able to put the house into a material it has never heard of. */
describe('what a house can be made of', () => {
  it('accepts the ones that exist and refuses everything else', () => {
    for (const f of FACES) expect(isFace(f.id)).toBe(true)
    for (const bad of ['frosted', '', null, undefined, 0, {}, 'GLASS']) expect(isFace(bad)).toBe(false)
  })

  it('gives every face a name and a line saying who it is for', () => {
    for (const f of FACES) {
      expect(f.label.trim()).toBeTruthy()
      expect(f.hint.trim()).toBeTruthy()
      expect(isFace(f.id)).toBe(true)
    }
  })

  it('has no two faces under the same id', () => {
    expect(new Set(FACES.map(f => f.id)).size).toBe(FACES.length)
  })

  it('starts on the face the house already had', () => {
    expect(FACES[0].id).toBe('paper')
  })
})
