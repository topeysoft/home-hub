// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// Taking a new image from the hub, and going back to the old one if it does not work.
//
// The puck's design, on a strip (docs/strip.md, "Updates, the puck's way"; the puck's half is
// brilliant/esp32-bridge/src/fwupdate.h, and both follow docs/puck-updates.md). The hub OFFERS over
// the broker -- the authenticated channel, whose credentials it handed over at setup -- and names the
// image by its SHA-256, so only the bytes travel over plain HTTP from the hub's own port.
//
//   strip/<chip>/offer    <- <fw> <size> <sha256> <port> <path>    retained, from the hub; "" withdraws
//   strip/<chip>/fw       -> <fw>                                  retained, on every connect
//   strip/<chip>/update   -> {"state":..., "fw":..., "why":...}    not retained
//        state: fetching | refused | failed | installed | rolledback
//
// A new image boots unconfirmed and confirms itself only when the strip is doing its job -- an address,
// the broker, and a light driver that started. Otherwise it asks the bootloader to take it back, which
// needs CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE in the bootloader a cable put there. The highest version
// it has confirmed is a floor, and a version that came back twice is not taken again.
#pragma once

#include <string>

// The NEXT release, from the moment the last one is cut. A working-tree build is this plus
// "-d<minutes>" (tools/dev.sh strip), passed in as -DSTRIP_FW; see main/versions.h for the order.
#ifndef STRIP_FW
#define STRIP_FW "0.4.0"
#endif

namespace fwupdate {

using Say = void (*)(const char *leaf, const char *payload, int retain);

// Early in app_main, after NVS: notices a rollback, and whether this image is on trial.
void begin(Say say);

// From the MQTT task. Decides, and if the offer is taken, starts the download on a task of its own:
// it is minutes of work and must not sit on the MQTT task or the watched housekeeping loop.
void offer(const std::string &msg, const std::string &hub_host);

// From housekeeping, every pass. `whole` is the test above; `broker_up` lets owed news go out.
void tick(bool whole, bool broker_up);

}  // namespace fwupdate
