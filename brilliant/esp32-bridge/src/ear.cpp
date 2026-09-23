// See ear.h. The contract a puck reports against is also the header of brain/hub/ears.py, and the two
// must agree: REPORT_EVERY, LOUDER and the payload are the same numbers and shape on both sides.
#include "ear.h"

#include <NimBLEDevice.h>

namespace {

// Ten of every hundred milliseconds, passive. The measurement is docs/strip.md item 42.
constexpr uint16_t kWindowMs = 10;
constexpr uint16_t kIntervalMs = 100;
// What the scanner is given back: exactly what setup() in main.cpp configures.
constexpr uint16_t kSetupWindowMs = 99;
constexpr uint16_t kSetupIntervalMs = 100;

constexpr uint32_t kReportEveryMs = 10000;   // hub/ears.py REPORT_EVERY
constexpr int kLouder = 6;                   // hub/ears.py LOUDER
constexpr uint32_t kForgetMs = 30000;        // hub/ears.py FRESH: not heard for this long, let it go
// NOT A READING. NimBLE hands back -8 dBm for some adverts -- seen on 23 September on a strip a metre
// away that read -37 either side of it, over and over -- and a value that loud is only physically
// possible with the antennas touching. Taken at face value it tripped a "louder" report every few
// seconds and would have made this puck the loudest ear in the house. hub/ears.py refuses the same.
constexpr int kLoudestReal = -15;

NimBLEUUID kMatter((uint16_t)0xFFF6);

// A few strips at once is an ordinary evening -- somebody unpacks a pair -- and eight is plenty.
struct Heard {
    bool used;
    char addr[18];
    uint8_t type;
    int8_t rssi;         // what is reported: a moving average, so one odd advert moves it a quarter
    int16_t rssiX4;      // ...kept at four times the scale so the average does not round away
    uint8_t svc[16];
    uint8_t svcLen;
    uint32_t heardAt;
    uint32_t reportedAt;
    int8_t reportedRssi;
    bool reported;
};
constexpr int kSlots = 8;
Heard gHeard[kSlots];
portMUX_TYPE gLock = portMUX_INITIALIZER_UNLOCKED;

void (*gPublish)(const char *, const char *) = nullptr;
bool gListening = false;

// On NimBLE's own task: note it and nothing else. Publishing happens from the loop.
class Ear : public NimBLEAdvertisedDeviceCallbacks {
    void onResult(NimBLEAdvertisedDevice *d) override {
        for (int k = 0; k < (int)d->getServiceDataCount(); k++) {
            if (!d->getServiceDataUUID(k).equals(kMatter)) continue;
            const int r = d->getRSSI();
            if (r >= kLoudestReal || r < -110) return;
            const std::string svc = d->getServiceData(k);
            const std::string addr = d->getAddress().toString();
            const uint32_t now = millis();
            portENTER_CRITICAL(&gLock);
            int slot = -1, free = -1, oldest = 0;
            for (int i = 0; i < kSlots; i++) {
                if (gHeard[i].used && !strcmp(gHeard[i].addr, addr.c_str())) { slot = i; break; }
                if (!gHeard[i].used && free < 0) free = i;
                if (gHeard[i].heardAt < gHeard[oldest].heardAt) oldest = i;
            }
            bool fresh = false;
            if (slot < 0) {
                slot = free >= 0 ? free : oldest;
                gHeard[slot] = {};
                gHeard[slot].used = true;
                strlcpy(gHeard[slot].addr, addr.c_str(), sizeof(gHeard[slot].addr));
                fresh = true;
            }
            Heard &h = gHeard[slot];
            h.type = d->getAddress().getType();
            h.rssiX4 = fresh ? (int16_t)(r * 4) : (int16_t)(h.rssiX4 + (r * 4 - h.rssiX4) / 4);
            h.rssi = (int8_t)(h.rssiX4 / 4);
            h.svcLen = (uint8_t)min(svc.size(), sizeof(h.svc));
            memcpy(h.svc, svc.data(), h.svcLen);
            h.heardAt = now;
            portEXIT_CRITICAL(&gLock);
            return;
        }
    }
};
Ear gEar;

void listen() {
    NimBLEScan *scan = NimBLEDevice::getScan();
    scan->stop();
    scan->clearResults();
    scan->setActiveScan(false);
    scan->setInterval(kIntervalMs);
    scan->setWindow(kWindowMs);
    scan->setMaxResults(0);                      // count, never keep: this runs all day
    scan->setAdvertisedDeviceCallbacks(&gEar, true);
    gListening = scan->start(0, nullptr, false);
    Serial.printf("[ear] listening passively, %u ms of every %u: %s\n", kWindowMs, kIntervalMs,
                  gListening ? "on" : "FAILED");
}

// Given back exactly as found, because the next user reads the results it keeps.
void stop() {
    NimBLEScan *scan = NimBLEDevice::getScan();
    scan->stop();
    scan->setAdvertisedDeviceCallbacks(nullptr, false);
    scan->setMaxResults(0xFF);
    scan->setActiveScan(true);
    scan->setInterval(kSetupIntervalMs);
    scan->setWindow(kSetupWindowMs);
    scan->clearResults();
    gListening = false;
    Serial.println("[ear] stopped; the scanner is somebody else's for a while");
}

void report(const Heard &h) {
    if (!gPublish) return;
    char hex[sizeof(h.svc) * 2 + 1];
    for (int i = 0; i < h.svcLen; i++) snprintf(hex + i * 2, 3, "%02x", h.svc[i]);
    hex[h.svcLen * 2] = 0;
    char body[160];
    snprintf(body, sizeof(body), "{\"addr\":\"%s\",\"type\":\"%s\",\"rssi\":%d,\"svc\":\"%s\"}",
             h.addr, h.type == BLE_ADDR_PUBLIC ? "public" : "random", h.rssi, hex);
    gPublish("heard", body);
}

}  // namespace

void ear_begin(void (*publish)(const char *leaf, const char *payload)) { gPublish = publish; }

void ear_tick(bool may_listen) {
    if (!may_listen) {
        if (gListening) stop();
        return;
    }
    // Start it, or start it again: a connect or anybody else's scan can end it without asking.
    if (!gListening || !NimBLEDevice::getScan()->isScanning()) listen();

    const uint32_t now = millis();
    Heard due[kSlots];
    int n = 0;
    portENTER_CRITICAL(&gLock);
    for (int i = 0; i < kSlots; i++) {
        Heard &h = gHeard[i];
        if (!h.used) continue;
        if (now - h.heardAt > kForgetMs) { h.used = false; continue; }
        const bool first = !h.reported;
        // Differences, never comparisons, so a puck up for fifty days does not stop reporting when
        // millis() wraps.
        const bool again = (int32_t)(h.heardAt - h.reportedAt) > 0 && now - h.reportedAt >= kReportEveryMs;
        // A single advert's loudness jitters by several dB, so a move is only news once a second.
        const bool moved = h.reported && abs(h.rssi - h.reportedRssi) >= kLouder && now - h.reportedAt >= 1000;
        if (first || again || moved) {
            h.reported = true;
            h.reportedAt = now;
            h.reportedRssi = h.rssi;
            due[n++] = h;
        }
    }
    portEXIT_CRITICAL(&gLock);
    for (int i = 0; i < n; i++) report(due[i]);
}
