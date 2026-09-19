<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { getCatalog, startFlow, getFlow, submitFlow, cancelFlow, setCredentials, type CatalogItem, type Step, type Field } from '../api'
import { notify } from '../store'
import { type Act, type Caught, type Working } from '../adding'
import Icon from '../Icon.vue'
import { parseKeyFile, keyFileWarning } from '../keyfile'

/*
 * SIGN IN TO IT. Beat two for anything that came with its own app: Hue, Sonos, a doorbell, a
 * thermostat. The proof is not on the object at all -- it is an account, and the maker holds it.
 *
 * This is the one route the house does not finish alone, and the screen says so plainly rather than
 * pretending: it opens the maker's page, and comes back when they are done. Everything the makers'
 * own forms ask for is drawn here in the panel's own furniture, so a person never falls through into
 * somebody else's design half way through adding a lamp.
 *
 * It ends in an ENTRY, not a device -- one account can bring in six lights and a speaker at once --
 * so beat four asks the rooms under New devices instead of pretending there is one room to ask about.
 *
 * design/adding/Proving.dc.html.
 */
const props = defineProps<{ on?: string | null }>()
const emit = defineEmits<{ working: [Working], caught: [Caught], wrong: [string, boolean?], acts: [Act[]], head: [string] }>()

const step = ref<Step | null>(null)
const values = reactive<Record<string, any>>({})
const busy = ref(false), q = ref(''), catalog = ref<CatalogItem[] | null>(null), error = ref('')
const warn = ref(''), hints = ref<Record<string, string>>({}), fileName = ref('')
const matches = computed(() => {
  const s = q.value.trim().toLowerCase()
  if (!s || !catalog.value) return []
  return catalog.value.filter(c => c.name.toLowerCase().includes(s) || c.domain.includes(s) || (c.brand ?? '').toLowerCase().includes(s)).slice(0, 8)
})
async function loadCatalog() { if (!catalog.value) try { catalog.value = await getCatalog() } catch {} }

const blank = (f: Field) => f.default ?? (f.kind === 'boolean' ? false : '')
function show(s: Step) {
  step.value = s; error.value = ''; warn.value = ''; fileName.value = ''
  for (const k of Object.keys(values)) delete values[k]
  for (const f of s.fields ?? []) values[f.name] = f.kind === 'section' ? Object.fromEntries((f.fields ?? []).map(g => [g.name, blank(g)])) : blank(f)
  if (s.title) emit('head', s.title)
  if (s.type === 'progress') { emit('working', { text: s.progress || 'Asking them for your things…' }); pollSoon() }
  if (s.type === 'create_entry') emit('caught', { many: true, name: s.entry_title || s.kind, what: undefined })
  if (s.type === 'abort') { emit('head', 'It would not join.'); emit('wrong', `${s.reason}${s.hint ? ' ' + s.hint : ''}`, !!s.retry) }
}
/* what goes back to the house: filled-in fields, numbers as numbers, a section as its own object */
function answers(fields: Field[], vals: Record<string, any>): Record<string, unknown> {
  return Object.fromEntries(fields.flatMap(f => {
    if (f.kind === 'section') return [[f.name, answers(f.fields ?? [], vals[f.name] ?? {})]]
    const v = vals[f.name]
    if (v === '' && !f.required) return []
    return [[f.name, f.kind === 'number' ? Number(v) : v]]
  }))
}
/* A conversation that was handed over can be gone by the time it is opened: used up by a first try,
   answered on another screen, or forgotten by the hub. That is not a failure worth a whole screen --
   and it must never be a dead end after "Try again", which is exactly where it used to land. So it
   falls back to the way in that always works, and says why it is asking again. */
