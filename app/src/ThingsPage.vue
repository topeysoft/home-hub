<!--
  SPDX-FileCopyrightText: 2026 Temitope Adeyeri
  SPDX-License-Identifier: AGPL-3.0-or-later
-->
<script setup lang="ts">
/*
 * What this house has: one door holding everything the hub knows about, and the
 * place a thing goes when somebody is done with it.
 *
 * Until this, getting rid of something meant knowing where it was kept — a
 * device behind a room's unlabeled pencil, a puck under This hub, an account on
 * Accounts, a light strip nowhere at all. Four vocabularies, none of them where
 * a person looks. design/forget/ drew the three answers and this is the one
 * chosen: the door holds all of it, and the row on a thing's own pane is the
 * shortcut for the thing in your hand.
 *
 * IT IS GROUPED BY WHAT BROUGHT IT, and that is the whole argument. What brought
 * a thing decides whether it may leave alone — an account's integration is
 * allowed to refuse, a puck re-announces its switches whatever the registry
 * says — so the answer IS the row: "Goes with Ring", with the door to Ring on
 * the group above it. Nothing has to be explained because the shape explains it.
 *
 * THE PANEL WRITES NONE OF THE WORDS. Every line, every button and every
 * question comes from brain/hub/things.py, the way Needs a look draws its acts.
 * Which kinds may leave on their own is the one thing only the brain knows.
 */
import { computed, onMounted, ref } from 'vue'
import { cap, deviceById, notify, load } from './store'
import { forgetDevice, forgetStrip, forgetBridge, removeAccount, getThings, type Act, type Thing, type ThingGroup } from './api'
import Icon from './Icon.vue'

const groups = ref<ThingGroup[]>([])
const count = ref(0)
const loading = ref(true)
const failed = ref('')
/* Which act is armed. One key for the whole page: two questions open at once is two things about to
   happen and no way to tell which tap answers which. */
const asking = ref('')
const busy = ref('')
/* What was just taken out, kept where it was. THERE IS NO UNDO ON THIS ONE -- everywhere else in the
   panel what you touched stays put and IS the undo (AGENTS.md), and here it cannot be, so the row
   stays to say what happened and offers nothing. It goes when the page is opened again. */
const gone = ref<Record<string, string>>({})

const ICON: Record<ThingGroup['kind'], string> = { account: 'lock', here: 'home', bridge: 'bolt', engine: 'sparkle' }
/* A row wears the icon of the thing it IS, not of the group it is in. Forty rows of the same house
   glyph is a list nobody can scan, and this page's whole job is being scanned. The store already
   holds the device, so this is the same question the room tiles answer, asked here. */
function iconFor(t: Thing, g: ThingGroup) {
  const d = deviceById(t.id)
  if (!d) return ICON[g.kind]
  const k = cap(d)
  return k === 'media' && /\b(tv|television|roku)\b/i.test(d.name) ? 'tv' : k
}

async function refresh() {
  try { const r = await getThings(); groups.value = r.groups; count.value = r.count; failed.value = '' }
  catch (e: any) { failed.value = e.message }
  loading.value = false
}
onMounted(refresh)

const lede = computed(() => loading.value ? 'Reading what the house has…'
  : count.value === 1 ? 'One thing, and what brought it.'
  : `${count.value} things, and what brought each of them. This is also where a thing goes when you are done with it.`)

const key = (a: Act) => `${a.act}:${a.to}`
function arm(a: Act) { asking.value = asking.value === key(a) ? '' : key(a) }

/* The brain said what to do and to what; this is the whole of the panel's knowledge about it. */
async function doIt(a: Act) {
  busy.value = key(a)
  try {
    if (a.act === 'forget') await forgetDevice(a.to!)
    else if (a.act === 'strip') await forgetStrip(a.to!)
    else if (a.act === 'bridge') await forgetBridge(a.to!)
    else if (a.act === 'account') await removeAccount(a.to!)
    gone.value[key(a)] = a.do
    asking.value = ''
    await refresh()
    /* the rooms behind this panel are holding the thing that has just left */
    load()
  } catch (e: any) { notify(e.message, 'error'); asking.value = '' }
  busy.value = ''
}

const took = (a: Act | null) => !!a && !!gone.value[key(a)]
</script>

<template>
  <div class="page">
    <p class="page-lede">{{ lede }}</p>

    <p class="empty" v-if="failed">{{ failed }}</p>

    <div class="things" v-for="g in groups" :key="g.id" :class="'is-' + g.kind">
      <div class="things-head">
        <span class="things-k"><Icon :name="ICON[g.kind]" :size="14" />{{ g.name }}</span>
        <!-- the group's own way out: the bigger hammer, said where the reason for it is visible -->
        <template v-if="g.act && !took(g.act)">
          <button class="things-a" :class="{ warn: asking === key(g.act) }" @click="arm(g.act)">{{ g.act.do }}</button>
        </template>
        <span class="things-a still" v-else-if="g.act">{{ gone[key(g.act)] }} · done</span>
      </div>
      <p class="things-ask" v-if="g.act && asking === key(g.act)">
        {{ g.act.ask }}
        <span class="things-ask-do">
          <button class="button small warn" :class="{ busy: busy === key(g.act) }" @click="doIt(g.act)">{{ g.act.yes }}</button>
          <button class="button small ghost" @click="asking = ''">{{ g.act.no }}</button>
        </span>
      </p>

      <ul class="things-rows">
        <li v-for="t in g.things" :key="t.id" :class="{ armed: t.out && asking === key(t.out), spent: t.out && took(t.out) }">
          <span class="things-icon"><Icon :name="iconFor(t, g)" :size="16" /></span>
          <span class="things-text">
            <span class="things-name">{{ t.name }}</span>
            <span class="things-sub" v-if="t.sub">{{ t.sub }}</span>
          </span>
          <span class="things-where">{{ t.where }}</span>
          <span class="things-do">
            <button v-if="t.out && !took(t.out)" class="button small ghost" :class="{ warn: asking === key(t.out) }" @click="arm(t.out)">
              {{ asking === key(t.out) ? 'Take it out?' : t.out.do }}
            </button>
            <span class="things-why" v-else-if="t.out">Taken out</span>
            <span class="things-why" v-else>{{ t.why }}</span>
          </span>
          <!-- what goes, said before it goes, across the row rather than inside the button -->
          <p class="things-ask" v-if="t.out && asking === key(t.out)">
            {{ t.out.ask }}
            <span class="things-ask-do">
              <button class="button small warn" :class="{ busy: busy === key(t.out) }" @click="doIt(t.out)">{{ t.out.yes }}</button>
              <button class="button small ghost" @click="asking = ''">{{ t.out.no }}</button>
            </span>
          </p>
        </li>
      </ul>
    </div>

    <p class="empty" v-if="!loading && !failed && !groups.length">Nothing in the house yet.</p>
    <p class="empty-sub" v-if="!loading && !failed && !groups.length">Anything added from <i>Add to the house</i> appears here, with what brought it.</p>
  </div>
</template>
