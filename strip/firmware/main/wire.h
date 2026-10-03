// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// One wire or two, found by the board at a run's first power-up instead of asked of anybody.
//
// A strip cannot say which kind it is (pixels.h, "TWO KINDS OF WIRE"), and the question asked of a
// person is worse than none: counting the wires answers Four for a WS2815, which has a backup data
// wire and takes its colors on one (design/controller-panel, page "wire", B). What rev A CAN do is
// watch a strip hear something. A two-wire strip given no clock cannot latch a thing, and a one-wire
// strip cannot make sense of a clocked frame, so the board lights the run faintly one way, reads the
// switch's current monitor, then the other way, and keeps the way that drew current (direction C).
// Where it cannot tell it says so and drives one wire, which is what every strip got before, and the
// household's setup falls back to one more look (direction A).
//
// THE NUMBERS BELOW ARE UNMEASURED. No rev A board exists, and the thresholds have to be found on a
// bench, on one-wire and two-wire strips of a few lengths: the monitor reads about 0.229 V an amp, and
// a faint glow on a short strip is tens of milliamps, which is near what the monitor can tell from
// nothing at all. They are written here as names so that the bench changes one line.
//
// AND A ONE-WIRE STRIP WILL PROBABLY DRAW ON BOTH. The clocked frame goes down its data line too, and
// a WS2812 reads SPI's bytes as bits of its own -- the 0xFF that opens every two-wire light is a long
// high, which it takes as a one -- so a one-wire strip may flash a few lights for an instant and read
// as "both". That comes out unclear, which drives one wire and is right for it; the case this exists
// for is the two-wire strip, which draws on the clocked frame and on nothing else. Whether "one drew"
// alone can be trusted, since a two-wire strip with no clock cannot have heard anything, is the
// bench's question too.
//
// Free of ESP-IDF, so test_wire_native.cpp holds the decision to all five cases. app_main.cpp is the
// half that lights the run and reads the monitor.
#pragma once

#include <stdio.h>
#include <stddef.h>

namespace wire {

enum Found : unsigned char { UNCLEAR = 0, ONE = 1, TWO = 2 };

static inline const char *word(Found f) { return f == ONE ? "one" : f == TWO ? "two" : "unclear"; }

// WHAT THE PROBE SENDS: the setup glow's own amber at a sixteenth, on every light it believes in. The
// glow comes on a moment later anyway, so a probe that shows reads as that glow starting, not as a
// different light. Saturated, not a panel color (AGENTS.md section 4). About 1.7 mA a light on a
// WS2812B at 5 V -- half an amp across 300 lights, tens of milliamps across a short strip.
constexpr unsigned char PROBE_R = 16, PROBE_G = 6, PROBE_B = 0;
constexpr float PROBE_A_PER_LIGHT = 0.0017f;

// How long a probe frame is left showing before the monitor is read: the frame latches as it ends, and
// the strip's own supply takes a moment to settle under the new load. Brief on purpose -- four frames
// of this is the whole probe.
constexpr unsigned SETTLE_MS = 40;

// A RISE THIS LARGE OVER IDLE IS A STRIP THAT HEARD. Unmeasured: chosen as a few counts of the ADC
// (about 2 mA a count at 6 dB) above the monitor's own few percent of error at a dark strip's draw.
constexpr float HEARD_A = 0.030f;
// A rise under this is a strip that did not. Between the two is a reading nobody should act on.
constexpr float QUIET_A = 0.012f;
// A RUN ALREADY DRAWING THIS MUCH DARK CANNOT BE READ for a faint frame: the monitor is good to a few
// percent of what it reads, and 3% of an amp is the whole of HEARD_A. Something else is happening on
// that run, and the answer is unclear rather than a guess.
constexpr float BUSY_A = 1.0f;

// The decision. `idle` is the run dark, `one` after a faint one-wire frame, `two` after a faint
// two-wire frame, all in amps; a negative reading is one that could not be taken. `lights` is how many
// the probe lit: when even all of them hearing could not rise past HEARD_A, there is nothing to read.
static inline Found decide(float idle, float one, float two, int lights)
{
    if (idle < 0 || one < 0 || two < 0) return UNCLEAR;
    if (idle > BUSY_A) return UNCLEAR;
    if (lights < 1 || lights * PROBE_A_PER_LIGHT < HEARD_A) return UNCLEAR;
    const float r1 = one - idle, r2 = two - idle;
    const bool heard1 = r1 >= HEARD_A, heard2 = r2 >= HEARD_A;
    const bool quiet1 = r1 < QUIET_A, quiet2 = r2 < QUIET_A;
    if (heard1 && quiet2) return ONE;
    if (heard2 && quiet1) return TWO;
    return UNCLEAR;     // neither drew, both drew, or one of them is in between
}

// What is said on `wire` (and `run2/wire`), retained: the answer and the three readings it came from,
// so the bench and the wall can see how close a call it was.
static inline int report(char *out, size_t n, Found f, float idle, float one, float two)
{
    return snprintf(out, n, "{\"found\":\"%s\",\"idle\":%.3f,\"one\":%.3f,\"two\":%.3f}", word(f), idle, one, two);
}

}  // namespace wire
