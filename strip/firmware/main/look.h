// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// A look on the roofline: the household's colors, moving or still, drawn by every box from one clock
// so that a roof of several boxes reads as one light.
//
// NOT A SIGNAL, AND NOT AN EFFECT. A signal (pixels.h) says something and is over; a look is how the
// house is lit for an evening -- red and green chasing for Christmas, orange and purple unsteady like
// embers for Halloween. Every motion here is a way for the given colors to BE: none brings a color of
// its own, which is the line design/occasion/ drew and design/roofline/ keeps.
//
// THE SPEC IS THE BOARD. design/roofline/OwnsA.dc.html draws each motion as a CSS animation on a light
// at a roof position, and its paint() and @keyframes (ch2, ch3, dr, tw, fl, hd) are what these
// functions reproduce: the same phase for the same light at the same moment, so the board the
// household chose from is the roof they get.
//
// DRAWN ON THE BOX FROM A SHARED CLOCK, NEVER STREAMED. A chase that crosses from one box's run to the
// next has to arrive at the seam on time, and two boxes on a house's Wi-Fi cannot be kept in step by
// sending them frames. So the hub sends each box the look once, with where each of its runs sits on
// the roof, and every box computes every frame as a function of (roof position, shared time). Two
// boxes that agree on the time agree on the picture without ever talking to each other.
//
// INTEGERS THROUGHOUT, SO EVERY BOX AGREES TO THE BYTE. The board used Math.sin for its hash; a
// float sine is not the same function on every libm, and "nearly the same" at a seam is a visible
// step. hash() below is an integer mix, and the phase arithmetic is integer too, so a box and the
// native test compute identical bytes.
//
// Free of ESP-IDF, so test_look_native.cpp holds every motion to its keyframes. app_main.cpp parses the
// message, keeps the clock fed, and calls draw() from the housekeeping loop.
#pragma once

#include <stdint.h>
#include <string.h>

#include "pixels.h"

namespace look {

constexpr int MOST_COLORS = 8;
constexpr int MOST_RUNS = 4;            // a box has at most two; room for a hub that lists more

enum Motion : uint8_t { OFF = 0, STILL, CHASE, DRIFT, FLICKER, TWINKLE, HEAD };

static inline Motion motion_of(const char *s)
{
    if (!s) return OFF;
    if (!strcmp(s, "still")) return STILL;
    if (!strcmp(s, "chase")) return CHASE;
    if (!strcmp(s, "drift")) return DRIFT;
    if (!strcmp(s, "flicker")) return FLICKER;
    if (!strcmp(s, "twinkle")) return TWINKLE;
    if (!strcmp(s, "head")) return HEAD;
    return OFF;
}

struct Rgb { uint8_t r = 0, g = 0, b = 0; };

// WHERE ONE OF THIS BOX'S RUNS SITS ON THE ROOF. Light k of the run is at roof position at + dir*k:
// `at` is where its FIRST light is -- the one at the box -- and `dir` -1 is a run that leaves its box
// against the way round the house, which nearly every real roof has one of, because a run always
// leaves its box. So a run of n lights going against the way, ending where the run before it ended at
// position e, has at = e + n and dir -1. `rgb` is only for "head", where each run shows its own color.
struct Run
{
    int32_t at = 0;
    int8_t dir = 1;
    bool given = false;     // named in the message, rather than the default at 0, dir 1
    bool has_rgb = false;
    Rgb rgb;
};

struct Look
{
    char id[48] = "";
    Motion motion = OFF;
    Rgb colors[MOST_COLORS];
    uint8_t n = 0;
    uint16_t block = 1;
    uint32_t ms = 0;        // the period; 0 is the motion's own (period())
    int64_t t0 = 0;         // hub ms since the epoch at which the look began
    Run runs[MOST_RUNS];

    bool on() const { return motion != OFF; }
    // A still look is painted once; anything else is drawn a frame at a time.
    bool moving() const { return motion != OFF && motion != STILL; }
    // 2.4 s is the board's own default (paint(): look.dur || 2.4) and 2.6 s is the head's (look.dur || 2.6).
    uint32_t period() const { return ms ? ms : motion == HEAD ? 2600 : 2400; }

