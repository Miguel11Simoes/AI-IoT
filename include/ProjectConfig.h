#pragma once

#include <Arduino.h>
#include <IPAddress.h>

#ifndef NODE_ID
#define NODE_ID "A"
#endif

#ifndef DEVICE_NAME
#define DEVICE_NAME "AI_COOLING_NODE"
#endif

#ifndef DEVICE_IP_4
#define DEVICE_IP_4 100
#endif

#ifndef SERVER_IP_1
#define SERVER_IP_1 192
#endif
#ifndef SERVER_IP_2
#define SERVER_IP_2 168
#endif
#ifndef SERVER_IP_3
#define SERVER_IP_3 1
#endif
#ifndef SERVER_IP_4
#define SERVER_IP_4 10
#endif

#ifndef SERVER_PORT
#define SERVER_PORT 5000
#endif

#ifndef NETWORK_SUBNET_1
#define NETWORK_SUBNET_1 255
#endif
#ifndef NETWORK_SUBNET_2
#define NETWORK_SUBNET_2 255
#endif
#ifndef NETWORK_SUBNET_3
#define NETWORK_SUBNET_3 255
#endif
#ifndef NETWORK_SUBNET_4
#define NETWORK_SUBNET_4 0
#endif

#ifndef NETWORK_GATEWAY_1
#define NETWORK_GATEWAY_1 192
#endif
#ifndef NETWORK_GATEWAY_2
#define NETWORK_GATEWAY_2 168
#endif
#ifndef NETWORK_GATEWAY_3
#define NETWORK_GATEWAY_3 1
#endif
#ifndef NETWORK_GATEWAY_4
#define NETWORK_GATEWAY_4 1
#endif

#ifndef NETWORK_DNS_1
#define NETWORK_DNS_1 8
#endif
#ifndef NETWORK_DNS_2
#define NETWORK_DNS_2 8
#endif
#ifndef NETWORK_DNS_3
#define NETWORK_DNS_3 8
#endif
#ifndef NETWORK_DNS_4
#define NETWORK_DNS_4 8
#endif

#ifndef MAC_1
#define MAC_1 0xDE
#endif
#ifndef MAC_2
#define MAC_2 0xAD
#endif
#ifndef MAC_3
#define MAC_3 0xBE
#endif
#ifndef MAC_4
#define MAC_4 0xEF
#endif
#ifndef MAC_5
#define MAC_5 0xFE
#endif
#ifndef MAC_6
#define MAC_6 0x01
#endif

#ifndef W5500_CS_PIN
#define W5500_CS_PIN 5
#endif
#ifndef W5500_RESET_PIN
#define W5500_RESET_PIN 4
#endif
#ifndef W5500_SCK_PIN
#define W5500_SCK_PIN 18
#endif
#ifndef W5500_MISO_PIN
#define W5500_MISO_PIN 19
#endif
#ifndef W5500_MOSI_PIN
#define W5500_MOSI_PIN 23
#endif

#ifndef ONE_WIRE_PIN
#define ONE_WIRE_PIN 14
#endif
#ifndef FAN_PIN
#define FAN_PIN 17
#endif
#ifndef PUMP_PIN
#define PUMP_PIN 16
#endif

#ifndef CYCLE_INTERVAL_MS
#define CYCLE_INTERVAL_MS 1000
#endif
#ifndef NETWORK_TIMEOUT_MS
#define NETWORK_TIMEOUT_MS 1300
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

struct NodeConfig {
  const char* nodeId;
  const char* deviceName;
  uint8_t mac[6];
  IPAddress ip;
  IPAddress dns;
  IPAddress gateway;
  IPAddress subnet;
  IPAddress serverIp;
  uint16_t serverPort;
  uint8_t csPin;
  uint8_t resetPin;
  uint8_t sckPin;
  uint8_t misoPin;
  uint8_t mosiPin;
  uint8_t oneWirePin;
  uint8_t fanPin;
  uint8_t pumpPin;
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
};

inline NodeConfig loadNodeConfig() {
  NodeConfig cfg{};
  cfg.nodeId = NODE_ID;
  cfg.deviceName = DEVICE_NAME;
  cfg.mac[0] = static_cast<uint8_t>(MAC_1);
  cfg.mac[1] = static_cast<uint8_t>(MAC_2);
  cfg.mac[2] = static_cast<uint8_t>(MAC_3);
  cfg.mac[3] = static_cast<uint8_t>(MAC_4);
  cfg.mac[4] = static_cast<uint8_t>(MAC_5);
  cfg.mac[5] = static_cast<uint8_t>(MAC_6);
  cfg.ip = IPAddress(192, 168, 1, DEVICE_IP_4);
  cfg.dns = IPAddress(NETWORK_DNS_1, NETWORK_DNS_2, NETWORK_DNS_3, NETWORK_DNS_4);
  cfg.gateway =
      IPAddress(NETWORK_GATEWAY_1, NETWORK_GATEWAY_2, NETWORK_GATEWAY_3, NETWORK_GATEWAY_4);
  cfg.subnet =
      IPAddress(NETWORK_SUBNET_1, NETWORK_SUBNET_2, NETWORK_SUBNET_3, NETWORK_SUBNET_4);
  cfg.serverIp = IPAddress(SERVER_IP_1, SERVER_IP_2, SERVER_IP_3, SERVER_IP_4);
  cfg.serverPort = static_cast<uint16_t>(SERVER_PORT);
  cfg.csPin = static_cast<uint8_t>(W5500_CS_PIN);
  cfg.resetPin = static_cast<uint8_t>(W5500_RESET_PIN);
  cfg.sckPin = static_cast<uint8_t>(W5500_SCK_PIN);
  cfg.misoPin = static_cast<uint8_t>(W5500_MISO_PIN);
  cfg.mosiPin = static_cast<uint8_t>(W5500_MOSI_PIN);
  cfg.oneWirePin = static_cast<uint8_t>(ONE_WIRE_PIN);
  cfg.fanPin = static_cast<uint8_t>(FAN_PIN);
  cfg.pumpPin = static_cast<uint8_t>(PUMP_PIN);
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
  return cfg;
}
