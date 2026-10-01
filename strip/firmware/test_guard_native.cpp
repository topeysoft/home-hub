// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// main/guard.h on the Mac: what keeps a rev A board from lighting a strip on the wrong supply, or
// drawing more than a run may carry.
//
//     c++ -std=c++17 -O1 -DSTRIP_BOARD_REVA -o /tmp/guard test_guard_native.cpp && /tmp/guard
//
// (The -isysroot note in test_hub_uri_native.cpp applies here too.)
//
// This exists because no rev A board exists yet, and every number below is one a board will act on
// with nobody watching: a 12 V strip on a 24 V supply is a strip on fire, and a limiter that predicts
// low is a run that trips and flashes off in somebody's living room. The arithmetic is checked here
// against the parts' own numbers (home-hub-hardware, strip/parts.md) so the first board is testing the
// hardware, not this.
#include "main/guard.h"

#include <stdio.h>

static int failures = 0;

#define CHECK(cond, ...)                                    \
    do {                                                    \
        if (!(cond)) {                                      \
            printf("  FAIL: ");                             \
            printf(__VA_ARGS__);                            \
            printf("   (%s:%d)\n", __FILE__, __LINE__);     \
            failures++;                                     \
        }                                                   \
    } while (0)

static bool near(float a, float b, float within) { return a > b - within && a < b + within; }

static void the_three_kinds_of_supply_and_nothing_between() {
    printf("5, 12 and 24 V are told apart, and what is between them is out of range\n");
    struct { float v; uint8_t want; } cases[] = {
        {4.2f, guard::NONE},   // below the switches' own floor
        {4.5f, guard::V5}, {5.0f, guard::V5}, {5.3f, guard::V5},
        {10.8f, guard::V12}, {12.0f, guard::V12}, {13.2f, guard::V12},   // 12 V, +/-10%
        {9.0f, guard::NONE}, {9.5f, guard::NONE},     // a 9 V adapter, a little high: between kinds
        {7.5f, guard::NONE}, {16.5f, guard::NONE},
        {19.5f, guard::NONE},                         // a laptop brick: between kinds, not a weak 24 V
        {21.6f, guard::V24}, {24.0f, guard::V24}, {28.8f, guard::V24},   // a 24 V supply trimmed up
        {30.5f, guard::NONE}, {36.0f, guard::NONE},   // past the board's own cutoff; a roofline adapter
        {0.0f, guard::NONE},
    };
    for (auto &c : cases)
        CHECK(guard::classify(c.v) == c.want, "%.1f V classed %u, want %u", c.v, guard::classify(c.v), c.want);
}

static void the_divider_reads_the_supply() {
    printf("the divider's millivolts are the supply's volts\n");
    // 200k over 10k: 24 V is 1.143 V at the pin, as parts.md says.
    CHECK(near(guard::supply_volts(1143), 24.0f, 0.05f), "1143 mV is %.2f V, want 24", guard::supply_volts(1143));
    CHECK(near(guard::supply_volts(238), 5.0f, 0.05f), "238 mV is %.2f V, want 5", guard::supply_volts(238));
    // The ADC pinned at the top of its range must not fall into a window.
    CHECK(guard::classify(guard::supply_volts(1 << 20)) == guard::NONE, "a pinned reading must be out of range");
}

static void a_run_is_lit_only_on_the_supply_it_was_first_lit_on() {
    printf("a run that was set up on one supply stays dark on another\n");
    using namespace guard;
    CHECK(may_light(V12, NONE) == FREE, "a run never lit lights on a 12 V supply (the first time)");
    CHECK(may_light(V12, V12) == FREE, "a 12 V run on a 12 V supply lights");
    CHECK(may_light(V24, V12) == SUPPLY, "a 12 V run on a 24 V supply must never light");
    CHECK(may_light(V5, V24) == SUPPLY, "a 24 V run on a 5 V supply is held too: it is not what it was set up on");
    CHECK(may_light(NONE, V12) == RANGE, "an out-of-range supply lights nothing");
    CHECK(may_light(NONE, NONE) == RANGE, "an out-of-range supply lights nothing, even the first time");
}

