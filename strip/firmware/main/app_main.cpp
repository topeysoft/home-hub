// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// A light strip controller: a Matter device in its own right, and a little more in a house with our hub.
//
// WHY THIS IS ESP-IDF AND NOT ARDUINO, because it was Arduino first and the hardware settled it. The
// Arduino framework ships its Matter libraries with CONFIG_ENABLE_CHIPOBLE unset on every target, so
// a strip built that way never advertises itself for commissioning: it has to be on the Wi-Fi
// already and be found over mDNS. Which means a household with an Apple TV and no hub of ours could
// not set one up at all. An evening went on a strip that would not pair, a BLE scan that found
// fifty-nine devices and not ours, and finally the same board running esp-matter's own example
// saying "CHIPoBLE advertising started" with nothing configured. docs/strip.md has both scans.
//
// So Matter carries the Wi-Fi credentials and the commissioning, in one encrypted flow, and the
// hand-rolled provisioning this firmware started with -- which put a household's Wi-Fi password on
// an open BLE link -- is gone rather than fixed.
//
// TWO WAYS TO OWN ONE, and the first is the whole product on its own:
//
//   Any Matter hub    commission it with the code. It is a color light: on, off, dim, any color, any
//                     warmth, in whatever app the household already has. Nothing of ours is involved.
//   Our hub as well   the same, plus the two questions Matter has no words for -- which order its
//                     colors come out in, and how far it goes -- over MQTT. A strip with no broker in
//                     its settings simply does not do this half and is none the worse for it.
//
// WHAT MATTER CANNOT SAY: the Extended Color Light is one color for the whole fitting. It has no
// concept of a pixel, so the setup instruments and anything spatial are ours and always will be.
// That is the same split Hue and Nanoleaf run and it is not a compromise.
//
// THE LIGHT NEVER REPORTS A FAULT BY CHANGING COLOR. This is the one place a strip is the opposite of
// the bridge puck. docs/puck-light.md puts a fault above a puck's light, because a puck glowing while
// its bridge is down is furniture that lies. A strip is behind somebody's television while they watch
// a film: turning it amber because a broker blinked is the product breaking, not reporting.
#include <esp_err.h>
#include <esp_log.h>
#include <esp_mac.h>
#include <esp_system.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <nvs_flash.h>
#include <nvs.h>
#include <driver/gpio.h>
#include <esp_wifi.h>
#include <esp_timer.h>
#include <mqtt_client.h>

#include <esp_heap_caps.h>

#include <esp_matter.h>
#include <esp_matter_console.h>
#include <esp_matter_ota.h>
#include <app/server/Server.h>
#include <setup_payload/OnboardingCodesUtil.h>

#include "pixels.h"
#include "prov.h"

using namespace esp_matter;
using namespace esp_matter::attribute;
using namespace esp_matter::endpoint;
using namespace chip::app::Clusters;

#define FW "0.3.0"
#ifndef DATA_PIN
#define DATA_PIN 5
#endif
// GPIO 0 is BOOT on every devkit and an ordinary input once running. A hold only counts once it has
// been seen let go: it is held down to flash, it is a strapping pin, and on some boards it sits low,
// and any of those would otherwise factory-reset the device five seconds into every boot for ever.
#ifndef BUTTON_PIN
#define BUTTON_PIN 0
#endif
#define HOLD_ARMED 1000
#define HOLD_DONE 5000

static const char *TAG = "strip";

// WHAT THE INSTRUMENTS ARE LIT IN, AND WHY IT IS NOT THE PANEL'S AMBER. This was rgb(233,184,114) --
// the panel's own --lamp, copied out of the palette -- and on the first real board it came out WHITE,
// which is exactly what AGENTS.md says a pastel does on an emitter and why it says never to drive one
// with a screen token. An indicator wants its off-channels near zero. The household's own light is
// deliberately untouched by this: that one is lighting a room rather than signalling.
static constexpr uint8_t SIG_R = 255, SIG_G = 96, SIG_B = 0;

