// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Getting the bytes in pixels.h onto the wire, on ESP-IDF's RMT driver -- and, for a strip with a
// clock line, on SPI.
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
//
// ONE CHANNEL PER OUTPUT, AND TWO OUTPUTS FIT. Rev A has two runs (board.h). The S3 has four RMT
// transmit channels of 48 symbols each, and only the fourth has DMA. An output without DMA asks for
// 64 symbols, as the devkit always has, which the driver rounds up to two channels' worth of memory;
// a second one like it would take the other two, and then the DMA channel -- which needs a block of
// its own -- could not be had. So run 1 keeps the devkit's channel exactly and run 2 takes the DMA
// one, and both fit with a block to spare. The DMA channel also stops caring how late Wi-Fi lets an
// interrupt run, which a non-DMA channel refilling every 40 us does care about.
#include "pixels.h"

#include <esp_heap_caps.h>
#include <esp_log.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "driver/gpio.h"
#include "driver/rmt_tx.h"
#include "driver/spi_master.h"

namespace {
const char *TAG = "pixels";

// WS2812B, in 100 ns ticks. T0H 350 ns, T1H 700 ns, period 1250 ns -- all comfortably inside the
// part's tolerances, and checked against them in test_pixels_native.cpp.
constexpr uint16_t T0H = 4, T0L = 9, T1H = 8, T1L = 5;
constexpr uint32_t TICK_HZ = 10 * 1000 * 1000;   // one tick is the 100 ns the numbers above assume

// A two-wire strip's clock. The rev A data path was shown good to 4 MHz on two meters of cable
// (parts.md, "Data path"); half that leaves room for a longer lead, and is still 16 ms for a
// thousand lights, which is faster than one wire does it at any length.
constexpr int SPI_HZ = 2 * 1000 * 1000;

struct Out {
    board::Run pins = {-1, -1, -1, -1, -1, -1, false, 0};
    px::Wire wire = px::Wire::ONE;
    rmt_channel_handle_t chan = nullptr;
    rmt_encoder_handle_t encoder = nullptr;
    spi_device_handle_t dev = nullptr;
    // The copy that goes out when it is not the picture itself (pixels.h, one_wire and two_wire).
    // INTERNAL and DMA-capable, asked for by name: with PSRAM on, an ordinary allocation this size may
    // be handed memory a DMA engine cannot read, and the SPI driver would then quietly make a second
    // copy of every frame.
    uint8_t *copy = nullptr;
    spi_transaction_t t = {};
};
Out outs[board::OUTPUTS];

bool start_one(Out &o) {
    rmt_tx_channel_config_t tx = {};
    tx.gpio_num = (gpio_num_t)o.pins.data;
    tx.clk_src = RMT_CLK_SRC_DEFAULT;
    tx.resolution_hz = TICK_HZ;
    // With DMA this is the DMA buffer, in internal RAM: 512 symbols is 64 bytes of lights a half,
    // an interrupt every 320 us rather than every 40.
    tx.mem_block_symbols = o.pins.dma ? 512 : 64;
    tx.trans_queue_depth = 4;
    tx.flags.with_dma = o.pins.dma;
    if (rmt_new_tx_channel(&tx, &o.chan) != ESP_OK) {
        ESP_LOGE(TAG, "no RMT channel on pin %d -- nothing will light", o.pins.data);
        o.chan = nullptr;
        return false;
    }

    rmt_bytes_encoder_config_t be = {};
    be.bit0 = {.duration0 = T0H, .level0 = 1, .duration1 = T0L, .level1 = 0};
    be.bit1 = {.duration0 = T1H, .level0 = 1, .duration1 = T1L, .level1 = 0};
    be.flags.msb_first = 1;   // WS2812 takes the most significant bit of each byte first
    if (rmt_new_bytes_encoder(&be, &o.encoder) != ESP_OK) {
        ESP_LOGE(TAG, "no RMT encoder -- nothing will light");
        o.encoder = nullptr;
        return false;
    }
    return rmt_enable(o.chan) == ESP_OK;
}

void stop_one(Out &o) {
    if (o.chan) { rmt_disable(o.chan); rmt_del_channel(o.chan); o.chan = nullptr; }
    if (o.encoder) { rmt_del_encoder(o.encoder); o.encoder = nullptr; }
}

spi_host_device_t host_of(const Out &o) { return o.pins.spi == 3 ? SPI3_HOST : SPI2_HOST; }

bool start_two(Out &o) {
    spi_bus_config_t bus = {};
    for (int &io : bus.iocfg) io = -1;
    bus.mosi_io_num = o.pins.data;
    bus.sclk_io_num = o.pins.clock;
    bus.max_transfer_sz = (int)px::wire_most(PX_MOST);
    if (spi_bus_initialize(host_of(o), &bus, SPI_DMA_CH_AUTO) != ESP_OK) {
        ESP_LOGE(TAG, "no SPI bus on pins %d/%d -- a two-wire strip will not light", o.pins.data, o.pins.clock);
        return false;
    }
    spi_device_interface_config_t dev = {};
    dev.mode = 0;                     // APA102 and SK9822 take data on the rising edge, clock idling low
    dev.clock_speed_hz = SPI_HZ;
    dev.spics_io_num = -1;
    dev.queue_size = 1;
    if (spi_bus_add_device(host_of(o), &dev, &o.dev) != ESP_OK) {
        ESP_LOGE(TAG, "no SPI device on pins %d/%d -- a two-wire strip will not light", o.pins.data, o.pins.clock);
        spi_bus_free(host_of(o));
        o.dev = nullptr;
        return false;
    }
    return true;
}

void stop_two(Out &o) {
    if (!o.dev) return;
    spi_bus_remove_device(o.dev);
    spi_bus_free(host_of(o));
    o.dev = nullptr;
}

// A clock line with nothing driving it is held low, so a two-wire strip on the end of a one-wire
// output sees no clock edges and shows nothing rather than noise.
void park(int pin) {
    if (pin < 0) return;
    gpio_reset_pin((gpio_num_t)pin);
    gpio_set_direction((gpio_num_t)pin, GPIO_MODE_OUTPUT);
    gpio_set_level((gpio_num_t)pin, 0);
}

bool have_copy(Out &o) {
    if (!o.copy)
        o.copy = (uint8_t *)heap_caps_malloc(px::wire_most(PX_MOST), MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    if (!o.copy) ESP_LOGE(TAG, "no internal memory for a frame -- this output stays as it was");
    return o.copy != nullptr;
}
}  // namespace

namespace px {

bool begin(int out, const board::Run &pins) {
    if (out < 0 || out >= board::OUTPUTS) return false;
    Out &o = outs[out];
    o.pins = pins;
    o.wire = Wire::ONE;
    park(pins.clock);
    return start_one(o);
}

bool rewire(int out, Wire w) {
    if (out < 0 || out >= board::OUTPUTS) return false;
    Out &o = outs[out];
    if (w == o.wire) return true;
    if (w == Wire::TWO && (o.pins.clock < 0 || !o.pins.spi)) return false;
    if (w == Wire::TWO) {
        stop_one(o);
        if (start_two(o)) { o.wire = w; return true; }
        // Put the one-wire output back rather than leave the strip with neither.
        start_one(o);
        return false;
    }
    stop_two(o);
    park(o.pins.clock);
    o.wire = w;
    return start_one(o);
}

Wire wire(int out) { return out >= 0 && out < board::OUTPUTS ? outs[out].wire : Wire::ONE; }

void show(const Pixels *const ps[], const uint16_t scale[], int n) {
    bool sent[board::OUTPUTS] = {};
    bool any_one = false;
    for (int i = 0; i < n && i < board::OUTPUTS; i++) {
        if (!ps[i]) continue;
        Out &o = outs[i];
        const Pixels &p = *ps[i];
        if (o.wire == Wire::ONE) {
            if (!o.chan || !o.encoder) continue;
            // Untouched, it goes straight from the picture -- which is the devkit's whole path, as it
            // was before there was a copy to make.
            const uint8_t *bytes = p.buf;
            size_t len = p.bytes_used();
            if (scale[i] < 256) {
                if (!have_copy(o)) continue;
                len = one_wire(p, scale[i], o.copy);
                bytes = o.copy;
            }
            rmt_transmit_config_t cfg = {};
            cfg.loop_count = 0;
            if (rmt_transmit(o.chan, o.encoder, bytes, len, &cfg) != ESP_OK) continue;
            any_one = true;
        } else {
            if (!o.dev || !have_copy(o)) continue;
            const size_t len = two_wire(p, scale[i], o.copy);
            o.t = {};
            o.t.length = len * 8;
            o.t.tx_buffer = o.copy;
            if (spi_device_queue_trans(o.dev, &o.t, portMAX_DELAY) != ESP_OK) continue;
        }
        sent[i] = true;
    }
    // Waited on, because the next caller may be about to rewrite the buffer under us -- and because
    // the reset gap below only means anything if the frame has actually finished going out.
    for (int i = 0; i < n && i < board::OUTPUTS; i++) {
        if (!sent[i]) continue;
        Out &o = outs[i];
        if (o.wire == Wire::ONE) {
            rmt_tx_wait_all_done(o.chan, portMAX_DELAY);
        } else {
            spi_transaction_t *done = nullptr;
            spi_device_get_trans_result(o.dev, &done, portMAX_DELAY);
        }
    }
    if (any_one) esp_rom_delay_us(300);   // the gap that says "that was a frame"
}

}  // namespace px
