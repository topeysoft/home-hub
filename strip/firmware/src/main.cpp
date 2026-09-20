// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// A light strip controller: it knocks over Bluetooth, is set up from the wall, and is an ordinary
// light in the house from then on.
//
// It never goes to the hub on a cable. It leaves the factory flashed, so the moment it has power it
// can say hello -- which is design/puck/Knock.dc.html's direction A, the one that lost for a bridge
// on the single objection "it only works on a board that already has firmware on it". A product we
// ship is flashed, so that objection is gone and docs/puck-hardware.md's open question is answered
// for this device class.
//
// WHAT IT ADVERTISES, AND WHEN. `hub-strip-<chip>` while it has never been set up, and NOTHING
// afterwards. That second half is the whole answer to "what about when the router reboots": it keeps
// the light the household asked for, alternates between the two Wi-Fi credentials it holds, and stays
// quiet. Opening a pairing window on an event that happens several times a year, with nobody present
// and nobody told, would be a security posture chosen by somebody else's firmware updates. Coming
// back needs a deliberate act -- the button -- which is what separates "my router rebooted" from
// "I have moved house".
//
// THE TOPICS, which brain/hub/strip.py is the other end of. <base> is "strip" and <id> is the chip.
//
//   strip/<id>/status        online | offline        (retained, LWT)
//   strip/<id>/order         the ordering in use      (retained)
//   strip/<id>/count         how many lights          (retained)
//   strip/<id>/fill          how far the fill has got
//   strip/<id>/hello         <- the hub, once, to see whether we are here
//   strip/<id>/show/set      <- "raw <b0> <b1> <b2>" | "fill" | "off"
//   strip/<id>/fill/stop     <- latch the fill and answer on .../count
//   strip/<id>/order/set     <- one of the six
//   strip/<id>/white/set     <- 1 if it carries a separate white
//   strip/<id>/count/set     <- how many lights
//   strip/<id>/room/set      <- the room it was put in
//   strip/<id>/set           <- the light itself: ON | OFF
//   strip/<id>/rgb/set, strip/<id>/brightness/set
//
// THE LIGHT NEVER REPORTS A FAULT BY CHANGING COLOR, and this is the one place a strip is the
// opposite of the bridge puck. docs/puck-light.md puts a fault above the puck's light, because a puck
// glowing while its bridge is down is furniture that lies. A strip is behind somebody's television
// while they watch a film: turning it amber because the broker blinked is the product breaking, not
// reporting. So it holds whatever it was asked for and the panel carries the fault.
#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <ESPmDNS.h>

#include "pixels.h"

namespace px {
bool begin(int pin);
void show(const Pixels &p);
}  // namespace px

#define FW "0.1.0"
#define DATA_PIN 5
#define BUTTON_PIN 0
// The provisioning service. One characteristic, written as `key=value` lines, because the whole
// conversation is six short strings and a protobuf schema would be more moving parts than message.
#define SVC_UUID "5f1b0001-9a2e-4c7d-8f31-2b6a0d4e7c10"
#define CHR_UUID "5f1b0002-9a2e-4c7d-8f31-2b6a0d4e7c10"

static Preferences nvs;
static WiFiClient net;
static PubSubClient mqtt(net);
static px::Pixels strip;
static px::Fill fill;
static char chipHex[13];
static char base[16] = "strip";

// The credentials it is using and the ones it used before. A house that changes its Wi-Fi password
// otherwise makes every strip in it permanently deaf, with no way back that is not a walk around with
// a laptop. Holding both and alternating makes the ORDER of a move stop mattering: whoever arrives
// second finds the other already there, and a mistyped password repairs itself in minutes.
static String ssid, pass, ssid2, pass2, host, muser, mpass;
static bool provisioned = false;
static bool showing_instrument = false;   // the setup instrument owns the strip; the household does not
static uint8_t want_r = 255, want_g = 180, want_b = 110, want_bri = 200;
static bool want_on = false;

// ---------------------------------------------------------------- what it is showing

