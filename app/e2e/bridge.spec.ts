// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* A bridge that went in has to be acknowledged, or it never goes away.
 *
 * What made this a spec: a puck was set up successfully, "It's in." was read and Done was pressed,
 * and the sheet came back a minute later. Then again. Then again. Closing it only changed the
 * panel's own copy of the state; the brain still had the finished job and answered every poll with
 * it, so the sheet reopened for ever and Done did nothing the hub could hear.
 *
 * The same bug had already been found and fixed for a job that FAILED, and the fix was written as
 * `if (was === 'failed')` -- so success kept it. This asserts the thing that was actually wrong: the
 * dismissal reaches the brain, and the state it then reports is one that draws nothing.
 *
 * Routed rather than driven through the mock's own bridge state, because the suite runs fully
 * parallel against one mock: pinning a bridge globally would drop a full-screen sheet over whatever
 * the other specs were clicking on.
 */
import { expect, test } from '@playwright/test'

const IN = /It.s in\./

test('a finished bridge is acknowledged, so it does not come back', async ({ page }) => {
  let told = 0
  let state: 'ready' | 'none' = 'ready'
  const body = () => state === 'ready'
    ? { state: 'ready', how: 'cable', switches: 5, unplaced: 3, bridges: 1, waiting: 0 }
    : { state: 'none', bridges: 1, waiting: 0 }

  // Registered first, so the more specific route below is matched before it.
  await page.route('**/bridge', route => route.fulfill({ json: body() }))
  await page.route('**/bridge/dismiss', route => {
    told++
    state = 'none'          // the brain, behaving like the brain: told once, it stops saying it
    return route.fulfill({ json: body() })
  })

  await page.goto('/?at=13:00', { waitUntil: 'networkidle' })
  const sheet = page.getByRole('dialog', { name: IN })
  await expect(sheet).toBeVisible()

  await page.getByRole('button', { name: 'Done' }).click()
  await expect(sheet).toBeHidden()
  expect(told, 'pressing Done has to reach the brain, or the next poll brings the sheet back').toBe(1)

  // The proof, and the thing a person actually experienced: come back to the panel and it is gone.
  await page.goto('/?at=13:00', { waitUntil: 'networkidle' })
  await expect(page.getByRole('dialog', { name: IN })).toBeHidden()
})

/* The one question, and the fact that the answer travels with the placing rather than after it.
 *
 * docs/puck-light.md: "Leave it here" no longer finishes the job -- it asks whether to leave the
 * light on, because that is the one moment somebody is standing in front of the thing in the place
 * it is going to live, and the answer goes in the same message. The three things worth holding are
 * that the question is asked at all, that BOTH answers place the bridge, and that walking away from
 * it places nothing -- the sheet's local step must never quietly decide on the household's behalf.
 */
const ASKED = /Leave its light on\?/

/* The stub has to behave like the brain on this one: a bridge that has been placed stops being one
   that is being placed. A route that answers `placing` for ever puts the sheet back on the walk a
   poll after the question is answered -- which is the stub lying, not the panel misbehaving. */
async function toTheQuestion(page: any, sent: any[]) {
  let state: 'placing' | 'ready' = 'placing'
  const body = () => state === 'placing'
    ? { state: 'placing', how: 'cable', switches: 11, signal: 'strong', bridges: 1, waiting: 0 }
    : { state: 'ready', how: 'cable', switches: 11, unplaced: 0, bridges: 1, waiting: 0 }

  await page.route('**/bridge', (route: any) => route.fulfill({ json: body() }))
  await page.route('**/bridge/placed', (route: any) => {
    sent.push(route.request().postData())
    state = 'ready'
    return route.fulfill({ json: body() })
  })
  await page.goto('/?at=13:00', { waitUntil: 'networkidle' })
  await page.getByRole('button', { name: 'Leave it here' }).click()
  await expect(page.getByRole('dialog', { name: ASKED })).toBeVisible()
}

test('leaving it here asks about the light, and yes goes with the placing', async ({ page }) => {
  const sent: any[] = []
  await toTheQuestion(page, sent)
  expect(sent, 'the brain must not be told until the question is answered').toHaveLength(0)

  await page.getByRole('button', { name: 'Leave it on' }).click()
  await expect(page.getByRole('dialog', { name: IN })).toBeVisible()
  expect(sent).toEqual(['{"night":true}'])
})

test('no is an answer, not a way out: it still places the bridge', async ({ page }) => {
  const sent: any[] = []
  await toTheQuestion(page, sent)
  await page.getByRole('button', { name: 'No, dark' }).click()
  await expect(page.getByRole('dialog', { name: IN })).toBeVisible()
  expect(sent).toEqual(['{"night":false}'])
})

