// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// main/look.h on the Mac: the roofline's looks, held to design/roofline/OwnsA.dc.html's keyframes.
//
//     c++ -std=c++17 -O1 -o /tmp/look test_look_native.cpp && /tmp/look
//     c++ -std=c++17 -O1 -DSTRIP_BOARD_REVA -o /tmp/look test_look_native.cpp && /tmp/look
//
// (The -isysroot note in test_hub_uri_native.cpp applies here too.)
//
// This exists because the thing a roof of several boxes can get wrong is the SEAM: a chase that
// arrives at the next box's run a light late, or running the wrong way, because that run leaves its
// box against the way round the house. Nobody can see that on a bench with one strip, and every box
// in a house would be drawing it. So two boxes are simulated here, drawing from nothing but the look
// and the time, and the roof they make is checked to be one pattern.
#include "main/look.h"

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

using look::Rgb;

static bool same(const Rgb &a, const Rgb &b) { return a.r == b.r && a.g == b.g && a.b == b.b; }

static const Rgb RED = {255, 45, 36}, GREEN = {20, 216, 96}, ORANGE = {255, 116, 16}, PURPLE = {154, 69, 255};

// What a box makes of the hub's message: the same bytes in, the same look out.
static look::Look christmas()
{
    look::Look l;
    strcpy(l.id, "christmas");
    l.motion = look::CHASE;
    l.colors[0] = RED;
    l.colors[1] = GREEN;
    l.n = 2;
    l.block = 4;
    l.ms = 2800;
    l.t0 = 1790000000000LL;      // an evening in 2026, in hub ms since the epoch
    l.tidy();
    return l;
}

// A box's picture, as rgb, whatever order its strip wants: every test strip here is rgb.
static Rgb pixel(const px::Pixels &p, int i)
{
    const uint8_t *b = &p.buf[i * p.order.per_pixel()];
    return Rgb{b[0], b[1], b[2]};
}

static void the_hash_is_an_integer_and_does_not_move() {
    printf("the hash is the same integer function on every box, and stays the same across releases\n");
    // lowbias32 at a few inputs. If these change, every box in a house that updates draws its embers
    // and twinkles differently from one that has not yet -- a roof of two looks.
    CHECK(look::mix(0) == 0u, "mix(0) = %08x", look::mix(0));
    CHECK(look::mix(1) == 0x688990c0u, "mix(1) = %08x", look::mix(1));
    CHECK(look::mix(300) == 0x3c32979au, "mix(300) = %08x", look::mix(300));
    CHECK(look::hash16(-1) == look::mix(0xffffffffu) >> 16, "a negative position hashes as its bits");
}

static void two_boxes_agree() {
    printf("two boxes given the same look and the same time draw the same light\n");
    const look::Look a = christmas(), b = christmas();
    for (int32_t p = -20; p < 700; p += 7)
        for (int64_t t = a.t0 - 5000; t < a.t0 + 20000; t += 333)
            CHECK(same(look::color_at(a, p, t), look::color_at(b, p, t)), "p %d t %lld", p, (long long)t);
}

static void a_chase_crosses_the_seam() {
    printf("a chase runs from one box's run into the next box's, which leaves its box the other way\n");
    // Box A: one run of 300 from its box, the way round the house: positions 0..299.
    // Box B: a run of 120 that leaves its box AGAINST the way round, so its first light is the far one,
    // at 419, and its last, light 119, sits beside box A's last, at 300.
    look::Look a = christmas(), b = christmas();
    a.runs[0].at = 0;   a.runs[0].dir = 1;  a.runs[0].given = true;
    b.runs[0].at = 419; b.runs[0].dir = -1; b.runs[0].given = true;
    px::Pixels A, B;
    A.order.set("rgb");
    B.order.set("rgb");
    A.set_count(300);
    B.set_count(120);
    const int64_t step = 2800 / 8;      // a chase moves one light every D / (block x colors)
    for (int64_t t = a.t0; t < a.t0 + 6000; t += 125) {
        look::draw(a, 0, t, 255, A);
        look::draw(b, 0, t, 255, B);
        // The roof as one strip, in roof order, from the two boxes' own pictures.
        Rgb roof[420];
        for (int k = 0; k < 300; k++) roof[k] = pixel(A, k);
        for (int k = 0; k < 120; k++) roof[419 - k] = pixel(B, k);
        // Each light is what the whole-roof pattern says it is...
        for (int p = 0; p < 420; p++)
            if (!same(roof[p], look::color_at(a, p, t))) {
                CHECK(false, "roof position %d at t+%lld is not the pattern's", p, (long long)(t - a.t0));
                break;
            }
        // ...and the pattern MOVES ACROSS THE SEAM: what is at 299 now is at 300 one step later.
        CHECK(same(look::color_at(a, 300, t + step), roof[299]), "the seam at t+%lld: 300 should follow 299",
              (long long)(t - a.t0));
        // and so for every neighbor pair along the roof
        for (int p = 0; p < 419; p++)
            if (!same(look::color_at(a, p + 1, t + step), roof[p])) {
                CHECK(false, "position %d does not follow %d one step later", p + 1, p);
                break;
            }
    }
}

