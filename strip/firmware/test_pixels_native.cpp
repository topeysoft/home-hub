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
#include "main/pixels.h"

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

// ---- signals (design/signal/) ----

// Where the brightest lit pixel is, in strip order, reading the red channel through the mapping.
static int brightest(const px::Pixels &p) {
    int best = -1, most = 0;
    const int n = p.order.per_pixel();
    for (int i = 0; i < p.count; i++) {
        const int v = p.buf[i * n + p.order.at[0]];
        if (v > most) { most = v; best = i; }
    }
    return best;
}

static px::Signal way(int8_t dir) {
    px::Signal s; s.kind = px::Signal::WAY; s.dir = dir; s.r = 255; s.g = 138; s.b = 0; s.ms = 2000; s.times = 3;
    s.start(1000);
    return s;
}

static void a_run_goes_the_way_it_was_asked() {
    printf("a run goes the way it was asked, and the two ways mirror\n");
    px::Pixels p; p.set_count(60);
    // Away from the plug end: the head moves up the strip as time passes.
    px::Signal s = way(1);
    s.draw(p, 1000 + 500); const int a = brightest(p);
    s.draw(p, 1000 + 1000); const int b = brightest(p);
    CHECK(a >= 0 && b > a, "a run away from the plug should climb, went %d then %d", a, b);
    // Toward it: the same moments, mirrored.
    px::Signal t = way(-1);
    t.draw(p, 1000 + 500); const int c = brightest(p);
    t.draw(p, 1000 + 1000); const int d = brightest(p);
    CHECK(c >= 0 && d < c, "a run toward the plug should fall, went %d then %d", c, d);
    CHECK(a + c == 59, "the two directions should mirror each other: %d and %d", a, c);
}

static void a_run_ends_and_says_so() {
    printf("a signal is over when its passes are, and a steady end is not\n");
    px::Signal s = way(1);
    CHECK(!s.over(1000 + 5999), "three passes of two seconds are not over at 5.999 s");
    CHECK(s.over(1000 + 6000), "and are over at 6 s");
    px::Signal e; e.kind = px::Signal::END; e.ms = 0; e.start(0);
    CHECK(!e.over(0xFFFFFF), "a steady end lasts until something else is shown");
}

static void a_frame_is_written_only_when_it_changes() {
    printf("a frame is written only when the picture changes\n");
    // The WS2812 rule: count how many distinct frames a breath asks for over one second at 100 Hz.
    // It must be far fewer than 100 -- and more than a handful, or it is not a breath.
    px::Signal s; s.kind = px::Signal::CALL; s.r = 255; s.ms = 1600; s.times = 1; s.start(0);
    uint32_t was = 0; int writes = 0;
    for (uint32_t t = 0; t < 1600; t += 10) { const uint32_t k = s.step(t, 60); if (k != was) { writes++; was = k; } }
    CHECK(writes > 20 && writes < 140, "a breath should ask for a few dozen frames, asked for %d", writes);
    // And a steady end asks for exactly one.
    px::Signal e; e.kind = px::Signal::END; e.ms = 0; e.start(0);
    was = 0; writes = 0;
    for (uint32_t t = 0; t < 5000; t += 10) { const uint32_t k = e.step(t, 60); if (k != was) { writes++; was = k; } }
    CHECK(writes == 1, "a steady end should be written once, was written %d times", writes);
}

static void the_end_is_the_end_it_was_asked_for() {
    printf("the end that lights is the end that was asked for\n");
    px::Pixels p; p.set_count(40);
    px::Signal e; e.kind = px::Signal::END; e.ms = 0; e.r = 255; e.end = 0; e.start(0);
    e.draw(p, 10);
    CHECK(p.buf[0 * 3 + p.order.at[0]] == 255 && p.buf[39 * 3 + p.order.at[0]] == 0, "end 0 is the plug end");
    e.end = 1; e.draw(p, 10);
    CHECK(p.buf[0 * 3 + p.order.at[0]] == 0 && p.buf[39 * 3 + p.order.at[0]] == 255, "end 1 is the far end");
}

static void a_fill_stops_at_its_level() {
    printf("a fill stops at its level\n");
    px::Pixels p; p.set_count(100);
    px::Signal f; f.kind = px::Signal::FILL; f.g = 208; f.level = 128; f.ms = 3000; f.times = 1; f.start(0);
    f.draw(p, 2200);                                     // risen and holding
    int lit = 0; for (int i = 0; i < 100; i++) if (p.buf[i * 3 + p.order.at[1]]) lit++;
    CHECK(lit == 50, "half a fill on a hundred lights is fifty, got %d", lit);
}

int main() {
    the_mapping_matches_the_brains_convention();
    a_half_applied_ordering_is_never_left_behind();
    raw_goes_out_exactly_as_given();
    three_bytes_into_a_four_byte_part_is_the_stripe();
    the_fill_latches_where_it_was();
    all_six_are_settled_by_what_somebody_can_see();
    a_run_goes_the_way_it_was_asked();
    a_run_ends_and_says_so();
    a_frame_is_written_only_when_it_changes();
    the_end_is_the_end_it_was_asked_for();
    a_fill_stops_at_its_level();
    printf(failures ? "\n%d failed\n" : "\nall good\n", failures);
    return failures ? 1 : 0;
}
