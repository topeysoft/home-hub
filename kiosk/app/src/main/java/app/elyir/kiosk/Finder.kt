// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
package app.elyir.kiosk

import android.content.Context
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Finding the house from the wall.
 *
 * A browser on a tablet often cannot resolve `hub.local` at all — Android's resolver only learned
 * mDNS recently and plenty of wall tablets are older than that. This is most of the reason the
 * kiosk is native code: it can ask the network the way a phone's Bonjour does, and hand the web
 * view a plain address that always works.
 *
 * The order is: the address someone typed, then the one that worked last time, then `hub.local`
 * for the tablets that can, then the network itself. Whatever answers `/phones/me` the way the
 * brain does is the house; nothing else on the Wi-Fi can pretend to be it by accident.
 */
object Finder {

    private const val PROBE_MS = 2500
    private const val BROWSE_MS = 6000L
    private const val OURS = "_home-hub._tcp."
    private const val ANY_HTTP = "_http._tcp."

    /** Blocking. Runs on the wall's background thread; `say` reports progress for the waiting screen. */
    fun find(ctx: Context, say: (String) -> Unit): String? {
        for (base in known(ctx)) {
            say(plainly(base))
            if (answers(base)) return base
        }
        say("asking the network")
        for (base in onTheNetwork(ctx)) if (answers(base)) return base
        return null
    }

    private fun known(ctx: Context): List<String> {
        val out = LinkedHashSet<String>()
        Prefs.address(ctx)?.let { out += it }
        Prefs.lastGood(ctx)?.let { out += it }
        out += "http://hub.local"
        return out.toList()
    }

    /**
     * The brain, and not merely something on port 80.
     *
     * `/phones/me` and not `/health`: a house with a code on it turns away every route but a
     * handful, and a wall that has not joined yet is a stranger like any other. This is the one
     * that answers whatever state the house is in — locked, open, joined or not — which is what a
     * thing looking for a house needs.
     */
    fun answers(base: String): Boolean = try {
        val c = (URL("$base/phones/me").openConnection() as HttpURLConnection).apply {
            connectTimeout = PROBE_MS
            readTimeout = PROBE_MS
            instanceFollowRedirects = true
            setRequestProperty("Accept", "application/json")
        }
        try {
            c.responseCode == 200 &&
                c.inputStream.bufferedReader().use { it.readText() }.take(400).contains("\"paired\"")
        } finally {
            c.disconnect()
        }
    } catch (_: Exception) {
        false
    }

    /** Every hub-shaped thing mDNS will admit to, best guess first. */
    private fun onTheNetwork(ctx: Context): List<String> {
        val nsd = ctx.getSystemService(Context.NSD_SERVICE) as? NsdManager ?: return emptyList()
        val wifi = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as? WifiManager
        val multicast = try {
            wifi?.createMulticastLock("elyir-kiosk")?.apply { setReferenceCounted(true); acquire() }
        } catch (_: Exception) {
            null
        }
        try {
            val found = LinkedHashSet<String>()
            for (type in listOf(OURS, ANY_HTTP)) {
                for (service in browse(nsd, type)) {
                    val full = resolve(nsd, service) ?: continue
                    val host = full.host?.hostAddress ?: continue
                    val ours = type == OURS ||
                        listOf(full.serviceName, full.host?.hostName ?: "").any { it.contains("hub", true) }
                    if (ours) found += address(host, full.port)
                }
                if (found.isNotEmpty()) break          // our own service type wins outright
            }
            return found.toList()
        } finally {
            try { multicast?.release() } catch (_: Exception) {}
        }
    }

    private fun browse(nsd: NsdManager, type: String): List<NsdServiceInfo> {
        val seen = ArrayList<NsdServiceInfo>()
        val listener = object : NsdManager.DiscoveryListener {
            override fun onDiscoveryStarted(t: String) {}
            override fun onDiscoveryStopped(t: String) {}
            override fun onStartDiscoveryFailed(t: String, code: Int) {}
            override fun onStopDiscoveryFailed(t: String, code: Int) {}
            override fun onServiceFound(s: NsdServiceInfo) { synchronized(seen) { seen += s } }
            override fun onServiceLost(s: NsdServiceInfo) {}
        }
        return try {
            nsd.discoverServices(type, NsdManager.PROTOCOL_DNS_SD, listener)
            Thread.sleep(BROWSE_MS)
            try { nsd.stopServiceDiscovery(listener) } catch (_: Exception) {}
            synchronized(seen) { ArrayList(seen) }
        } catch (_: Exception) {
            emptyList()
        }
    }

    @Suppress("DEPRECATION")     // the callback that replaces it is API 34; wall tablets are older
    private fun resolve(nsd: NsdManager, service: NsdServiceInfo): NsdServiceInfo? {
        val out = arrayOfNulls<NsdServiceInfo>(1)
        val done = CountDownLatch(1)
        try {
            nsd.resolveService(service, object : NsdManager.ResolveListener {
                override fun onResolveFailed(s: NsdServiceInfo, code: Int) { done.countDown() }
                override fun onServiceResolved(s: NsdServiceInfo) { out[0] = s; done.countDown() }
            })
        } catch (_: Exception) {
            return null
        }
        done.await(4, TimeUnit.SECONDS)
        return out[0]
    }

    internal fun address(host: String, port: Int): String =
        if (port <= 0 || port == 80) "http://$host" else "http://$host:$port"

    private fun plainly(base: String) = base.removePrefix("http://").removePrefix("https://")
}
