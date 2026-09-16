// Brilliant OTA reachability probe.
//
// The switches broadcast a proprietary-mesh DFU "Firmware ID" beacon (service
// data 0xFEE4, packet type 0xFFFE) advertising company 0x0820, app 0x0001,
// version 0x0c107186. That is Nordic's OpenMesh DFU transport -- how the dead
// Control panels pushed firmware.
//
// This probe broadcasts a DFU "State (Application)" packet (0xFFFD) offering a
// HIGHER version for the same company+app. A switch that is willing to receive
// a transfer answers by broadcasting DFU "data request" packets (0xFFFB) asking
// for segment 0 -- and it does that BEFORE any flash is written. If we see those
// requests, the OTA channel is open to us. We never send firmware, so nothing
// on the switch changes.
//
// Uses the raw ESP-IDF GAP API (Arduino's BLEDevice can't set raw adv payloads).

#include <Arduino.h>
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_ble_api.h"

// ---- what the switches currently run (from their FWID beacon) --------------
static const uint32_t COMPANY_ID = 0x00000820;  // Brilliant
static const uint16_t APP_ID     = 0x0001;
static const uint32_t CUR_VER    = 0x0c107186;
static const uint32_t OFFER_VER  = 0x0c107187;  // one higher -> "update available"

static const uint16_t SVC_UUID   = 0xFEE4;      // Nordic OpenMesh service data

// DFU packet types
static const uint16_t PKT_FWID     = 0xFFFE;
static const uint16_t PKT_STATE    = 0xFFFD;
static const uint16_t PKT_DATA     = 0xFFFC;  // (start is a DATA packet, seg 0)
static const uint16_t PKT_DATA_REQ = 0xFFFB;
static const uint16_t PKT_DATA_RSP = 0xFFFA;

static uint32_t transferId = 0;
static uint32_t reqCount = 0, stateSeen = 0, fwidSeen = 0;
static uint32_t lastReport = 0;

// ---- build the DFU State (Application) advertising payload ------------------
// AD: [len][0x16][UUID lo][UUID hi][ DFU packet ... ]
static uint8_t advRaw[31];
static uint8_t advLen = 0;

static void put16(uint8_t *p, uint16_t v) { p[0] = v & 0xFF; p[1] = v >> 8; }
static void put32(uint8_t *p, uint32_t v) {
    p[0] = v & 0xFF; p[1] = (v >> 8) & 0xFF; p[2] = (v >> 16) & 0xFF; p[3] = v >> 24;
}

static void buildStateAdv() {
    uint8_t dfu[18];
    put16(dfu + 0, PKT_STATE);       // packet type
    dfu[2] = 0x04;                   // DFU type = application
    dfu[3] = 0x07;                   // transfer info: authority=7 (max), flood=0
    put32(dfu + 4, transferId);      // transfer id
    put32(dfu + 8, COMPANY_ID);      // company id
    put16(dfu + 12, APP_ID);         // app id
    put32(dfu + 14, OFFER_VER);      // offered (higher) app version
    const uint8_t dfuLen = 18;

    uint8_t *p = advRaw;
    *p++ = dfuLen + 3;               // AD length = svc-data(1+2) + payload
    *p++ = 0x16;                     // AD type: Service Data - 16-bit UUID
    put16(p, SVC_UUID); p += 2;
    memcpy(p, dfu, dfuLen); p += dfuLen;
    advLen = p - advRaw;
}

// ---- decode incoming 0xFEE4 packets from the switches ----------------------
static void onAdvReport(const uint8_t *data, uint8_t len, const uint8_t *mac, int rssi) {
    // walk AD structures looking for Service Data 0xFEE4
    uint8_t i = 0;
    while (i + 1 < len) {
        uint8_t adLen = data[i];
        if (adLen == 0 || i + 1 + adLen > len) break;
        uint8_t adType = data[i + 1];
        const uint8_t *ad = &data[i + 2];
        uint8_t adDataLen = adLen - 1;
        if (adType == 0x16 && adDataLen >= 2 && ad[0] == (SVC_UUID & 0xFF) &&
            ad[1] == (SVC_UUID >> 8)) {
            const uint8_t *dfu = ad + 2;
            uint8_t dlen = adDataLen - 2;
            if (dlen >= 2) {
                uint16_t type = dfu[0] | (dfu[1] << 8);
                char m[18];
                snprintf(m, sizeof(m), "%02x:%02x:%02x:%02x:%02x:%02x",
                         mac[5], mac[4], mac[3], mac[2], mac[1], mac[0]);
                if (type == PKT_DATA_REQ) {
                    reqCount++;
                    uint16_t seg = dlen >= 4 ? (dfu[2] | (dfu[3] << 8)) : 0;
                    uint32_t tid = dlen >= 8 ? (dfu[4] | (dfu[5]<<8) | (dfu[6]<<16) | ((uint32_t)dfu[7]<<24)) : 0;
                    Serial.printf("  <== DATA-REQUEST from %s seg=%u tid=0x%08x rssi=%d  %s\n",
                                  m, seg, tid, rssi,
                                  tid == transferId ? "**OURS -- switch wants our transfer**" : "");
                } else if (type == PKT_STATE) {
                    stateSeen++;
                    Serial.printf("  <== STATE from %s (someone else offering a transfer) rssi=%d\n", m, rssi);
                } else if (type == PKT_DATA || type == PKT_DATA_RSP) {
                    Serial.printf("  <== DATA/RSP from %s rssi=%d\n", m, rssi);
                } else if (type == PKT_FWID) {
                    fwidSeen++;   // the idle beacon; count quietly
                }
            }
        }
        i += 1 + adLen;
    }
}

