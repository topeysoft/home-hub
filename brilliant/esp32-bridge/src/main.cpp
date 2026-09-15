// Brilliant mesh -> MQTT bridge.
//
// The ESP32 is NOT a mesh node. It is a mesh PROXY CLIENT: it connects over
// GATT to whichever Brilliant switch is advertising our Network ID, opens the
// proxy filter, and then speaks the mesh network layer directly. Same approach
// (and same keys) as the Python tooling in ../.
//
// Publishes   brilliant/<src>/event   {json}
// Subscribes  brilliant/<addr>/set    "on" | "off" | "dim:0-100"

#include <Arduino.h>
#include <BLEDevice.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include "mesh_crypto.h"
#include "secrets.h"

// Our own address on the mesh. Deliberately NOT PROVISIONER_ADDR: the Mac
// tooling uses that, and two senders sharing one address with independent
// sequence counters would trip the nodes' replay protection.
#define BRIDGE_ADDR 0x0010

static BLEUUID SVC_PROXY((uint16_t)0x1828);
static BLEUUID CH_IN("00002add-0000-1000-8000-00805f9b34fb");
static BLEUUID CH_OUT("00002ade-0000-1000-8000-00805f9b34fb");

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
Preferences prefs;

static BLEClient *bleClient = nullptr;
static BLERemoteCharacteristic *chIn = nullptr;
static BLEAdvertisedDevice *target = nullptr;
static volatile bool connected = false;
static uint8_t ourNetId[8];
static uint32_t txSeq = 0;
static uint8_t appAid = 0;

// proxy SAR reassembly
static uint8_t sarBuf[512];
static size_t sarLen = 0;

// ---------------------------------------------------------------- helpers

static void hexstr(const uint8_t *b, size_t n, char *out) {
    static const char *H = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) {
        out[i * 2] = H[b[i] >> 4];
        out[i * 2 + 1] = H[b[i] & 0xF];
    }
    out[n * 2] = 0;
}

static uint32_t nextSeq() {
    txSeq++;
    // persist every 32 to limit flash wear; on boot we skip ahead to be safe
    if ((txSeq & 0x1F) == 0) prefs.putUInt("seq", txSeq);
    return txSeq;
}

static void proxySend(uint8_t type, const uint8_t *pdu, size_t len) {
    if (!chIn || !connected) return;
    const size_t room = 64;  // conservative; negotiated MTU is larger
    if (len <= room) {
        uint8_t buf[80];
        buf[0] = type;
        memcpy(buf + 1, pdu, len);
        chIn->writeValue(buf, len + 1, false);
        return;
    }
    size_t off = 0, idx = 0, total = (len + room - 1) / room;
    while (off < len) {
        size_t n = min(room, len - off);
        uint8_t sar = (idx == 0) ? 0b01 : ((idx == total - 1) ? 0b11 : 0b10);
        uint8_t buf[80];
        buf[0] = (sar << 6) | type;
        memcpy(buf + 1, pdu + off, n);
        chIn->writeValue(buf, n + 1, false);
        off += n;
        idx++;
        delay(20);
    }
}

// Send an access message to a node, encrypted with the application key.
static void sendAccess(uint16_t dst, const uint8_t *access, size_t alen) {
    uint32_t seq = nextSeq();
    uint8_t upper[32];
    size_t ulen = mesh_app_encrypt(APP_KEY, false, IV_INDEX, seq, BRIDGE_ADDR,
                                   dst, access, alen, upper);
    if (!ulen || ulen > 15) {
        Serial.println("[tx] access too large for unsegmented, dropped");
        return;
    }
    uint8_t lower[32];
    lower[0] = 0x40 | (appAid & 0x3F);  // AKF=1
    memcpy(lower + 1, upper, ulen);

    uint8_t npdu[48];
    size_t nlen = mesh_net_encrypt(NET_KEY, IV_INDEX, 0, 5, seq, BRIDGE_ADDR, dst,
                                   lower, ulen + 1, 0x00, npdu);
    if (nlen) proxySend(0x00, npdu, nlen);
}

static void setProxyFilter() {
    uint32_t seq = nextSeq();
    const uint8_t cfg[2] = {0x00, 0x01};  // Set Filter Type = deny-list
    uint8_t npdu[48];
    size_t nlen = mesh_net_encrypt(NET_KEY, IV_INDEX, 1, 0, seq, BRIDGE_ADDR,
                                   0x0000, cfg, 2, 0x03, npdu);
    if (nlen) proxySend(0x02, npdu, nlen);
    Serial.println("[ble] proxy filter opened");
}

// ---------------------------------------------------------------- rx

