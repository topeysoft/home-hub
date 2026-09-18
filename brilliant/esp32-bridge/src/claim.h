// Letting a new switch into the network this puck carries.
//
// The provisioner and the PB-GATT bearer know how to claim a switch; nothing
// could ask them to. This is the asking: three commands off the broker, run on
// the loop, with what they found published back.
//
//   mesh/bridge/<chip>/claim   <- survey
//                                 look around and say what is out there
//                              <- blink <uuid> <seconds>
//                                 make one of them announce itself to a person
//                              <- add <uuid> <unicast> [oob]
//                                 claim it; `oob` is the QR's 16-byte secret in
//                                 hex, and leaving it off is the codeless route
//
//   mesh/bridge/<chip>/nearby  -> JSON list from a survey
//   mesh/bridge/<chip>/claimed -> JSON result of an add, devkey included
//
// THE HUB ALLOCATES THE ADDRESS, not the puck. A puck knows what it can hear and
// nothing about what the house has already given out, so `add` carries the
// unicast to assign. That keeps the one piece of state that must not collide in
// the one place that can see all of it.
//
// AND IT CLAIMS ONTO THE NETWORK IT BRIDGES -- whatever keys this puck was given.
// A puck bridging the old panel's mesh would claim a switch INTO the panel's
// mesh, which is almost never what anybody wants; the puck to send this to is
// the one carrying the house's own network.
#pragma once
#include <Arduino.h>

// Called from the MQTT callback. Copies the command and returns: no radio work
// happens here, because doing any from inside a callback deadlocks the link the
// callback arrived on (main.cpp says the same about the BLE notify path).
bool claim_queue(const char *payload, size_t len);

// Called from loop(). Runs a queued command to completion -- a survey takes
// seconds and an add takes tens of them, during which this puck is not bridging.
void claim_tick();

// Is there a job waiting or running? The caller uses it to leave the proxy link
// alone rather than reconnecting underneath us.
bool claim_busy();

// `publish` takes a leaf under mesh/bridge/<chip>/ and a payload.
void claim_begin(const uint8_t netkey[16], uint32_t iv_index,
                 void (*publish)(const char *leaf, const char *payload));
