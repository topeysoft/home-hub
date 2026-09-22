// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// See prov.h for why this file exists at all. What follows is the shape of it, because the ordering
// is the part that is easy to get wrong:
//
//   at boot      reserve() builds a GATT service and hands it to CHIP, which merges it in beside
//                CHIPoBLE. The endpoint NAMES are not known yet -- only how many there will be and
//                what their sixteen-bit ids are, which network_provisioning fixes -- so the table is
//                built from ids alone and the names are served later, at read time.
//   later        network_prov_mgr_start_provisioning() calls our prov_start with a live protocomm
//                instance and the name-to-id table it built. Nothing is registered here; the
//                characteristics already exist. All prov_start does is make them answer.
//
// The reason for that split is a hard edge in CHIP: ConfigureExtraServices returns
// CHIP_ERROR_INCORRECT_STATE once its own service list is non-empty, and that happens inside
// esp_matter::start(), long before anybody asks to be provisioned.
#include "prov.h"

#include <cstring>
#include <string>
#include <vector>

#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include <esp_log.h>
#include <esp_random.h>
#include <esp_timer.h>
#include <esp_srp.h>
#include <host/ble_hs.h>
// CHIPDeviceLayer.h first: BLEManagerImpl.h is not self-contained and will not compile without the
// platform types it assumes somebody else has already pulled in.
#include <platform/CHIPDeviceLayer.h>
#include <platform/internal/BLEManager.h>
#include <platform/ESP32/BLEManagerImpl.h>
#include <app/server/Server.h>
#include <protocomm.h>

static const char *TAG = "prov";

