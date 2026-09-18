// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
package app.elyir.kiosk

import android.app.Activity
import android.app.AlertDialog
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.Uri
import android.net.http.SslError
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.MotionEvent
import android.view.View
import android.view.ViewConfiguration
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.SslErrorHandler
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.EditText
import android.widget.TextView
import androidx.core.view.WindowCompat
import androidx.core.view.WindowInsetsCompat
import androidx.core.view.WindowInsetsControllerCompat
import java.util.concurrent.Executors
import kotlin.math.abs

/**
 * The wall.
 *
 * A tablet with this installed as its home screen is not a tablet with a website open: it comes up
 * on the panel after a power cut, it stays awake, it has no browser chrome to escape into, and the
 * home button leads back to the house rather than away from it. The only way out is a corner held
 * for three seconds, which nobody finds by accident.
 *
 * It draws nothing of its own except the screen it shows while it is looking for the house. The
 * panel comes from the hub, so the wall is never a version behind it.
 */
class Wall : Activity() {

    private companion object {
        const val BEAT = 30_000L          // how often a showing wall checks the house is still there
        const val HOLD = 3_000L           // how long the corner has to be held before the way out opens
        const val CORNER = 80             // dp square, top left: the clock's corner, which has no control in it
    }

    private val ui = Handler(Looper.getMainLooper())
    private val work = Executors.newSingleThreadExecutor()

    private lateinit var web: WebView
    private lateinit var waiting: View
    private lateinit var line: TextView
    private lateinit var hint: TextView

    private var showing: String? = null
    private var looking = false
    private var misses = 0
    private var unanswered = 0

