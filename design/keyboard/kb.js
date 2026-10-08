// The wall's keyboard, three ways, over three real fields. Each board is <div class="wall"
// data-dir="today|A|B|C" data-field="code|where|command">; a board without data-field shows the
// yellow switch so one board covers all three. The screens are the panel's own, at 1440x900.
(function () {
  const FIELDS = {
    // Setup, step 2: two passcode fields, the second being typed into.
    code: { img: 'code.jpg', label: 'Passcode', go: 'Continue', keep: 611,
      typed: [{ x: 438, y: 470, w: 230, h: 50, text: '••••', dots: true },
              { x: 438, y: 561, w: 230, h: 50, text: '••', dots: true, caret: true }],
      at: { x: 420, y: 561, w: 260, h: 50 } },
    // Setup, step 3: a town, with what it found under the field.
    where: { img: 'where.jpg', label: 'A town', go: 'Search', keep: 601,
      typed: [{ x: 465, y: 459, w: 520, h: 46, text: 'Holts Su', caret: true, mask: true }],
      at: { x: 420, y: 457, w: 600, h: 50 } },
    // Home: the command box, open.
    command: { img: 'command.jpg', label: 'Command box', go: 'Go', keep: 869,
      typed: [{ x: 103, y: 817, w: 320, h: 50, text: 'kitchen li', caret: true, mask: true }],
      at: { x: 40, y: 815, w: 458, h: 54 } },
  }
  const LETTERS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
  const SYMBOLS = ['1234567890', '-/:;()$&@"', ".,?!'"]
  // What "kitchen li" can finish as in the house's own fixed grammar, then its rooms and questions.
  const CHIPS = [['kitchen lights off', 0], ['kitchen lights on', 0], ['kitchen lights dim', 0], ['Living room', 1], ['Den', 1], ['Is anything on?', 1]]

  const SHIFT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 4 4 12h4.5v7h7v-7H20z"/></svg>'
  const DEL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"><path d="M9 5h11v14H9l-6-7z"/><path d="m12 9 5 6m0-6-5 6"/></svg>'

  const el = (tag, cls, html) => { const d = document.createElement(tag); if (cls) d.className = cls; if (html != null) d.innerHTML = html; return d }
  const key = (label, w, h, cls = '') => { const k = el('div', 'key ' + cls, label); k.style.width = w + 'px'; k.style.height = h + 'px'; return k }

  // A full keyboard: letters, or the symbol layer the passcode lands on in A.
  function full(field, k, layer) {
    const { w, h, gap } = k, rows = el('div', 'rows'), set = layer === 'symbols' ? SYMBOLS : LETTERS
    set.forEach((r, i) => {
      const row = el('div', 'row')
      if (i === 2) row.append(key(layer === 'symbols' ? '#+=' : SHIFT, w * 1.5 + gap / 2, h, 'mod'))
      ;[...r].forEach((c) => row.append(key(c, w, h, field === 'command' && layer === 'letters' && c === 'i' ? 'press' : '')))
      if (i === 2) row.append(key(DEL, w * 1.5 + gap / 2, h, 'mod'))
      rows.append(row)
    })
    const last = el('div', 'row')
    last.append(key(layer === 'symbols' ? 'ABC' : '123', w * 1.5, h, 'mod'), key('', w * 6 + gap * 5, h, 'mod'), key(FIELDS[field].go, w * 2.5 + gap, h, 'go'))
    rows.append(last)
    return rows
  }

  // Digits only, large: what C gives a passcode, and B gives it small.
  const OK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m5 12.5 4.5 4.5L19 7.5"/></svg>'
  function pad(field, w, h, gap) {
    const rows = el('div', 'rows')
    for (const r of ['123', '456', '789']) { const row = el('div', 'row'); [...r].forEach((c) => row.append(key(c, w, h))); rows.append(row) }
    const last = el('div', 'row'); last.append(key(DEL, w, h, 'mod'), key('0', w, h), key(w < 100 ? OK : FIELDS[field].go, w, h, 'go')); rows.append(last)
    rows.style.gap = gap + 'px'; [...rows.children].forEach((r) => (r.style.gap = gap + 'px'))
    return rows
  }

  function typed(screen, f) {
    for (const t of f.typed) {
      const d = el('div', 'typed' + (t.dots ? ' dots' : ''), t.text.replace(/ /g, ' ') + (t.caret ? '<i></i>' : ''))
      Object.assign(d.style, { left: t.x + 'px', top: t.y + 'px', width: t.w + 'px', height: t.h + 'px' })
      if (t.mask) d.dataset.mask = '1'
      screen.append(d)
    }
  }

  // The screenshot's placeholder sits where the typed words go, so each typed line is backed with
  // the field's own color, read off the screenshot itself.
  function maskAll(wall, img) {
    const im = new Image()
    im.onload = () => {
      try {
        const c = document.createElement('canvas'); c.width = 1440; c.height = 900
        const g = c.getContext('2d'); g.drawImage(im, 0, 0, 1440, 900)
        wall.querySelectorAll('.typed[data-mask]').forEach((d) => {
          const x = parseFloat(d.style.left) + parseFloat(d.style.width) - 6, y = parseFloat(d.style.top) + parseFloat(d.style.height) / 2
          const [r, gg, b] = g.getImageData(x, y, 1, 1).data
          d.style.background = `rgb(${r},${gg},${b})`
        })
      } catch { wall.querySelectorAll('.typed[data-mask]').forEach((d) => (d.style.background = '#25262c')) }
    }
    im.src = img
  }

  function draw(wall, dir, field) {
    wall.innerHTML = ''
    const f = FIELDS[field]
    const screen = el('div', 'screen'); screen.style.backgroundImage = `url(${f.img})`
    wall.append(screen); typed(screen, f); maskAll(wall, f.img)
    if (dir === 'today') return

    if (dir === 'A' || dir === 'C') {
      // Docked along the bottom; the page moves up just far enough to keep the field and what
      // answers it in view.
      const kb = el('div', 'kb docked'), k = { w: 92, h: 62, gap: 10 }
      if (dir === 'C' && field === 'code') kb.append(pad(field, 150, 64, 12))
      else {
        if (dir === 'C' && field === 'command') {
          const chips = el('div', 'chips')
          CHIPS.forEach(([t, q]) => chips.append(el('div', 'chip' + (q ? ' quiet' : ''), t)))
          kb.append(chips)
        }
        kb.append(full(field, k, dir === 'A' && field === 'code' ? 'symbols' : 'letters'))
      }
      wall.append(kb)
      const top = 900 - kb.offsetHeight
      screen.style.transform = `translateY(${-Math.max(0, f.keep - (top - 24))}px)`
    }

    if (dir === 'B') {
      // Small, beside the field it types into, with a tail pointing at it; nothing else moves.
      const kb = el('div', 'kb float'), tail = el('div', 'tail')
      let x, y, tx, ty
      if (field === 'code') { kb.append(pad(field, 72, 52, 8)); x = 712; y = 470; tx = x - 9; ty = 577 }
      else { kb.append(full(field, { w: 56, h: 50, gap: 8 }, 'letters')); x = field === 'where' ? 380 : 40; y = field === 'where' ? 618 : 500 }
      Object.assign(kb.style, { left: x + 'px', top: y + 'px' })
      wall.append(kb)
      const hgt = kb.offsetHeight
      if (field === 'where') { tx = 520; ty = y - 9 }
      if (field === 'command') { tx = 140; ty = y + hgt - 9 }
      Object.assign(tail.style, { left: tx + 'px', top: ty + 'px' })
      wall.insertBefore(tail, kb)
    }
  }

  function mount(wall) {
    const dir = wall.dataset.dir
    if (wall.dataset.field) return draw(wall, dir, wall.dataset.field)
    let field = 'command'
    const pick = el('div', 'pick')
    const show = () => { draw(wall, dir, field); wall.append(pick); [...pick.children].forEach((b) => b.classList.toggle('on', b.dataset.f === field)) }
    for (const [f, v] of Object.entries(FIELDS)) {
      const b = el('b', '', v.label); b.dataset.f = f; b.onclick = () => { field = f; show() }; pick.append(b)
    }
    show()
  }

  window.Keyboard = { mount, FIELDS }
  document.querySelectorAll('.wall[data-dir]').forEach(mount)
})()
