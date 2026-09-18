// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The pages of This house, and the store.sheet values that open the panel on
   one of them. 'house' is the panel's own front page. See HousePanel.vue. */
export type PageId = 'house' | 'location' | 'look' | 'routines' | 'people' | 'accounts' | 'add' | 'share' | 'hub' | 'code' | 'notes'
export const PAGES: PageId[] = ['house', 'location', 'look', 'routines', 'people', 'accounts', 'add', 'share', 'hub', 'code', 'notes']
export const isPage = (v: unknown): v is PageId => (PAGES as unknown[]).includes(v)
