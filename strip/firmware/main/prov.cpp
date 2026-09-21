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
#include <vector>

#include <esp_log.h>
#include <host/ble_hs.h>
// CHIPDeviceLayer.h first: BLEManagerImpl.h is not self-contained and will not compile without the
// platform types it assumes somebody else has already pulled in.
#include <platform/CHIPDeviceLayer.h>
#include <platform/internal/BLEManager.h>
#include <platform/ESP32/BLEManagerImpl.h>
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
uint8_t gScanRsp[18];

// Live only while provisioning is running.
protocomm_t *gPc = nullptr;
struct Endpoint {
    const char *name;
    uint16_t id;
};
std::vector<Endpoint> gEndpoints;
uint8_t *gResp = nullptr;
ssize_t gRespLen = 0;

const char *name_for(uint16_t id) {
    for (const auto &e : gEndpoints)
        if (e.id == id) return e.name;
    return nullptr;
}

void drop_response() {
    free(gResp);
    gResp = nullptr;
    gRespLen = 0;
}

// A write is a request and a read is its answer: protocomm is request/response over two operations
// on one characteristic, so the answer has to be kept between them.
int chr_access(uint16_t conn, uint16_t, struct ble_gatt_access_ctxt *ctxt, void *arg) {
    const uint16_t id = (uint16_t)(uintptr_t)arg;

    if (ctxt->op == BLE_GATT_ACCESS_OP_READ_CHR) {
        if (!gResp || gRespLen <= 0) return 0;  // nothing asked yet; an empty read is not an error
        const int rc = os_mbuf_append(ctxt->om, gResp, (uint16_t)gRespLen);
        drop_response();
        return rc == 0 ? 0 : BLE_ATT_ERR_INSUFFICIENT_RES;
    }

    if (ctxt->op != BLE_GATT_ACCESS_OP_WRITE_CHR) return BLE_ATT_ERR_UNLIKELY;

    const char *ep = name_for(id);
    if (!gPc || !ep) {
        ESP_LOGW(TAG, "write to 0x%04x with no provisioning running", id);
        return BLE_ATT_ERR_UNLIKELY;
    }

    uint16_t len = 0;
    const uint16_t room = OS_MBUF_PKTLEN(ctxt->om);
    uint8_t *req = (uint8_t *)malloc(room ? room : 1);
    if (!req) return BLE_ATT_ERR_INSUFFICIENT_RES;
    if (ble_hs_mbuf_to_flat(ctxt->om, req, room, &len) != 0) {
        free(req);
        return BLE_ATT_ERR_UNLIKELY;
    }

    drop_response();
    const esp_err_t err = protocomm_req_handle(gPc, ep, conn, req, len, &gResp, &gRespLen);
    free(req);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "%s refused the request: %s", ep, esp_err_to_name(err));
        drop_response();
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
    gPc = nullptr;
    for (auto &e : gEndpoints) free((void *)e.name);
    gEndpoints.clear();
    drop_response();
    ESP_LOGI(TAG, "our door is shut");
    return ESP_OK;
}

network_prov_scheme_t gScheme = {};

}  // namespace

esp_err_t reserve() {
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

    // One AD structure: complete list of 128-bit service UUIDs, which is 18 of the 31 bytes.
    gScanRsp[0] = 0x11;
    gScanRsp[1] = 0x07;
    memcpy(&gScanRsp[2], kServiceUuid, sizeof(kServiceUuid));
    err = ble.ConfigureScanResponseData(chip::ByteSpan(gScanRsp, sizeof(gScanRsp)));
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

    ESP_LOGI(TAG, "%d characteristics reserved beside Matter's, scan response %u bytes of 31",
             kCount, (unsigned)sizeof(gScanRsp));
    return ESP_OK;
}

const network_prov_scheme_t &scheme() { return gScheme; }

}  // namespace prov
