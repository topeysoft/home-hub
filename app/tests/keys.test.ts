// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The wall's keyboard, C in design/keyboard/: the picture chosen is the spec. A passcode gets a keypad, the command
   box gets letters with the house's completions, anything else gets letters; the return key says what it does;
   typing lands at the caret and tells Vue; the page moves up just far enough. These fail if any of that drifts. */
import { describe, expect, it } from 'vitest'
import { enter, erase, goLabel, lift, onWall, shapeOf, type, typable, wantsCapital } from '../src/keys'

const input = (attrs: Record<string, string> = {}, value = '') => {
  const el = document.createElement('input')
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v)
  el.value = value
  document.body.append(el)
  return el
}

describe('only on the wall', () => {
  it('is mounted when the wall opens the panel saying so, and nowhere else', () => {
    expect(onWall('?wall=1')).toBe(true)
    expect(onWall('?wall=1&room=kitchen')).toBe(true)
    expect(onWall('')).toBe(false)
    expect(onWall('?setup=1')).toBe(false)
  })
})

describe('the shape follows the field', () => {
  it('gives a passcode a keypad', () => {
    expect(shapeOf(input({ inputmode: 'numeric' }))).toBe('pad')
    expect(shapeOf(input({ type: 'number' }))).toBe('pad')
  })
  it('gives the command box letters with its completions', () => {
    expect(shapeOf(input({ 'data-keys': 'command' }))).toBe('command')
  })
  it('gives everything else letters', () => {
    expect(shapeOf(input({ type: 'search' }))).toBe('letters')
    expect(shapeOf(input({ type: 'password' }))).toBe('letters')
    expect(shapeOf(input())).toBe('letters')
  })
  it('leaves checkboxes, sliders and files alone', () => {
    expect(typable(input({ type: 'checkbox' }))).toBe(false)
    expect(typable(input({ type: 'range' }))).toBe(false)
    expect(typable(input({ disabled: '' }))).toBe(false)
    expect(typable(input({ type: 'search' }))).toBe(true)
  })
})

describe('the return key says what it does', () => {
  it('reads the field’s own enterkeyhint', () => {
    expect(goLabel(input({ enterkeyhint: 'next' }))).toBe('Continue')
    expect(goLabel(input({ enterkeyhint: 'search' }))).toBe('Search')
    expect(goLabel(input({ enterkeyhint: 'send' }))).toBe('Go')
    expect(goLabel(input())).toBe('Done')
  })
})

describe('typing', () => {
  it('lands at the caret, over a selection, and tells Vue', () => {
    const el = input({}, 'kitchn'), seen: string[] = []
    el.addEventListener('input', () => seen.push(el.value))
    el.setSelectionRange(5, 5)
    type(el, 'e')
    expect(el.value).toBe('kitchen')
    el.setSelectionRange(0, 7)
    type(el, 'den')
    expect(el.value).toBe('den')
    expect(seen).toEqual(['kitchen', 'den'])
  })
  it('stops at the field’s own length', () => {
    const el = input({ maxlength: '4' }, '123')
    type(el, '4'); type(el, '5')
    expect(el.value).toBe('1234')
  })
  it('deletes the character before the caret, or the selection', () => {
    const el = input({}, 'lights')
    el.setSelectionRange(6, 6); erase(el)
    expect(el.value).toBe('light')
    el.setSelectionRange(0, 5); erase(el)
    expect(el.value).toBe('')
    erase(el)
    expect(el.value).toBe('')
  })
  it('capitalizes the start of a word only where the field asks for it', () => {
    expect(wantsCapital(input({ autocapitalize: 'words' }, ''))).toBe(true)
    const named = input({ autocapitalize: 'words' }, 'Living ')
    named.setSelectionRange(7, 7)
    expect(wantsCapital(named)).toBe(true)
    expect(wantsCapital(input({ autocapitalize: 'off' }, ''))).toBe(false)
  })
  it('sends Enter to the field, and submits its form when nothing took it', () => {
    const form = document.createElement('form'), el = document.createElement('input')
    let submitted = 0, keyed = 0
    form.append(el); document.body.append(form)
    form.addEventListener('submit', (e) => { e.preventDefault(); submitted++ })
    el.addEventListener('keydown', (e) => { if (e.key === 'Enter') keyed++ })
    enter(el)
    expect([keyed, submitted]).toEqual([1, 1])
  })
})

describe('the page moves up just far enough', () => {
  it('keeps what has to stay 24 px above the keyboard, and does not move when it already is', () => {
    expect(lift(611, 900, 318)).toBe(53)
    expect(lift(869, 900, 318)).toBe(311)
    expect(lift(400, 900, 318)).toBe(0)
  })
})
