// What the puck's light says, held on a laptop: src/lightrule.h, the rule as it runs on the puck.
//
//   clang++ -std=c++17 -I native -o /tmp/lt native/test_light_native.cpp && /tmp/lt
//
// Two pucks, one rule. A puck that bridges wall switches keeps the light it shipped with
// (design/puck/Placing.dc.html): green needs the switches AND the hub, far is "looked, found none".
// A puck with nothing to bridge has the light chosen on 5 October 2026 (design/bridge-light/, A):
// green means it reached the hub, amber is finding it, red is no Wi-Fi where it stands.
#include <stdio.h>
#include "../src/lightrule.h"

static int fails = 0;
static const char *name(Light l) {
    switch (l) { case Light::Off: return "off"; case Light::Looking: return "looking"; case Light::Heard: return "heard";
                 case Light::Far: return "far"; case Light::Night: return "night"; }
    return "?";
}
static void is(const char *what, Light got, Light want) {
    bool ok = got == want;
    printf("%-62s %s\n", what, ok ? "PASS" : "FAIL");
    if (!ok) { fails++; printf("   got %s, want %s\n", name(got), name(want)); }
}

int main() {
    // ---- a puck with nothing to bridge: A ----
    LightIn plain = {};
    is("no Wi-Fi yet, not for long: finding the hub", lightFor(plain), Light::Looking);
    plain.wifiLongDown = true;
    is("no Wi-Fi here for half a minute: no Wi-Fi here", lightFor(plain), Light::Far);
    plain.wifiLongDown = false;
    is("Wi-Fi but no hub yet: finding the hub", lightFor(plain), Light::Looking);
    plain.broker = true;
    is("it reached the hub: leave it here", lightFor(plain), Light::Heard);
    plain.linkUp = false; plain.linkFar = true;
    is("...and a module's link means nothing when there is no module", lightFor(plain), Light::Heard);
    plain.settled = true;
    is("placed, no nightlight asked for: dark", lightFor(plain), Light::Off);
    plain.night = true;
    is("placed, nightlight asked for: the nightlight", lightFor(plain), Light::Night);
    plain.broker = false;
    is("a placed nightlight that loses the hub is the instrument again", lightFor(plain), Light::Looking);

    // ---- a puck that bridges wall switches: exactly as it shipped ----
    LightIn mesh = {};
    mesh.carries = true; mesh.broker = true;
    is("switches not heard yet, hub up: looking for your switches", lightFor(mesh), Light::Looking);
    mesh.linkFar = true;
    is("looked three times, no switch in reach: too far", lightFor(mesh), Light::Far);
    mesh.linkFar = false; mesh.wifiLongDown = true; mesh.broker = false;
    is("no Wi-Fi does not make a switch puck say far: that is the mesh's word", lightFor(mesh), Light::Looking);
    mesh.wifiLongDown = false; mesh.linkUp = true;
    is("switches heard but no hub: still looking (green needs both)", lightFor(mesh), Light::Looking);
    mesh.broker = true;
    is("switches heard and the hub: leave it here", lightFor(mesh), Light::Heard);
    mesh.settled = true; mesh.night = true;
    is("placed and asked for: the nightlight", lightFor(mesh), Light::Night);

    printf(fails ? "\n%d FAILED\n" : "\nall good\n", fails);
    return fails ? 1 : 0;
}
