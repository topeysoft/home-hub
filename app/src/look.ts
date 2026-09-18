// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/*
 * What the house looks like, as one choice instead of four.
 *
 * The Look page used to ask four questions -- an arrangement for Home, where the
 * way around lives, what the panel is made of, and a tone for the cards. Three
 * by two by two by four is forty-eight answers, and nobody outside this repo
 * knows what "Rail, Top, Glass, Pastel" will look like until they have built it
 * by trial. A person who wants the house to look nice should not have to hold a
 * four-dimensional space in their head to get there.
 *
 * So the four split in two, along a line that was already there:
 *
 *   TASTE -- what it is made of, and which way the cards lean. Nobody can answer
 *   this for you, so it stays a question. It is asked once, as three whole
 *   looks, each of which is a place you would actually want to be.
 *
 *   PLACE -- how Home is arranged and where the way around lives. Read the hints
 *   in layout.ts: "reads well on a phone", "made for a wall", "read from across
 *   a room". That was never taste. It is a fact about the screen, and the screen
 *   already knows it, so it stops being a question and becomes placeOf() below.
 *
 * This is the one thing in the panel that is NOT the same on every screen, and
 * that is not a retreat from "the house decides, not the screen" -- it is what
 * that rule meant all along. Two screens disagreeing about their TASTE is a bug:
 * one house, one feel, and LookPage still writes the feel to the hub so it lands
 * everywhere at once. Two screens disagreeing about their ARRANGEMENT is a phone
 * being a phone. The same look, cut to fit what it is being shown on.
 */

import type { FaceName, LayoutName, NavName } from './layout'
import type { ToneName } from './tone'

export type FeelName = 'calm' | 'daylight' | 'nightfall'

export type Feel = {
  id: FeelName
  label: string
  hint: string
  face: FaceName
  tone: ToneName
}

/*
 * Three, and the case for each one is that it is somewhere to be rather than a
 * setting. What decided this particular three was the picker itself: these are
 * shown live, side by side, at whatever hour you happen to open the page, so any
 * two that can ever look the same are a bad pair no matter how well they read on
 * paper. Cosy -- warm on paper -- was the obvious third and had to go for exactly
 * that reason: `follow` IS warm after sunset, so from dusk to dawn Cosy and Calm
 * were the same picture twice and the page was asking people to choose between
 * two identical things. Pastel cannot collide with either: it holds dL .335 off
 * the sky where the others hold .135, so it is visibly the lighter one at
 * midnight as well as at noon.
 *
 * So: two ends of the light on paper, and the other material. `warm` and `cool`
 * are still there under Customise, which is the honest place for a tone whose
 * whole character is that it ignores the hour.
 */
export const FEELS: Feel[] = [
  { id: 'calm', label: 'Calm', hint: 'Paper cards laid on the sky, following the light through the day.', face: 'paper', tone: 'follow' },
  { id: 'daylight', label: 'Daylight', hint: 'Light and open at every hour, the way a room is with the curtains back.', face: 'paper', tone: 'pastel' },
  { id: 'nightfall', label: 'Nightfall', hint: 'The same house behind frosted panes, with the sky moving through them.', face: 'glass', tone: 'follow' },
]

export const DEFAULT_FEEL: FeelName = 'calm'

export function isFeel(v: unknown): v is FeelName {
  return v === 'calm' || v === 'daylight' || v === 'nightfall'
}

export function feelOf(v: unknown): Feel {
  return FEELS.find(f => f.id === v) ?? FEELS[0]
}

/*
 * Which feel a house is on, read from the whole look rather than from the one
 * key that names it.
 *
 * The naming key is the fragile one. A hub drops what it has never heard of --
 * that is the whole point of LOOK in api.py, and it is the right behaviour --
 * so a panel from this branch talking to a hub that has not been updated yet
 * sends "feel" and gets back a look with no feel in it. Read only that key and
 * every pick on the Look page snaps straight back to Calm, for no reason anybody
 * looking at the screen could work out. Hubs update on their own schedule; a
 * panel that is unusable until they do is a panel that is broken.
 *
 * It does not need that key, because a feel IS a face and a tone. Those two have
 * been in the vocabulary for as long as the faces have, so they come back from
 * any hub, and the feel falls out of them. The key stays -- it is what makes a
 * feel survive a future where two of them share a face and a tone -- but nothing
 * depends on it any more.
 */
export function feelFrom(look: { feel?: string; face?: string; tone?: string } | null | undefined): Feel {
  const named = FEELS.find(f => f.id === look?.feel)
  if (named) return named
  const made = FEELS.find(f => f.face === (look?.face ?? 'paper') && f.tone === (look?.tone ?? 'follow'))
  return made ?? FEELS[0]
}

/*
 * Where this screen is, read off how wide it is, because that is the only thing
 * a browser will tell us about the room it is in. The seam at 861 is the panel's
 * one real breakpoint -- panel.css turns on the whole of its wall behaviour
 * there -- and 1280 is where a screen stops being something you stand in front
 * of and starts being something you read from the sofa.
 *
 * A phone keeps the side rail on purpose: under 861 it already folds into a
 * strip across the top, so "side" on a phone is not a list down the left, and
 * swapping it for tabs here would be a redesign wearing a preset's clothes.
 */
export const TOUCHED_AT = 861      // a tablet on a wall, within arm's reach
export const READ_AT = 1280        // a big screen, read from across the room

export type Place = { layout: LayoutName; nav: NavName }

export function placeOf(width: number): Place {
  if (width >= READ_AT) return { layout: 'wall', nav: 'top' }
  if (width >= TOUCHED_AT) return { layout: 'rail', nav: 'top' }
  return { layout: 'stack', nav: 'side' }
}

/* what the hub holds once a feel is picked: the taste spelled out, so an older
   panel that has never heard of a feel still gets a face and a tone it knows,
   and the arrangement handed back to the screen */
export function lookOf(feel: FeelName): { feel: FeelName; face: FaceName; tone: ToneName; layout: string; nav: string } {
  const f = feelOf(feel)
  return { feel: f.id, face: f.face, tone: f.tone, layout: 'auto', nav: 'auto' }
}

/*
 * Has someone been under Customise? Only worth asking so the page can say
 * "Calm, adjusted" instead of quietly showing Calm as chosen while the panel
 * looks like something else. A house that set its look by hand before feels
 * existed lands here too, and that is right: it IS adjusted, and nothing it
 * chose gets taken away.
 */
export function adjusted(look: Record<string, any> | undefined | null): boolean {
  if (!look) return false
  const want = lookOf(feelFrom(look).id)
  return (['face', 'tone', 'layout', 'nav'] as const).some(k => look[k] != null && look[k] !== want[k])
}
