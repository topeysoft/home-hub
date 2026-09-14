package app.elyir.kiosk

import android.app.admin.DeviceAdminReceiver

/**
 * Only so that `adb shell dpm set-device-owner app.elyir.kiosk/.Admin` has something to name, on a
 * tablet being set up as a wall panel for good. With it, the kiosk pins itself properly and there
 * is no way out but the corner. Without it, everything still works. See the README.
 */
class Admin : DeviceAdminReceiver()
