import { reactive } from 'vue'

/* The code on the settings. Kept for this tab only; asked for the first time something needs it. */
export const lock = reactive({
  prompt: null as null | { resolve: (ok: boolean) => void; wrong: boolean; note: string },
  unpaired: new URLSearchParams(location.search).get('join') === '1',   // the house has a code and this is not one of its phones: the join screen is up (?join=1 previews it)
})
const KEY = 'hub-code'
function saved(): string { try { return sessionStorage.getItem(KEY) ?? '' } catch { return '' } }
export function remember(code: string) { try { code ? sessionStorage.setItem(KEY, code) : sessionStorage.removeItem(KEY) } catch {} }

export function askCode(wrong = false, note = ''): Promise<boolean> {
  return new Promise(resolve => { lock.prompt = { resolve, wrong, note } })
}

/** fetch with the code attached, and one chance to type it when the house asks. */
export async function request(url: string, init: RequestInit = {}): Promise<Response> {
  const go = () => {
    const code = saved()
    const headers = new Headers(init.headers ?? {})
    if (code) headers.set('X-Hub-Code', code)
    return fetch(url, { ...init, headers })
  }
  let r = await go(), wrong = false
  for (let tries = 0; r.status === 401 && tries < 4; tries++) {
    let detail = ''
    try { detail = (await r.clone().json()).detail } catch {}
    if (detail === 'phone') { lock.unpaired = true; throw new Error('This phone is not in the house yet.') }
    if (detail !== 'code') break
    if (!(await askCode(wrong))) throw new Error('That needs the code.')
    wrong = true
    r = await go()
  }
  return r
}
