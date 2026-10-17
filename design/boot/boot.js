// The wall unit starting up, drawn for any second after power is applied.
//
// Every board in this collection is a <div class="wall" data-dir="..."> and this file builds
// what that direction shows and sets it for a moment in the startup. A wall with data-t is held
// at that second (the frames sheet); one without plays the whole startup on a loop, with a chip
// in the corner giving the real time since power so a frame can be read against the startup.
//
// The times are a hub unit's -- the CM5 starting the house as well as the glass -- and they are
// estimates until a unit is on the bench: the screen's own startup is seconds, the house behind it
// about a minute. A wall that is only a wall finds the house in about twenty seconds instead,
// and every direction here works the same, only shorter.
(function () {
  const T = { esp: 0.3, lit: 0.6, kernel: 3, plymouth: 4, login: 12.4, browser: 13.2, page: 14.3, engine: 22, brain: 62, ready: 75 }
  const clamp = (x) => Math.max(0, Math.min(1, x))
  const ramp = (t, a, b) => clamp((t - a) / (b - a))
  const ease = (x) => x * x * (3 - 2 * x)
  // A live board fast-forwards the long wait, so breathing reads the real clock instead of the
  // startup's time; otherwise a slow breath would play eight times too fast.
  let realClock = null
  const breath = (t, period) => 0.5 + 0.5 * Math.sin(((realClock ?? t) / period) * Math.PI * 2 - Math.PI / 2)
  const el = (cls, html) => { const d = document.createElement('div'); d.className = cls; if (html) d.innerHTML = html; return d }

  // The roof and the walls are two strokes, in the order a pen would draw them: the roof from the
  // left eave over the ridge, then the walls from the top of the left one, down, across and up.
  // The trace copies are the warm point of light F runs along the line.
  const ROOF = 'M112 248 256 120l144 128', WALLS = 'M148 226v170h216V226'
  const LINE = 'fill="none" stroke-width="26" stroke-linecap="round" stroke-linejoin="round"'
  const HOUSE = (s) => `<svg width="${s}" height="${s}" viewBox="0 0 512 512">
    <path class="roof" d="${ROOF}" stroke="#f1eee8" ${LINE}/>
    <path class="walls" d="${WALLS}" stroke="#f1eee8" ${LINE}/>
    <g class="trace" style="opacity:0; filter: drop-shadow(0 0 10px rgba(233,184,114,.9))">
      <path class="troof" d="${ROOF}" stroke="#e9b872" ${LINE}/><path class="twalls" d="${WALLS}" stroke="#e9b872" ${LINE}/></g>
    <circle class="dot" cx="256" cy="306" r="30"/></svg>`

  const BERRY = `<svg width="46" height="56" viewBox="0 0 46 56"><path d="M23 14c-6-9-14-10-18-8 3 6 10 9 18 8zm0 0c6-9 14-10 18-8-3 6-10 9-18 8z" fill="#6cc24a"/>
    <g fill="#c51a4a"><circle cx="15" cy="24" r="7"/><circle cx="31" cy="24" r="7"/><circle cx="23" cy="28" r="7"/><circle cx="12" cy="36" r="7"/>
    <circle cx="34" cy="36" r="7"/><circle cx="23" cy="40" r="7"/><circle cx="17" cy="48" r="6"/><circle cx="29" cy="48" r="6"/></g></svg>`

  const LOG = [
    '[    0.000000] Booting Linux on physical CPU 0x0000000000',
    '[    0.000000] Machine model: Raspberry Pi Compute Module 5',
    '[    0.000000] Memory: 8058112K available',
    '[    0.412207] vc4-drm gpu: bound 1000120000.dsi (ops vc4_dsi_ops)',
    '[    0.903114] mmc0: new HS400 MMC card at address 0001',
    '[    1.204551] EXT4-fs (mmcblk0p2): mounted filesystem',
    '[  OK  ] Started systemd-journald.service - Journal Service.',
    '[  OK  ] Finished systemd-remount-fs.service - Remount Root and Kernel File Systems.',
    '[  OK  ] Reached target local-fs.target - Local File Systems.',
    '         Starting systemd-udevd.service - Rule-based Manager for Device Events...',
    '[  OK  ] Started systemd-udevd.service - Rule-based Manager for Device Events.',
    '[  OK  ] Found device dev-ttyAMA10.device - /dev/ttyAMA10.',
    '[  OK  ] Reached target sysinit.target - System Initialization.',
    '[  OK  ] Started dbus.service - D-Bus System Message Bus.',
    '         Starting NetworkManager.service - Network Manager...',
    '[  OK  ] Started avahi-daemon.service - Avahi mDNS/DNS-SD Stack.',
    '[  OK  ] Started bluetooth.service - Bluetooth service.',
    '[  OK  ] Started NetworkManager.service - Network Manager.',
    '[  OK  ] Reached target network.target - Network.',
    '         Starting docker.service - Docker Application Container Engine...',
    '[  OK  ] Started ssh.service - OpenBSD Secure Shell server.',
    '[  OK  ] Reached target network-online.target - Network is Online.',
    '[  OK  ] Started docker.service - Docker Application Container Engine.',
    '         Starting home-hub.service - The house...',
    '[  OK  ] Started home-hub.service - The house.',
    '[  OK  ] Started getty@tty1.service - Getty on tty1.',
    '[  OK  ] Reached target multi-user.target - Multi-User System.',
    '         Starting wall-kiosk.service - The wall...',
    '[  OK  ] Started wall-kiosk.service - The wall.',
  ]

  function build(wall, dir) {
    const L = {}
    const add = (k, node) => { L[k] = node; wall.appendChild(node); node.style.opacity = 0; return node }

    if (dir === 'today') {
      add('backlit', el('backlit'))
      const c = add('console', el('console', `<div class="logos">${BERRY.repeat(4)}</div><div class="lines"></div>`))
      L.lines = c.querySelector('.lines')
      add('login', el('login', 'Debian GNU/Linux 12 wall tty1\n\nwall login: <span class="cur">_</span>'))
      add('white', el('white'))
      add('err', el('err', `<div class="box"><svg width="64" height="64" viewBox="0 0 24 24" fill="#5f6368"><path d="M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 14H4V8h16v10z"/><path d="M9 11l2 2-2 2m4 0h3" stroke="#5f6368" stroke-width="1.6" fill="none"/></svg>
        <h1>This site can’t be reached</h1><p><b>localhost</b> refused to connect.</p><code>ERR_CONNECTION_REFUSED</code><button>Reload</button></div>`))
      add('panel', el('panel'))
    }

    if ('GHIJK'.includes(dir)) buildHi(wall, dir, L, add)

    if ('ACDEFGHIJ'.includes(dir)) {
      const S = dir === 'C' ? 150 : 340
      const cx = 720, cy = dir === 'A' ? 440 : 430
      const m = add('mark', el('mark', `<div class="dotglow"></div>${HOUSE(S)}`))
      const svg = m.querySelector('svg')
      svg.style.left = cx - S / 2 + 'px'; svg.style.top = cy - S / 2 + 'px'
      L.svg = svg; L.dot = svg.querySelector('.dot'); L.glow = m.querySelector('.dotglow')
      L.geo = { S, x0: cx - S / 2, y0: cy - S / 2, dx: cx - S / 2 + (256 * S) / 512, dy: cy - S / 2 + (306 * S) / 512 }
      for (const k of ['roof', 'walls', 'troof', 'twalls']) L[k] = svg.querySelector('.' + k)
      L.trace = svg.querySelector('.trace')
      L.tip = m.appendChild(el('tip'))
    }

    if (dir === 'C') {
      const w = add('words', el('words', '<div class="line"></div><div class="steps"><i></i><i></i><i></i></div>'))
      L.line = w.querySelector('.line'); L.steps = [...w.querySelectorAll('.steps i')]
    }

    if (dir !== 'today') add('panel', el('panel'))
    if (dir === 'B') add('halo', el('halo'))
    return L
  }

  // The lamp in the mark, from unlit (a warm gray) to lit, with its glow.
  function lamp(L, k, scale) {
    const a = [74, 64, 52], b = [233, 184, 114]
    const c = a.map((v, i) => Math.round(v + (b[i] - v) * k))
    L.dot.setAttribute('fill', `rgb(${c})`)
    const g = L.geo.S * (0.95 + 0.25 * k) * (scale || 1)
    Object.assign(L.glow.style, { width: g + 'px', height: g + 'px', left: L.geo.dx - g / 2 + 'px', top: L.geo.dy - g / 2 + 'px', opacity: k })
  }

  // How much of each stroke is drawn, 0 to 1, as a pen would leave it.
  function drawn(L, roofK, wallK) {
    for (const [k, v] of [['roof', roofK], ['walls', wallK]]) {
      const p = L[k], n = p.getTotalLength()
      p.style.strokeDasharray = `${n} ${n}`
      p.style.strokeDashoffset = n * (1 - v)
      p.style.opacity = v > 0 ? 1 : 0
    }
  }

  // The end of the line, where the pen is, in the wall's own pixels.
  function penAt(L, roofK, wallK) {
    const p = wallK > 0 ? L.walls : L.roof, k = wallK > 0 ? wallK : roofK
    const q = p.getPointAtLength(p.getTotalLength() * k), f = L.geo.S / 512
    return [L.geo.x0 + q.x * f, L.geo.y0 + q.y * f]
  }

  function tip(L, xy, a) {
    Object.assign(L.tip.style, { left: xy[0] - 22 + 'px', top: xy[1] - 22 + 'px', opacity: a })
  }

  function set(L, dir, t) {
    const o = (k, v) => { if (L[k]) L[k].style.opacity = v }

    if (dir === 'today') {
      o('backlit', t >= T.lit && t < T.browser ? 1 : 0)
      o('console', t >= T.kernel && t < T.login ? 1 : 0)
      if (t >= T.kernel && t < T.login) {
        const n = Math.min(LOG.length, Math.floor((t - T.kernel) * 3.4) + 1)
        L.lines.innerHTML = LOG.slice(0, n).map((s) => s.replace('[  OK  ]', '[  <span class="ok">OK</span>  ]')).join('\n')
      }
      o('login', t >= T.login && t < T.browser ? 1 : 0)
      o('white', t >= T.browser && t < T.page ? 1 : 0)
      o('err', t >= T.page && t < T.ready ? 1 : 0)
      o('panel', t >= T.ready ? 1 : 0)
    }

    if (dir === 'A') {
      // Plymouth draws the mark with the lamp unlit; the browser's first page draws the same mark
      // at the same pixels, so the handoff is invisible -- and then the lamp comes on and breathes.
      const out = ease(ramp(t, T.ready, T.ready + 0.8))
      o('mark', ease(ramp(t, T.plymouth, T.plymouth + 0.9)) * (1 - out))
      const warm = ease(ramp(t, T.page + 0.4, T.page + 2.4))
      const k = t < T.ready ? warm * (0.72 + 0.28 * breath(t, 3.2)) : 1
      lamp(L, k, 1 + 3 * out)
      L.svg.style.transform = `scale(${1 + 0.18 * out})`
      o('panel', ease(ramp(t, T.ready + 0.2, T.ready + 1.2)))
    }

    if (dir === 'B') {
      // The glass stays dark -- backlight off -- until it has the house to show. The halo is the
      // only sign of life, lit by the coprocessor a third of a second after power.
      const on = ease(ramp(t, T.esp, T.esp + 1))
      const wait = 0.55 + 0.45 * breath(t, 4)
      const flare = ramp(t, T.ready - 0.6, T.ready)
      const off = 1 - ease(ramp(t, T.ready + 1, T.ready + 3))
      o('halo', on * (t < T.ready - 0.6 ? wait : wait + (1 - wait) * flare) * off)
      o('panel', ease(ramp(t, T.ready + 0.3, T.ready + 1.6)))
    }

    if ('DEF'.includes(dir)) setDrawn(L, dir, t)
    if ('GHIJK'.includes(dir)) setHi(L, dir, t)

    if (dir === 'C') {
      // Three stages, each one the wall can observe for itself on the same box: nothing answering,
      // the engine answering but not the brain, the brain answering but the house not loaded yet.
      const stage = t < T.engine ? 0 : t < T.brain ? 1 : 2
      const out = ease(ramp(t, T.ready, T.ready + 0.6))
      o('mark', ease(ramp(t, T.plymouth, T.plymouth + 0.9)) * (1 - out))
      lamp(L, [0.25, 0.55, 0.85][stage] + 0.1 * breath(t, 3.2) * (t >= T.page ? 1 : 0))
      // Plymouth shows the mark alone; the words begin with the browser's page.
      o('words', ease(ramp(t, T.page, T.page + 0.6)) * (1 - out))
      L.line.textContent = ['Starting up', 'Starting the house', 'Almost ready'][stage]
      L.steps.forEach((d, i) => { d.style.opacity = i < stage ? 0.9 : i === stage ? 0.45 + 0.5 * breath(t, 1.6) : 0.18 })
      o('panel', ease(ramp(t, T.ready + 0.3, T.ready + 1.3)))
    }
  }

  function setDrawn(L, dir, t) {
    const o = (k, v) => { if (L[k]) L[k].style.opacity = v }
    o('mark', 1)
    if (dir === 'D' || dir === 'F') {
      // Drawn once as the screen first lights -- inside Plymouth, which is held until the drawing
      // is finished so the browser always takes over from the whole house.
      const roofK = ease(ramp(t, T.plymouth, T.plymouth + 1.3)), wallK = ease(ramp(t, T.plymouth + 1.1, T.plymouth + 3))
      const out = ease(ramp(t, T.ready + (dir === 'F' ? 0.4 : 0), T.ready + (dir === 'F' ? 1.2 : 0.8)))
      drawn(L, roofK, wallK)
      L.dot.style.opacity = wallK
      L.svg.style.opacity = 1 - out
      L.svg.style.transform = `scale(${1 + 0.18 * out})`
      if (dir === 'D') {
        const warm = ease(ramp(t, T.page + 0.4, T.page + 2.4))
        lamp(L, t < T.ready ? warm * (0.72 + 0.28 * breath(t, 3.2)) : 1, 1 + 3 * out)
        L.glow.style.opacity = (t < T.ready ? warm * (0.72 + 0.28 * breath(t, 3.2)) : 1) * (1 - out)
        o('panel', ease(ramp(t, T.ready + 0.2, T.ready + 1.2)))
      } else {
        // The pen keeps going: a warm point runs the line, roof then walls, until the house is ready.
        const run = ramp(t, T.page, T.page + 0.6) * (1 - ramp(t, T.ready, T.ready + 0.3))
        const lr = L.troof.getTotalLength(), lw = L.twalls.getTotalLength(), c = 120
        const s = (((t - T.page) / 2.8) % 1) * (lr + lw)
        L.troof.style.strokeDasharray = L.twalls.style.strokeDasharray = `${c} ${lr + lw + c}`
        L.troof.style.strokeDashoffset = -s
        L.twalls.style.strokeDashoffset = -(s - lr)
        L.trace.style.opacity = run
        const lit = ease(ramp(t, T.ready, T.ready + 0.4))
        lamp(L, 0.3 + 0.7 * lit, 1 + 3 * out)
        L.glow.style.opacity = lit * (1 - out)
        o('panel', ease(ramp(t, T.ready + 0.6, T.ready + 1.6)))
      }
      tip(L, [0, 0], 0)
    }
    if (dir === 'E') {
      // The drawing is the progress. The roof is drawn while the screen starts; then each thing the
      // wall can see for itself adds a stroke: the browser up, the left wall; the engine answering,
      // the floor; the brain answering, the right wall. The light comes on when the house is ready.
      const a = 170 / 556, b = 386 / 556, d = 1.4
      const roofK = ease(ramp(t, T.plymouth, T.plymouth + 1.6))
      const wallK = a * ease(ramp(t, T.page, T.page + d)) + (b - a) * ease(ramp(t, T.engine, T.engine + d)) + (1 - b) * ease(ramp(t, T.brain, T.brain + d))
      const out = ease(ramp(t, T.ready + 0.6, T.ready + 1.3))
      drawn(L, roofK, wallK)
      L.svg.style.opacity = 1 - out
      L.svg.style.transform = `scale(${1 + 0.18 * out})`
      const k = ease(ramp(t, T.ready, T.ready + 0.6))
      lamp(L, k, 1 + 3 * out)
      L.dot.style.opacity = k
      L.glow.style.opacity = k * (1 - out)
      // While it waits between strokes, the pen rests at the end of the line and glows, so a long
      // stage still shows it has not stopped.
      const waiting = roofK > 0 && t < T.ready ? 0.35 + 0.55 * breath(t, 2.4) : 0
      tip(L, penAt(L, roofK, wallK), waiting)
      o('panel', ease(ramp(t, T.ready + 0.7, T.ready + 1.7)))
    }
  }

  // Round three: a greeting first. Hi comes up with the first frame Plymouth draws, holds for three
  // and a half seconds, and gives way to the house, which waits with its lamp breathing.
  // One slow breath every 6.4 s, shared by the dot and the house's lamp so the handoff does not jump.
  const LAMP_BREATH = 6.4
  const HI = { in: T.plymouth, hold: T.plymouth + 3.5, house: T.plymouth + 4.2 }
  const SCRIPT = 'M60 230C110 200 170 120 190 70C205 30 180 10 160 40C140 75 140 160 135 240C150 190 185 150 220 150' +
    'C255 150 255 190 252 215C250 240 270 248 295 225C315 205 330 180 338 160C334 195 330 225 345 240C360 250 390 235 420 205'

  const ELYIR = 'M68 222C80 216 90 211 100 205C120 195 145 180 145 165C145 150 118 152 110 175C102 200 110 240 140 240' +
    'C160 240 175 225 185 205C200 170 225 90 225 55C225 25 200 25 195 60C190 100 190 200 200 230C207 245 225 245 240 225' +
    'C248 210 252 185 255 160C252 195 255 240 280 240C300 240 310 205 312 160C312 230 310 300 295 330C285 350 260 345 268 320' +
    'C278 290 320 265 345 235C352 215 358 185 362 160C358 195 356 225 368 240C378 250 395 235 405 215C410 195 415 175 420 160' +
    'C428 168 440 170 448 162C450 190 452 220 458 240C463 228 476 214 494 208'
  const ELYIR_AT = { write: 2.6, hold: 4.5 }

  function buildHi(wall, dir, L, add) {
    if (dir === 'J' || dir === 'K') {
      const h = add('hi', el('hi-script', `<svg width="795" height="570" viewBox="10 10 530 380">
        <path class="ink" d="${ELYIR}" fill="none" stroke="#f1eee8" stroke-width="10" stroke-linecap="round" stroke-linejoin="round"/></svg>`))
      L.ink = h.querySelector('.ink')
      L.ldot = add('ldot', el('hi-dot'))
    }
    if (dir === 'G') {
      add('light', el('hi-light'))
      L.word = add('hi', el('hi-word', 'Hi'))
    }
    if (dir === 'H') {
      const h = add('hi', el('hi-script', `<svg width="900" height="450" viewBox="15 -20 450 300">
        <path class="ink" d="${SCRIPT}" fill="none" stroke="#f1eee8" stroke-width="11" stroke-linecap="round" stroke-linejoin="round"/>
        <circle class="tittle" cx="343" cy="112" r="9" fill="#f1eee8"/></svg>`))
      L.ink = h.querySelector('.ink'); L.tittle = h.querySelector('.tittle')
    }
    if (dir === 'I') {
      const w = add('hi', el('hi-word', 'H<span class="i">ı</span>'))
      L.word = w; L.i = w.querySelector('.i')
      L.ldot = add('ldot', el('hi-dot'))
    }
  }

  function afterHi(L, t, lampFrom, houseAt = HI.house) {
    const inn = ease(ramp(t, houseAt - 0.2, houseAt + 0.8))
    const out = ease(ramp(t, T.ready, T.ready + 0.8))
    L.mark.style.opacity = 1
    L.svg.style.opacity = inn * (1 - out)
    L.svg.style.transform = `scale(${0.96 + 0.04 * inn + 0.18 * out})`
    const warm = lampFrom === null ? 1 : ease(ramp(t, lampFrom, lampFrom + 1.6))
    const k = t < T.ready ? warm * (0.72 + 0.28 * breath(t, LAMP_BREATH)) : 1
    lamp(L, k, 1 + 3 * out)
    L.glow.style.opacity = k * inn * (1 - out)
    L.dot.style.opacity = inn
    L.panel.style.opacity = ease(ramp(t, T.ready + 0.2, T.ready + 1.2))
  }

  // The dot of the i as a lamp: it appears unlit, lights, breathes, and glides to where it lands.
  // With handOff the house's own lamp takes over on landing; without it the dot stays and, when the
  // product is ready, swells and fades as the panel comes up.
  function carryDot(L, t, o) {
    const move = ease(ramp(t, o.leave, o.land))
    const x = o.from[0] + (o.to[0] - o.from[0]) * move, y = o.from[1] + (o.to[1] - o.from[1]) * move
    const opening = o.handOff ? 0 : ease(ramp(t, T.ready, T.ready + 0.9))
    const size = (o.size0 + (o.size1 - o.size0) * move) * (1 + 1.5 * opening)
    const k = ease(ramp(t, o.lit, o.lit + 0.8)) * (t < T.ready ? 0.72 + 0.28 * breath(t, LAMP_BREATH) : 1)
    const c = [74, 64, 52].map((v, j) => Math.round(v + ([233, 184, 114][j] - v) * k))
    const shown = o.handOff && t >= o.land ? 0 : ease(ramp(t, o.appear, o.appear + 0.3)) * (1 - opening)
    Object.assign(L.ldot.style, {
      opacity: shown, width: size + 'px', height: size + 'px', left: x - size / 2 + 'px', top: y - size / 2 + 'px',
      background: `rgb(${c})`, boxShadow: `0 0 ${60 * k}px ${18 * k}px rgba(233, 184, 114, ${0.45 * k})`,
    })
  }

  function setHi(L, dir, t) {
    const inn = ease(ramp(t, HI.in, HI.in + 1.2)), gone = ease(ramp(t, HI.hold, HI.hold + 0.9))
    L.hi.style.opacity = inn * (1 - gone)

    if (dir === 'G') {
      // Focus pulls in from a blur, and a warm light drifts slowly behind the word while it holds.
      L.word.style.filter = `blur(${(1 - inn) * 18 + gone * 12}px)`
      L.word.style.letterSpacing = `${0.04 * (1 - inn) - 0.02}em`
      const drift = Math.sin(t / 2.2)
      Object.assign(L.light.style, { opacity: inn * (1 - gone) * (0.8 + 0.2 * breath(t, 3)), transform: `translate(${drift * 40}px, ${Math.cos(t / 2.9) * 18}px)` })
      afterHi(L, t, HI.house + 0.4)
    }

    if (dir === 'J' || dir === 'K') {
      const hold = HI.in + ELYIR_AT.hold, out = ease(ramp(t, hold, hold + 0.9))
      const n = L.ink.getTotalLength(), w = ease(ramp(t, HI.in, HI.in + ELYIR_AT.write))
      L.hi.style.opacity = (t >= HI.in ? 1 : 0) * (1 - out)
      L.ink.style.strokeDasharray = `${n} ${n}`
      L.ink.style.strokeDashoffset = n * (1 - w)
      L.ink.style.opacity = w > 0 ? 1 : 0
      const dotted = HI.in + ELYIR_AT.write + 0.1, houseAt = hold + 0.7
      const from = [(1440 - 795) / 2 + (364 - 10) * 1.5, (900 - 570) / 2 + (118 - 10) * 1.5]
      if (dir === 'J') {
        carryDot(L, t, { from, to: [L.geo.dx, L.geo.dy], size0: 24, size1: (L.geo.S * 60) / 512, appear: dotted, lit: dotted + 0.4, leave: hold + 0.1, land: houseAt + 0.6, handOff: true })
        afterHi(L, t, null, houseAt)
        L.dot.style.opacity = t >= houseAt + 0.6 ? 1 : 0
        if (t < houseAt + 0.6) L.glow.style.opacity = 0
      } else {
        // The same light, left on its own: it settles in the middle of the screen and breathes
        // until the product is ready, then opens into it. Nothing here belongs to one product.
        carryDot(L, t, { from, to: [720, 450], size0: 24, size1: 44, appear: dotted, lit: dotted + 0.4, leave: hold + 0.1, land: hold + 1.4, handOff: false })
        L.panel.style.opacity = ease(ramp(t, T.ready + 0.2, T.ready + 1.2))
      }
    }

    if (dir === 'H') {
      const n = L.ink.getTotalLength(), w = ease(ramp(t, HI.in, HI.in + 1.8))
      L.hi.style.opacity = (t >= HI.in ? 1 : 0) * (1 - gone)
      L.ink.style.strokeDasharray = `${n} ${n}`
      L.ink.style.strokeDashoffset = n * (1 - w)
      L.ink.style.opacity = w > 0 ? 1 : 0
      L.tittle.style.opacity = ease(ramp(t, HI.in + 1.9, HI.in + 2.2))
      afterHi(L, t, HI.house + 0.4)
    }

    if (dir === 'I') {
      // The dot of the i is the house's lamp: it lights after the letters, breathes while Hi holds,
      // then carries over to its place in the house as the letters go.
      L.word.style.transform = `translateY(${(1 - inn) * 14}px)`
      const i = L.i, from = [i.offsetLeft + i.offsetWidth / 2, i.offsetTop + 240 * 0.235]
      carryDot(L, t, { from, to: [L.geo.dx, L.geo.dy], size0: 27, size1: (L.geo.S * 60) / 512, appear: HI.in + 0.5, lit: HI.in + 1.0, leave: HI.hold + 0.1, land: HI.house + 0.6, handOff: true })
      afterHi(L, t, null)
      const handed = t >= HI.house + 0.6
      L.dot.style.opacity = handed ? 1 : 0
      if (!handed) L.glow.style.opacity = 0
    }
  }

  function stageName(t) {
    if (t < T.lit) return 'power applied'
    if (t < T.kernel) return 'firmware'
    if (t < T.page) return 'Linux starting'
    if (t < T.engine) return 'browser up, nothing answering'
    if (t < T.brain) return 'the engine starting'
    if (t < T.ready) return 'the brain starting'
    return 'the house is ready'
  }

  // A loop that spends its time where the decisions are: the first sixteen seconds at 1.5x, the long
  // wait at 8x, and the arrival of the panel at real speed. The chip always shows real time.
  const SEG = [[0, 3, 3], [3, 16, 1], [16, 72, 8], [72, 82, 1]]
  const LOOP = SEG.reduce((s, [a, b, r]) => s + (b - a) / r, 0)
  function realAt(x) {
    for (const [a, b, r] of SEG) { const d = (b - a) / r; if (x < d) return a + x * r; x -= d }
    return 82
  }
  const mmss = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`

  function mount(wall) {
    const dir = wall.dataset.dir
    const L = build(wall, dir)
    if (wall.dataset.t !== undefined) { set(L, dir, +wall.dataset.t); return }
    const chip = el('chip'); wall.appendChild(chip)
    let x = 0, last = performance.now(), paused = false
    chip.onclick = () => { paused = !paused }
    const tick = (now) => {
      if (!paused) x = (x + (now - last) / 1000) % LOOP
      last = now
      const t = realAt(x)
      realClock = now / 1000
      set(L, dir, t)
      realClock = null
      chip.textContent = `${mmss(t)} since power · ${stageName(t)}${paused ? ' · paused' : ''}`
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  }

  window.Boot = { T, mount, set, build }
  document.querySelectorAll('.wall[data-dir]').forEach(mount)
})()