namespace prov {
namespace {

// The five endpoints network_provisioning always creates, with the ids it always gives them
// (manager.c). A characteristic is reserved for each at boot; the two spares are for endpoints of
// our own -- the broker details the strip needs and Matter has no words for -- which are added later
// and would otherwise have nowhere to live, because the table cannot grow once Matter has started.
constexpr uint16_t kIds[] = {0xFF4F, 0xFF50, 0xFF51, 0xFF52, 0xFF53, 0xFF54, 0xFF55};
constexpr int kCount = sizeof(kIds) / sizeof(kIds[0]);

// protocomm's own service UUID, kept rather than replaced with one of ours so that a client which
// already speaks this protocol can drive the strip without being taught anything. It becomes ours
// when the hub is the only client that matters; see docs/strip.md item 13.
constexpr uint8_t kServiceUuid[16] = {0x07, 0xed, 0x9b, 0x2d, 0x0f, 0x06, 0x7c, 0x87,
                                      0x9b, 0x43, 0x43, 0x6b, 0x4d, 0x24, 0x75, 0x17};

ble_uuid128_t gSvcUuid;
ble_uuid128_t gChrUuid[kCount];
ble_uuid16_t gDscUuid = BLE_UUID16_INIT(0x2901);  // Characteristic User Description
ble_gatt_dsc_def gDscs[kCount][2];
ble_gatt_chr_def gChrs[kCount + 1];
uint8_t gScanRsp[31];
size_t gScanRspLen = 0;

// Live only while provisioning is running.
protocomm_t *gPc = nullptr;
// The name is a std::string and not a strdup because this table now outlives one opening of the
// door: dropping a rung stops the manager and starts it again against the SAME scheme config, so
// anything freed on the way out is read again on the way back in. It was a strdup freed in
// prov_stop, which the Config it was copied from went on pointing at.
struct Endpoint {
    std::string name;
    uint16_t id;
};
std::vector<Endpoint> gEndpoints;
// One kept answer per characteristic, replaced by the next write to it and never dropped on a read:
// NimBLE serves a long read as several callbacks with rising offsets, so an answer freed after the
// first is an answer cut off at the MTU, which is what a 400-byte SRP public key then is.
struct Kept {
    uint8_t *buf = nullptr;
    ssize_t len = 0;
};
Kept gResp[kCount];

// Defined with the rest of the door, below. Declared here because the transport is what enforces it.
bool gate_is_open();

int slot_for(uint16_t id) {
    for (int i = 0; i < kCount; i++)
        if (kIds[i] == id) return i;
    return -1;
}
// The one protocomm session, keyed by the BLE connection it belongs to. SECURITY_2 refuses every
// message until a session has been opened for the connection ("Invalid session ID, expected -1"),
// and the reference transport opens it from the GAP connect event, which CHIP owns here. So it is
// opened on the first write from a connection instead, and closed when CHIP says the link went.
constexpr uint32_t kNoSession = 0xFFFFFFFF;
uint32_t gSession = kNoSession;

void end_session() {
    if (gPc && gSession != kNoSession) protocomm_close_session(gPc, gSession);
    gSession = kNoSession;
}

const char *name_for(uint16_t id) {
    for (const auto &e : gEndpoints)
        if (e.id == id) return e.name.c_str();
    return nullptr;
}

void drop_response(int slot) {
    if (slot < 0) return;
    free(gResp[slot].buf);
    gResp[slot].buf = nullptr;
    gResp[slot].len = 0;
}
void drop_responses() {
    for (int i = 0; i < kCount; i++) drop_response(i);
}

// ASK THE OTHER END TO BE PATIENT (docs/strip.md item 15). CHIP negotiates no connection parameters
// at all, so a link runs on whatever the central proposed -- and BlueZ proposes a short supervision
// timeout with a fast interval, which the strip cannot always meet while it is also holding up
// Wi-Fi on the same radio. Measured on 21 September: a session completes at -51 dBm and dies three
// to five seconds in at -64 with reason 0x208, a supervision timeout. Thirteen decibels, and a real
// strip is behind a television with the hub in another room.
//
// So we ask for a slower interval and ten seconds of patience the moment a client speaks to us. It
// is a request: the central may refuse, and nothing here depends on it being granted.
void ask_for_a_patient_link(uint16_t conn) {
    struct ble_gap_upd_params want = {};
    want.itvl_min = 24;              // 30 ms, in 1.25 ms units
    want.itvl_max = 40;              // 50 ms -- room between events for the Wi-Fi half of the radio
    want.latency = 0;                // provisioning is a conversation; do not let it skip events
    want.supervision_timeout = 1000; // 10 s, in 10 ms units
    const int rc = ble_gap_update_params(conn, &want);
    ESP_LOGI(TAG, "asked link %u to be patient: %s", conn, rc == 0 ? "ok" : "refused");
}

}  // namespace

// Every link that is currently up, asked once each. There is no "list connections" call in NimBLE
// and at three maximum connections walking the handles is honest enough.
//
// THIS IS POLLED, AND IT HAS TO BE. The obvious hook, CHIP's kCHIPoBLEConnectionEstablished, is
// raised when a client subscribes to CHIPoBLE and not when the GAP link comes up -- and the link
// was dying during service discovery, several seconds before any of that. CHIP owns the GAP event
// handler and we are not forking it, so the housekeeping loop looks instead. A link is found within
// a tick of forming, which is early enough to matter and late enough to cost nothing.
void be_patient_with_everyone() {
    static uint8_t asked = 0;
    // NOT EVERY TICK, AND NOT WHEN THE DOOR IS SHUT. The first version of this walked three handles
    // on every pass of the housekeeping loop whether or not anything was connected, and NimBLE logs
    // "GAP conn_find: connection not found" for each miss -- three hundred lines a second, a core
    // spent on nothing, and a console in which the thing you were actually looking for could not be
    // found. Discovered on 21 September while reading the log for something else, which is exactly
    // how a log that shouts loses the message it was kept for.
    //
    // A quarter of a second is forty times less often and still far inside the window that matters:
    // the link it needs to catch dies a second or more after it forms.
    if (!gPc) return;   // gPc is set only while the door is open
    const int64_t now = esp_timer_get_time();
    static int64_t looked = 0;
    if (now - looked < 250000) return;
    looked = now;

    for (uint16_t h = 0; h < 3; h++) {
        struct ble_gap_conn_desc desc;
        const bool up = ble_gap_conn_find(h, &desc) == 0;
        const uint8_t bit = (uint8_t)(1u << h);
        if (up && !(asked & bit)) {
            asked = (uint8_t)(asked | bit);
            ask_for_a_patient_link(h);
        } else if (!up) {
            asked = (uint8_t)(asked & ~bit);
        }
    }
}

namespace {

// A write is a request and a read is its answer: protocomm is request/response over two operations
// on one characteristic, so the answer has to be kept between them.
int chr_access(uint16_t conn, uint16_t, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    const uint16_t id = (uint16_t)(uintptr_t)arg;
    const int slot = slot_for(id);
    if (slot < 0) return BLE_ATT_ERR_UNLIKELY;

    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        const Kept &k = gResp[slot];
        if (!k.buf || k.len <= 0) return 0;  // nothing asked yet; an empty read is not an error
        return os_mbuf_append(ctxt->om, k.buf, (uint16_t)k.len) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
    }

    if (ctxt->op != BLE_GATT_ACCESS_OP_WRITE_CHR) return BLE_ATT_ERR_UNLIKELY;

    const char *ep = name_for(id);
    if (!gPc || !ep) {
        ESP_LOGW(TAG, "write to 0x%04x with no provisioning running", id);
        return BLE_ATT_ERR_UNLIKELY;
    }

    if (gSession != conn) {
        end_session();
        if (protocomm_open_session(gPc, conn) != ESP_OK) return BLE_ATT_ERR_UNLIKELY;
        gSession = conn;
    }

