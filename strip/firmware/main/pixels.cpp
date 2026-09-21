// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Getting the bytes in pixels.h onto the wire, on ESP-IDF's RMT driver.
//
// THE BUFFER IS GONE, and that is the whole difference from the Arduino version. That one had to
// build an RMT symbol per bit by hand -- four bytes for every bit of every frame, 76 KB claimed up
// front on a part with no PSRAM -- and when that allocation failed the draw call returned silently
// for ever, which on a bench looks exactly like a strip that never lights. IDF has a bytes encoder:
// it is told what a zero and a one look like once, and then streams the pixel bytes straight out.
// Nothing to allocate, nothing to size, nothing to fail quietly.
//
// One transmission per frame, which is not an optimization. The gap between two transmissions is
// whatever the scheduler feels like, and a gap over about 50 us is what a WS2812 reads as END OF
// FRAME -- so a frame sent in pieces would look right at thirty lights and tear at three hundred.
//
// The other thing the bridge puck learned still holds: 3.3 V logic into a part running off 5 V is
// electrically marginal, a fraction of frames are misread, and a fill writes every frame by
// definition. The shipped board carries a level shifter and this assumes one.
#include "pixels.h"

#include <esp_log.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "driver/rmt_tx.h"

namespace {
const char *TAG = "pixels";
rmt_channel_handle_t chan = nullptr;
rmt_encoder_handle_t encoder = nullptr;

// WS2812B, in 100 ns ticks. T0H 350 ns, T1H 700 ns, period 1250 ns -- all comfortably inside the
// part's tolerances, and checked against them in test_pixels_native.cpp.
constexpr uint16_t T0H = 4, T0L = 9, T1H = 8, T1L = 5;
constexpr uint32_t TICK_HZ = 10 * 1000 * 1000;   // one tick is the 100 ns the numbers above assume
}  // namespace

namespace px {

bool begin(int pin) {
    rmt_tx_channel_config_t tx = {};
    tx.gpio_num = (gpio_num_t)pin;
    tx.clk_src = RMT_CLK_SRC_DEFAULT;
    tx.resolution_hz = TICK_HZ;
    tx.mem_block_symbols = 64;
    tx.trans_queue_depth = 4;
    if (rmt_new_tx_channel(&tx, &chan) != ESP_OK) {
        ESP_LOGE(TAG, "no RMT channel on pin %d -- nothing will light", pin);
        return false;
    }

    rmt_bytes_encoder_config_t be = {};
    be.bit0 = {.duration0 = T0H, .level0 = 1, .duration1 = T0L, .level1 = 0};
    be.bit1 = {.duration0 = T1H, .level0 = 1, .duration1 = T1L, .level1 = 0};
    be.flags.msb_first = 1;   // WS2812 takes the most significant bit of each byte first
    if (rmt_new_bytes_encoder(&be, &encoder) != ESP_OK) {
        ESP_LOGE(TAG, "no RMT encoder -- nothing will light");
        return false;
    }
    return rmt_enable(chan) == ESP_OK;
}

void show(const Pixels &p) {
    if (!chan || !encoder) return;
    rmt_transmit_config_t cfg = {};
    cfg.loop_count = 0;
    if (rmt_transmit(chan, encoder, p.buf, p.bytes_used(), &cfg) != ESP_OK) return;
    // Waited on, because the next caller may be about to rewrite the buffer under us -- and because
    // the reset gap below only means anything if the frame has actually finished going out.
    rmt_tx_wait_all_done(chan, portMAX_DELAY);
    esp_rom_delay_us(300);   // the gap that says "that was a frame"
}

}  // namespace px
