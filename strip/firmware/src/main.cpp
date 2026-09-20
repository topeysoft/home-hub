// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// A light strip controller: a Matter device in its own right, and a little more than that in a house
// that has our hub.
//
// WHY MATTER RATHER THAN OUR OWN PROVISIONING, and this is the decision the file exists to record.
// The first draft of this firmware set itself up over a hand-rolled BLE characteristic taking
// key=value lines. It worked, and it sent the household's Wi-Fi password over an unauthenticated
// link, where anything in radio range during setup could read it. Matter's commissioning is PASE
// with SPAKE2+ and then CASE: the credentials never cross in the clear, in a stack a great many
// people have looked at. So this is not a feature that was added on top -- it REPLACED the thing
// that was wrong, and got Apple Home, Google Home, Alexa and SmartThings while it was there.
//
// TWO WAYS TO OWN ONE, and the first is the whole product on its own:
//
//   Any Matter hub          commission it with the code, and it is a color light. On, off, dim, any
//                           color, any warmth, in whatever app the household already uses. Nothing
//                           below this line is needed and the strip never hears of us.
//   Our hub as well         the same, plus the two questions Matter has no words for -- which order
//                           its colors come out in, and how far it goes -- over MQTT. A strip with no
//                           broker in its NVS simply does not do this half, and is none the worse.
//
// WHAT MATTER CANNOT SAY, which is why the second half exists at all. The Enhanced Color Light is
// on/off, level, hue, saturation and color temperature -- one color for the whole fitting. It has no
// concept of a pixel, so the setup instruments and anything spatial are ours and always will be.
// That is the same split Hue and Nanoleaf run and it is not a compromise.
//
// THE LIGHT NEVER REPORTS A FAULT BY CHANGING COLOR. This is the one place a strip is the opposite of
// the bridge puck. docs/puck-light.md puts a fault above a puck's light, because a puck glowing while
// its bridge is down is furniture that lies. A strip is behind somebody's television while they watch
// a film: turning it amber because a broker blinked is the product breaking, not reporting. It holds
// what it was asked for, and the panel carries the fault.
#include <Arduino.h>
#include <Matter.h>
#include <Preferences.h>
#include <PubSubClient.h>
#include <WiFi.h>
#include <ESPmDNS.h>

#include "pixels.h"

namespace px {
bool begin(int pin);
void show(const Pixels &p);
}  // namespace px

#define FW "0.2.0"
#define DATA_PIN 5

static MatterEnhancedColorLight light;
static Preferences nvs;
static WiFiClient net;
static PubSubClient mqtt(net);
static px::Pixels strip;
static px::Fill fill;
static char chipHex[13];
static char base[16] = "strip";
static String mhost, muser, mpass;

// The setup instruments own the strip while they are running, and the household's own color is put
// back the moment they stop. Without this a "fill" that was never stopped would leave somebody's
// living room running a test pattern for ever.
static bool instrument = false;

static bool want_on = false;
static uint8_t want_r = 233, want_g = 184, want_b = 114, want_bri = 200;

// ---------------------------------------------------------------- what it is showing

static void paint() {
    if (instrument) return;
    if (!want_on) strip.clear();
    else {
        const uint16_t k = want_bri ? want_bri : 1;
        strip.solid((uint8_t)(want_r * k / 255), (uint8_t)(want_g * k / 255), (uint8_t)(want_b * k / 255));
    }
    px::show(strip);
}

// Matter hands colors over as HSV, because that is what the cluster carries.
static void fromHSV(espHsvColor_t c, uint8_t &r, uint8_t &g, uint8_t &b) {
    const espRgbColor_t rgb = espHsvColorToRgbColor(c);
    r = rgb.r; g = rgb.g; b = rgb.b;
}

// ---------------------------------------------------------------- our hub, when there is one

static void topic(char *out, size_t n, const char *leaf) {
    snprintf(out, n, "%s/%s/%s", base, chipHex, leaf);
}

static void say(const char *leaf, const char *payload, bool retain = false) {
    if (!mqtt.connected()) return;
    char t[96];
    topic(t, sizeof(t), leaf);
    mqtt.publish(t, payload, retain);
}