    // THE GATE, AND IT IS HERE RATHER THAN ON THE HUB (design/strip/Press.dc.html). This is the whole
    // of what the press buys, and it is four lines in the one place a request can be stopped: anything
    // in radio range may open a session, walk the table and ask the strip its version, and it gets
    // exactly this far. The credentials are refused until somebody in the room has touched the object.
    //
    // It is deliberately not the hub's to decide. A gate the hub releases is a gate whoever spoke
    // first releases, which is the unauthenticated link this firmware was rewritten to remove.
    if (strcmp(ep, "prov-config") == 0 && !gate_is_open()) {
        ESP_LOGW(TAG, "somebody asked for the Wi-Fi before the button was pressed. No.");
        // AUTHORIZATION, NOT AUTHENTICATION. 0x05 and 0x0f both mean "encrypt the link and come
        // back", so a central takes them as an invitation to pair -- CoreBluetooth answered our
        // 0x05 with "Insufficient Encryption" on 21 September, having tried. There is nothing to
        // pair: the link is fine and the answer is no. 0x08 is the one that says so.
        return BLE_ATT_ERR_INSUFFICIENT_AUTHOR;
    }

    uint16_t len = 0;
    const uint16_t room = OS_MBUF_PKTLEN(ctxt->om);
    uint8_t *req = (uint8_t *)malloc(room ? room : 1);
    if (!req) return BLE_ATT_ERR_INSUFFICIENT_RES;
    if (ble_hs_mbuf_to_flat(ctxt->om, req, room, &len) != 0) {
        free(req);
        return BLE_ATT_ERR_UNLIKELY;
    }

    drop_response(slot);
    const esp_err_t err = protocomm_req_handle(gPc, ep, conn, req, len, &gResp[slot].buf, &gResp[slot].len);
    free(req);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "%s refused the request: %s", ep, esp_err_to_name(err));
        drop_response(slot);
        return BLE_ATT_ERR_UNLIKELY;
    }
    return 0;
}

// The name of the endpoint, which is how a client tells the characteristics apart. It is served from
// the live table rather than baked in, because at the moment this table was registered nobody had
// been told the names yet.
int dsc_access(uint16_t, uint16_t, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    const uint16_t id = (uint16_t)(uintptr_t)arg;
    const char *ep = name_for(id);
    if (!ep) return 0;
    return os_mbuf_append(ctxt->om, ep, strlen(ep)) == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
}

// ---- the scheme network_provisioning drives us through -------------------------------------------

struct Config {
    std::vector<Endpoint> endpoints;
};

void *new_config() { return new (std::nothrow) Config(); }
void delete_config(void *config) { delete (Config *)config; }

esp_err_t set_config_service(void *, const char *service_name, const char *) {
    // The reference scheme puts this in the BLE device name. We have no room for a name: Matter's
    // payload owns the advertisement and our UUID owns the scan response, so a client finds us by
    // UUID instead (docs/strip.md item 12).
    ESP_LOGD(TAG, "service name '%s' ignored; there is no room for one", service_name ? service_name : "");
    return ESP_OK;
}

esp_err_t set_config_endpoint(void *config, const char *endpoint_name, uint16_t uuid) {
    if (!config || !endpoint_name) return ESP_ERR_INVALID_ARG;
    for (uint16_t id : kIds) {
        if (id != uuid) continue;
        ((Config *)config)->endpoints.push_back({endpoint_name, uuid});
        return ESP_OK;
    }
    // Reserving the table at boot means a late endpoint has nowhere to go, and failing loudly here is
    // better than a characteristic that silently does not exist.
    ESP_LOGE(TAG, "endpoint '%s' wants 0x%04x, which no characteristic was reserved for", endpoint_name, uuid);
    return ESP_ERR_NOT_FOUND;
}

esp_err_t prov_start(protocomm_t *pc, void *config) {
    if (!pc || !config) return ESP_ERR_INVALID_ARG;
    gEndpoints = ((Config *)config)->endpoints;
    gPc = pc;
    ESP_LOGI(TAG, "our door is open, %d endpoints on CHIP's own radio", (int)gEndpoints.size());
    return ESP_OK;
}

esp_err_t prov_stop(protocomm_t *) {
    end_session();
    gPc = nullptr;
    gEndpoints.clear();
    drop_responses();
    ESP_LOGI(TAG, "our door is shut");
    return ESP_OK;
}

network_prov_scheme_t gScheme = {};

// ---- the door itself -----------------------------------------------------------------------------

uint8_t gRhythm[4] = {0, 0, 0, 0};
bool gBusy = false;
char *gSalt = nullptr;
char *gVerifier = nullptr;
int gVerifierLen = 0;

// The username is fixed and public. "wifiprov" because that is what every existing protocomm client
// sends unless told otherwise, and a bench client should just work.
constexpr char kUser[] = "wifiprov";
// And on the press rung the PASSWORD is fixed and public too, which is the point rather than an
// oversight: there is no secret on this rung. What stops a stranger is gate_is_open() below.
constexpr char kOpenSesame[] = "press";

