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

#include <esp_log.h>
#include <esp_random.h>
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
struct Endpoint {
    const char *name;
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
        if (e.id == id) return e.name;
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
        char *copy = strdup(endpoint_name);
        if (!copy) return ESP_ERR_NO_MEM;
        ((Config *)config)->endpoints.push_back({copy, uuid});
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
    for (auto &e : gEndpoints) free((void *)e.name);
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

// The username is fixed and public; the rhythm is the whole secret. "wifiprov" because that is what
// every existing protocomm client sends unless told otherwise, and a bench client should just work.
constexpr char kUser[] = "wifiprov";

HubDetails gHubDetails = nullptr;
Taken gTaken = nullptr;

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

void on_prov_event(void *, network_prov_cb_event_t event, void *data) {
    switch (event) {
    case NETWORK_PROV_START:
        // Registered here rather than before starting, because protocomm_add_endpoint needs a
        // running manager; the characteristic it lands on was reserved at boot.
        if (network_prov_mgr_endpoint_register("hub", hub_handler, nullptr) != ESP_OK)
            ESP_LOGE(TAG, "no 'hub' endpoint; a strip set up here will not know where we are");
        ESP_LOGI(TAG, "listening. The rhythm is %d %d %d %d", gRhythm[0], gRhythm[1], gRhythm[2], gRhythm[3]);
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
        gBusy = false;
        network_prov_mgr_deinit();
        break;
    default:
        break;
    }
}

}  // namespace

esp_err_t open() {
    if (gPc) return ESP_ERR_INVALID_STATE;

    // esp_random() is the hardware RNG once the radio is up, which it is by now.
    char pass[5];
    for (int i = 0; i < 4; i++) {
        gRhythm[i] = (uint8_t)(1 + esp_random() % 6);
        pass[i] = (char)('0' + gRhythm[i]);
    }
    pass[4] = 0;

    free(gSalt); free(gVerifier);
    gSalt = gVerifier = nullptr;
    esp_err_t err = esp_srp_gen_salt_verifier(kUser, sizeof(kUser) - 1, pass, 4, &gSalt, 16, &gVerifier, &gVerifierLen);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "could not make a verifier from the rhythm: %s", esp_err_to_name(err));
        return err;
    }

    network_prov_mgr_config_t cfg = {};  // NOLINT: the scheme is copied in below
    cfg.scheme = gScheme;
    cfg.scheme_event_handler = NETWORK_PROV_EVENT_HANDLER_NONE;
    cfg.app_event_handler.event_cb = on_prov_event;
    err = network_prov_mgr_init(cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "the manager would not start: %s", esp_err_to_name(err));
        return err;
    }

    // 0xFF53 + 1, which is the first characteristic reserve() kept spare.
    if (network_prov_mgr_endpoint_create("hub") != ESP_OK) {
        ESP_LOGE(TAG, "could not make room for the 'hub' endpoint");
        network_prov_mgr_deinit();
        return ESP_FAIL;
    }

    protocomm_security2_params_t sec2 = {};
    sec2.salt = gSalt;
    sec2.salt_len = 16;
    sec2.verifier = gVerifier;
    sec2.verifier_len = (uint16_t)gVerifierLen;
    err = network_prov_mgr_start_provisioning(NETWORK_PROV_SECURITY_2, &sec2, "strip", nullptr);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "the door would not open: %s", esp_err_to_name(err));
        network_prov_mgr_deinit();
        return err;
    }
    return ESP_OK;
}

void disconnected() { end_session(); drop_responses(); }

void on_hub_details(HubDetails fn) { gHubDetails = fn; }

void on_taken(Taken fn) { gTaken = fn; }

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
