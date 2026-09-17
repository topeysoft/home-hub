// Brilliant panel mesh -> MQTT bridge, with Home Assistant discovery.
//
// The ESP32 is NOT a mesh node. It is a mesh PROXY CLIENT: it connects over
// GATT to whichever Brilliant switch is advertising the panel's Network ID,
// opens the proxy filter, and then speaks the mesh network layer directly with
// the captured panel keys (netkey + appkey, see ../STATUS.md). One proxy link
// reaches every switch, because the switches relay for each other.
//
// What it does, per switch it hears from:
//   reads   Generic OnOff Status / Generic Level Status the switches publish
//           whenever someone touches them, and polls vendor field 0x13 (the
//           PIR's analogue motion level) the way the panel itself does
//   writes  Generic OnOff Set and Generic Level Set (0-1000 scale) on command
//   tells   Home Assistant about each switch over MQTT discovery: a light with
//           brightness, a motion binary_sensor, and a diagnostic motion level
//
// Identity. A switch belongs to a mesh network, not to whichever puck relays
// it, so switches are keyed by <net> (the network id, 16 hex) + <addr> (their
// unicast, 4 hex): two pucks on one network map a switch to the same HA entity,
// and pucks on different networks share one MQTT base. The puck itself is keyed
// by <chip>, six hex digits derived from its factory MAC, and its mesh source
// address is derived from the same so two pucks never share one.
//
// MQTT contract (the base is cfg.mqttBase, "mesh" unless the hub says otherwise):
//   mesh/bridge/<chip>/status          online | offline        (retained, LWT)
//   mesh/bridge/<chip>/proxy           "<ble addr> rssi <n>"    (retained)
//   mesh/bridge/<chip>/iv              iv index in use          (retained)
//   mesh/bridge/<chip>/net             network id it carries    (retained)
//   mesh/<net>/<addr>/state            ON | OFF                 (retained)
//   mesh/<net>/<addr>/brightness       0-255                    (retained)
//   mesh/<net>/<addr>/motion           ON | OFF                 (retained)
//   mesh/<net>/<addr>/motion_level     raw vendor 0x13 value    (retained)
//   mesh/<net>/<addr>/event            {json} every decoded message that is
//                                      not a motion poll reply  (not retained)
//   mesh/<net>/<addr>/set              ON | OFF | on | off | dim:<0-100>
//   mesh/<net>/<addr>/brightness/set   0-255
// HA discovery: homeassistant/<component>/mesh_<net>_<addr>[_motion|_motion_level]/config,
// entity ids mesh_<net4>_<addr>, device "<label> switch <addr>", via mesh_bridge_<chip>.
//
// Everything mesh-side runs on the Arduino loop task. The BLE notify callback
// only queues bytes: writing to the proxy from inside a GATT callback deadlocks
// Bluedroid, so acks and replies are never sent from there.

#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>

#include "esp_coexist.h"
#include "mesh_crypto.h"
#include "config.h"
#include "light.h"
// The compiled-in fallback for everything in cfg, plus the tunables below. One
// header per puck (-DSECRETS_FILE='"secrets-s3.h"' in platformio.ini), and
// OPTIONAL: the image the hub ships is built without one and comes up blank,
// to be written over the cable -- see config.h.
#ifndef SECRETS_FILE
#define SECRETS_FILE "secrets.h"
#endif
#if __has_include(SECRETS_FILE)
#include SECRETS_FILE
#endif

// ---------------------------------------------------------------- tunables
// Override any of these in secrets.h (make_secrets.py carries them over).

// BRIDGE_ADDR may be set in secrets.h to pin this puck's mesh unicast. By
// default it is derived from the chip id (0x7000 | chip<<4, sixteen addresses
// per puck for sequence-number generations): two senders sharing one address
// with independent sequence counters trip the switches' replay protection,
// and the laptop tools (0x0001 / 0x001a) and the panel hand out low addresses.
#ifndef PANEL_NODE
#define PANEL_NODE ""            // pin the proxy to one BLE address, or "" for the strongest
#endif
#ifndef SWITCH_SEED
#define SWITCH_SEED {0x000a}     // switches announced to HA at boot, before any traffic
#endif
#ifndef SWITCH_EXCLUDE
#define SWITCH_EXCLUDE {0x0012}  // panel elements that answer but are not lights
#endif
#ifndef POLL_MS
#define POLL_MS 250              // one motion poll per this many ms, round-robin
#endif
#ifndef MOTION_ON_ABOVE
#define MOTION_ON_ABOVE 4        // vendor 0x13 sits ~2 at rest, 7-8 on a walk-past
#endif
#ifndef MOTION_HOLD_MS
#define MOTION_HOLD_MS 20000     // motion stays ON this long after the last active sample
#endif
#ifndef HA_PREFIX
#define HA_PREFIX "homeassistant"
#endif
#ifndef TX_TTL
#define TX_TTL 5
#endif

#define MAX_SWITCHES 32
#define RESYNC_MS (10UL * 60UL * 1000UL)   // OnOff/Level Get to all-nodes, every 10 min
#define FILTER_MS 30000                    // re-assert the proxy filter
#define LINK_DEAD_MS 120000                // no proxy PDU at all for this long: reconnect

static const uint16_t VENDOR_CID = 0x0820;
static const uint8_t VENDOR_MOTION_FIELD = 0x13;   // polled: analogue motion level

// ---------------------------------------------------------------- state

static NimBLEUUID SVC_PROXY((uint16_t)0x1828);
static NimBLEUUID CH_IN("00002add-0000-1000-8000-00805f9b34fb");
static NimBLEUUID CH_OUT("00002ade-0000-1000-8000-00805f9b34fb");

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
Preferences prefs;

static NimBLEClient *bleClient = nullptr;
static NimBLERemoteCharacteristic *chIn = nullptr;
static NimBLEAddress targetAddr;
static bool haveTarget = false;
static volatile bool connected = false;
static bool linkUp = false;              // filter opened, ready to talk
static char proxyDesc[40] = "none";
static uint32_t lastRxAt = 0, lastFilterAt = 0, lastResyncAt = 0, lastPollAt = 0;
static uint32_t linkUpAt = 0;
static uint8_t sweepsDone = 0;
static uint8_t resyncIdx = 0xFF;         // walking the switch list with unicast Gets; 0xFF = idle
static uint32_t lastResyncStepAt = 0;

