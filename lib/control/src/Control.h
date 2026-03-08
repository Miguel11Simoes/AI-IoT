#pragma once

#include <Arduino.h>

class ControlManager {
 public:
  struct Config {
    uint8_t heatPin;
    uint8_t minHeatPwm;
    uint8_t maxHeatPwm;
    uint32_t remoteTtlMs;
    float anomalyTempC;
    float criticalTempC;
    float maxRiseRateCPerSec;
    uint16_t heatWindowMs;
  };

  struct RemoteSetpoints {
    bool valid = false;
    uint8_t heatPwm = 0;
    bool anomaly = false;
  };

  struct Actuation {
    uint8_t heatPwm = 0;
    bool localAnomaly = false;
    bool usedRemote = false;
  };

  explicit ControlManager(const Config& config);

  void begin();
  Actuation compute(float tHotC, float tLiquidC, bool sensorOk, uint32_t nowMs);
  void apply(const Actuation& actuation, uint32_t nowMs);
  void service(uint32_t nowMs);
  void setRemoteSetpoints(const RemoteSetpoints& remote, uint32_t nowMs);
  uint8_t heatPwm() const;

 private:
  uint8_t clampPwm(int value, uint8_t minV, uint8_t maxV) const;
  uint8_t localHeatFromTemp(float tHotC, float tLiquidC) const;
  bool remoteFresh(uint32_t nowMs) const;

  Config config_;
  RemoteSetpoints remote_;
  uint32_t remoteReceivedAtMs_;
  float lastHotC_;
  uint32_t lastSampleMs_;
  uint8_t appliedHeatPwm_;
  uint32_t heatWindowStartMs_;
  bool heaterOn_;
};
