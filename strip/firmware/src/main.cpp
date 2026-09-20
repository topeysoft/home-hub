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
#include <platform/ConfigurationManager.h>

#include "pixels.h"

namespace px {
bool begin(int pin);
void show(const Pixels &p);
}  // namespace px

#define FW "0.2.0"
// Overridable at build time (-DDATA_PIN=48), because the right pin is a fact about the board on the
// desk and not about this firmware. GPIO 5 is free on a bare devkit and is a camera pin on several
// of the S3 boards people actually have lying around, which is a dead strip and no error anywhere.
#ifndef DATA_PIN
#define DATA_PIN 5
#endif
// The way back, and there has to be one. A commissioned Matter device stops advertising itself as
// commissionable -- which is correct, and means the pairing code printed at boot works exactly once.
// Every later attempt sits on "connecting" and then fails, with nothing anywhere saying why. Adding a
// SECOND ecosystem is done by opening a window from the first; starting over is this button.
// GPIO 0 is the BOOT button on every devkit and an ordinary input once running.
#ifndef BUTTON_PIN
#define BUTTON_PIN 0
#endif
#define HOLD_ARMED 1000
#define HOLD_DONE 5000

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

// WHAT THE INSTRUMENTS ARE LIT IN, AND WHY IT IS NOT THE PANEL'S AMBER.
//
// This was rgb(233,184,114) -- the panel's own --lamp, copied straight out of the palette -- and on
// the first real board it came out WHITE. Which is exactly what AGENTS.md says will happen and why
// it says never to drive an emitter with a screen token: a pastel is chosen to read as ink on a dark
// field, and an LED gives the eye no reference to read it against, so the eye takes it as white.
//
// An indicator wants its off-channels near zero. This is the same amber the panel means, said in the
// only way an emitter can say it. NOTE THIS DOES NOT APPLY TO THE HOUSEHOLD'S OWN LIGHT: that is
// illuminating a room rather than signalling, and washing it out to a saturated amber would be the
// product overriding what somebody asked for. Only the instruments use this.
static constexpr uint8_t SIG_R = 255, SIG_G = 96, SIG_B = 0;

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

#ifdef SELFTEST
// THE ONE TEST THAT SEPARATES "MY DRIVER IS WRONG" FROM "THE WIRING IS WRONG", and it needs nothing
// attached: most S3 devkits carry a single WS2812 of their own, usually on GPIO 48. Point at that,
// write one light, and watch. If the four colors come out in order the driver, the timing, the bit
// order and the RMT setup are all proven, and whatever is wrong is on the bench. If nothing happens
// on a pin that is soldered to an LED, the fault is mine.
static void selftest() {
    char line[120];
    snprintf(line, sizeof(line), "[strip] SELF TEST on pin %d, one light, ignoring what is saved", DATA_PIN);
    tell(line);
    strip.set_count(1);
    const struct { const char *name; uint8_t r, g, b; } steps[] = {
        {"RED", 255, 0, 0}, {"GREEN", 0, 255, 0}, {"BLUE", 0, 0, 255}, {"warm white", 255, 180, 110}};
    for (const auto &s : steps) {
        snprintf(line, sizeof(line), "[strip]   now showing %s", s.name);
        tell(line);
        strip.solid(s.r, s.g, s.b);
        px::show(strip);
        delay(1500);
    }
    strip.clear();
    px::show(strip);
    tell("[strip] SELF TEST over. Four colors in that order means the driver is fine and the fault is");
    tell("[strip]   on the bench. A color in the WRONG place means this board's own light is not grb,");
    tell("[strip]   which is the same question the panel asks about a strip -- and still a pass.");
}
#endif

