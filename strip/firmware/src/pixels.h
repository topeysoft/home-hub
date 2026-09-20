// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// What goes down the wire, and the two things about a strip nobody can ask it.
//
// A WS2812-family strip has one data line and no way back: it is write-only, on every part in this
// family. So the controller cannot discover how long the strip is, and cannot discover which order
// the strip wants its colors in. Both are settled by SHOWING something and having a person say what
// they can see (design/strip/Order.dc.html, design/strip/Fill.dc.html), and both answers arrive here
// over MQTT from the hub and live in NVS afterwards.
//
// EVERYTHING IN THIS HEADER IS FREE OF Arduino, ON PURPOSE. It is the part that is easy to get subtly
// wrong and impossible to notice on a bench -- a strip with its red and green swapped looks like it
// is working -- so it compiles on a Mac and is checked against the brain's own arithmetic
// (test_pixels_native.cpp, and brain/hub/strip.py). The RMT writing lives in pixels.cpp, which is
// where the Arduino include is.
#pragma once

#include <stddef.h>
#include <stdint.h>
#include <string.h>

// The most lights one controller will drive. Not a limit anybody should meet: a 5 m strip at 60/m is
// 300, and past about that the 5 V rail is the thing that gives out, not this.
#define PX_MOST 1200

// How many lights to write before the household has said. A strip shorter than this simply does not
// receive the rest -- the surplus falls off the end of the wire and nobody ever sees it -- which is
// what makes "never ask" a real design option rather than a shortcut (design/strip/Never.dc.html).
#define PX_ASSUMED 300

namespace px {

// Where each channel sits in the bytes that go out, for one of the six orderings in circulation.
// "grb" is WS2812B and is most of what anybody owns; "rgb" is WS2811 and APA106; the rest are clones.
// A separate white, when the strip has one, is always last -- SK6812 is "grbw" -- so it is a flag
// here rather than a fourth letter, and no ordering in the wild puts it anywhere else.
struct Order {
    uint8_t at[3] = {1, 0, 2};   // at[0] is where RED goes, at[1] green, at[2] blue. Default: grb.
    bool white = false;

    // Returns false and changes nothing if `s` is not three of r, g and b with none repeated. A
    // strip left on its old ordering is wrong in a way somebody can see and fix; one left on a half
    // applied ordering is wrong in a way nobody can describe.
    bool set(const char *s) {
        if (!s) return false;
        uint8_t next[3];
        bool got[3] = {false, false, false};
        for (int i = 0; i < 3; i++) {
            int c = s[i] == 'r' ? 0 : s[i] == 'g' ? 1 : s[i] == 'b' ? 2 : -1;
            if (c < 0 || got[c]) return false;
            got[c] = true;
            next[c] = (uint8_t)i;
        }
        if (s[3] != '\0') return false;
        memcpy(at, next, sizeof(at));
        return true;
    }

    // The three bytes for one pixel of this color, in the order this strip wants them.
    void bytes(uint8_t r, uint8_t g, uint8_t b, uint8_t *out) const {
        out[at[0]] = r;
        out[at[1]] = g;
        out[at[2]] = b;
    }

    int per_pixel() const { return white ? 4 : 3; }
};

// The buffer, and what is currently being shown.
struct Pixels {
    uint8_t buf[PX_MOST * 4] = {0};
    int count = PX_ASSUMED;
    Order order;

    size_t bytes_used() const { return (size_t)count * order.per_pixel(); }

    void clear() { memset(buf, 0, bytes_used()); }

    void solid(uint8_t r, uint8_t g, uint8_t b, uint8_t w = 0) {
        const int n = order.per_pixel();
        for (int i = 0; i < count; i++) {
            order.bytes(r, g, b, &buf[i * n]);
            if (order.white) buf[i * n + 3] = w;
        }
    }

    // THE ORDER QUESTION, and the reason it is not just solid() with the mapping turned off.
    //
    // The hub works out which three bytes would be red IF the strip is what we are guessing, and
    // sends those bytes. They go out exactly as given, because applying a mapping here would be
    // applying the very guess that is being tested.
    //
    // It writes a REPEATING THREE-BYTE PATTERN across the whole buffer, and on a strip that carries
    // a separate white that is the point rather than a bug: three bytes per pixel fed to a part that
    // eats four misaligns by one byte per pixel and comes out as a candy-stripe instead of one
    // color. That is the household's "stripes of color" answer, and it tells the hub how many
    // channels the strip has without anybody having to know the word. So this deliberately ignores
    // order.white and always strides three.
    void raw3(uint8_t b0, uint8_t b1, uint8_t b2) {
        const uint8_t triple[3] = {b0, b1, b2};
        const size_t span = (size_t)count * (size_t)order.per_pixel();
        for (size_t i = 0; i < span; i++) buf[i] = triple[i % 3];
    }

    void set_count(int n) { count = n < 1 ? 1 : n > PX_MOST ? PX_MOST : n; }
};

// THE FILL, and the one thing it must get right.
//
// Lights come on one at a time from the plug end and the household taps when the far end lights. The
// moment the strip is past the real end it is writing to pixels that do not exist, so nothing visible
// changes -- which is exactly why it is a fill and not a travelling dot: a dot would simply vanish
// and there would be nothing left to tap.
//
// STOP LATCHES HERE, in the firmware, at the instant the message arrives. Reading a number back to
// the hub and letting the hub decide would add however busy the Wi-Fi is to an answer whose only
// other error is a person's reaction time -- so a strip would measure short on a busy evening and
// right on a quiet one, which is the worst kind of wrong.
struct Fill {
    bool running = false;
    int at = 0;            // how many are lit
    uint32_t last = 0;     // when the last one came on
    uint32_t step = 28;    // ms between lights: about eleven seconds for a 5 m strip

    void start(uint32_t now) { running = true; at = 0; last = now; }

    // Advances by however many steps have elapsed, so a loop that stalls does not fall behind. Wraps
    // to empty when it runs off the end, because missing it has to cost nothing but another pass.
    void tick(uint32_t now, int most) {
        if (!running || most < 1) return;
        while (now - last >= step) {
            last += step;
            if (++at > most) at = 0;
        }
    }

    int stop() { running = false; return at < 1 ? 1 : at; }
};

}  // namespace px
