// hub.elyir.com/install, one address for two readers (Cloudflare Pages Functions; wrangler picks up this folder when
// `pages deploy` runs in site/). curl asks for anything and gets install.sh, which
// `curl -fsSL https://hub.elyir.com/install | sudo bash` pipes to bash. A browser asks for HTML and is sent to the ways
// to get it on the front page. The two must never swap: a page that came back to curl would be run by bash, so only an
// explicit text/html is sent elsewhere.
export async function onRequest({ request, env }) {
  if (request.method !== 'GET' && request.method !== 'HEAD') return new Response(null, { status: 405, headers: { Allow: 'GET, HEAD' } })
  if ((request.headers.get('Accept') || '').includes('text/html')) {
    return new Response(null, { status: 302, headers: { Location: '/#get', Vary: 'Accept' } })
  }
  const res = await env.ASSETS.fetch(new Request(new URL('/install.sh', request.url), { method: request.method }))
  const out = new Response(res.body, res)
  if (res.ok) {
    out.headers.set('Content-Type', 'text/plain; charset=utf-8')
    out.headers.set('Cache-Control', 'no-cache')
  }
  out.headers.append('Vary', 'Accept')
  return out
}
