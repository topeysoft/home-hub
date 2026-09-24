#include "fwupdate.h"
#include "config.h"
#include <HTTPClient.h>
#include <Preferences.h>
#include <Update.h>
#include <WiFi.h>
#include "esp_ota_ops.h"
#include "mbedtls/sha256.h"

// How long a new image has to prove itself. Longer than LINK_DEAD_MS on purpose: the first boot joins
// the Wi-Fi (up to twenty seconds in setup), finds the broker, then hunts for a proxy in six-second
// scans, and a switch that is slow to advertise at three in the morning must not read as a broken
// image. A false rollback costs a night; a stranded puck costs a walk.
#define TRIAL_MS 180000UL
// An image that has come back this many times is not offered again by this puck.
#define GIVE_UP_AFTER 2

static void (*g_publish)(const char *, const char *, bool) = nullptr;
static Preferences nv;

static bool g_trial = false;       // running an image that has not confirmed itself
static uint32_t g_trialFrom = 0;
static char g_owed[160] = "";      // something to say once the broker is up (a rollback, a confirm)

static char g_offer[200];
static volatile bool g_offered = false;
static bool g_ready = false;       // accepted: fw, size, sha, port and path parsed below
static char o_fw[16], o_sha[65], o_path[96];
static uint32_t o_size = 0;
static uint16_t o_port = 0;

// "0.4.1" -> comparable. Anything that is not three numbers is treated as zero, which is older than
// every real version, so a malformed offer is refused rather than taken.
static uint32_t vnum(const char *v) {
    unsigned a = 0, b = 0, c = 0;
    if (!v || sscanf(v, "%u.%u.%u", &a, &b, &c) != 3) return 0;
    return (a << 20) | ((b & 0x3FF) << 10) | (c & 0x3FF);
}

static void say(const char *state, const char *fw, const char *why) {
    char j[160];
    snprintf(j, sizeof(j), "{\"state\":\"%s\",\"fw\":\"%s\",\"why\":\"%s\"}", state, fw ? fw : "", why ? why : "");
    Serial.printf("[update] %s\n", j);
    if (g_publish) g_publish("update", j, false);
}

void update_begin(void (*publish)(const char *, const char *, bool)) {
    g_publish = publish;
    nv.begin("update", false);

    // What happened last time we restarted for an image. `try` is written just before that restart
    // and names the version we went to; if we are not it, the bootloader brought us back.
    String tried = nv.getString("try", "");
    if (tried.length()) {
        if (tried == BRIDGE_FW) {
            // We are the new image. Nothing to say until we have proved ourselves.
        } else {
            uint8_t n = (nv.getString("bad", "") == tried) ? nv.getUChar("badn", 0) : 0;
            nv.putString("bad", tried);
            nv.putUChar("badn", n + 1);
            nv.remove("try");
            snprintf(g_owed, sizeof(g_owed), "{\"state\":\"rolledback\",\"fw\":\"%s\",\"why\":\"%u\"}",
                     tried.c_str(), (unsigned)(n + 1));
        }
    }

    const esp_partition_t *running = esp_ota_get_running_partition();
    esp_ota_img_states_t st;
    if (running && esp_ota_get_state_partition(running, &st) == ESP_OK && st == ESP_OTA_IMG_PENDING_VERIFY) {
        g_trial = true;
        g_trialFrom = millis();
        Serial.printf("[update] %s is on trial: it has %lu s to reach a switch and the hub\n", BRIDGE_FW,
                      TRIAL_MS / 1000);
    }
}

bool update_on_trial() { return g_trial; }

void update_offer(const uint8_t *payload, size_t len) {
    if (len >= sizeof(g_offer)) return;   // not an offer this code wrote
    memcpy(g_offer, payload, len);
    g_offer[len] = 0;
    g_offered = true;
}

// Decide about the offer on the loop, where NVS and the log are safe to touch.
static void consider() {
    g_offered = false;
    g_ready = false;
    if (!g_offer[0]) return;               // withdrawn
    char fw[16], sha[65], path[96];
    unsigned long size = 0, port = 0;
    if (sscanf(g_offer, "%15s %lu %64s %lu %95s", fw, &size, sha, &port, path) != 5 || strlen(sha) != 64 ||
        !size || !port || port > 65535 || path[0] != '/') {
        say("refused", "", "unreadable");
        return;
    }
    uint32_t want = vnum(fw), have = vnum(BRIDGE_FW), floor = vnum(nv.getString("floor", "0.0.0").c_str());
    if (want <= have) {
        // Not a fault: the hub has an old idea of what we run. Saying our version again fixes that.
        if (want != have) say("refused", fw, "older");
        if (g_publish) g_publish("fw", BRIDGE_FW, true);
        return;
    }
    if (want < floor) { say("refused", fw, "below the floor"); return; }
    if (g_trial) { say("refused", fw, "on trial"); return; }   // prove this one first
    if (nv.getString("bad", "") == fw && nv.getUChar("badn", 0) >= GIVE_UP_AFTER) {
        say("refused", fw, "came back twice");
        return;
    }
    const esp_partition_t *next = esp_ota_get_next_update_partition(nullptr);
    if (!next || size > next->size) { say("refused", fw, "does not fit"); return; }
    strlcpy(o_fw, fw, sizeof(o_fw));
    strlcpy(o_sha, sha, sizeof(o_sha));
    for (char *p = o_sha; *p; p++) *p = tolower(*p);
    strlcpy(o_path, path, sizeof(o_path));
    o_size = size;
    o_port = (uint16_t)port;
    g_ready = true;
}

