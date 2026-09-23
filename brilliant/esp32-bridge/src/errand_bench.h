// A BENCH INSTRUMENT, AND NOTHING ELSE. It is built only by the `esp32s3-bench`
// environment and must never reach a puck in a house.
//
// design/ears/ chose direction A -- the bridge puck becomes a BLE errand runner
// for a hub that cannot hear a strip -- and the whole of that direction rests on
// one thing nobody had tried. This puck is ALREADY a GATT central: the mesh
// proxy link is a GATT connection to a Brilliant switch. The question is whether
// it can hold a SECOND central link, to a strip that is knocking, for the length
// of a handshake, while the mesh link stays up and the switches keep answering,
// with Wi-Fi and MQTT running throughout.
//
// So this does not implement an errand. It opens the second link, walks the
// strip's GATT table, and then reads and writes across it for as long as it is
// told to -- and, the whole time, says once a second how both links are doing.
// The second link is deliberately dumb: the real design keeps the SRP6a session
// end to end, so the puck would only ever be carrying bytes it cannot read, and
// what is being measured here is the radio, not the protocol.
//
// Commands, on <base>/bridge/<chip>/errand/set, and answers on .../errand:
//   idle [secs]        open nothing: what the mesh link does when nothing is asked of it
//   look [secs]        scan for everything, then say which of it is a strip door
//   go [secs]          second link to the loudest strip, walk it, hold it, read it
//   go <addr> [secs]   the same, to one named BLE address
//   drop               let go now

#pragma once

// The door a strip opens for us. brain/hub/strip_door.py owns these: the service
// is ours, and protocomm puts each endpoint's sixteen bits at byte 12 of it.
static NimBLEUUID DOOR_SVC("1775244d-6b43-439b-877c-060f2d9bed07");
static const uint16_t DOOR_EP[] = {0xFF51, 0xFF52, 0xFF53, 0xFF54, 0xFF55};
static const char *DOOR_EP_NAME[] = {"prov-session", "prov-config", "proto-ver", "hub", "press"};

static NimBLEUUID doorChr(uint16_t ep) {
    char u[40];
    snprintf(u, sizeof(u), "1775%04x-6b43-439b-877c-060f2d9bed07", ep);
    return NimBLEUUID(u);
}

// How the mesh side is doing is answered by two numbers, both kept in main.cpp:
// how long ago the proxy last handed us a PDU (`lastRxAt`) and how many it has
// handed us in all (`proxyPdus`). With POLL_MS at 250 and switches replying, the
// age sits well under a second, so a climb is the thing to watch for.

enum class Errand { Idle, Queued, Scanning, Connecting, Walking, Holding, Watching };
static Errand errandState = Errand::Idle;
static char errandCmd[64] = {0};
static NimBLEClient *errandClient = nullptr;
static NimBLEAddress errandAddr;
static int errandRssi = 0;
static uint32_t errandUntil = 0, errandSampleAt = 0, errandStartedAt = 0;
static uint32_t errandReads = 0, errandBytes = 0, errandReadFails = 0;
static uint32_t errandWrites = 0, errandWroteBytes = 0, errandWriteFails = 0, errandRefused = 0;
static uint32_t proxyPdusAtStart = 0;
static uint8_t errandEp = 0;

static void errandSay(const char *fmt, ...) {
    char line[200];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof(line), fmt, ap);
    va_end(ap);
    Serial.printf("[errand] %s\n", line);
    char t[80];
    bridgeTopic(t, sizeof(t), "errand");
    mqttPub(t, line, false);
}

// Queue only -- every line of the radio work below runs on the loop, for the same
// reason claim and the notify path do.
static bool errandQueue(const uint8_t *payload, unsigned int len) {
    if (errandState != Errand::Idle && errandState != Errand::Holding) return false;
    size_t n = min((unsigned int)(sizeof(errandCmd) - 1), len);
    memcpy(errandCmd, payload, n);
    errandCmd[n] = 0;
    errandState = Errand::Queued;
    return true;
}

