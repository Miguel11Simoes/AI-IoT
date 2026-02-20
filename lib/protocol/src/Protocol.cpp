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

String encodeTelemetryJson(const TelemetryMessage& message) {
  JsonDocument doc;
  doc["id"] = message.nodeId;
  doc["cycle"] = message.cycle;
  doc["uptime_ms"] = message.uptimeMs;
  doc["t_hot"] = message.tHotC;
  doc["t_liquid"] = message.tLiquidC;
  doc["fan_pwm"] = message.fanPwm;
  doc["pump_pwm"] = message.pumpPwm;
  doc["virtual_flow"] = message.virtualFlow;
  doc["sensor_ok"] = message.sensorOk;
  doc["sim_mode"] = message.simulationMode;
  doc["local_anomaly"] = message.localAnomaly;
  doc["network_ok"] = message.networkOk;

  String output;
  serializeJson(doc, output);
  return output;
}

bool decodeCommandJson(const String& responseLine, CommandMessage& outCommand) {
  JsonDocument doc;
  const DeserializationError err = deserializeJson(doc, responseLine);
  if (err) {
    outCommand.valid = false;
    return false;
  }

  outCommand.targetFanPwm = clampByte(doc["target_fan_pwm"] | 0);
  outCommand.targetPumpPwm = clampByte(doc["target_pump_pwm"] | 0);
  outCommand.globalAvgHotC = doc["global_avg_hot"] | 0.0f;
  outCommand.anomaly = doc["anomaly"] | false;

  const char* mode = doc["mode"] | "unknown";
  strncpy(outCommand.mode, mode, sizeof(outCommand.mode) - 1);
  outCommand.mode[sizeof(outCommand.mode) - 1] = '\0';

  outCommand.valid = true;
  return true;
}