test('walking away from the question places nothing at all', async ({ page }) => {
  const sent: any[] = []
  await toTheQuestion(page, sent)
  await page.getByRole('dialog', { name: ASKED }).getByRole('button', { name: /close/i }).click()
  expect(sent, 'a question nobody answered is not a bridge nobody placed').toHaveLength(0)

  // ...and it is still to be placed when the sheet comes back, at the step it was on.
  await page.goto('/?at=13:00', { waitUntil: 'networkidle' })
  await expect(page.getByRole('button', { name: 'Leave it here' })).toBeVisible()
})

/* This hub, and the thing that had no home before it.
 *
 * A puck used to appear on the panel only when something was WRONG with it, so the only place a
 * household could act on one was a problem report -- which is why hub/nightlight.py's "brighten as
 * you pass" was reachable nowhere but Home Assistant. These hold the two halves of the fix: every
 * bridge is listed whether or not anything is wrong, and what it sends when a switch is flipped.
 */
const ROWS = [
  { chip: 'c8ebba', room: 'hall', where: 'Hallway', online: true, signal: 'strong', switches: 11,
    fw: '0.5.0', behind: false, shipped: '0.5.0', night: true, level: 110, lift: false },
  { chip: '9a01cc', room: null, where: 'A bridge', online: false, signal: 'none', switches: 0,
    fw: null, behind: false, shipped: '0.5.0', night: null, level: null, lift: false },
  // On the broker, no proxy link, software too old to have a light. A real hub produced this and the
  // card called it "Strong, and hears 0 switches" -- a claim about a link it had never seen.
  { chip: 'd21e04', room: 'kitchen', where: 'Kitchen', online: true, signal: 'none', switches: 0,
    fw: '0.3.1', behind: false, shipped: null, night: null, level: null, lift: false },
]

async function toTheHub(page: any, sent: any[]) {
  await page.route('**/bridge/list', (route: any) => route.fulfill({ json: { bridges: ROWS } }))
  await page.route('**/bridge/light', (route: any) => {
    sent.push(JSON.parse(route.request().postData() || '{}'))
    return route.fulfill({ json: { bridges: ROWS } })
  })
  await page.goto('/?at=13:00&sheet=hub', { waitUntil: 'networkidle' })
}

test('this hub lists every bridge, not only the ones something is wrong with', async ({ page }) => {
  await toTheHub(page, [])
  await expect(page.getByRole('button', { name: /Hallway/ })).toBeVisible()
  // ...including one it cannot place, named honestly rather than by a chip id nobody can read.
  await expect(page.getByRole('button', { name: /A bridge/ })).toBeVisible()
})

test('opening one gives the nightlight a place to be turned on', async ({ page }) => {
  const sent: any[] = []
  await toTheHub(page, sent)
  await page.getByRole('button', { name: /Hallway/ }).click()

  const card = page.getByRole('dialog', { name: 'Hallway bridge' })
  await expect(card).toBeVisible()
  await card.getByRole('switch', { name: 'Brighten as you pass' }).click()
  expect(sent).toEqual([{ chip: 'c8ebba', lift: true }])
})

test('a bridge that has never spoken is not drawn with its light off', async ({ page }) => {
  const sent: any[] = []
  await toTheHub(page, sent)
  await page.getByRole('button', { name: /A bridge/ }).click()

  const card = page.getByRole('dialog', { name: 'A bridge bridge' })
  await expect(card.getByText('Nothing said about a light yet.')).toBeVisible()
  await expect(card.getByRole('switch', { name: 'Nightlight' })).toBeHidden()
  expect(sent, 'nothing can be changed about a puck the hub has not heard').toHaveLength(0)
})

test('a bridge with no link yet is not called strong', async ({ page }) => {
  await toTheHub(page, [])
  await page.getByRole('button', { name: /Kitchen/ }).click()

  const card = page.getByRole('dialog', { name: 'Kitchen bridge' })
  await expect(card).toBeVisible()
  await expect(card.getByText(/Strong/)).toBeHidden()
  await expect(card.getByText(/hears 0 switches/)).toBeHidden()
  await expect(card.getByText(/has not heard a switch yet/)).toBeVisible()
})

test('a hub that cannot say what it ships does not call a puck current', async ({ page }) => {
  await toTheHub(page, [])
  await page.getByRole('button', { name: /Kitchen/ }).click()
  const card = page.getByRole('dialog', { name: 'Kitchen bridge' })
  await expect(card.getByText(/current/)).toBeHidden()
  await expect(card.getByText(/can.t say whether that is the latest/)).toBeVisible()
})
