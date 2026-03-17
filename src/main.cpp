#include <Arduino.h>
#include <math.h>

#include "EdgeNetwork.h"
#include "ProjectConfig.h"
#include "Protocol.h"

#if DEVICE_ROLE == ROLE_RACK
#include "Control.h"
#include "Sensors.h"
#endif

namespace {
uint8_t rampPwm(uint8_t current, uint8_t target, uint8_t step = 5) {
  if (current < target) {
    const int next = current + step;
    return static_cast<uint8_t>(next > target ? target : next);
  }
  if (current > target) {
    const int next = current - step;
    return static_cast<uint8_t>(next < target ? target : next);
  }
  return current;
}

bool pinAvailable(uint8_t pin) { return pin != 0xFF; }
}  // namespace

#if DEVICE_ROLE == ROLE_RACK
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

RackNodeConfig gConfig = loadRackConfig();

SensorManager::Config makeSensorConfig(const RackNodeConfig& cfg) {
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
  return out;
}

ControlManager::Config makeControlConfig(const RackNodeConfig& cfg) {
  ControlManager::Config out{};
  out.heatPin = cfg.heatPin;
  out.minHeatPwm = 0;
  out.maxHeatPwm = 255;
  out.remoteTtlMs = cfg.remoteCmdTtlMs;
  out.anomalyTempC = cfg.anomalyTempC;
  out.criticalTempC = cfg.criticalTempC;
  out.maxRiseRateCPerSec = 5.0f;
  out.heatWindowMs = cfg.heatWindowMs;
  return out;
}

EdgeNetworkManager::Config makeNetworkConfig(const RackNodeConfig& cfg) {
  EdgeNetworkManager::Config out{};
  out.wifiSsid = cfg.wifiSsid;
  out.wifiPassword = cfg.wifiPassword;
  out.serverHost = cfg.serverHost;
  out.edgeWsPort = cfg.edgeWsPort;
  out.edgeWsPath = cfg.edgeWsPath;
  out.responseTimeoutMs = cfg.networkTimeoutMs;
  return out;
}

SensorManager gSensors(makeSensorConfig(gConfig));
ControlManager gControl(makeControlConfig(gConfig));
EdgeNetworkManager gNetwork(makeNetworkConfig(gConfig));

NodeState gState = NodeState::INIT;
uint32_t gCycleStartedMs = 0;
uint32_t gCycleCounter = 0;
uint32_t gAckCounter = 0;
uint32_t gTimeoutCounter = 0;
uint32_t gFailureCounter = 0;
uint32_t gLastReportMs = 0;

SensorReadout gLastSensor{};
ControlManager::Actuation gLastActuation{};
RackCommandMessage gLastCommand{};

String gPayload;
String gResponse;
bool gNetworkOk = false;
bool gCommandFresh = false;
bool gControlReady = false;

void transitionTo(NodeState next) { gState = next; }

void printBootBanner() {
  Serial.println();
  Serial.println("=== AI-IoT Rack Node ===");
  Serial.print("Node: ");
  Serial.println(gConfig.nodeId);
  Serial.print("Rack ID: ");
  Serial.println(gConfig.rackId);
  Serial.print("Host: ");
  Serial.print(gConfig.serverHost);
  Serial.print(":");
  Serial.println(gConfig.edgeWsPort);
  Serial.print("Cooling mode: ");
  Serial.println(gConfig.simulatedCooling ? "SIMULATED" : "DS18B20");
  Serial.println("========================");
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
  if (gLastSensor.liquidAvailable) {
    Serial.print(gLastSensor.tLiquidC, 2);
  } else {
    Serial.print("n/a");
  }
  Serial.print(" heat=");
  Serial.print(gLastActuation.heatPwm);
  Serial.print(" ack=");
  Serial.print(gAckCounter);
  Serial.print(" timeout=");
  Serial.print(gTimeoutCounter);
  Serial.print(" fail=");
  Serial.print(gFailureCounter);
  Serial.print(" mode=");
  Serial.println(gLastCommand.mode);
}

