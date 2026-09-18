#include "prov_crypto.h"
#include <string.h>
#include "mbedtls/ccm.h"
#include "mbedtls/ecdh.h"
#include "mbedtls/ecp.h"
#include "mbedtls/entropy.h"
#include "mbedtls/ctr_drbg.h"

static mbedtls_ecp_keypair g_kp;
static bool g_kp_ready = false;

bool prov_ecdh_generate(uint8_t pub_xy[64]) {
    mbedtls_entropy_context ent;
    mbedtls_ctr_drbg_context drbg;
    mbedtls_entropy_init(&ent);
    mbedtls_ctr_drbg_init(&drbg);
    bool ok = false;
    const char *pers = "mesh-prov";
    do {
        if (mbedtls_ctr_drbg_seed(&drbg, mbedtls_entropy_func, &ent,
                (const unsigned char *)pers, strlen(pers)) != 0) break;
        if (g_kp_ready) { mbedtls_ecp_keypair_free(&g_kp); g_kp_ready = false; }
        mbedtls_ecp_keypair_init(&g_kp);
        if (mbedtls_ecp_group_load(&g_kp.grp, MBEDTLS_ECP_DP_SECP256R1) != 0) break;
        if (mbedtls_ecp_gen_keypair(&g_kp.grp, &g_kp.d, &g_kp.Q,
                mbedtls_ctr_drbg_random, &drbg) != 0) break;
        // the wire format is the bare affine coordinates, X then Y, big-endian --
        // no 0x04 point prefix, which is what a reader of the spec expects and
        // what an OpenSSL habit would put there.
        if (mbedtls_mpi_write_binary(&g_kp.Q.X, pub_xy, 32) != 0) break;
        if (mbedtls_mpi_write_binary(&g_kp.Q.Y, pub_xy + 32, 32) != 0) break;
        ok = true;
    } while (0);
    g_kp_ready = ok;
    mbedtls_ctr_drbg_free(&drbg);
    mbedtls_entropy_free(&ent);
    return ok;
}

bool prov_ecdh_shared(const uint8_t peer_xy[64], uint8_t secret[32]) {
    if (!g_kp_ready) return false;
    mbedtls_ecp_point peer;
    mbedtls_mpi z;
    mbedtls_ecp_point_init(&peer);
    mbedtls_mpi_init(&z);
    bool ok = false;
    do {
        if (mbedtls_mpi_read_binary(&peer.X, peer_xy, 32) != 0) break;
        if (mbedtls_mpi_read_binary(&peer.Y, peer_xy + 32, 32) != 0) break;
        if (mbedtls_mpi_lset(&peer.Z, 1) != 0) break;
        if (mbedtls_ecdh_compute_shared(&g_kp.grp, &z, &peer, &g_kp.d,
                NULL, NULL) != 0) break;
        // the shared secret is the X coordinate alone, 32 bytes, and mbedtls
        // gives exactly that -- no KDF, the mesh does its own with k1.
        if (mbedtls_mpi_write_binary(&z, secret, 32) != 0) break;
        ok = true;
    } while (0);
    mbedtls_ecp_point_free(&peer);
    mbedtls_mpi_free(&z);
    return ok;
}

bool prov_ccm_encrypt(const uint8_t key[16], const uint8_t nonce[13],
                      const uint8_t *in, size_t len, uint8_t *out) {
    mbedtls_ccm_context c;
    mbedtls_ccm_init(&c);
    bool ok = false;
    if (mbedtls_ccm_setkey(&c, MBEDTLS_CIPHER_ID_AES, key, 128) == 0) {
        ok = mbedtls_ccm_encrypt_and_tag(&c, len, nonce, 13, NULL, 0,
                                         in, out, out + len, 8) == 0;
    }
    mbedtls_ccm_free(&c);
    return ok;
}
