# SPDX-FileCopyrightText: 2026 Temitope Adeyeri
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Run from brain/: .venv/bin/python -m unittest -v.

What a phone is allowed to keep. A home screen app on iOS keeps its own copy, in its own store,
separate from the same phone's Safari, and nothing on the wall can clear it -- so the hub has to be
explicit about what may be reused and what has to be checked. Left unsaid, a browser guesses, and the
icon opens a build the hub stopped serving days ago.
"""
import unittest

from tests.apptest import ApiTest


class PanelCachingTests(ApiTest):
    def test_the_page_itself_is_never_reused_without_asking(self):
        # index.html names the build's hashed files. A stale copy of it points at a build that is gone,
        # which is the whole bug: no-cache still keeps the copy, it just has to revalidate first.
        r = self.client.get("/")
        self.assertEqual(r.headers.get("Cache-Control"), "no-cache")

    def test_hashed_files_are_kept_for_good(self):
        r = self.client.get("/assets/index-abc123.js")
        self.assertEqual(r.headers.get("Cache-Control"), "public, max-age=31536000, immutable")

    def test_a_route_that_asked_for_something_else_keeps_it(self):
        # The QR wants a day, camera frames want no-store. The default must not overwrite either.
        r = self.client.get("/qr.svg", params={"text": "http://hub.local"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers.get("Cache-Control"), "max-age=86400")

    def test_house_state_is_checked_every_time(self):
        # Not the reported bug, but the same cause: no header at all let a browser reuse these too.
        self.assertEqual(self.client.get("/home").headers.get("Cache-Control"), "no-cache")


if __name__ == "__main__":
    unittest.main()
