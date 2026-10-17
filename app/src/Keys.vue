<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { complete } from './api'
import { LETTERS, SYMBOLS, enter, erase, goLabel, lift, shapeOf, typable, type, wantsCapital, type Shape } from './keys'
/* The wall's keyboard (design/keyboard/, C): docked along the bottom, in the shape the focused field wants, mounted
   only on the wall. Keys act on pointerdown and cancel it, so the field never loses its focus to a key; the keyboard
   goes when the field does, which is a tap outside or the field's own Enter moving on. */
const field = ref<HTMLInputElement | HTMLTextAreaElement | null>(null)
const shape = ref<Shape>('letters'), layer = ref<'letters' | 'symbols'>('letters')
const shift = ref(false), capital = ref(false), go = ref('Done')
const sentences = ref<string[]>([])
const board = ref<HTMLElement | null>(null)
let asking = 0, timer = 0
// The completions row comes and goes as the sentence changes, so the keyboard's height does too.
const resized = new ResizeObserver(() => { if (field.value) place() })

const upper = computed(() => shift.value || capital.value)
const rows = computed(() => layer.value === 'symbols' ? SYMBOLS : LETTERS)

// The page moves up by --keys-lift, which panel.css reads only while the wall's keyboard is mounted.
function setLift(px: number) { document.documentElement.style.setProperty('--keys-lift', `${px}px`) }

/* What has to stay above the keyboard: the field, and whatever its data-keys-keep names in the same section --
   the passcode's Continue, the town's results -- so typing never hides the answer to what is typed. */
function keepBottom(el: HTMLElement) {
  const sel = el.dataset.keysKeep, scope = el.closest('section, form, [role="dialog"]') ?? document
  const all = [el, ...(sel ? Array.from(scope.querySelectorAll<HTMLElement>(sel)) : [])]
  return Math.max(...all.map((e) => e.getBoundingClientRect().bottom))
}

// Where the page is right now, mid-slide included, so a measurement taken while it moves is still true.
function movedNow() {
  const s = document.querySelector('.shell')
  return s ? parseFloat(getComputedStyle(s).translate.split(' ')[1] ?? '0') || 0 : 0
}

async function place() {
  await nextTick()
  const el = field.value, kb = board.value
  if (!el || !kb) return
  resized.observe(kb)
  setLift(lift(keepBottom(el) - movedNow(), innerHeight, kb.offsetHeight))
}

function settle() {
  const el = field.value
  capital.value = !!el && wantsCapital(el)
  if (shape.value === 'command') ask()
}

function ask() {
  clearTimeout(timer)
  timer = window.setTimeout(async () => {
    const el = field.value; if (!el) return
    const mine = ++asking, got = await complete(el.value, el.dataset.room || null)
    if (mine === asking) sentences.value = got
  }, 120)
}

function open(el: HTMLInputElement | HTMLTextAreaElement) {
  const was = field.value
  field.value = el
  shape.value = shapeOf(el); layer.value = 'letters'; shift.value = false; go.value = goLabel(el)
  if (was !== el) sentences.value = []
  settle(); place()
}

function close() {
  field.value = null; sentences.value = []
  setLift(0)
}

function onFocusIn(e: FocusEvent) { if (typable(e.target as Element)) open(e.target as HTMLInputElement) }
function onFocusOut() { setTimeout(() => { const a = document.activeElement; if (typable(a)) open(a); else close() }) }
function onInput(e: Event) { if (e.target === field.value) settle() }

function key(c: string) {
  const el = field.value; if (!el) return
  type(el, upper.value ? c.toUpperCase() : c)
  shift.value = false
}
function back() { if (field.value) erase(field.value) }
function space() { if (field.value) type(field.value, ' ') }
function done() {
  const el = field.value; if (!el) return
  enter(el)
  if (go.value === 'Search' || go.value === 'Done') el.blur()
}
function pick(s: string) {
  const el = field.value; if (!el) return
  el.value = ''; type(el, s); sentences.value = []
}

onMounted(() => {
  document.documentElement.dataset.wallKeys = ''
  document.addEventListener('focusin', onFocusIn)
  document.addEventListener('focusout', onFocusOut)
  document.addEventListener('input', onInput, true)
  if (typable(document.activeElement)) open(document.activeElement)
})
onBeforeUnmount(() => {
  document.removeEventListener('focusin', onFocusIn)
  document.removeEventListener('focusout', onFocusOut)
  document.removeEventListener('input', onInput, true)
  close()
  resized.disconnect()
  delete document.documentElement.dataset.wallKeys
})
</script>

<template>
  <Teleport to="body">
    <Transition name="wallkeys">
      <div v-if="field" ref="board" class="wallkeys" :data-shape="shape" role="group" aria-label="Keyboard" @pointerdown.prevent>
        <div v-if="shape === 'command' && sentences.length" class="wallkeys-chips">
          <button v-for="(s, i) in sentences" :key="s" type="button" class="wallkeys-chip" :class="{ quiet: i >= 3 }" @pointerdown.prevent="pick(s)">{{ s }}</button>
        </div>
        <div v-if="shape === 'pad'" class="wallkeys-rows pad">
          <div v-for="r in ['123', '456', '789']" :key="r" class="wallkeys-row">
            <button v-for="c in r" :key="c" type="button" class="wallkey" @pointerdown.prevent="key(c)">{{ c }}</button>
          </div>
          <div class="wallkeys-row">
            <button type="button" class="wallkey mod" aria-label="Delete" @pointerdown.prevent="back"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"><path d="M9 5h11v14H9l-6-7z" /><path d="m12 9 5 6m0-6-5 6" /></svg></button>
            <button type="button" class="wallkey" @pointerdown.prevent="key('0')">0</button>
            <button type="button" class="wallkey go" @pointerdown.prevent="done">{{ go }}</button>
          </div>
        </div>
        <div v-else class="wallkeys-rows">
          <div v-for="(r, i) in rows" :key="r" class="wallkeys-row">
            <button v-if="i === 2" type="button" class="wallkey mod wide" :class="{ on: upper && layer === 'letters' }" :aria-label="layer === 'letters' ? 'Shift' : 'More symbols'"
              @pointerdown.prevent="layer === 'letters' ? (shift = !shift) : null">
              <svg v-if="layer === 'letters'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><path d="M12 4 4 12h4.5v7h7v-7H20z" /></svg>
            </button>
            <button v-for="c in r" :key="c" type="button" class="wallkey" @pointerdown.prevent="key(c)">{{ upper && layer === 'letters' ? c.toUpperCase() : c }}</button>
            <button v-if="i === 2" type="button" class="wallkey mod wide" aria-label="Delete" @pointerdown.prevent="back"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round" stroke-linecap="round"><path d="M9 5h11v14H9l-6-7z" /><path d="m12 9 5 6m0-6-5 6" /></svg></button>
          </div>
          <div class="wallkeys-row">
            <button type="button" class="wallkey mod wide" @pointerdown.prevent="layer = layer === 'letters' ? 'symbols' : 'letters'">{{ layer === 'letters' ? '123' : 'ABC' }}</button>
            <button type="button" class="wallkey mod space" aria-label="Space" @pointerdown.prevent="space"></button>
            <button type="button" class="wallkey go wider" @pointerdown.prevent="done">{{ go }}</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