// THE GATE. Anything in radio range can open a session; nothing gets the household's Wi-Fi out of it
// until somebody standing in the room has touched the strip. Two minutes is the walk across a house
// and back, and it is also the window an attacker would have to be racing in.
constexpr int64_t kPressGoodFor = (int64_t)120 * 1000000;
bool gPressed = false;
int64_t gPressedAt = 0;
// The hub has asked for the rung below. It cannot be done from the handler that hears it -- that runs
// on the manager's own task, inside the manager it would be tearing down -- so it is a flag, and
// tend_the_door() picks it up from somewhere safe.
bool gDropARung = false;
bool gReopenWithRhythm = false;
// The manager has finished with the door and its memory is still ours to give back. See the
// NETWORK_PROV_END case for why that cannot be done where it is noticed.
bool gDoorIsShut = false;

// True when the door may hand over credentials.
//
// On the rung below there is nothing to gate: four counts went through SRP6a to get this far, so the
// session itself is the proof and the strip has already refused everybody who got them wrong.
bool gate_is_open() {
    if (gRhythm[0]) return true;
    if (!gPressed) return false;
    if (esp_timer_get_time() - gPressedAt >= kPressGoodFor) {
        gPressed = false;
        ESP_LOGW(TAG, "that press is too old now. Waiting for another");
        return false;
    }
    return true;
}

HubDetails gHubDetails = nullptr;
Taken gTaken = nullptr;
int64_t gOpenedAt = 0;

// TWO DAYS, IN OUR OWN CODE (design/strip/KnockTwoDays.dc.html). CHIP caps a commissioning window at
// 900 seconds and its own way round that, CONFIG_ENABLE_BLE_EXT_ANNOUNCEMENT, does not compile in
// this connectedhomeip -- it is `default n`, nobody builds that path, and BLEManagerImpl.cpp drops a
// nodiscard CHIP_ERROR under -Werror. Patching vendored CHIP would put the fix outside this
// repository, so the window is simply reopened here until the budget runs out. The board said B was
// one line of configuration; it is not, and that is written down in docs/strip.md.
constexpr int64_t kKnockFor = (int64_t)48 * 60 * 60 * 1000000;  // microseconds

// WHERE OUR HUB IS, HANDED OVER IN THE SESSION THAT IS ALREADY OPEN. This is item 2a, which was an
// empty string from the day Matter came in: a strip finishes provisioning knowing the household's
// Wi-Fi and nothing about us, so the color question and the fill can never be asked. The one moment
// it is safe to say is this one -- a session the strip authenticated, with somebody standing in the
// room -- and it costs one endpoint on a characteristic that was reserved at boot for exactly this.
//
// Lines of key=value, not protobuf: the schema is ours on both ends, there are four keys, and a
// hub-side client that has to be hand-written anyway should not also need a .proto.
esp_err_t hub_handler(uint32_t, const uint8_t *inbuf, ssize_t inlen, uint8_t **outbuf, ssize_t *outlen, void *) {
    int taken = 0, refused = 0;
    std::string body((const char *)inbuf, inlen > 0 ? (size_t)inlen : 0);
    size_t at = 0;
    while (at < body.size()) {
        size_t nl = body.find('\n', at);
        if (nl == std::string::npos) nl = body.size();
        const std::string line = body.substr(at, nl - at);
        at = nl + 1;
        const size_t eq = line.find('=');
        if (eq == std::string::npos || eq == 0) continue;
        const std::string k = line.substr(0, eq), v = line.substr(eq + 1);
        if (gHubDetails && gHubDetails(k.c_str(), v.c_str())) taken++;
        else { refused++; ESP_LOGW(TAG, "the hub offered '%s', which this strip does not keep", k.c_str()); }
    }
    ESP_LOGI(TAG, "the hub said where it is: %d details taken, %d refused", taken, refused);
    const char *answer = refused ? "partial" : (taken ? "ok" : "empty");
    *outlen = (ssize_t)strlen(answer);
    *outbuf = (uint8_t *)malloc(*outlen);
    if (!*outbuf) { *outlen = 0; return ESP_ERR_NO_MEM; }
    memcpy(*outbuf, answer, *outlen);
    return ESP_OK;
}

// IS IT PRESSED YET? The hub asks this, politely, every second or so while the wall says it is
// waiting; the answer moves the wall off that beat. A plain word each way rather than protobuf, for
// the same reason the `hub` endpoint is: the schema is ours on both ends and there are three words.
//
// Asking for "rhythm" is the household tapping "It has no button I can reach" -- see tend_the_door().
esp_err_t press_handler(uint32_t, const uint8_t *inbuf, ssize_t inlen, uint8_t **outbuf, ssize_t *outlen, void *) {
    const std::string asked((const char *)inbuf, inlen > 0 ? (size_t)inlen : 0);
    const char *answer = "waiting";
    if (asked == "rhythm") {
        gDropARung = true;
        answer = "ok";
    } else if (gate_is_open()) {
        answer = "pressed";
    }
    *outlen = (ssize_t)strlen(answer);
    *outbuf = (uint8_t *)malloc(*outlen);
    if (!*outbuf) { *outlen = 0; return ESP_ERR_NO_MEM; }
    memcpy(*outbuf, answer, *outlen);
    return ESP_OK;
}

