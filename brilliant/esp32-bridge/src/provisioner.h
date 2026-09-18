// The provisioner half of PB-GATT: how a puck claims a factory-fresh switch.
//
// The bridge is a proxy CLIENT -- it joins a network somebody else made. This
// is the other job, the one that makes a network member out of a switch in a
// box, and it is the last thing standing between the design and a working
// "Add a wall switch".
//
// tools/provision.py is the reference; this mirrors it step for step, and the
// provisionee firmware in ../../mesh-provisionee/ plays the opposite side of the
// same exchange, so between the three there is a worked example of every PDU.
//
// DELIBERATELY TRANSPORT-FREE. This class never touches BLE. It is fed incoming
// provisioning PDUs and asked what to send next, which means the whole handshake
// -- the part with the cryptography in it, the part that is hard to debug on a
// chip -- can be run and checked on a workstation against known-good values.
// The GATT link, its SAR and its notifications are the caller's business.
//
// Usage -- SETTINGS FIRST, then begin(), which queues the Invite and starts it:
//     Provisioner p;
//     p.useStaticOOB(oob);          // from the QR; omit for a switch we reset
//     p.useAttention(5);            // blink it; omit when the QR named it
//     p.begin(netkey, 0, 0, iv, unicast);
//     while (size_t n = p.next(buf)) send(buf, n);
//     ... on each notification: p.feed(pdu, len); then drain next() again
//     if (p.state() == Provisioner::DONE) { p.devkey(); p.elements(); }
#pragma once
#include <Arduino.h>

class Provisioner {
 public:
    enum State : uint8_t { IDLE, INVITED, STARTED, KEYED, EXCHANGED, SENT_DATA, DONE, FAILED };

    // A provisioning PDU is at most a type byte plus a 64-byte public key. A
    // 64-byte buffer overflows on exactly that message and reboots the chip
    // mid-handshake, which is documented in docs/brilliant.md as a thing that
    // actually happened. 66 leaves room and the length is checked besides.
    static const size_t MAX_PDU = 66;

    // Call the use*() setters BEFORE this. begin() builds and queues the Invite,
    // so an attention timer set afterwards is set for a PDU already sent -- and
    // it would go unnoticed, because the handshake still completes, just without
    // the blink that was the whole point of asking for it.
    void begin(const uint8_t netkey[16], uint16_t key_index, uint8_t flags,
               uint32_t iv_index, uint16_t unicast);

    // The 16-byte Static OOB from the switch's QR code (the QR is 32 bytes of
    // ASCII hex: 16 of Device UUID, then these 16). With it the Start PDU asks
    // for auth method 0x01 and the confirmation is salted with the secret, which
    // is the mesh's own proof that somebody is holding the switch. Without it we
    // fall back to No OOB, which only a switch WE factory-reset will accept.
    void useStaticOOB(const uint8_t oob[16]);

    // Seconds of Attention Timer in the Invite: the device is asked to make
    // itself known to a person. Zero for a QR add, where they are already
    // holding the switch. Non-zero is the entire identity check when there is no
    // code to scan -- the house blinks a candidate and asks whether the blinking
    // one is the switch whose plate they just had a finger on.
    void useAttention(uint8_t seconds);

    // Deterministic randomness, for the native test. Production leaves it alone.
    void useRandom(void (*fn)(uint8_t *out, size_t len));

    void feed(const uint8_t *pdu, size_t len);
    size_t next(uint8_t *out);          // 0 when there is nothing to send

    State state() const { return st_; }
    uint8_t reason() const { return reason_; }      // Provisioning Failed code
    const uint8_t *devkey() const { return devkey_; }
    uint8_t elements() const { return caps_[0]; }

 private:
    void fail(uint8_t code);
    void queue(uint8_t type, const uint8_t *params, size_t len);

    State st_ = IDLE;
    uint8_t reason_ = 0;

    uint8_t netkey_[16], flags_ = 0;
    uint16_t key_index_ = 0, unicast_ = 0;
    uint32_t iv_index_ = 0;

    uint8_t attention_ = 0;
    bool have_oob_ = false;
    uint8_t oob_[16];
    void (*rand_)(uint8_t *, size_t) = nullptr;

    // the transcript, kept because the confirmation is over all of it
    uint8_t invite_[1], caps_[11], start_[5];
    uint8_t pub_p_[64], pub_d_[64];
    uint8_t secret_[32], conf_key_[16], conf_salt_[16];
    uint8_t rand_p_[16], conf_d_[16];
    uint8_t devkey_[16];

    uint8_t out_[2][MAX_PDU];
    size_t out_len_[2] = {0, 0};
    uint8_t out_head_ = 0, out_tail_ = 0;
};
