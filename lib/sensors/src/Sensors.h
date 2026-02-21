#pragma once

#include <Arduino.h>
#include <DallasTemperature.h>
#include <OneWire.h>

struct SensorReadout {
  float tHotC = 0.0f;
  float tLiquidC = 0.0f;
  bool sensorOk = false;
  float virtualFlow = 0.0f;
};

class SensorManager {
 public:
  struct Config {
    uint8_t oneWirePin;
    bool simulationMode;
    float ambientC;
    float initialHotC;
    float initialLiquidC;
    float heatGainCPerSec;
    float hotToLiquidCoeff;
    float hotToAmbientCoeff;
    float liquidToAmbientCoeff;
    float flowCoolingCoeff;
  };

  explicit SensorManager(const Config& config);

  void begin();
  SensorReadout update(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm, uint8_t pumpPwm);
  bool simulationMode() const;

 private:
  SensorReadout updateSimulated(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm, uint8_t pumpPwm,
                                bool sensorOkValue);
  SensorReadout updateFromHardware(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm,
                                   uint8_t pumpPwm);
  bool validTemperature(float value) const;
  float clampFloat(float value, float minV, float maxV) const;

  Config config_;
  OneWire oneWire_;
  DallasTemperature dallas_;
  uint32_t lastUpdateMs_;
  float simulatedHotC_;
  float simulatedLiquidC_;
};
