// What the light says, as a rule with no hardware in it, so it can be held by a test on a laptop
// (native/test_light_native.cpp) as well as run on the puck.
//
// The light answers one question -- "is here good?" -- for somebody standing at a socket with the
// puck in their hand, and then gets out of the way. Four rows, strictly ordered (docs/puck-light.md):
//
//   1  anything wrong            the instrument. Outranks everything under it
//   2  well, not yet placed      green, until somebody taps "Leave it here"
//   3  placed, and asked for it  the nightlight
//   4  placed, and did not       dark
//
// What "well" means depends on what the puck carries. A puck bridging wall switches is well when it
// can hear them AND reach the hub, and it is far when it has looked for them and found none
// (design/puck/Placing.dc.html). A puck with nothing of that kind is well when it reached the hub,
// and far when there has been no Wi-Fi where it stands for half a minute (design/bridge-light/, A,
// chosen 5 October 2026).
#pragma once
#include "light.h"

struct LightIn {
    bool broker;          // on the broker, which is the hub answering
    bool carries;         // a module with something to bridge (src/module.h, mod_carries)
    bool linkUp;          // ...and its link is up
    bool linkFar;         // ...and it has looked and found nothing in reach
    bool wifiLongDown;    // no Wi-Fi here for half a minute
    bool settled;         // somebody tapped "Leave it here"
    bool night;           // the nightlight is asked for
};

inline Light lightFor(const LightIn &in) {
    bool well = in.broker && (!in.carries || in.linkUp);
    if (!well) return (in.carries ? in.linkFar : in.wifiLongDown) ? Light::Far : Light::Looking;
    if (!in.settled) return Light::Heard;
    if (in.night) return Light::Night;
    return Light::Off;
}
