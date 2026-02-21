#pragma once

#include <Arduino.h>

struct RackTelemetryMessage {
  const char* rackId;
  float tHotC;
  float tLiquidC;
  uint8_t fanLocalPwm;
  uint8_t heatPwm;
  uint8_t pumpV;
  int32_t rssi;
  bool localAnomaly;
  uint32_t tsMs;
};

struct RackCommandMessage {
  bool valid = false;
  uint8_t fanLocalPwm = 0;
  uint8_t heatPwm = 0;
  uint8_t pumpV = 0;
  float globalAvgHotC = 0.0f;
  bool anomaly = false;
  char mode[20] = "unknown";
};

struct CduTelemetryMessage {
  const char* cduId;
  uint8_t fanAPwm;
  uint8_t fanBPwm;
  float tSupplyA;
  float tSupplyB;
  uint32_t tsMs;
};

struct CduCommandMessage {
  bool valid = false;
  uint8_t fanAPwm = 0;
  uint8_t fanBPwm = 0;
  float tSupplyTarget = 0.0f;
  char fallbackTarget[24] = "maintain_supply";
};

String encodeRackTelemetryJson(const RackTelemetryMessage& message);
bool decodeRackCommandJson(const String& responseLine, RackCommandMessage& outCommand);

String encodeCduTelemetryJson(const CduTelemetryMessage& message);
bool decodeCduCommandJson(const String& responseLine, CduCommandMessage& outCommand);
