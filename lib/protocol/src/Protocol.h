#pragma once

#include <Arduino.h>

struct TelemetryMessage {
  const char* nodeId;
  uint32_t cycle;
  uint32_t uptimeMs;
  float tHotC;
  float tLiquidC;
  uint8_t fanPwm;
  uint8_t pumpPwm;
  float virtualFlow;
  bool sensorOk;
  bool simulationMode;
  bool localAnomaly;
  bool networkOk;
};

struct CommandMessage {
  bool valid = false;
  uint8_t targetFanPwm = 0;
  uint8_t targetPumpPwm = 0;
  float globalAvgHotC = 0.0f;
  bool anomaly = false;
  char mode[20] = "unknown";
};

String encodeTelemetryJson(const TelemetryMessage& message);
bool decodeCommandJson(const String& responseLine, CommandMessage& outCommand);
