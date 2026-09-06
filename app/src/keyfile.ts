/** The JSON a maker's developer console hands out with an OAuth client. Google's is one object under
 *  "web" (a Web application client) or "installed" (a desktop one) holding the client ID, the secret,
 *  the Cloud project ID and the redirect addresses it was created with. Parsed in the browser only;
 *  the file itself never goes anywhere. */
export type KeyFile = { client_id: string; client_secret: string; project_id: string | null; kind: 'web' | 'installed' | 'other'; redirects: string[] }

export function parseKeyFile(text: string): KeyFile | null {
  let j: any
  try { j = JSON.parse(text) } catch { return null }
  if (!j || typeof j !== 'object') return null
  const kind: KeyFile['kind'] = j.web ? 'web' : j.installed ? 'installed' : 'other'
  const o = j.web ?? j.installed ?? j
  if (typeof o?.client_id !== 'string' || typeof o?.client_secret !== 'string') return null
  return { client_id: o.client_id.trim(), client_secret: o.client_secret.trim(), project_id: typeof o.project_id === 'string' ? o.project_id : null,
           kind, redirects: Array.isArray(o.redirect_uris) ? o.redirect_uris.filter((r: unknown) => typeof r === 'string') : [] }
}

/** What to tell the person before they continue, or null when the key looks right for `redirect`. */
export function keyFileWarning(k: KeyFile, redirect: string | undefined): string | null {
  if (k.kind === 'installed') return 'This key is for a desktop app. Google Nest needs a Web application client; make one of those and download its file instead.'
  if (redirect && k.redirects.length && !k.redirects.includes(redirect)) return `This key was downloaded without the redirect address below. Add it on Google's side, or continue if you added it after downloading.`
  return null
}
