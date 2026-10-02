// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* What a failure says, pinned to the sheet the household chose on 2 October (design/words-band/, A):
   a reason the hub wrote for a person reaches the person; anything else -- a developer's guard, the
   server's status line, the browser's own words -- becomes one plain sentence, and a toast that names
   what failed says so once, not twice. Cancelling the passcode question is never a failure. */
import { describe, expect, it } from 'vitest'
import { failed, plainError, TRY_AGAIN, CANCELED } from '../src/code'
import { notify, store } from '../src/store'

describe('what a failure says', () => {
  it('keeps a sentence the hub wrote for a person', () => {
    expect(plainError('Monitor light is not answering, so there would be nothing to see.').message)
      .toBe('Monitor light is not answering, so there would be nothing to see.')
  })
  it('turns anything else into one plain sentence', () => {
    for (const raw of ['unknown room', 'Internal Server Error', 'could not rename it: Timeout', '', undefined, [{ loc: ['body'] }]])
      expect(plainError(raw).message).toBe(TRY_AGAIN)
  })
  it('names what failed once, with the reason when there is one', () => {
    expect(failed('Couldn’t rename it', plainError('unknown device'))).toBe('Couldn’t rename it. Try again in a moment.')
    expect(failed('Couldn’t rename it', plainError('Sam’s lamp is not answering.'))).toBe('Couldn’t rename it. Sam’s lamp is not answering.')
  })
  it('never toasts a cancelled passcode question as a failure', () => {
    store.toast = null
    notify(CANCELED, 'error')
    expect(store.toast).toBeNull()
  })
})
