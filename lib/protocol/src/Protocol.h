#pragma once

#include <Arduino.h>

struct RackTelemetryMessage {
  const char* rackId;
  float tHotRealC;
  float tLiquidRealC;
  bool hasLiquidReal = false;
  const char* tHotSource;
  const char* tLiquidSource;
  const char* telemetryMode;
  bool sensorOk;
  uint8_t fanLocalPwm;
  uint8_t heatPwm;
  bool heaterOn;
  float heaterRatedPowerW;
  float heaterAvgPowerW;
  int32_t rssi;
  bool localAnomaly;
  uint32_t tsMs;
};

struct RackCommandMessage {
  bool valid = false;
  uint8_t fanLocalPwm = 0;
  uint8_t heatPwm = 0;
  float globalAvgHotC = 0.0f;
  bool anomaly = false;
  char mode[20] = "unknown";
};

struct CduTelemetryMessage {
  const char* cduId;
  uint8_t fanAPwm;
  uint8_t fanBPwm;
  bool peltierAOn;
  bool peltierBOn;
  float tSupplyA;
  float tSupplyB;
  uint32_t tsMs;
};

struct CduCommandMessage {
  bool valid = false;
  uint8_t fanAPwm = 0;
  uint8_t fanBPwm = 0;
  bool peltierAOn = false;
  bool peltierBOn = false;
  bool hasSupplyTarget = false;
  float tSupplyTarget = 0.0f;
  char fallbackTarget[24] = "maintain_supply";
};

String encodeRackTelemetryJson(const RackTelemetryMessage& message);
bool decodeRackCommandJson(const String& responseLine, RackCommandMessage& outCommand);

String encodeCduTelemetryJson(const CduTelemetryMessage& message);
bool decodeCduCommandJson(const String& responseLine, CduCommandMessage& outCommand);
