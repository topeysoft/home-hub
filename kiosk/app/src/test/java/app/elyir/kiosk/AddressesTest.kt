// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
package app.elyir.kiosk

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** The two places a typed or discovered address turns into one the web view can be handed. */
class AddressesTest {

    @Test fun `a bare name becomes a plain http address`() {
        assertEquals("http://hub.local", Prefs.tidy("hub.local"))
    }

    @Test fun `a port survives`() {
        assertEquals("http://hub.local:8300", Prefs.tidy("hub.local:8300"))
    }

    @Test fun `a trailing slash and stray spaces do not make a second address`() {
        assertEquals("http://10.0.0.4", Prefs.tidy("  http://10.0.0.4/  "))
    }

    @Test fun `https is left as it was typed`() {
        assertEquals("https://hub.local", Prefs.tidy("https://hub.local"))
    }

    @Test fun `nothing typed means find it yourself`() {
        assertNull(Prefs.tidy(null))
        assertNull(Prefs.tidy("   "))
    }

    @Test fun `the front door needs no port on it`() {
        assertEquals("http://192.168.1.9", Finder.address("192.168.1.9", 80))
        assertEquals("http://192.168.1.9", Finder.address("192.168.1.9", 0))
    }

    @Test fun `anything else keeps the port mdns gave`() {
        assertEquals("http://192.168.1.9:8300", Finder.address("192.168.1.9", 8300))
    }
}
