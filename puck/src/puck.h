// What main.cpp lends a module (src/module.h): the broker, the puck's name, and the few helpers
// every topic on it is spelled with. Nothing else of main.cpp is a module's to touch.
#pragma once
#include <Arduino.h>
#include <PubSubClient.h>

#ifndef HA_PREFIX
#define HA_PREFIX "homeassistant"
#endif

extern PubSubClient mqtt;
extern char chipHex[7];               // this puck: six hex digits from the factory MAC

void hexstr(const uint8_t *b, size_t n, char *out);
void mqttPub(const char *topic, const char *payload, bool retain);
void bridgeTopic(char *out, size_t n, const char *leaf);   // <base>/bridge/<chip>/<leaf>
void bridgeDevice(char *out, size_t n);   // the puck's own device, as a discovery payload's "dev":{...}
void hubMqttReconnect();              // one attempt at the broker, rate-limited as the loop's own is
void hubLightRefresh();               // the light, recomputed now rather than on the next pass
