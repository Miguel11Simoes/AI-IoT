#include "Control.h"

ControlManager::ControlManager(const Config& config)
    : config_(config),
      remote_(),
      remoteReceivedAtMs_(0),
      lastHotC_(0.0f),
      lastSampleMs_(0),
      appliedFanPwm_(0),
      appliedPumpPwm_(0) {}

void ControlManager::begin() {
  pinMode(config_.fanPin, OUTPUT);
  pinMode(config_.pumpPin, OUTPUT);
  appliedFanPwm_ = config_.minFanPwm;
  appliedPumpPwm_ = config_.minPumpPwm;
  analogWrite(config_.fanPin, appliedFanPwm_);
  analogWrite(config_.pumpPin, appliedPumpPwm_);
  lastSampleMs_ = millis();
}

ControlManager::Actuation ControlManager::compute(float tHotC, float tLiquidC, bool sensorOk,
                                                  uint32_t nowMs) {
  Actuation out{};
  uint8_t fan = localFanFromTemp(tHotC, tLiquidC);
  uint8_t pump = localPumpFromTemp(tHotC, tLiquidC);

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
    fan = config_.maxFanPwm;
    pump = config_.maxPumpPwm;
  }

  if (remote_.valid && remoteFresh(nowMs)) {
    const int blendedFan = static_cast<int>((fan * 4 + remote_.fanPwm * 6) / 10);
    const int blendedPump = static_cast<int>((pump * 4 + remote_.pumpPwm * 6) / 10);
    fan = clampPwm(blendedFan, config_.minFanPwm, config_.maxFanPwm);
    pump = clampPwm(blendedPump, config_.minPumpPwm, config_.maxPumpPwm);
    out.usedRemote = true;

    if (remote_.anomaly) {
      fan = config_.maxFanPwm;
      pump = config_.maxPumpPwm;
    }
  }

  if (tHotC >= config_.criticalTempC) {
    fan = config_.maxFanPwm;
    pump = config_.maxPumpPwm;
    out.localAnomaly = true;
  }

  out.fanPwm = fan;
  out.pumpPwm = pump;
  return out;
}

void ControlManager::apply(const Actuation& actuation) {
  appliedFanPwm_ = actuation.fanPwm;
  appliedPumpPwm_ = actuation.pumpPwm;
  analogWrite(config_.fanPin, appliedFanPwm_);
  analogWrite(config_.pumpPin, appliedPumpPwm_);
}

void ControlManager::setRemoteSetpoints(const RemoteSetpoints& remote, uint32_t nowMs) {
  remote_ = remote;
  remoteReceivedAtMs_ = nowMs;
}

uint8_t ControlManager::fanPwm() const { return appliedFanPwm_; }

uint8_t ControlManager::pumpPwm() const { return appliedPumpPwm_; }

uint8_t ControlManager::clampPwm(int value, uint8_t minV, uint8_t maxV) const {
  if (value < minV) {
    return minV;
  }
  if (value > maxV) {
    return maxV;
  }
  return static_cast<uint8_t>(value);
}

uint8_t ControlManager::localFanFromTemp(float tHotC, float tLiquidC) const {
  const float delta = tHotC - tLiquidC;
  const int raw = static_cast<int>(90.0f + (tHotC - 30.0f) * 3.5f + delta * 3.0f);
  return clampPwm(raw, config_.minFanPwm, config_.maxFanPwm);
}

uint8_t ControlManager::localPumpFromTemp(float tHotC, float tLiquidC) const {
  const float delta = tHotC - tLiquidC;
  const int raw = static_cast<int>(80.0f + (tHotC - 30.0f) * 3.0f + delta * 2.0f);
  return clampPwm(raw, config_.minPumpPwm, config_.maxPumpPwm);
}

bool ControlManager::remoteFresh(uint32_t nowMs) const {
  if (!remote_.valid) {
    return false;
  }
  return (nowMs - remoteReceivedAtMs_) <= config_.remoteTtlMs;
}