void on_prov_event(void *, network_prov_cb_event_t event, void *data) {
    switch (event) {
    case NETWORK_PROV_START:
        // Registered here rather than before starting, because protocomm_add_endpoint needs a
        // running manager; the characteristic it lands on was reserved at boot.
        if (network_prov_mgr_endpoint_register("hub", hub_handler, nullptr) != ESP_OK)
            ESP_LOGE(TAG, "no 'hub' endpoint; a strip set up here will not know where we are");
        if (network_prov_mgr_endpoint_register("press", press_handler, nullptr) != ESP_OK)
            ESP_LOGE(TAG, "no 'press' endpoint; nothing can ever be let in through our door");
        gOpenedAt = esp_timer_get_time();
        if (gRhythm[0])
            ESP_LOGI(TAG, "listening. The rhythm is %d %d %d %d", gRhythm[0], gRhythm[1], gRhythm[2], gRhythm[3]);
        else
            ESP_LOGI(TAG, "listening. Press the button to let anybody in");
        break;
    case NETWORK_PROV_WIFI_CRED_RECV: {
        // Somebody counted right. From here the manager owns the Wi-Fi driver until it succeeds or
        // gives up, and the light stops being an instrument.
        auto *cfg = (wifi_sta_config_t *)data;
        gBusy = true;
        ESP_LOGI(TAG, "credentials for '%s' arrived through our door", (const char *)cfg->ssid);
        break;
    }
    case NETWORK_PROV_WIFI_CRED_FAIL:
        ESP_LOGW(TAG, "the house's Wi-Fi did not take those credentials");
        break;
    case NETWORK_PROV_WIFI_CRED_SUCCESS: {
        // THE FIRST SESSION TO COMPLETE TAKES THE STRIP, and the other door shuts
        // (design/strip/Both.dc.html). Remembered in NVS because a strip that came through our door
        // has no Matter fabric, so nothing else on the device can answer this at the next boot --
        // without it the strip flashes its rhythm for ever and tries to reopen a door it has
        // already been through.
        gOpenedAt = 0;
        if (gTaken) gTaken(true);
        // ON THE CHIP TASK, NOT THIS ONE. We are on network_provisioning's thread here, and touching
        // the stack from it is not a race that might bite later: CHIP checks, calls the access
        // "unsafe/racy", and aborts the device. It cost a reboot loop on 21 September.
        const CHIP_ERROR scheduled = chip::DeviceLayer::PlatformMgr().ScheduleWork([](intptr_t) {
            chip::Server::GetInstance().GetCommissioningWindowManager().CloseCommissioningWindow();
            ESP_LOGI(TAG, "Matter's window is shut; this strip is ours");
        });
        if (scheduled != CHIP_NO_ERROR)
            ESP_LOGE(TAG, "Matter's window stayed open: %s", chip::ErrorStr(scheduled));
        ESP_LOGI(TAG, "on the household's Wi-Fi, through our own door");
        break;
    }
    case NETWORK_PROV_END:
        // One completed session shuts the door, and it stays shut: the strip does not re-advertise
        // on a router reboot or anything else (docs/strip.md, "The light never reports a fault").
        //
        // AND THE DEINIT DOES NOT HAPPEN HERE, which cost an evening on the bench on 21 September.
        // This callback is made from inside prov_stop_and_notify(), on the esp_timer task, WITH THE
        // MANAGER'S OWN LOCK ALREADY HELD -- the comment in manager.c says so and nothing in the
        // header does. network_prov_mgr_deinit() takes that same lock, and it is not recursive, so
        // the call never returns and the task it was on is gone for good. Nothing is logged. The
        // strip goes on looking perfectly alive until something else wants a timer, and the next
        // task to ask the manager for anything joins it -- which is how the whole housekeeping loop,
        // the button with it, stopped dead one line after asking to open a door a rung lower.
        //
        // So it is noticed here and done in tend_the_door(), from a task that holds nothing.
        gBusy = false;
        gDoorIsShut = true;
        break;
    default:
        break;
    }
}

}  // namespace

