// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Which board this image is for, and every pin it owns, in one place.
//
// Two boards run this firmware. The DEVKIT is whatever S3 board is on the desk: one output, on a pin
// that is a fact about the desk rather than about the firmware (README, "The data pin"), and nothing
// to measure. REV A is the strip controller itself (home-hub-hardware, strip/strip-revA/gen_sch.py,
// whose PARTS dict and per-run loop are the authority this copies): two runs, each switched, limited
// and measured by its own eFuse, a supply that can be anything from 5 to 24 V, and a button sealed
// into the wall of the box.
//
// CHOSEN WHEN IT IS BUILT, NOT WHEN IT BOOTS (`idf.py -DSTRIP_BOARD=reva`, README). A pin map is
// soldered, not configured: a board cannot be asked which one it is, and the wrong guess drives an
// eFuse's current-monitor pin as a data line. So the two images are different files with different
// names (CMakeLists.txt), and an update refuses an image built for the other board (fwupdate.cpp).
//
// Free of ESP-IDF, so the native tests can include it.
#pragma once

#include <stdint.h>

namespace board {

// One output: where its picture goes, and -- on rev A -- the switch that powers it and the three
// lines that say what that switch and the data-line protector think of it. -1 is "not on this board".
struct Run {
    int data;       // DATA, through a level translator (and on rev A, a line protector)
    int clock;      // CLK, for a two-wire strip (APA102, SK9822); -1 where there is none
    int en;         // the eFuse's SHDN: high lights the run. Pulled down on the board, so dark through reset
    int flt;        // the eFuse's fault: open drain, LOW when it has cut the run (current, voltage, heat)
    int dflt;       // the data-line protector's fault: LOW while something above ~6 V is on DATA or CLK
    int imon;       // the eFuse's current monitor, on ADC1
    bool dma;       // this output's one-wire channel is the RMT channel with DMA (TX channel 3 on the S3)
    int spi;        // which SPI host carries it as a two-wire strip: 2 or 3; 0 for none
};

#if defined(STRIP_BOARD_REVA)

#if defined(DATA_PIN) || defined(CLOCK_PIN) || defined(BUTTON_PIN)
#error "rev A's pins are soldered: DATA_PIN, CLOCK_PIN and BUTTON_PIN mean nothing for it. Unset them (idf.py -UDATA_PIN ...)."
#endif

constexpr const char *NAME = "reva";
constexpr int OUTPUTS = 2;

// Module pin -> GPIO, read off gen_sch.py's U1 and the per-run loop (ESP32-S3-WROOM-1 pinout):
//   19/20 -> 11/12 D1/C1     21/22 -> 13/14 D2/C2     23/24 -> 21/47 EN1/EN2
//    8/9  -> 15/16 FLT1/2    10/11 -> 17/18 DFLT1/2    5/6  ->  5/6  IMON1/2
//    7    ->  7 VSENSE       12    ->  8 NTC            4   ->  4    the press
// DATA1/CLK1 are SPI2's own pins; run 2 reaches SPI3 through the matrix. Run 1 keeps the devkit's
// one-wire channel, which is proven; run 2 takes the channel with DMA (pixels.cpp says why both fit).
constexpr Run RUNS[OUTPUTS] = {
    {11, 12, 21, 15, 17, 5, false, 2},
    {13, 14, 47, 16, 18, 6, true, 3},
};

// THE SUPPLY, through 200k over 10k: a ratio of 21, read at the 6 dB range, where 24 V is 1.14 V
// at the pin and 30 V is 1.43 V. 100 nF at the pin.
constexpr int VSENSE = 7;
constexpr float VSENSE_RATIO = (200.0f + 10.0f) / 10.0f;

// THE BOARD'S OWN TEMPERATURE: a 10k NTC (B3435) to ground with a 10k pull-up to the 3.3 V rail,
// read at 12 dB. The rail is the LMR38020's 1.0 V x (1 + 100k/43.2k).
constexpr int NTC = 8;
constexpr float NTC_RAIL_MV = 1000.0f * (1.0f + 100.0f / 43.2f);

// THE CURRENT MONITOR: 27.9 uA per amp into 8.2 kohm, 0.229 V an amp. The switch's own limit is
// 18/3.3k = 5.45 A nominal and 5.07 A at the low end of its tolerance; the product promises 5 A.
constexpr float IMON_V_PER_A = 27.9e-6f * 8200.0f;

// THE PRESS: a sealed gold-contact tact switch with a 2.2k pull-up, active low, and not a strapping
// pin. A press shorter than this is a contact bouncing, not a finger.
constexpr int BUTTON = 4;
constexpr uint32_t PRESS_SHORTEST_MS = 30;

// THE MOST LIGHTS ONE OUTPUT WILL DRIVE, and why it is a thousand rather than more.
//   Time: a one-wire light is 30 us on the wire, so a thousand is 30 ms a frame -- about 33 a second,
//         which is where a run of light down a drive (design/signal/) stops reading as motion and
//         starts reading as steps. More lights on one output buys a picture that stutters.
//   Memory: every frame lives in INTERNAL RAM, because it goes out by DMA and the S3's PSRAM is the
//         wrong side of the cache for that. Four bytes a light for the picture and four more for the
//         copy that goes out dimmed (or framed, for a two-wire strip) is about 8 KB an output and
//         16 KB for both, plus 2 KB of RMT DMA buffer, against the ~95 KB low-water mark Matter
//         leaves today. Twice this would still fit and would leave the radio's heap thinner than
//         anybody has measured it run on.
//   PSRAM: the 2 MB on the module does not raise this number. It is for what is drawn rather than
//         what is sent -- effect buffers, streamed frames -- and frames are copied in from it.
//   Power: at 5 A a run the limiter is dimming long before a thousand lights are all lit anyway.
#define PX_MOST 1000

#else  // the devkit: today's board, unchanged

constexpr const char *NAME = "devkit";
constexpr int OUTPUTS = 1;

#ifndef DATA_PIN
#define DATA_PIN 5
#endif
// GPIO 0 is BOOT on every devkit and an ordinary input once running. A hold only counts once it has
// been seen let go: it is held down to flash, it is a strapping pin, and on some boards it sits low,
// and any of those would otherwise factory-reset the device five seconds into every boot for ever.
#ifndef BUTTON_PIN
#define BUTTON_PIN 0
#endif
// A CLOCK pin for trying a two-wire strip on a bench (`idf.py -DCLOCK_PIN=6`). Unset, the devkit has
// one wire and `type/set` is ignored, exactly as before there was a second kind of strip.
#ifndef CLOCK_PIN
#define CLOCK_PIN -1
#endif

constexpr Run RUNS[OUTPUTS] = {
    {DATA_PIN, CLOCK_PIN, -1, -1, -1, -1, false, CLOCK_PIN >= 0 ? 2 : 0},
};
constexpr int BUTTON = BUTTON_PIN;
constexpr uint32_t PRESS_SHORTEST_MS = 0;   // as it always was: any press the loop sees counts

#endif

}  // namespace board