static void sayWhatWeAre() {
    char v[16];
    snprintf(v, sizeof(v), "%d", strip.count);
    say("count", v, true);
    const char letters[3] = {'r', 'g', 'b'};
    char ord[4] = {0, 0, 0, 0};
    for (int c = 0; c < 3; c++) ord[strip.order.at[c]] = letters[c];
    say("order", ord, true);
    say("status", "online", true);
}

static void onMqtt(char *t, uint8_t *payload, unsigned int len) {
    String msg;
    msg.reserve(len + 1);
    for (unsigned i = 0; i < len; i++) msg += (char)payload[i];
    String leaf = String(t);
    const int cut = leaf.indexOf(String(chipHex) + "/");
    if (cut < 0) return;
    leaf = leaf.substring(cut + strlen(chipHex) + 1);

    if (leaf == "hello") { sayWhatWeAre(); return; }

    if (leaf == "show/set") {
        if (msg.startsWith("raw ")) {
            const int a = msg.indexOf(' '), b = msg.indexOf(' ', a + 1), c = msg.indexOf(' ', b + 1);
            if (a < 0 || b < 0 || c < 0) return;
            instrument = true;
            fill.running = false;
            // Exactly as given. Putting these through the strip's mapping would be applying the very
            // guess the question exists to test (pixels.h, raw3).
            strip.raw3((uint8_t)msg.substring(a + 1, b).toInt(),
                       (uint8_t)msg.substring(b + 1, c).toInt(),
                       (uint8_t)msg.substring(c + 1).toInt());
            px::show(strip);
        } else if (msg == "fill") {
            instrument = true;
            strip.clear();
            px::show(strip);
            fill.start(millis());
        } else if (msg == "off") {
            instrument = false;
            paint();
        }
        return;
    }

    if (leaf == "fill/stop") {
        // Latched HERE, at the moment the message lands. A person's reaction time is already the only
        // error in this answer; adding however busy the Wi-Fi is on top of it would make a strip
        // measure short on a busy evening and right on a quiet one.
        const int n = fill.stop();
        strip.set_count(n);
        nvs.putInt("count", n);
        char v[16];
        snprintf(v, sizeof(v), "%d", n);
        say("count", v, true);
        instrument = false;
        paint();
        return;
    }
    if (leaf == "order/set") {
        char want[8];
        msg.toCharArray(want, sizeof(want));
        if (strip.order.set(want)) { nvs.putString("order", msg); say("order", want, true); }
        return;
    }
    if (leaf == "white/set")  { strip.order.white = msg == "1"; nvs.putBool("white", strip.order.white); return; }
    if (leaf == "count/set")  { strip.set_count(msg.toInt()); nvs.putInt("count", strip.count); return; }
    if (leaf == "room/set")   { nvs.putString("room", msg); return; }
}

static void findHub() {
    if (mqtt.connected() || !mhost.length()) return;
    static uint32_t tried = 0;
    if (tried && millis() - tried < 20000) return;
    tried = millis();
    // By name first, then by whatever answered last. A house whose router filters multicast is caught
    // by the second; a house that reshuffles its leases is caught by the first.
    IPAddress ip = MDNS.queryHost(mhost.c_str());
    if (ip) mqtt.setServer(ip, 1883); else mqtt.setServer((mhost + ".local").c_str(), 1883);
    char will[96];
    topic(will, sizeof(will), "status");
    if (mqtt.connect(chipHex, muser.c_str(), mpass.c_str(), will, 0, true, "offline")) {
        char sub[96];
        topic(sub, sizeof(sub), "#");
        mqtt.subscribe(sub);
        sayWhatWeAre();
    }
}

// ---------------------------------------------------------------- setup

// SAY IT ON BOTH PORTS, because on an S3 they are two different consoles and the one somebody opens
// is not the one this was written to. With USB CDC on boot `Serial` is the native port, while the ROM
// bootloader and every esp-idf log line come out of UART0 -- so a bring-up log full of IDF errors and
// no word from us is the ordinary experience, and it reads as a board that never ran our code. It ran.
static void tell(const char *line) {
    Serial.println(line);
#if ARDUINO_USB_CDC_ON_BOOT
    Serial0.println(line);
#endif
}