static px::Pixels strip;
static px::Fill fill;
static nvs_handle_t nvs;
static char chipHex[13];
static char base[16] = "strip";
static uint16_t light_endpoint = 0;

// The setup instruments own the strip while they run, and the household's own color goes back the
// moment they stop. Without this a fill that was never stopped leaves somebody's living room running
// a test pattern for ever -- and, on the Arduino version, the waiting glow was drawn and then wiped a
// fraction of a second later by the first attribute sync, which from a bench looks like a dead strip.
static bool instrument = false;
// The knocking is over and nobody took the strip. It keeps the light, drained, rather than going
// dark, and the rhythm stops.
static bool waiting_over = false;
static bool want_on = false;
static uint8_t want_r = 255, want_g = 180, want_b = 110, want_bri = 200;

static esp_mqtt_client_handle_t mqtt = nullptr;
static bool broker_up = false;

static inline uint32_t now_ms() { return (uint32_t)(esp_timer_get_time() / 1000); }

// ---------------------------------------------------------------- settings

static std::string get_str(const char *key, const char *fallback) {
    size_t len = 0;
    if (nvs_get_str(nvs, key, nullptr, &len) != ESP_OK || len == 0) return fallback;
    std::string out(len, '\0');
    if (nvs_get_str(nvs, key, out.data(), &len) != ESP_OK) return fallback;
    out.resize(len - 1);
    return out;
}
static void put_str(const char *key, const std::string &v) {
    nvs_set_str(nvs, key, v.c_str());
    nvs_commit(nvs);
}
static int get_i32(const char *key, int fallback) {
    int32_t v = 0;
    return nvs_get_i32(nvs, key, &v) == ESP_OK ? (int)v : fallback;
}
static void put_i32(const char *key, int v) { nvs_set_i32(nvs, key, v); nvs_commit(nvs); }

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

// Matter carries color as hue and saturation, 0-254 each. Value is the level, which is its own
// attribute -- so this is at full output and paint() scales it, exactly as the panel's color.ts does
// and for the same reason: a swatch says which color, the dimmer says how much of it.
static void from_hs(uint8_t hue, uint8_t sat, uint8_t &r, uint8_t &g, uint8_t &b) {
    const float h = hue * 360.0f / 254.0f / 60.0f;
    const float s = sat / 254.0f;
    const int i = ((int)h) % 6;
    const float f = h - (int)h;
    const float p = 1 - s, q = 1 - s * f, t = 1 - s * (1 - f);
    float c[3];
    switch (i) {
        case 0: c[0] = 1; c[1] = t; c[2] = p; break;
        case 1: c[0] = q; c[1] = 1; c[2] = p; break;
        case 2: c[0] = p; c[1] = 1; c[2] = t; break;
        case 3: c[0] = p; c[1] = q; c[2] = 1; break;
        case 4: c[0] = t; c[1] = p; c[2] = 1; break;
        default: c[0] = 1; c[1] = p; c[2] = q; break;
    }
    r = (uint8_t)(c[0] * 255); g = (uint8_t)(c[1] * 255); b = (uint8_t)(c[2] * 255);
}

// ---------------------------------------------------------------- our hub, when there is one

static void say(const char *leaf, const char *payload, int retain = 0) {
    if (!mqtt || !broker_up) return;
    char t[96];
    snprintf(t, sizeof(t), "%s/%s/%s", base, chipHex, leaf);
    esp_mqtt_client_publish(mqtt, t, payload, 0, 1, retain);
}

static void say_what_we_are() {
    char v[16];
    snprintf(v, sizeof(v), "%d", strip.count);
    say("count", v, 1);
    const char letters[3] = {'r', 'g', 'b'};
    char ord[4] = {0, 0, 0, 0};
    for (int c = 0; c < 3; c++) ord[strip.order.at[c]] = letters[c];
    say("order", ord, 1);
    say("status", "online", 1);
}