    // What arrived, kept within what the arithmetic below was sized for: a period from a fifth of a
    // second to two minutes, blocks of up to 64, up to eight colors. Nothing a household chose is near
    // any of them.
    void tidy()
    {
        if (ms && ms < 200) ms = 200;
        if (ms > 120000) ms = 120000;
        if (block < 1) block = 1;
        if (block > 64) block = 64;
        if (n > MOST_COLORS) n = MOST_COLORS;
    }
};

// ---------------------------------------------------------------- the arithmetic

// A remainder that is never negative, so a position or a moment before the look began is still on the
// same pattern rather than mirrored at zero.
static inline int64_t mod(int64_t a, int64_t m) { const int64_t r = a % m; return r < 0 ? r + m : r; }
static inline int32_t floordiv(int32_t a, int32_t b) { return a >= 0 ? a / b : -((-a + b - 1) / b); }

// THE HASH, the same on every box: Chris Wellons' "lowbias32" integer mix, taken to its top sixteen
// bits as a fraction out of 65536. It stands where the board's Math.sin hash stood -- a light's own
// steady randomness, for which ember it is and when it twinkles -- and is not the same numbers, which
// does not matter: what matters is that every box draws light p the same way.
static inline uint32_t mix(uint32_t x)
{
    x ^= x >> 16;
    x *= 0x7feb352du;
    x ^= x >> 15;
    x *= 0x846ca68bu;
    x ^= x >> 16;
    return x;
}
static inline uint32_t hash16(int32_t p) { return mix((uint32_t)p) >> 16; }

// Q16 fractions of a period: 65536 is the whole of it.
constexpr uint32_t ONE16 = 65536;
static inline uint32_t pct16(uint32_t pct) { return pct * ONE16 / 100; }

static inline uint8_t lerp8(uint8_t a, uint8_t b, uint32_t x, uint32_t span)
{
    if (!span) return b;
    return (uint8_t)((int32_t)a + ((int32_t)b - (int32_t)a) * (int32_t)x / (int32_t)span);
}
static inline Rgb lerp(const Rgb &a, const Rgb &b, uint32_t x, uint32_t span)
{
    Rgb o;
    o.r = lerp8(a.r, b.r, x, span);
    o.g = lerp8(a.g, b.g, x, span);
    o.b = lerp8(a.b, b.b, x, span);
    return o;
}
// `c` at `level` out of 65536.
static inline Rgb at_level(const Rgb &c, uint32_t level)
{
    Rgb o;
    o.r = (uint8_t)((c.r * level) >> 16);
    o.g = (uint8_t)((c.g * level) >> 16);
    o.b = (uint8_t)((c.b * level) >> 16);
    return o;
}
// CSS's ease-in-out, which the twinkle is timed with, as smoothstep: the same shape to within a few
// percent, and an integer one.
static inline uint32_t ease16(uint32_t x)
{
    const uint64_t x2 = (uint64_t)x * x >> 16;
    const uint64_t x3 = x2 * x >> 16;
    const int64_t s = 3 * (int64_t)x2 - 2 * (int64_t)x3;
    return (uint32_t)(s < 0 ? 0 : s > ONE16 ? ONE16 : s);
}

// A keyframe table of levels, linear between: `at` in percent, `lv` in thousandths.
static inline uint32_t keyed(const uint8_t *at, const uint16_t *lv, int n, uint32_t f16)
{
    for (int i = 1; i < n; i++) {
        const uint32_t a = pct16(at[i - 1]), b = pct16(at[i]);
        if (f16 < b || i == n - 1) {
            const uint32_t x = f16 < a ? 0 : f16 - a, span = b - a;
            const int32_t v = (int32_t)lv[i - 1] + ((int32_t)lv[i] - (int32_t)lv[i - 1]) * (int32_t)(x > span ? span : x) / (int32_t)(span ? span : 1);
            return (uint32_t)v * ONE16 / 1000;
        }
    }
    return (uint32_t)lv[n - 1] * ONE16 / 1000;
}

// THE FLICKER'S FL KEYFRAMES: unsteady, never dark. Opacity .45 to 1, which an ember is.
constexpr uint8_t FL_AT[] = {0, 12, 20, 34, 49, 63, 78, 100};
constexpr uint16_t FL_LV[] = {920, 500, 1000, 660, 950, 450, 880, 920};

// ---------------------------------------------------------------- the color of one light

// The moment, worked out once a frame: time since the look began, and where in its period that is.
struct Moment
{
    int64_t e = 0;
    uint32_t in = 0;        // e mod period
};

static inline Moment moment(const Look &l, int64_t t_ms)
{
    Moment m;
    m.e = t_ms - l.t0;
    m.in = (uint32_t)mod(m.e, l.period());
    return m;
}

// THE COLOR AT ROOF POSITION p, AT SHARED TIME t, at full brightness. For "head", p is the light's
// index along its OWN run, counted from the box in the run's direction, and `own` is the run's color.
static inline Rgb color_in(const Look &l, int32_t p, const Moment &m, const Rgb *own = nullptr)
{
    static const Rgb warm = {255, 180, 110};
    const Rgb *cs = l.n ? l.colors : &warm;
    const int32_t n = l.n ? l.n : 1, b = l.block ? l.block : 1;
    const uint32_t D = l.period();
    switch (l.motion) {
    case STILL:
        return cs[mod(floordiv(p, b), n)];

    case CHASE: {
        // ch2/ch3: each light steps through the colors in turn, a block's width of phase behind the
        // light before it, so the pattern moves toward increasing p. progress = frac(t/D - (p%P)/P).
        const uint32_t P = (uint32_t)(b * n);
        const uint32_t DP = D * P;
        const uint32_t k = (uint32_t)mod((int64_t)m.in * P - (int64_t)mod(p, P) * D, DP);
        return cs[(uint64_t)k * n / DP];
    }

    case DRIFT: {
        // dr: c1, c2 at 33%, c3 at 66%, c1 again, crossfaded; forty-six lights to one sweep of phase.
        const uint32_t W = 46, DW = D * W;
        const uint32_t k = (uint32_t)mod((int64_t)m.in * W - (int64_t)mod(p, W) * D, DW);
        const Rgb &c1 = cs[0], &c2 = cs[1 % n], &c3 = cs[2 % n];
        const uint32_t a = DW / 100 * 33 + DW % 100 * 33 / 100, z = DW / 100 * 66 + DW % 100 * 66 / 100;
        if (k < a) return lerp(c1, c2, k, a);
        if (k < z) return lerp(c2, c3, k - a, z - a);
        return lerp(c3, c1, k - z, DW - z);
    }

    case FLICKER: {
        // fl: each light its own ember color, its own period of 1.3 to 2.2 s, and its own place in it.
        const Rgb &c = cs[(int64_t)hash16(p + 11) * n >> 16];
        const uint32_t period = 1300 + (hash16(p) * 900 >> 16);
        const uint32_t off = hash16(p + 3) * 2000 >> 16;
        const uint32_t f = (uint32_t)((uint64_t)mod(m.e + off, period) * ONE16 / period);
        return at_level(c, keyed(FL_AT, FL_LV, 8, f));
    }

    case TWINKLE: {
        // tw: .55 most of the time; brighter and toward white at 7%; back by 16%. Each light at its own
        // place in the period.
        const Rgb &c = cs[mod(floordiv(p, b), n)];
        const uint32_t off = (uint32_t)((uint64_t)hash16(p) * D >> 16);
        const uint32_t f = (uint32_t)((uint64_t)((m.in + off) % D) * ONE16 / D);
        const uint32_t up = pct16(7), down = pct16(16);
        uint32_t a = 0;
        if (f < up) a = ease16(f * ONE16 / up);
        else if (f < down) a = ONE16 - ease16((f - up) * ONE16 / (down - up));
        // brightness(1.7) at the peak, clipped: the off-channels lift, which is what reads as a glint.
        const uint32_t lift = ONE16 + (45875u * a >> 16);   // 1.0 .. 1.7
        Rgb lit;
        lit.r = (uint8_t)(((c.r * lift) >> 16) > 255 ? 255 : (c.r * lift) >> 16);
        lit.g = (uint8_t)(((c.g * lift) >> 16) > 255 ? 255 : (c.g * lift) >> 16);
        lit.b = (uint8_t)(((c.b * lift) >> 16) > 255 ? 255 : (c.b * lift) >> 16);
        return at_level(lit, 36045u + (29491u * a >> 16));  // .55 .. 1.0
    }

    case HEAD: {
        // hd: a white head runs along each run from its box, at twenty lights a second, and the run
        // sits at half its own color behind it -- which is how the yard says which way each run goes.
        const Rgb c = own ? *own : cs[0];
        static const Rgb white = {255, 255, 255};
        const int64_t lag = (int64_t)p * 50;
        const uint32_t f = (uint32_t)((uint64_t)mod((int64_t)m.in - lag, D) * ONE16 / D);
        const uint32_t nine = pct16(9), thirty = pct16(30);
        if (f < nine) return lerp(white, c, f, nine);
        if (f < thirty) return at_level(c, ONE16 - (ONE16 / 2) * (f - nine) / (thirty - nine));
        return at_level(c, ONE16 / 2);
    }

    default:
        return cs[0];
    }
}

static inline Rgb color_at(const Look &l, int32_t p, int64_t t_ms, const Rgb *own = nullptr)
{
    return color_in(l, p, moment(l, t_ms), own);
}

// Where light k of this box's run `run` is on the roof. A run the message did not name is at 0, dir 1.
static inline int32_t position(const Look &l, int run, int k)
{
    if (run < 0 || run >= MOST_RUNS) return k;
    const Run &r = l.runs[run];
    return r.at + (r.dir < 0 ? -k : k);
}

// THE FRAME FOR ONE OUTPUT, drawn into its picture at the household's brightness and through its own
// color order, exactly as the household's light is (app_main.cpp, paint): a white byte, if the strip
// has one, stays dark. Returns whether any byte changed, which is the whole of the rule that a frame
// goes down the wire only when it is a different one (AGENTS.md section 4).
static inline bool draw(const Look &l, int run, int64_t t_ms, uint8_t bri, px::Pixels &out)
{
    const Moment m = moment(l, t_ms);
    const uint16_t k = bri ? bri : 1;
    const int per = out.order.per_pixel();
    const Run *r = run >= 0 && run < MOST_RUNS ? &l.runs[run] : nullptr;
    const Rgb own = r && r->has_rgb ? r->rgb : (l.n ? l.colors[0] : Rgb{255, 180, 110});
    bool changed = false;
    for (int i = 0; i < out.count; i++) {
        const int32_t p = l.motion == HEAD ? i : position(l, run, i);
        const Rgb c = color_in(l, p, m, &own);
        uint8_t px3[4] = {0, 0, 0, 0};
        out.order.bytes((uint8_t)(c.r * k / 255), (uint8_t)(c.g * k / 255), (uint8_t)(c.b * k / 255), px3);
        uint8_t *at = &out.buf[i * per];
        if (memcmp(at, px3, per) != 0) {
            memcpy(at, px3, per);
            changed = true;
        }
    }
    return changed;
}

// ---------------------------------------------------------------- the shared clock

// THE HUB'S TIME, AS WELL AS THIS BOX CAN KNOW IT. The hub says its own milliseconds since the epoch
// (`clock/set`, and `now` in every `look/set`); the box keeps the difference from its own uptime.
//
// A MESSAGE CAN ONLY EVER BE LATE. MQTT's delay -- the broker, the Wi-Fi, a retry -- adds to the time
// between the hub reading its clock and this box hearing it, and never takes away. So each sample's
// offset is the true one minus some delay, and the LARGEST recent one is the least delayed and the
// best. The last eight are kept, so a hub whose clock is set back is followed within eight samples
// rather than never.
//
// AND IT DECAYS, SLOWLY, because two crystals drift. Each kept sample counts for a millisecond less
// every ten seconds of its age -- 100 ppm, past what either crystal drifts -- so an old, lucky sample
// cannot hold the estimate above the truth for ever. Every box decays the same way, so what they lose
// to it they lose together; a hub that says the time every minute or so keeps it to a few ms.
struct Clock
{
    static constexpr int KEEP = 8;
    static constexpr int64_t DECAY_EVERY_MS = 10000;
    int64_t off[KEEP] = {};
    int64_t at[KEEP] = {};
    int n = 0, next = 0;

    void heard(int64_t hub_ms, int64_t local_ms)
    {
        off[next] = hub_ms - local_ms;
        at[next] = local_ms;
        next = (next + 1) % KEEP;
        if (n < KEEP) n++;
    }
    bool known() const { return n > 0; }
    int64_t offset(int64_t local_ms) const
    {
        int64_t best = 0;
        for (int i = 0; i < n; i++) {
            const int64_t age = local_ms - at[i];
            const int64_t o = off[i] - (age > 0 ? age / DECAY_EVERY_MS : 0);
            if (i == 0 || o > best) best = o;
        }
        return best;
    }
    // The hub's time now, or this box's own uptime when it has never been told -- a look still draws,
    // and only agreeing with the box next door has to wait for the first `clock/set`.
    int64_t now(int64_t local_ms) const { return local_ms + offset(local_ms); }
};

}  // namespace look