static void a_run_against_the_way_runs_toward_its_box() {
    printf("dir -1 reverses: on a run that goes against the way, the chase moves toward its own box\n");
    look::Look l = christmas();
    l.runs[1].at = 9; l.runs[1].dir = -1; l.runs[1].given = true;
    for (int k = 0; k < 10; k++)
        CHECK(look::position(l, 1, k) == 9 - k, "light %d of a reversed run at %d, want %d", k, look::position(l, 1, k), 9 - k);
    px::Pixels P, Q;
    P.order.set("rgb"); Q.order.set("rgb");
    P.set_count(10); Q.set_count(10);
    look::draw(l, 1, l.t0 + 1000, 255, P);
    look::draw(l, 1, l.t0 + 1000 + 350, 255, Q);
    for (int k = 1; k < 10; k++)
        CHECK(same(pixel(Q, k - 1), pixel(P, k)), "light %d one step later should show what light %d did", k - 1, k);
}

static void still_is_in_blocks() {
    printf("still: the colors in blocks, from roof position 0, and on before it too\n");
    look::Look l = christmas();
    l.motion = look::STILL;
    for (int p = 0; p < 4; p++) CHECK(same(look::color_at(l, p, 0), RED), "p %d red", p);
    for (int p = 4; p < 8; p++) CHECK(same(look::color_at(l, p, 0), GREEN), "p %d green", p);
    CHECK(same(look::color_at(l, 8, 0), RED), "p 8 red again");
    for (int p = -4; p < 0; p++) CHECK(same(look::color_at(l, p, 0), GREEN), "p %d is the block before 0: green", p);
    CHECK(same(look::color_at(l, 5, l.t0), look::color_at(l, 5, l.t0 + 98765)), "and still does not move");
    CHECK(!l.moving(), "a still look is painted once");
    // drawn twice at different times, the second draw changes nothing and so sends nothing
    px::Pixels P;
    P.order.set("grb");
    P.set_count(50);
    CHECK(look::draw(l, 0, 0, 200, P), "the first draw is a change");
    CHECK(!look::draw(l, 0, 5000, 200, P), "the same picture again is not");
    const uint8_t *b = &P.buf[0];
    CHECK(b[0] == 45 * 200 / 255 && b[1] == 255 * 200 / 255 && b[2] == 36 * 200 / 255,
          "at the household's brightness, in the strip's own order: %d %d %d", b[0], b[1], b[2]);
}

static void drift_crossfades_through_the_three() {
    printf("drift: c1, c2 at a third, c3 at two thirds, back to c1, crossfaded\n");
    look::Look l = christmas();
    l.motion = look::DRIFT;
    l.colors[2] = PURPLE;
    l.n = 3;
    l.ms = 14000;
    CHECK(same(look::color_at(l, 0, l.t0), RED), "light 0 starts on c1");
    const Rgb third = look::color_at(l, 0, l.t0 + 14000 * 33 / 100);
    CHECK(third.g > 200, "at 33%% it is c2 (green %d)", third.g);
    const Rgb two = look::color_at(l, 0, l.t0 + 14000 * 66 / 100);
    CHECK(two.b > 240 && two.r < 160, "at 66%% it is c3 (%d %d %d)", two.r, two.g, two.b);
    const Rgb half = look::color_at(l, 0, l.t0 + 14000 * 33 / 200);
    CHECK(half.r < 255 && half.r > 20 && half.g > 45 && half.g < 216, "halfway it is between (%d %d %d)", half.r, half.g, half.b);
    // a light 23 along is half the drift's sweep behind
    CHECK(same(look::color_at(l, 23, l.t0 + 7000), look::color_at(l, 0, l.t0)), "light 23 is half a period behind light 0");
}

static void flicker_stays_an_ember() {
    printf("flicker: every light within the fl keyframes' range, unsteady, never dark\n");
    look::Look l = christmas();
    l.motion = look::FLICKER;
    l.colors[0] = ORANGE;
    l.n = 1;
    int lo = 255, hi = 0;
    for (int p = 0; p < 300; p += 3)
        for (int64_t t = l.t0; t < l.t0 + 6000; t += 17) {
            const Rgb c = look::color_at(l, p, t);
            if (c.r < lo) lo = c.r;
            if (c.r > hi) hi = c.r;
        }
    CHECK(lo >= 255 * 45 / 100 - 1, "dimmest %d, the keyframes go no lower than .45 (114)", lo);
    CHECK(hi <= 255, "brightest %d", hi);
    CHECK(lo <= 120 && hi >= 250, "and it really is unsteady: from %d to %d", lo, hi);
    // Two colors, one in three purple: each light keeps the one it was given.
    l.colors[1] = ORANGE; l.colors[2] = PURPLE; l.n = 3;
    int purple = 0;
    for (int p = 0; p < 600; p++) {
        const Rgb a = look::color_at(l, p, l.t0), b = look::color_at(l, p, l.t0 + 777);
        CHECK((a.b > a.r) == (b.b > b.r), "light %d changed ember", p);
        if (a.b > a.r) purple++;
    }
    CHECK(purple > 150 && purple < 250, "about one in three purple: %d of 600", purple);
}