namespace {

// Everything both rungs have in common, which is all of it but the password. `again` is the second
// opening of a door that has already been built once -- the manager is still initialised and its
// endpoints still exist, so all that is wanted is a start with a different verifier.
esp_err_t open_on(const char *pass, size_t pass_len, bool again = false) {
    if (gPc) return ESP_ERR_INVALID_STATE;

    free(gSalt); free(gVerifier);
    gSalt = gVerifier = nullptr;
    esp_err_t err = esp_srp_gen_salt_verifier(kUser, sizeof(kUser) - 1, pass, (int)pass_len,
                                              &gSalt, 16, &gVerifier, &gVerifierLen);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "could not make a verifier: %s", esp_err_to_name(err));
        return err;
    }

    if (!again) {
        network_prov_mgr_config_t cfg = {};  // NOLINT: the scheme is copied in below
        cfg.scheme = gScheme;
        cfg.scheme_event_handler = NETWORK_PROV_EVENT_HANDLER_NONE;
        cfg.app_event_handler.event_cb = on_prov_event;
        err = network_prov_mgr_init(cfg);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "the manager would not start: %s", esp_err_to_name(err));
            return err;
        }

        // 0xFF53 + 1 and + 2, which are the characteristics reserve() kept spare. Both have to be
        // made BEFORE provisioning starts -- the manager hands the whole endpoint table to the
        // scheme in one go, and reserve() cannot grow the table once Matter has started. Registering
        // a handler later (NETWORK_PROV_START) without creating the endpoint here gives it nowhere
        // to live, and the only sign of it is the endpoint count in the log being one short.
        //
        // AND ONLY ONCE, EVER. endpoint_create hands out the next id each time it is called, so
        // asking again on the second opening would ask for 0xFF56 and 0xFF57, which no characteristic
        // was reserved for. The table the manager already holds is the one to reuse.
        for (const char *ep : {"hub", "press"}) {
            if (network_prov_mgr_endpoint_create(ep) == ESP_OK) continue;
            ESP_LOGE(TAG, "could not make room for the '%s' endpoint", ep);
            network_prov_mgr_deinit();
            return ESP_FAIL;
        }
    }

    protocomm_security2_params_t sec2 = {};
    sec2.salt = gSalt;
    sec2.salt_len = 16;
    sec2.verifier = gVerifier;
    sec2.verifier_len = (uint16_t)gVerifierLen;
    err = network_prov_mgr_start_provisioning(NETWORK_PROV_SECURITY_2, &sec2, "strip", nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "the door would not open: %s", esp_err_to_name(err));
        if (!again) network_prov_mgr_deinit();
        return err;
    }
    return ESP_OK;
}

// THE RUNG BELOW. Four counts of one to six, minted fresh, shown on the strip and made into a real
// SRP6a verifier. esp_random() is the hardware RNG once the radio is up, which it is by now. It is
// small until SRP6a is under it: no offline attack, one wrong guess ends the session, and a fresh
// rhythm every time somebody asks for one.
esp_err_t open_with_a_rhythm() {
    char pass[5];
    for (int i = 0; i < 4; i++) {
        gRhythm[i] = (uint8_t)(1 + esp_random() % 6);
        pass[i] = (char)('0' + gRhythm[i]);
    }
    pass[4] = 0;
    return open_on(pass, 4, /*again=*/true);
}

}  // namespace

esp_err_t open() {
    // Nothing to show and nothing to count: the strip is simply lit, and stays that way until the
    // button is pressed. rhythm()[0] staying zero is how everything else tells the two rungs apart.
    memset(gRhythm, 0, sizeof(gRhythm));
    gPressed = false;
    gPressedAt = 0;
    return open_on(kOpenSesame, sizeof(kOpenSesame) - 1);
}

bool press() {
    if (!gPc || !gOpenedAt) return false;   // nothing is asking, so nothing to answer
    if (gRhythm[0]) return false;           // a rung down, the flashes are the proof and this is not
    gPressed = true;
    gPressedAt = esp_timer_get_time();
    ESP_LOGI(TAG, "pressed. Whoever is at the door has %d seconds", (int)(kPressGoodFor / 1000000));
    return true;
}