static void publishEvent(const MeshNetMsg &m, const uint8_t *access, size_t alen) {
    uint32_t op;
    size_t olen;
    if (!(access[0] & 0x80)) {
        op = access[0];
        olen = 1;
    } else if ((access[0] & 0xC0) == 0x80) {
        op = ((uint32_t)access[0] << 8) | access[1];
        olen = 2;
    } else {
        op = ((uint32_t)access[0] << 16) | ((uint32_t)access[1] << 8) | access[2];
        olen = 3;
    }

    char params[2 * 32 + 1] = {0};
    size_t plen = alen > olen ? alen - olen : 0;
    if (plen > 32) plen = 32;
    hexstr(access + olen, plen, params);

    char topic[64];
    snprintf(topic, sizeof(topic), "%s/%04x/event", MQTT_BASE, m.src);

    char payload[256];
    const char *kind = (olen == 3) ? "vendor" : "sig";
    snprintf(payload, sizeof(payload),
             "{\"src\":\"0x%04x\",\"dst\":\"0x%04x\",\"opcode\":\"0x%06lx\","
             "\"kind\":\"%s\",\"params\":\"%s\",\"seq\":%lu}",
             m.src, m.dst, (unsigned long)op, kind, params, (unsigned long)m.seq);

    Serial.printf("[rx] %s %s\n", topic, payload);
    if (mqtt.connected()) mqtt.publish(topic, payload);

    // Convenience topic for plain on/off so HA can use it directly.
    if (op == 0x8204 && plen >= 1) {
        char st[64];
        snprintf(st, sizeof(st), "%s/%04x/state", MQTT_BASE, m.src);
        if (mqtt.connected()) mqtt.publish(st, access[olen] ? "ON" : "OFF", true);
    }
}

static void handleNetworkPdu(const uint8_t *pdu, size_t len) {
    MeshNetMsg m;
    if (!mesh_net_decrypt(NET_KEY, IV_INDEX, pdu, len, &m)) return;
    if (m.ctl) return;  // control messages (acks etc) -- ignore for now
    if (m.tlen < 2) return;

    bool seg = m.transport[0] & 0x80;
    if (seg) {
        // Segmented access messages are not reassembled yet; report so we can
        // see that they are happening rather than silently dropping them.
        Serial.printf("[rx] segmented access from 0x%04x (not reassembled)\n",
                      m.src);
        return;
    }

    bool akf = (m.transport[0] >> 6) & 1;
    uint8_t out[48];
    size_t olen;
    const uint8_t *key = akf ? APP_KEY : DEV_KEY;
    if (!mesh_app_decrypt(key, !akf, IV_INDEX, m.seq, m.src, m.dst,
                          m.transport + 1, m.tlen - 1, 4, out, &olen)) {
        return;
    }
    publishEvent(m, out, olen);
}

static void notifyCb(BLERemoteCharacteristic *c, uint8_t *data, size_t len,
                     bool isNotify) {
    if (len < 1) return;
    uint8_t sar = (data[0] & 0xC0) >> 6;
    uint8_t type = data[0] & 0x3F;
    const uint8_t *p = data + 1;
    size_t n = len - 1;

    if (sar == 0b00) {
        if (type == 0x00) handleNetworkPdu(p, n);
        return;
    }
    if (sar == 0b01) {
        sarLen = 0;
    }
    if (sarLen + n < sizeof(sarBuf)) {
        memcpy(sarBuf + sarLen, p, n);
        sarLen += n;
    }
    if (sar == 0b11) {
        if (type == 0x00) handleNetworkPdu(sarBuf, sarLen);
        sarLen = 0;
    }
}

// ---------------------------------------------------------------- ble

class ScanCb : public BLEAdvertisedDeviceCallbacks {
    void onResult(BLEAdvertisedDevice dev) override {
        if (!dev.haveServiceData()) return;
        for (int i = 0; i < dev.getServiceDataUUIDCount(); i++) {
            if (!dev.getServiceDataUUID(i).equals(SVC_PROXY)) continue;
            std::string sd = dev.getServiceData(i);
            // Network ID beacon: 0x00 || 8-byte network id
            if (sd.size() < 9 || sd[0] != 0x00) continue;
            if (memcmp(sd.data() + 1, ourNetId, 8) != 0) continue;
            Serial.printf("[ble] found our node %s (rssi %d)\n",
                          dev.getAddress().toString().c_str(), dev.getRSSI());
            if (target) delete target;
            target = new BLEAdvertisedDevice(dev);
            BLEDevice::getScan()->stop();
            return;
        }
    }
};

class ClientCb : public BLEClientCallbacks {
    void onConnect(BLEClient *c) override { connected = true; }
    void onDisconnect(BLEClient *c) override {
        connected = false;
        chIn = nullptr;
        Serial.println("[ble] disconnected");
    }
};

