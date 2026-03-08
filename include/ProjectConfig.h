#pragma once

#include <Arduino.h>

#ifndef DEVICE_ROLE
#define DEVICE_ROLE 1
#endif

#define ROLE_RACK 1
#define ROLE_CDU 2

#ifndef NODE_ID
#define NODE_ID "A"
#endif

#ifndef RACK_ID
#define RACK_ID "R00"
#endif

#ifndef DEVICE_NAME
#define DEVICE_NAME "AI_COOLING_NODE"
#endif

#ifndef CDU_ID
#define CDU_ID "CDU1"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID "CHANGE_ME_SSID"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "CHANGE_ME_PASS"
#endif

#ifndef SERVER_HOST
#define SERVER_HOST "192.168.1.10"
#endif

#ifndef EDGE_WS_PORT
#define EDGE_WS_PORT 8765
#endif

#ifndef EDGE_WS_PATH
#define EDGE_WS_PATH "/"
#endif

#ifndef CYCLE_INTERVAL_MS
#define CYCLE_INTERVAL_MS 1000
#endif

#ifndef NETWORK_TIMEOUT_MS
#define NETWORK_TIMEOUT_MS 1500
#endif

#ifndef REMOTE_CMD_TTL_MS
#define REMOTE_CMD_TTL_MS 5000
#endif

#ifndef SIMULATED_COOLING
#define SIMULATED_COOLING 1
#endif

#ifndef DEFAULT_AMBIENT_C
#define DEFAULT_AMBIENT_C 26
#endif
#ifndef INITIAL_HOT_C
#define INITIAL_HOT_C 40
#endif
#ifndef INITIAL_LIQUID_C
#define INITIAL_LIQUID_C 34
#endif
#ifndef HEAT_GAIN_C_PER_SEC
#define HEAT_GAIN_C_PER_SEC 2.8
#endif
#ifndef HOT_TO_LIQUID_COEFF
#define HOT_TO_LIQUID_COEFF 0.22
#endif
#ifndef HOT_TO_AMBIENT_COEFF
#define HOT_TO_AMBIENT_COEFF 0.03
#endif
#ifndef LIQUID_TO_AMBIENT_COEFF
#define LIQUID_TO_AMBIENT_COEFF 0.11
#endif
#ifndef FLOW_COOLING_COEFF
#define FLOW_COOLING_COEFF 0.24
#endif

#ifndef ANOMALY_TEMP_C
#define ANOMALY_TEMP_C 80
#endif
#ifndef CRITICAL_TEMP_C
#define CRITICAL_TEMP_C 88
#endif
#ifndef HEAT_WINDOW_MS
#define HEAT_WINDOW_MS 2000
#endif

#ifndef ONE_WIRE_PIN
#define ONE_WIRE_PIN 14
#endif
#ifndef HEAT_PIN
#define HEAT_PIN 18
#endif

#ifndef CDU_FAN_A_PIN
#define CDU_FAN_A_PIN 10
#endif
#ifndef CDU_FAN_B_PIN
#define CDU_FAN_B_PIN 11
#endif

struct RackNodeConfig {
  const char* nodeId;
  const char* rackId;
  const char* deviceName;
  const char* wifiSsid;
  const char* wifiPassword;
  const char* serverHost;
  uint16_t edgeWsPort;
  const char* edgeWsPath;
  uint8_t oneWirePin;
  uint8_t heatPin;
  uint32_t cycleIntervalMs;
  uint32_t networkTimeoutMs;
  uint32_t remoteCmdTtlMs;
  bool simulatedCooling;
  float ambientC;
  float initialHotC;
  float initialLiquidC;
  float heatGainCPerSec;
  float hotToLiquidCoeff;
  float hotToAmbientCoeff;
  float liquidToAmbientCoeff;
  float flowCoolingCoeff;
  float anomalyTempC;
  float criticalTempC;
  uint16_t heatWindowMs;
};

inline RackNodeConfig loadRackConfig() {
  RackNodeConfig cfg{};
  cfg.nodeId = NODE_ID;
  cfg.rackId = RACK_ID;
  cfg.deviceName = DEVICE_NAME;
  cfg.wifiSsid = WIFI_SSID;
  cfg.wifiPassword = WIFI_PASSWORD;
  cfg.serverHost = SERVER_HOST;
  cfg.edgeWsPort = static_cast<uint16_t>(EDGE_WS_PORT);
  cfg.edgeWsPath = EDGE_WS_PATH;
  cfg.oneWirePin = static_cast<uint8_t>(ONE_WIRE_PIN);
  cfg.heatPin = static_cast<uint8_t>(HEAT_PIN);
  cfg.cycleIntervalMs = static_cast<uint32_t>(CYCLE_INTERVAL_MS);
  cfg.networkTimeoutMs = static_cast<uint32_t>(NETWORK_TIMEOUT_MS);
  cfg.remoteCmdTtlMs = static_cast<uint32_t>(REMOTE_CMD_TTL_MS);
  cfg.simulatedCooling = (SIMULATED_COOLING != 0);
  cfg.ambientC = static_cast<float>(DEFAULT_AMBIENT_C);
  cfg.initialHotC = static_cast<float>(INITIAL_HOT_C);
  cfg.initialLiquidC = static_cast<float>(INITIAL_LIQUID_C);
  cfg.heatGainCPerSec = static_cast<float>(HEAT_GAIN_C_PER_SEC);
  cfg.hotToLiquidCoeff = static_cast<float>(HOT_TO_LIQUID_COEFF);
  cfg.hotToAmbientCoeff = static_cast<float>(HOT_TO_AMBIENT_COEFF);
  cfg.liquidToAmbientCoeff = static_cast<float>(LIQUID_TO_AMBIENT_COEFF);
  cfg.flowCoolingCoeff = static_cast<float>(FLOW_COOLING_COEFF);
  cfg.anomalyTempC = static_cast<float>(ANOMALY_TEMP_C);
  cfg.criticalTempC = static_cast<float>(CRITICAL_TEMP_C);
  cfg.heatWindowMs = static_cast<uint16_t>(HEAT_WINDOW_MS);
  return cfg;
}

struct CduConfig {
  const char* cduId;
  const char* deviceName;
  const char* wifiSsid;
  const char* wifiPassword;
  const char* serverHost;
  uint16_t edgeWsPort;
  const char* edgeWsPath;
  uint8_t fanAPin;
  uint8_t fanBPin;
  uint32_t cycleIntervalMs;
  uint32_t networkTimeoutMs;
  uint32_t remoteCmdTtlMs;
};

inline CduConfig loadCduConfig() {
  CduConfig cfg{};
  cfg.cduId = CDU_ID;
  cfg.deviceName = DEVICE_NAME;
  cfg.wifiSsid = WIFI_SSID;
  cfg.wifiPassword = WIFI_PASSWORD;
  cfg.serverHost = SERVER_HOST;
  cfg.edgeWsPort = static_cast<uint16_t>(EDGE_WS_PORT);
  cfg.edgeWsPath = EDGE_WS_PATH;
  cfg.fanAPin = static_cast<uint8_t>(CDU_FAN_A_PIN);
  cfg.fanBPin = static_cast<uint8_t>(CDU_FAN_B_PIN);
  cfg.cycleIntervalMs = static_cast<uint32_t>(CYCLE_INTERVAL_MS);
  cfg.networkTimeoutMs = static_cast<uint32_t>(NETWORK_TIMEOUT_MS);
  cfg.remoteCmdTtlMs = static_cast<uint32_t>(REMOTE_CMD_TTL_MS);
  return cfg;
}
