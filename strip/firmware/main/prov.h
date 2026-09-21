// SPDX-FileCopyrightText: 2026 Temitope Adeyeri
// SPDX-License-Identifier: AGPL-3.0-or-later
//
// OUR OWN DOOR ONTO THE STRIP, sharing the radio with Matter's.
//
// A strip has two ways in and the household is never asked which (design/strip/Both.dc.html). Matter's
// is CHIPoBLE and it is somebody else's code. Ours is protocomm with SRP6a, and the reason it is
// protocomm rather than a handshake of our own is that the first firmware DID write a handshake of its
// own and put a household's Wi-Fi password on an unauthenticated link.
//
// What could not be reused is protocomm's BLE transport: protocomm_nimble stands up its own NimBLE host
// -- nimble_port_init, its own gatt table, its own advertising -- and CHIP has already done all three.
// So this file is the transport, and only the transport. Everything above it (the endpoints, their
// protobufs, SRP6a, applying the credentials) is network_provisioning's, unchanged, which is also what
// lets a client that already exists drive it. docs/strip.md item 13 has the reasoning.
#pragma once

#include <esp_err.h>
#include <network_provisioning/manager.h>

namespace prov {

// Puts our characteristics into CHIP's GATT table. MUST be called before esp_matter::start():
// ConfigureExtraServices refuses once the stack is up, and there is no second chance at it.
// It also puts our service UUID in the scan response, because Matter's own payload has already
// filled the advertisement and 31 bytes will not hold both (docs/strip.md item 12).
// `name` rides in the scan response beside the UUID and may be at most 11 characters: the UUID takes
// 18 of the 31 bytes and a name costs two plus its length. It exists for one reason, which is that
// Espressif's own app finds devices by name prefix and shows nothing without one.
esp_err_t reserve(const char *name);

// The scheme to hand to network_prov_mgr_init(). Valid once reserve() has succeeded.
const network_prov_scheme_t &scheme();

// OPEN THE DOOR. Mints the rhythm, makes the SRP6a verifier from it, and starts the manager. Call
// after esp_matter::start(), and only on a strip nobody has taken yet.
//
// THE RHYTHM IS THE PROOF OF POSSESSION (design/strip/PopLight.dc.html). Four groups of one to six
// flashes, minted fresh each time the strip is plugged in and shown on the strip itself; the person
// taps what they count and that is the SRP6a password. Nothing printed, nothing derived from the chip.
// Rhythm rather than color because "Is it red?" has not been asked yet, so a color cannot be trusted
// and a count can. It is small until SRP6a is under it: no offline attack, one wrong guess ends the
// session, and the next power cycle mints a new one.
esp_err_t open();

// Called when the hub hands over where our broker is, on the `hub` endpoint, inside the same
// session that carried the Wi-Fi. Each line is `key=value`; the keys are the ones find_hub() reads.
// Return false to refuse, which tells the hub it asked for something this strip does not keep.
using HubDetails = bool (*)(const char *key, const char *value);
void on_hub_details(HubDetails fn);

// The four counts, 1..6 each, for whoever is drawing them. Zero until open() has run.
const uint8_t *rhythm();

// CHIP saw the BLE link close. Whatever session was on it is over.
void disconnected();

// True from the moment credentials arrive until the manager has finished with them. The light is
// the manager's while this is true.
bool busy();

}  // namespace prov
