#include "Sensors.h"

#include <math.h>

namespace {
TemperatureSource simulatedSource(bool nominalSimulation) {
  return nominalSimulation ? TemperatureSource::SIMULATED : TemperatureSource::FALLBACK_SIMULATED;
}
}  // namespace

SensorManager::SensorManager(const Config& config)
    : config_(config),
      oneWire_(config.oneWirePin),
      dallas_(&oneWire_),
      lastUpdateMs_(0),
      conversionReadyAtMs_(0),
      conversionPending_(false),
      haveHardwareReadout_(false),
      lastHardwareReadout_(),
      simulatedHotC_(config.initialHotC),
      simulatedLiquidC_(config.initialLiquidC) {}

void SensorManager::begin() {
  lastUpdateMs_ = millis();
  simulatedHotC_ = config_.initialHotC;
  simulatedLiquidC_ = config_.initialLiquidC;

  if (!config_.simulationMode) {
    dallas_.begin();
    dallas_.setResolution(kSensorResolutionBits);
    dallas_.setWaitForConversion(false);
    dallas_.requestTemperatures();
    conversionReadyAtMs_ = lastUpdateMs_ + kConversionTimeMs;
    conversionPending_ = true;
    haveHardwareReadout_ = false;
  }
}

SensorReadout SensorManager::update(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm) {
  if (config_.simulationMode) {
    return updateSimulated(nowMs, fanPwm, heatPwm, true);
  }
  return updateFromHardware(nowMs, fanPwm, heatPwm);
}

bool SensorManager::simulationMode() const { return config_.simulationMode; }

SensorReadout SensorManager::updateSimulated(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm,
                                             bool sensorOkValue) {
  const uint32_t elapsedMs = nowMs - lastUpdateMs_;
  float dtSec = static_cast<float>(elapsedMs) / 1000.0f;
  if (dtSec < 0.05f) {
    dtSec = 0.05f;
  }
  if (dtSec > 2.0f) {
    dtSec = 2.0f;
  }
  lastUpdateMs_ = nowMs;

  const float fanNorm = static_cast<float>(fanPwm) / 255.0f;
  const float heatNorm = static_cast<float>(heatPwm) / 255.0f;

  const float hotMinusLiquid = simulatedHotC_ - simulatedLiquidC_;
  const float hotMinusAmbient = simulatedHotC_ - config_.ambientC;
  const float liquidMinusAmbient = simulatedLiquidC_ - config_.ambientC;

  const float hotToLiquid = config_.hotToLiquidCoeff * hotMinusLiquid;
  const float hotToAmbient =
      config_.hotToAmbientCoeff * (0.2f + fanNorm) * hotMinusAmbient;
  const float liquidToAmbient =
      config_.liquidToAmbientCoeff * (0.2f + fanNorm) * liquidMinusAmbient;

  const float heatGain = config_.heatGainCPerSec * (0.45f + heatNorm * 1.2f);
  const float dHot = heatGain - hotToAmbient - hotToLiquid;
  const float dLiquid = hotToLiquid - liquidToAmbient;

  simulatedHotC_ += dHot * dtSec;
  simulatedLiquidC_ += dLiquid * dtSec;

  if (simulatedLiquidC_ > simulatedHotC_ - 0.1f) {
    simulatedLiquidC_ = simulatedHotC_ - 0.1f;
  }

  simulatedHotC_ = clampFloat(simulatedHotC_, config_.ambientC - 2.0f, 130.0f);
  simulatedLiquidC_ = clampFloat(simulatedLiquidC_, config_.ambientC - 2.0f, 120.0f);

  SensorReadout out{};
  out.tHotC = simulatedHotC_;
  out.sensorOk = sensorOkValue;
  out.hotSource = simulatedSource(sensorOkValue);
  if (sensorOkValue) {
    out.tLiquidC = simulatedLiquidC_;
    out.liquidAvailable = true;
    out.liquidSource = simulatedSource(sensorOkValue);
  } else {
    out.tLiquidC = 0.0f;
    out.liquidAvailable = false;
    out.liquidSource = TemperatureSource::UNAVAILABLE;
  }
  return out;
}

SensorReadout SensorManager::updateFromHardware(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm) {
  if (!conversionPending_) {
    dallas_.requestTemperatures();
    conversionReadyAtMs_ = nowMs + kConversionTimeMs;
    conversionPending_ = true;
  }

  if (static_cast<int32_t>(nowMs - conversionReadyAtMs_) < 0) {
    if (haveHardwareReadout_) {
      return lastHardwareReadout_;
    }
    return updateSimulated(nowMs, fanPwm, heatPwm, false);
  }

  const float hot = dallas_.getTempCByIndex(0);

  dallas_.requestTemperatures();
  conversionReadyAtMs_ = nowMs + kConversionTimeMs;
  conversionPending_ = true;

  const bool hotValid = validTemperature(hot);
  if (hotValid) {
    simulatedHotC_ = hot;
    lastUpdateMs_ = nowMs;

    SensorReadout out{};
    out.tHotC = simulatedHotC_;
    out.tLiquidC = 0.0f;
    out.sensorOk = true;
    out.liquidAvailable = false;
    out.hotSource = TemperatureSource::SENSOR;
    out.liquidSource = TemperatureSource::UNAVAILABLE;
    lastHardwareReadout_ = out;
    haveHardwareReadout_ = true;
    return out;
  }

  haveHardwareReadout_ = false;
  return updateSimulated(nowMs, fanPwm, heatPwm, false);
}

bool SensorManager::validTemperature(float value) const {
  if (!isfinite(value)) {
    return false;
  }
  if (value <= -100.0f || value >= 130.0f) {
    return false;
  }
  if (value == DEVICE_DISCONNECTED_C) {
    return false;
  }
  return true;
}

float SensorManager::clampFloat(float value, float minV, float maxV) const {
  if (value < minV) {
    return minV;
  }
  if (value > maxV) {
    return maxV;
  }
  return value;
}

const char* temperatureSourceLabel(TemperatureSource source) {
  switch (source) {
    case TemperatureSource::SENSOR:
      return "sensor";
    case TemperatureSource::ESTIMATED:
      return "estimated";
    case TemperatureSource::FALLBACK_SIMULATED:
      return "fallback_simulated";
    case TemperatureSource::UNAVAILABLE:
      return "unavailable";
    case TemperatureSource::SIMULATED:
    default:
      return "simulated";
  }
}
