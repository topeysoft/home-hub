// The one light on the puck: three things it can say, and what it does once it
// has said them.
//
// Setting a bridge up ends with a walk: unplug it, find it a socket near a
// switch. The wall panel cannot follow and the phone is in the other hand, so
// the thing that answers "is here good?" is the object itself
// (design/puck/Placing.dc.html). Nobody is taught the colors; you stand there
// until it goes green.
//
//   LOOKING   blinking amber   no proxy link yet -- still looking for a switch,
//                              or still waiting to be told its config
//   HEARD     steady green     linked, and a switch has answered: leave it here
//   FAR       breathing red    it has looked and looked and found nothing in
//                              range -- try a socket nearer a switch
//   NIGHT     warm and still   settled, well, and the household asked for it:
//                              the nightlight (docs/puck-light.md)
//
// The first three answer "is here good?", and that question is over about a
// minute after the puck is plugged in. NIGHT is what the light does for the
// other fourteen hours, because the shipped puck is an object in a living
// space rather than a devkit on a shelf. It is opt-in, it is off by default,
// and it NEVER outranks the first three: the order is decided in one place,
// lightRefresh() in main.cpp, and a fault takes the light straight back.
// That is the point of it -- green is a promise about the mesh AND the
// broker, so a glow that outlives the bridge going down is furniture that
// lies. A nightlight that has turned amber is a fault report somebody reads
// at 2am on their way past. design/puck/Nightlight.dc.html is the board.
//
// On a board with a color LED (an S3 devkit's WS2812) that is exactly what is
// shown. On a board with one plain LED the three become rhythms -- a slow
// blink, steady on, a quick double blink -- which is worse, and is why the
// shipped puck is the color one -- and NIGHT is simply dark on such a board,
// because one indicator LED at full brightness is not a nightlight and a
// blinking one is a lie. Either way the light runs on its own task:
// the main loop stalls for seconds at a time and a blink that stutters reads
// as a fault.
#pragma once

#include <Arduino.h>

enum class Light : uint8_t { Off, Looking, Heard, Far, Night };

void lightBegin();
void lightSet(Light what);
Light lightGet();

// How bright the nightlight is, 0-255, scaling WARM in light.cpp. Set from cfg at boot and whenever
// the household changes it. Only NIGHT uses it; the three states are an instrument and have one
// brightness, which is the one they can be read at.
void lightNightLevel(uint8_t level);
