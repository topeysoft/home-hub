// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// src/pixels.h on the Mac, against the arithmetic the brain does at the other end.
//
//     c++ -std=c++17 -O1 -o /tmp/px test_pixels_native.cpp && /tmp/px
//
// This exists because a strip with its red and green swapped LOOKS LIKE IT IS WORKING. Everything
// lights, everything dims, every tile is right, and the only symptom is that the household's idea of
// pink is not the lamp's -- which is indistinguishable from the ordinary variation between makes that
// design/device page 4 exists to tune away. There is no bench test for that and no e2e that catches
// it. So the mapping is checked here, against the convention brain/hub/strip.py writes down, and the
// last case walks all six orderings the way a household would actually answer them.
#include "src/pixels.h"

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

// The six, exactly as brain/hub/strip.py spells them.
static const char *ORDERS[6] = {"rgb", "rbg", "grb", "gbr", "brg", "bgr"};

// What the brain sends for the first question: the bytes that are red IF the strip is `assume`.
// This is brain/hub/strip.py probe() -- 255 on the byte that drives red under the guess.
static void probe(const char *assume, uint8_t out[3]) {
    for (int i = 0; i < 3; i++) out[i] = assume[i] == 'r' ? 255 : 0;
}

// What a household standing in the room actually sees, given what really went down the wire and what
// the strip really is: the loud byte lights whichever channel sits at that position.
static char seen(const char *truth, const uint8_t wire[3]) {
    for (int i = 0; i < 3; i++)
        if (wire[i] == 255) return truth[i];
    return '?';
}

static void the_mapping_matches_the_brains_convention() {
    printf("the mapping matches the brain's convention\n");
    px::Order o;
    // "grb" means byte 0 carries GREEN. The brain's probe("grb") is (0,255,0) -- red in the middle --
    // so red must land at byte 1 here or the two ends disagree about what the word means.
    CHECK(o.set("grb"), "grb should be accepted");
    CHECK(o.at[0] == 1 && o.at[1] == 0 && o.at[2] == 2, "grb put red at %d, want 1", o.at[0]);
    uint8_t b[3];
    o.bytes(255, 0, 0, b);
    uint8_t want[3];
    probe("grb", want);
    CHECK(memcmp(b, want, 3) == 0, "red on a grb strip went out as %d,%d,%d", b[0], b[1], b[2]);

    for (int i = 0; i < 6; i++) {
        px::Order x;
        CHECK(x.set(ORDERS[i]), "%s should be accepted", ORDERS[i]);
        uint8_t got[3], expect[3];
        x.bytes(255, 0, 0, got);
        probe(ORDERS[i], expect);
        CHECK(memcmp(got, expect, 3) == 0, "%s disagrees with the brain about red", ORDERS[i]);
    }
}

static void a_half_applied_ordering_is_never_left_behind() {
    printf("a bad ordering changes nothing\n");
    px::Order o;
    uint8_t before[3];
    memcpy(before, o.at, 3);
    const char *junk[] = {"rr", "rrg", "rgbb", "xyz", "RGB", "", "rg"};
    for (auto s : junk) {
        CHECK(!o.set(s), "\"%s\" should have been refused", s);
        CHECK(memcmp(o.at, before, 3) == 0, "\"%s\" was refused but changed the mapping", s);
    }
}

static void raw_goes_out_exactly_as_given() {
    printf("the order probe is not put through the guess it is testing\n");
    px::Pixels p;
    p.set_count(4);
    CHECK(p.order.set("bgr"), "bgr");
    p.raw3(0, 255, 0);
    // Not remapped by "bgr": what the hub said is what the wire carries.
    CHECK(p.buf[0] == 0 && p.buf[1] == 255 && p.buf[2] == 0, "raw3 was remapped");
    CHECK(p.buf[3] == 0 && p.buf[4] == 255 && p.buf[5] == 0, "raw3 did not repeat");
}