void update_tick(bool whole, bool brokerUp) {
    if (g_offered) consider();
    if (brokerUp && g_owed[0] && g_publish) {
        Serial.printf("[update] %s\n", g_owed);
        g_publish("update", g_owed, false);
        g_owed[0] = 0;
    }
    if (!g_trial) return;
    if (whole) {
        esp_ota_mark_app_valid_cancel_rollback();
        g_trial = false;
        // The floor only ever rises, and only on an image that has proved itself.
        if (vnum(BRIDGE_FW) > vnum(nv.getString("floor", "0.0.0").c_str())) nv.putString("floor", BRIDGE_FW);
        nv.remove("try");
        if (nv.getString("bad", "") == BRIDGE_FW) { nv.remove("bad"); nv.remove("badn"); }
        say("installed", BRIDGE_FW, "");
        return;
    }
    if (millis() - g_trialFrom > TRIAL_MS) {
        Serial.println("[update] never reached a switch and the hub: going back to the image before");
        Serial.flush();
        esp_ota_mark_app_invalid_rollback_and_reboot();   // returns only if there is nothing to go back to
        g_trial = false;                                  // then this is the only image; keep running it
    }
}

bool update_ready() { return g_ready && !g_offered; }

void update_run(const char *hubIp) {
    g_ready = false;
    char fw[16];
    strlcpy(fw, o_fw, sizeof(fw));
    if (!hubIp || !hubIp[0] || WiFi.status() != WL_CONNECTED) { say("failed", fw, "no hub"); return; }
    say("fetching", fw, "");

    WiFiClient net;
    HTTPClient http;
    http.setTimeout(15000);
    http.setFollowRedirects(HTTPC_DISABLE_FOLLOW_REDIRECTS);
    if (!http.begin(net, hubIp, o_port, o_path)) { say("failed", fw, "connect"); return; }
    int code = http.GET();
    if (code != 200) {
        char why[24];
        snprintf(why, sizeof(why), "http %d", code);
        http.end();
        say("failed", fw, why);
        return;
    }
    if (http.getSize() != (int)o_size) { http.end(); say("failed", fw, "wrong size"); return; }
    if (!Update.begin(o_size, U_FLASH)) { http.end(); say("failed", fw, Update.errorString()); return; }

    // The hash is taken over exactly what is written, as it is written, so there is no second read of
    // the slot to disagree with the first.
    mbedtls_sha256_context sha;
    mbedtls_sha256_init(&sha);
    mbedtls_sha256_starts_ret(&sha, 0);
    WiFiClient *in = http.getStreamPtr();
    static uint8_t buf[2048];
    uint32_t got = 0, quietSince = millis();
    while (got < o_size) {
        size_t avail = in->available();
        if (!avail) {
            if (!http.connected() || millis() - quietSince > 15000) break;
            delay(2);
            continue;
        }
        size_t n = in->readBytes(buf, min(avail, min(sizeof(buf), (size_t)(o_size - got))));
        if (!n) continue;
        mbedtls_sha256_update_ret(&sha, buf, n);
        if (Update.write(buf, n) != n) break;
        got += n;
        quietSince = millis();
    }
    http.end();
    uint8_t digest[32];
    mbedtls_sha256_finish_ret(&sha, digest);
    mbedtls_sha256_free(&sha);
    if (got != o_size) { Update.abort(); say("failed", fw, "short"); return; }
    char hex[65];
    for (int i = 0; i < 32; i++) sprintf(hex + i * 2, "%02x", digest[i]);
    if (strcmp(hex, o_sha)) {
        // A refusal, not a fault: this is the puck doing its job.
        Update.abort();
        say("refused", fw, "hash");
        return;
    }
    if (!Update.end()) { say("failed", fw, Update.errorString()); return; }
    nv.putString("try", fw);
    Serial.printf("[update] %s written and checked; restarting into it\n", fw);
    Serial.flush();
    delay(200);
    ESP.restart();
}

// The core confirms every image at boot unless told otherwise (esp32-hal-misc.c). Told otherwise:
// an image confirms itself here, in update_tick(), and only once it has done its job.
// C linkage: the weak default it replaces is declared in a .c file.
extern "C" bool verifyRollbackLater() { return true; }
