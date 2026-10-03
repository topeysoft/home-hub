// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// main/wire.h on the Mac: one wire or two, decided from what the run drew.
//
//     c++ -std=c++17 -O1 -o /tmp/wire test_wire_native.cpp && /tmp/wire
//
// (The -isysroot note in test_hub_uri_native.cpp applies here too.)
//
// This exists because the answer is acted on with nobody watching, at a strip's first power-up, and
// a wrong one is a strip that stays dark until somebody works out why. Unclear is always allowed --
// setup asks once more -- but ONE for a two-wire strip, or TWO for a one-wire strip, never is. The
// thresholds are unmeasured (wire.h); what is held here is the shape of the decision around them.
#include "main/wire.h"

#include <stdio.h>
#include <string.h>

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

static const char *w(wire::Found f) { return wire::word(f); }

static void a_clear_one_and_a_clear_two() {
    printf("the strip that drew on one way and not the other is that way\n");
    // 300 lights of WS2812B: a dark strip draws about 0.3 A; the faint frame adds about half an amp.
    wire::Found f = wire::decide(0.30f, 0.80f, 0.30f, 300);
    CHECK(f == wire::ONE, "drew on one wire only: %s, want one", w(f));
    // An APA102 hears nothing without a clock, and the faint frame on SPI.
    f = wire::decide(0.30f, 0.302f, 0.78f, 300);
    CHECK(f == wire::TWO, "drew on two wires only: %s, want two", w(f));
    // A short two-wire strip: tens of milliamps is still a clear rise.
    f = wire::decide(0.020f, 0.021f, 0.065f, 300);
    CHECK(f == wire::TWO, "a short strip's 45 mA rise on two wires: %s, want two", w(f));
}

static void neither_or_both_is_unclear() {
    printf("a strip that drew both ways, or neither, is not guessed at\n");
    wire::Found f = wire::decide(0.30f, 0.305f, 0.302f, 300);
    CHECK(f == wire::UNCLEAR, "drew on neither: %s, want unclear", w(f));
    // What a one-wire strip may well do: the clocked frame's bytes read as bits of its own (wire.h).
    f = wire::decide(0.30f, 0.80f, 1.10f, 300);
    CHECK(f == wire::UNCLEAR, "drew on both: %s, want unclear", w(f));
    // A rise between quiet and heard on the other wire is not quiet.
    f = wire::decide(0.30f, 0.30f + wire::QUIET_A + 0.005f, 0.80f, 300);
    CHECK(f == wire::UNCLEAR, "an in-between reading on one wire: %s, want unclear", w(f));
}

static void a_busy_run_or_a_handful_of_lights_cannot_be_read() {
    printf("a run already drawing a lot, a few lights, or an unreadable monitor says unclear\n");
    wire::Found f = wire::decide(1.40f, 1.40f, 1.90f, 300);
    CHECK(f == wire::UNCLEAR, "a run drawing 1.4 A dark: %s, want unclear", w(f));
    f = wire::decide(0.01f, 0.01f, 0.20f, 10);
    CHECK(f == wire::UNCLEAR, "ten lights cannot rise past what the monitor can tell: %s, want unclear", w(f));
    f = wire::decide(-1.0f, 0.2f, 0.8f, 300);
    CHECK(f == wire::UNCLEAR, "an idle that could not be read: %s, want unclear", w(f));
    f = wire::decide(0.3f, 0.3f, -1.0f, 300);
    CHECK(f == wire::UNCLEAR, "two wires that could not be tried: %s, want unclear", w(f));
}

static void what_is_said() {
    printf("the report says the answer and the three readings\n");
    char j[128];
    wire::report(j, sizeof(j), wire::TWO, 0.3f, 0.302f, 0.78f);
    CHECK(!strcmp(j, "{\"found\":\"two\",\"idle\":0.300,\"one\":0.302,\"two\":0.780}"), "got %s", j);
    wire::report(j, sizeof(j), wire::UNCLEAR, 0.3f, 0.8f, 1.1f);
    CHECK(strstr(j, "\"found\":\"unclear\"") != nullptr, "got %s", j);
}

int main() {
    a_clear_one_and_a_clear_two();
    neither_or_both_is_unclear();
    a_busy_run_or_a_handful_of_lights_cannot_be_read();
    what_is_said();
    printf(failures ? "\n%d failed\n" : "\nwire: all good\n", failures);
    return failures ? 1 : 0;
}
