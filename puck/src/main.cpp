// The bridge puck: the hub's own small device on a socket.
//
// It is set up over its USB cable (src/config.h), finds the hub by name, by the last address that
// answered or by the one it was given, and keeps a spare Wi-Fi on the ring. It takes new firmware
// over the broker (src/fwupdate.h), listens for light strips knocking (src/ear.h), runs errands to
// the ones the hub cannot hear (src/errand.h), and has one light that says whether this spot is good
// and can be a nightlight (src/light.h, src/lightrule.h).
//
// A module can add a kind of device the puck bridges on top of that (src/module.h). The one that
// exists carries a Bluetooth mesh of wall switches, kept in a repository of its own and built in with
// -DPUCK_MESH (platformio.ini, private/*.ini); a puck
// without it is whole, and says so on `caps`.
//
// The puck is keyed by <chip>, six hex digits derived from its factory MAC.
//
// MQTT contract, the puck's own (the base is cfg.mqttBase, "mesh" unless the hub says otherwise):
//   mesh/bridge/<chip>/status          online | offline        (retained, LWT)
//   mesh/bridge/<chip>/caps            what it can do, words   (retained): light ear errand update [mesh]
//   mesh/bridge/<chip>/light           looking|heard|night|off  (retained)
//   mesh/bridge/<chip>/night           ON | OFF                 (retained)
//   mesh/bridge/<chip>/night/brightness  0-255                  (retained)
//   mesh/bridge/<chip>/settled         yes | no                 (retained)
//   mesh/bridge/<chip>/night/set       ON | OFF
//   mesh/bridge/<chip>/night/brightness/set  0-255
//   mesh/bridge/<chip>/night/lift/set  0-255, transient: see below
//   mesh/bridge/<chip>/settled/set     1 | 0
//   mesh/bridge/<chip>/fw              the version it runs      (retained)
//   mesh/bridge/<chip>/offer           an image from the hub    (retained; src/fwupdate.h)
//   mesh/bridge/<chip>/update          what it did with one     {json}
//   mesh/bridge/<chip>/heard           a strip knocking nearby (src/ear.h)
//   mesh/bridge/<chip>/errand/ask      an errand for the hub   (src/errand.h)
//   mesh/bridge/<chip>/cfg             wifi / spare, from the hub (retained); cfgack answers it
// HA discovery: the puck's own device <base>_bridge_<chip> carries its Nightlight (a light with
// brightness -- docs/puck-light.md) and a diagnostic saying what its LED is actually doing, which is
// a different question from what the nightlight is set to. A module adds its own.

#include <Arduino.h>
#include <NimBLEDevice.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <ESPmDNS.h>

#include "esp_coexist.h"
#include "ear.h"
#include "errand.h"
#include "config.h"
#include "release_keys.h"
#include "light.h"
#include "lightrule.h"
#include "fwupdate.h"
#include "module.h"
#include "puck.h"
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

// ---------------------------------------------------------------- state

WiFiClient wifiClient;
PubSubClient mqtt(wifiClient);
char chipHex[7] = "000000";   // this puck: derived from the factory MAC

// ---------------------------------------------------------------- helpers

void hexstr(const uint8_t *b, size_t n, char *out) {
    static const char *H = "0123456789abcdef";
    for (size_t i = 0; i < n; i++) {
        out[i * 2] = H[b[i] >> 4];
        out[i * 2 + 1] = H[b[i] & 0xF];
    }
    out[n * 2] = 0;
}

void mqttPub(const char *topic, const char *payload, bool retain) {
    if (mqtt.connected()) mqtt.publish(topic, payload, retain);
}

void bridgeTopic(char *out, size_t n, const char *leaf) {
    snprintf(out, n, "%s/bridge/%s/%s", cfg.mqttBase, chipHex, leaf);
}

// The puck's own device, as every discovery payload on it spells it. `sw` is the firmware it runs,
// which is what somebody looking at it in Home Assistant wants to know.
void bridgeDevice(char *out, size_t n) {
    snprintf(out, n,
             "\"dev\":{\"ids\":[\"%s_bridge_%s\"],\"name\":\"%s bridge %s\","
             "\"mf\":\"Elyir\",\"mdl\":\"%s\",\"sw\":\"%s\"}",
             cfg.mqttBase, chipHex, cfg.label, chipHex, mod_model(), BRIDGE_VERSION);
}

