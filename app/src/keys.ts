// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The wall's own keyboard, as rules rather than drawing (design/keyboard/, C). The wall unit is cage and Chromium on
   Linux, which has no on-screen keyboard, so the panel brings one -- only there; phones and tablets keep their own.
   Its shape follows the field: digits get a keypad, the command box gets letters with the house's completions
   above them, anything else gets letters. Keys.vue draws it; these are the parts a test can hold. */

export type Shape = 'pad' | 'letters' | 'command'

// The wall says so when it opens the panel (startup/wall.sh), and nothing else does.
export const onWall = (search = location.search) => new URLSearchParams(search).get('wall') === '1'

const TEXT = new Set(['text', 'search', 'password', 'email', 'url', 'tel', 'number', ''])
export function typable(el: Element | null): el is HTMLInputElement | HTMLTextAreaElement {
  if (el instanceof HTMLTextAreaElement) return !el.disabled && !el.readOnly
  return el instanceof HTMLInputElement && TEXT.has(el.type) && !el.disabled && !el.readOnly
}

export function shapeOf(el: HTMLInputElement | HTMLTextAreaElement): Shape {
  if (el.dataset.keys === 'command') return 'command'
  const mode = el.getAttribute('inputmode')
  if (mode === 'numeric' || mode === 'decimal' || (el instanceof HTMLInputElement && (el.type === 'number' || el.type === 'tel'))) return 'pad'
  return 'letters'
}

// The return key says what it will do, from the field's own enterkeyhint.
export function goLabel(el: HTMLInputElement | HTMLTextAreaElement): string {
  return { go: 'Go', send: 'Go', search: 'Search', next: 'Continue', previous: 'Back', done: 'Done', enter: 'Return' }[el.getAttribute('enterkeyhint') ?? ''] ?? 'Done'
}

// Whether the next letter starts a word that the field wants capitalized.
export function wantsCapital(el: HTMLInputElement | HTMLTextAreaElement): boolean {
  const cap = el.getAttribute('autocapitalize')
  if (cap !== 'words' && cap !== 'sentences') return false
  const before = el.value.slice(0, el.selectionStart ?? el.value.length)
  return cap === 'words' ? before === '' || /\s$/.test(before) : before.trim() === '' || /[.!?]\s+$/.test(before)
}

// Typing into a field the way a keyboard does: at the caret, over any selection, then telling Vue it changed.
export function type(el: HTMLInputElement | HTMLTextAreaElement, text: string) {
  const max = el.maxLength > 0 ? el.maxLength : Infinity
  try {
    const start = el.selectionStart ?? el.value.length, end = el.selectionEnd ?? start
    if (el.value.length - (end - start) + text.length > max) return
    el.setRangeText(text, start, end, 'end')
  } catch {
    if (el.value.length + text.length > max) return
    el.value += text      // a number field has no selection to type into
  }
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

export function erase(el: HTMLInputElement | HTMLTextAreaElement) {
  try {
    const start = el.selectionStart ?? el.value.length, end = el.selectionEnd ?? start
    if (start === end && start === 0) return
    el.setRangeText('', start === end ? start - 1 : start, end, 'end')
  } catch {
    el.value = el.value.slice(0, -1)
  }
  el.dispatchEvent(new Event('input', { bubbles: true }))
}

// Return: the field's own Enter handler first, then its form if it is in one.
export function enter(el: HTMLInputElement | HTMLTextAreaElement) {
  const ev = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true })
  el.dispatchEvent(ev)
  if (!ev.defaultPrevented && el.form) el.form.requestSubmit()
}

// How far the page has to move up for the field -- or what answers it, marked data-keys-keep -- to stay above the keyboard.
export function lift(keepBottom: number, viewport: number, keyboard: number, margin = 24): number {
  return Math.max(0, Math.round(keepBottom + margin - (viewport - keyboard)))
}

export const LETTERS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
export const SYMBOLS = ['1234567890', '-/:;()$&@"', ".,?!'"]
