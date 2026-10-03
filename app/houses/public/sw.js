// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
/* The Houses app's worker. Nothing is cached: every house is live or it is not, and an app that showed a
   house from yesterday would be worse than one that says it cannot reach it. It is here for what comes
   next -- one notification key for every house, the way the printer app does it (docs/away.md, step 6). */
self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()))
