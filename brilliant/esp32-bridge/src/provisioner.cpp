#include "provisioner.h"
#include "prov_crypto.h"
#include "mesh_crypto.h"
#include <string.h>
#ifdef ARDUINO
#include "esp_random.h"
#endif

// Provisioning PDU types (Mesh Profile 1.0.1, 5.4.1).
enum { T_INVITE = 0x00, T_CAPS = 0x01, T_START = 0x02, T_PUBKEY = 0x03,
       T_INPUT_COMPLETE = 0x04, T_CONFIRM = 0x05, T_RANDOM = 0x06,
       T_DATA = 0x07, T_COMPLETE = 0x08, T_FAILED = 0x09 };

// Failure codes we raise ourselves. 0x01 is the spec's "Invalid PDU"; 0x05 is
// "Confirmation Failed", which is the one that matters -- it means the device
// could not prove it holds the secret, and on a QR add that usually means the
// code belongs to a different switch from the one in front of you.
enum { F_BAD_PDU = 0x01, F_CONFIRM = 0x05, F_RESOURCES = 0x02 };

static void default_random(uint8_t *out, size_t len) {
#ifdef ARDUINO
    for (size_t i = 0; i < len; i++) out[i] = (uint8_t)esp_random();
#else
    for (size_t i = 0; i < len; i++) out[i] = (uint8_t)(i * 7 + 1);
#endif
}

void Provisioner::begin(const uint8_t netkey[16], uint16_t key_index,
                        uint8_t flags, uint32_t iv_index, uint16_t unicast) {
    memcpy(netkey_, netkey, 16);
    key_index_ = key_index;
    flags_ = flags;
    iv_index_ = iv_index;
    unicast_ = unicast;
    st_ = IDLE;
    reason_ = 0;
    out_head_ = out_tail_ = 0;
    if (!rand_) rand_ = default_random;

    // Invite. Its one parameter is the attention timer, and it defaults to zero
    // because a QR add has the person holding the switch already. useAttention()
    // is what a codeless add sets, and it is not decoration there: it is the only
    // thing that distinguishes the switch they touched from any other unclaimed
    // one within radio range.
    invite_[0] = attention_;
    queue(T_INVITE, invite_, 1);
    st_ = INVITED;
}

void Provisioner::useStaticOOB(const uint8_t oob[16]) {
    memcpy(oob_, oob, 16);
    have_oob_ = true;
}

void Provisioner::useAttention(uint8_t seconds) { attention_ = seconds; }

void Provisioner::useRandom(void (*fn)(uint8_t *, size_t)) { rand_ = fn; }

void Provisioner::queue(uint8_t type, const uint8_t *params, size_t len) {
    if (len + 1 > MAX_PDU) { fail(F_RESOURCES); return; }
    uint8_t slot = out_tail_ % 2;
    if (out_tail_ - out_head_ >= 2) { fail(F_RESOURCES); return; }
    out_[slot][0] = type;
    if (len) memcpy(out_[slot] + 1, params, len);
    out_len_[slot] = len + 1;
    out_tail_++;
}

size_t Provisioner::next(uint8_t *out) {
    if (out_head_ == out_tail_) return 0;
    uint8_t slot = out_head_ % 2;
    memcpy(out, out_[slot], out_len_[slot]);
    out_head_++;
    return out_len_[slot];
}

void Provisioner::fail(uint8_t code) {
    st_ = FAILED;
    reason_ = code;
    out_head_ = out_tail_ = 0;
}

