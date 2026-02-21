#include "Protocol.h"

#include <ArduinoJson.h>

namespace {
uint8_t clampByte(int value) {
  if (value < 0) {
    return 0;
  }
  if (value > 255) {
    return 255;
  }
  return static_cast<uint8_t>(value);
}
}  // namespace

String encodeRackTelemetryJson(const RackTelemetryMessage& message) {
  JsonDocument doc;
  doc["type"] = "rack_telemetry";
  doc["id"] = message.rackId;
  doc["t_hot"] = message.tHotC;
  doc["t_liquid"] = message.tLiquidC;
  doc["fan_local_pwm"] = message.fanLocalPwm;
  doc["heat_pwm"] = message.heatPwm;
  doc["pump_v"] = message.pumpV;
  doc["rssi"] = message.rssi;
  doc["local_anomaly"] = message.localAnomaly;
  doc["ts"] = message.tsMs;

  String output;
  serializeJson(doc, output);
  return output;
}

bool decodeRackCommandJson(const String& responseLine, RackCommandMessage& outCommand) {
  JsonDocument doc;
  const DeserializationError err = deserializeJson(doc, responseLine);
  if (err) {
    outCommand.valid = false;
    return false;
  }

  outCommand.fanLocalPwm =
      clampByte(doc["fan_local_pwm"] | doc["target_fan_pwm"] | 0);
  outCommand.heatPwm = clampByte(doc["heat_pwm"] | doc["target_heat_pwm"] | 0);
  outCommand.pumpV = clampByte(doc["pump_v"] | doc["target_pump_pwm"] | 0);
  outCommand.globalAvgHotC = doc["global_avg_hot"] | 0.0f;
  outCommand.anomaly = doc["anomaly"] | false;

  const char* mode = doc["mode"] | "unknown";
  strncpy(outCommand.mode, mode, sizeof(outCommand.mode) - 1);
  outCommand.mode[sizeof(outCommand.mode) - 1] = '\0';

  outCommand.valid = true;
  return true;
}

String encodeCduTelemetryJson(const CduTelemetryMessage& message) {
  JsonDocument doc;
  doc["type"] = "cdu_telemetry";
  doc["id"] = message.cduId;
  doc["fanA_pwm"] = message.fanAPwm;
  doc["fanB_pwm"] = message.fanBPwm;
  doc["t_supply_A"] = message.tSupplyA;
  doc["t_supply_B"] = message.tSupplyB;
  doc["ts"] = message.tsMs;

  String output;
  serializeJson(doc, output);
  return output;
}

bool decodeCduCommandJson(const String& responseLine, CduCommandMessage& outCommand) {
  JsonDocument doc;
  const DeserializationError err = deserializeJson(doc, responseLine);
  if (err) {
    outCommand.valid = false;
    return false;
  }

  outCommand.fanAPwm = clampByte(doc["fanA_pwm"] | 0);
  outCommand.fanBPwm = clampByte(doc["fanB_pwm"] | 0);
  outCommand.tSupplyTarget = doc["t_supply_target"] | 0.0f;

  const char* fallback = doc["fallback_target"] | "maintain_supply";
  strncpy(outCommand.fallbackTarget, fallback, sizeof(outCommand.fallbackTarget) - 1);
  outCommand.fallbackTarget[sizeof(outCommand.fallbackTarget) - 1] = '\0';

  outCommand.valid = true;
  return true;
}