static void the_current_monitor_reads_amps() {
    printf("the current monitor's millivolts are amps\n");
    // 27.9 uA/A into 8.2k is 0.229 V/A; the switch's limit is 5.45 A nominal, 1.247 V.
    CHECK(near(guard::imon_amps(229), 1.0f, 0.01f), "229 mV is %.3f A, want 1", guard::imon_amps(229));
    CHECK(near(guard::imon_amps(1247), 5.45f, 0.02f), "1247 mV is %.3f A, want 5.45", guard::imon_amps(1247));
}

static void the_thermistor_reads_degrees() {
    printf("the thermistor reads the board's temperature, and an open or shorted one says so\n");
    const float rail = board::NTC_RAIL_MV;
    // At 25 C the NTC is 10k against the 10k pull-up: half the rail.
    CHECK(near(guard::ntc_celsius((int)(rail / 2), rail), 25.0f, 0.5f), "half the rail is %.1f C, want 25",
          guard::ntc_celsius((int)(rail / 2), rail));
    // 85 C: R = 10k * exp(3435 * (1/358.15 - 1/298.15)) = 1.45k.
    const float r85 = 1450.0f, mv85 = rail * r85 / (10000.0f + r85);
    CHECK(near(guard::ntc_celsius((int)mv85, rail), 85.0f, 1.0f), "%.0f mV is %.1f C, want 85", mv85,
          guard::ntc_celsius((int)mv85, rail));
    // Colder is a higher voltage.
    CHECK(guard::ntc_celsius(2900, rail) < 0.0f, "2900 mV should be below freezing, got %.1f",
          guard::ntc_celsius(2900, rail));
    const float open = guard::ntc_celsius((int)rail, rail), shorted = guard::ntc_celsius(0, rail);
    CHECK(open != open && shorted != shorted, "an open or shorted thermistor reads as unknown");
}

static void a_hot_board_dims_and_never_goes_dark() {
    printf("a run may draw 4.75 A to 85 C, less above it, and never nothing\n");
    CHECK(guard::most_amps(25.0f) == guard::MOST_A, "a cool board: %.2f A", guard::most_amps(25.0f));
    CHECK(guard::most_amps(85.0f) == guard::MOST_A, "at 85 C the switch is still in its rating");
    CHECK(guard::MOST_A < 5.07f * 0.95f, "4.75 A must sit under the switch's lowest trip, 5.07 A, with a margin");
    const float a95 = guard::most_amps(95.0f), a105 = guard::most_amps(105.0f);
    CHECK(a95 < guard::MOST_A && a105 < a95, "it falls as the board warms: %.2f then %.2f", a95, a105);
    CHECK(guard::most_amps(150.0f) == guard::HOT_MOST_A && guard::HOT_MOST_A > 0, "it never goes to nothing");
    CHECK(guard::most_amps(NAN) == guard::most_amps(85.0f), "an unreadable thermistor counts as 85 C");
}

static void the_limiter_dims_a_bright_picture_before_it_is_sent() {
    printf("a picture that would trip is sent dimmed, and one that would not is sent as drawn\n");
    guard::Limiter l;
    // 300 WS2812B at full white: 900 channels, 18 A by the cautious guess.
    const uint32_t white300 = 300u * 3 * 255;
    const uint16_t s = l.scale(white300, 300, guard::MOST_A);
    const float predicted = l.idle_for(300) + l.per_unit * (white300 / 255.0f) * s / 256.0f;
    CHECK(s < 256, "full white on 300 lights must be dimmed");
    CHECK(predicted <= guard::MOST_A + 0.01f, "dimmed, it is predicted at %.2f A, over %.2f", predicted, guard::MOST_A);
    // A warm glow at a fifth is nowhere near.
    CHECK(l.scale(300u * (51 + 36 + 22), 300, guard::MOST_A) == 256, "a dim glow must go out as drawn");
    CHECK(l.scale(0, 300, guard::MOST_A) == 256, "black is black");
}