static void paint() {
    if (showing_instrument) return;          // the fill and the color question are not the household's
    if (!want_on) { strip.clear(); }
    else {
        const uint16_t k = want_bri;
        strip.solid((uint8_t)(want_r * k / 255), (uint8_t)(want_g * k / 255), (uint8_t)(want_b * k / 255));
    }
    px::show(strip);
}

static void topic(char *out, size_t n, const char *leaf) {
    snprintf(out, n, "%s/%s/%s", base, chipHex, leaf);
}

static void say(const char *leaf, const char *payload, bool retain = false) {
    char t[96];
    topic(t, sizeof(t), leaf);
    mqtt.publish(t, payload, retain);
}

// ---------------------------------------------------------------- Home Assistant discovery
//
// One more payload and the strip IS a light in the house -- so the schedules, "everything off", the
// room tile and the color swatches are all machinery that already exists and none of it has to be
// invented here. That was the lesson of the bridge puck's nightlight and it applies twice over to a
// thing whose entire job is being a light.
static void announce() {
    char t[128], p[640], avty[96], devj[240];
    topic(avty, sizeof(avty), "status");
    snprintf(devj, sizeof(devj),
             "\"dev\":{\"ids\":[\"%s_%s\"],\"name\":\"Light strip %s\",\"mf\":\"home-hub\","
             "\"mdl\":\"Light strip controller\",\"sw\":\"" FW "\"}",
             base, chipHex, chipHex);
    snprintf(t, sizeof(t), "homeassistant/light/%s_%s/config", base, chipHex);
    // JSON schema, not the legacy per-topic form: it is the only one that does rgbw cleanly, and it
    // is one message per change rather than four that can arrive out of order.
    snprintf(p, sizeof(p),
             "{\"schema\":\"json\",\"name\":null,\"uniq_id\":\"%s_%s_light\",\"obj_id\":\"%s_%s\","
             "\"~\":\"%s/%s\",\"stat_t\":\"~/state\",\"cmd_t\":\"~/set\","
             "\"brightness\":true,\"supported_color_modes\":[\"%s\"],"
             "\"avty_t\":\"%s\",%s}",
             base, chipHex, base, chipHex, base, chipHex,
             strip.order.white ? "rgbw" : "rgb", avty, devj);
    mqtt.publish(t, p, true);
    say("status", "online", true);
    char v[16];
    snprintf(v, sizeof(v), "%d", strip.count);
    say("count", v, true);
    const char letters[3] = {'r', 'g', 'b'};
    char ord[4] = {0, 0, 0, 0};
    for (int c = 0; c < 3; c++) ord[strip.order.at[c]] = letters[c];
    say("order", ord, true);
}

// ---------------------------------------------------------------- the hub talking

