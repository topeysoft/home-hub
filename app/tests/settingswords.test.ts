// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The settings' words, pinned to the sheet the household chose on 2 October (design/words-settings/,
   Chosen): one name for each thing. The box is The hub on its row and on its page; the passcode is
   Passcode on both; restarting says how deep, never which part; and the words that had two meanings
   on these pages -- the little computer, the door that opens for five minutes, the bridge that
   carries what is shared -- stay gone. These fail on purpose if a second name grows back. */
import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const src = (p: string) => readFileSync(p, 'utf8')
const panel = src('src/HousePanel.vue')

describe('one name each', () => {
  it('calls the box The hub on its row and its page', () => {
    expect(panel).toContain("hub: 'The hub'")
    expect(panel).toMatch(/id: 'hub' as const[^}]*name: 'The hub'/)
  })
  it('calls the passcode Passcode on its row and its page, and never a lock or a code', () => {
    expect(panel).toContain("code: 'Passcode'")
    expect(panel).toMatch(/id: 'code' as const[^}]*name: 'Passcode'/)
    for (const f of ['src/HousePanel.vue', 'src/CodePage.vue']) expect(src(f)).not.toMatch(/Lock the settings|'Lock'/)
    expect(src('../brain/hub/api.py')).not.toMatch(/HTTPException\([^)]*\bno code\b|Set a code first/)
  })
})

describe('restarting', () => {
  it('names how deep each restart goes, never which part restarts', () => {
    const restart = src('../brain/hub/restart.py')
    expect(restart).toContain('DO = {"hub": "Quick restart", "everything": "Full restart", "machine": "Power off and on"}')
    for (const f of ['src/HubPage.vue', '../brain/hub/restart.py']) expect(src(f)).not.toMatch(/little computer|Restart everything/)
  })
})

describe('words with two meanings on these pages', () => {
  it('opens no door and fills no bridge on Share', () => {
    const share = src('src/SharePage.vue').replace(/<!--[\s\S]*?-->|\/\*[\s\S]*?\*\//g, '')   // comments keep their idiom
    expect(share).not.toMatch(/door is open|door shuts|bridge can carry|held by/)
  })
  it('lists the connections under Connections, by their standard names', () => {
    expect(src('src/HubPage.vue')).not.toContain('Behind the scenes')
    expect(src('../brain/hub/provision.py')).toContain('"Device messages"')
  })
})