// The puck's own device in Home Assistant, and everything hanging off it.
//
// Three entities now, and the second is the point of docs/puck-light.md: the puck IS a light in the
// house, so the schedule, the "good night", the all-off and the room tile are all the house's own
// machinery and none of it has to be built here. Firmware holds one setting and the precedence.
//
// WHAT THE `night` ENTITY REPORTS IS THE SETTING, NOT THE LED. The two differ whenever the puck is
// unwell or unplaced -- lightRefresh() puts a fault above the nightlight -- and the setting is the
// honest thing to put on a switch somebody flips: report the LED instead and a puck that lost its
// broker would show its nightlight as "off", which is an invitation for an automation to turn it
// back "on" and for the household to wonder why nothing happens. What the LED is actually doing is
// the third entity, a diagnostic, which is also how you ask a settled puck whether it is well once
// green has stopped being the answer.
// The names the light's states go out under, on the broker and on the cable's `status` line. Indexed
// with & 7 and padded to eight: this was & 3 with four entries, and a fifth state would have masked
// itself silently onto "off".
static const char *LIGHT_NAMES[] = {"off", "looking", "heard", "far", "night", "?", "?", "?"};

static void announceBridge() {
    char topic[128], payload[640], st[80], devj[260];   // worst case: a 16-char base and a 24-char label
    bridgeTopic(st, sizeof(st), "status");
    bridgeDevice(devj, sizeof(devj));

    char base[80];
    bridgeTopic(base, sizeof(base), "night");
    snprintf(topic, sizeof(topic), "%s/light/%s_bridge_%s_night/config", HA_PREFIX, cfg.mqttBase, chipHex);
    snprintf(payload, sizeof(payload),
             "{\"name\":\"Nightlight\",\"uniq_id\":\"%s_bridge_%s_night\",\"obj_id\":\"%s_bridge_%s_night\","
             "\"~\":\"%s\",\"stat_t\":\"~\",\"cmd_t\":\"~/set\","
             "\"bri_stat_t\":\"~/brightness\",\"bri_cmd_t\":\"~/brightness/set\",\"bri_scl\":255,"
             "\"on_cmd_type\":\"first\",\"ic\":\"mdi:weather-night\",\"avty_t\":\"%s\",%s}",
             cfg.mqttBase, chipHex, cfg.mqttBase, chipHex, base, st, devj);
    mqtt.publish(topic, payload, true);

    bridgeTopic(base, sizeof(base), "light");
    snprintf(topic, sizeof(topic), "%s/sensor/%s_bridge_%s_light/config", HA_PREFIX, cfg.mqttBase, chipHex);
    snprintf(payload, sizeof(payload),
             "{\"name\":\"Light\",\"uniq_id\":\"%s_bridge_%s_light\",\"obj_id\":\"%s_bridge_%s_light\","
             "\"ent_cat\":\"diagnostic\",\"stat_t\":\"%s\",\"avty_t\":\"%s\",%s}",
             cfg.mqttBase, chipHex, cfg.mqttBase, chipHex, base, st, devj);
    mqtt.publish(topic, payload, true);
}

// The setting, retained, so a hub that restarts finds it without asking. Cheap enough to call on any
// change: configSetNight() has already dropped the ones that changed nothing.
static void publishNight() {
    if (!mqtt.connected()) return;
    char t[80], v[8];
    bridgeTopic(t, sizeof(t), "night");
    mqtt.publish(t, cfg.night ? "ON" : "OFF", true);
    bridgeTopic(t, sizeof(t), "night/brightness");
    snprintf(v, sizeof(v), "%u", (unsigned)cfg.nightLevel);
    mqtt.publish(t, v, true);
    bridgeTopic(t, sizeof(t), "settled");
    mqtt.publish(t, cfg.settled ? "yes" : "no", true);
}

// And what the LED is doing, whenever that changes -- which is not the same question.
static void publishLight(bool force) {
    static Light last = Light::Off;
    static bool ever = false;
    Light now = lightGet();
    if (!mqtt.connected()) { ever = false; return; }
    if (ever && !force && now == last) return;
    char t[80];
    bridgeTopic(t, sizeof(t), "light");
    mqtt.publish(t, LIGHT_NAMES[(int)now & 7], true);
    last = now;
    ever = true;
}

