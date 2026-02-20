#include <Arduino.h>

#include "Control.h"
#include "Network.h"
#include "ProjectConfig.h"
#include "Protocol.h"
#include "Sensors.h"

namespace {
enum class NodeState : uint8_t {
  INIT,
  READ_SENSORS,
  CONTROL_LOCAL,
  SEND_DATA,
  WAIT_SERVER,
  APPLY_COMMAND,
  WAIT_NEXT
};

NodeConfig gConfig = loadNodeConfig();

SensorManager::Config makeSensorConfig(const NodeConfig& cfg) {
  SensorManager::Config out{};
  out.oneWirePin = cfg.oneWirePin;
  out.simulationMode = cfg.simulatedCooling;
  out.ambientC = cfg.ambientC;
  out.initialHotC = cfg.initialHotC;
  out.initialLiquidC = cfg.initialLiquidC;
  out.heatGainCPerSec = cfg.heatGainCPerSec;
  out.hotToLiquidCoeff = cfg.hotToLiquidCoeff;
  out.hotToAmbientCoeff = cfg.hotToAmbientCoeff;
  out.liquidToAmbientCoeff = cfg.liquidToAmbientCoeff;
  out.flowCoolingCoeff = cfg.flowCoolingCoeff;
  return out;
}

ControlManager::Config makeControlConfig(const NodeConfig& cfg) {
  ControlManager::Config out{};
  out.fanPin = cfg.fanPin;
  out.pumpPin = cfg.pumpPin;
  out.minFanPwm = 70;
  out.maxFanPwm = 255;
  out.minPumpPwm = 60;
  out.maxPumpPwm = 255;
  out.remoteTtlMs = cfg.remoteCmdTtlMs;
  out.anomalyTempC = cfg.anomalyTempC;
  out.criticalTempC = cfg.criticalTempC;
  out.maxRiseRateCPerSec = 5.0f;
  return out;
}

NetworkManager::Config makeNetworkConfig(const NodeConfig& cfg) {
  NetworkManager::Config out{};
  for (uint8_t i = 0; i < 6; ++i) {
    out.mac[i] = cfg.mac[i];
  }
  out.ip = cfg.ip;
  out.dns = cfg.dns;
  out.gateway = cfg.gateway;
  out.subnet = cfg.subnet;
  out.serverIp = cfg.serverIp;
  out.serverPort = cfg.serverPort;
  out.csPin = cfg.csPin;
  out.resetPin = cfg.resetPin;
  out.sckPin = cfg.sckPin;
  out.misoPin = cfg.misoPin;
  out.mosiPin = cfg.mosiPin;
  out.responseTimeoutMs = cfg.networkTimeoutMs;
  return out;
}

SensorManager gSensors(makeSensorConfig(gConfig));
ControlManager gControl(makeControlConfig(gConfig));
NetworkManager gNetwork(makeNetworkConfig(gConfig));

NodeState gState = NodeState::INIT;
uint32_t gStateEnteredMs = 0;
uint32_t gCycleStartedMs = 0;
uint32_t gCycleCounter = 0;
uint32_t gAckCounter = 0;
uint32_t gTimeoutCounter = 0;
uint32_t gFailureCounter = 0;
uint32_t gLastReportMs = 0;

SensorReadout gLastSensor{};
ControlManager::Actuation gLastActuation{};
CommandMessage gLastCommand{};

String gPayload;
String gResponse;
bool gNetworkOk = false;
bool gCommandFresh = false;

const char* stateName(NodeState state) {
  switch (state) {
    case NodeState::INIT:
      return "INIT";
    case NodeState::READ_SENSORS:
      return "READ_SENSORS";
    case NodeState::CONTROL_LOCAL:
      return "CONTROL_LOCAL";
    case NodeState::SEND_DATA:
      return "SEND_DATA";
    case NodeState::WAIT_SERVER:
      return "WAIT_SERVER";
    case NodeState::APPLY_COMMAND:
      return "APPLY_COMMAND";
    case NodeState::WAIT_NEXT:
      return "WAIT_NEXT";
    default:
      return "UNKNOWN";
  }
}

void transitionTo(NodeState next) {
  if (gState == next) {
    return;
  }
  Serial.print("[FSM] ");
  Serial.print(stateName(gState));
  Serial.print(" -> ");
  Serial.println(stateName(next));
  gState = next;
  gStateEnteredMs = millis();
}

void printBootBanner() {
  Serial.println();
  Serial.println("=== AI-IoT Cooperative Cooling Node ===");
  Serial.print("Node: ");
  Serial.println(gConfig.nodeId);
  Serial.print("Device: ");
  Serial.println(gConfig.deviceName);
  Serial.print("IP: ");
  Serial.println(gConfig.ip);
  Serial.print("Server: ");
  Serial.print(gConfig.serverIp);
  Serial.print(":");
  Serial.println(gConfig.serverPort);
  Serial.print("Cooling mode: ");
  Serial.println(gConfig.simulatedCooling ? "SIMULATED" : "DS18B20");
  Serial.println("=======================================");
}

void printPeriodicReport(uint32_t nowMs) {
  if (nowMs - gLastReportMs < 3000) {
    return;
  }
  gLastReportMs = nowMs;

  Serial.print("[STAT] cycle=");
  Serial.print(gCycleCounter);
  Serial.print(" t_hot=");
  Serial.print(gLastSensor.tHotC, 2);
  Serial.print(" t_liquid=");
  Serial.print(gLastSensor.tLiquidC, 2);
  Serial.print(" fan=");
  Serial.print(gLastActuation.fanPwm);
  Serial.print(" pump=");
  Serial.print(gLastActuation.pumpPwm);
  Serial.print(" ack=");
  Serial.print(gAckCounter);
  Serial.print(" timeout=");
  Serial.print(gTimeoutCounter);
  Serial.print(" fail=");
  Serial.print(gFailureCounter);
  Serial.print(" mode=");
  Serial.println(gLastCommand.mode);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  const uint32_t startedAt = millis();
  while (!Serial && (millis() - startedAt < 3000)) {
  }
  printBootBanner();
}

void loop() {
  const uint32_t nowMs = millis();

  switch (gState) {
    case NodeState::INIT: {
      gSensors.begin();
      gControl.begin();
      gNetwork.begin();
      gCycleStartedMs = nowMs;
      transitionTo(NodeState::READ_SENSORS);
      break;
    }

    case NodeState::READ_SENSORS:
      gLastSensor = gSensors.update(nowMs, gControl.fanPwm(), gControl.pumpPwm());
      transitionTo(NodeState::CONTROL_LOCAL);
      break;

    case NodeState::CONTROL_LOCAL: {
      gLastActuation =
          gControl.compute(gLastSensor.tHotC, gLastSensor.tLiquidC, gLastSensor.sensorOk, nowMs);
      gControl.apply(gLastActuation);

      TelemetryMessage telemetry{};
      telemetry.nodeId = gConfig.nodeId;
      telemetry.cycle = gCycleCounter;
      telemetry.uptimeMs = nowMs;
      telemetry.tHotC = gLastSensor.tHotC;
      telemetry.tLiquidC = gLastSensor.tLiquidC;
      telemetry.fanPwm = gLastActuation.fanPwm;
      telemetry.pumpPwm = gLastActuation.pumpPwm;
      telemetry.virtualFlow = gLastSensor.virtualFlow;
      telemetry.sensorOk = gLastSensor.sensorOk;
      telemetry.simulationMode = gConfig.simulatedCooling;
      telemetry.localAnomaly = gLastActuation.localAnomaly;
      telemetry.networkOk = gNetworkOk;
      gPayload = encodeTelemetryJson(telemetry);

      transitionTo(NodeState::SEND_DATA);
      break;
    }

    case NodeState::SEND_DATA:
      gCommandFresh = false;
      if (gNetwork.startRequest(gPayload)) {
        transitionTo(NodeState::WAIT_SERVER);
      } else {
        gNetworkOk = false;
        gFailureCounter++;
        transitionTo(NodeState::WAIT_NEXT);
      }
      break;

    case NodeState::WAIT_SERVER: {
      NetworkManager::PollStatus poll = gNetwork.pollResponse(gResponse);
      if (poll == NetworkManager::PollStatus::PENDING) {
        break;
      }
      if (poll == NetworkManager::PollStatus::COMPLETED) {
        CommandMessage cmd{};
        if (decodeCommandJson(gResponse, cmd)) {
          gLastCommand = cmd;
          gCommandFresh = true;
          gAckCounter++;
          gNetworkOk = true;
        } else {
          gFailureCounter++;
          gNetworkOk = false;
        }
      } else if (poll == NetworkManager::PollStatus::TIMEOUT) {
        gTimeoutCounter++;
        gNetworkOk = false;
      } else {
        gFailureCounter++;
        gNetworkOk = false;
      }
      transitionTo(NodeState::APPLY_COMMAND);
      break;
    }

    case NodeState::APPLY_COMMAND:
      if (gCommandFresh && gLastCommand.valid) {
        ControlManager::RemoteSetpoints remote{};
        remote.valid = true;
        remote.fanPwm = gLastCommand.targetFanPwm;
        remote.pumpPwm = gLastCommand.targetPumpPwm;
        remote.anomaly = gLastCommand.anomaly;
        gControl.setRemoteSetpoints(remote, nowMs);
      }
      transitionTo(NodeState::WAIT_NEXT);
      break;

    case NodeState::WAIT_NEXT:
      if (nowMs - gCycleStartedMs >= gConfig.cycleIntervalMs) {
        gCycleStartedMs = nowMs;
        gCycleCounter++;
        transitionTo(NodeState::READ_SENSORS);
      }
      break;
  }

  printPeriodicReport(nowMs);
}
