// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// The half of guard.h that reads pins. Rev A only: a devkit has no switches to hold off, no supply
// to measure and no current monitor, so there it is the few lines at the foot that say yes to
// everything -- which is exactly what the devkit did before there was a guard.
#include "guard.h"

#include <stdio.h>
#include <string.h>

#if defined(STRIP_BOARD_REVA)

#include <driver/gpio.h>
#include <esp_adc/adc_cali.h>
#include <esp_adc/adc_cali_scheme.h>
#include <esp_adc/adc_oneshot.h>
#include <esp_log.h>
#include <esp_timer.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <nvs.h>

namespace guard {
namespace {

const char *TAG = "guard";

// A switch takes about 11 ms to bring a run up at 24 V (its dV/dt capacitor), and a strip's chips
// want a moment after that before they will take a frame. Anything sent sooner is lost.
constexpr uint32_t COME_UP_MS = 60;
// Over-voltage while running: the board's own cutoff is 30.1 V, so this is a second line just past it,
// with room either side so a supply sitting on the edge does not flicker the runs.
constexpr float OVER_V = 30.5f, BACK_V = 29.5f;
// A frame has to have been on the strip this long before the monitor reading means that frame: the
// last light latches as the frame ends, and the filter at the pin is a tenth of a millisecond.
constexpr uint32_t SETTLED_MS = 20;
// Brighter again only by a clear step, and resent no more than five times a second, so a reading at
// the edge cannot turn into a strip that shimmers.
constexpr uint16_t BRIGHTER_BY = 10;
constexpr uint32_t RESEND_EVERY_MS = 200;
// Said when something has changed, and otherwise this often.
constexpr uint32_t SAY_EVERY_MS = 10000;

struct Chan { adc_channel_t ch = ADC_CHANNEL_0; adc_cali_handle_t cali = nullptr; adc_atten_t atten = ADC_ATTEN_DB_6; bool ok = false; };

struct RunState {
    Faults faults;
    Limiter lim;
    uint8_t kept = NONE;       // what it was first lit on, from NVS
    uint8_t held = STARTING;   // sticky reasons (SUPPLY, TRIPS, WIRING) and STARTING; RANGE comes and goes
    bool on = false, up = false;
    uint32_t on_at = 0;
    float amps = 0;
    uint32_t sent_load = 0, picture_load = 0, sent_at = 0;
    uint16_t sent_scale = 256;
    int lights = 0;
};

adc_oneshot_unit_handle_t adc = nullptr;
Chan vsense, ntc, imon[board::OUTPUTS];
nvs_handle_t nv = 0;
RunState runs[board::OUTPUTS];
uint8_t supply = NONE;        // the kind of supply, as decided with both runs off
bool decided = false, over = false;
uint8_t seen = NONE;
int seen_times = 0;
float volts = 0, celsius = NAN;
uint32_t measured_at = 0, warmed_at = 0, resent_at = 0, said_at = 0;
uint32_t said_shape = 0;      // what was last said, apart from the numbers that drift
bool said_once = false;

uint32_t now_ms() { return (uint32_t)(esp_timer_get_time() / 1000); }

void key(char *out, int run, const char *k) { snprintf(out, 16, "%s%s", k, run ? "2" : ""); }

bool open_chan(Chan &c, int gpio, adc_atten_t atten) {
    adc_unit_t unit;
    if (adc_oneshot_io_to_channel(gpio, &unit, &c.ch) != ESP_OK || unit != ADC_UNIT_1) {
        ESP_LOGE(TAG, "GPIO %d is not on ADC1", gpio);
        return false;
    }
    adc_oneshot_chan_cfg_t cfg = {};
    cfg.atten = atten;
    cfg.bitwidth = ADC_BITWIDTH_DEFAULT;
    if (adc_oneshot_config_channel(adc, c.ch, &cfg) != ESP_OK) return false;
    c.atten = atten;
    adc_cali_curve_fitting_config_t cc = {};
    cc.unit_id = ADC_UNIT_1;
    cc.chan = c.ch;
    cc.atten = atten;
    cc.bitwidth = ADC_BITWIDTH_DEFAULT;
    // Without calibration the reading is a straight line through the range, which is still good enough
    // to tell 5 from 12 from 24 V. Said, so a board that has lost its calibration is not a mystery.
    if (adc_cali_create_scheme_curve_fitting(&cc, &c.cali) != ESP_OK) {
        ESP_LOGW(TAG, "no ADC calibration for GPIO %d; reading it uncalibrated", gpio);
        c.cali = nullptr;
    }
    c.ok = true;
    return true;
}

// Millivolts at the pin, averaged over a few readings; -1 when it cannot be read.
int read_mv(const Chan &c, int times = 4) {
    if (!c.ok) return -1;
    int sum = 0, got = 0;
    for (int i = 0; i < times; i++) {
        int raw = 0;
        if (adc_oneshot_read(adc, c.ch, &raw) != ESP_OK) continue;
        int mv = 0;
        if (c.cali) {
            if (adc_cali_raw_to_voltage(c.cali, raw, &mv) != ESP_OK) continue;
        } else {
            mv = raw * (c.atten == ADC_ATTEN_DB_12 ? 3100 : 1750) / 4095;
        }
        // Pinned at the top of the range is "more than this can read", which for the supply is past
        // every window and must not average down into one.
        if (raw >= 4095) return 1 << 20;
        sum += mv;
        got++;
    }
    return got ? sum / got : -1;
}

void measure_supply() {
    const int mv = read_mv(vsense, 8);
    volts = mv < 0 ? 0 : supply_volts(mv);
}

void measure_heat() {
    const int mv = read_mv(ntc);
    celsius = mv < 0 ? NAN : ntc_celsius(mv, board::NTC_RAIL_MV);
}

void switch_run(int i, bool on, uint32_t now) {
    RunState &r = runs[i];
    if (r.on == on) return;
    r.on = on;
    r.up = false;
    r.on_at = now;
    gpio_set_level((gpio_num_t)board::RUNS[i].en, on ? 1 : 0);
    if (on && r.kept == NONE) {
        // THE FIRST LIGHTING FIXES WHAT THIS RUN EXPECTS (guard.h, may_light).
        r.kept = supply;
        char k[16];
        key(k, i, "cls");
        nvs_set_u8(nv, k, r.kept);
        nvs_commit(nv);
        ESP_LOGI(TAG, "run %d is first lit on a %u V supply; it will expect one from now on", i + 1, r.kept);
    }
    ESP_LOGI(TAG, "run %d %s", i + 1, on ? "on" : "off");
}

// Once the supply has read the same kind three times running with both runs off, each run's case is
// decided. Out of range keeps them all waiting, and it is asked again a tenth of a second later, so a
// supply that comes up slowly is not a strip that never lights.
void decide(uint32_t now) {
    const uint8_t c = classify(volts);
    if (c != seen) { seen = c; seen_times = 0; }
    if (++seen_times < 3) return;
    if (c == NONE) {
        for (auto &r : runs) r.held = RANGE;
        return;
    }
    supply = c;
    decided = true;
    for (int i = 0; i < board::OUTPUTS; i++) {
        RunState &r = runs[i];
        r.held = may_light(supply, r.kept);
        if (r.held == SUPPLY)
            ESP_LOGE(TAG, "run %d was set up on a %u V supply and this one is %u V (%.1f V). It stays dark.",
                     i + 1, r.kept, supply, volts);
    }
    ESP_LOGI(TAG, "supply %.1f V, a %u V supply", volts, supply);
    (void)now;
}

}  // namespace

void begin(uint32_t nvs) {
    nv = (nvs_handle_t)nvs;
    // OFF FIRST. The board's pull-downs already hold both runs dark through reset; this makes it the
    // firmware's word as well before anything else is asked of the pins.
    for (int i = 0; i < board::OUTPUTS; i++) {
        const board::Run &p = board::RUNS[i];
        gpio_set_level((gpio_num_t)p.en, 0);
        gpio_config_t out = {};
        out.pin_bit_mask = 1ULL << p.en;
        out.mode = GPIO_MODE_OUTPUT;
        gpio_config(&out);
        gpio_set_level((gpio_num_t)p.en, 0);
        // Both fault lines are open drain with 10k pull-ups on the board.
        gpio_config_t in = {};
        in.pin_bit_mask = (1ULL << p.flt) | (1ULL << p.dflt);
        in.mode = GPIO_MODE_INPUT;
        gpio_config(&in);
        char k[16];
        key(k, i, "cls");
        uint8_t kept = NONE;
        nvs_get_u8(nv, k, &kept);
        runs[i].kept = kept;
    }

    adc_oneshot_unit_init_cfg_t unit = {};
    unit.unit_id = ADC_UNIT_1;
    if (adc_oneshot_new_unit(&unit, &adc) != ESP_OK) {
        ESP_LOGE(TAG, "no ADC -- the runs stay dark, because nothing here can say they are safe");
        return;
    }
    open_chan(vsense, board::VSENSE, ADC_ATTEN_DB_6);
    open_chan(ntc, board::NTC, ADC_ATTEN_DB_12);
    for (int i = 0; i < board::OUTPUTS; i++) open_chan(imon[i], board::RUNS[i].imon, ADC_ATTEN_DB_6);

    // Measured here, at boot, so that in the ordinary case the runs are up before anything is drawn.
    for (int i = 0; i < 6 && !decided; i++) {
        measure_supply();
        decide(now_ms());
        if (!decided) vTaskDelay(pdMS_TO_TICKS(20));
    }
    measure_heat();
    if (!decided) ESP_LOGW(TAG, "supply %.1f V is not one a strip is made for; both runs stay dark", volts);
    const uint32_t now = now_ms();
    for (int i = 0; i < board::OUTPUTS; i++)
        if (decided && runs[i].held == FREE) switch_run(i, true, now);
    vTaskDelay(pdMS_TO_TICKS(COME_UP_MS));
    for (auto &r : runs) r.up = r.on;
}

bool live(int i) { return i >= 0 && i < board::OUTPUTS && runs[i].on && runs[i].up; }

uint16_t scale(int i, const px::Pixels &p) {
    if (i < 0 || i >= board::OUTPUTS) return 256;
    RunState &r = runs[i];
    r.picture_load = px::load(p, px::wire(i));
    r.lights = p.count;
    const uint16_t s = r.lim.scale(r.picture_load, r.lights, most_amps(celsius));
    r.sent_scale = s;
    r.sent_load = (uint32_t)((uint64_t)r.picture_load * s / 256);
    r.sent_at = now_ms();
    return s;
}

bool tick(uint32_t now) {
    if (!adc) return false;
    bool again = false;

    // The fault lines, every pass: they are only pins.
    for (int i = 0; i < board::OUTPUTS; i++) {
        RunState &r = runs[i];
        const bool flt = !gpio_get_level((gpio_num_t)board::RUNS[i].flt);
        const bool dflt = !gpio_get_level((gpio_num_t)board::RUNS[i].dflt);
        const uint8_t why = r.faults.see(flt, dflt, r.on, now);
        if (r.faults.sw.on && r.faults.sw.since == now)
            ESP_LOGW(TAG, "run %d: its switch cut it (trip %u)", i + 1, r.faults.sw.times);
        if (r.faults.wires.on && r.faults.wires.since == now)
            ESP_LOGW(TAG, "run %d: more than 6 V on its data or clock line", i + 1);
        if (why != FREE && r.held != why && (r.held == FREE || r.held == RANGE)) {
            r.held = why;
            ESP_LOGE(TAG, "run %d held off until it is next powered on: %s", i + 1, held_word(why));
        }
    }

    // The supply ten times a second, the board's temperature once a second.
    if (now - measured_at >= 100) {
        measured_at = now;
        measure_supply();
        if (!decided) decide(now);
        else if (!over && volts > OVER_V) { over = true; ESP_LOGE(TAG, "supply %.1f V: both runs off", volts); }
        else if (over && volts < BACK_V) { over = false; ESP_LOGI(TAG, "supply back to %.1f V", volts); }
    }
    if (now - warmed_at >= 1000) { warmed_at = now; measure_heat(); }

    for (int i = 0; i < board::OUTPUTS; i++) {
        RunState &r = runs[i];
        if (decided && (r.held == FREE || r.held == RANGE)) r.held = over ? RANGE : FREE;
        switch_run(i, decided && r.held == FREE, now);
        if (r.on && !r.up && now - r.on_at >= COME_UP_MS) { r.up = true; again = true; }

        // The monitor, every pass while lit. A run that is off reads nothing and teaches nothing.
        if (!r.on) { r.amps = 0; continue; }
        const int mv = read_mv(imon[i]);
        if (mv < 0) continue;
        r.amps = imon_amps(mv);
        if (r.up && now - r.sent_at >= SETTLED_MS) r.lim.heard(r.amps, r.sent_load, r.lights);
        // What is showing would now be sent dimmer -- it is drawing more than was predicted, or the
        // board has warmed -- or could now be sent clearly brighter. Either way it is a different
        // frame, so it is written; and only then, because a WS2812 latches (AGENTS.md).
        if (r.up) {
            const uint16_t s = r.lim.scale(r.picture_load, r.lights, most_amps(celsius));
            if ((s < r.sent_scale || s >= r.sent_scale + BRIGHTER_BY) && now - resent_at >= RESEND_EVERY_MS) {
                resent_at = now;
                again = true;
            }
        }
    }
    return again;
}

bool report(char *out, size_t n, uint32_t now, bool force) {
    if (!adc && !force) return false;
    // The SHAPE is everything a person would want to hear about at once; the numbers drift and are
    // said every SAY_EVERY_MS.
    uint32_t shape = supply | (decided ? 0x100 : 0) | (over ? 0x200 : 0);
    for (int i = 0; i < board::OUTPUTS; i++) {
        const RunState &r = runs[i];
        shape = shape * 31 + (r.on ? 1 : 0) + (r.held << 1) + (r.faults.sw.on ? 64 : 0) + (r.faults.wires.on ? 128 : 0)
                + ((uint32_t)r.faults.sw.times << 8) + ((uint32_t)r.kept << 20);
    }
    if (!force && said_once && shape == said_shape && now - said_at < SAY_EVERY_MS) return false;
    said_once = true;
    said_shape = shape;
    said_at = now;

    int at = 0;
    auto put = [&](const char *fmt, auto... v) {
        if (at >= 0 && (size_t)at < n) at += snprintf(out + at, n - at, fmt, v...);
    };
    put("{\"board\":\"%s\",\"v\":%.1f,\"class\":%u,", board::NAME, volts, decided ? supply : 0);
    if (celsius == celsius) put("\"board_c\":%.0f,", celsius);
    else put("\"board_c\":null,");
    put("\"runs\":[");
    for (int i = 0; i < board::OUTPUTS; i++) {
        const RunState &r = runs[i];
        const uint8_t held = r.held == FREE && over ? (uint8_t)RANGE : r.held;
        put("%s{\"on\":%s,\"class\":%u,\"a\":%.2f,\"most\":%.2f,\"dim\":%u,\"switch\":%s,\"wiring\":%s,"
            "\"trips\":%u,\"held\":\"%s\"}",
            i ? "," : "", r.on ? "true" : "false", r.kept, r.amps, most_amps(celsius),
            (unsigned)(r.on ? (r.sent_scale * 100 + 128) / 256 : 100), r.faults.sw.on ? "true" : "false",
            r.faults.wires.on ? "true" : "false", r.faults.sw.times, held_word(held));
    }
    put("]}");
    return at > 0 && (size_t)at < n;
}

}  // namespace guard

#else  // the devkit: nothing switched, nothing measured, and nothing changed from before

namespace guard {
void begin(uint32_t) {}
bool live(int) { return true; }
uint16_t scale(int, const px::Pixels &) { return 256; }
bool tick(uint32_t) { return false; }
bool report(char *, size_t, uint32_t, bool) { return false; }
}  // namespace guard

#endif