// ---------------------------------------------------------------- finding the hub
//
// docs/network.md, piece 1. The address written into a puck at setup is a DHCP lease, and a router
// reboot that reshuffles the pool used to strand every puck in the house without anybody touching
// the Wi-Fi at all. So there are three ways to find the hub and they are tried in turn:
//
//   the name, over mDNS   -- survives the lease changing
//   the last address that answered -- survives mDNS being filtered, which some mesh routers do
//   the address it was given -- survives a puck that has never connected
//
// `hubTry` moves on after every failed attempt, so a name that resolves to something stale cannot
// pin the puck to a dead address for ever. Whatever works is written down.
static uint8_t hubTry = 0;

static const char *hubAddress() {
    static char out[64];
    for (int i = 0; i < 3; i++) {
        switch ((hubTry + i) % 3) {
        case 0:
            if (cfg.mqttName[0]) {
                IPAddress a = MDNS.queryHost(cfg.mqttName, 2000);
                if ((uint32_t)a != 0) { strlcpy(out, a.toString().c_str(), sizeof(out)); return out; }
            }
            break;
        case 1:
            if (cfg.lastIp[0]) { strlcpy(out, cfg.lastIp, sizeof(out)); return out; }
            break;
        case 2:
            if (cfg.mqttHost[0]) { strlcpy(out, cfg.mqttHost, sizeof(out)); return out; }
            break;
        }
    }
    strlcpy(out, cfg.mqttHost, sizeof(out));
    return out;
}

// ---------------------------------------------------------------- two keys on the ring
//
// docs/network.md, piece 3. When neither network can be reached the puck alternates between the one
// it is on and the one it was on before, every couple of minutes, for ever. That is what makes a
// mistyped password a four-minute inconvenience rather than a walk around the house with a USB lead,
// and what makes it not matter whether the hub or the pucks move first.
#define WIFI_SWAP_MS 120000

static void wifiTick() {
    static uint32_t downSince = 0;
    if (WiFi.status() == WL_CONNECTED) {
        if (downSince) {
            downSince = 0;
            // This pair is the one that works. If the alternation had put the spare in front, write
            // the ring down in its new order so a reboot does not start on the dead one.
            configConfirmWifi();
        }
        return;
    }
    if (!downSince) { downSince = millis(); return; }
    if (!cfg.ssid2[0] || millis() - downSince < WIFI_SWAP_MS) return;
    configSwapWifi();
    WiFi.disconnect();
    WiFi.begin(cfg.ssid, cfg.pass);
    downSince = millis();
}

// ---------------------------------------------------------------- what the hub tells us
//
// One command topic per puck, in the same shape as `claim`: words, not JSON, hex-encoded so nothing
// needs quoting, queued here and acted on from the loop. Doing it in the callback would mean tearing
// down Wi-Fi from inside the MQTT client's own stack.
//
//   wifi <at> <ssid-hex> <pass-hex> <name-hex> <ip> <port>
//   spare forget <at>
//
// The command is RETAINED, so a puck that was switched off during a move gets it when it comes back.
// `at` is what stops a retained command being obeyed for ever: the newest one already applied is
// kept in NVS and anything at or before it is ignored.
static char cfgLine[400];
static volatile bool cfgWaiting = false;

static int unhexTo(const char *s, char *out, size_t max) {
    size_t n = strlen(s);
    if ((n & 1) || n / 2 >= max) return -1;
    for (size_t i = 0; i < n; i += 2) {
        auto v = [](char c) -> int {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
            return -1;
        };
        int a = v(s[i]), b = v(s[i + 1]);
        if (a < 0 || b < 0) return -1;
        out[i / 2] = (char)((a << 4) | b);
    }
    out[n / 2] = 0;
    return (int)(n / 2);
}

static void cfgAck();

