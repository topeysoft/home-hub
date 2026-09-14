package app.elyir.kiosk

import android.content.Context

/** The two things this wall remembers: an address someone typed, and the one that last worked. */
object Prefs {

    private fun store(ctx: Context) = ctx.getSharedPreferences("wall", Context.MODE_PRIVATE)

    /** What someone typed on the sheet, tidied into a base url. Empty means: find it yourself. */
    fun address(ctx: Context): String? = tidy(raw(ctx))

    fun raw(ctx: Context): String? = store(ctx).getString("address", null)?.ifBlank { null }

    fun setAddress(ctx: Context, typed: String?) {
        store(ctx).edit().apply {
            if (typed.isNullOrBlank()) remove("address") else putString("address", typed.trim())
        }.apply()
    }

    fun lastGood(ctx: Context): String? = store(ctx).getString("last", null)

    fun remember(ctx: Context, base: String) {
        store(ctx).edit().putString("last", base).apply()
    }

    /** `hub.local`, `hub.local:8300`, `http://10.0.0.4` and `http://hub.local/` all mean one thing. */
    fun tidy(typed: String?): String? {
        val t = typed?.trim()?.trimEnd('/') ?: return null
        if (t.isEmpty()) return null
        return if (t.startsWith("http://") || t.startsWith("https://")) t else "http://$t"
    }
}