const char* telemetryModeForReadout(const SensorReadout& readout) {
  if (readout.hotSource == TemperatureSource::FALLBACK_SIMULATED) {
    return "sensor_fallback";
  }
  if (readout.hotSource == TemperatureSource::SIMULATED) {
    return "simulated";
  }
  if (readout.hotSource == TemperatureSource::SENSOR &&
      readout.liquidSource == TemperatureSource::UNAVAILABLE) {
    return "measured_hot_only";
  }
  if (readout.hotSource == TemperatureSource::SENSOR &&
      readout.liquidSource == TemperatureSource::SENSOR) {
    return "measured";
  }
  return "mixed";
}

float heaterAveragePowerW(uint8_t heatPwm) {
  return (static_cast<float>(heatPwm) / 255.0f) * gConfig.heaterRatedPowerW;
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
  if (gControlReady) {
    gControl.service(nowMs);
  }

  switch (gState) {
    case NodeState::INIT:
      gSensors.begin();
      gControl.begin();
      gControlReady = true;
      gNetwork.begin();
      gCycleStartedMs = nowMs;
      transitionTo(NodeState::READ_SENSORS);
      break;

    case NodeState::READ_SENSORS:
      gLastSensor = gSensors.update(nowMs, 0, gControl.heatPwm());
      transitionTo(NodeState::CONTROL_LOCAL);
      break;

    case NodeState::CONTROL_LOCAL: {
      gLastActuation =
          gControl.compute(gLastSensor.tHotC, gLastSensor.sensorOk, nowMs);
      gControl.apply(gLastActuation, nowMs);

      RackTelemetryMessage telemetry{};
      telemetry.rackId = gConfig.rackId;
      telemetry.tHotRealC = gLastSensor.tHotC;
      telemetry.tLiquidRealC = gLastSensor.tLiquidC;
      telemetry.hasLiquidReal = gLastSensor.liquidAvailable;
      telemetry.tHotSource = temperatureSourceLabel(gLastSensor.hotSource);
      telemetry.tLiquidSource = temperatureSourceLabel(gLastSensor.liquidSource);
      telemetry.telemetryMode = telemetryModeForReadout(gLastSensor);
      telemetry.sensorOk = gLastSensor.sensorOk;
      telemetry.fanLocalPwm = 0;
      telemetry.heatPwm = gLastActuation.heatPwm;
      telemetry.heaterOn = gControl.heaterOn();
      telemetry.heaterRatedPowerW = gConfig.heaterRatedPowerW;
      telemetry.heaterAvgPowerW = heaterAveragePowerW(gLastActuation.heatPwm);
      telemetry.rssi = gNetwork.rssi();
      telemetry.localAnomaly = gLastActuation.localAnomaly;
      telemetry.tsMs = nowMs;
      gPayload = encodeRackTelemetryJson(telemetry);

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
      EdgeNetworkManager::PollStatus poll = gNetwork.pollResponse(gResponse);
      if (poll == EdgeNetworkManager::PollStatus::PENDING) {
        break;
      }

      if (poll == EdgeNetworkManager::PollStatus::COMPLETED) {
        RackCommandMessage cmd{};
        if (decodeRackCommandJson(gResponse, cmd)) {
          gLastCommand = cmd;
          gCommandFresh = true;
          gAckCounter++;
          gNetworkOk = true;
        } else {
          gFailureCounter++;
          gNetworkOk = false;
        }
      } else if (poll == EdgeNetworkManager::PollStatus::TIMEOUT) {
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
        remote.heatPwm = gLastCommand.heatPwm;
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

#else
namespace {
enum class CduStateFsm : uint8_t { INIT, SEND_DATA, WAIT_SERVER, APPLY_CMD, WAIT_NEXT };

CduConfig gConfig = loadCduConfig();
EdgeNetworkManager gNetwork({gConfig.wifiSsid, gConfig.wifiPassword, gConfig.serverHost,
                             gConfig.edgeWsPort, gConfig.edgeWsPath, gConfig.networkTimeoutMs});

CduStateFsm gState = CduStateFsm::INIT;
uint32_t gCycleStartedMs = 0;
uint32_t gLastCmdMs = 0;
uint32_t gLastLoopMs = 0;
uint32_t gCycleCounter = 0;

uint8_t gFanACurrent = 160;
uint8_t gFanBCurrent = 160;
uint8_t gFanATarget = 160;
uint8_t gFanBTarget = 160;
bool gPeltierACurrent = false;
bool gPeltierBCurrent = false;
bool gPeltierATarget = false;
bool gPeltierBTarget = false;
float gSupplyA = 29.0f;
float gSupplyB = 30.0f;
float gSupplyTarget = 29.5f;

String gPayload;
String gResponse;
CduCommandMessage gLastCommand{};

uint8_t applyFan(uint8_t pin, uint8_t current, uint8_t target) {
  if (!pinAvailable(pin)) {
    return 0;
  }
  const uint8_t next = rampPwm(current, target, 4);
  analogWrite(pin, next);
  return next;
}

void applyFans() {
  gFanACurrent = applyFan(gConfig.fanAPin, gFanACurrent, gFanATarget);
  gFanBCurrent = applyFan(gConfig.fanBPin, gFanBCurrent, gFanBTarget);
}

void writePeltier(uint8_t pin, bool enabled) {
  if (!pinAvailable(pin)) {
    return;
  }
  const bool activeHigh = gConfig.peltierActiveHigh;
  digitalWrite(pin, (enabled == activeHigh) ? HIGH : LOW);
}

void writePeltierFan(uint8_t pin, bool enabled) {
  if (!pinAvailable(pin)) {
    return;
  }
  const bool activeHigh = gConfig.peltierFanActiveHigh;
  digitalWrite(pin, (enabled == activeHigh) ? HIGH : LOW);
}

void applyPeltiers() {
  gPeltierACurrent = gPeltierATarget;
  gPeltierBCurrent = gPeltierBTarget;
  writePeltier(gConfig.peltierAPin, gPeltierACurrent);
  writePeltier(gConfig.peltierBPin, gPeltierBCurrent);
  writePeltierFan(gConfig.peltierFanAPin, gPeltierACurrent);
  writePeltierFan(gConfig.peltierFanBPin, gPeltierBCurrent);
}

void updateVirtualSupply(float dtSec) {
  const float peltierBoostA = gPeltierACurrent ? 0.95f : 0.0f;
  const float peltierBoostB = gPeltierBCurrent ? 0.95f : 0.0f;
  const float coolA = (static_cast<float>(gFanACurrent) / 255.0f) * 1.8f + peltierBoostA;
  const float coolB = (static_cast<float>(gFanBCurrent) / 255.0f) * 1.8f + peltierBoostB;
  const float loadA = 1.3f;
  const float loadB = 1.3f;

  gSupplyA += (loadA - coolA) * 0.12f * dtSec;
  gSupplyB += (loadB - coolB) * 0.12f * dtSec;
  gSupplyA = constrain(gSupplyA, 18.0f, 45.0f);
  gSupplyB = constrain(gSupplyB, 18.0f, 45.0f);
}

void applyFallbackIfStale(uint32_t nowMs) {
  if (nowMs - gLastCmdMs <= gConfig.remoteCmdTtlMs) {
    return;
  }
  const float avgSupply = (gSupplyA + gSupplyB) * 0.5f;
  const float err = avgSupply - gSupplyTarget;
  const int correction = static_cast<int>(err * 15.0f);
  gFanATarget = static_cast<uint8_t>(constrain(160 + correction, 120, 220));
  gFanBTarget = static_cast<uint8_t>(constrain(160 + correction, 120, 220));
  gPeltierATarget = gSupplyA >= (gSupplyTarget + 3.0f);
  gPeltierBTarget = gSupplyB >= (gSupplyTarget + 3.0f);
}
}  // namespace

void setup() {
  Serial.begin(115200);
  if (pinAvailable(gConfig.fanAPin)) {
    pinMode(gConfig.fanAPin, OUTPUT);
  }
  if (pinAvailable(gConfig.fanBPin)) {
    pinMode(gConfig.fanBPin, OUTPUT);
  }
  if (pinAvailable(gConfig.peltierAPin)) {
    pinMode(gConfig.peltierAPin, OUTPUT);
  }
  if (pinAvailable(gConfig.peltierBPin)) {
    pinMode(gConfig.peltierBPin, OUTPUT);
  }
  if (pinAvailable(gConfig.peltierFanAPin)) {
    pinMode(gConfig.peltierFanAPin, OUTPUT);
  }
  if (pinAvailable(gConfig.peltierFanBPin)) {
    pinMode(gConfig.peltierFanBPin, OUTPUT);
  }
  if (pinAvailable(gConfig.fanAPin)) {
    analogWrite(gConfig.fanAPin, gFanACurrent);
  } else {
    gFanACurrent = 0;
    gFanATarget = 0;
  }
  if (pinAvailable(gConfig.fanBPin)) {
    analogWrite(gConfig.fanBPin, gFanBCurrent);
  } else {
    gFanBCurrent = 0;
    gFanBTarget = 0;
  }
  writePeltier(gConfig.peltierAPin, false);
  writePeltier(gConfig.peltierBPin, false);
  writePeltierFan(gConfig.peltierFanAPin, false);
  writePeltierFan(gConfig.peltierFanBPin, false);
  gNetwork.begin();
  const uint32_t nowMs = millis();
  gCycleStartedMs = nowMs;
  gLastCmdMs = nowMs;
  gLastLoopMs = nowMs;
  Serial.println("=== AI-IoT CDU Controller ===");
}

void loop() {
  const uint32_t nowMs = millis();
  uint32_t elapsedMs = nowMs - gLastLoopMs;
  if (elapsedMs == 0 || elapsedMs > 5000U) {
    elapsedMs = 1U;
  }
  const float dtSec = static_cast<float>(elapsedMs) / 1000.0f;
  gLastLoopMs = nowMs;
  updateVirtualSupply(dtSec);
  applyFallbackIfStale(nowMs);
  applyFans();
  applyPeltiers();

  switch (gState) {
    case CduStateFsm::INIT:
      gState = CduStateFsm::SEND_DATA;
      break;

    case CduStateFsm::SEND_DATA: {
      CduTelemetryMessage telemetry{};
      telemetry.cduId = gConfig.cduId;
      telemetry.fanAPwm = gFanACurrent;
      telemetry.fanBPwm = gFanBCurrent;
      telemetry.peltierAOn = gPeltierACurrent;
      telemetry.peltierBOn = gPeltierBCurrent;
      telemetry.tSupplyA = gSupplyA;
      telemetry.tSupplyB = gSupplyB;
      telemetry.tsMs = nowMs;
      gPayload = encodeCduTelemetryJson(telemetry);

      if (gNetwork.startRequest(gPayload)) {
        gState = CduStateFsm::WAIT_SERVER;
      } else {
        gState = CduStateFsm::WAIT_NEXT;
      }
      break;
    }

    case CduStateFsm::WAIT_SERVER: {
      EdgeNetworkManager::PollStatus poll = gNetwork.pollResponse(gResponse);
      if (poll == EdgeNetworkManager::PollStatus::PENDING) {
        break;
      }
      if (poll == EdgeNetworkManager::PollStatus::COMPLETED) {
        CduCommandMessage cmd{};
        if (decodeCduCommandJson(gResponse, cmd) && cmd.valid) {
          gLastCommand = cmd;
          gState = CduStateFsm::APPLY_CMD;
        } else {
          gState = CduStateFsm::WAIT_NEXT;
        }
      } else {
        gState = CduStateFsm::WAIT_NEXT;
      }
      break;
    }

    case CduStateFsm::APPLY_CMD:
      gFanATarget = gLastCommand.fanAPwm;
      gFanBTarget = gLastCommand.fanBPwm;
      gPeltierATarget = gLastCommand.peltierAOn;
      gPeltierBTarget = gLastCommand.peltierBOn;
      if (gLastCommand.hasSupplyTarget && isfinite(gLastCommand.tSupplyTarget)) {
        gSupplyTarget = constrain(gLastCommand.tSupplyTarget, 18.0f, 45.0f);
      }
      gLastCmdMs = nowMs;
      gState = CduStateFsm::WAIT_NEXT;
      break;

    case CduStateFsm::WAIT_NEXT:
      if (nowMs - gCycleStartedMs >= gConfig.cycleIntervalMs) {
        gCycleStartedMs = nowMs;
        gCycleCounter++;
        gState = CduStateFsm::SEND_DATA;
      }
      break;
  }
}
#endif