static void on_command(const std::string &leaf, const std::string &msg) {
    if (leaf == "hello") { say_what_we_are(); return; }

    if (leaf == "show/set") {
        if (msg.rfind("raw ", 0) == 0) {
            int b0 = 0, b1 = 0, b2 = 0;
            if (sscanf(msg.c_str() + 4, "%d %d %d", &b0, &b1, &b2) != 3) return;
            instrument = true;
            fill.running = false;
            // Exactly as given. Putting these through the strip's mapping would be applying the very
            // guess the question exists to test (pixels.h, raw3).
            strip.raw3((uint8_t)b0, (uint8_t)b1, (uint8_t)b2);
            px::show(strip);
        } else if (msg == "fill") {
            instrument = true;
            strip.clear();
            px::show(strip);
            fill.start(now_ms());
        } else if (msg == "off") {
            instrument = false;
            paint();
        }
        return;
    }

    if (leaf == "fill/stop") {
        // Latched HERE, at the moment the message lands. A person's reaction time is already the only
        // error in this answer; adding however busy the Wi-Fi is would make a strip measure short on a
        // busy evening and right on a quiet one, which is the worst kind of wrong.
        const int n = fill.stop();
        strip.set_count(n);
        put_i32("count", n);
        char v[16];
        snprintf(v, sizeof(v), "%d", n);
        say("count", v, 1);
        instrument = false;
        paint();
        return;
    }
    if (leaf == "order/set") {
        if (strip.order.set(msg.c_str())) { put_str("order", msg); say("order", msg.c_str(), 1); }
        return;
    }
    if (leaf == "white/set") {
        strip.order.white = (msg == "1");
        nvs_set_u8(nvs, "white", strip.order.white); nvs_commit(nvs);
        return;
    }
    if (leaf == "count/set") { strip.set_count(atoi(msg.c_str())); put_i32("count", strip.count); return; }
    if (leaf == "room/set")  { put_str("room", msg); return; }
}

static void mqtt_event(void *arg, esp_event_base_t, int32_t id, void *data) {
    auto *e = (esp_mqtt_event_handle_t)data;
    switch ((esp_mqtt_event_id_t)id) {
        case MQTT_EVENT_CONNECTED: {
            broker_up = true;
            char sub[96];
            snprintf(sub, sizeof(sub), "%s/%s/#", base, chipHex);
            esp_mqtt_client_subscribe(mqtt, sub, 1);
            say_what_we_are();
            break;
        }
        case MQTT_EVENT_DISCONNECTED: broker_up = false; break;
        case MQTT_EVENT_DATA: {
            std::string topic(e->topic, e->topic_len), msg(e->data, e->data_len);
            const std::string prefix = std::string(chipHex) + "/";
            const size_t cut = topic.find(prefix);
            if (cut == std::string::npos) break;
            on_command(topic.substr(cut + prefix.size()), msg);
            break;
        }
        default: break;
    }
}

static void find_hub() {
    const std::string host = get_str("mhost", "");
    // Blank on a strip that has never met our hub, which is the ordinary case for one bought in a
    // shop. It is then simply a Matter light and none of this half ever runs.
    if (host.empty()) return;
    const std::string uri = "mqtt://" + host + ".local:1883";
    esp_mqtt_client_config_t cfg = {};
    cfg.broker.address.uri = uri.c_str();
    cfg.credentials.username = strdup(get_str("muser", "").c_str());
    cfg.credentials.authentication.password = strdup(get_str("mpass", "").c_str());
    char will[96];
    snprintf(will, sizeof(will), "%s/%s/status", base, chipHex);
    cfg.session.last_will.topic = strdup(will);
    cfg.session.last_will.msg = "offline";
    cfg.session.last_will.retain = 1;
    mqtt = esp_mqtt_client_init(&cfg);
    if (!mqtt) return;
    esp_mqtt_client_register_event(mqtt, MQTT_EVENT_ANY, mqtt_event, nullptr);
    esp_mqtt_client_start(mqtt);
}

// ---------------------------------------------------------------- Matter

