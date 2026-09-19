#include "light.h"

#include <math.h>

// Which LED this board has. A color one (WS2812) on the pins the S3 devkits put it on -- GPIO48 on
// the v1.0 board and on the clones, GPIO38 on v1.1 -- and the shipped image cannot know which it
// landed on, so it drives both; each is a free pin on the other revision. -DBRIDGE_RGB_PIN=n names a
// single other pin. A board with none of that gets the plain LED_BUILTIN; nothing at all stays silent.
//
// Each pin gets its own RMT channel through the core's rmt API -- the same thing neopixelWrite()
// does, which is tied to one static channel and so one pin. The channels are written one after the
// other rather than together; see rgbWrite() for what firing both at once did to a board that has
// the two pins bridged.
//
// A hand-timed bit-bang was tried first and abandoned: its timing was a guess, and a guess is the
// wrong thing to stand between "the LED is dark" and "the board's RGB solder pad is not bridged",
// which is what the dark LED actually was.
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
static int nDrive = NPINS;

// Are the two candidate pins the same wire?
//
// Driving both is how one image serves a devkit with its LED on GPIO48 and one with it on GPIO38.
// On a board that bridges them it is a disaster: two frames down one wire, and the LED spends its
// life reading whichever arrived last through the interference of the other. That is what made
// this puck white, then pale, then flicker -- three symptoms, one cause, and it took a build with
// the pin pinned by hand to see it.
//
// So ask the board instead of guessing. Hold the first pin low and read the second with its pull-up
// on: an unconnected pin reads high, a bridged one is dragged low. If they are bridged, only the
// first gets driven from then on. A board with the LED on just one pin is unaffected either way,
// which is the point -- nothing has to be configured, and no revision is left with a dark light.
static void detectBridge() {
    if (NPINS < 2) return;
    pinMode(RGB_PINS[0], OUTPUT);
    digitalWrite(RGB_PINS[0], LOW);
    pinMode(RGB_PINS[1], INPUT_PULLUP);
    delayMicroseconds(200);                     // let the pull-up win if nothing is fighting it
    bool bridged = digitalRead(RGB_PINS[1]) == LOW;
    pinMode(RGB_PINS[1], INPUT);                // leave it alone again
    if (bridged) nDrive = 1;
    log_i("[light] pins %d/%d %s", RGB_PINS[0], RGB_PINS[1], bridged ? "bridged: driving one" : "separate: driving both");
}

static void rgbBegin() {
    detectBridge();
    for (int i = 0; i < nDrive; i++) {
        chan[i] = rmtInit(RGB_PINS[i], RMT_TX_MODE, RMT_MEM_64);
        if (chan[i]) rmtSetTick(chan[i], 100);   // 100 ns per tick: the numbers below are the WS2812's own
    }
}
// How long the LED needs to see a quiet line before it takes the frame it just got. The WS2812B
// datasheet says 50 us; the V5 revision moved it to 280. This is the cheap end of a busy-wait --
// two pins at 30 us of frame plus this is under a millisecond, once every 40.
#define LATCH_US 300

// One frame per pin, in turn, each given time to latch -- not both channels fired at once.
//
// Driving both pins is how the image copes with not knowing which revision it landed on, but on a
// board that ties them together (a solder bridge, a jumper, or a clone that simply routes both to
// the LED) two channels started a few microseconds apart put two push-pull outputs on one wire.
// The high pulses merge, a 0 bit's 0.4 us stretches past the threshold that separates it from a 1,
// and the LED reads ones all the way across: full white, with the real color surfacing only on
// the frames where the skew happens to line up. That is the fault this replaces.
//
// Serialized, a one-LED board sees exactly what it saw before, and a board that bridges the pins
// sees the same frame written twice with a gap -- which is just the same color, latched twice.
// A WS2812 latches what it is given and holds it until the next frame, so a color that has not
// changed does not need sending again -- and on a board whose data line is marginal (3.3 V logic
// into an LED powered from 5 V wants 3.5 V to read a 1) every frame sent is another chance to be
// misread. Rewriting a steady color 25 times a second turns one dice roll into 25 per second,
// which is what made the steady green flicker between green and a paler, whiter green. Heard is
// now a single write that stands; Looking is two a second; only the breathing red still writes
// every frame, and that one is genuinely changing.
//
// ...but "never write again" is too far. A frame that is misread then stands for ever, because the
// code believes it already sent the right color -- which is how a stuck pale green appeared after
// a spell out of range, where the radio scans six seconds in every eight and the supply is at its
// noisiest. So an unchanged color is still resent, just slowly: often enough that a bad latch is
// measured in seconds rather than being permanent, rarely enough that it cannot read as flicker.
#define REFRESH_MS 2000

static uint8_t lastRGB[3];
static uint32_t lastWriteAt = 0;
static bool haveLast = false;

static void rgbWrite(uint8_t r, uint8_t g, uint8_t b) {
    bool same = haveLast && lastRGB[0] == r && lastRGB[1] == g && lastRGB[2] == b;
    if (same && (millis() - lastWriteAt) < REFRESH_MS) return;
    lastRGB[0] = r; lastRGB[1] = g; lastRGB[2] = b;
    lastWriteAt = millis();
    haveLast = true;

    rmt_data_t bits[24];
    uint32_t grb = ((uint32_t)g << 16) | ((uint32_t)r << 8) | b;
    for (int i = 0; i < 24; i++) {
        bool one = grb & (1UL << (23 - i));
        // These are the core's own neopixelWrite() numbers, and they stay that way. Widening them
        // to 9/3 to buy margin was tried and reverted: it assumed a WS2812B, whose T1H tops out at
        // 0.95 us, but the part on these clone boards may be an SK6812, which tops out nearer 0.75
        // -- so the "wider margin" pushed 1 bits out of spec and made a steady green oscillate.
        // 8/4 is the one encoding both parts accept. Do not tune this without a scope on the pin.
        bits[i].level0 = 1; bits[i].duration0 = one ? 8 : 4;   // 0.8 us / 0.4 us high
        bits[i].level1 = 0; bits[i].duration1 = one ? 4 : 8;   // 0.4 us / 0.8 us low
    }
    for (int i = 0; i < nDrive; i++) {
        if (!chan[i]) continue;
        rmtWriteBlocking(chan[i], bits, 24);   // returns with the frame already out on the wire
        delayMicroseconds(LATCH_US);
    }
}
#endif