void Provisioner::feed(const uint8_t *pdu, size_t len) {
    if (st_ == FAILED || st_ == DONE || len < 1) return;
    const uint8_t type = pdu[0];
    const uint8_t *p = pdu + 1;
    const size_t plen = len - 1;

    if (type == T_FAILED) { fail(plen ? p[0] : F_BAD_PDU); return; }

    switch (st_) {
    case INVITED: {
        if (type != T_CAPS || plen != 11) { fail(F_BAD_PDU); return; }
        memcpy(caps_, p, 11);

        // Start: algorithm 0 (FIPS P-256), public key OOB 0 (in-band), then the
        // authentication method. 0x01 is Static OOB and takes the QR's secret;
        // 0x00 is No OOB. The last two bytes are the action and size, which are
        // meaningless for both of those methods and must be zero.
        start_[0] = 0x00;
        start_[1] = 0x00;
        start_[2] = have_oob_ ? 0x01 : 0x00;
        start_[3] = 0x00;
        start_[4] = 0x00;
        queue(T_START, start_, 5);

        if (!prov_ecdh_generate(pub_p_)) { fail(F_RESOURCES); return; }
        queue(T_PUBKEY, pub_p_, 64);
        st_ = STARTED;
        return;
    }
    case STARTED: {
        if (type != T_PUBKEY || plen != 64) { fail(F_BAD_PDU); return; }
        memcpy(pub_d_, p, 64);
        if (!prov_ecdh_shared(pub_d_, secret_)) { fail(F_RESOURCES); return; }

        // ConfirmationInputs is the whole conversation so far, in order:
        // invite || capabilities || start || our public key || theirs. 145 bytes,
        // and getting one field's width wrong here fails at the very last step
        // with nothing to point at.
        uint8_t ci[145];
        size_t o = 0;
        memcpy(ci + o, invite_, 1);  o += 1;
        memcpy(ci + o, caps_, 11);   o += 11;
        memcpy(ci + o, start_, 5);   o += 5;
        memcpy(ci + o, pub_p_, 64);  o += 64;
        memcpy(ci + o, pub_d_, 64);  o += 64;
        mesh_s1(ci, sizeof(ci), conf_salt_);
        mesh_k1(secret_, 32, conf_salt_, (const uint8_t *)"prck", 4, conf_key_);

        uint8_t auth[16];
        if (have_oob_) memcpy(auth, oob_, 16); else memset(auth, 0, 16);

        rand_(rand_p_, 16);
        uint8_t msg[32];
        memcpy(msg, rand_p_, 16);
        memcpy(msg + 16, auth, 16);
        uint8_t conf_p[16];
        mesh_cmac(conf_key_, msg, 32, conf_p);
        queue(T_CONFIRM, conf_p, 16);
        st_ = KEYED;
        return;
    }
    case KEYED: {
        if (type != T_CONFIRM || plen != 16) { fail(F_BAD_PDU); return; }
        memcpy(conf_d_, p, 16);
        queue(T_RANDOM, rand_p_, 16);
        st_ = EXCHANGED;
        return;
    }
    case EXCHANGED: {
        if (type != T_RANDOM || plen != 16) { fail(F_BAD_PDU); return; }
        const uint8_t *rand_d = p;

        // The device's confirmation, recomputed now that its random is known.
        // This is the step that proves it holds the Static OOB from the QR --
        // skip it and anything within radio range can pretend to be the switch
        // whose code was just scanned.
        uint8_t auth[16];
        if (have_oob_) memcpy(auth, oob_, 16); else memset(auth, 0, 16);
        uint8_t msg[32], chk[16];
        memcpy(msg, rand_d, 16);
        memcpy(msg + 16, auth, 16);
        mesh_cmac(conf_key_, msg, 32, chk);
        if (memcmp(chk, conf_d_, 16) != 0) { fail(F_CONFIRM); return; }

        uint8_t ps_in[48];
        memcpy(ps_in, conf_salt_, 16);
        memcpy(ps_in + 16, rand_p_, 16);
        memcpy(ps_in + 32, rand_d, 16);
        uint8_t prov_salt[16];
        mesh_s1(ps_in, sizeof(ps_in), prov_salt);

        uint8_t session_key[16], nonce16[16];
        mesh_k1(secret_, 32, prov_salt, (const uint8_t *)"prsk", 4, session_key);
        mesh_k1(secret_, 32, prov_salt, (const uint8_t *)"prsn", 4, nonce16);
        mesh_k1(secret_, 32, prov_salt, (const uint8_t *)"prdk", 4, devkey_);

        // The session nonce is the LAST 13 bytes of that k1 output, not the
        // first: k1 gives 16 and the nonce is 13.
        const uint8_t *nonce = nonce16 + 3;

        // 25 bytes, all big-endian, and the IV index must match the network or
        // every message this node later sends fails to decrypt in silence.
        uint8_t data[25];
        memcpy(data, netkey_, 16);
        data[16] = (uint8_t)(key_index_ >> 8);
        data[17] = (uint8_t)key_index_;
        data[18] = flags_;
        data[19] = (uint8_t)(iv_index_ >> 24);
        data[20] = (uint8_t)(iv_index_ >> 16);
        data[21] = (uint8_t)(iv_index_ >> 8);
        data[22] = (uint8_t)iv_index_;
        data[23] = (uint8_t)(unicast_ >> 8);
        data[24] = (uint8_t)unicast_;

        uint8_t enc[33];
        if (!prov_ccm_encrypt(session_key, nonce, data, 25, enc)) {
            fail(F_RESOURCES);
            return;
        }
        queue(T_DATA, enc, 33);
        st_ = SENT_DATA;
        return;
    }
    case SENT_DATA: {
        if (type != T_COMPLETE) { fail(F_BAD_PDU); return; }
        st_ = DONE;
        return;
    }
    default:
        return;
    }
}
