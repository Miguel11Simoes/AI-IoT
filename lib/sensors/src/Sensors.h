#pragma once

#include <Arduino.h>
#include <DallasTemperature.h>
#include <OneWire.h>

enum class TemperatureSource : uint8_t {
  SIMULATED = 0,
  SENSOR = 1,
  ESTIMATED = 2,
  FALLBACK_SIMULATED = 3,
  UNAVAILABLE = 4,
};

struct SensorReadout {
  float tHotC = 0.0f;
  float tLiquidC = 0.0f;
  bool sensorOk = false;
  bool liquidAvailable = false;
  TemperatureSource hotSource = TemperatureSource::SIMULATED;
  TemperatureSource liquidSource = TemperatureSource::SIMULATED;
};

class SensorManager {
 public:
  static constexpr uint8_t kSensorResolutionBits = 10;
  static constexpr uint32_t kConversionTimeMs = 188;

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
  };

  explicit SensorManager(const Config& config);

  void begin();
  SensorReadout update(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm);
  bool simulationMode() const;

 private:
  SensorReadout updateSimulated(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm,
                                bool sensorOkValue);
  SensorReadout updateFromHardware(uint32_t nowMs, uint8_t fanPwm, uint8_t heatPwm);
  bool validTemperature(float value) const;
  float clampFloat(float value, float minV, float maxV) const;

  Config config_;
  OneWire oneWire_;
  DallasTemperature dallas_;
  uint32_t lastUpdateMs_;
  uint32_t conversionReadyAtMs_;
  bool conversionPending_;
  bool haveHardwareReadout_;
  SensorReadout lastHardwareReadout_;
  float simulatedHotC_;
  float simulatedLiquidC_;
};

const char* temperatureSourceLabel(TemperatureSource source);
