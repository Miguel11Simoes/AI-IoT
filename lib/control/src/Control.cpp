#include "Control.h"

ControlManager::ControlManager(const Config& config)
    : config_(config),
      remote_(),
      remoteReceivedAtMs_(0),
      lastHotC_(0.0f),
      lastSampleMs_(0),
      appliedHeatPwm_(0),
      heatWindowStartMs_(0),
      heaterOn_(false) {}

void ControlManager::begin() {
  pinMode(config_.heatPin, OUTPUT);
  appliedHeatPwm_ = config_.minHeatPwm;
  heatWindowStartMs_ = millis();
  heaterOn_ = false;
  digitalWrite(config_.heatPin, LOW);
  lastSampleMs_ = millis();
}

ControlManager::Actuation ControlManager::compute(float tHotC, float tLiquidC, bool sensorOk,
                                                  uint32_t nowMs) {
  Actuation out{};
  uint8_t heat = localHeatFromTemp(tHotC, tLiquidC);

  float riseRate = 0.0f;
  if (lastSampleMs_ > 0 && nowMs > lastSampleMs_) {
    const float dtSec = static_cast<float>(nowMs - lastSampleMs_) / 1000.0f;
    if (dtSec > 0.01f) {
      riseRate = (tHotC - lastHotC_) / dtSec;
    }
  }
  lastSampleMs_ = nowMs;
  lastHotC_ = tHotC;

  const bool localFault = (!sensorOk) || (tHotC >= config_.anomalyTempC) ||
                          (riseRate >= config_.maxRiseRateCPerSec);
  if (localFault) {
    out.localAnomaly = true;
    heat = config_.minHeatPwm;
  }

  if (remote_.valid && remoteFresh(nowMs)) {
    const int blendedHeat = static_cast<int>((heat * 4 + remote_.heatPwm * 6) / 10);
    heat = clampPwm(blendedHeat, config_.minHeatPwm, config_.maxHeatPwm);
    out.usedRemote = true;

    if (remote_.anomaly) {
      heat = config_.minHeatPwm;
    }
  }

  if (tHotC >= config_.criticalTempC) {
    heat = config_.minHeatPwm;
    out.localAnomaly = true;
  }

  out.heatPwm = heat;
  return out;
}

void ControlManager::apply(const Actuation& actuation, uint32_t nowMs) {
  appliedHeatPwm_ = actuation.heatPwm;
  service(nowMs);
}

void ControlManager::service(uint32_t nowMs) {
  const uint16_t windowMs = config_.heatWindowMs > 0 ? config_.heatWindowMs : 2000;
  const uint32_t elapsed = nowMs - heatWindowStartMs_;
  if (elapsed >= windowMs) {
    heatWindowStartMs_ = nowMs - (elapsed % windowMs);
  }

  const uint32_t onMs =
      (static_cast<uint32_t>(appliedHeatPwm_) * static_cast<uint32_t>(windowMs)) / 255UL;
  const bool shouldBeOn = (nowMs - heatWindowStartMs_) < onMs;
  if (shouldBeOn != heaterOn_) {
    heaterOn_ = shouldBeOn;
    digitalWrite(config_.heatPin, heaterOn_ ? HIGH : LOW);
  }
}

void ControlManager::setRemoteSetpoints(const RemoteSetpoints& remote, uint32_t nowMs) {
  remote_ = remote;
  remoteReceivedAtMs_ = nowMs;
}

uint8_t ControlManager::heatPwm() const { return appliedHeatPwm_; }

uint8_t ControlManager::clampPwm(int value, uint8_t minV, uint8_t maxV) const {
  if (value < minV) {
    return minV;
  }
  if (value > maxV) {
    return maxV;
  }
  return static_cast<uint8_t>(value);
}

uint8_t ControlManager::localHeatFromTemp(float tHotC, float tLiquidC) const {
  const float delta = tHotC - tLiquidC;
  const int raw = static_cast<int>(190.0f - (tHotC - 40.0f) * 4.0f - delta * 2.5f);
  return clampPwm(raw, config_.minHeatPwm, config_.maxHeatPwm);
}

bool ControlManager::remoteFresh(uint32_t nowMs) const {
  if (!remote_.valid) {
    return false;
  }
  return (nowMs - remoteReceivedAtMs_) <= config_.remoteTtlMs;
}