void setup() {
    Serial.begin(115200);
#if ARDUINO_USB_CDC_ON_BOOT
    Serial0.begin(115200);
#endif
    const uint64_t mac = ESP.getEfuseMac();
    snprintf(chipHex, sizeof(chipHex), "%06llx", (unsigned long long)(mac >> 24) & 0xFFFFFF);

    pinMode(BUTTON_PIN, INPUT_PULLUP);
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

    // THE ONE PIECE OF IDENTITY WE CAN SET WITHOUT BUYING ONE.
    //
    // On the first commissioning the hub saw manufacturer TEST_VENDOR and model TEST_PRODUCT, which
    // are esp-matter's defaults for a test vendor id and are the same on every device anybody builds
    // this way -- so nothing in that registry entry could tell one of our strips from another, or
    // from somebody else's project. Vendor and product names come with a real Vendor ID and cannot be
    // had before certification. The serial number can, and it is the field that matters: it is what
    // lets the hub join the light it can see in Home Assistant to the strip it has been talking to
    // over the broker, which is what the two rows on the light's own pane are waiting for.
    //
    // Stored rather than declared, so it is read back from config on every boot after this one. The
    // Basic Information cluster has already been built by the time we get here, so the very first
    // boot after a flash still reports the default and the one after it is right.
    chip::DeviceLayer::ConfigurationMgr().StoreSerialNumber(chipHex, strlen(chipHex));

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

#ifdef SELFTEST
    selftest();
#endif

    // THE GLOW WHILE IT WAITS IS AN INSTRUMENT, and saying so is what stops it being wiped. Matter
    // starts the light off, and the moment its stack syncs that attribute our onChange fires with
    // state=false, paint() clears the strip and the "I am here" light is gone -- drawn, then undrawn,
    // a fraction of a second apart, which from the bench is indistinguishable from never lighting at
    // all. It is the same flag the fill and the color question use, and for the same reason: while an
    // instrument owns the strip, nobody else may draw on it.
    if (!Matter.isDeviceCommissioned()) {
        instrument = true;
        // Lit while it waits, because being lit IS the identity check: the wall asks whether the
        // thing that just came on is theirs, and there is nothing to disambiguate -- it is two meters
        // of light and it is the only one lit (design/strip/Spine.dc.html).
        strip.solid(SIG_R, SIG_G, SIG_B);
        px::show(strip);
        // The code goes on the box and in the log. Our own hub reads it off the commissionable-node
        // advertisement instead, so a household with our panel still never types anything -- which is
        // what keeps design/puck/Knock.dc.html's argument intact for the people we sell to.
        snprintf(line, sizeof(line), "[strip] not commissioned yet\n  code: %s\n  qr:   %s",
                 Matter.getManualPairingCode().c_str(), Matter.getOnboardingQRCodeUrl().c_str());
        tell(line);
    } else {
        tell("[strip] already commissioned -- the pairing code above works ONCE and is spent.");
        tell("[strip]   to add another ecosystem, open a window from the one that has it.");
        tell("[strip]   to start over, hold the BOOT button for five seconds.");
        paint();
    }
    mqtt.setBufferSize(1024);
    mqtt.setCallback(onMqtt);
}

// Held down: the strip goes red to say the hold has registered, and forgets the house if it is kept
// there. The feedback is the point -- a reset you cannot tell is happening is one people do twice,
// and the second one lands on a device that was already back to new.
static void button() {
    static uint32_t down = 0;
    static bool armed = false;
    // A HOLD ONLY COUNTS ONCE THE BUTTON HAS BEEN SEEN LET GO, and without this the feature eats the
    // product. GPIO 0 is BOOT: it is held to flash, it is a strapping pin, and on some boards it sits
    // low. Any of those and the device factory-resets itself five seconds into EVERY boot, for ever,
    // so it never stays advertising long enough to be commissioned -- which from the outside is a
    // device that pairs once and then never again, with the log scrolling past too fast to read.
    static bool released = false;
    if (digitalRead(BUTTON_PIN) == HIGH) released = true;
    else if (!released) {
        static bool moaned = false;
        if (!moaned && millis() > 3000) {
            moaned = true;
            tell("[strip] the button has been down since boot, so it is being ignored. Let it go once.");
        }
        return;
    }
    if (digitalRead(BUTTON_PIN) == LOW) {
        if (!down) down = millis();
        const uint32_t held = millis() - down;
        if (!armed && held > HOLD_ARMED) {
            armed = true;
            instrument = true;
            strip.solid(255, 0, 0);
            px::show(strip);
            tell("[strip] keep holding to forget the house...");
        }
        if (held > HOLD_DONE) {
            tell("[strip] forgetting the house. It will come back new.");
            strip.clear();
            px::show(strip);
            // OURS FIRST, because decommission() is esp_matter::factory_reset(), which erases the NVS
            // partition and restarts the chip itself. Anything written after it is a race with a
            // reboot that has already been asked for, and the first version of this put the clear and
            // a restart of its own on the far side of exactly that.
            nvs.clear();
            nvs.end();
            delay(50);
            Matter.decommission();
            delay(2000);                 // it restarts itself; this is only for if it ever does not
            ESP.restart();
        }
    } else if (down) {
        down = 0;
        if (armed) {   // let go in time: nothing happened, and it says so by going back
            armed = false;
            instrument = !Matter.isDeviceCommissioned();
            if (instrument) { strip.solid(SIG_R, SIG_G, SIG_B); px::show(strip); } else paint();
        }
    }
}

void loop() {
    button();

    // The knock is over the moment somebody has taken it. Hand the strip back, and draw whatever the
    // household's own state says -- which is off, until they turn it on, exactly like any other new
    // light in their app. Without this it sat on the setup glow for ever and looked stuck.
    static bool taken = false;
    if (!taken && Matter.isDeviceCommissioned()) {
        taken = true;
        instrument = false;
        tell("[strip] commissioned. The light is the household's now.");
        paint();
    }

    if (Matter.isDeviceConnected() && mhost.length()) {
        if (!mqtt.connected()) findHub(); else mqtt.loop();
    }

    if (fill.running) {
        const int was = fill.at;
        fill.tick(millis(), strip.count);
        if (fill.at != was) {
            strip.clear();
            for (int i = 0; i < fill.at; i++)
                strip.order.bytes(SIG_R, SIG_G, SIG_B, &strip.buf[i * strip.order.per_pixel()]);
            px::show(strip);
            char v[16];
            snprintf(v, sizeof(v), "%d", fill.at);
            say("fill", v);
        }
    }
    delay(5);
}