static void errandDrop(const char *why) {
    if (errandClient) {
        if (errandClient->isConnected()) errandClient->disconnect();
        NimBLEDevice::deleteClient(errandClient);
        errandClient = nullptr;
    }
    if (errandState != Errand::Idle) errandSay("let go: %s", why);
    errandState = Errand::Idle;
}

// One line a second, for both links at once. This is the whole instrument: a
// before-and-after cannot tell a link that survived from one that was rebuilt
// while nobody was looking.
static void errandSample(const char *phase) {
    uint32_t now = millis();
    int rssi = (errandClient && errandClient->isConnected()) ? errandClient->getRssi() : 0;
    errandSay("%-8s t+%-5lu mesh %s age %lums pdus %lu | strip %s rssi %d wrote %lu/%lu read %lu/%lu refused %lu fails %lu/%lu | heap %u",
              phase, (unsigned long)(now - errandStartedAt),
              linkUp ? "up" : "DOWN", (unsigned long)(now - lastRxAt), (unsigned long)proxyPdus,
              (errandClient && errandClient->isConnected()) ? "up" : "down", rssi,
              (unsigned long)errandWrites, (unsigned long)errandWroteBytes,
              (unsigned long)errandReads, (unsigned long)errandBytes, (unsigned long)errandRefused,
              (unsigned long)errandWriteFails, (unsigned long)errandReadFails,
              (unsigned)ESP.getFreeHeap());
}

// Scan for EVERYTHING and say what came back before saying which of it is a door.
// A filtered scan cannot tell "no strip is knocking" from "the radio is dead".
static bool errandFind(NimBLEAddress *out, int *rssiOut, uint32_t secs, bool announceAll) {
    NimBLEScan *scan = NimBLEDevice::getScan();
    scan->setActiveScan(true);
    errandSay("scanning %lus for everything...", (unsigned long)secs);
    NimBLEScanResults res = scan->start(secs, false);
    int best = -999;
    bool found = false;
    int doors = 0;
    for (int i = 0; i < res.getCount(); i++) {
        NimBLEAdvertisedDevice d = res.getDevice(i);
        bool isDoor = d.isAdvertisingService(DOOR_SVC);
        if (isDoor) doors++;
        if (announceAll || isDoor)
            errandSay("  %-17s rssi %4d %-20s %s", d.getAddress().toString().c_str(), d.getRSSI(),
                      d.getName().c_str(), isDoor ? "<- a strip door" : "");
        if (isDoor && d.getRSSI() > best) {
            best = d.getRSSI();
            *out = d.getAddress();
            *rssiOut = d.getRSSI();
            found = true;
        }
    }
    errandSay("scan saw %d devices, %d of them a strip door", res.getCount(), doors);
    scan->clearResults();
    return found;
}

static bool errandWalk() {
    std::vector<NimBLERemoteService *> *svcs = errandClient->getServices(true);
    if (!svcs) return false;
    errandSay("mtu %u, %u services", errandClient->getMTU(), (unsigned)svcs->size());
    for (auto *s : *svcs) {
        std::vector<NimBLERemoteCharacteristic *> *chrs = s->getCharacteristics(true);
        errandSay("  svc %s (%u chrs)", s->getUUID().toString().c_str(),
                  (unsigned)(chrs ? chrs->size() : 0));
        if (!chrs) continue;
        for (auto *c : *chrs) {
            const char *name = "";
            for (size_t k = 0; k < sizeof(DOOR_EP) / sizeof(DOOR_EP[0]); k++)
                if (c->getUUID().equals(doorChr(DOOR_EP[k]))) name = DOOR_EP_NAME[k];
            errandSay("    chr %s %s%s%s %s", c->getUUID().toString().c_str(),
                      c->canRead() ? "r" : "-", c->canWrite() ? "w" : "-",
                      c->canNotify() ? "n" : "-", name);
        }
    }
    return true;
}

