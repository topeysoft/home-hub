#include "light.h"

#include <math.h>

// Which LED this board has. A colour one (WS2812) on the pins the S3 devkits put it on -- GPIO48 on
// the v1.0 board and on the clones, GPIO38 on v1.1 -- and the shipped image cannot know which it
// landed on, so it drives both; each is a free pin on the other revision. -DBRIDGE_RGB_PIN=n names a
// single other pin. A board with none of that gets the plain LED_BUILTIN; nothing at all stays silent.
//
// Each pin gets its own RMT channel through the core's rmt API -- the same thing neopixelWrite()
// does, which is tied to one static channel and so one pin. A hand-timed bit-bang was tried first
// and abandoned: its timing was a guess, and a guess is the wrong thing to stand between "the LED
// is dark" and "the board's RGB solder pad is not bridged", which is what the dark LED actually was.
#if defined(BRIDGE_RGB_PIN)
static const int RGB_PINS[] = {BRIDGE_RGB_PIN};
#define HAVE_RGB 1
#elif defined(CONFIG_IDF_TARGET_ESP32S3)
static const int RGB_PINS[] = {48, 38};
#define HAVE_RGB 1
#endif

#ifdef HAVE_RGB
#include "esp32-hal-rmt.h"
static const int NPINS = sizeof(RGB_PINS) / sizeof(RGB_PINS[0]);
static rmt_obj_t *chan[NPINS] = {nullptr};

static void rgbBegin() {
    for (int i = 0; i < NPINS; i++) {
        chan[i] = rmtInit(RGB_PINS[i], RMT_TX_MODE, RMT_MEM_64);
        if (chan[i]) rmtSetTick(chan[i], 100);   // 100 ns per tick: the numbers below are the WS2812's own
    }
}
static void rgbWrite(uint8_t r, uint8_t g, uint8_t b) {
    rmt_data_t bits[24];
    uint32_t grb = ((uint32_t)g << 16) | ((uint32_t)r << 8) | b;
    for (int i = 0; i < 24; i++) {
        bool one = grb & (1UL << (23 - i));
        bits[i].level0 = 1; bits[i].duration0 = one ? 8 : 4;   // 0.8 us / 0.4 us high
        bits[i].level1 = 0; bits[i].duration1 = one ? 4 : 8;   // 0.4 us / 0.8 us low
    }
    for (int i = 0; i < NPINS; i++) if (chan[i]) rmtWrite(chan[i], bits, 24);
}
#endif

static volatile Light want = Light::Off;

// The three colours, as the panel draws them (--lamp, --live, --danger),
// dimmed: a WS2812 at full white is a torch, not an indicator.
static const uint8_t AMBER[3] = {58, 36, 8};
static const uint8_t GREEN[3] = {10, 52, 24};
static const uint8_t RED[3] = {56, 12, 12};

static void paint(const uint8_t *c, float k) {
#if defined(HAVE_RGB)
    rgbWrite((uint8_t)(c[0] * k), (uint8_t)(c[1] * k), (uint8_t)(c[2] * k));
#elif defined(LED_BUILTIN)
    (void)c;
    digitalWrite(LED_BUILTIN, k > 0.5f ? HIGH : LOW);
#else
    (void)c; (void)k;
#endif
}

static void lightTask(void *) {
    for (;;) {
        uint32_t t = millis();
        switch (want) {
        case Light::Looking:                     // amber, half a second on, half off
            paint(AMBER, (t % 1000) < 500 ? 1.f : 0.f);
            break;
        case Light::Heard:                       // green, and still
            paint(GREEN, 1.f);
            break;
        case Light::Far: {                       // red, breathing over two seconds
#if defined(HAVE_RGB)
            float k = 0.5f + 0.5f * sinf((t % 2000) / 2000.f * 6.2831853f);
            paint(RED, 0.15f + 0.85f * k);
#else
            uint32_t m = t % 1000;               // one LED: a quick double blink, then dark
            paint(RED, (m < 120 || (m > 240 && m < 360)) ? 1.f : 0.f);
#endif
            break;
        }
        default:
            paint(AMBER, 0.f);
        }
        vTaskDelay(pdMS_TO_TICKS(40));
    }
}

void lightBegin() {
#if defined(HAVE_RGB)
    rgbBegin();
#elif defined(LED_BUILTIN)
    pinMode(LED_BUILTIN, OUTPUT);
#endif
    xTaskCreate(lightTask, "light", 2048, nullptr, 1, nullptr);
}

void lightSet(Light what) { want = what; }
Light lightGet() { return want; }