static uint8_t ourNetId[8];
static uint8_t appAid = 0;
static char chipHex[7] = "000000";   // this puck: derived from the factory MAC
static char netHex[17] = "";         // this network: k3(netkey), 16 hex
static char netShort[5] = "";        // first four of it, for readable entity ids
static uint16_t bridgeBase = 0x7000; // our mesh unicast block (16 addresses)

// Sequence numbers are 24-bit and every poll spends one. When an address
// nears exhaustion we step to the next address in our block (bridgeBase + generation):
// a fresh source is a fresh sequence space, and the switches' replay lists
// are RAM, cleared by any power cut.
static uint32_t txSeq = 0;
static uint16_t addrGen = 0;
static uint32_t ivIndex = 0;             // set in setup() from cfg
static bool ivUpdating = false;

struct Switch {
    uint16_t addr;
    int8_t onoff;          // -1 unknown
    int16_t level;         // -1 unknown, else 0..1000
    int16_t motionLevel;   // -1 unknown
    int16_t motionFloor;   // slow-tracking minimum of motionLevel: the switch's own resting value
    uint32_t floorAt;      // when the floor last crept up
    bool motionOn;
    uint32_t motionActiveAt;
    uint32_t seenAt;
    bool announced;        // HA discovery published this MQTT session
};
static Switch switches[MAX_SWITCHES];
static uint8_t nSwitches = 0;
static uint8_t pollIdx = 0;

// replay / relay-duplicate cache, per source
struct SeqSeen { uint16_t src; uint32_t seq; };
static SeqSeen seen[MAX_SWITCHES + 8];
static uint8_t nSeen = 0;

// inbound proxy PDUs, queued from the BLE task to the loop task
struct RxItem { uint8_t type; uint8_t len; uint8_t data[96]; };
static QueueHandle_t rxq;
static uint8_t sarBuf[160];
static size_t sarLen = 0;

// segmented access reassembly (a vendor 0x03 status is two segments)
struct Reasm {
    bool used;
    uint16_t src, seqzero;
    uint8_t segn, szmic;
    uint32_t mask, firstSeq, at;
    uint8_t data[8 * 12];
    uint8_t lens[8];
};
static Reasm reasm[4];

static uint8_t tidCounter = 0;

// ---------------------------------------------------------------- helpers

static void hexstr(const uint8_t *b, size_t n, char *out) {
    static const char *H = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) {
        out[i * 2] = H[b[i] >> 4];
        out[i * 2 + 1] = H[b[i] & 0xF];
    }
    out[n * 2] = 0;
}

static uint16_t srcAddr() { return (uint16_t)(bridgeBase + (addrGen & 0x0F)); }

static uint32_t nextSeq() {
    if (txSeq >= 0xFFFF00) {
        addrGen = (addrGen + 1) & 0x0F;
        txSeq = 0;
        prefs.putUShort("gen", addrGen);
        prefs.putUInt("seq", 0);
        Serial.printf("[seq] exhausted; now sending as 0x%04x\n", srcAddr());
    }
    txSeq++;
    if ((txSeq & 0xFF) == 0) prefs.putUInt("seq", txSeq);
    return txSeq;
}

static uint32_t txIv() { return ivUpdating ? ivIndex - 1 : ivIndex; }

static bool isOurs(uint16_t a) { return a >= bridgeBase && a < bridgeBase + 16; }

static bool excluded(uint16_t a) {
    static const uint16_t ex[] = SWITCH_EXCLUDE;
    for (size_t i = 0; i < sizeof(ex) / sizeof(ex[0]); i++)
        if (ex[i] == a) return true;
    return false;
}

static void mqttPub(const char *topic, const char *payload, bool retain) {
    if (mqtt.connected()) mqtt.publish(topic, payload, retain);
}

static void swTopic(char *out, size_t n, uint16_t addr, const char *leaf) {
    snprintf(out, n, "%s/%s/%04x/%s", cfg.mqttBase, netHex, addr, leaf);
}

static void bridgeTopic(char *out, size_t n, const char *leaf) {
    snprintf(out, n, "%s/bridge/%s/%s", cfg.mqttBase, chipHex, leaf);
}

// ---------------------------------------------------------------- switches

static void announce(Switch &s);
static void publishState(Switch &s);
static void saveSwitchList();

static Switch *findSwitch(uint16_t addr) {
    for (uint8_t i = 0; i < nSwitches; i++)
        if (switches[i].addr == addr) return &switches[i];
    return nullptr;
}

static Switch *learnSwitch(uint16_t addr, bool persist) {
    Switch *s = findSwitch(addr);
    if (s) return s;
    if (addr == 0 || addr >= 0x8000 || isOurs(addr) || excluded(addr)) return nullptr;
    if (nSwitches >= MAX_SWITCHES) return nullptr;
    s = &switches[nSwitches++];
    memset(s, 0, sizeof(*s));
    s->addr = addr;
    s->onoff = -1;
    s->level = -1;
    s->motionLevel = -1;
    s->motionFloor = -1;
    Serial.printf("[sw] learned switch 0x%04x (%u known)\n", addr, nSwitches);
    if (persist) saveSwitchList();
    announce(*s);
    return s;
}

static void saveSwitchList() {
    uint16_t list[MAX_SWITCHES];
    for (uint8_t i = 0; i < nSwitches; i++) list[i] = switches[i].addr;
    prefs.putBytes("sw", list, nSwitches * sizeof(uint16_t));
}

static void loadSwitchList() {
    static const uint16_t seed[] = SWITCH_SEED;
    for (size_t i = 0; i < sizeof(seed) / sizeof(seed[0]); i++) learnSwitch(seed[i], false);
    uint16_t list[MAX_SWITCHES];
    size_t n = prefs.getBytes("sw", list, sizeof(list)) / sizeof(uint16_t);
    for (size_t i = 0; i < n; i++) learnSwitch(list[i], false);
}

static int briOf(int16_t level) { return (int)((level * 255L + 500) / 1000); }

static void publishState(Switch &s) {
    char t[64], v[16];
    if (s.onoff >= 0) {
        swTopic(t, sizeof(t), s.addr, "state");
        mqttPub(t, s.onoff ? "ON" : "OFF", true);
    }
    if (s.level >= 0) {
        swTopic(t, sizeof(t), s.addr, "brightness");
        snprintf(v, sizeof(v), "%d", briOf(s.level));
        mqttPub(t, v, true);
    }
    if (s.motionLevel >= 0) {
        swTopic(t, sizeof(t), s.addr, "motion");
        mqttPub(t, s.motionOn ? "ON" : "OFF", true);
        swTopic(t, sizeof(t), s.addr, "motion_level");
        snprintf(v, sizeof(v), "%d", s.motionLevel);
        mqttPub(t, v, true);
    }
}