// THE TRAFFIC, one exchange per tick so the mesh side keeps its turn on the loop.
//
// A read on its own comes back empty, and that is protocomm rather than a fault:
// each characteristic answers with the reply to the last thing written to it, so
// a link that is only read from carries no bytes at all. The strip's real
// handshake writes a few hundred bytes and reads a few hundred back, over an MTU
// of 69, which means a long write and a read split across several callbacks. So
// that is what this does -- the same size and the same cadence as an SRP6a round,
// with bytes the strip cannot make sense of. What is being measured is the radio.
static const size_t ERRAND_PAYLOAD = 384;
static uint8_t errandBuf[ERRAND_PAYLOAD];

static void errandRead() {
    NimBLERemoteService *svc = errandClient->getService(DOOR_SVC);
    if (!svc) { errandReadFails++; return; }

    // The big one: a 384-byte write to prov-session, which at an MTU of 69 is a
    // long write split across several callbacks -- the same shape as the first
    // round of a real SRP6a handshake. The bytes are garbage, so protocomm answers
    // ESP_ERR_INVALID_ARG and its GATT stack returns an ATT error. THAT IS A PASS,
    // not a failure: an application refusing a payload is a payload that arrived.
    // A write that never got there fails with the link, and is counted separately.
    NimBLERemoteCharacteristic *big = svc->getCharacteristic(doorChr(0xFF51));
    if (!big) { errandWriteFails++; return; }
    for (size_t i = 0; i < ERRAND_PAYLOAD; i++) errandBuf[i] = (uint8_t)(errandWrites + i);
    bool ok = big->writeValue(errandBuf, ERRAND_PAYLOAD, true);
    if (!errandClient->isConnected()) { errandWriteFails++; return; }
    errandWrites++;
    errandWroteBytes += ERRAND_PAYLOAD;
    if (!ok) errandRefused++;

    // And one exchange that answers with real bytes, so the read direction is
    // measured too: proto-ver hands back the protocomm version for any request
    // at all, which is the one endpoint that does not need a valid session.
    NimBLERemoteCharacteristic *ver = svc->getCharacteristic(doorChr(0xFF53));
    if (!ver) { errandReadFails++; return; }
    uint8_t ask[8] = {0};
    ver->writeValue(ask, sizeof(ask), true);
    NimBLEAttValue v = ver->readValue();
    if (v.length() == 0) { errandReadFails++; return; }
    errandReads++;
    errandBytes += v.length();
}

