/* The house's own power, for the mock brain (brain/hub/power.py, design/energy/).

   A house with a Tesla gateway is a different house -- a line in the band, the sun warmer in the drawing -- and
   every other board and test was drawn at the house without one. So it is there only when the PAGE asks:
   `?power=` on the panel's own address, read off each request's Referer, or POWER=<scenario> for the whole mock.

     ?power=1 | afternoon   the boards' afternoon: 5.8 kW from the roof, the battery at 84% and charging
     ?power=spare           the battery full and 3.7 kW going to the grid: Sun to spare
     ?power=out             the grid down half an hour ago, the battery carrying the house
     ?power=low             still out, and the battery at 18%
     ?power=back            the grid back two minutes ago, after 2 hours 10 minutes
     ?power=night           the sun down and the battery carrying the house, which says nothing

   ?at=14:47 sets the clock the day's curve ends at, as the boards do. */

function asked(req) {
  let q = new URLSearchParams()
  try { q = new URL(req.headers.referer || '').searchParams } catch { /* no page behind it */ }
  const scenario = q.get('power') ?? process.env.POWER ?? null
  const now = new Date(), at = q.get('at')
  if (at) { const [h, m] = at.split(':').map(Number); now.setHours(h || 0, m || 0, 0, 0) }
  return { scenario: scenario === '1' ? 'afternoon' : scenario, now: now.getTime() / 1000 }
}

const BASE = { reserve: 20, has_battery: true, spare: false, out_since: null, back: null, grid_up: true }
function power(scenario, now) {
  switch (scenario) {
    case 'afternoon': return { ...BASE, solar: 5.8, house: 1.2, battery: 2.4, grid: -2.2, charge: 84, left: 24.1 }
    case 'spare': return { ...BASE, solar: 5.1, house: 1.4, battery: 0, grid: -3.7, charge: 100, left: 27, spare: true }
    case 'out': return { ...BASE, solar: 0, house: 1.7, battery: -1.7, grid: 0, charge: 84, left: 24.1, grid_up: false, out_since: now - 1800 }
    case 'low': return { ...BASE, solar: 0, house: 1.6, battery: -1.6, grid: 0, charge: 18, left: 5.1, grid_up: false, out_since: now - 6 * 3600 }
    case 'back': return { ...BASE, solar: 2.1, house: 1.1, battery: 1.0, grid: 0, charge: 31, left: 8.9, back: { at: now - 120, lasted: 7800 } }
    case 'night': return { ...BASE, solar: 0, house: 0.9, battery: -0.9, grid: 0, charge: 62, left: 17.8 }
    default: return null
  }
}

/* Sunrise at 7:10, sunset at 6:40, a cloud going over at half past twelve -- the boards' afternoon. */
function day(now) {
  const midnight = new Date(now * 1000); midnight.setHours(0, 0, 0, 0)
  const since = midnight.getTime() / 1000, curve = []
  for (let t = since; t <= now; t += 300) {
    const h = (t - since) / 3600
    const sun = h < 7.2 || h > 18.6 ? 0 : Math.max(0, 6.6 * Math.sin(Math.PI * (h - 7.2) / 11.4) * (Math.abs(h - 12.6) < 0.3 ? 0.6 : 1))
    const house = 0.6 + 0.5 * Math.exp(-((h - 7.6) ** 2) / 0.5) + 0.4 * Math.exp(-((h - 12.2) ** 2) / 0.3) + 0.6 * Math.exp(-((h - 19) ** 2) / 1.5)
    curve.push({ at: t, solar: +sun.toFixed(2), house: +house.toFixed(2) })
  }
  return { made: 24.6, used: 9.8, peak: 7.9, since, curve }
}

export function powerRoute(req, res, p) {
  if (p !== '/power' && p !== '/power/day') return false
  const { scenario, now } = asked(req)
  const body = !power(scenario, now) ? null : p === '/power' ? power(scenario, now) : day(now)
  res.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' })
  res.end(JSON.stringify(body))
  return true
}
