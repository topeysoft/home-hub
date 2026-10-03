// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The houses, in IndexedDB rather than localStorage: Safari may clear localStorage for a Home Screen app, and
   this list is the one thing the app has that nobody else keeps (the printer app learned it first). */
const DB = 'houses', STORE = 'houses'

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const r = indexedDB.open(DB, 1)
    r.onupgradeneeded = () => { if (!r.result.objectStoreNames.contains(STORE)) r.result.createObjectStore(STORE, { keyPath: 'id' }) }
    r.onsuccess = () => resolve(r.result)
    r.onerror = () => reject(r.error)
  })
}

function tx<T>(mode: IDBTransactionMode, run: (s: IDBObjectStore) => IDBRequest): Promise<T> {
  return open().then(db => new Promise<T>((resolve, reject) => {
    const req = run(db.transaction(STORE, mode).objectStore(STORE))
    req.onsuccess = () => resolve(req.result as T)
    req.onerror = () => reject(req.error)
  }))
}

export const all = <T>() => tx<T[]>('readonly', s => s.getAll())
export const put = (v: unknown) => tx<IDBValidKey>('readwrite', s => s.put(v))
export const del = (id: string) => tx<undefined>('readwrite', s => s.delete(id))
