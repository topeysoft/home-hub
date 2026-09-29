// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

/* WHAT DRAWS OVER WHAT. A sheet is something somebody asked for or something that asked for the
 * screen, and it opens from inside a pane or from This house -- so when it drew at a lower layer than
 * the page that opened it, it appeared underneath, and the tap that opened it looked like it did
 * nothing. That happened three times, fixed once each, before the ladder was written down in
 * panel.css. This reads the numbers back out of the sheet, so the order is the thing pinned rather
 * than any one value. */
const css = readFileSync('src/panel.css', 'utf8')

function layer(selector: string): number {
  const at = css.search(new RegExp(`^${selector.replace(/\./g, '\\.')} \\{`, 'm'))
  expect(at, `${selector} is in panel.css`).toBeGreaterThanOrEqual(0)
  const block = css.slice(at, css.indexOf('}', at))
  const z = block.match(/z-index:\s*(-?\d+)/)
  expect(z, `${selector} says its layer`).not.toBeNull()
  return Number(z![1])
}

describe('the layers', () => {
  it('puts a sheet over every pane that can open one', () => {
    for (const pane of ['.viewer', '.opened', '.house'])
      expect(layer('.sheet-back'), `a sheet over ${pane}`).toBeGreaterThan(layer(pane))
  })

  it('keeps a toast readable over the sheet that caused it', () => {
    expect(layer('.toast')).toBeGreaterThan(layer('.sheet-back'))
  })

  it('lets the rest screen cover everything but the code prompt', () => {
    expect(layer('.idle')).toBeGreaterThan(layer('.toast'))
    expect(layer('.code-back')).toBeGreaterThan(layer('.idle'))
  })
})
