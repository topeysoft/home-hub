// Post-provisioning recorder: pose as a proxy node and answer the panel app's
// configuration, capturing the AppKey and every vendor write it makes.
//
// The provisioning handshake (main.cpp) gives us the netkey + our devkey. The
// app then RECONNECTS over the proxy service and configures the "switch":
// Composition Data Get, AppKey Add, model bindings, publication set, and the
// Brilliant-specific vendor writes that set load type and enable motion. We
// answer just enough for the app to keep going, and we log the secrets.
#pragma once
#include <Arduino.h>

// Arm the recorder with what provisioning yielded. After this, feed it proxy
// PDUs and it will answer via the sender set below.
void rec_init(const uint8_t netkey[16], const uint8_t devkey[16],
              uint16_t unicast, uint32_t iv);

// How the recorder sends a proxy PDU back to the app (main.cpp frames it into
// GATT notifications on the proxy Data Out characteristic).
void rec_set_sender(void (*send_proxy)(uint8_t type, const uint8_t *pdu, size_t len));

// Feed one fully-reassembled proxy PDU (type = byte0 & 0x3F of the proxy header).
void rec_on_proxy(uint8_t type, const uint8_t *pdu, size_t len);

// True once the AppKey has been captured (so the caller can announce it).
bool rec_have_appkey();