static void cfgApply() {
    cfgWaiting = false;
    char line[400];
    strlcpy(line, cfgLine, sizeof(line));
    char *w[8] = {0};
    int nw = 0;
    for (char *q = strtok(line, " \t"); q && nw < 8; q = strtok(nullptr, " \t")) w[nw++] = q;
    if (nw < 2) return;

    if (!strcmp(w[0], "spare") && !strcmp(w[1], "forget") && nw == 3) {
        configForgetSpare((uint32_t)strtoul(w[2], nullptr, 10));
        cfgAck();
        return;
    }
    if (strcmp(w[0], "wifi") || nw < 5) { Serial.printf("[cfg] not understood: %s\n", w[0]); return; }
    uint32_t at = (uint32_t)strtoul(w[1], nullptr, 10);
    char ssid[33], pass[65], name[33];
    if (unhexTo(w[2], ssid, sizeof(ssid)) < 0 || unhexTo(w[3], pass, sizeof(pass)) < 0) { Serial.println("[cfg] bad hex"); return; }
    name[0] = 0;
    if (nw >= 5) unhexTo(w[4], name, sizeof(name));
    const char *ip = nw >= 6 ? w[5] : "";
    if (!configNewWifi(ssid, pass, name, ip, at)) {
        // Nothing changed -- we are already on it, or this is a replay. Still worth answering: the
        // hub is waiting to hear that this puck is where it should be, and silence would put it on
        // the "did not follow" list while it sits there perfectly connected.
        cfgAck();
        return;
    }
    Serial.printf("[cfg] moving to %s\n", cfg.ssid);
    // The ack cannot be sent from the new network until we are on it, and we may never get there --
    // in which case wifiTick() walks us back onto the spare and the ack goes out from there.
    WiFi.disconnect();
    WiFi.begin(cfg.ssid, cfg.pass);
}


// What the hub is waiting to hear. Retained, so it survives the hub restarting mid-move, and sent on
// every broker connect rather than once after a change: an ack can only be published from a network
// the puck actually joined, which is what makes it proof rather than a promise.
static void cfgAck() {
    if (!mqtt.connected()) return;
    char t[80], body[160], s1[70], s2[70];
    auto esc = [](const char *in, char *out, size_t max) {
        size_t j = 0;
        for (size_t i = 0; in[i] && j + 2 < max; i++) {
            if (in[i] == '"' || in[i] == '\\') out[j++] = '\\';
            out[j++] = in[i];
        }
        out[j] = 0;
    };
    esc(cfg.ssid, s1, sizeof(s1));
    esc(cfg.ssid2, s2, sizeof(s2));
    snprintf(body, sizeof(body), "{\"at\":%lu,\"ssid\":\"%s\",\"spare\":\"%s\"}",
             (unsigned long)cfg.cfgAt, s1, s2);
    bridgeTopic(t, sizeof(t), "cfgack");
    mqtt.publish(t, body, true);
}

// ---------------------------------------------------------------- mqtt

// What the ear heard (ear.h). Not retained: a knock is news, and a strip that stops knocking must be
// able to leave the hub's table just by not being heard again.
static void earSay(const char *leaf, const char *payload) {
    if (!mqtt.connected()) return;
    char t[80];
    bridgeTopic(t, sizeof(t), leaf);
    mqtt.publish(t, payload, false);
}

static void updateSay(const char *leaf, const char *payload, bool retain) {
    if (!mqtt.connected()) return;
    char t[80];
    bridgeTopic(t, sizeof(t), leaf);
    mqtt.publish(t, payload, retain);
}