static esp_err_t on_attribute(attribute::callback_type_t type, uint16_t endpoint_id, uint32_t cluster_id,
                              uint32_t attribute_id, esp_matter_attr_val_t *val, void *) {
    if (type != PRE_UPDATE || endpoint_id != light_endpoint) return ESP_OK;
    static uint8_t hue = 21, sat = 216;
    if (cluster_id == OnOff::Id && attribute_id == OnOff::Attributes::OnOff::Id) {
        want_on = val->val.b;
    } else if (cluster_id == LevelControl::Id && attribute_id == LevelControl::Attributes::CurrentLevel::Id) {
        want_bri = val->val.u8;
    } else if (cluster_id == ColorControl::Id) {
        if (attribute_id == ColorControl::Attributes::CurrentHue::Id) hue = val->val.u8;
        else if (attribute_id == ColorControl::Attributes::CurrentSaturation::Id) sat = val->val.u8;
        else return ESP_OK;
        from_hs(hue, sat, want_r, want_g, want_b);
    } else {
        return ESP_OK;
    }
    paint();
    return ESP_OK;
}

static esp_err_t on_identify(identification::callback_type_t, uint16_t, uint8_t, uint8_t, void *) {
    return ESP_OK;
}

static void on_event(const ChipDeviceEvent *event, intptr_t) {
    // The knock is over the moment somebody has taken it: hand the strip back and draw whatever the
    // household's own state says, which is off until they turn it on, exactly like any other new
    // light in their app. Without this it sat on the setup glow for ever, looking stuck.
    if (event->Type == chip::DeviceLayer::DeviceEventType::kCHIPoBLEConnectionClosed) prov::disconnected();

    // TWO DAYS LATER, AND NOBODY CAME (design/strip/KnockTwoDays.dc.html). When the advertisement
    // finally stops, a strip nobody has taken must read as STOPPED rather than as broken: going
    // dark is what a dead strip does. So the rhythm ends and a drained version of the same glow
    // stays, which is the rule the whole panel runs on -- what was asking is still there, quieter,
    // saying it is no longer asking. A power cycle starts the two days again.
    if (event->Type == chip::DeviceLayer::DeviceEventType::kCHIPoBLEAdvertisingChange &&
        event->CHIPoBLEAdvertisingChange.Result == chip::DeviceLayer::kActivity_Stopped && instrument &&
        !waiting_over) {
        if (prov::keep_knocking()) return;
        waiting_over = true;
        strip.solid(SIG_R / 6, SIG_G / 6, SIG_B / 6);
        px::show(strip);
        ESP_LOGI(TAG, "nobody came. Still here, no longer asking -- power it off and on to ask again");
    }
    if (event->Type == chip::DeviceLayer::DeviceEventType::kCommissioningComplete) {
        ESP_LOGI(TAG, "commissioned. The light is the household's now.");
        instrument = false;
        paint();
        find_hub();
    }
}

// ---------------------------------------------------------------- the button, and the fill

// THE RHYTHM, DRAWN. Four groups of flashes with a gap between groups and a pause after the last,
// repeating; the whole thing is a function of time so there is nothing to keep in step. Written to the
// strip only on a change of state, because a WS2812 latches and rewriting a steady frame is how the
// bridge puck turned one misread into twenty-five a second (AGENTS.md).
static constexpr uint32_t RH_ON = 220, RH_OFF = 220, RH_GAP = 700, RH_PAUSE = 1800;
static bool rhythm_lit(uint32_t t) {
    const uint8_t *r = prov::rhythm();
    uint32_t period = RH_PAUSE;
    for (int g = 0; g < 4; g++) period += r[g] * (RH_ON + RH_OFF) + RH_GAP;
    uint32_t at = t % period;
    for (int g = 0; g < 4; g++) {
        const uint32_t group = r[g] * (RH_ON + RH_OFF);
        if (at < group) return (at % (RH_ON + RH_OFF)) < RH_ON;
        at -= group;
        if (at < RH_GAP) return false;
        at -= RH_GAP;
    }
    return false;
}