void setup() {
    Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
    Serial0.begin(115200);
#endif
    const uint64_t mac = ESP.getEfuseMac();
    snprintf(chipHex, sizeof(chipHex), "%06llx", (unsigned long long)(mac >> 24) & 0xFFFFFF);

    nvs.begin("strip", false);
    // isKey() first, because Preferences logs getString of a missing key as an ERROR. On a strip that
    // has never been set up every one of these is missing, which is correct -- and a first boot that
    // prints five red lines about it is a product telling its own maker it is broken when it is not.
    strip.set_count(nvs.getInt("count", PX_ASSUMED));
    strip.order.white = nvs.getBool("white", false);
    char o[8];
    (nvs.isKey("order") ? nvs.getString("order") : String("grb")).toCharArray(o, sizeof(o));
    strip.order.set(o);
    (nvs.isKey("base") ? nvs.getString("base") : String("strip")).toCharArray(base, sizeof(base));
    // Blank on a strip that has never met our hub, which is the ordinary case for one bought in a
    // shop. It is then simply a Matter light and everything above this line is all it ever does.
    mhost = nvs.isKey("mhost") ? nvs.getString("mhost") : String("");
    muser = nvs.isKey("muser") ? nvs.getString("muser") : String("");
    mpass = nvs.isKey("mpass") ? nvs.getString("mpass") : String("");

    const bool lit = px::begin(DATA_PIN);

    light.onChange([](bool state, espHsvColor_t hsv, uint8_t bri, uint16_t) -> bool {
        want_on = state;
        want_bri = bri;
        fromHSV(hsv, want_r, want_g, want_b);
        paint();
        return true;
    });
    light.begin(false, {21, 216, 120}, 180);

    Matter.begin();

    // Said on EVERY boot, not only an interesting one. The first thing anybody does with a board that
    // is not behaving is open the serial monitor, and a board that says nothing there has given them
    // no way to tell "it is working and you cannot see it" from "it never started".
    delay(600);   // USB CDC enumerates after boot; without this the first lines go nowhere
    const char letters[3] = {'r', 'g', 'b'};
    char ord[4] = {0, 0, 0, 0};
    for (int c = 0; c < 3; c++) ord[strip.order.at[c]] = letters[c];
    char line[160];
    snprintf(line, sizeof(line), "\n[strip] " FW "  chip %s  pin %d  %d lights, order %s%s",
             chipHex, DATA_PIN, strip.count, ord, strip.order.white ? "w" : "");
    tell(line);
    if (!lit) tell("[strip] THE LIGHT DRIVER DID NOT START -- nothing will light. Check the pin.");
    snprintf(line, sizeof(line), "[strip] free heap %u, psram %u",
             (unsigned)ESP.getFreeHeap(), (unsigned)ESP.getPsramSize());
    tell(line);

    if (!Matter.isDeviceCommissioned()) {
        // Lit while it waits, because being lit IS the identity check: the wall asks whether the
        // thing that just came on is theirs, and there is nothing to disambiguate -- it is two meters
        // of light and it is the only one lit (design/strip/Spine.dc.html).
        strip.solid(233, 184, 114);
        px::show(strip);
        // The code goes on the box and in the log. Our own hub reads it off the commissionable-node
        // advertisement instead, so a household with our panel still never types anything -- which is
        // what keeps design/puck/Knock.dc.html's argument intact for the people we sell to.
        snprintf(line, sizeof(line), "[strip] not commissioned yet\n  code: %s\n  qr:   %s",
                 Matter.getManualPairingCode().c_str(), Matter.getOnboardingQRCodeUrl().c_str());
        tell(line);
    } else {
        paint();
    }
    mqtt.setBufferSize(1024);
    mqtt.setCallback(onMqtt);
}

void loop() {
    if (Matter.isDeviceConnected() && mhost.length()) {
        if (!mqtt.connected()) findHub(); else mqtt.loop();
    }

    if (fill.running) {
        const int was = fill.at;
        fill.tick(millis(), strip.count);
        if (fill.at != was) {
            strip.clear();
            for (int i = 0; i < fill.at; i++)
                strip.order.bytes(233, 184, 114, &strip.buf[i * strip.order.per_pixel()]);
            px::show(strip);
            char v[16];
            snprintf(v, sizeof(v), "%d", fill.at);
            say("fill", v);
        }
    }
    delay(5);
}
