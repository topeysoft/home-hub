// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Getting the bytes in pixels.h onto the wire.
//
// The RMT peripheral, the same route brilliant/esp32-bridge/src/light.cpp takes for its one indicator
// pixel: the timing is generated in hardware, so a main loop that stalls for a second cannot corrupt
// a frame halfway down a strip.
//
// ONE WRITE PER FRAME, AND THAT IS NOT AN OPTIMISATION. A first draft here built the symbols eight
// bytes at a time and called rmtWrite for each block. The gap between two of those calls is whatever
// the scheduler feels like, and a gap over about 50 us is exactly what a WS2812 reads as END OF
// FRAME -- so a long strip would have shown the first block, latched, and then taken the rest as the
// beginning of a new frame. The symptom would have been a strip that looks right at 30 pixels and
// tears at 300, which is the kind of thing that gets found in somebody's living room.
//
// TWO THINGS THE BRIDGE PUCK LEARNED THE HARD WAY, and a strip makes both worse. 3.3 V logic into a
// part running off 5 V is electrically marginal and a fraction of frames are misread; on one pixel
// that was a "steady" green that flickered pale, and the fix was to write only on change. THAT
// WORKAROUND DOES NOT SURVIVE HERE, because a fill writes every frame by definition. So the shipped
// board carries a level shifter and this assumes one.
#include "pixels.h"

#include <Arduino.h>
#include <esp_heap_caps.h>

#include "esp32-hal-rmt.h"

namespace {
int dataPin = -1;
bool ready = false;
// One RMT symbol per bit of the frame. Allocated once, big enough for the largest frame this
// controller will ever send, and out of PSRAM where there is any -- 600 rgbw pixels is 76 KB of
// symbols, which is a lot to ask of internal RAM on a part that is also holding Matter and Wi-Fi.
rmt_data_t *symbols = nullptr;
size_t symbolsFor = 0;

// WS2812B, in 100 ns ticks. T0H 350 ns, T1H 700 ns, period 1250 ns.
constexpr uint16_t T0H = 4, T0L = 9, T1H = 8, T1L = 5;
constexpr uint32_t TICK_HZ = 10 * 1000 * 1000;   // 10 MHz: one tick is the 100 ns the numbers assume
}  // namespace

namespace px {

bool begin(int pin) {
    dataPin = pin;
    const size_t want = (size_t)PX_MOST * 4 * 8;
    symbols = (rmt_data_t *)heap_caps_malloc(want * sizeof(rmt_data_t), MALLOC_CAP_SPIRAM);
    if (!symbols) symbols = (rmt_data_t *)heap_caps_malloc(want * sizeof(rmt_data_t), MALLOC_CAP_8BIT);
    if (!symbols) return false;
    symbolsFor = want;
    ready = rmtInit(pin, RMT_TX_MODE, RMT_MEM_NUM_BLOCKS_1, TICK_HZ);
    return ready;
}

void show(const Pixels &p) {
    if (!ready || !symbols) return;
    const size_t n = p.bytes_used();
    if (n * 8 > symbolsFor) return;
    for (size_t i = 0; i < n; i++) {
        const uint8_t byte = p.buf[i];
        for (int k = 0; k < 8; k++) {
            const bool one = byte & (0x80 >> k);
            rmt_data_t &d = symbols[i * 8 + k];
            d.level0 = 1; d.duration0 = one ? T1H : T0H;
            d.level1 = 0; d.duration1 = one ? T1L : T0L;
        }
    }
    rmtWrite(dataPin, symbols, n * 8, RMT_WAIT_FOR_EVER);
    // The gap that says "that was a frame". Without it the next write is read as a continuation and
    // the strip shows one frame smeared across two.
    delayMicroseconds(300);
}

}  // namespace px
