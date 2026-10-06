// See errand.h. Ported from the bench relay in errand_bench.h, which proved each piece on the air
// (docs/strip.md items 38 to 40) and spoke a binary format the brain could never have sent.
#include "errand.h"

#include <NimBLEDevice.h>
#include "mbedtls/base64.h"

namespace {

// Our door (brain/hub/strip_door.py owns these): protocomm puts each endpoint's sixteen bits at byte
// 12 of the service UUID, so a characteristic is found from its endpoint id alone.
const char *kDoorSvc = "1775244d-6b43-439b-877c-060f2d9bed07";
constexpr uint16_t kPress = 0xFF55;

NimBLEUUID chr(uint16_t ep) {
    char u[40];
    snprintf(u, sizeof(u), "1775%04x-6b43-439b-877c-060f2d9bed07", ep);
    return NimBLEUUID(u);
}

// A hub that has gone quiet must not leave a second link holding the radio. The hub asks at least
// every ten seconds while it waits for a press (strip_door.RING_POLL), so thirty is three misses.
constexpr uint32_t kIdleMs = 30000;
// The largest thing a strip's door says or is told is a little over 400 bytes (item 39).
constexpr size_t kMaxBody = 600;

// A handful of commands can arrive between two passes of the loop -- a close hard on the heels of a
// send is the ordinary one -- so there is room for a few, each copied whole.
constexpr int kQueue = 4;
constexpr size_t kCmdMax = 900;
char gCmd[kQueue][kCmdMax];
volatile int gHead = 0, gTail = 0;
portMUX_TYPE gLock = portMUX_INITIALIZER_UNLOCKED;

void (*gPublish)(const char *, const char *) = nullptr;
NimBLEClient *gClient = nullptr;
char gId[24] = "";
bool gLinked = false;
bool gCanRing = false;
volatile bool gRang = false;
uint32_t gLastAt = 0;

// Sized for the longest line: "ok <id> <n> " and 600 bytes as base64.
char gOut[1000];

void tell(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(gOut, sizeof(gOut), fmt, ap);
    va_end(ap);
    if (gPublish) gPublish("errand/tell", gOut);
}

void ringCb(NimBLERemoteCharacteristic *, uint8_t *, size_t, bool) { gRang = true; }   // NimBLE's task

void letGo(const char *why) {
    if (gClient) {
        if (gClient->isConnected()) gClient->disconnect();
        NimBLEDevice::deleteClient(gClient);
        gClient = nullptr;
    }
    if (gLinked && why) tell("closed %s %s", gId, why);
    gLinked = false;
    gCanRing = false;
    gRang = false;
    gId[0] = 0;
}

void open(const char *id, const char *addr, const char *type) {
    if (gLinked) { tell("fail %s - busy", id); return; }
    if (!addr) { tell("fail %s - noaddr", id); return; }
    // A STRIP'S ADDRESS IS RANDOM. An address read from a string defaults to public, and six right
    // bytes of the wrong type are nobody's -- which cost a morning (item 42). The ear says which.
    const uint8_t kind = (type && !strcasecmp(type, "public")) ? BLE_ADDR_PUBLIC : BLE_ADDR_RANDOM;
    gClient = NimBLEDevice::createClient();
    if (!gClient) { tell("fail %s - noclient", id); return; }
    // Slower than the mesh link on purpose: an errand can afford latency and the proxy cannot.
    gClient->setConnectionParams(24, 40, 0, 600);
    gClient->setConnectTimeout(10);
    if (!gClient->connect(NimBLEAddress(std::string(addr), kind))) {
        NimBLEDevice::deleteClient(gClient);
        gClient = nullptr;
        tell("fail %s - connect", id);
        return;
    }
    gClient->getServices(true);
    NimBLERemoteService *door = gClient->getService(NimBLEUUID(kDoorSvc));
    if (!door) {
        gClient->disconnect();
        NimBLEDevice::deleteClient(gClient);
        gClient = nullptr;
        tell("fail %s - nodoor", id);
        return;
    }
    strlcpy(gId, id, sizeof(gId));
    gLinked = true;
    gLastAt = millis();
    // The ring (design/ears/Tell.dc.html): a strip that can notify on its press is asked once and
    // then told, instead of being asked a hundred and seventy times. An older one is simply quiet.
    NimBLERemoteCharacteristic *bell = door->getCharacteristic(chr(kPress));
    gCanRing = bell && bell->canNotify() && bell->subscribe(true, ringCb);
    tell("open %s %s", gId, gCanRing ? "ring" : "quiet");
}

uint8_t gIn[kMaxBody], gBack[kMaxBody];

void send(const char *id, const char *n, const char *ep, const char *b64) {
    if (!gLinked || strcmp(id, gId)) { tell("fail %s %s gone", id, n ? n : "-"); return; }
    if (!n || !ep || !b64) { tell("fail %s %s malformed", id, n ? n : "-"); return; }
    gLastAt = millis();
    size_t len = 0;
    if (mbedtls_base64_decode(gIn, sizeof(gIn), &len, (const unsigned char *)b64, strlen(b64)) != 0) {
        tell("fail %s %s base64", id, n);
        return;
    }
    NimBLERemoteService *door = gClient->getService(NimBLEUUID(kDoorSvc));
    NimBLERemoteCharacteristic *c = door ? door->getCharacteristic(chr((uint16_t)strtoul(ep, nullptr, 0))) : nullptr;
    if (!c) { tell("fail %s %s noendpoint", id, n); return; }
    // A refusal is the strip's answer, not a fault of the corridor: an ATT error means the bytes
    // arrived and protocomm said no (item 38). The hub decides what that means, not the puck.
    if (!c->writeValue(gIn, len, true)) { tell("fail %s %s write", id, n); return; }
    NimBLEAttValue v = c->readValue();
    size_t got = v.length() > sizeof(gBack) ? sizeof(gBack) : v.length();
    memcpy(gBack, v.data(), got);
    char enc[kMaxBody * 4 / 3 + 8];
    size_t elen = 0;
    if (mbedtls_base64_encode((unsigned char *)enc, sizeof(enc), &elen, gBack, got) != 0) {
        tell("fail %s %s base64", id, n);
        return;
    }
    enc[elen] = 0;
    tell("ok %s %s %s", id, n, enc);
}

void run(char *line) {
    char *verb = strtok(line, " ");
    char *id = strtok(nullptr, " ");
    if (!verb || !id) return;
    if (!strcmp(verb, "open")) {
        char *addr = strtok(nullptr, " ");
        open(id, addr, strtok(nullptr, " "));
    } else if (!strcmp(verb, "send")) {
        char *n = strtok(nullptr, " ");
        char *ep = strtok(nullptr, " ");
        send(id, n, ep, strtok(nullptr, " "));
    } else if (!strcmp(verb, "close")) {
        if (gLinked && !strcmp(id, gId)) letGo("asked");
    } else {
        tell("fail %s - unknown", id);
    }
}

}  // namespace