// Home Assistant MQTT discovery: one device per switch, three entities.
static void announce(Switch &s) {
    if (!mqtt.connected() || s.announced) return;
    char topic[128], payload[720], avty[80], devj[260];
    bridgeTopic(avty, sizeof(avty), "status");
    snprintf(devj, sizeof(devj),
             "\"dev\":{\"ids\":[\"%s_%s_%04x\"],\"name\":\"%s switch %04x\","
             "\"mf\":\"Brilliant\",\"mdl\":\"Smart Dimmer Switch\",\"via_device\":\"%s_bridge_%s\"}",
             cfg.mqttBase, netHex, s.addr, cfg.label, s.addr, cfg.mqttBase, chipHex);

    snprintf(topic, sizeof(topic), "%s/light/%s_%s_%04x/config", HA_PREFIX, cfg.mqttBase, netHex, s.addr);
    snprintf(payload, sizeof(payload),
             "{\"name\":null,\"uniq_id\":\"%s_%s_%04x_light\",\"obj_id\":\"%s_%s_%04x\","
             "\"~\":\"%s/%s/%04x\",\"stat_t\":\"~/state\",\"cmd_t\":\"~/set\","
             "\"bri_stat_t\":\"~/brightness\",\"bri_cmd_t\":\"~/brightness/set\",\"bri_scl\":255,"
             "\"on_cmd_type\":\"first\",\"avty_t\":\"%s\",%s}",
             cfg.mqttBase, netHex, s.addr, cfg.mqttBase, netShort, s.addr, cfg.mqttBase, netHex, s.addr, avty, devj);
    mqtt.publish(topic, payload, true);

    snprintf(topic, sizeof(topic), "%s/binary_sensor/%s_%s_%04x_motion/config", HA_PREFIX, cfg.mqttBase, netHex, s.addr);
    snprintf(payload, sizeof(payload),
             "{\"name\":\"Motion\",\"uniq_id\":\"%s_%s_%04x_motion\",\"obj_id\":\"%s_%s_%04x_motion\","
             "\"dev_cla\":\"motion\",\"stat_t\":\"%s/%s/%04x/motion\",\"avty_t\":\"%s\",%s}",
             cfg.mqttBase, netHex, s.addr, cfg.mqttBase, netShort, s.addr, cfg.mqttBase, netHex, s.addr, avty, devj);
    mqtt.publish(topic, payload, true);

    snprintf(topic, sizeof(topic), "%s/sensor/%s_%s_%04x_motion_level/config", HA_PREFIX, cfg.mqttBase, netHex, s.addr);
    snprintf(payload, sizeof(payload),
             "{\"name\":\"Motion level\",\"uniq_id\":\"%s_%s_%04x_motion_level\","
             "\"obj_id\":\"%s_%s_%04x_motion_level\",\"ent_cat\":\"diagnostic\",\"stat_cla\":\"measurement\","
             "\"stat_t\":\"%s/%s/%04x/motion_level\",\"avty_t\":\"%s\",%s}",
             cfg.mqttBase, netHex, s.addr, cfg.mqttBase, netShort, s.addr, cfg.mqttBase, netHex, s.addr, avty, devj);
    mqtt.publish(topic, payload, true);

    s.announced = true;
    publishState(s);
}

static void announceBridge() {
    char topic[128], payload[420], st[80], px[80];
    bridgeTopic(st, sizeof(st), "status");
    bridgeTopic(px, sizeof(px), "proxy");
    snprintf(topic, sizeof(topic), "%s/sensor/%s_bridge_%s_proxy/config", HA_PREFIX, cfg.mqttBase, chipHex);
    snprintf(payload, sizeof(payload),
             "{\"name\":\"Proxy node\",\"uniq_id\":\"%s_bridge_%s_proxy\",\"obj_id\":\"%s_bridge_%s_proxy\","
             "\"ent_cat\":\"diagnostic\",\"stat_t\":\"%s\",\"avty_t\":\"%s\","
             "\"dev\":{\"ids\":[\"%s_bridge_%s\"],\"name\":\"%s bridge %s\","
             "\"mf\":\"home-hub\",\"mdl\":\"ESP32 mesh proxy client\",\"sw\":\"net %s\"}}",
             cfg.mqttBase, chipHex, cfg.mqttBase, chipHex, px, st, cfg.mqttBase, chipHex, cfg.label, chipHex, netHex);
    mqtt.publish(topic, payload, true);
}

static void setMotion(Switch &s, int level) {
    uint32_t now = millis();
    bool changedLevel = (s.motionLevel != level);
    bool first = (s.motionLevel < 0);
    s.motionLevel = level;
    if (s.motionFloor < 0 || level < s.motionFloor) {
        s.motionFloor = level;
        s.floorAt = now;
    } else if (now - s.floorAt > 60000 && s.motionFloor < level) {
        s.motionFloor++;
        s.floorAt = now;
    }
    bool wasOn = s.motionOn;
    if (level - s.motionFloor > MOTION_ON_ABOVE) {
        s.motionActiveAt = now;
        s.motionOn = true;
    }
    char t[64], v[16];
    if (changedLevel) {
        swTopic(t, sizeof(t), s.addr, "motion_level");
        snprintf(v, sizeof(v), "%d", level);
        mqttPub(t, v, true);
    }
    if (s.motionOn != wasOn) {
        Serial.printf("[motion] 0x%04x ON (level %d, floor %d)\n", s.addr, level, s.motionFloor);
        swTopic(t, sizeof(t), s.addr, "motion");
        mqttPub(t, "ON", true);
    } else if (first) {
        swTopic(t, sizeof(t), s.addr, "motion");
        mqttPub(t, s.motionOn ? "ON" : "OFF", true);
    }
}

// A switch published a vendor field on its own (to all-nodes). Logged, not
// acted on: field 0x0c turned out to be an on/off notice (0 on off, 1 on on or
// on any command received), and the motion signal is the polled/published
// field 0x13 handled by setMotion().
static void vendorPublished(Switch &s, uint8_t field, int value) {
    Serial.printf("[vendor] 0x%04x published field 0x%02x = %d\n", s.addr, field, value);
}