static void onMqtt(char *t, uint8_t *payload, unsigned int len) {
    String msg;
    msg.reserve(len + 1);
    for (unsigned i = 0; i < len; i++) msg += (char)payload[i];
    String leaf = String(t);
    int cut = leaf.indexOf(String(chipHex) + "/");
    if (cut < 0) return;
    leaf = leaf.substring(cut + strlen(chipHex) + 1);

    if (leaf == "hello") { announce(); return; }

    if (leaf == "show/set") {
        if (msg.startsWith("raw ")) {
            int a = msg.indexOf(' '), b = msg.indexOf(' ', a + 1), c = msg.indexOf(' ', b + 1);
            if (a < 0 || b < 0 || c < 0) return;
            showing_instrument = true;
            fill.running = false;
            strip.raw3((uint8_t)msg.substring(a + 1, b).toInt(),
                       (uint8_t)msg.substring(b + 1, c).toInt(),
                       (uint8_t)msg.substring(c + 1).toInt());
            px::show(strip);
        } else if (msg == "fill") {
            showing_instrument = true;
            strip.clear();
            px::show(strip);
            fill.start(millis());
        } else if (msg == "off") {
            showing_instrument = false;
            paint();
        }
        return;
    }

    if (leaf == "fill/stop") {
        // Latched HERE, at the moment the message lands, and not by reading a number back to the hub
        // afterwards. The only other error in this answer is a person's reaction time; adding however
        // busy the Wi-Fi is on top of it would make a strip measure short on a busy evening.
        const int n = fill.stop();
        strip.set_count(n);
        nvs.putInt("count", n);
        char v[16];
        snprintf(v, sizeof(v), "%d", n);
        say("count", v, true);
        showing_instrument = false;
        paint();
        return;
    }

    if (leaf == "order/set") {
        char want[8];
        msg.toCharArray(want, sizeof(want));
        if (strip.order.set(want)) {
            nvs.putString("order", msg);
            say("order", want, true);
            announce();          // rgb and rgbw are different entities to Home Assistant
        }
        return;
    }
    if (leaf == "white/set") {
        strip.order.white = msg == "1";
        nvs.putBool("white", strip.order.white);
        announce();
        return;
    }
    if (leaf == "count/set") { strip.set_count(msg.toInt()); nvs.putInt("count", strip.count); return; }
    if (leaf == "room/set")  { nvs.putString("room", msg); return; }

    if (leaf == "set") {
        // The JSON schema's one command topic. Parsed by hand: this is four fields and pulling in a
        // JSON library for it would cost more flash than the whole of pixels.cpp.
        want_on = msg.indexOf("\"ON\"") >= 0;
        int b = msg.indexOf("\"brightness\"");
        if (b >= 0) want_bri = (uint8_t)msg.substring(msg.indexOf(':', b) + 1).toInt();
        int c = msg.indexOf("\"color\"");
        if (c >= 0) {
            int r = msg.indexOf("\"r\"", c), g = msg.indexOf("\"g\"", c), bl = msg.indexOf("\"b\"", c);
            if (r > 0) want_r = (uint8_t)msg.substring(msg.indexOf(':', r) + 1).toInt();
            if (g > 0) want_g = (uint8_t)msg.substring(msg.indexOf(':', g) + 1).toInt();
            if (bl > 0) want_b = (uint8_t)msg.substring(msg.indexOf(':', bl) + 1).toInt();
        }
        paint();
        char st[128];
        snprintf(st, sizeof(st),
                 "{\"state\":\"%s\",\"brightness\":%u,\"color_mode\":\"rgb\",\"color\":{\"r\":%u,\"g\":%u,\"b\":%u}}",
                 want_on ? "ON" : "OFF", want_bri, want_r, want_g, want_b);
        say("state", st, true);
        return;
    }
}

// ---------------------------------------------------------------- being set up, over Bluetooth

class Provision : public NimBLECharacteristicCallbacks {
    void onWrite(NimBLECharacteristic *c) override {
        String line = String(c->getValue().c_str());
        int eq = line.indexOf('=');
        if (eq < 0) return;
        String k = line.substring(0, eq), v = line.substring(eq + 1);
        if (k == "ssid") ssid = v;
        else if (k == "pass") pass = v;
        else if (k == "host") host = v;
        else if (k == "user") muser = v;
        else if (k == "mpass") mpass = v;
        else if (k == "base") v.toCharArray(base, sizeof(base));
        else if (k == "apply") {
            // The ring: whatever it was on becomes the spare before the new one is written, so a
            // household that mistypes a password has the old one still to fall back to.
            nvs.putString("ssid2", nvs.getString("ssid", "")); nvs.putString("pass2", nvs.getString("pass", ""));
            nvs.putString("ssid", ssid); nvs.putString("pass", pass);
            nvs.putString("host", host); nvs.putString("user", muser); nvs.putString("mpass", mpass);
            nvs.putString("base", base);
            nvs.putBool("set", true);
            c->setValue("ok");
            delay(150);
            ESP.restart();
        }
    }
};

static void advertise() {
    char name[32];
    snprintf(name, sizeof(name), "hub-strip-%s", chipHex);
    NimBLEDevice::init(name);
    NimBLEServer *s = NimBLEDevice::createServer();
    NimBLEService *svc = s->createService(SVC_UUID);
    NimBLECharacteristic *c = svc->createCharacteristic(CHR_UUID, NIMBLE_PROPERTY::WRITE | NIMBLE_PROPERTY::READ);
    c->setCallbacks(new Provision());
    svc->start();
    NimBLEAdvertising *adv = NimBLEDevice::getAdvertising();
    adv->addServiceUUID(SVC_UUID);
    adv->setName(name);
    adv->start();
}

