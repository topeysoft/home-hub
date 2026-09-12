/* The whole panel, watched: the mock brain and Vite together, from one command, killed together.
   `npm run dev:mock`, then open what it prints. Every change to src/ is on the screen before you
   have looked back at it — no build, no restart, and the mock's preview knobs all still work
   (?at=19:40, ?room=kitchen, ?sheet=hub, WX=rainy, LOCKED=1 …).

   `npm run dev` on its own is the same thing against a real hub on :8300. */
import { spawn } from 'node:child_process'

const MOCK_PORT = process.env.PORT || '8399'
const kids = []

function start(name, cmd, args, env) {
  const p = spawn(cmd, args, { stdio: ['ignore', 'inherit', 'inherit'], env: { ...process.env, ...env } })
  p.on('exit', (code, signal) => {
    // One of them going down makes the other useless, so the pair lives and dies together.
    if (!stopping) { console.error(`\n${name} stopped (${signal || code}); stopping the other.`); stop(code ?? 1) }
  })
  kids.push(p)
  return p
}

let stopping = false
function stop(code = 0) {
  if (stopping) return
  stopping = true
  for (const p of kids) { try { p.kill('SIGTERM') } catch {} }
  setTimeout(() => process.exit(code), 120)
}
for (const sig of ['SIGINT', 'SIGTERM']) process.on(sig, () => stop(0))

start('the mock brain', process.execPath, ['mock/brain.mjs'], { PORT: MOCK_PORT })
start('vite', 'npx', ['vite'], { BRAIN: `http://localhost:${MOCK_PORT}` })