static volatile Light want = Light::Off;

// One breath of the Far state, in milliseconds. The fade is recomputed 50 times inside it whatever
// this is set to, so changing it changes the speed and the write rate together, not the smoothness.
#ifndef BREATH_MS
#define BREATH_MS 4000
#endif

// The three colors, as an emitter -- NOT as the panel draws them.
//
// These started as the panel's own tokens (--lamp #e9b872, --live #6fcf97, --danger #e08a8a),
// scaled down. That was a category error and it is why the light looked washed out. Those tokens
// are pastel tints, picked to stay legible as ink on a dark surface, and on a screen they read as
// amber, green and red because the dark field around them hands the eye a white reference. A bare
// LED hands it nothing: the eye normalizes to the brightest thing in the room, which is the LED,
// so a pastel emitter reads as white. #e08a8a is a pink, and at arm's length it looked like one.
//
// So the off-channels go to (near) zero and the peak stays exactly where it was -- 58, 52, 56 --
// because the brightness was never the problem, only the saturation. A little blue is left in the
// green because a WS2812's raw green is yellowish; amber and red want none at all.
static const uint8_t AMBER[3] = {58, 20, 0};
static const uint8_t GREEN[3] = {0, 52, 10};
static const uint8_t RED[3] = {56, 0, 0};

// And the one color that breaks the rule above, on purpose.
//
// The three constants are saturated because they are SIGNALS: the eye normalises to the brightest
// thing in the room, so an emitter with its off-channels lit reads as white and says nothing. The
// nightlight is not a signal. It is lighting a floor, and warm white is exactly what it should be --
// so here the off-channels are wanted, and "reads as white" is the goal rather than the failure.
//
// Roughly 2000 K, which is the warm end of a domestic bulb: no cold light in a corridor at 3am, and
// far enough from AMBER's hue and behaviour (this one never blinks) that the two cannot be confused.
// The peak is deliberately higher than the instrument's 58 -- it is meant to be seen by, not read --
// and lightNightLevel() scales it, so the household's brightness is the only thing that moves.
static const uint8_t WARM[3] = {255, 140, 45};

// 0-255, scaling WARM. The default is a glow to find a doorway by, not a lamp; the house changes it.
static volatile uint8_t nightK = 110;

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
        Light w = want;
#ifdef LIGHT_SELFTEST
        // -DLIGHT_SELFTEST: for the first minute after a reset, walk the three states regardless
        // of what the radio is doing -- twenty seconds each, then hand back to the real state. The
        // Far state needs three empty scans to reach honestly, which you cannot do on a desk next
        // to a live switch, and a light nobody can make light up is a light nobody has checked.
        if (t < 60000) w = (t < 20000) ? Light::Looking : (t < 40000) ? Light::Heard : Light::Far;
#endif
        // How long one breath takes, and how often the fade is recomputed inside it. The two move
        // together on purpose: the step you can see is amplitude x (2*pi/period) x interval, so
        // doubling the period and halving the rate looks identically smooth -- 50 steps a breath
        // either way -- while halving the number of frames put on a wire that misreads some.
        uint32_t breathMs = BREATH_MS, breathStep = BREATH_MS / 50;
#ifdef LIGHT_BREATH_SWEEP
        // Three speeds, twenty seconds each, for picking one by eye on the real LED.
        if (t < 60000) {
            w = Light::Far;
            breathMs = (t < 20000) ? 2000 : (t < 40000) ? 4000 : 6000;
            breathStep = breathMs / 50;
        }
#endif
        switch (w) {
        case Light::Looking:                     // amber, half a second on, half off
            paint(AMBER, (t % 1000) < 500 ? 1.f : 0.f);
            break;
        case Light::Heard:                       // green, and still
            paint(GREEN, 1.f);
            break;
        case Light::Night:                       // warm, still, and only ever on a color LED
#if defined(HAVE_RGB)
            // Static between transitions: rgbWrite() drops the unchanged frames, so this costs one
            // write every REFRESH_MS all night. Anything that FADES writes every frame and walks
            // straight back into the misread-frame fault -- see the comment on rgbWrite(). A sunset
            // ramp waits for a board whose data line is actually driven (docs/puck-light.md).
            paint(WARM, nightK / 255.f);
#else
            paint(WARM, 0.f);                    // one plain LED cannot be a nightlight; stay dark
#endif
            break;
        case Light::Far: {                       // red, breathing
#if defined(HAVE_RGB)
            // Time is quantised to the step before the fade is computed, so every frame inside a
            // step produces byte-identical color and rgbWrite() drops it. That is what turns the
            // rate down -- the task still runs at 40 ms, it just stops resending what it just sent.
            uint32_t tq = (t / breathStep) * breathStep;
            float k = 0.5f + 0.5f * sinf((tq % breathMs) / (float)breathMs * 6.2831853f);
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
void lightNightLevel(uint8_t level) { nightK = level; }
Light lightGet() { return want; }
