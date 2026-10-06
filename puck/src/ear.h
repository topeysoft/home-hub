// Listening for a strip that is knocking, all day, for a hub that cannot hear it.
//
// A hub goes where the Ethernet is and a strip goes where the light is wanted, and Bluetooth does not
// cross that (docs/strip.md item 15). So every puck is an ear: a PASSIVE scan, ten milliseconds of
// every hundred, left running while the mesh link is up, reporting each commissionable Matter advert
// it hears to the hub, which ranks them (brain/hub/ears.py). Measured on 23 September: about 6% of
// the mesh's traffic, and a knocking strip heard twice a second (docs/strip.md item 42). Passive,
// because an active look like the hub's own leaves the mesh deaf for as long as it runs.
//
//   mesh/bridge/<chip>/heard  -> {"addr": "e7:38:84:e2:89:0a", "type": "random", "rssi": -37,
//                                 "svc": "00000ff1ff008000"}           not retained
//
// THE PUCK DOES NOT DECODE WHAT IT HEARD. `svc` is the raw 0xFFF6 service data as hex, and the hub
// reads it with the one decoder it already trusts: two decoders that disagree is how a strip gets
// called somebody else's. The address TYPE goes with the address because a strip's is random, and an
// address opened as the wrong type is six right bytes nobody answers.
//
// ONE SCANNER, SEVERAL USERS. Finding the proxy and claiming a switch both run blocking active scans
// on the same NimBLE scanner and read back the results it keeps. So the ear gives the scanner back
// exactly as setup left it, every time anything else needs it: ear_tick(false) before any of them.
#pragma once
#include <Arduino.h>

// `publish` takes a leaf under mesh/bridge/<chip>/ and a payload.
void ear_begin(void (*publish)(const char *leaf, const char *payload));

// From loop(), every pass. `may_listen` is true only while the mesh link is up and nothing else wants
// the scanner; the ear starts, keeps going, or stops accordingly, and says what it has heard.
void ear_tick(bool may_listen);