static void the_limiter_learns_a_hungrier_strip_at_once() {
    printf("a strip that draws more than guessed is believed at once, one that draws less slowly\n");
    guard::Limiter l;
    l.heard(0.3f, 0, 300);                         // black: the chips alone
    CHECK(near(l.idle, 0.3f, 0.001f), "idle learned as %.3f", l.idle);
    const uint32_t sent = 300u * 3 * 64;           // a quarter-bright white
    // It drew 30 mA a channel at full: half again the guess.
    const float units = sent / 255.0f, amps = 0.3f + 0.030f * units;
    l.heard(amps, sent, 300);
    CHECK(near(l.per_unit, 0.030f, 0.0005f), "learned %.4f A a channel, want 0.030 at once", l.per_unit);
    // Then a reading that says 10 mA: it comes down, but only a little at a time.
    l.heard(0.3f + 0.010f * units, sent, 300);
    CHECK(l.per_unit < 0.030f && l.per_unit > 0.025f, "came down to %.4f; it should move a tenth of the way",
          l.per_unit);
    // And with what it learned, full white is now dimmed harder than before.
    guard::Limiter fresh;
    CHECK(l.scale(300u * 3 * 255, 300, guard::MOST_A) < fresh.scale(300u * 3 * 255, 300, guard::MOST_A),
          "a hungrier strip must be sent dimmer");
}

static void the_limiter_ignores_what_it_cannot_learn_from() {
    printf("a reading from almost no light teaches nothing\n");
    guard::Limiter l;
    const float before = l.per_unit;
    l.heard(0.05f, 3 * 255, 300);                  // three channels lit: inside the monitor's noise
    CHECK(l.per_unit == before, "learned %.4f from three channels", l.per_unit);
}

static void a_run_that_keeps_tripping_is_held() {
    printf("five trips in a minute hold a run off; four do not; a long one does\n");
    guard::Faults f;
    uint32_t t = 1000;
    uint8_t why = guard::FREE;
    for (int i = 0; i < 4; i++) {
        why = f.see(true, false, true, t); t += 100;
        CHECK(why == guard::FREE, "trip %d alone should not hold the run", i + 1);
        f.see(false, false, true, t); t += 650;
    }
    why = f.see(true, false, true, t);
    CHECK(why == guard::TRIPS, "the fifth trip inside a minute holds the run");

    guard::Faults slow;
    t = 0;
    for (int i = 0; i < 8; i++) {
        why = slow.see(true, false, true, t); t += 100;
        slow.see(false, false, true, t); t += 20000;  // one every twenty seconds
    }
    CHECK(why == guard::FREE, "trips spread over minutes are the switch coping, not a fault to hold");

    guard::Faults stuck;
    stuck.see(true, false, true, 0);
    CHECK(stuck.see(true, false, true, 4999) == guard::FREE, "not yet");
    CHECK(stuck.see(true, false, true, 5000) == guard::TRIPS, "a trip that lasts five seconds holds the run");

    guard::Faults off;
    CHECK(off.see(true, false, false, 0) == guard::FREE && !off.sw.on, "a switch that is off has nothing to say");
}

static void a_miswired_data_line_is_held_and_a_glitch_is_not() {
    printf("a data line over 6 V for 100 ms holds the run; a 2 ms blip does not\n");
    guard::Faults f;
    f.see(false, true, true, 0);
    CHECK(f.see(false, false, true, 2) == guard::FREE, "a blip that clears in 2 ms is not a miswire");
    CHECK(f.wires.times == 1, "but it is counted");
    f.see(false, true, true, 10);
    CHECK(f.see(false, true, true, 109) == guard::FREE, "not yet");
    CHECK(f.see(false, true, true, 110) == guard::WIRING, "held after 100 ms");
    CHECK(strcmp(guard::held_word(guard::WIRING), "wiring") == 0, "and said as wiring");
    CHECK(strcmp(guard::held_word(guard::WIRING), guard::held_word(guard::TRIPS)) != 0,
          "a switch fault and a wiring fault are different words");
}

int main() {
    the_three_kinds_of_supply_and_nothing_between();
    the_divider_reads_the_supply();
    a_run_is_lit_only_on_the_supply_it_was_first_lit_on();
    the_current_monitor_reads_amps();
    the_thermistor_reads_degrees();
    a_hot_board_dims_and_never_goes_dark();
    the_limiter_dims_a_bright_picture_before_it_is_sent();
    the_limiter_learns_a_hungrier_strip_at_once();
    the_limiter_ignores_what_it_cannot_learn_from();
    a_run_that_keeps_tripping_is_held();
    a_miswired_data_line_is_held_and_a_glitch_is_not();
    printf(failures ? "\n%d failed\n" : "\nguard: all good\n", failures);
    return failures ? 1 : 0;
}
