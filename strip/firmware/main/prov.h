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
esp_err_t reserve();

// The scheme to hand to network_prov_mgr_init(). Valid once reserve() has succeeded.
const network_prov_scheme_t &scheme();

}  // namespace prov
