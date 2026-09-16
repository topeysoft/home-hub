// Bluetooth SIG Mesh crypto, ESP32 / mbedtls.
// Mirrors mesh.py exactly -- verified against the spec's section 8.1 vectors.
#pragma once
#include <Arduino.h>

void mesh_cmac(const uint8_t key[16], const uint8_t *msg, size_t len,
               uint8_t out[16]);
void mesh_s1(const uint8_t *msg, size_t len, uint8_t out[16]);
void mesh_k1(const uint8_t *n, size_t nlen, const uint8_t salt[16],
             const uint8_t *p, size_t plen, uint8_t out[16]);
void mesh_k2(const uint8_t netkey[16], uint8_t *nid, uint8_t enc[16],
             uint8_t priv[16]);
void mesh_k3(const uint8_t netkey[16], uint8_t out[8]);
uint8_t mesh_k4(const uint8_t appkey[16]);

// Network layer. Returns length written to out, or 0 on failure.
size_t mesh_net_encrypt(const uint8_t netkey[16], uint32_t iv, uint8_t ctl,
                        uint8_t ttl, uint32_t seq, uint16_t src, uint16_t dst,
                        const uint8_t *transport, size_t tlen, uint8_t nonce_type,
                        uint8_t *out);

struct MeshNetMsg {
    uint8_t ctl, ttl;
    uint32_t seq;
    uint16_t src, dst;
    uint8_t transport[32];
    size_t tlen;
};
bool mesh_net_decrypt(const uint8_t netkey[16], uint32_t iv, const uint8_t *pdu,
                      size_t len, MeshNetMsg *out);

// Upper transport (access messages).
size_t mesh_app_encrypt(const uint8_t key[16], bool is_devkey, uint32_t iv,
                        uint32_t seq, uint16_t src, uint16_t dst,
                        const uint8_t *access, size_t alen, uint8_t *out);
bool mesh_app_decrypt(const uint8_t key[16], bool is_devkey, uint32_t iv,
                      uint32_t seq, uint16_t src, uint16_t dst,
                      const uint8_t *ct, size_t clen, uint8_t tag_len,
                      uint8_t *out, size_t *olen);
bool mesh_selftest(Stream &s);

// ECDH P-256 for provisioning. Returns false on failure.
bool ecdh_generate(uint8_t pub_xy[64]);
bool ecdh_shared(const uint8_t peer_xy[64], uint8_t secret[32]);

// Decrypt the 25-byte provisioning data (session key + 13-byte nonce, 8-byte MIC).
bool mesh_prov_ccm_decrypt(const uint8_t key[16], const uint8_t nonce[13],
                           const uint8_t *ct, size_t ctlen, uint8_t out[25]);