void errand_begin(void (*publish)(const char *leaf, const char *payload)) { gPublish = publish; }

bool errand_queue(const uint8_t *payload, size_t len) {
    portENTER_CRITICAL(&gLock);
    const int next = (gTail + 1) % kQueue;
    const bool room = next != gHead && len < kCmdMax;
    if (room) {
        memcpy(gCmd[gTail], payload, len);
        gCmd[gTail][len] = 0;
        gTail = next;
    }
    portEXIT_CRITICAL(&gLock);
    return room;
}

bool errand_holds_link() { return gLinked && gClient && gClient->isConnected(); }

bool errand_busy() { return gLinked || gHead != gTail; }

void errand_tick() {
    if (gLinked && (!gClient || !gClient->isConnected())) letGo("lost");
    if (gLinked && millis() - gLastAt > kIdleMs) letGo("idle");
    if (gLinked && gRang) {
        gRang = false;
        tell("ring %s", gId);
    }
    // One command a pass, so the mesh keeps its turn on the loop between them.
    static char line[kCmdMax];   // static: 900 bytes is a lot to ask of the loop task's stack
    bool have = false;
    portENTER_CRITICAL(&gLock);
    if (gHead != gTail) {
        memcpy(line, gCmd[gHead], kCmdMax);
        gHead = (gHead + 1) % kQueue;
        have = true;
    }
    portEXIT_CRITICAL(&gLock);
    if (have) run(line);
}
