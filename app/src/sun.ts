/** Where the sun and moon are, from the clock and the home's location. No network, no model. */
const rad = Math.PI / 180

export function sunPosition(date: Date, lat: number, lon: number): { elevation: number; azimuth: number } {
  const n = date.getTime() / 86400000 + 2440587.5 - 2451545.0            // days since J2000
  const L = ((280.46 + 0.9856474 * n) % 360 + 360) % 360                  // mean longitude
  const g = (((357.528 + 0.9856003 * n) % 360 + 360) % 360) * rad         // mean anomaly
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * rad  // ecliptic longitude
  const eps = (23.439 - 0.0000004 * n) * rad
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda))
  const dec = Math.asin(Math.sin(eps) * Math.sin(lambda))
  const gmst = ((18.697374558 + 24.06570982441908 * n) % 24 + 24) % 24
  const lst = ((gmst + lon / 15) % 24 + 24) % 24
  let ha = lst * 15 * rad - ra
  ha = ((ha + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI
  const φ = lat * rad
  const el = Math.asin(Math.sin(φ) * Math.sin(dec) + Math.cos(φ) * Math.cos(dec) * Math.cos(ha))
  const az = Math.atan2(Math.sin(ha), Math.cos(ha) * Math.sin(φ) - Math.tan(dec) * Math.cos(φ))
  return { elevation: el / rad, azimuth: ((az / rad + 180) % 360 + 360) % 360 }
}

/** Without a location: a plausible day, sunrise 6:45, sunset 19:45, so the sky still breathes. */
export function sunGuess(date: Date): { elevation: number; azimuth: number } {
  const h = date.getHours() + date.getMinutes() / 60
  const t = (h - 6.75) / 13
  if (t >= 0 && t <= 1) return { elevation: 62 * Math.sin(Math.PI * t), azimuth: 90 + 180 * t }
  const night = (((h < 6.75 ? h + 24 : h) - 19.75) / 11)
  return { elevation: -34 * Math.sin(Math.PI * night), azimuth: 270 + 180 * night }
}

/** 0 = new, 0.5 = full, 1 = new again. */
export function moonPhase(date: Date): number {
  const synodic = 29.530588853
  const days = (date.getTime() - Date.UTC(2000, 0, 6, 18, 14)) / 86400000
  return ((days % synodic) + synodic) % synodic / synodic
}
