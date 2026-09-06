<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { getCatalog, startFlow, getFlow, submitFlow, cancelFlow, setCredentials, type CatalogItem, type Step, type Found } from './api'
import { store, notify, refreshFound } from './store'
import Icon from './Icon.vue'
import { parseKeyFile, keyFileWarning } from './keyfile'

/* Adding things to the house. Lists what was noticed on the network, offers a search for anything
   else, and walks through the short form each one needs. Used on the setup screen and in a sheet. */
const emit = defineEmits<{ added: [title: string] }>()
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

function show(s: Step) {
  step.value = s; error.value = ''; warn.value = ''; fileName.value = ''
  for (const k of Object.keys(values)) delete values[k]
  for (const f of s.fields ?? []) values[f.name] = f.default ?? (f.kind === 'boolean' ? false : '')
  if (s.type === 'progress') pollSoon()
}
async function open(f: Found) {
  busy.value = true
  try { show(await getFlow(f.flow_id)) } catch (e: any) { notify(`Couldn't start: ${e.message}`, 'error') }
  busy.value = false
}
async function begin(c: CatalogItem) {
  busy.value = true; q.value = ''
  try { show(await startFlow(c.domain)) } catch (e: any) { notify(`Couldn't start: ${e.message}`, 'error') }
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
  const body = data ?? Object.fromEntries((step.value.fields ?? []).filter(f => values[f.name] !== '' || f.required).map(f => [f.name, f.kind === 'number' ? Number(values[f.name]) : values[f.name]]))
  try {
    const s = await submitFlow(step.value.flow_id, body)
    show(s)
    if (s.type === 'create_entry') { notify(`Added ${s.entry_title || s.kind}.`); emit('added', s.entry_title || s.kind); refreshFound() }
  } catch (e: any) { error.value = e.message }
  busy.value = false
}
let poll: number | undefined
function pollSoon() { clearTimeout(poll); poll = window.setTimeout(async () => { if (step.value?.type === 'progress' && step.value.flow_id) try { show(await getFlow(step.value.flow_id)) } catch {} }, 2000) }
async function back(cancel = true) {
  clearTimeout(poll)
  if (cancel && step.value?.flow_id && (step.value.type === 'form' || step.value.type === 'menu' || step.value.type === 'external')) cancelFlow(step.value.flow_id)
  step.value = null; refreshFound()
}
const heading = computed(() => step.value?.title || (step.value?.type === 'create_entry' ? 'Added' : `Add ${step.value?.kind ?? ''}`))
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
watch(() => store.status?.driver, d => { if (d === 'ready') refreshFound() })
onMounted(refreshFound)
onUnmounted(() => clearTimeout(poll))
</script>

