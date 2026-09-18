// The two primitives provisioning needs and the bridge did not have.
//
// mesh_crypto.* covers everything a proxy client does: CMAC, k1..k4, the
// network and upper-transport layers. None of that claims a switch. Claiming
// one is an ECDH key exchange and one CCM encryption of the 25 bytes that carry
// the network's keys, and both live here so mesh_crypto stays what it says it
// is -- the parts verified against the spec's section 8 vectors.
//
// The provisionee firmware (../../mesh-provisionee/) already had the ECDH, since
// it plays the other side of this same handshake. This is that code, moved
// rather than rewritten, with the direction reversed: the provisionee DECRYPTS
// the provisioning data, a provisioner ENCRYPTS it.
#pragma once
#include <Arduino.h>

// P-256. `prov_ecdh_generate` keeps the private half in a static keypair, so a
// second call abandons the first exchange -- one handshake at a time, which is
// all a puck in a hallway is ever doing.
bool prov_ecdh_generate(uint8_t pub_xy[64]);
bool prov_ecdh_shared(const uint8_t peer_xy[64], uint8_t secret[32]);

// CCM with a 13-byte nonce and an 8-byte MIC: `out` takes len + 8 bytes.
bool prov_ccm_encrypt(const uint8_t key[16], const uint8_t nonce[13],
                      const uint8_t *in, size_t len, uint8_t *out);