static void gapCb(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t *p) {
    switch (event) {
        case ESP_GAP_BLE_ADV_DATA_RAW_SET_COMPLETE_EVT: {
            esp_ble_adv_params_t adv = {};
            adv.adv_int_min = 0x30;      // ~30ms
            adv.adv_int_max = 0x30;
            adv.adv_type = ADV_TYPE_NONCONN_IND;   // OpenMesh uses non-connectable
            adv.own_addr_type = BLE_ADDR_TYPE_PUBLIC;
            adv.channel_map = ADV_CHNL_ALL;
            adv.adv_filter_policy = ADV_FILTER_ALLOW_SCAN_ANY_CON_ANY;
            esp_ble_gap_start_advertising(&adv);
            break;
        }
        case ESP_GAP_BLE_SCAN_PARAM_SET_COMPLETE_EVT:
            esp_ble_gap_start_scanning(0);   // 0 = scan forever
            break;
        case ESP_GAP_BLE_ADV_START_COMPLETE_EVT:
            Serial.printf("[adv] start status=%d (0=OK)\n", p->adv_start_cmpl.status);
            break;
        case ESP_GAP_BLE_SCAN_START_COMPLETE_EVT:
            Serial.printf("[scan] start status=%d (0=OK)\n", p->scan_start_cmpl.status);
            break;
        case ESP_GAP_BLE_SCAN_RESULT_EVT: {
            auto *r = &p->scan_rst;
            if (r->search_evt == ESP_GAP_SEARCH_INQ_RES_EVT)
                onAdvReport(r->ble_adv, r->adv_data_len + r->scan_rsp_len,
                            r->bda, r->rssi);
            break;
        }
        default: break;
    }
}

void setup() {
    Serial.begin(115200);
    delay(400);
    Serial.println("\n=== Brilliant OTA reachability probe ===");

    transferId = esp_random();
    Serial.printf("offering app 0x%04x company 0x%06x version 0x%08x (cur 0x%08x)\n",
                  APP_ID, COMPANY_ID, OFFER_VER, CUR_VER);
    Serial.printf("transfer id 0x%08x\n", transferId);
    Serial.println("broadcasting STATE offer; listening for DATA-REQUESTs.\n");
    Serial.println("A data-request addressed to our transfer id = the switch will");
    Serial.println("accept a firmware transfer from us. NO firmware is sent.\n");

    btStart();
    esp_bluedroid_init();
    esp_bluedroid_enable();
    esp_ble_gap_register_callback(gapCb);

    buildStateAdv();
    esp_ble_gap_config_adv_data_raw(advRaw, advLen);

    esp_ble_scan_params_t sp = {};
    sp.scan_type = BLE_SCAN_TYPE_ACTIVE;
    sp.own_addr_type = BLE_ADDR_TYPE_PUBLIC;
    sp.scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ALL;
    sp.scan_interval = 0x200;   // 320ms
    sp.scan_window = 0x30;      // 30ms -> ~90% radio free for adv
    sp.scan_duplicate = BLE_SCAN_DUPLICATE_DISABLE;
    esp_ble_gap_set_scan_params(&sp);
}

void loop() {
    if (millis() - lastReport > 5000) {
        lastReport = millis();
        Serial.printf("[t=%lus] fwid-beacons=%lu  data-requests=%lu  other-state=%lu\n",
                      millis() / 1000, fwidSeen, reqCount, stateSeen);
        if (reqCount == 0)
            Serial.println("           (no transfer request yet -- keep waiting, or move closer)");
    }
    delay(50);
}
