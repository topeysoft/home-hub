// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The picture chosen in design/boot/ (J) is the spec. These fail on purpose when the board, the
// sequence and the splash that ships stop agreeing: change the board first, then sequence.mjs,
// then `node startup/render.mjs`.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { NAME, HOUSE, TIME, BREATH } from './sequence.mjs'
import { THEME, NAME_FRAMES, fingerprint, themeFile, timingSh, script } from './plymouth.mjs'

const theme = (f) => new URL(`plymouth/${THEME}/${f}`, import.meta.url)
const read = (u) => readFileSync(u, 'utf8')
const board = read(new URL('../design/boot/boot.js', import.meta.url))

test('the splash was drawn from this sequence', () => {
  assert.equal(read(theme('fingerprint')).trim(), fingerprint(), 'sequence.mjs or render.mjs changed: run node startup/render.mjs')
})

test('the committed theme is what the sequence generates', () => {
  assert.equal(read(theme(`${THEME}.script`)), script())
  assert.equal(read(theme(`${THEME}.plymouth`)), themeFile())
  assert.equal(read(theme('timing.sh')), timingSh())
})

test('every image the script asks for is there', () => {
  const names = [...script().matchAll(/Image\("([^"]+)"\)/g)].map((m) => m[1]).filter((f) => !f.startsWith('name-'))
  for (let i = 0; i < NAME_FRAMES; i++) names.push(`name-${String(i).padStart(2, '0')}.png`)
  for (const f of names) assert.ok(existsSync(theme(f)), `missing ${f}`)
})

test('the board draws the same name, house and timing', () => {
  const pieces = board.match(/const ELYIR = ([\s\S]*?)\n\s*const ELYIR_AT/)[1]
  assert.equal([...pieces.matchAll(/'([^']*)'/g)].map((m) => m[1]).join(''), NAME.d)
  assert.match(board, /const ELYIR_AT = \{ write: ([\d.]+), hold: ([\d.]+) \}/)
  const [, write, hold] = board.match(/const ELYIR_AT = \{ write: ([\d.]+), hold: ([\d.]+) \}/)
  assert.equal(+write, TIME.write)
  assert.equal(+hold, TIME.hold)
  assert.equal(+board.match(/const LAMP_BREATH = ([\d.]+)/)[1], BREATH.period)
  assert.match(board, /const S = dir === 'C' \? 150 : 340/)
  assert.equal(HOUSE.size, 340)
  assert.match(board, /viewBox="10 10 530 380"/)
  assert.deepEqual(NAME.viewBox, [10, 10, 530, 380])
  assert.match(board, /\(364 - 10\) \* 1\.5, \(900 - 570\) \/ 2 \+ \(118 - 10\) \* 1\.5/, 'the dot of the i starts where the board puts it')
})

test('the moments come in order', () => {
  assert.ok(TIME.write < TIME.dotted && TIME.dotted < TIME.lit && TIME.lit + 0.8 < TIME.hold)
  assert.ok(TIME.hold < TIME.leave && TIME.leave < TIME.land)
  assert.ok(TIME.readyAfter >= TIME.land, 'the ending may not start before the dot has landed')
  assert.ok(TIME.hold + TIME.nameOut >= 3 && TIME.hold + TIME.nameOut <= 6, 'the name is on screen for a few seconds, as asked')
})
