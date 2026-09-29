// Taking a new image from the hub, and going back to the old one if it does not work.
//
// Not update.h: on a case-insensitive disk that name hides the core's <Update.h>, which this uses.
//
// A puck is the piece of this system most likely to be behind a sofa and least likely to be near a
// laptop, so a fix has to reach it where it is (docs/puck-updates.md). The hub OFFERS; the puck
// decides. The offer arrives on the authenticated channel -- the broker, whose credentials the hub
// wrote at adoption -- and names the image by its SHA-256, so only the bytes themselves travel over
// plain HTTP from the hub's own port, and something impersonating the hub on the LAN needs those
// credentials before it can name a hash this puck will accept.
//
//   mesh/bridge/<chip>/offer    <- <fw> <size> <sha256> <port> <path>    retained, from the hub
//                                  empty payload: the hub withdrew it
//   mesh/bridge/<chip>/fw       -> <fw>                                  retained, on every connect
//   mesh/bridge/<chip>/update   -> {"state":..., "fw":..., "why":...}    not retained
//        state: fetching | refused | failed | installed | rolledback
//
// The image is fetched from the address the broker last answered on, which is the hub. Nothing here
// resolves a name or follows a redirect.
//
// COMING BACK IS THE WHOLE FEATURE. A new image boots unconfirmed, and confirms itself only when the
// puck is doing its whole job: on the Wi-Fi, on the broker, and linked to a switch. If that does not
// happen in time it asks the bootloader to take it back, and the old image boots, notices, and says
// so. "It booted" is not the test -- a puck that boots and bridges nothing is exactly the one that
// strands somebody.
//
// OLDER IS NOT AN UPGRADE. The highest version this puck has ever confirmed is kept in NVS and nothing
// below it is taken, so a genuine old image with its old bug in it cannot be walked back onto a puck.
// A deliberate downgrade is a cable job. And an image that has come back twice is not tried again:
// that is a puck telling the hub something, not a puck having bad luck.
#pragma once
#include <Arduino.h>

// Early in setup(), before anything can reboot: notices a rollback and remembers what to say about it.
void update_begin(void (*publish)(const char *leaf, const char *payload, bool retain));

// From the MQTT callback: copies the offer and returns. Nothing is fetched here.
void update_offer(const uint8_t *payload, size_t len);

// From loop(), every pass. `whole` is the test above -- Wi-Fi, broker and a switch -- and is what lets
// a new image confirm itself. Also says anything owed from the boot, once the broker is up.
void update_tick(bool whole, bool brokerUp);

// Is there an accepted offer waiting for the radio? main.cpp drops the mesh link, then calls
// update_run(), which fetches, writes and restarts -- or says why not and returns.
bool update_ready();
void update_run(const char *hubIp);

// This image is on trial: it has not yet confirmed itself.
bool update_on_trial();