static void errandTick() {
    uint32_t now = millis();

    if (errandState == Errand::Queued) {
        char cmd[64];
        strlcpy(cmd, errandCmd, sizeof(cmd));
        char *verb = strtok(cmd, " ");
        char *a1 = strtok(nullptr, " ");
        char *a2 = strtok(nullptr, " ");
        if (!verb) { errandState = Errand::Idle; return; }
        if (!strcasecmp(verb, "drop")) { errandDrop("asked to"); return; }
        errandStartedAt = now;
        proxyPdusAtStart = proxyPdus;
        errandReads = errandBytes = errandReadFails = 0;
        errandWrites = errandWroteBytes = errandWriteFails = errandRefused = 0;
        errandEp = 0;
        // The baseline. Without it a rate measured during an errand is a number
        // with nothing to be compared against, and the cost of the errand is a guess.
        if (!strcasecmp(verb, "idle")) {
            uint32_t secs = a1 ? atoi(a1) : 60;
            if (secs < 5) secs = 60;
            errandUntil = now + secs * 1000UL;
            errandSampleAt = now;
            errandSample("idle");
            errandState = Errand::Watching;
            return;
        }
        if (!strcasecmp(verb, "look")) {
            NimBLEAddress a; int r;
            errandSample("before");
            errandFind(&a, &r, a1 ? atoi(a1) : 6, true);
            errandSample("after");
            errandState = Errand::Idle;
            return;
        }
        if (strcasecmp(verb, "go")) { errandSay("don't know '%s'", verb); errandState = Errand::Idle; return; }

        uint32_t hold = 20;
        bool named = a1 && strchr(a1, ':');
        if (named && a2) hold = atoi(a2);
        else if (!named && a1) hold = atoi(a1);
        if (hold < 5) hold = 20;

        errandSample("before");
        if (named) {
            errandAddr = NimBLEAddress(std::string(a1));
            errandRssi = 0;
        } else if (!errandFind(&errandAddr, &errandRssi, 6, false)) {
            errandSay("no strip is knocking -- nothing to run an errand to");
            errandSample("after");
            errandState = Errand::Idle;
            return;
        }
        errandSay("second link -> %s (rssi %d at scan), holding %lus",
                  errandAddr.toString().c_str(), errandRssi, (unsigned long)hold);
        errandSample("scanned");

        // The clients the controller already has: the mesh proxy is one of them,
        // and NimBLE's ceiling is CONFIG_BT_NIMBLE_MAX_CONNECTIONS.
        errandSay("clients before: %u of %d", (unsigned)NimBLEDevice::getClientListSize(),
                  CONFIG_BT_NIMBLE_MAX_CONNECTIONS);
        errandClient = NimBLEDevice::createClient();
        if (!errandClient) {
            errandSay("NO SECOND CLIENT: createClient() refused at %u of %d",
                      (unsigned)NimBLEDevice::getClientListSize(), CONFIG_BT_NIMBLE_MAX_CONNECTIONS);
            errandState = Errand::Idle;
            return;
        }
        // Slower than the mesh link on purpose: the errand can afford latency and
        // the proxy cannot, so the second link asks for the smaller share.
        errandClient->setConnectionParams(24, 40, 0, 600);
        errandClient->setConnectTimeout(10);
        errandState = Errand::Connecting;
        errandUntil = now + hold * 1000UL;
        return;
    }

    if (errandState == Errand::Connecting) {
        uint32_t t0 = millis();
        bool ok = errandClient->connect(errandAddr);
        errandSay("connect %s in %lums; clients now %u", ok ? "OK" : "FAILED",
                  (unsigned long)(millis() - t0), (unsigned)NimBLEDevice::getClientListSize());
        errandSample(ok ? "linked" : "nolink");
        if (!ok) { errandDrop("connect failed"); return; }
        errandState = Errand::Walking;
        return;
    }

    if (errandState == Errand::Walking) {
        if (!errandWalk()) { errandDrop("no GATT table"); return; }
        errandSample("walked");
        errandSampleAt = now;
        errandState = Errand::Holding;
        return;
    }

    if (errandState == Errand::Watching) {
        if (now - errandSampleAt >= 5000) {
            errandSampleAt = now;
            errandSample("idle");
        }
        if (now >= errandUntil) {
            errandSay("idle %lums; mesh PDUs during: %lu",
                      (unsigned long)(now - errandStartedAt),
                      (unsigned long)(proxyPdus - proxyPdusAtStart));
            errandState = Errand::Idle;
        }
        return;
    }

    if (errandState == Errand::Holding) {
        if (!errandClient->isConnected()) {
            errandSay("THE SECOND LINK DROPPED by itself at t+%lums",
                      (unsigned long)(now - errandStartedAt));
            errandSample("dropped");
            errandDrop("peer went");
            return;
        }
        errandRead();
        if (now - errandSampleAt >= 1000) {
            errandSampleAt = now;
            errandSample("holding");
        }
        if (now >= errandUntil) {
            errandSample("done");
            errandSay("held %lums: wrote %lu exchanges / %lu bytes, read %lu / %lu bytes, "
                      "%lu refused by protocomm (which means they arrived), "
                      "fails %lu write %lu read; mesh PDUs during: %lu",
                      (unsigned long)(now - errandStartedAt),
                      (unsigned long)errandWrites, (unsigned long)errandWroteBytes,
                      (unsigned long)errandReads, (unsigned long)errandBytes,
                      (unsigned long)errandRefused,
                      (unsigned long)errandWriteFails, (unsigned long)errandReadFails,
                      (unsigned long)(proxyPdus - proxyPdusAtStart));
            errandDrop("time up");
            errandSample("after");
        }
        return;
    }
}
