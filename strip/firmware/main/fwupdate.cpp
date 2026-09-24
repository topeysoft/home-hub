// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
#include "fwupdate.h"

#include <string.h>

#include <atomic>

#include "esp_http_client.h"
#include "esp_log.h"
#include "esp_ota_ops.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "nvs.h"
#include "psa/crypto.h"

#include "versions.h"

namespace fwupdate {

static const char *TAG = "update";

// How long a new image has to prove itself. A strip's first boot joins the Wi-Fi and then looks for
// the hub by name, and a router that is slow to answer at three in the morning must not read as a
// broken image. A false rollback costs a night; a strip nobody can reach costs a ladder.
static const int64_t TRIAL_MS = 180000;
static const uint8_t GIVE_UP_AFTER = 2;     // the puck's number, and the hub's TRIES

static Say g_say = nullptr;
static nvs_handle_t nv = 0;
static bool g_trial = false;
static int64_t g_trial_from = 0;
static char g_owed[160] = "";               // said once the broker is up: a rollback, from the last boot
static std::atomic<bool> g_busy{false};     // a download is running

struct Offer { char fw[24]; char sha[65]; char path[96]; char host[64]; uint32_t size; uint16_t port; };
static Offer g_offer;

static int64_t now_ms() { return esp_timer_get_time() / 1000; }

static std::string nv_str(const char *key) {
    size_t n = 0;
    if (nvs_get_str(nv, key, nullptr, &n) != ESP_OK || n == 0) return "";
    std::string s(n, '\0');
    nvs_get_str(nv, key, s.data(), &n);
    s.resize(n ? n - 1 : 0);
    return s;
}

static void nv_put(const char *key, const char *value) { nvs_set_str(nv, key, value); nvs_commit(nv); }
static void nv_drop(const char *key) { nvs_erase_key(nv, key); nvs_commit(nv); }

static void say(const char *state, const char *fw, const char *why) {
    char j[160];
    snprintf(j, sizeof(j), "{\"state\":\"%s\",\"fw\":\"%s\",\"why\":\"%s\"}", state, fw ? fw : "", why ? why : "");
    ESP_LOGI(TAG, "%s", j);
    if (g_say) g_say("update", j, 0);
}

void begin(Say s) {
    g_say = s;
    nvs_open("update", NVS_READWRITE, &nv);

    // What happened the last time we restarted for an image. `try` names the version we went to; if we
    // are not it, the bootloader brought us back.
    const std::string tried = nv_str("try");
    if (!tried.empty() && tried != STRIP_FW) {
        uint8_t n = 0;
        if (nv_str("bad") == tried) nvs_get_u8(nv, "badn", &n);
        nv_put("bad", tried.c_str());
        nvs_set_u8(nv, "badn", n + 1);
        nv_drop("try");
        snprintf(g_owed, sizeof(g_owed), "{\"state\":\"rolledback\",\"fw\":\"%s\",\"why\":\"%u\"}",
                 tried.c_str(), (unsigned)(n + 1));
        ESP_LOGW(TAG, "%s did not prove itself; this is the image from before it", tried.c_str());
    }

    esp_ota_img_states_t st;
    const esp_partition_t *running = esp_ota_get_running_partition();
    if (running && esp_ota_get_state_partition(running, &st) == ESP_OK && st == ESP_OTA_IMG_PENDING_VERIFY) {
        g_trial = true;
        g_trial_from = now_ms();
        ESP_LOGI(TAG, STRIP_FW " is on trial: %lld s to reach the hub", (long long)(TRIAL_MS / 1000));
    }
}

static void fetch(void *) {
    Offer o = g_offer;
    esp_http_client_config_t c = {};
    c.host = o.host;
    c.port = o.port;
    c.path = o.path;
    c.transport_type = HTTP_TRANSPORT_OVER_TCP;
    c.timeout_ms = 15000;
    c.disable_auto_redirect = true;
    esp_http_client_handle_t http = esp_http_client_init(&c);
    esp_ota_handle_t ota = 0;
    const esp_partition_t *next = esp_ota_get_next_update_partition(nullptr);
    psa_hash_operation_t hash = PSA_HASH_OPERATION_INIT;
    static uint8_t buf[4096];
    uint32_t got = 0;
    const char *why = nullptr;

    say("fetching", o.fw, "");
    if (!http || esp_http_client_open(http, 0) != ESP_OK) why = "connect";
    else if (esp_http_client_fetch_headers(http) != (int64_t)o.size) why = "wrong size";
    else if (esp_http_client_get_status_code(http) != 200) why = "http";
    else if (!next || esp_ota_begin(next, o.size, &ota) != ESP_OK) why = "no slot";
    else if (psa_crypto_init() != PSA_SUCCESS || psa_hash_setup(&hash, PSA_ALG_SHA_256) != PSA_SUCCESS) why = "hash";
    while (!why && got < o.size) {
        const int n = esp_http_client_read(http, (char *)buf, sizeof(buf));
        if (n <= 0) { why = "short"; break; }
        // Hashed exactly as it is written, so there is no second read of the slot to disagree with.
        if (psa_hash_update(&hash, buf, n) != PSA_SUCCESS || esp_ota_write(ota, buf, n) != ESP_OK) why = "write";
        got += n;
    }
    if (http) { esp_http_client_close(http); esp_http_client_cleanup(http); }

    uint8_t digest[32];
    size_t dlen = 0;
    if (!why && (psa_hash_finish(&hash, digest, sizeof(digest), &dlen) != PSA_SUCCESS || dlen != 32)) why = "hash";
    if (!why) {
        char hex[65];
        for (int i = 0; i < 32; i++) snprintf(hex + i * 2, 3, "%02x", digest[i]);
        if (strcmp(hex, o.sha)) {
            // A refusal, not a fault: this is the strip doing its job.
            psa_hash_abort(&hash);
            if (ota) esp_ota_abort(ota);
            say("refused", o.fw, "hash");
            g_busy = false;
            vTaskDelete(nullptr);
        }
    }
    psa_hash_abort(&hash);
    if (!why && esp_ota_end(ota) != ESP_OK) { ota = 0; why = "not an image"; }
    else if (why && ota) esp_ota_abort(ota);
    if (!why && esp_ota_set_boot_partition(next) != ESP_OK) why = "boot";
    if (why) {
        say("failed", o.fw, why);
        g_busy = false;
        vTaskDelete(nullptr);
    }
    nv_put("try", o.fw);
    ESP_LOGI(TAG, "%s written and checked; restarting into it", o.fw);
    vTaskDelay(pdMS_TO_TICKS(300));
    esp_restart();
}

void offer(const std::string &msg, const std::string &hub_host) {
    if (msg.empty()) return;                                  // withdrawn
    char fw[24], sha[65], path[96];
    unsigned long size = 0, port = 0;
    if (msg.size() > 200 ||
        sscanf(msg.c_str(), "%23s %lu %64s %lu %95s", fw, &size, sha, &port, path) != 5 ||
        strlen(sha) != 64 || !size || !port || port > 65535 || path[0] != '/') {
        say("refused", "", "unreadable");
        return;
    }
    const int vs = version_cmp(fw, STRIP_FW);
    if (vs <= 0) {
        // Not a fault: the hub has an old idea of what we run, and saying it again fixes that.
        if (vs < 0) say("refused", fw, "older");
        if (g_say) g_say("fw", STRIP_FW, 1);
        return;
    }
    const std::string floor = nv_str("floor");
    if (!floor.empty() && version_cmp(fw, floor.c_str()) < 0) { say("refused", fw, "below the floor"); return; }
    if (g_trial) { say("refused", fw, "on trial"); return; }
    uint8_t badn = 0;
    if (nv_str("bad") == fw && nvs_get_u8(nv, "badn", &badn) == ESP_OK && badn >= GIVE_UP_AFTER) {
        say("refused", fw, "came back twice");
        return;
    }
    const esp_partition_t *next = esp_ota_get_next_update_partition(nullptr);
    if (!next || size > next->size) { say("refused", fw, "does not fit"); return; }
    std::string host = hub_host;
    if (host.size() > 2 && host.front() == '[') host = host.substr(1, host.size() - 2);   // a URI's brackets
    if (host.empty() || host.size() >= sizeof(g_offer.host)) { say("failed", fw, "no hub"); return; }
    if (g_busy.exchange(true)) { say("refused", fw, "busy"); return; }

    strlcpy(g_offer.fw, fw, sizeof(g_offer.fw));
    for (int i = 0; i < 65; i++) g_offer.sha[i] = (char)tolower((unsigned char)sha[i]);
    strlcpy(g_offer.path, path, sizeof(g_offer.path));
    strlcpy(g_offer.host, host.c_str(), sizeof(g_offer.host));
    g_offer.size = size;
    g_offer.port = (uint16_t)port;
    if (xTaskCreate(fetch, "update", 6144, nullptr, 4, nullptr) != pdPASS) {
        g_busy = false;
        say("failed", fw, "no task");
    }
}

void tick(bool whole, bool broker_up) {
    if (broker_up && g_owed[0] && g_say) {
        g_say("update", g_owed, 0);
        g_owed[0] = 0;
    }
    if (!g_trial) return;
    if (whole) {
        esp_ota_mark_app_valid_cancel_rollback();
        g_trial = false;
        // The floor only rises, and only on an image that has proved itself.
        const std::string floor = nv_str("floor");
        if (floor.empty() || version_cmp(STRIP_FW, floor.c_str()) > 0) nv_put("floor", STRIP_FW);
        nv_drop("try");
        if (nv_str("bad") == STRIP_FW) { nv_drop("bad"); nv_drop("badn"); }
        say("installed", STRIP_FW, "");
        return;
    }
    if (now_ms() - g_trial_from > TRIAL_MS) {
        ESP_LOGW(TAG, "never reached the hub: going back to the image before");
        esp_ota_mark_app_invalid_rollback_and_reboot();   // returns only if there is nothing to go back to
        g_trial = false;
    }
}

}  // namespace fwupdate
