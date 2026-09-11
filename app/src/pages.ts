/* The pages of This house, and the store.sheet values that open the panel on
   one of them. 'house' is the panel's own front page. See HousePanel.vue. */
export type PageId = 'house' | 'location' | 'look' | 'routines' | 'people' | 'add' | 'hub' | 'code'
export const PAGES: PageId[] = ['house', 'location', 'look', 'routines', 'people', 'add', 'hub', 'code']
export const isPage = (v: unknown): v is PageId => (PAGES as unknown[]).includes(v)
