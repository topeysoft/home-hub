// What the general puck asks of a module built in beside it, and the nothing it gets without one.
//
// The puck in this directory is the hub's own: it is set up over its cable, finds the hub, takes
// updates over the broker, listens for strips knocking and runs errands to them, and has a light.
// A module adds a kind of device the puck bridges on top of that. The one that exists carries a
// Bluetooth mesh of wall switches, kept in a repository of its own and built in with -DPUCK_MESH
// (platformio.ini, private/*.ini); a build without it
// is a whole puck that simply has nothing of that kind to bridge, and every call below is then a
// no-op that says so honestly: nothing to link, nothing busy, nothing to add to the status line.
//
// The calls are made from main.cpp only, on the Arduino loop task, in the order setup() and loop()
// make them. A module may use what src/puck.h offers and nothing else of main.cpp's.
#pragma once
#include <stddef.h>
#include <stdint.h>

// What the module leaves the radio free for on one pass of the loop. A module holding the scanner
// or the radio for itself (finding its link, letting a device in) says so, and the ear and the
// errands wait for the next pass rather than fighting it.
struct ModTick { bool ear; bool errand; };

#ifdef PUCK_MESH
#include <puck_module.h>   // the module's library: naming it is what makes PlatformIO build it
void mod_begin(uint32_t chip);          // setup(), before the cable can talk: restore what NVS keeps
void mod_start();                       // setup(), once the puck is configured: queues, saved lists
bool mod_mqtt(const char *topic, const uint8_t *payload, unsigned len, const char *msg);  // true: it was the module's
void mod_subscribe();                   // a fresh broker session: its topics, before the update offer's
void mod_announce();                    // ...and then everything it says retained, after the puck's own
ModTick mod_tick();                     // its share of one loop pass
bool mod_carries();                     // whether it has anything to bridge yet (keys, for the mesh)
bool mod_link_ok();                     // whether its link is up -- part of "the whole job"
bool mod_far();                         // whether it has looked and found nothing in reach
bool mod_busy();                        // in the middle of something an update must not interrupt
void mod_drop(const char *why);         // let go of the radio: an update is about to take it
size_t mod_status(char *out, size_t n); // its fields on the cable's status line, each " key=value"
const char *mod_caps();                 // its words on the retained caps topic, " mesh"
const char *mod_model();                // what the puck is, on its device in Home Assistant
#else
inline void mod_begin(uint32_t) {}
inline void mod_start() {}
inline bool mod_mqtt(const char *, const uint8_t *, unsigned, const char *) { return false; }
inline void mod_subscribe() {}
inline void mod_announce() {}
inline ModTick mod_tick() { return {true, true}; }
inline bool mod_carries() { return false; }
inline bool mod_link_ok() { return true; }
inline bool mod_far() { return false; }
inline bool mod_busy() { return false; }
inline void mod_drop(const char *) {}
inline size_t mod_status(char *out, size_t n) { if (n) out[0] = 0; return 0; }
inline const char *mod_caps() { return ""; }
inline const char *mod_model() { return "Bridge"; }
#endif
