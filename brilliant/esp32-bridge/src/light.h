// The one light on the puck, and the three things it can say.
//
// Setting a bridge up ends with a walk: unplug it, find it a socket near a
// switch. The wall panel cannot follow and the phone is in the other hand, so
// the thing that answers "is here good?" is the object itself
// (design/puck/Placing.dc.html). Nobody is taught the colours; you stand there
// until it goes green.
//
//   LOOKING   blinking amber   no proxy link yet -- still looking for a switch,
//                              or still waiting to be told its config
//   HEARD     steady green     linked, and a switch has answered: leave it here
//   FAR       breathing red    it has looked and looked and found nothing in
//                              range -- try a socket nearer a switch
//
// On a board with a colour LED (an S3 devkit's WS2812) that is exactly what is
// shown. On a board with one plain LED the three become rhythms -- a slow
// blink, steady on, a quick double blink -- which is worse, and is why the
// shipped puck is the colour one. Either way the light runs on its own task:
// the main loop stalls for seconds at a time and a blink that stutters reads
// as a fault.
#pragma once

#include <Arduino.h>

enum class Light : uint8_t { Off, Looking, Heard, Far };

void lightBegin();
void lightSet(Light what);
Light lightGet();