    private val whenTheNetworkComesBack = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            ui.post { if (showing == null) look() }
        }
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        stayAwake()
        setContentView(R.layout.wall)

        web = findViewById(R.id.web)
        waiting = findViewById(R.id.waiting)
        line = findViewById(R.id.line)
        hint = findViewById(R.id.hint)

        dress(web)
        watchTheNetwork()
        look()
        ui.postDelayed(heartbeat, BEAT)
    }

    override fun onResume() {
        super.onResume()
        fullScreen()
        pin()
        if (showing == null) look()
    }

    override fun onWindowFocusChanged(has: Boolean) {
        super.onWindowFocusChanged(has)
        if (has) fullScreen()
    }

    /** Back goes back through the panel, and never out of it. */
    @Suppress("DEPRECATION", "MissingSuperCall")
    override fun onBackPressed() {
        if (web.canGoBack()) web.goBack()
    }

    override fun onDestroy() {
        ui.removeCallbacks(heartbeat)
        ui.removeCallbacks(opening)
        try {
            (getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager)
                .unregisterNetworkCallback(whenTheNetworkComesBack)
        } catch (_: Exception) {
        }
        work.shutdownNow()
        super.onDestroy()
    }

    /**
     * The panel repairs its own stream after a short drop, so this waits out anything brief. Two
     * minutes of a house not answering is a hub that went away — a power cut, a new address, an
     * update — and the wall says so and starts looking again. Coming back reloads the page, so a
     * hub that restarted on a new build hands over a new panel.
     */
    private val heartbeat = object : Runnable {
        override fun run() {
            val base = showing
            if (base != null) work.execute {
                val ok = Finder.answers(base)
                ui.post {
                    if (showing != base) return@post
                    if (ok) unanswered = 0
                    else if (++unanswered >= 4) { unanswered = 0; lost("the house stopped answering") }
                }
            }
            ui.postDelayed(this, BEAT)
        }
    }

    // ---------- finding the house ----------

    private fun look() {
        if (looking) return
        looking = true
        if (showing == null) waiting.visibility = View.VISIBLE
        line.setText(R.string.looking)
        work.execute {
            val found = Finder.find(this) { word -> ui.post { hint.text = word } }
            ui.post {
                looking = false
                if (found != null) {
                    misses = 0
                    unanswered = 0
                    Prefs.remember(this, found)
                    show(found)
                } else {
                    misses++
                    line.setText(R.string.looking)
                    hint.text = "not answering yet — trying again"
                    ui.postDelayed({ look() }, again())
                }
            }
        }
    }

    /** 3 seconds, then 5, 10, 20, and half a minute forever after. A wall has all night. */
    private fun again(): Long = when (misses) {
        1 -> 3_000
        2 -> 5_000
        3 -> 10_000
        4 -> 20_000
        else -> 30_000
    }

    private fun show(base: String) {
        if (showing == base) {
            web.reload()
        } else {
            showing = base
            web.loadUrl("$base/")
        }
    }

    private fun lost(why: String) {
        showing = null
        hint.text = why
        waiting.visibility = View.VISIBLE
        if (!looking) ui.postDelayed({ look() }, 1_500)
    }

    // ---------- the web view is the panel, and nothing else ----------

    private fun dress(web: WebView) {
        CookieManager.getInstance().setAcceptCookie(true)          // the phone cookie lives here
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true)

        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            mediaPlaybackRequiresUserGesture = false               // a sound a rule started just plays
            useWideViewPort = true
            loadWithOverviewMode = true
            setSupportZoom(false)
            builtInZoomControls = false
            displayZoomControls = false
            textZoom = 100
            userAgentString = "$userAgentString Elyir-Kiosk/${BuildConfig.VERSION_NAME}"
        }
        web.isLongClickable = false
        web.setOnLongClickListener { true }                        // no selection handles on a wall
        web.overScrollMode = View.OVER_SCROLL_NEVER
        web.isVerticalScrollBarEnabled = false
        web.isHorizontalScrollBarEnabled = false
        web.setBackgroundColor(getColor(R.color.ground))

        web.webViewClient = object : WebViewClient() {
            /**
             * The wall opens nothing that is not this box. The Advanced door — Home Assistant's own
             * UI on :8123 — is this box, so it still opens; the whole of the rest of the internet
             * is not, and a tap on it does nothing at all.
             */
            override fun shouldOverrideUrlLoading(v: WebView, r: WebResourceRequest): Boolean =
                !sameHouse(r.url)

            override fun onPageFinished(v: WebView, url: String) {
                if (showing != null) waiting.visibility = View.GONE
            }

            override fun onReceivedError(v: WebView, r: WebResourceRequest, e: WebResourceError) {
                if (r.isForMainFrame) lost("the house stopped answering")
            }

            override fun onReceivedSslError(v: WebView, handler: SslErrorHandler, e: SslError) {
                handler.cancel()                                   // the wall's path is plain http
            }
        }
    }

    private fun sameHouse(url: Uri): Boolean {
        val house = Uri.parse(showing ?: return false).host ?: return false
        return url.host == house
    }

    // ---------- being a wall and not a tablet ----------

    private fun stayAwake() {
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON or
                    WindowManager.LayoutParams.FLAG_DISMISS_KEYGUARD
            )
        }
    }

    private fun fullScreen() {
        WindowCompat.setDecorFitsSystemWindows(window, false)
        WindowInsetsControllerCompat(window, web).apply {
            hide(WindowInsetsCompat.Type.systemBars())
            systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
        }
    }

    /** With device owner set, the wall pins itself and the status bar goes for good. Without, this does nothing. */
    private fun pin() {
        val dpm = getSystemService(Context.DEVICE_POLICY_SERVICE) as? DevicePolicyManager ?: return
        if (!dpm.isDeviceOwnerApp(packageName)) return
        val admin = ComponentName(this, Admin::class.java)
        try {
            dpm.setLockTaskPackages(admin, arrayOf(packageName))
            dpm.setKeyguardDisabled(admin, true)
            dpm.setStatusBarDisabled(admin, true)
            if (!isInLockTask()) startLockTask()
        } catch (_: Exception) {
        }
    }

    private fun isInLockTask(): Boolean {
        val am = getSystemService(Context.ACTIVITY_SERVICE) as android.app.ActivityManager
        return am.lockTaskModeState != android.app.ActivityManager.LOCK_TASK_MODE_NONE
    }

    private fun watchTheNetwork() {
        try {
            (getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager)
                .registerDefaultNetworkCallback(whenTheNetworkComesBack)
        } catch (_: Exception) {
        }
    }

    // ---------- the corner ----------

    /**
     * The way out: the top left corner — the clock's corner, where the panel has nothing to press —
     * held for three seconds. Nobody finds it by accident and a guest does not find it at all.
     *
     * It watches the touch without taking it. A kiosk that swallowed the corner would swallow
     * whatever the panel later puts there, and the house would stop answering a tap it should have.
     */
    private var holding = false
    private var from = 0f to 0f
    private val opening = Runnable { holding = false; sheet() }

    override fun dispatchTouchEvent(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> if (inTheCorner(event.x, event.y)) {
                holding = true
                from = event.x to event.y
                ui.postDelayed(opening, HOLD)
            }
            MotionEvent.ACTION_MOVE -> if (holding && wandered(event)) letGo()
            MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> letGo()
        }
        return super.dispatchTouchEvent(event)
    }

    private fun inTheCorner(x: Float, y: Float): Boolean {
        val side = CORNER * resources.displayMetrics.density
        return x <= side && y <= side
    }

    private fun wandered(event: MotionEvent): Boolean {
        val slop = ViewConfiguration.get(this).scaledTouchSlop * 2
        return abs(event.x - from.first) > slop || abs(event.y - from.second) > slop
    }

    private fun letGo() {
        if (!holding) return
        holding = false
        ui.removeCallbacks(opening)
    }

    private fun sheet() {
        val view = layoutInflater.inflate(R.layout.sheet, null)
        val address = view.findViewById<EditText>(R.id.address)
        address.setText(Prefs.raw(this) ?: "")
        view.findViewById<TextView>(R.id.showing).text =
            showing?.let { "Showing ${it.removePrefix("http://")}" } ?: "Not showing the house yet"

        val dialog = AlertDialog.Builder(this)
            .setView(view)
            .setPositiveButton(R.string.use) { _, _ ->
                Prefs.setAddress(this, address.text.toString())
                showing = null
                misses = 0
                look()
            }
            .setNeutralButton(R.string.reload) { _, _ -> if (showing != null) web.reload() else look() }
            .setNegativeButton(R.string.leave) { _, _ -> leave() }
            .create()

        // Open it without letting the system bars back in on the way.
        dialog.window?.setFlags(
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE
        )
        dialog.setOnDismissListener { fullScreen() }
        dialog.show()
        dialog.window?.let { w ->
            WindowInsetsControllerCompat(w, w.decorView).apply {
                hide(WindowInsetsCompat.Type.systemBars())
                systemBarsBehavior = WindowInsetsControllerCompat.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE
            }
            w.clearFlags(WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE)
        }
    }

    private fun leave() {
        try { if (isInLockTask()) stopLockTask() } catch (_: Exception) {}
        try {
            startActivity(Intent(Settings.ACTION_HOME_SETTINGS))
        } catch (_: Exception) {
            try { startActivity(Intent(Settings.ACTION_SETTINGS)) } catch (_: Exception) {}
        }
    }
}