static void mqttCb(char *topic, uint8_t *payload, unsigned int len) {
    char msg[32] = {0};
    memcpy(msg, payload, min((unsigned int)31, len));
    char t[128];
    strlcpy(t, topic, sizeof(t));

    char own[80];   // the puck's own topics, matched before anything is handed to the module
    // Before `msg` is used for anything: an offer is longer than the 31 bytes it keeps.
    bridgeTopic(own, sizeof(own), "offer");
    if (!strcmp(t, own)) {
        update_offer(payload, len);     // decided on the loop; see update.h
        return;
    }
    bridgeTopic(own, sizeof(own), "cfg");
    if (!strcmp(t, own)) {
        strlcpy(cfgLine, (const char *)msg, sizeof(cfgLine));
        cfgWaiting = true;              // acted on from the loop; see cfgApply()
        return;
    }
    // An errand for a hub that cannot hear a strip (errand.h). Queued whole, never read here: the
    // radio work happens on the loop, like the notify path.
    bridgeTopic(own, sizeof(own), "errand/ask");
    if (!strcmp(t, own)) {
        if (!errand_queue(payload, len)) Serial.println("[errand] queue full -- dropped a command");
        return;
    }

    // The nightlight is the puck's own, so it arrives on the bridge's topic like cfg.
    // Acting here rather than queueing is safe in a way the ones above are not: this touches no radio
    // and no NVS that is not already guarded, and the publish that answers it is three bytes.
    bridgeTopic(own, sizeof(own), "night/set");
    if (!strcmp(t, own)) {
        configSetNight(!strcasecmp(msg, "on") || !strcasecmp(msg, "1"), cfg.nightLevel);
        publishNight();
        return;
    }
    bridgeTopic(own, sizeof(own), "night/brightness/set");
    if (!strcmp(t, own)) {
        int bri = constrain(atoi(msg), 0, 255);
        // A brightness of zero from HA is an "off" in all but name; treat it as one rather than
        // leaving a nightlight that is on and invisible, which nobody can explain.
        configSetNight(bri > 0, (uint8_t)(bri > 0 ? bri : cfg.nightLevel));
        publishNight();
        return;
    }
    // A LIFT IS NOT A BRIGHTNESS, and the difference is the whole reason this topic exists.
    //
    // The brain swells the nightlight when somebody walks past the switch beside it and lets it
    // settle afterwards (docs/puck-light.md). Sent on night/brightness/set that would be two NVS
    // writes per walk-past, for ever, on a part with a finite number of erases -- and it would drag
    // the household's own brightness setting up and down in Home Assistant, where what they set is
    // supposed to be what it says. So a lift touches the LIGHT and nothing else: no NVS, no retained
    // state, no entity moved. 0 (or anything that is not a number) means "back to what they chose",
    // which is also what a reboot means, so a brain that dies mid-swell cannot leave it bright.
    bridgeTopic(own, sizeof(own), "night/lift/set");
    if (!strcmp(t, own)) {
        int lvl = constrain(atoi(msg), 0, 255);
        lightNightLevel(lvl > 0 ? (uint8_t)lvl : cfg.nightLevel);
        return;
    }
    bridgeTopic(own, sizeof(own), "settled/set");
    if (!strcmp(t, own)) {
        configSetSettled(msg[0] == '1' || msg[0] == 'y' || msg[0] == 'Y');
        publishNight();
        return;
    }

    mod_mqtt(t, payload, len, msg);    // anything else is the module's, or nobody's
}

// Why this re-asserts the server every attempt: setServer() was called once in
// setup() from the config as it stood at boot. A puck whose broker changes
// afterwards (a cable write that does not restart, a field left blank at first
// boot) would keep the stale address for ever and retry into nothing -- the
// broker never sees a connection attempt at all, which reads as a dead puck
// with healthy Wi-Fi. Re-asserting costs nothing and cannot go stale.
static void mqttReconnect() {
    if (mqtt.connected()) return;
    static uint32_t last = 0;
    if (millis() - last < 5000) return;
    last = millis();

    static uint32_t lastWhy = 0;        // say out loud why we are not on the broker, once a minute
    bool moan = (millis() - lastWhy > 60000);
    if (!cfg.mqttHost[0]) {
        if (moan) { lastWhy = millis(); Serial.println("[mqtt] no broker configured -- waiting for the hub"); }
        return;
    }
    const char *addr = hubAddress();
    mqtt.setServer(addr, cfg.mqttPort);

    char id[40], will[80];
    snprintf(id, sizeof(id), "%s-bridge-%s", cfg.mqttBase, chipHex);
    bridgeTopic(will, sizeof(will), "status");
    bool ok = mqtt.connect(id, cfg.mqttUser[0] ? cfg.mqttUser : nullptr,
                           cfg.mqttUser[0] ? cfg.mqttPass : nullptr, will, 0, true, "offline");
    if (!ok) {
        // Name the broker in the failure: "connect failed" against the wrong or
        // an empty host looks identical to a broker that is refusing us.
        if (moan) {
            lastWhy = millis();
            Serial.printf("[mqtt] connect failed (rc %d) to %s:%u as %s\n", mqtt.state(),
                          addr, (unsigned)cfg.mqttPort, id);
        }
        hubTry++;      // that way of finding the hub did not work; try the next one
        return;
    }
    // It answered. Whatever found it is worth keeping, whichever of the three it was.
    configRemember(addr);
    mqtt.publish(will, "online", true);
    char sub[80];
    bridgeTopic(sub, sizeof(sub), "errand/ask");
    mqtt.subscribe(sub);
    bridgeTopic(sub, sizeof(sub), "cfg");
    mqtt.subscribe(sub);
    bridgeTopic(sub, sizeof(sub), "night/set");
    mqtt.subscribe(sub);
    bridgeTopic(sub, sizeof(sub), "night/brightness/set");
    mqtt.subscribe(sub);
    bridgeTopic(sub, sizeof(sub), "night/lift/set");
    mqtt.subscribe(sub);
    bridgeTopic(sub, sizeof(sub), "settled/set");
    mqtt.subscribe(sub);
    mod_subscribe();
    // Last, so the retained offer that arrives with it lands after everything above is listening.
    bridgeTopic(sub, sizeof(sub), "offer");
    mqtt.subscribe(sub);
    cfgAck();
    Serial.printf("[mqtt] connected as %s, commands on %s\n", id, sub);
    announceBridge();
    char t[80], v[48];
    // What this puck runs, so the hub can count who has a fix without waiting for a cable.
    bridgeTopic(t, sizeof(t), "fw");
    mqtt.publish(t, BRIDGE_VERSION, true);
    // What it can do, so the hub can tell a puck with nothing to bridge from one that has not said yet
    // (brain/hub/bridge.py, _no_mesh): retained, and the module adds its own word.
    bridgeTopic(t, sizeof(t), "caps");
    snprintf(v, sizeof(v), "light ear errand update%s", mod_caps());
    mqtt.publish(t, v, true);
    publishNight();
    publishLight(true);   // forced: a fresh session has nothing retained from this boot
    mod_announce();
}