void tend_the_door() {
    // EVERY LINE OF THIS COST A ROUND ON THE BENCH ON 21 SEPTEMBER, and none of it is in a header.
    //
    // ONE: stop_provisioning() is asynchronous -- it arms a cleanup timer and returns -- so the flag
    // is cleared HERE rather than when the stop lands. This loop runs every ten milliseconds, and the
    // first version watched gPc instead and asked for the same stop eighteen times in a fifth of a
    // second.
    //
    // TWO: the thing to wait for is gPc going null, which our own prov_stop does. Not an event: the
    // first version waited for NETWORK_PROV_END, which a stop does not raise on its own, and the
    // strip shut its door and then sat there in silence with nothing open at either rung.
    //
    // THREE: the reopen is a start and nothing else. A stop leaves the manager initialised and IDLE
    // with its endpoints intact, which is exactly what a second start_provisioning wants -- and a
    // deinit in between is the deadlock the NETWORK_PROV_END case above is about.
    if (gDropARung) {
        gDropARung = false;
        gReopenWithRhythm = true;
        ESP_LOGI(TAG, "nobody can reach the button. Shutting the door to open it a rung lower");
        network_prov_mgr_stop_provisioning();
        return;
    }
    if (gReopenWithRhythm && !gPc) {
        gReopenWithRhythm = false;
        gDoorIsShut = false;   // it is about to be open again, so there is nothing to give back
        if (open_with_a_rhythm() != ESP_OK)
            ESP_LOGE(TAG, "the door would not reopen with a rhythm; this strip cannot be taken now");
        return;
    }
    // The door is shut for good. Give the manager's memory back -- ON A TASK OF ITS OWN, and that
    // is the whole point of these four lines.
    //
    // THE BUTTON MUST NEVER BE BEHIND ANYTHING THAT CAN BLOCK. It is the way out of every other
    // mistake in this firmware -- the factory reset lives on it -- and it is read from the same loop
    // as this. network_prov_mgr_deinit() takes the manager's own lock, and the manager's cleanup
    // timer holds that lock while it tells us the door has shut; it is exactly the call that already
    // hung a task once. Worse, THIS line only runs after a session has actually completed, so it
    // never ran on a bench whose Wi-Fi was a name that does not exist, and ran every time on a real
    // house. Reported from one on 21 September as "holding BOOT does nothing until I press RESET
    // first", which is what a housekeeping loop that is no longer running looks like from outside.
    //
    // On its own task, the worst a block costs is the manager's memory. On this one it costs the
    // button, the fill, the light and the way out.
    if (gDoorIsShut && !gPc) {
        gDoorIsShut = false;
        auto pack_away = [](void *) {
            network_prov_mgr_deinit();
            ESP_LOGI(TAG, "the door is shut and the manager is packed away");
            vTaskDelete(nullptr);
        };
        if (xTaskCreate(pack_away, "prov_pack", 4096, nullptr, 4, nullptr) != pdPASS)
            ESP_LOGW(TAG, "could not pack the manager away; it keeps its memory and we keep going");
    }
}

void disconnected() { end_session(); drop_responses(); }

void on_hub_details(HubDetails fn) { gHubDetails = fn; }

void on_taken(Taken fn) { gTaken = fn; }

// KEEP IT SHOUTING WHILE IT IS STILL KNOCKING. CHIP drops from fast advertising to slow after thirty
// seconds, which is right for a device somebody is standing over and wrong for ours: a household
// plugs a strip in and then walks to the wall, so the hub always looks after the thirty seconds are
// up. Measured on 21 September -- from the far end of a room the Pi found the strip in seconds at a
// 25 ms interval and could not find it at all in twenty seconds at 500 ms. A strip on mains power
// that nobody has taken has nothing better to do than be findable.
//
// It is a nudge on a timer rather than a reaction to an event, because CHIP does not raise one when
// it drops to slow: kCHIPoBLEAdvertisingChange does not fire, and the first version of this hung off
// that and silently never ran.
void stay_loud() {
    if (!gPc || !gOpenedAt) return;
    if (!chip::Server::GetInstance().GetCommissioningWindowManager().IsCommissioningWindowOpen()) return;
    const CHIP_ERROR e = chip::DeviceLayer::PlatformMgr().ScheduleWork([](intptr_t) {
        const CHIP_ERROR set = chip::DeviceLayer::Internal::BLEMgr().SetAdvertisingMode(
            chip::DeviceLayer::ConnectivityManager::BLEAdvertisingMode::kFastAdvertising);
        if (set != CHIP_NO_ERROR) ESP_LOGW(TAG, "could not stay loud: %s", chip::ErrorStr(set));
    });
    if (e != CHIP_NO_ERROR) ESP_LOGW(TAG, "could not stay loud: %s", chip::ErrorStr(e));
}

bool keep_knocking() {
    if (!gPc || !gOpenedAt) return false;                       // never opened, or already taken

    // CHIP STOPS ADVERTISING FOR REASONS THAT ARE NOT THE WINDOW CLOSING. It stops and restarts when
    // it drops from fast to slow advertising, and again around a connection. Treating every stop as
    // the end of the window reopened it constantly, kicked the radio back to fast advertising for
    // ever, and dropped a client that was in the middle of discovering services -- which is how this
    // was found, with a Pi failing at "failed to discover services, device disconnected".
    if (chip::Server::GetInstance().GetCommissioningWindowManager().IsCommissioningWindowOpen()) return true;

    if (esp_timer_get_time() - gOpenedAt >= kKnockFor) {
        ESP_LOGI(TAG, "two days of knocking is enough");
        return false;
    }
    // Reopening is a CHIP call, so it goes on the CHIP task: doing it from anywhere else does not
    // race, it aborts the device.
    const CHIP_ERROR e = chip::DeviceLayer::PlatformMgr().ScheduleWork([](intptr_t) {
        const CHIP_ERROR opened =
            chip::Server::GetInstance().GetCommissioningWindowManager().OpenBasicCommissioningWindow();
        if (opened != CHIP_NO_ERROR) ESP_LOGE(TAG, "the window would not reopen: %s", chip::ErrorStr(opened));
    });
    if (e != CHIP_NO_ERROR) {
        ESP_LOGE(TAG, "could not keep knocking: %s", chip::ErrorStr(e));
        return false;
    }
    ESP_LOGI(TAG, "still nobody. Knocking again");
    return true;
}