static void three_bytes_into_a_four_byte_part_is_the_stripe() {
    printf("the stripes answer falls out of the wire, not out of a special case\n");
    px::Pixels p;
    p.set_count(4);
    p.order.white = true;          // an SK6812: four bytes a pixel
    p.raw3(255, 0, 0);
    // The controller still strides three, so pixel 0 gets 255,0,0 and its fourth byte is the FIRST
    // byte of the next triple. Every pixel is a different phase of the pattern, which is the
    // candy-stripe a household reports. Pixel 1 therefore does not start at 255.
    CHECK(p.buf[0] == 255 && p.buf[3] == 255, "the pattern should keep striding three");
    CHECK(p.buf[4] != 255, "pixel 1 should be a different phase, not another red");
    CHECK(p.bytes_used() == 16, "four rgbw pixels are 16 bytes, got %zu", p.bytes_used());
}

static void the_fill_latches_where_it_was() {
    printf("the fill latches in the firmware, at the moment it is told\n");
    px::Fill f;
    f.start(0);
    f.tick(f.step * 186, 300);
    CHECK(f.at == 186, "fill reached %d, want 186", f.at);
    CHECK(f.stop() == 186, "stop did not latch where it was");
    CHECK(!f.running, "stop should end it");

    // A loop that stalls must not fall behind: the fill is a clock, not a counter of loop passes.
    px::Fill g;
    g.start(0);
    g.tick(g.step * 40, 300);
    g.tick(g.step * 41, 300);
    CHECK(g.at == 41, "a stalled loop lost lights: at %d", g.at);

    // And it wraps, because missing it has to cost nothing but another pass.
    px::Fill h;
    h.start(0);
    h.tick(h.step * 12, 10);
    CHECK(h.at <= 10, "the fill ran past the end and stayed there: %d", h.at);
}

static void all_six_are_settled_by_what_somebody_can_see() {
    printf("all six orderings come back from two honest answers\n");
    for (int i = 0; i < 6; i++) {
        const char *truth = ORDERS[i];

        // Question one: the hub sends what red would be on the strip it is guessing.
        uint8_t wire[3];
        probe("grb", wire);
        px::Pixels p;
        p.set_count(8);
        CHECK(p.order.set(truth), "%s", truth);
        p.raw3(wire[0], wire[1], wire[2]);
        char first = seen(truth, &p.buf[0]);

        // Question two, reached only when the first answer was not red: red on the FIRST byte.
        uint8_t wire2[3] = {255, 0, 0};
        p.raw3(wire2[0], wire2[1], wire2[2]);
        char second = seen(truth, &p.buf[0]);

        // The hub's rule: whichever channel came back names the one that byte drives.
        const char *got = nullptr;
        for (int k = 0; k < 6; k++) {
            const char *cand = ORDERS[k];
            if (cand[1] != first) continue;          // the probe made byte 1 loud
            if (first == 'r' && strcmp(cand, "grb") == 0) { got = cand; break; }   // the prior
            if (first != 'r' && cand[0] == second) { got = cand; break; }
        }
        // "brg" is the one case the single tap gets wrong on purpose: it answers red like a grb
        // strip does, and the pane has a row that asks again. Everything else must come back exactly.
        if (strcmp(truth, "brg") == 0) {
            CHECK(got && strcmp(got, "grb") == 0, "brg should fall to the prior, got %s", got ? got : "none");
        } else {
            CHECK(got && strcmp(got, truth) == 0, "%s came back as %s", truth, got ? got : "none");
        }
    }
}

int main() {
    the_mapping_matches_the_brains_convention();
    a_half_applied_ordering_is_never_left_behind();
    raw_goes_out_exactly_as_given();
    three_bytes_into_a_four_byte_part_is_the_stripe();
    the_fill_latches_where_it_was();
    all_six_are_settled_by_what_somebody_can_see();
    printf(failures ? "\n%d failed\n" : "\nall good\n", failures);
    return failures ? 1 : 0;
}
