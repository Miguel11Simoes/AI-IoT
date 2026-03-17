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
  doc["t_hot_real_c"] = message.tHotRealC;
  doc["t_hot_source"] = message.tHotSource;
  doc["t_liquid_source"] = message.tLiquidSource;
  doc["telemetry_mode"] = message.telemetryMode;
  doc["sensor_ok"] = message.sensorOk;
  doc["t_hot"] = message.tHotRealC;
  if (message.hasLiquidReal) {
    doc["t_liquid_real_c"] = message.tLiquidRealC;
    doc["t_liquid"] = message.tLiquidRealC;
  }
  doc["fan_local_pwm"] = message.fanLocalPwm;
  doc["heat_pwm"] = message.heatPwm;
  doc["heater_on"] = message.heaterOn;
  doc["heater_rated_power_w"] = message.heaterRatedPowerW;
  doc["heater_avg_power_w"] = message.heaterAvgPowerW;
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
  doc["peltierA_on"] = message.peltierAOn;
  doc["peltierB_on"] = message.peltierBOn;
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
  outCommand.peltierAOn = doc["peltierA_on"] | false;
  outCommand.peltierBOn = doc["peltierB_on"] | false;
  JsonVariantConst supplyTarget = doc["t_supply_target"];
  outCommand.hasSupplyTarget = !supplyTarget.isNull();
  outCommand.tSupplyTarget = outCommand.hasSupplyTarget ? supplyTarget.as<float>() : 0.0f;

  const char* fallback = doc["fallback_target"] | "maintain_supply";
  strncpy(outCommand.fallbackTarget, fallback, sizeof(outCommand.fallbackTarget) - 1);
  outCommand.fallbackTarget[sizeof(outCommand.fallbackTarget) - 1] = '\0';

  outCommand.valid = true;
  return true;
}
