// Running an errand for a hub that cannot hear the thing it wants to talk to.
//
// A hub goes where the Ethernet is and a strip goes where the light is wanted (docs/strip.md item
// 15). So the hub hands the conversation to a puck that can hear the strip -- the one its ears table
// says is loudest (brain/hub/ears.py) -- and the puck is the corridor: it opens a GATT link, writes
// what it is given where it is told, and hands back what came out. THE SESSION STAYS END TO END: the
// SRP6a session is opened at the hub and closed at the strip, the bytes are ciphertext from the second
// message on, and nothing here could read them if it wanted to (items 38 and 39). The press gate stays
// on the strip, where item 23 put it.
//
// THE FORMAT IS TEXT, because the hub has no other way in. The brain reaches MQTT only through Home
// Assistant -- the `mqtt.publish` service out and the websocket's `mqtt/subscribe` in -- and both carry
// strings, so the opaque bytes travel as base64. Space-separated words, the way `claim` already is.
//
//   mesh/bridge/<chip>/errand/ask   <- open <id> <addr> <random|public>
//                                   <- send <id> <n> <ep> <base64>
//                                   <- close <id>
//   mesh/bridge/<chip>/errand/tell  -> open <id> ring|quiet      linked; whether the strip can ring
//                                   -> ok <id> <n> <base64>      what came back for send n
//                                   -> fail <id> <n|-> <why>     busy, connect, gone, write, ...
//                                   -> ring <id>                  the strip was pressed: ask it now
//                                   -> closed <id> <why>          asked, idle, lost
//
// `id` is the hub's, one per errand; this puck holds one errand at a time, and anything carrying
// another id is refused rather than written to the wrong strip. `ep` is protocomm's sixteen-bit
// endpoint id (0xFF51 prov-session ... 0xFF55 press), not an index into a list that could drift.
// Nothing is retained, ever (item 33). An errand nobody sends to for IDLE seconds is closed, because a
// hub that went away must not leave a second link holding the radio.
//
// WHILE AN ERRAND HOLDS A LINK, two other rules hold and main.cpp owns both: the ear stands aside
// (NimBLE will not connect while scanning), and the mesh's own polls are held back when the buffer
// pool runs low, because otherwise they queue up on the shared radio and the strip's next write fails
// with rc=6 -- which reads as a dropped link and is not one (item 40).
#pragma once
#include <Arduino.h>

// From the MQTT callback: copies the command and returns. The radio work happens in errand_tick().
bool errand_queue(const uint8_t *payload, size_t len);

// From loop(), every pass while the mesh link is up.
void errand_tick();

// Is an errand using the radio -- connecting, or holding a link? The ear and the mesh polls ask.
bool errand_busy();
bool errand_holds_link();

// `publish` takes a leaf under mesh/bridge/<chip>/ and a payload.
void errand_begin(void (*publish)(const char *leaf, const char *payload));