static void expireMotion() {
    uint32_t now = millis();
    for (uint8_t i = 0; i < nSwitches; i++) {
        Switch &s = switches[i];
        if (s.motionOn && now - s.motionActiveAt > MOTION_HOLD_MS) {
            s.motionOn = false;
            Serial.printf("[motion] 0x%04x off\n", s.addr);
            char t[64];
            swTopic(t, sizeof(t), s.addr, "motion");
            mqttPub(t, "OFF", true);
        }
    }
}

// ---------------------------------------------------------------- tx

// One proxy PDU per ATT write, or SAR-segmented when the link's MTU is small
// (MTU negotiation fails on some links and leaves the default 23, where a
// Level Set no longer fits in one write).
static void proxySend(uint8_t type, const uint8_t *pdu, size_t len) {
    if (!chIn || !connected) return;
    uint16_t mtu = bleClient ? bleClient->getMTU() : 23;
    if (mtu < 23) mtu = 23;
    const size_t room = min((size_t)(mtu - 4), (size_t)64);
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

// Send an access message under the panel appkey. Unsegmented only: everything
// we send (OnOff Set, Level Set, vendor Get) fits in 11 access bytes.
static bool sendAccess(uint16_t dst, const uint8_t *access, size_t alen) {
    if (!linkUp) return false;
    uint32_t seq = nextSeq();
    uint8_t upper[32];
    size_t ulen = mesh_app_encrypt(cfg.appKey, false, txIv(), seq, srcAddr(), dst,
                                   access, alen, upper);
    if (!ulen || ulen > 15) {
        Serial.println("[tx] access too large for unsegmented, dropped");
        return false;
    }
    uint8_t lower[32];
    lower[0] = 0x40 | (appAid & 0x3F);  // AKF=1
    memcpy(lower + 1, upper, ulen);
    uint8_t npdu[48];
    size_t nlen = mesh_net_encrypt(cfg.netKey, txIv(), 0, TX_TTL, seq, srcAddr(), dst,
                                   lower, ulen + 1, 0x00, npdu);
    if (!nlen) return false;
    proxySend(0x00, npdu, nlen);
    return true;
}

static void sendSegAck(uint16_t dst, uint16_t seqzero, uint32_t block) {
    uint8_t t[7];
    t[0] = 0x00;
    uint16_t sz = (seqzero << 2) & 0x7FFF;
    t[1] = sz >> 8;
    t[2] = sz & 0xFF;
    t[3] = block >> 24;
    t[4] = block >> 16;
    t[5] = block >> 8;
    t[6] = block;
    uint32_t seq = nextSeq();
    uint8_t npdu[48];
    size_t n = mesh_net_encrypt(cfg.netKey, txIv(), 1, TX_TTL, seq, srcAddr(), dst, t, 7,
                                0x00, npdu);
    if (n) proxySend(0x00, npdu, n);
}

static void setProxyFilter() {
    uint32_t seq = nextSeq();
    const uint8_t filt[2] = {0x00, 0x01};  // Set Filter Type = reject list (empty): forward everything
    uint8_t npdu[48];
    size_t nlen = mesh_net_encrypt(cfg.netKey, txIv(), 1, 0, seq, srcAddr(), 0x0000, filt, 2,
                                   0x03, npdu);
    if (nlen) proxySend(0x02, npdu, nlen);
    lastFilterAt = millis();
}

static void cmdOnOff(uint16_t dst, bool on) {
    uint8_t a[4] = {0x82, 0x02, (uint8_t)(on ? 1 : 0), ++tidCounter};
    sendAccess(dst, a, sizeof(a));
    Serial.printf("[cmd] 0x%04x -> %s\n", dst, on ? "on" : "off");
}

// Captured from the panel: Generic Level Set with the level on a 0-1000 scale
// (NOT the SIG -32768..32767 mapping), transition 0x05, delay 0x00.
static void cmdLevel(uint16_t dst, int pct) {
    pct = constrain(pct, 0, 100);
    uint16_t lvl = (uint16_t)(pct * 10);
    uint8_t a[7] = {0x82, 0x06, (uint8_t)(lvl & 0xFF), (uint8_t)(lvl >> 8), ++tidCounter, 0x05, 0x00};
    sendAccess(dst, a, sizeof(a));
    Serial.printf("[cmd] 0x%04x -> dim %d%% (raw %u)\n", dst, pct, lvl);
}

static void pollMotion(uint16_t dst) {
    uint8_t a[5] = {0xC1, (uint8_t)(VENDOR_CID & 0xFF), (uint8_t)(VENDOR_CID >> 8), 0x11,
                    VENDOR_MOTION_FIELD};
    sendAccess(dst, a, sizeof(a));
}

// Discovery: one Get to all-nodes makes every OnOff server answer, which is
// how switches we have never heard of get learned. Replies collide when a
// dozen answer at once, so state is NOT trusted to this; resyncStep() asks
// each known switch on its own afterwards.
static void sweepAll() {
    const uint8_t onoffGet[2] = {0x82, 0x01};
    sendAccess(0xFFFF, onoffGet, 2);
    resyncIdx = 0;
    lastResyncAt = millis();
}

static void resyncStep() {
    if (resyncIdx >= nSwitches) {
        resyncIdx = 0xFF;
        return;
    }
    if (millis() - lastResyncStepAt < 300) return;
    lastResyncStepAt = millis();
    const uint8_t onoffGet[2] = {0x82, 0x01};
    const uint8_t levelGet[2] = {0x82, 0x05};
    uint16_t a = switches[resyncIdx++].addr;
    sendAccess(a, onoffGet, 2);
    delay(60);
    sendAccess(a, levelGet, 2);
}

// ---------------------------------------------------------------- rx

static bool seenBefore(uint16_t src, uint32_t seq) {
    for (uint8_t i = 0; i < nSeen; i++) {
        if (seen[i].src != src) continue;
        if (seq <= seen[i].seq) return true;
        seen[i].seq = seq;
        return false;
    }
    if (nSeen < sizeof(seen) / sizeof(seen[0])) {
        seen[nSeen].src = src;
        seen[nSeen].seq = seq;
        nSeen++;
    }
    return false;
}

static void publishEvent(uint16_t src, uint16_t dst, uint32_t op, bool vendor, const uint8_t *params,
                         size_t plen) {
    char hex[2 * 40 + 1] = {0};
    if (plen > 40) plen = 40;
    hexstr(params, plen, hex);
    char topic[64], payload[200];
    swTopic(topic, sizeof(topic), src, "event");
    snprintf(payload, sizeof(payload),
             "{\"src\":\"0x%04x\",\"dst\":\"0x%04x\",\"opcode\":\"0x%06lx\",\"kind\":\"%s\",\"params\":\"%s\"}",
             src, dst, (unsigned long)op, vendor ? "vendor" : "sig", hex);
    Serial.printf("[rx] %s %s\n", topic, payload);
    mqttPub(topic, payload, false);
}

static void handleAccess(uint16_t src, uint16_t dst, const uint8_t *a, size_t n) {
    uint32_t op;
    size_t olen;
    if (!(a[0] & 0x80)) {
        op = a[0];
        olen = 1;
    } else if ((a[0] & 0xC0) == 0x80) {
        op = ((uint32_t)a[0] << 8) | a[1];
        olen = 2;
    } else {
        op = ((uint32_t)a[0] << 16) | ((uint32_t)a[1] << 8) | a[2];
        olen = 3;
    }
    if (n < olen) return;
    const uint8_t *p = a + olen;
    size_t plen = n - olen;
    bool vendor = (olen == 3);

    Switch *s = nullptr;
    if (op == 0x8204 || op == 0x8208) s = learnSwitch(src, true);
    else s = findSwitch(src);
    if (s) s->seenAt = millis();

    if (op == 0x8204 && plen >= 1 && s) {            // Generic OnOff Status
        int8_t now = p[0] ? 1 : 0;
        if (s->onoff != now) {
            // The motion level's resting value moves with the load (the PIR sits
            // next to the triac: ~0 lamp off, ~130 lamp full), so the floor is
            // re-learned after any on/off rather than crept toward.
            s->motionFloor = -1;
        }
        s->onoff = now;
        char t[64];
        swTopic(t, sizeof(t), s->addr, "state");
        mqttPub(t, s->onoff ? "ON" : "OFF", true);
    } else if (op == 0x8208 && plen >= 2 && s) {     // Generic Level Status, 0-1000
        int16_t lvl = (int16_t)(p[0] | (p[1] << 8));
        s->level = constrain(lvl, 0, 1000);
        char t[64], v[8];
        swTopic(t, sizeof(t), s->addr, "brightness");
        snprintf(v, sizeof(v), "%d", briOf(s->level));
        mqttPub(t, v, true);
    } else if (vendor && a[1] == (VENDOR_CID & 0xFF) && a[2] == (VENDOR_CID >> 8) && plen >= 3) {
        uint8_t cmd = p[0], field = p[1];
        int value = p[2] | (plen >= 4 ? (p[3] << 8) : 0);
        if ((cmd == 0x13 || cmd == 0x03) && field == VENDOR_MOTION_FIELD && s) {
            if (value >= 0xFF00) return;                 // 0xffff: the switch has no reading right now
            static int lastRaw[MAX_SWITCHES];
            if (lastRaw[s - switches] != value) {
                char hex[24];
                hexstr(p + 2, min(plen - 2, (size_t)8), hex);
                Serial.printf("[motion raw] 0x%04x field 13 = %s\n", src, hex);
                lastRaw[s - switches] = value;
            }
            setMotion(*s, value);
            return;                                  // poll replies are not events
        }
        if (cmd == 0x13 && dst >= 0xC000 && s) vendorPublished(*s, field, value);
    }
    publishEvent(src, dst, op, vendor, p, plen);
}

static bool netDecrypt(const uint8_t *pdu, size_t len, MeshNetMsg *m) {
    // The IVI bit says which of the two live IV indexes the sender used.
    uint8_t ivi = pdu[0] >> 7;
    if ((ivIndex & 1) == ivi && mesh_net_decrypt(cfg.netKey, ivIndex, pdu, len, m)) return true;
    if (ivIndex > 0 && ((ivIndex - 1) & 1) == ivi && mesh_net_decrypt(cfg.netKey, ivIndex - 1, pdu, len, m))
        return true;
    return false;
}

static void handleNetworkPdu(const uint8_t *pdu, size_t len) {
    MeshNetMsg m;
    if (!netDecrypt(pdu, len, &m)) return;
    if (isOurs(m.src)) return;
    if (seenBefore(m.src, m.seq)) return;
    if (m.ctl) return;  // segment acks, heartbeats, friendship: nothing for us
    if (m.tlen < 2) return;

    bool akf = (m.transport[0] >> 6) & 1;
    if (!akf) return;   // devkey-encrypted config traffic, not ours to read

    const uint8_t *body;
    size_t blen;
    uint32_t seqAuth;
    uint8_t taglen;
    uint8_t joined[8 * 12];

    if (m.transport[0] & 0x80) {
        if (m.tlen < 5) return;
        uint32_t hdr = ((uint32_t)m.transport[1] << 16) | ((uint32_t)m.transport[2] << 8) | m.transport[3];
        uint8_t szmic = (hdr >> 23) & 1;
        uint16_t seqzero = (hdr >> 10) & 0x1FFF;
        uint8_t sego = (hdr >> 5) & 0x1F, segn = hdr & 0x1F;
        if (segn >= 8) return;
        Reasm *r = nullptr;
        for (auto &x : reasm)
            if (x.used && x.src == m.src && x.seqzero == seqzero) r = &x;
        if (!r) {
            for (auto &x : reasm) {
                if (!x.used || millis() - x.at > 10000) { r = &x; break; }
            }
            if (!r) return;
            memset(r, 0, sizeof(*r));
            r->used = true;
            r->src = m.src;
            r->seqzero = seqzero;
            r->segn = segn;
            r->szmic = szmic;
        }
        r->at = millis();
        size_t sl = m.tlen - 4;
        if (sl > 12) sl = 12;
        memcpy(r->data + sego * 12, m.transport + 4, sl);
        r->lens[sego] = sl;
        r->mask |= (1UL << sego);
        uint32_t all = (1UL << (segn + 1)) - 1;
        if (r->mask != all) return;
        sendSegAck(m.src, seqzero, all);
        blen = 0;
        for (uint8_t i = 0; i <= segn; i++) {
            memcpy(joined + blen, r->data + i * 12, r->lens[i]);
            blen += r->lens[i];
        }
        r->used = false;
        body = joined;
        // SeqAuth: the first segment's SEQ, reconstructed from this one's
        uint32_t base = (m.seq & ~0x1FFFUL) | seqzero;
        seqAuth = ((m.seq & 0x1FFF) < seqzero) ? base - 0x2000 : base;
        taglen = szmic ? 8 : 4;
    } else {
        body = m.transport + 1;
        blen = m.tlen - 1;
        seqAuth = m.seq;
        taglen = 4;
    }

    uint8_t out[8 * 12];
    size_t olen;
    // Try the IV the network layer accepted, in the same order.
    uint32_t iv = ((ivIndex & 1) == (pdu[0] >> 7)) ? ivIndex : ivIndex - 1;
    if (!mesh_app_decrypt(cfg.appKey, false, iv, seqAuth, m.src, m.dst, body, blen, taglen, out, &olen))
        return;
    handleAccess(m.src, m.dst, out, olen);
}

// Secure Network Beacon: flags, network id, iv index, auth. Authenticated
// under the netkey, so it is the one thing we trust to move the IV index.
static void handleBeacon(const uint8_t *p, size_t n) {
    if (n != 22 || p[0] != 0x01) return;
    if (memcmp(p + 2, ourNetId, 8) != 0) return;
    if (!mesh_beacon_verify(cfg.netKey, p + 1)) {
        Serial.println("[beacon] our network id but bad auth; ignored");
        return;
    }
    bool upd = (p[1] >> 1) & 1;
    uint32_t iv = ((uint32_t)p[10] << 24) | ((uint32_t)p[11] << 16) | ((uint32_t)p[12] << 8) | p[13];
    if (iv != ivIndex || upd != ivUpdating) {
        Serial.printf("[beacon] iv index %lu -> %lu (update %s)\n", (unsigned long)ivIndex,
                      (unsigned long)iv, upd ? "in progress" : "done");
        if (iv > ivIndex) {
            txSeq = 0;
            prefs.putUInt("seq", 0);
            nSeen = 0;
        }
        ivIndex = iv;
        ivUpdating = upd;
        prefs.putUInt("iv", ivIndex);
        char v[16];
        snprintf(v, sizeof(v), "%lu", (unsigned long)ivIndex);
        char t[80];
        bridgeTopic(t, sizeof(t), "iv");
        mqttPub(t, v, true);
    }
}

static void notifyCb(NimBLERemoteCharacteristic *c, uint8_t *data, size_t len, bool isNotify) {
    if (len < 1) return;
    uint8_t sar = (data[0] & 0xC0) >> 6;
    uint8_t type = data[0] & 0x3F;
    const uint8_t *p = data + 1;
    size_t n = len - 1;
    RxItem it;
    it.type = type;
    if (sar == 0b00) {
        if (n > sizeof(it.data)) return;
        it.len = n;
        memcpy(it.data, p, n);
        xQueueSend(rxq, &it, 0);
        return;
    }
    if (sar == 0b01) sarLen = 0;
    if (sarLen + n <= sizeof(sarBuf)) {
        memcpy(sarBuf + sarLen, p, n);
        sarLen += n;
    }
    if (sar == 0b11) {
        if (sarLen <= sizeof(it.data)) {
            it.len = sarLen;
            memcpy(it.data, sarBuf, sarLen);
            xQueueSend(rxq, &it, 0);
        }
        sarLen = 0;
    }
}

static void drainRx() {
    RxItem it;
    while (xQueueReceive(rxq, &it, 0) == pdTRUE) {
        lastRxAt = millis();
        switch (it.type) {
        case 0x00: handleNetworkPdu(it.data, it.len); break;
        case 0x01: handleBeacon(it.data, it.len); break;
        case 0x02: {
            char h[200];
            hexstr(it.data, min((size_t)it.len, (size_t)96), h);
            Serial.printf("[proxy] config status %s\n", h);
            break;
        }
        default: break;
        }
    }
}

// ---------------------------------------------------------------- ble

class ClientCb : public NimBLEClientCallbacks {
    void onConnect(NimBLEClient *c) override { connected = true; }
    void onDisconnect(NimBLEClient *c) override {
        connected = false;
        linkUp = false;
        chIn = nullptr;
        Serial.println("[ble] disconnected");
    }
};

// Strongest node advertising the panel's Network ID, or the pinned one.
static bool findProxy() {
    NimBLEScan *scan = NimBLEDevice::getScan();
    Serial.println("[ble] scanning 6s for a panel proxy...");
    NimBLEScanResults res = scan->start(6, false);
    int bestScore = -999;
    bool found = false;
    NimBLEAddress bestAddr;
    int bestRssi = 0;
    for (int i = 0; i < res.getCount(); i++) {
        NimBLEAdvertisedDevice dev = res.getDevice(i);
        if (!dev.haveServiceData()) continue;
        for (int k = 0; k < (int)dev.getServiceDataCount(); k++) {
            if (!dev.getServiceDataUUID(k).equals(SVC_PROXY)) continue;
            std::string sd = dev.getServiceData(k);
            if (sd.size() < 9 || sd[0] != 0x00) continue;               // Network ID beacon
            if (memcmp(sd.data() + 1, ourNetId, 8) != 0) continue;
            bool pinned = strlen(PANEL_NODE) && !strcasecmp(dev.getAddress().toString().c_str(), PANEL_NODE);
            Serial.printf("[ble]   %s rssi %d%s\n", dev.getAddress().toString().c_str(), dev.getRSSI(),
                          pinned ? " (pinned)" : "");
            int score = pinned ? 1000 : dev.getRSSI();
            if (score > bestScore) {
                bestScore = score;
                bestAddr = dev.getAddress();
                bestRssi = dev.getRSSI();
                found = true;
            }
        }
    }
    scan->clearResults();
    if (!found) {
        Serial.println("[ble] no panel-network proxy in range");
        return false;
    }
    targetAddr = bestAddr;
    haveTarget = true;
    snprintf(proxyDesc, sizeof(proxyDesc), "%s rssi %d", bestAddr.toString().c_str(), bestRssi);
    Serial.printf("[ble] -> %s\n", proxyDesc);
    return true;
}

static bool connectToNode() {
    if (!haveTarget) return false;
    Serial.println("[ble] connecting...");
    if (!bleClient) {
        bleClient = NimBLEDevice::createClient();
        bleClient->setClientCallbacks(new ClientCb(), false);
        // 50-100 ms connection interval (units of 1.25 ms), 4 s supervision
        // timeout: plenty for a few mesh PDUs a second, and it leaves the
        // WiFi side of the shared radio room to breathe.
        bleClient->setConnectionParams(40, 80, 0, 400);
        bleClient->setConnectTimeout(10);
    }
    if (!bleClient->connect(targetAddr)) {
        Serial.println("[ble] connect failed");
        return false;
    }
    Serial.printf("[ble] mtu %u\n", bleClient->getMTU());
    NimBLERemoteService *svc = bleClient->getService(SVC_PROXY);
    if (!svc) {
        Serial.println("[ble] no proxy service");
        bleClient->disconnect();
        return false;
    }
    chIn = svc->getCharacteristic(CH_IN);
    NimBLERemoteCharacteristic *chOut = svc->getCharacteristic(CH_OUT);
    if (!chIn || !chOut) {
        Serial.println("[ble] missing proxy characteristics");
        bleClient->disconnect();
        return false;
    }
    if (!chOut->subscribe(true, notifyCb)) {
        Serial.println("[ble] subscribe failed");
        bleClient->disconnect();
        return false;
    }
    connected = true;
    delay(300);
    setProxyFilter();
    linkUp = true;
    linkUpAt = lastRxAt = millis();
    lightSet(Light::Heard);
    sweepsDone = 0;
    Serial.println("[ble] bridge up: filter opened");
    char t[80];
    bridgeTopic(t, sizeof(t), "proxy");
    mqttPub(t, proxyDesc, true);
    return true;
}

static void dropLink(const char *why) {
    lightSet(Light::Looking);
    Serial.printf("[ble] dropping link: %s\n", why);
    linkUp = false;
    if (bleClient && bleClient->isConnected()) bleClient->disconnect();
    connected = false;
    chIn = nullptr;
    haveTarget = false;
}

// ---------------------------------------------------------------- mqtt

static void mqttCb(char *topic, uint8_t *payload, unsigned int len) {
    char msg[32] = {0};
    memcpy(msg, payload, min((unsigned int)31, len));
    char t[128];
    strlcpy(t, topic, sizeof(t));

    // <base>/<net>/<addr>/<leaf>, and only for our own network
    char prefix[40];
    snprintf(prefix, sizeof(prefix), "%s/%s/", cfg.mqttBase, netHex);
    size_t plen = strlen(prefix);
    if (strncmp(t, prefix, plen)) return;
    char *end = nullptr;
    unsigned long addr = strtoul(t + plen, &end, 16);
    if (!end || *end != '/' || addr == 0 || addr >= 0x8000) return;
    const char *leaf = end + 1;

    if (!strcmp(leaf, "set")) {
        if (!strcasecmp(msg, "on") || !strcasecmp(msg, "off")) {
            cmdOnOff(addr, !strcasecmp(msg, "on"));
        } else if (!strncasecmp(msg, "dim:", 4)) {
            cmdLevel(addr, atoi(msg + 4));
        }
    } else if (!strcmp(leaf, "brightness/set")) {
        int bri = constrain(atoi(msg), 0, 255);
        cmdLevel(addr, (bri * 100 + 127) / 255);
    }
}

static void mqttReconnect() {
    if (mqtt.connected()) return;
    static uint32_t last = 0;
    if (millis() - last < 5000) return;
    last = millis();
    char id[40], will[80];
    snprintf(id, sizeof(id), "%s-bridge-%s", cfg.mqttBase, chipHex);
    bridgeTopic(will, sizeof(will), "status");
    bool ok = mqtt.connect(id, cfg.mqttUser[0] ? cfg.mqttUser : nullptr,
                           cfg.mqttUser[0] ? cfg.mqttPass : nullptr, will, 0, true, "offline");
    if (!ok) {
        Serial.printf("[mqtt] connect failed (rc %d)\n", mqtt.state());
        return;
    }
    mqtt.publish(will, "online", true);
    char sub[80];
    snprintf(sub, sizeof(sub), "%s/%s/+/set", cfg.mqttBase, netHex);
    mqtt.subscribe(sub);
    snprintf(sub, sizeof(sub), "%s/%s/+/brightness/set", cfg.mqttBase, netHex);
    mqtt.subscribe(sub);
    Serial.printf("[mqtt] connected as %s, commands on %s\n", id, sub);
    announceBridge();
    char t[80], v[16];
    bridgeTopic(t, sizeof(t), "proxy");
    mqtt.publish(t, linkUp ? proxyDesc : "none", true);
    bridgeTopic(t, sizeof(t), "iv");
    snprintf(v, sizeof(v), "%lu", (unsigned long)ivIndex);
    mqtt.publish(t, v, true);
    // Which mesh this puck carries, so the hub can count the switches that are this bridge's and not
    // another's (brain/hub/bridge.py reads it off the broker while the puck is being placed).
    bridgeTopic(t, sizeof(t), "net");
    mqtt.publish(t, netHex, true);
    for (uint8_t i = 0; i < nSwitches; i++) {
        switches[i].announced = false;
        announce(switches[i]);
        mqtt.loop();
    }
}

// ---------------------------------------------------------------- lifecycle

// One line for the hub's `status`, key=value so it can be read without a parser, and kept
// short: the CDC link drops the middle of long lines (see reply() in config.cpp). The proxy's
// address is on MQTT already; only its signal strength is worth the bytes here.
void bridgeStatusLine(char *out, size_t n) {
    static const char *LIGHTS[] = {"off", "looking", "heard", "far"};
    // No String temporaries here: this runs on the serial task's stack.
    char ip[20] = "down";
    if (WiFi.status() == WL_CONNECTED) {
        IPAddress a = WiFi.localIP();
        snprintf(ip, sizeof(ip), "%u.%u.%u.%u", a[0], a[1], a[2], a[3]);
    }
    int rssi = 0;
    if (linkUp) { const char *r = strstr(proxyDesc, "rssi "); if (r) rssi = atoi(r + 5); }
    snprintf(out, n, "status wifi=%s mqtt=%s rssi=%d sw=%u light=%s", ip,
             mqtt.connected() ? "up" : "down", rssi, (unsigned)nSwitches, LIGHTS[(int)lightGet() & 3]);
}

void setup() {
#if ARDUINO_USB_CDC_ON_BOOT && ARDUINO_USB_MODE
    // The S3's hardware CDC has a 256-byte send ring by default; the boot log fills it in an instant
    // and the core drops what does not fit. Room for a whole burst. (The torn replies to the hub were
    // a different fault -- see reply() in config.cpp -- this only stops the log eating itself.)
    Serial.setTxBufferSize(4096);
#endif
    Serial.begin(115200);
    delay(300);
    Serial.println("\n=== Brilliant panel mesh -> MQTT bridge " BRIDGE_FW " ===");

    // Who we are and what we were told, before anything else looks at either.
    configLoad();
    lightBegin();
    lightSet(Light::Looking);

    prefs.begin("meshbridge", false);
    addrGen = prefs.getUShort("gen", 0);
    txSeq = prefs.getUInt("seq", 0) + 512;  // skip past anything unsaved at the last reset
    prefs.putUInt("seq", txSeq);
    ivIndex = prefs.getUInt("iv", cfg.ivIndex);
    if (ivIndex < cfg.ivIndex) ivIndex = cfg.ivIndex;   // the config was rewritten with a newer IV

    Serial.println("crypto self-test:");
    if (!mesh_selftest(Serial)) Serial.println("  !! CRYPTO BROKEN -- do not trust results");

    mesh_k3(cfg.netKey, ourNetId);
    hexstr(ourNetId, 8, netHex);
    memcpy(netShort, netHex, 4);
    netShort[4] = 0;
    appAid = mesh_k4(cfg.appKey);
    // Puck identity from the factory MAC: six hex digits, and a mesh address block.
    uint64_t mac = ESP.getEfuseMac();
    uint32_t chip = (uint32_t)((mac ^ (mac >> 24)) & 0xFFFFFF);
    snprintf(chipHex, sizeof(chipHex), "%06lx", (unsigned long)chip);
#ifdef BRIDGE_ADDR
    bridgeBase = BRIDGE_ADDR;
#else
    bridgeBase = 0x7000 | ((chip & 0xFF) << 4);
#endif
    configSerialBegin(chipHex);   // the hub can talk to us from here on, whatever else happens below
    if (configBlank()) {
        // Nothing written yet: a board straight off the shipped image. There is nothing to connect to,
        // so this is the end of setup -- the puck sits on the cable, blinking amber, waiting to be told.
        Serial.printf("puck %s   blank: waiting for the hub on the cable\n", chipHex);
        return;
    }
    if (!cfg.haveKeys) Serial.println("[cfg] no mesh keys yet: Wi-Fi only until the hub hands them over");
    Serial.printf("network id %s   app aid 0x%02x   iv %lu\n", netHex, appAid, (unsigned long)ivIndex);
    Serial.printf("puck %s   our addr 0x%04x   seq %lu   poll every %d ms\n", chipHex, srcAddr(),
                  (unsigned long)txSeq, POLL_MS);

    rxq = xQueueCreate(24, sizeof(RxItem));
    loadSwitchList();

    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.onEvent([](WiFiEvent_t ev, WiFiEventInfo_t info) {
        if (ev == ARDUINO_EVENT_WIFI_STA_DISCONNECTED)
            Serial.printf("[wifi] disconnected (reason %d)\n", info.wifi_sta_disconnected.reason);
        else if (ev == ARDUINO_EVENT_WIFI_STA_GOT_IP)
            Serial.printf("[wifi] %s\n", WiFi.localIP().toString().c_str());
    });
    // Modem sleep must still be ON when the BT controller starts (its
    // coexistence layer aborts otherwise); it is turned off after BLE init.
    WiFi.begin(cfg.ssid, cfg.pass);
    Serial.print("[wifi] connecting");
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();
    if (WiFi.status() == WL_CONNECTED)
        Serial.printf("[wifi] %s\n", WiFi.localIP().toString().c_str());
    else
        Serial.println("[wifi] not yet connected; will keep trying");

    mqtt.setServer(cfg.mqttHost, cfg.mqttPort);
    mqtt.setBufferSize(1024);   // discovery payloads are bigger than the 256-byte default
    mqtt.setKeepAlive(60);      // a stalled second or two on the shared radio must not drop the session
    mqtt.setSocketTimeout(5);
    mqtt.setCallback(mqttCb);

    NimBLEDevice::init("mesh-bridge");
    NimBLEDevice::setMTU(69);
    // WiFi and BLE share one radio. Modem sleep has to stay on (the driver
    // aborts otherwise), so the WiFi side is protected two other ways: it is
    // preferred by the coexistence scheduler, and the BLE link asks for a long
    // connection interval (see connectToNode) so it does not hog the air.
    esp_coex_preference_set(ESP_COEX_PREFER_WIFI);
    NimBLEScan *scan = NimBLEDevice::getScan();
    scan->setActiveScan(true);
    scan->setInterval(100);
    scan->setWindow(99);
}

// How many scans in a row found no switch at all. Three (about half a minute) is
// long enough to say "too far" to somebody standing at a socket, and short enough
// that they are still standing there.
static uint8_t emptyScans = 0;

void loop() {
    if (configBlank()) {   // waiting for the hub; the serial task is doing the work
        delay(200);
        return;
    }
    if (WiFi.status() == WL_CONNECTED) {
        mqttReconnect();
        mqtt.loop();
    }
    if (!cfg.haveKeys) {   // on the Wi-Fi, nothing to say on the mesh yet
        delay(200);
        return;
    }

    if (!connected) {
        linkUp = false;
        if (!haveTarget && !findProxy()) {
            if (emptyScans < 3) emptyScans++;
            lightSet(emptyScans >= 3 ? Light::Far : Light::Looking);
            delay(2000);
            return;
        }
        emptyScans = 0;
        if (!connectToNode()) {
            haveTarget = false;
            delay(2000);
            return;
        }
    }

    drainRx();
    expireMotion();

    if (!linkUp) {
        delay(20);
        return;
    }
    uint32_t now = millis();

    if (now - lastRxAt > LINK_DEAD_MS) {
        dropLink("no proxy traffic for two minutes");
        return;
    }
    if (now - lastFilterAt > FILTER_MS) setProxyFilter();

    // Discovery sweeps just after the link comes up, then a slow resync.
    if (sweepsDone < 2 && now - linkUpAt > (sweepsDone == 0 ? 1000UL : 6000UL)) {
        sweepsDone++;
        Serial.println("[sweep] OnOff/Level Get -> all nodes");
        sweepAll();
    } else if (sweepsDone >= 2 && now - lastResyncAt > RESYNC_MS) {
        sweepAll();
    }
    if (resyncIdx != 0xFF) resyncStep();

    // Motion: one vendor Get per POLL_MS, round-robin over known switches.
    if (nSwitches && now - lastPollAt >= POLL_MS) {
        lastPollAt = now;
        if (pollIdx >= nSwitches) pollIdx = 0;
        pollMotion(switches[pollIdx].addr);
        pollIdx++;
    }
    delay(5);
}