const uint8_t *rhythm() { return gRhythm; }
bool busy() { return gBusy; }

esp_err_t reserve(const char *name) {
    memcpy(gSvcUuid.value, kServiceUuid, sizeof(kServiceUuid));
    gSvcUuid.u.type = BLE_UUID_TYPE_128;

    for (int i = 0; i < kCount; i++) {
        // Each characteristic is the service UUID with the endpoint's sixteen-bit id dropped in at
        // byte 12, which is where protocomm puts it and therefore where a client looks for it.
        gChrUuid[i] = gSvcUuid;
        gChrUuid[i].value[12] = (uint8_t)(kIds[i] & 0xff);
        gChrUuid[i].value[13] = (uint8_t)(kIds[i] >> 8);

        gDscs[i][0] = {};
        gDscs[i][0].uuid = &gDscUuid.u;
        gDscs[i][0].att_flags = BLE_ATT_F_READ;
        gDscs[i][0].access_cb = dsc_access;
        gDscs[i][0].arg = (void *)(uintptr_t)kIds[i];
        gDscs[i][1] = {};

        gChrs[i] = {};
        gChrs[i].uuid = &gChrUuid[i].u;
        gChrs[i].access_cb = chr_access;
        gChrs[i].arg = (void *)(uintptr_t)kIds[i];
        gChrs[i].descriptors = gDscs[i];
        gChrs[i].flags = BLE_GATT_CHR_F_READ | BLE_GATT_CHR_F_WRITE;
    }
    gChrs[kCount] = {};

    ble_gatt_svc_def svc = {};
    svc.type = BLE_GATT_SVC_TYPE_PRIMARY;
    svc.uuid = &gSvcUuid.u;
    svc.characteristics = gChrs;

    auto &ble = chip::DeviceLayer::Internal::BLEMgrImpl();
    std::vector<struct ble_gatt_svc_def> extra{svc};
    CHIP_ERROR err = ble.ConfigureExtraServices(extra, true);
    if (err != CHIP_NO_ERROR) {
        ESP_LOGE(TAG, "CHIP would not take our service: %s", chip::ErrorStr(err));
        return ESP_FAIL;
    }

    // Two AD structures: the complete list of 128-bit service UUIDs, 18 bytes, and a complete local
    // name in whatever is left. A name longer than fits is cut, not refused, because the UUID is the
    // identifier and the name is a courtesy.
    //
    // THIRTY, NOT THIRTY-ONE. The spec allows 31 and CHIP accepts 31, and at 31 the strip vanished
    // from every scanner on 21 September -- not the name, the whole advertisement, Matter's included.
    // At 30 it is all there. Whether that is the controller or the scanners does not matter to a
    // household that cannot find its strip, so one byte is left on the table on purpose.
    constexpr size_t kScanRspMax = 30;
    gScanRsp[0] = 0x11;
    gScanRsp[1] = 0x07;
    memcpy(&gScanRsp[2], kServiceUuid, sizeof(kServiceUuid));
    gScanRspLen = 18;
    size_t n = name ? strlen(name) : 0;
    if (n > kScanRspMax - gScanRspLen - 2) n = kScanRspMax - gScanRspLen - 2;
    if (n) {
        gScanRsp[gScanRspLen++] = (uint8_t)(n + 1);
        gScanRsp[gScanRspLen++] = 0x09;
        memcpy(&gScanRsp[gScanRspLen], name, n);
        gScanRspLen += n;
    }
    err = ble.ConfigureScanResponseData(chip::ByteSpan(gScanRsp, gScanRspLen));
    if (err != CHIP_NO_ERROR) {
        ESP_LOGE(TAG, "CHIP would not take our scan response: %s", chip::ErrorStr(err));
        return ESP_FAIL;
    }

    gOpenedAt = 0;
    gScheme.prov_start = prov_start;
    gScheme.prov_stop = prov_stop;
    gScheme.new_config = new_config;
    gScheme.delete_config = delete_config;
    gScheme.set_config_service = set_config_service;
    gScheme.set_config_endpoint = set_config_endpoint;
#ifdef CONFIG_NETWORK_PROV_NETWORK_TYPE_WIFI
    gScheme.wifi_mode = WIFI_MODE_STA;
#endif

    ESP_LOGI(TAG, "%d characteristics reserved beside Matter's, scan response %u bytes of %u%s%.*s",
             kCount, (unsigned)gScanRspLen, (unsigned)kScanRspMax, n ? ", named " : "", (int)n, name ? name : "");
    return ESP_OK;
}

const network_prov_scheme_t &scheme() { return gScheme; }

}  // namespace prov
