// The waitlist: one email, one product, one time, so we can write once when there's a hub ready to plug in. One Elyir
// list (5 October 2026): the product is a column, and Bench's page can write to the same database. Nothing else is
// kept, and whether an address was already on the list is never said back.
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/
const ok = () => Response.json({ ok: true })

export async function onRequestPost({ request, env }) {
  let body
  try { body = await request.json() } catch { return Response.json({ detail: 'Send JSON.' }, { status: 400 }) }
  if (body?.website) return ok()   // the field people can't see: only a script fills it in
  const email = String(body?.email || '').trim().toLowerCase()
  if (email.length > 254 || !EMAIL.test(email)) return Response.json({ detail: "That doesn't look like an email address." }, { status: 400 })
  if (!env.WAITLIST) return Response.json({ detail: 'The list is not set up here.' }, { status: 503 })
  await env.WAITLIST.prepare('CREATE TABLE IF NOT EXISTS signups (email TEXT NOT NULL, product TEXT NOT NULL, at TEXT NOT NULL, PRIMARY KEY (email, product))').run()
  await env.WAITLIST.prepare('INSERT OR IGNORE INTO signups (email, product, at) VALUES (?1, ?2, ?3)').bind(email, 'hub', new Date().toISOString()).run()
  return ok()
}