const gone = ref(false)
async function open(flowId: string) {
  busy.value = true
  try { show(await getFlow(flowId)) } catch { gone.value = true; loadCatalog() }
  busy.value = false
}
async function begin(c: CatalogItem) {
  busy.value = true; q.value = ''
  try { show(await startFlow(c.domain)) } catch (e: any) { emit('wrong', `Couldn't start: ${e.message}`, false) }
  busy.value = false
}
async function submit(data?: Record<string, unknown>) {
  if (!step.value || busy.value) return
  if (step.value.type === 'credentials') {
    if (!values.client_id?.trim() || !values.client_secret?.trim()) { error.value = 'Both boxes are needed.'; return }
    busy.value = true
    const h = hints.value; hints.value = {}
    try { show(await setCredentials(step.value.handler, values.client_id.trim(), values.client_secret.trim(), h)) } catch (e: any) { error.value = e.message; hints.value = h }
    busy.value = false; return
  }
  if (!step.value.flow_id) return
  busy.value = true
  const body = data ?? answers(step.value.fields ?? [], values)
  try { show(await submitFlow(step.value.flow_id, body)) } catch (e: any) { error.value = e.message }
  busy.value = false
}
let poll: number | undefined
function pollSoon() { clearTimeout(poll); poll = window.setTimeout(async () => { if (step.value?.type === 'progress' && step.value.flow_id) try { show(await getFlow(step.value.flow_id)) } catch {} }, 2000) }

const haUrl = `http://${location.hostname}:8123`

/* The key file a maker's console hands out: choose it, drop it, or paste its text into either box. Read here,
   never sent anywhere; only the two fields go to the hub, plus the project ID for a later step. */
function absorb(text: string, name = ''): boolean {
  const k = parseKeyFile(text)
  if (!k) return false
  values.client_id = k.client_id; values.client_secret = k.client_secret
  hints.value = k.project_id ? { cloud_project_id: k.project_id } : {}
  warn.value = keyFileWarning(k, step.value?.redirect_url) ?? ''
  fileName.value = name || 'pasted key'; error.value = ''
  return true
}
async function fromFile(f: File | undefined | null) {
  if (!f) return
  if (!absorb(await f.text(), f.name)) error.value = `${f.name} doesn't look like a key file.`
}
const picked = (e: Event) => { const i = e.target as HTMLInputElement; fromFile(i.files?.[0]); i.value = '' }
const dropped = (e: DragEvent) => fromFile(e.dataTransfer?.files?.[0])
function pasted(e: ClipboardEvent) { const t = e.clipboardData?.getData('text') ?? ''; if (t.trim().startsWith('{') && absorb(t)) e.preventDefault() }
async function copy(text: string) { try { await navigator.clipboard.writeText(text); notify('Copied.') } catch { notify(text) } }

/* What this piece needs offering. The shell says them in the house's order, with the way out last. */
watch(step, s => {
  if (!s) return emit('acts', [])
  if (s.type === 'credentials' || s.type === 'form') emit('acts', [{ label: s.type === 'form' && !s.fields?.length ? 'Add it' : 'Continue', primary: true, run: () => submit() }])
  else if (s.type === 'external') emit('acts', [
    { label: 'Open their page', primary: true, run: () => window.open(s.url, '_blank', 'noopener') },
    { label: 'I’ve done that', run: () => s.flow_id && getFlow(s.flow_id).then(show) },
  ])
  else emit('acts', [])
}, { immediate: true, deep: true })

/* Walking away from a flow this screen started closes it, so the hub is not left holding a half-asked
   question. A conversation handed over by somebody else is not this screen's to close. */
onMounted(() => { if (props.on) open(props.on); else loadCatalog() })
onUnmounted(() => {
  clearTimeout(poll)
  const own = step.value?.flow_id !== props.on
  if (own && step.value?.flow_id && ['form', 'menu', 'external'].includes(step.value.type)) cancelFlow(step.value.flow_id)
})
</script>