<template>
  <div class="add">
    <template v-if="!step">
      <div class="add-block" v-if="store.found.length">
        <h3 class="label">Found nearby</h3>
        <ul class="found">
          <li v-for="f in store.found" :key="f.flow_id">
            <span class="found-icon"><Icon name="sparkle" :size="18" /></span>
            <span class="found-text"><span class="found-title">{{ f.title }}</span><span class="found-kind">{{ f.kind }}</span></span>
            <button class="button small" :disabled="busy" @click="open(f)">Add</button>
          </li>
        </ul>
      </div>
      <p class="add-empty" v-else-if="store.status?.driver === 'ready'">Nothing new has been noticed on the network yet. Things you plug in tend to appear here within a minute.</p>
      <p class="add-empty" v-else>Looking around…</p>

      <div class="add-block">
        <h3 class="label">Add something else</h3>
        <label class="search">
          <Icon name="search" :size="18" />
          <input v-model="q" @focus="loadCatalog" @input="loadCatalog" type="search" placeholder="Search by brand: Hue, Nest, Roku, Ring, Sonos…" autocomplete="off" spellcheck="false" />
        </label>
        <ul class="results" v-if="matches.length">
          <li v-for="c in matches" :key="c.domain"><button :disabled="busy" @click="begin(c)"><span class="r-name">{{ c.name }}</span><span class="r-sub">{{ c.local ? 'Works without the internet' : 'Needs its account' }}</span></button></li>
        </ul>
        <p class="sheet-status" v-else-if="q.trim().length > 1 && catalog">Nothing by that name. Try the brand on the box.</p>
      </div>
    </template>

    <div class="flow" v-else>
      <h3 class="flow-title display">{{ heading }}</h3>
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
        <div class="flow-actions">
          <button class="button ghost" @click="back(false)">Not now</button>
          <button class="button" :class="{ busy }" @click="submit()">Continue</button>
        </div>
      </template>

      <template v-else-if="step.type === 'form'">
        <p class="error" v-if="step.errors?.base || error">{{ step.errors?.base || error }}</p>
        <label class="field" v-for="f in step.fields" :key="f.name">
          <span class="field-label">{{ f.label }}<span v-if="!f.required" class="field-opt"> optional</span></span>
          <select v-if="f.kind === 'select'" v-model="values[f.name]" class="input"><option v-for="o in f.options" :key="String(o.value)" :value="o.value">{{ o.label }}</option></select>
          <span v-else-if="f.kind === 'boolean'" class="check"><input type="checkbox" v-model="values[f.name]" /><span>{{ f.hint || 'Yes' }}</span></span>
          <input v-else class="input" :type="f.kind === 'password' ? 'password' : f.kind === 'number' ? 'number' : 'text'" v-model="values[f.name]" :placeholder="f.hint" autocomplete="off" autocapitalize="off" spellcheck="false" @keydown.enter="submit()" />
          <span class="field-hint" v-if="f.hint && f.kind !== 'boolean'">{{ f.hint }}</span>
          <span class="field-err" v-if="step.errors?.[f.name]">{{ step.errors[f.name] }}</span>
        </label>
        <div class="flow-actions">
          <button class="button ghost" @click="back()">Cancel</button>
          <button class="button" :class="{ busy }" @click="submit()">{{ step.fields?.length ? 'Continue' : 'Yes, add it' }}</button>
        </div>
      </template>

      <template v-else-if="step.type === 'menu'">
        <div class="menu">
          <button v-for="o in step.options" :key="o.id" class="menu-item" :disabled="busy" @click="submit({ next_step_id: o.id })">{{ o.label }}<Icon name="back" :size="16" class="flip" /></button>
        </div>
        <div class="flow-actions"><button class="button ghost" @click="back()">Cancel</button></div>
      </template>

      <template v-else-if="step.type === 'progress'">
        <p class="flow-desc pulse">{{ step.progress || 'Working…' }}</p>
        <div class="flow-actions"><button class="button ghost" @click="back()">Cancel</button></div>
      </template>

      <template v-else-if="step.type === 'external'">
        <p class="flow-desc">This one finishes on the maker's own page: sign in there and allow it. If a page asks for your Home Assistant address, it is <b>{{ haUrl }}</b>. Come back here when it says it is done.</p>
        <div class="flow-actions">
          <button class="button ghost" @click="back()">Cancel</button>
          <a class="button" :href="step.url" target="_blank" rel="noopener">Open it</a>
          <button class="button ghost" @click="step.flow_id && getFlow(step.flow_id).then(show)">I've done that</button>
        </div>
      </template>

      <template v-else-if="step.type === 'abort'">
        <p class="flow-desc">{{ step.reason }}</p>
        <div class="flow-actions"><button class="button" @click="back(false)">OK</button></div>
      </template>

      <template v-else-if="step.type === 'create_entry'">
        <p class="flow-done"><span class="done-icon"><Icon name="check" :size="20" /></span>{{ step.entry_title || step.kind }} is part of the house now. It will show up in a room shortly; anything without a room lands under New devices.</p>
        <div class="flow-actions"><button class="button" @click="back(false)">Done</button></div>
      </template>
    </div>
  </div>
</template>