void hubMqttReconnect() { mqttReconnect(); }

// ---------------------------------------------------------------- lifecycle

// One line for the hub's `status`, key=value so it can be read without a parser, and kept
// short: the CDC link drops the middle of long lines (see reply() in config.cpp). The proxy's
// address is on MQTT already; only its signal strength is worth the bytes here.
void bridgeStatusLine(char *out, size_t n) {
    // `spare` says whether this puck has a way back if the Wi-Fi changes under it -- the one thing
    // somebody holding it on a cable cannot see. The SSID itself is deliberately NOT here: this line
    // is parsed on spaces (brain/hub/puck_cable.py) and a network called "Flat 3 guest" would tear it in
    // half. The hub learns the name from cfgack, over the broker, where it is quoted properly.
    // Which of the maker's keys this image carries, two bytes of each. Nothing verifies a signature
    // yet (docs/puck-updates.md), but a key cannot be added to a puck after its cable visit, so they
    // go in before anything needs them -- and a puck that cannot say which keys it holds is one
    // nobody can check before it disappears behind a sofa. This is also what keeps them in the
    // binary at all: an unused static const array in a header is not linked into the image.
    char keys[8 * N_RELEASE_KEYS];
    char *kp = keys;
    for (int i = 0; i < N_RELEASE_KEYS; i++)
        kp += snprintf(kp, sizeof(keys) - (kp - keys), i ? ",%02x%02x" : "%02x%02x",
                       RELEASE_KEYS[i][0], RELEASE_KEYS[i][1]);
    // No String temporaries here: this runs on the serial task's stack.
    char ip[20] = "down";
    if (WiFi.status() == WL_CONNECTED) {
        IPAddress a = WiFi.localIP();
        snprintf(ip, sizeof(ip), "%u.%u.%u.%u", a[0], a[1], a[2], a[3]);
    }
    char extra[48];
    mod_status(extra, sizeof(extra));
    snprintf(out, n, "status wifi=%s mqtt=%s%s light=%s spare=%s night=%s keys=%s", ip,
             mqtt.connected() ? "up" : "down", extra, LIGHT_NAMES[(int)lightGet() & 7],
             cfg.ssid2[0] ? "yes" : "no",
             !cfg.settled ? "unplaced" : cfg.night ? "on" : "off", keys);
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
    Serial.println("\n=== bridge puck " BRIDGE_VERSION " ===");

    // Who we are and what we were told, before anything else looks at either.
    configLoad();
    lightBegin();
    lightNightLevel(cfg.nightLevel);   // before anything can reach Light::Night
    lightSet(Light::Looking);

    update_begin(updateSay);   // before anything else can restart: it notices a rollback
    // Puck identity from the factory MAC: six hex digits, and the module's address block.
    uint64_t mac = ESP.getEfuseMac();
    uint32_t chip = (uint32_t)((mac ^ (mac >> 24)) & 0xFFFFFF);
    snprintf(chipHex, sizeof(chipHex), "%06lx", (unsigned long)chip);
    mod_begin(chip);
    ear_begin(earSay);
    errand_begin(earSay);   // the same: not retained, a leaf under the puck's own topic

    configSerialBegin(chipHex);   // the hub can talk to us from here on, whatever else happens below
    if (configBlank()) {
        // Nothing written yet: a board straight off the shipped image. There is nothing to connect to,
        // so this is the end of setup -- the puck sits on the cable, blinking amber, waiting to be told.
        Serial.printf("puck %s   blank: waiting for the hub on the cable\n", chipHex);
        return;
    }
    mod_start();

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
    // So the hub can be found by name rather than by a DHCP lease that will change. Starting this
    // needs no network of its own -- it is answered and asked for over whatever link comes up.
    MDNS.begin(chipHex);

    mqtt.setServer(cfg.mqttHost, cfg.mqttPort);
    mqtt.setBufferSize(1024);   // discovery payloads are bigger than the 256-byte default
    mqtt.setKeepAlive(60);      // a stalled second or two on the shared radio must not drop the session
    mqtt.setSocketTimeout(5);
    mqtt.setCallback(mqttCb);

    NimBLEDevice::init("mesh-bridge");
    NimBLEDevice::setMTU(69);
    // WiFi and BLE share one radio. Modem sleep has to stay on (the driver
    // aborts otherwise), so the WiFi side is protected two other ways: it is
    // preferred by the coexistence scheduler, and a module's link asks for a long
    // connection interval so it does not hog the air.
    esp_coex_preference_set(ESP_COEX_PREFER_WIFI);
    NimBLEScan *scan = NimBLEDevice::getScan();
    scan->setActiveScan(true);
    scan->setInterval(100);
    scan->setWindow(99);
}

