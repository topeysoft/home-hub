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

// OPEN THE DOOR. Call after esp_matter::start(), and only on a strip nobody has taken yet.
//
// THE PROOF OF POSSESSION IS A PRESS (design/door/PressIt.dc.html, design/strip/Press.dc.html). The
// door opens on a password that is fixed and public, so anything in radio range can start a session
// and get exactly as far as the Wi-Fi question -- where THIS FILE refuses it until press() has been
// called. The gate is on the strip; the hub asks and waits and cannot let itself in.
//
// What that buys is possession rather than a keyspace: nothing printed, nothing derived from the
// chip, nothing to count. What it does not buy is protection from somebody in radio range at the
// exact moment of the press, which is the trade every push-button pairing makes and is written down
// in docs/strip.md rather than left implied.
esp_err_t open();

// SOMEBODY TOUCHED THE STRIP. Opens the gate for two minutes. Returns true if that mattered -- the
// door was open and waiting -- so the caller knows whether to answer the press on the light.
bool press();

// THE RUNG BELOW (design/strip/ReachRhythm.dc.html), for a strip already mounted where nobody can
// reach the controller. The hub asks for it on the `press` endpoint; the door then shuts and opens
// again with an SRP6a verifier made from four freshly minted counts, because a verifier cannot be
// swapped inside a live session. Call this every pass of a task that is NOT the manager's own --
// stopping the manager from inside its own handler is not a thing -- and it does nothing until asked.
void tend_the_door();

// Called when the hub hands over where our broker is, on the `hub` endpoint, inside the same
// session that carried the Wi-Fi. Each line is `key=value`; the keys are the ones find_hub() reads.
// Return false to refuse, which tells the hub it asked for something this strip does not keep.
using HubDetails = bool (*)(const char *key, const char *value);
void on_hub_details(HubDetails fn);

// True once a session through our door has completed, which is remembered across reboots. A strip
// adopted this way never joins a Matter fabric, so the fabric table cannot answer "has anybody taken
// this strip?" and this is the other half of that question.
using Taken = void (*)(bool);
void on_taken(Taken fn);

// The four counts, 1..6 each, for whoever is drawing them. ZERO UNLESS THE RUNG BELOW IS IN USE,
// which is also how a caller tells the two apart: on the press rung there is nothing to show and the
// strip is simply lit.
const uint8_t *rhythm();

// CHIP stopped advertising. If the strip is still untaken and the two days are not up, the window
// is reopened; otherwise this returns false and the knocking is over for this power cycle.
bool keep_knocking();

// Put the advertisement back to its fast interval if CHIP has let it fall to slow. Safe to call
// often and does nothing once the strip has been taken; see prov.cpp for why it is on a timer.
void stay_loud();

// Ask every live BLE link for a slower interval and a longer supervision timeout. Called the moment
// CHIP says a connection came up, because the link dies during service discovery -- before any
// characteristic of ours is touched -- and a request made on first write comes far too late.
void be_patient_with_everyone();

// CHIP saw the BLE link close. Whatever session was on it is over.
void disconnected();

// True from the moment credentials arrive until the manager has finished with them. The light is
// the manager's while this is true.
bool busy();

}  // namespace prov