// ---------------------------------------------------------------- the house

static bool joinWifi(const String &s, const String &p, uint32_t patience = 12000) {
    if (!s.length()) return false;
    WiFi.begin(s.c_str(), p.c_str());
    const uint32_t end = millis() + patience;
    while (millis() < end && WiFi.status() != WL_CONNECTED) delay(150);
    return WiFi.status() == WL_CONNECTED;
}

static void connectBroker() {
    if (mqtt.connected()) return;
    // By name first, then by whatever answered last. A house whose router filters multicast is caught
    // by the second; a house that reshuffles its leases is caught by the first.
    IPAddress ip;
    if (MDNS.begin("strip") && (ip = MDNS.queryHost(host.length() ? host.c_str() : "hub"))) {
        mqtt.setServer(ip, 1883);
    } else {
        mqtt.setServer(host.length() ? host.c_str() : "hub.local", 1883);
    }
    char will[96];
    topic(will, sizeof(will), "status");
    if (mqtt.connect(chipHex, muser.c_str(), mpass.c_str(), will, 0, true, "offline")) {
        char sub[96];
        topic(sub, sizeof(sub), "#");
        mqtt.subscribe(sub);
        announce();
        paint();
    }
}

void setup() {
    uint64_t mac = ESP.getEfuseMac();
    snprintf(chipHex, sizeof(chipHex), "%06llx", (unsigned long long)(mac >> 24) & 0xFFFFFF);
    pinMode(BUTTON_PIN, INPUT_PULLUP);
    nvs.begin("strip", false);
    px::begin(DATA_PIN);

    provisioned = nvs.getBool("set", false);
    strip.set_count(nvs.getInt("count", PX_ASSUMED));
    strip.order.white = nvs.getBool("white", false);
    String ord = nvs.getString("order", "grb");
    char o[8]; ord.toCharArray(o, sizeof(o)); strip.order.set(o);
    nvs.getString("base", "strip").toCharArray(base, sizeof(base));

    if (!provisioned) {
        // Lit, because being lit IS the identity check: the wall asks whether the thing that just
        // came on is theirs, and there is nothing to disambiguate -- it is two meters of light and it
        // is the only one lit (design/strip/Spine.dc.html).
        strip.solid(233, 184, 114);
        px::show(strip);
        advertise();
        return;
    }
    ssid = nvs.getString("ssid", ""); pass = nvs.getString("pass", "");
    ssid2 = nvs.getString("ssid2", ""); pass2 = nvs.getString("pass2", "");
    host = nvs.getString("host", "hub"); muser = nvs.getString("user", "");
    mpass = nvs.getString("mpass", "");
    mqtt.setBufferSize(1024);           // a discovery payload does not fit the 256-byte default
    mqtt.setCallback(onMqtt);
    if (!joinWifi(ssid, pass)) joinWifi(ssid2, pass2);
    paint();                            // lit before the broker: the light is not waiting on the hub
}

void loop() {
    if (!provisioned) { delay(50); return; }

    static uint32_t ring = 0;
    if (WiFi.status() != WL_CONNECTED && millis() - ring > 120000) {
        // For ever, alternating. There is no state in which it gives up: a strip that stopped trying
        // is a strip somebody has to go and find.
        ring = millis();
        if (!joinWifi(ssid, pass, 8000)) joinWifi(ssid2, pass2, 8000);
    }
    if (WiFi.status() == WL_CONNECTED) { connectBroker(); mqtt.loop(); }

    if (fill.running) {
        const int was = fill.at;
        fill.tick(millis(), strip.count);
        if (fill.at != was) {
            strip.clear();
            for (int i = 0; i < fill.at; i++) strip.order.bytes(233, 184, 114, &strip.buf[i * strip.order.per_pixel()]);
            px::show(strip);
            char v[16];
            snprintf(v, sizeof(v), "%d", fill.at);
            say("fill", v);
        }
    }
    delay(2);
}