static void twinkle_peaks_then_rests() {
    printf("twinkle: .55 most of the time, brighter and whiter at 7%%, back by 16%%\n");
    look::Look l = christmas();
    l.motion = look::TWINKLE;
    l.colors[0] = RED; l.n = 1;
    l.block = 5;
    l.ms = 2400;
    const int p = 17;
    int at_rest = 0, peak_t = -1;
    Rgb peak = {0, 0, 0};
    for (int t = 0; t < 2400; t++) {
        const Rgb c = look::color_at(l, p, l.t0 + t);
        if (c.r == (uint8_t)(255 * 36045u >> 16)) at_rest++;
        if (c.g > peak.g) { peak = c; peak_t = t; }
    }
    CHECK(at_rest > 2400 * 80 / 100, "at rest for %d of 2400 ms, want about 84%%", at_rest);
    CHECK(peak.r == 255 && peak.g >= 74 && peak.b >= 59, "the peak is lifted toward white: %d %d %d", peak.r, peak.g, peak.b);
    // and it peaks where the light's own offset says: 7% into its period
    const uint32_t off = (uint32_t)((uint64_t)look::hash16(p) * 2400 >> 16);
    const int want = (int)((2400 * 7 / 100 + 2400 - off) % 2400);
    CHECK(peak_t >= want - 2 && peak_t <= want + 2, "peak at %d ms, want %d", peak_t, want);
    // different lights twinkle at different moments
    int differ = 0;
    for (int q = 0; q < 50; q++) differ += !same(look::color_at(l, q, l.t0 + 100), look::color_at(l, q + 1, l.t0 + 100));
    CHECK(differ > 5, "only %d of 50 neighbors differ at one moment", differ);
}

static void head_runs_along_each_run() {
    printf("head: a white head runs from each run's box at twenty lights a second, over half its own color\n");
    look::Look l = christmas();
    l.motion = look::HEAD;
    l.ms = 0;
    CHECK(l.period() == 2600, "the head's own period is 2.6 s");
    l.runs[0].at = 419; l.runs[0].dir = -1; l.runs[0].given = true;   // ignored by head: it counts from the box
    l.runs[0].has_rgb = true; l.runs[0].rgb = Rgb{255, 0, 0};
    px::Pixels P;
    P.order.set("rgb");
    P.set_count(40);
    for (int e = 0; e < 1900; e += 250) {
        look::draw(l, 0, l.t0 + e, 255, P);
        int white = -1, whites = 0;
        for (int k = 0; k < 40; k++) {
            const Rgb c = pixel(P, k);
            if (c.r == 255 && c.g == 255 && c.b == 255) { white = k; whites++; }
        }
        CHECK(whites == 1 && white == e / 50, "at %d ms the head is at light %d (%d of them), want %d", e, white, whites, e / 50);
    }
    look::draw(l, 0, l.t0 + 1000, 255, P);
    CHECK(same(pixel(P, 0), (Rgb{127, 0, 0})), "behind the head the run is at half its own color: %d %d %d",
          pixel(P, 0).r, pixel(P, 0).g, pixel(P, 0).b);
}

static void the_clock_prefers_the_least_late() {
    printf("the clock keeps the least-delayed offset, decays slowly, and follows a hub set back\n");
    look::Clock c;
    CHECK(!c.known() && c.now(5000) == 5000, "never told: its own uptime");
    const int64_t hub = 1790000000000LL;      // the hub's clock at local 0
    c.heard(hub + 1000, 1000 + 80);           // the hub said 1000 and it arrived 80 ms late
    c.heard(hub + 2000, 2000 + 5);            // 5 ms late
    c.heard(hub + 3000, 3000 + 140);          // 140 ms late
    CHECK(c.offset(3200) == hub - 5, "the least-late sample wins: off by %lld", (long long)(c.offset(3200) - hub));
    CHECK(c.offset(2000 + 5 + 100000) == hub - 5 - 10, "and decays a millisecond every ten seconds: %lld",
          (long long)(c.offset(102005) - hub));
    // A hub whose clock was set back a minute: the old samples age out of the eight kept.
    for (int i = 0; i < 8; i++) c.heard(hub - 60000 + 10000 + i * 1000, 10000 + i * 1000);
    CHECK(c.offset(18000) == hub - 60000, "followed the hub back within eight samples: %lld", (long long)(c.offset(18000) - hub));
}

int main() {
    the_hash_is_an_integer_and_does_not_move();
    two_boxes_agree();
    a_chase_crosses_the_seam();
    a_run_against_the_way_runs_toward_its_box();
    still_is_in_blocks();
    drift_crossfades_through_the_three();
    flicker_stays_an_ember();
    twinkle_peaks_then_rests();
    head_runs_along_each_run();
    the_clock_prefers_the_least_late();
    printf(failures ? "\n%d failed\n" : "\nlook: all good\n", failures);
    return failures ? 1 : 0;
}
