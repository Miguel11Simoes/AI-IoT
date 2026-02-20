#pragma once

#include <Arduino.h>

class ControlManager {
 public:
  struct Config {
    uint8_t fanPin;
    uint8_t pumpPin;
    uint8_t minFanPwm;
    uint8_t maxFanPwm;
    uint8_t minPumpPwm;
    uint8_t maxPumpPwm;
    uint32_t remoteTtlMs;
    float anomalyTempC;
    float criticalTempC;
    float maxRiseRateCPerSec;
  };

  struct RemoteSetpoints {
    bool valid = false;
    uint8_t fanPwm = 0;
    uint8_t pumpPwm = 0;
    bool anomaly = false;
  };

  struct Actuation {
    uint8_t fanPwm = 0;
    uint8_t pumpPwm = 0;
    bool localAnomaly = false;
    bool usedRemote = false;
  };

  explicit ControlManager(const Config& config);

  void begin();
  Actuation compute(float tHotC, float tLiquidC, bool sensorOk, uint32_t nowMs);
  void apply(const Actuation& actuation);
  void setRemoteSetpoints(const RemoteSetpoints& remote, uint32_t nowMs);
  uint8_t fanPwm() const;
  uint8_t pumpPwm() const;

 private:
  uint8_t clampPwm(int value, uint8_t minV, uint8_t maxV) const;
  uint8_t localFanFromTemp(float tHotC, float tLiquidC) const;
  uint8_t localPumpFromTemp(float tHotC, float tLiquidC) const;
  bool remoteFresh(uint32_t nowMs) const;

  Config config_;
  RemoteSetpoints remote_;
  uint32_t remoteReceivedAtMs_;
  float lastHotC_;
  uint32_t lastSampleMs_;
  uint8_t appliedFanPwm_;
  uint8_t appliedPumpPwm_;
};
