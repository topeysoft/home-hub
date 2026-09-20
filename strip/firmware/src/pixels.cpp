// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Getting the bytes in pixels.h onto the wire.
//
// The RMT peripheral, the same route brilliant/esp32-bridge/src/light.cpp takes for its one
// indicator pixel -- the timing is generated in hardware, so a main loop that stalls for a second
// cannot corrupt a frame halfway down a strip.
//
// TWO THINGS THE BRIDGE PUCK LEARNED THE HARD WAY, and a strip makes both of them worse.
//
// One: 3.3 V logic into a part running off 5 V is electrically marginal, and a fraction of frames get
// misread. On one pixel that showed up as a "steady" green that flickered pale, and the fix was to
// write only when the color changed. THAT WORKAROUND DOES NOT SURVIVE HERE -- a fill writes every
// frame by definition, and so does anything that fades. So the shipped board carries a level shifter
// and this file assumes one. It keeps write-on-change anyway, because it costs nothing and a strip
// holding a steady color all evening should not be rewriting it sixty times a second.
//
// Two: the reset gap between frames is not optional. Two frames run together are one long frame and
// the second half of the strip takes the first half's colors.
#include "pixels.h"

#include <Arduino.h>
#include "esp32-hal-rmt.h"

namespace {
rmt_obj_t *chan = nullptr;
int dataPin = -1;
// One rmt_data_t per bit. A 300-pixel rgbw frame is 9600 bits, so this is built and sent in blocks
// rather than all at once: the RMT ring is 64 symbols deep and the driver streams through it.
constexpr int BLOCK_BYTES = 8;
rmt_data_t bits[BLOCK_BYTES * 8];

// WS2812B, in 100 ns ticks (rmtSetTick below). T0H 350 ns, T1H 700 ns, period 1250 ns.
constexpr uint16_t T0H = 4, T0L = 9, T1H = 8, T1L = 5;
}  // namespace

namespace px {

bool begin(int pin) {
    dataPin = pin;
    chan = rmtInit(pin, RMT_TX_MODE, RMT_MEM_64);
    if (!chan) return false;
    rmtSetTick(chan, 100);   // 100 ns a tick: the numbers above are the part's own
    return true;
}

void show(const Pixels &p) {
    if (!chan) return;
    const uint8_t *b = p.buf;
    size_t left = p.bytes_used();
    while (left) {
        const size_t n = left < BLOCK_BYTES ? left : BLOCK_BYTES;
        for (size_t i = 0; i < n; i++) {
            const uint8_t byte = b[i];
            for (int k = 0; k < 8; k++) {
                const bool one = byte & (0x80 >> k);
                rmt_data_t &d = bits[i * 8 + k];
                d.level0 = 1; d.duration0 = one ? T1H : T0H;
                d.level1 = 0; d.duration1 = one ? T1L : T0L;
            }
        }
        rmtWriteBlocking(chan, bits, n * 8);
        b += n;
        left -= n;
    }
    // The gap that says "that was a frame". Without it the next write is read as a continuation and
    // the strip shows one frame smeared across two.
    delayMicroseconds(300);
}

}  // namespace px