// THE PRESS, ANSWERED ON THE THING THAT WAS PRESSED. A household standing at a socket with the wall
// in another room has nothing else to tell them it worked, and "nothing happened" is what a dead
// button and a button that is not wired both look like.
static void blink_back() {
    strip.solid(255, 255, 255);
    px::show(strip);
    vTaskDelay(pdMS_TO_TICKS(120));
    strip.solid(SIG_R, SIG_G, SIG_B);
    px::show(strip);
}

static void housekeeping(void *) {
    bool released = false, armed = false, was_lit = true;
    uint32_t loud_at = 0;
    uint32_t down = 0;
    for (;;) {
        // While the strip is waiting through our door it flashes its rhythm; once credentials have
        // arrived it holds the steady glow until the manager is done with the Wi-Fi.
        // Every ten seconds while the strip is still knocking, in case CHIP has quietly dropped the
        // advertisement to its slow interval and put the strip out of earshot of the hub.
        // A link that has just come up needs slower parameters before it times out in somebody
        // else's service discovery, and nothing tells us when one appears; see prov.cpp.
        prov::be_patient_with_everyone();

        if (instrument && !waiting_over && now_ms() - loud_at > 10000) {
            loud_at = now_ms();
            prov::stay_loud();
        }

        // WHAT THE STRIP IS DOING WHILE IT WAITS (design/strip/Press.dc.html). On our own door it is
        // simply LIT, steady, end to end: a steady light is a thing you can point at, and it says
        // nothing a stranger could use. It only flashes on the rung below, where four counts ARE the
        // secret -- which is what rhythm()[0] distinguishes. Written on a change of state only,
        // because a WS2812 latches and rewriting a steady frame is how the bridge puck turned one
        // misread into twenty-five a second (AGENTS.md).
        if (instrument && !waiting_over && !armed && !fill.running) {
            const bool lit = prov::busy() || !prov::rhythm()[0] || rhythm_lit(now_ms());
            if (lit != was_lit) {
                if (lit) strip.solid(SIG_R, SIG_G, SIG_B); else strip.clear();
                px::show(strip);
                was_lit = lit;
            }
        }
        // The household said nobody can reach the button, so the door is being shut and reopened a
        // rung lower. It has to be driven from here rather than from the handler that heard it: that
        // one runs on the manager's own task, inside the manager it would be tearing down.
        prov::tend_the_door();
        // A hold only counts once the button has been seen let go; see BUTTON_PIN above.
        //
        // AND IT SAYS WHEN IT SEES ONE. A household holding the button and getting nothing has no
        // way to tell a button that is not wired from a hold that is not long enough from the wrong
        // button entirely -- on a devkit RST sits next to BOOT and looks identical. On 21 September
        // a five-second hold produced a reboot and no log line at all, which is what the wrong
        // button looks like and what a dead pin looks like, and there was no way to tell them apart
        // without a flash cycle. One line at the press ends that for good.
        if (gpio_get_level((gpio_num_t)BUTTON_PIN)) released = true;
        else if (released) {
            if (!down) { down = now_ms(); ESP_LOGI(TAG, "button down -- hold %d s to forget the house", HOLD_DONE / 1000); }
            const uint32_t held = now_ms() - down;
            if (!armed && held > HOLD_ARMED) {
                armed = true;
                instrument = true;
                strip.solid(255, 0, 0);
                px::show(strip);
                ESP_LOGW(TAG, "keep holding to forget the house...");
            }
            if (held > HOLD_DONE) {
                ESP_LOGW(TAG, "forgetting the house. It will come back new.");
                strip.clear();
                px::show(strip);
                nvs_erase_all(nvs);
                nvs_commit(nvs);
                esp_matter::factory_reset();   // erases Matter's own storage and restarts
                vTaskDelay(pdMS_TO_TICKS(2000));
                esp_restart();
            }
        }
        if (gpio_get_level((gpio_num_t)BUTTON_PIN) && down) {
            const uint32_t held = now_ms() - down;
            down = 0;
            if (armed) { armed = false; instrument = !chip::Server::GetInstance().GetFabricTable().FabricCount();
                         if (instrument) { strip.solid(SIG_R, SIG_G, SIG_B); px::show(strip); } else paint(); }
            // A SHORT PRESS IS THE WHOLE HANDSHAKE (design/door/PressIt.dc.html). It is counted on the
            // way UP and only if the hold never armed, so the two lengths of the same button cannot be
            // confused by anybody doing either of them on purpose: under a second lets somebody in,
            // five forgets the house, and one second turns the strip red to say which is coming.
            //
            // AND THE THING THAT WAS PRESSED IS WHAT ANSWERS. One bright blink on the strip itself,
            // because the wall may be in another room and the person is looking at their hand.
            else if (held < HOLD_ARMED && prov::press()) {
                blink_back();
                was_lit = true;
            }
        }

        if (fill.running) {
            const int was = fill.at;
            fill.tick(now_ms(), strip.count);
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
        // TEN, NOT FIVE. The tick is 100 Hz, so pdMS_TO_TICKS(5) is 0 ticks, and vTaskDelay(0) only
        // yields to tasks at this priority or above -- never to the idle task at 0. This loop was
        // therefore a busy spin that starved IDLE0 and tripped the task watchdog every five seconds.
        // Anything under one tick here silently means "do not sleep at all".
        vTaskDelay(pdMS_TO_TICKS(10));
    }
}

#ifdef SELFTEST
// ONE LIGHT, FOUR COLORS, NOTHING ATTACHED. Most S3 devkits carry a WS2812 of their own, usually on
// GPIO 48: point at that and watch. Four colors in order proves the driver, the timing, the bit order
// and the RMT setup, and says the fault is on the bench. A color in the wrong place means this board's
// own light is not grb -- the same question the panel asks about a strip -- and is still a pass.
// Nothing at all means the fault is in pixels.cpp.
static void selftest() {
    // What is saved is borrowed, not spent. Without putting it back the strip runs on one pixel for
    // the rest of its life and lights exactly one LED however long it really is -- which on a board
    // somebody has just paired reads as a broken strip rather than as a self test that forgot.
    const int saved = strip.count;
    ESP_LOGW(TAG, "SELF TEST on pin %d, one light, borrowing what is saved", DATA_PIN);
    strip.set_count(1);
    const struct { const char *name; uint8_t r, g, b; } steps[] = {
        {"RED", 255, 0, 0}, {"GREEN", 0, 255, 0}, {"BLUE", 0, 0, 255}, {"warm white", 255, 180, 110}};
    for (const auto &st : steps) {
        ESP_LOGW(TAG, "  now showing %s", st.name);
        strip.solid(st.r, st.g, st.b);
        px::show(strip);
        vTaskDelay(pdMS_TO_TICKS(1500));
    }
    strip.clear();
    px::show(strip);
    strip.set_count(saved);
    ESP_LOGW(TAG, "SELF TEST over, %d lights restored. Four colors in that order means the fault is "
                  "on the bench.", strip.count);
}
#endif

// Free internal DRAM, which is the one that runs out. Printed at the few moments that decide
// whether a second BLE service fits: docs/strip.md item 12 exists because every heap figure
// this project had written down came from the Arduino build and meant nothing here.
static void heap(const char *when) {
    ESP_LOGI(TAG, "heap %-16s free %u  largest block %u  low water %u", when,
             (unsigned)heap_caps_get_free_size(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
             (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL | MALLOC_CAP_8BIT),
             (unsigned)esp_get_minimum_free_heap_size());
}

extern "C" void app_main() {
    heap("at boot");
    nvs_flash_init();
    nvs_open("strip", NVS_READWRITE, &nvs);

    uint8_t mac[6] = {0};
    esp_read_mac(mac, ESP_MAC_WIFI_STA);
    snprintf(chipHex, sizeof(chipHex), "%02x%02x%02x", mac[3], mac[4], mac[5]);

    strip.set_count(get_i32("count", PX_ASSUMED));
    uint8_t w = 0;
    nvs_get_u8(nvs, "white", &w);
    strip.order.white = w;
    strip.order.set(get_str("order", "grb").c_str());
    snprintf(base, sizeof(base), "%s", get_str("base", "strip").c_str());

    const bool lit = px::begin(DATA_PIN);
    gpio_config_t btn = {};
    btn.pin_bit_mask = 1ULL << BUTTON_PIN;
    btn.mode = GPIO_MODE_INPUT;
    btn.pull_up_en = GPIO_PULLUP_ENABLE;
    gpio_config(&btn);

    // One console, which the Arduino version could not manage: there, the framework logs came out of
    // UART0 while our own Serial was the native USB port, so a bring-up log full of errors and not one
    // word from us was the ordinary experience and read as a board that never ran our code.
    const char letters[3] = {'r', 'g', 'b'};
    char ord[4] = {0, 0, 0, 0};
    for (int c = 0; c < 3; c++) ord[strip.order.at[c]] = letters[c];
    ESP_LOGI(TAG, FW "  chip %s  pin %d  %d lights, order %s%s", chipHex, DATA_PIN, strip.count, ord,
             strip.order.white ? "w" : "");
    if (!lit) ESP_LOGE(TAG, "THE LIGHT DRIVER DID NOT START -- nothing will light. Check the pin.");

#ifdef SELFTEST
    selftest();
#endif

    node::config_t node_config;
    node_t *node = node::create(&node_config, on_attribute, on_identify);
    if (!node) { ESP_LOGE(TAG, "no Matter node"); return; }

    extended_color_light::config_t light_config;
    light_config.on_off.on_off = false;
    light_config.level_control.current_level = 180;
    light_config.level_control.on_level = 180;
    light_config.color_control.color_mode = (uint8_t)ColorControl::ColorMode::kCurrentHueAndCurrentSaturation;
    light_config.color_control.enhanced_color_mode = (uint8_t)ColorControl::ColorMode::kCurrentHueAndCurrentSaturation;
    endpoint_t *ep = extended_color_light::create(node, &light_config, ENDPOINT_FLAG_NONE, nullptr);
    if (!ep) { ESP_LOGE(TAG, "no light endpoint"); return; }
    light_endpoint = endpoint::get_id(ep);

    // Before Matter, and it has to be: CHIP will not take another GATT service once its own stack
    // has started, and there is no second chance at it. See prov.h. A strip somebody has already
    // taken offers no door, so it does not reserve one either.
    const bool ours = get_i32("ours", 0) != 0;
    char prov_name[24];  // "PROV_" and six hex digits; sized up only to keep the compiler quiet
    snprintf(prov_name, sizeof(prov_name), "PROV_%s", chipHex);  // prov::reserve cuts it to fit
    if (!ours && prov::reserve(prov_name) != ESP_OK)
        ESP_LOGE(TAG, "our own door will not open this boot");

    heap("before Matter");
    esp_matter::start(on_event);
    heap("after Matter");

    // Lit while it waits, because being lit IS the identity check: the wall asks whether the thing
    // that just came on is theirs, and there is nothing to disambiguate -- it is two meters of light
    // and it is the only one lit (design/strip/Spine.dc.html). Marked as an instrument so the first
    // attribute sync cannot quietly wipe it, which is exactly what happened on the Arduino version.
    // HAS ANYBODY TAKEN THIS STRIP? The fabric table cannot answer it on its own: a strip that came
    // through our own door never joins a Matter fabric, so FabricCount stays 0 for the rest of its
    // life. Asking only that made an adopted strip flash its rhythm at every boot and try to reopen
    // a door it had already been through -- and by then CHIP owns the Wi-Fi driver, so the attempt
    // failed with "sta is connecting, cannot set config" and the wall said it was waiting when it
    // was not. "Ours" is remembered in NVS beside everything else the household chose.
    if (chip::Server::GetInstance().GetFabricTable().FabricCount() == 0 && !ours) {
        instrument = true;
        strip.solid(SIG_R, SIG_G, SIG_B);
        px::show(strip);
        ESP_LOGI(TAG, "nobody has taken this strip yet -- both doors are open");
        // The four things a strip needs to find us again after a reboot. Anything else the hub
        // offers is refused out loud rather than silently dropped, so a mismatch between the two
        // halves shows up on the bench instead of as a strip that never speaks.
        prov::on_taken([](bool yes) { put_i32("ours", yes ? 1 : 0); });
        prov::on_hub_details([](const char *key, const char *value) {
            for (const char *k : {"mhost", "muser", "mpass", "base"})
                if (!strcmp(key, k)) { put_str(key, value); return true; }
            return false;
        });
        // A STRIP THAT TOOK CREDENTIALS AND NEVER JOINED CANNOT OPEN ITS DOOR AGAIN, and this is a
        // way to brick one in somebody's living room. Setup hands over a Wi-Fi name and password;
        // the strip stores them and tries; the join fails -- a typo, the wrong band, a network that
        // has since moved -- so NETWORK_PROV_WIFI_CRED_SUCCESS never fires and `ours` is never
        // written. At the next boot CHIP is already connecting with those stored credentials, and
        // the provisioning manager cannot set an empty config over a connecting STA: the door comes
        // back ESP_ERR_WIFI_STATE and this is a strip that advertises itself for ever and can never
        // be taken by anybody. Seen on a real hub on 21 September, where it read as "the hub could
        // not finish setting it up" and nothing said why.
        //
        // We are inside "no fabric and not ours", so this strip has never finished setup with
        // anybody. Whatever is stored is from an attempt that failed, and it is in the way.
        const esp_err_t opened = prov::open();
        if (opened == ESP_ERR_WIFI_STATE && get_i32("wificlr", 0) == 0) {
            // Once per stored-credential mess, so a restore that does not take cannot become a
            // reboot loop in a house. The flag is cleared the moment a door opens normally.
            put_i32("wificlr", 1);
            ESP_LOGW(TAG, "credentials from a setup that never finished are in the way. "
                          "Clearing them and starting over");
            esp_wifi_restore();
            vTaskDelay(pdMS_TO_TICKS(250));
            esp_restart();
        }
        if (opened != ESP_OK) {
            ESP_LOGE(TAG, "our own door did not open (%s); only Matter's is on", esp_err_to_name(opened));
        } else if (get_i32("wificlr", 0) != 0) {
            put_i32("wificlr", 0);
        }
        // The code this strip can be paired with, said out loud. Without this the only way to
        // commission it was to know that a test build uses the default passcode, which is exactly
        // the sort of thing that is obvious until the day it is not.
        PrintOnboardingCodes(chip::RendezvousInformationFlag::kBLE);
    } else {
        ESP_LOGI(TAG, "already set up, %s", ours ? "through our own door" : "by somebody else");
        // AND THE OTHER DOOR STAYS SHUT (design/strip/Both.dc.html). CHIP opens a commissioning
        // window by itself whenever there are no fabrics, and a strip taken through our door never
        // has one -- so without this it goes back to advertising as commissionable at every boot,
        // and anybody in radio range could put it into their own app.
        if (ours) {
            const CHIP_ERROR e = chip::DeviceLayer::PlatformMgr().ScheduleWork([](intptr_t) {
                chip::Server::GetInstance().GetCommissioningWindowManager().CloseCommissioningWindow();
                ESP_LOGI(TAG, "Matter's window shut again; this strip is still ours");
            });
            if (e != CHIP_NO_ERROR) ESP_LOGE(TAG, "Matter's window stayed open: %s", chip::ErrorStr(e));
        }
        paint();
        find_hub();
    }

    xTaskCreate(housekeeping, "strip", 4096, nullptr, 5, nullptr);
}