<template>
  <!-- no flow yet: which maker is it -->
  <template v-if="!step">
    <p class="flow-desc" v-if="gone">That one is not waiting any more &mdash; it was either added already, or the hub has forgotten it. It will turn up again on its own; or find it by its brand here.</p>
    <p class="flow-desc" v-else>Search the brand on the box. Most of them sign in on their own page; some are already on your Wi‑Fi and just need saying yes to.</p>
    <label class="search">
      <Icon name="search" :size="18" />
      <input v-model="q" @focus="loadCatalog" @input="loadCatalog" type="search" placeholder="Hue, Nest, Roku, Ring, Sonos…" autocomplete="off" spellcheck="false" />
    </label>
    <ul class="results" v-if="matches.length">
      <li v-for="c in matches" :key="c.domain"><button :disabled="busy" @click="begin(c)"><span class="r-name">{{ c.name }}</span><span class="r-sub">{{ c.local ? 'Works without the internet' : 'Needs its account' }}</span></button></li>
    </ul>
    <p class="sheet-status" v-else-if="q.trim().length > 1 && catalog">Nothing by that name. Try the brand on the box.</p>
  </template>

  <template v-else>
    <div class="flow-desc" v-if="step.description" v-html="step.description"></div>

    <template v-if="step.type === 'credentials'">
      <p class="error" v-if="error">{{ error }}</p>
      <div class="copy-row" v-if="step.redirect_url"><span class="copy-label">Redirect address</span><code class="copy-text">{{ step.redirect_url }}</code><button class="button small ghost" @click="copy(step.redirect_url!)">Copy</button></div>
      <label class="drop" :class="{ has: fileName }" @dragover.prevent @drop.prevent="dropped">
        <input type="file" accept=".json,application/json" hidden @change="picked" />
        <Icon :name="fileName ? 'check' : 'plus'" :size="18" />
        <span v-if="fileName">Filled in from <b>{{ fileName }}</b>. Check the boxes and continue.</span>
        <span v-else>Downloaded the key file? <b>Choose it</b>, drop it here, or paste its text into either box.</span>
      </label>
      <p class="field-hint warn" v-if="warn">{{ warn }}</p>
      <label class="field" v-for="f in step.fields" :key="f.name">
        <span class="field-label">{{ f.label }}</span>
        <input class="input" :type="f.kind === 'password' ? 'password' : 'text'" v-model="values[f.name]" autocomplete="off" autocapitalize="off" spellcheck="false" @paste="pasted" @keydown.enter="submit()" />
      </label>
    </template>

    <template v-else-if="step.type === 'form'">
      <p class="error" v-if="step.errors?.base || error">{{ step.errors?.base || error }}</p>
      <template v-for="f in step.fields" :key="f.name">
        <details class="section" v-if="f.kind === 'section'" :open="f.expanded">
          <summary>{{ f.label }}</summary>
          <p class="field-hint" v-if="f.hint">{{ f.hint }}</p>
          <label class="field" v-for="g in f.fields" :key="g.name">
            <span class="field-label">{{ g.label }}<span v-if="!g.required" class="field-opt"> optional</span></span>
            <select v-if="g.kind === 'select'" v-model="values[f.name][g.name]" class="input"><option v-for="o in g.options" :key="String(o.value)" :value="o.value">{{ o.label }}</option></select>
            <span v-else-if="g.kind === 'boolean'" class="check"><input type="checkbox" v-model="values[f.name][g.name]" /><span>{{ g.hint || 'Yes' }}</span></span>
            <input v-else class="input" :type="g.kind === 'password' ? 'password' : g.kind === 'number' ? 'number' : 'text'" v-model="values[f.name][g.name]" :placeholder="g.hint" autocomplete="off" autocapitalize="off" spellcheck="false" />
          </label>
        </details>
        <label class="field" v-else>
          <span class="field-label">{{ f.label }}<span v-if="!f.required" class="field-opt"> optional</span></span>
          <select v-if="f.kind === 'select'" v-model="values[f.name]" class="input"><option v-for="o in f.options" :key="String(o.value)" :value="o.value">{{ o.label }}</option></select>
          <span v-else-if="f.kind === 'boolean'" class="check"><input type="checkbox" v-model="values[f.name]" /><span>{{ f.hint || 'Yes' }}</span></span>
          <input v-else class="input" :type="f.kind === 'password' ? 'password' : f.kind === 'number' ? 'number' : 'text'" v-model="values[f.name]" :placeholder="f.hint" autocomplete="off" autocapitalize="off" spellcheck="false" @keydown.enter="submit()" />
          <span class="field-hint" v-if="f.hint && f.kind !== 'boolean'">{{ f.hint }}</span>
          <span class="field-err" v-if="step.errors?.[f.name]">{{ step.errors[f.name] }}</span>
        </label>
      </template>
    </template>

    <template v-else-if="step.type === 'menu'">
      <div class="menu">
        <button v-for="o in step.options" :key="o.id" class="menu-item" :disabled="busy" @click="submit({ next_step_id: o.id })">{{ o.label }}<Icon name="back" :size="16" class="flip" /></button>
      </div>
    </template>

    <template v-else-if="step.type === 'external'">
      <p class="flow-desc">This one finishes on the maker’s own page: sign in there and allow it. If a page asks for your Home Assistant address, it is <b>{{ haUrl }}</b>. Come back here when it says it is done.</p>
    </template>
  </template>
</template>
