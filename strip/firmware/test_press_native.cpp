// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// main/press.h on the Mac: the one button, read the way a sealed box outdoors needs it read.
//
//     c++ -std=c++17 -O1 -o /tmp/press test_press_native.cpp && /tmp/press
//
// (The -isysroot note in test_hub_uri_native.cpp applies here too.)
//
// This exists because the failure it guards against is a strip that forgets its house every time it
// boots -- a button held by ice, or by a seal that shrank on a cold night, and a hold that counts
// before anybody let go. Nothing on a bench shows that, because on a bench nobody is pressing it.
#include "main/press.h"

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

// Holds the button from `from` to `to`, read every 10 ms like the housekeeping loop, and returns every
// event seen, or'd together.
static uint8_t hold(Press &p, uint32_t from, uint32_t to) {
    uint8_t all = 0;
    for (uint32_t t = from; t < to; t += 10) all |= p.tick(false, t);
    return all;
}

static void held_at_boot_is_ignored() {
    printf("a button held at boot does nothing, however long it is held\n");
    Press p;
    const uint8_t ev = hold(p, 0, 60000);           // a minute of ice
    CHECK(ev == 0, "a button never let go must not count at all, saw %02x", ev);
    CHECK(!(p.tick(true, 60000) & Press::PRESSED), "and letting go of it is not a press");
}

static void a_press_counts_on_release() {
    printf("a short press counts on the way up, not the way down\n");
    Press p;
    p.tick(true, 0);
    const uint8_t down = hold(p, 10, 200);
    CHECK(down == Press::DOWN, "going down says only that it went down, saw %02x", down);
    CHECK(p.tick(true, 200) & Press::PRESSED, "a 190 ms press counts when it is let go");
}

static void a_hold_arms_then_forgets_and_a_short_one_does_not() {
    printf("past a second it arms; past five it forgets; let go in between and nothing happens\n");
    Press p;
    p.tick(true, 0);
    uint8_t ev = hold(p, 10, 2000);
    CHECK(ev & Press::ARMED, "a two-second hold arms");
    CHECK(!(ev & Press::DONE), "but does not forget");
    ev = p.tick(true, 2000);
    CHECK((ev & Press::LET_GO) && !(ev & Press::PRESSED), "letting go of an armed hold is not a press");

    Press q;
    q.tick(true, 0);
    ev = hold(q, 10, 5200);
    CHECK(ev & Press::DONE, "five seconds forgets the house");
}

static void ice_cannot_loop_a_reset() {
    printf("a button stuck down forgets once, and the board that comes back ignores it\n");
    Press before;
    before.tick(true, 0);
    CHECK(hold(before, 10, 6000) & Press::DONE, "a button that sticks after being let go forgets the house once");
    Press after;                                      // the restart, with the button still stuck
    CHECK(hold(after, 0, 600000) == 0, "the board that comes back must not forget again");
}

static void a_bounce_is_not_a_press_on_rev_a() {
    printf("a contact bouncing is not a press where a shortest press is set, and is where it is not\n");
    Press reva;
    reva.shortest = 30;
    reva.tick(true, 0);
    reva.tick(false, 10);
    CHECK(!(reva.tick(true, 20) & Press::PRESSED), "a 10 ms blip on rev A is a bounce");
    reva.tick(false, 100);
    hold(reva, 110, 160);
    CHECK(reva.tick(true, 160) & Press::PRESSED, "60 ms is a finger");

    Press devkit;                                     // shortest 0: exactly the old loop
    devkit.tick(true, 0);
    devkit.tick(false, 10);
    CHECK(devkit.tick(true, 20) & Press::PRESSED, "the devkit counts what the loop sees, as it always did");
}

int main() {
    held_at_boot_is_ignored();
    a_press_counts_on_release();
    a_hold_arms_then_forgets_and_a_short_one_does_not();
    ice_cannot_loop_a_reset();
    a_bounce_is_not_a_press_on_rev_a();
    printf(failures ? "\n%d failed\n" : "\npress: all good\n", failures);
    return failures ? 1 : 0;
}
