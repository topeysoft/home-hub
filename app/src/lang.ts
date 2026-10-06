// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What language the house is in, and the one place that answers it.
 *
 * This is NOT a translation layer. The panel's own words -- "Welcome home.", "It's in.", the
 * buttons, the ledes -- are English, and they are written here rather than looked up. What this
 * file settles is the other language question, the one the panel had already answered four
 * different ways by accident:
 *
 *   the chrome said English            <html lang="en">, and every string written in a template
 *   the clock said the device          16 toLocale* calls passing [], which means navigator's
 *   the voice said the device          ear.ts and mouth.ts, both on navigator.language
 *   everything the makers wrote        said English, pinned by language="en" in the brain
 *
 * So a tablet in Lyon showed "vendredi 20 septembre" under an English heading, listened for
 * French, and then failed to understand it because the command parser is English. Four answers,
 * none of them chosen.
 *
 * Now there is one answer and the HOUSE owns it, the way it owns the look and the location -- a
 * phone and the wall must not disagree about what the thermostat's maker is called. It arrives on
 * `status.language`, it is set once at first run from whatever browser did the setting up, and it
 * is changed from This hub. Until the status lands, the device's own language is the best guess
 * available, which is also what the panel did before.
 *
 * What it reaches today: dates and times, the place search, the voice, <html lang>, and -- the
 * one that is worth the whole file -- Home Assistant's own translations of every integration
 * name, form label and error on the Add screen. HA ships those in about seventy languages. The
 * panel owns none of those strings and never will.
 */
import { ref } from 'vue'

/*
 * Held here rather than read out of the store, and the store pushes it in. store.ts formats dates
 * and so calls locale(); if this file reached back into the store for it, the two would import
 * each other. A live ref costs nothing and keeps the arrow pointing one way.
 */
const house = ref<string | null>(null)

/** The house has said what language it is in. Called from the store whenever a status lands. */
export function setHouseLanguage(code: string | null | undefined) {
  house.value = code || null
  applyLang()
}

/** The house's language as a BCP-47 tag, else this device's. Safe before anything has loaded. */
export function locale(): string {
  if (house.value) return house.value
  try { return navigator.language || 'en' } catch { return 'en' }
}

/** The primary subtag on its own: "pt-BR" -> "pt". What asks that want a language, not a locale, take. */
export const language = () => locale().split('-')[0]

/*
 * Kept in step with the document itself, because `lang` is not decoration: it picks the hyphenation
 * and quote rules, it is what a screen reader chooses a voice from, and `:lang()` selectors and
 * font fallback hang off it. It was hard-coded to "en" in index.html and never touched again.
 */
export function applyLang() {
  try { document.documentElement.lang = locale() } catch { /* no document: a test, and nothing to set */ }
}

/*
 * The languages This hub offers. Deliberately a short list and not the ~70 Home Assistant has:
 * a picker with seventy rows on a wall panel is a worse answer than a picker with fifteen and a
 * hub that takes whatever the browser asked for. Anything else still works -- the brain accepts
 * any well-formed tag, and first run sets one straight from the device without consulting this
 * list at all. This is for the household that wants to change its mind afterwards.
 *
 * The name is written in the language itself, because somebody looking for their own language is
 * not reading the one they are trying to leave.
 */
export const LANGUAGES: { code: string; name: string }[] = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Español' },
  { code: 'fr', name: 'Français' },
  { code: 'de', name: 'Deutsch' },
  { code: 'it', name: 'Italiano' },
  { code: 'nl', name: 'Nederlands' },
  { code: 'pt', name: 'Português' },
  { code: 'pt-BR', name: 'Português (Brasil)' },
  { code: 'pl', name: 'Polski' },
  { code: 'sv', name: 'Svenska' },
  { code: 'nb', name: 'Norsk bokmål' },
  { code: 'da', name: 'Dansk' },
  { code: 'fi', name: 'Suomi' },
  { code: 'cs', name: 'Čeština' },
  { code: 'tr', name: 'Türkçe' },
  { code: 'ru', name: 'Русский' },
  { code: 'zh-Hans', name: '简体中文' },
  { code: 'ja', name: '日本語' },
  { code: 'ko', name: '한국어' },
]

/** What to call a tag on screen: the list's name where there is one, else the tag itself. */
export function languageName(code: string | null | undefined): string {
  if (!code) return 'English'
  const known = LANGUAGES.find(l => l.code.toLowerCase() === code.toLowerCase())
  if (known) return known.name
  // A tag nobody put on the list -- set by a browser, or typed by someone who knew what they wanted.
  // Intl can usually name it in itself, and saying the tag back is a poor second but never wrong.
  try { return new Intl.DisplayNames([code], { type: 'language' }).of(code) || code } catch { return code }
}
