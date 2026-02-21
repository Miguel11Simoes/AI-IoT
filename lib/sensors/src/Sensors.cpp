#include "Sensors.h"

SensorManager::SensorManager(const Config& config)
    : config_(config),
      oneWire_(config.oneWirePin),
      dallas_(&oneWire_),
      lastUpdateMs_(0),
      simulatedHotC_(config.initialHotC),
      simulatedLiquidC_(config.initialLiquidC) {}

void SensorManager::begin() {
  lastUpdateMs_ = millis();
  simulatedHotC_ = config_.initialHotC;
  simulatedLiquidC_ = config_.initialLiquidC;

  if (!config_.simulationMode) {
    dallas_.begin();
    dallas_.setResolution(10);
  }
}

SensorReadout SensorManager::update(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm,
                                    uint8_t pumpPwm) {
  if (config_.simulationMode) {
    return updateSimulated(nowMs, fanPwm, heatPwm, pumpPwm, true);
  }
  return updateFromHardware(nowMs, fanPwm, heatPwm, pumpPwm);
}

bool SensorManager::simulationMode() const { return config_.simulationMode; }

SensorReadout SensorManager::updateSimulated(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm,
                                             uint8_t pumpPwm, bool sensorOkValue) {
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
  const float flowNorm = static_cast<float>(pumpPwm) / 255.0f;

  const float hotMinusLiquid = simulatedHotC_ - simulatedLiquidC_;
  const float hotMinusAmbient = simulatedHotC_ - config_.ambientC;
  const float liquidMinusAmbient = simulatedLiquidC_ - config_.ambientC;

  const float hotToLiquid = config_.hotToLiquidCoeff * hotMinusLiquid;
  const float hotToAmbient =
      config_.hotToAmbientCoeff * (0.2f + fanNorm) * hotMinusAmbient;
  const float flowCooling = config_.flowCoolingCoeff * flowNorm * hotMinusLiquid;
  const float liquidToAmbient =
      config_.liquidToAmbientCoeff * (0.2f + fanNorm) * liquidMinusAmbient;

  const float heatGain = config_.heatGainCPerSec * (0.45f + heatNorm * 1.2f);
  const float dHot = heatGain - hotToAmbient - hotToLiquid - (0.45f * flowCooling);
  const float dLiquid = hotToLiquid + flowCooling - liquidToAmbient;

  simulatedHotC_ += dHot * dtSec;
  simulatedLiquidC_ += dLiquid * dtSec;

  if (simulatedLiquidC_ > simulatedHotC_ - 0.1f) {
    simulatedLiquidC_ = simulatedHotC_ - 0.1f;
  }

  simulatedHotC_ = clampFloat(simulatedHotC_, config_.ambientC - 2.0f, 130.0f);
  simulatedLiquidC_ = clampFloat(simulatedLiquidC_, config_.ambientC - 2.0f, 120.0f);

  SensorReadout out{};
  out.tHotC = simulatedHotC_;
  out.tLiquidC = simulatedLiquidC_;
  out.sensorOk = sensorOkValue;
  out.virtualFlow = flowNorm;
  return out;
}

SensorReadout SensorManager::updateFromHardware(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm,
                                                uint8_t pumpPwm) {
  dallas_.requestTemperatures();
  const float hot = dallas_.getTempCByIndex(0);
  const float liquid = dallas_.getTempCByIndex(1);
  const float fanNorm = static_cast<float>(fanPwm) / 255.0f;
  const float flowNorm = static_cast<float>(pumpPwm) / 255.0f;

  const bool hotValid = validTemperature(hot);
  const bool liquidValid = validTemperature(liquid);
  if (hotValid) {
    simulatedHotC_ = hot;
    if (liquidValid) {
      simulatedLiquidC_ = liquid;
    } else {
      // With one DS18B20 physically mounted, estimate liquid temperature as a
      // damped virtual state tied to hot temperature and cooling effort.
      float targetDelta = 4.8f - (1.7f * flowNorm) - (0.9f * fanNorm);
      targetDelta = clampFloat(targetDelta, 2.0f, 8.5f);
      const float targetLiquid = simulatedHotC_ - targetDelta;
      simulatedLiquidC_ += (targetLiquid - simulatedLiquidC_) * 0.22f;
    }
    float liqMin = config_.ambientC - 2.0f;
    float liqMax = simulatedHotC_ - 0.1f;
    if (liqMax <= liqMin) {
      liqMin = liqMax - 0.5f;
    }
    simulatedLiquidC_ = clampFloat(simulatedLiquidC_, liqMin, liqMax);
    lastUpdateMs_ = nowMs;

    SensorReadout out{};
    out.tHotC = simulatedHotC_;
    out.tLiquidC = simulatedLiquidC_;
    out.sensorOk = true;
    out.virtualFlow = flowNorm;
    return out;
  }

  return updateSimulated(nowMs, fanPwm, heatPwm, pumpPwm, false);
}

bool SensorManager::validTemperature(float value) const {
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