static bool connectToNode() {
    if (!target) return false;
    Serial.println("[ble] connecting...");
    if (!bleClient) {
        bleClient = BLEDevice::createClient();
        bleClient->setClientCallbacks(new ClientCb());
    }
    if (!bleClient->connect(target)) {
        Serial.println("[ble] connect failed");
        return false;
    }
    bleClient->setMTU(69);
    BLERemoteService *svc = bleClient->getService(SVC_PROXY);
    if (!svc) {
        Serial.println("[ble] no proxy service");
        bleClient->disconnect();
        return false;
    }
    chIn = svc->getCharacteristic(CH_IN);
    BLERemoteCharacteristic *chOut = svc->getCharacteristic(CH_OUT);
    if (!chIn || !chOut) {
        Serial.println("[ble] missing proxy characteristics");
        bleClient->disconnect();
        return false;
    }
    chOut->registerForNotify(notifyCb);
    connected = true;
    delay(300);
    setProxyFilter();
    Serial.println("[ble] bridge up");
    return true;
}

// ---------------------------------------------------------------- mqtt

static void mqttCb(char *topic, uint8_t *payload, unsigned int len) {
    char msg[32] = {0};
    memcpy(msg, payload, min((unsigned int)31, len));

    unsigned addr = NODE_ADDR;
    const char *slash = strchr(topic + strlen(MQTT_BASE) + 1, '/');
    if (slash) sscanf(topic + strlen(MQTT_BASE) + 1, "%x", &addr);

    static uint8_t tid = 0;
    tid++;
    if (!strcasecmp(msg, "on") || !strcasecmp(msg, "off")) {
        uint8_t a[4] = {0x82, 0x02, (uint8_t)(!strcasecmp(msg, "on") ? 1 : 0), tid};
        sendAccess(addr, a, 4);
        Serial.printf("[cmd] 0x%04x -> %s\n", addr, msg);
    } else if (!strncasecmp(msg, "dim:", 4)) {
        int pct = constrain(atoi(msg + 4), 0, 100);
        int16_t lvl = (int16_t)(-32768 + (pct * 65535L) / 100);
        uint8_t a[5] = {0x82, 0x09, (uint8_t)(lvl & 0xFF), (uint8_t)((lvl >> 8) & 0xFF),
                        tid};
        sendAccess(addr, a, 5);
        Serial.printf("[cmd] 0x%04x -> dim %d%%\n", addr, pct);
    }
}

static void mqttReconnect() {
    if (mqtt.connected()) return;
    static uint32_t last = 0;
    if (millis() - last < 5000) return;
    last = millis();
    String id = "brilliant-bridge-" + String((uint32_t)ESP.getEfuseMac(), HEX);
    bool ok = strlen(MQTT_USER) ? mqtt.connect(id.c_str(), MQTT_USER, MQTT_PASS)
                                : mqtt.connect(id.c_str());
    if (ok) {
        char sub[64];
        snprintf(sub, sizeof(sub), "%s/+/set", MQTT_BASE);
        mqtt.subscribe(sub);
        Serial.printf("[mqtt] connected, subscribed %s\n", sub);
    }
}

// ---------------------------------------------------------------- lifecycle

void setup() {
    Serial.begin(115200);
    delay(300);
    Serial.println("\n=== Brilliant mesh -> MQTT bridge ===");

    prefs.begin("brilliant", false);
    txSeq = prefs.getUInt("seq", 0) + 64;  // skip ahead past any unsaved seq
    prefs.putUInt("seq", txSeq);

    Serial.println("crypto self-test:");
    if (!mesh_selftest(Serial)) Serial.println("  !! CRYPTO BROKEN -- do not trust results");

    mesh_k3(NET_KEY, ourNetId);
    char s[20];
    hexstr(ourNetId, 8, s);
    Serial.printf("network id %s\n", s);
    appAid = mesh_k4(APP_KEY);
    Serial.printf("app aid 0x%02x, bridge addr 0x%04x, seq %lu\n", appAid,
                  BRIDGE_ADDR, (unsigned long)txSeq);

    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    Serial.print("[wifi] connecting");
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED)
        Serial.printf("[wifi] %s\n", WiFi.localIP().toString().c_str());
    else
        Serial.println("[wifi] FAILED (check secrets.h)");

    mqtt.setServer(MQTT_HOST, MQTT_PORT);
    mqtt.setCallback(mqttCb);

    BLEDevice::init("brilliant-bridge");
    BLEScan *scan = BLEDevice::getScan();
    scan->setAdvertisedDeviceCallbacks(new ScanCb());
    scan->setActiveScan(true);
    scan->setInterval(100);
    scan->setWindow(99);
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        mqttReconnect();
        mqtt.loop();
    }
    if (!connected) {
        if (!target) {
            Serial.println("[ble] scanning for our network...");
            BLEDevice::getScan()->start(8, false);
            BLEDevice::getScan()->clearResults();
        }
        if (target && !connectToNode()) {
            delete target;
            target = nullptr;
            delay(2000);
        }
    }
    delay(50);
}
