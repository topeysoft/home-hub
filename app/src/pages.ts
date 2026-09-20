// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The pages of This house, and the store.sheet values that open the panel on
   one of them. 'house' is the panel's own front page. See HousePanel.vue. */
export type PageId = 'house' | 'location' | 'look' | 'routines' | 'people' | 'accounts' | 'add' | 'share' | 'hub' | 'code' | 'notes' | 'happened' | 'changes'
export const PAGES: PageId[] = ['house', 'location', 'look', 'routines', 'people', 'accounts', 'add', 'share', 'hub', 'code', 'notes', 'happened', 'changes']
/* 'changes' has no door of its own: it is reached from inside What happened, and the door for that
   one stays lit while it is open. LIT says which door a page belongs to where it is not itself one. */
export const LIT: Partial<Record<PageId, PageId>> = { changes: 'happened' }
export const isPage = (v: unknown): v is PageId => (PAGES as unknown[]).includes(v)