// How long this spot has had no Wi-Fi at all. Half a minute is long enough to say "no Wi-Fi here"
// to somebody standing at a socket, and short enough that they are still standing there.
#define WIFI_FAR_MS 30000
static uint32_t wifiDownSince = 0;

// Recomputed every pass rather than set at the moments things change, because Wi-Fi can go after
// everything else is up and a light that was only ever set on the way in would never say so. The
// rule itself, and why green is a promise, is src/lightrule.h.
static void lightRefresh() {
    bool wifi = WiFi.status() == WL_CONNECTED;
    if (wifi) wifiDownSince = 0;
    else if (!wifiDownSince) wifiDownSince = millis() | 1;
    LightIn in;
    in.broker = wifi && mqtt.connected();
    in.carries = mod_carries();
    in.linkUp = mod_link_ok();
    in.linkFar = mod_far();
    in.wifiLongDown = !wifi && millis() - wifiDownSince >= WIFI_FAR_MS;
    in.settled = cfg.settled;
    in.night = cfg.night;
    lightSet(lightFor(in));
}

void hubLightRefresh() { lightRefresh(); }

void loop() {
    if (configBlank()) {   // waiting for the hub; the serial task is doing the work
        static uint32_t saidBlank = 0;
        if (millis() - saidBlank > 60000) {
            saidBlank = millis();
            Serial.println("[cfg] blank: no Wi-Fi/broker yet, so no MQTT and no mesh (cable only)");
        }
        delay(200);
        return;
    }
    // Both of these before anything on the radio: one decides which Wi-Fi we are even trying, and
    // the other may be about to change it. Neither can run inside the MQTT callback that queued it.
    wifiTick();
    if (cfgWaiting) cfgApply();
    if (WiFi.status() == WL_CONNECTED) {
        mqttReconnect();
        mqtt.loop();
    }
    // A new image proves itself by doing the whole job: the broker, and the module's link if it has
    // one. A puck with nothing to bridge has the broker as its whole job.
    bool brokerUp = WiFi.status() == WL_CONNECTED && mqtt.connected();
    update_tick(brokerUp && mod_link_ok(), brokerUp);
    // Taking an update waits for anything a household started -- a switch being let in, a strip being
    // set up -- and then has the radio to itself. It restarts on success and returns otherwise.
    if (brokerUp && update_ready() && !mod_busy() && !errand_busy()) {
        mod_drop("taking an update");
        update_run(cfg.lastIp);
    }

    ModTick free = mod_tick();
    lightRefresh();      // every pass: the broker can go while everything else stays up
    publishLight(false); // ...and say so, but only when it really moved

    // THE EAR, whenever nothing else wants the scanner (ear.h, docs/strip.md item 42). A strip
    // knocking behind the television is heard here and not in the garage. It stands aside while an
    // errand connects or holds a link: NimBLE will not connect while scanning.
    ear_tick(free.ear && !errand_busy());
    if (free.errand) errand_tick();
    delay(5);
}
