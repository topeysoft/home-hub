// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
package app.elyir.kiosk

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * A wall tablet that kept its own launcher still comes back to the panel after a power cut.
 * When this app is the home screen the system has already done it, and this does nothing.
 */
class Boot : BroadcastReceiver() {
    override fun onReceive(ctx: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED) return
        ctx.startActivity(
            Intent(ctx, Wall::class.java).addFlags(
                Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK
            )
        )
    }
}
