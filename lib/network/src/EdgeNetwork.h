#pragma once

#include <Arduino.h>
#include <WebSocketsClient.h>

#if defined(ARDUINO_ARCH_ESP8266)
#include <ESP8266WiFi.h>
#else
#include <WiFi.h>
#endif

class EdgeNetworkManager {
 public:
  struct Config {
    const char* wifiSsid;
    const char* wifiPassword;
    const char* serverHost;
    uint16_t edgeWsPort;
    const char* edgeWsPath;
    uint32_t responseTimeoutMs;
  };

  enum class PollStatus : uint8_t { IDLE, PENDING, COMPLETED, FAILED, TIMEOUT };

  explicit EdgeNetworkManager(const Config& config);

  void begin();
  bool ready() const;
  bool linkUp() const;
  bool startRequest(const String& payloadLine);
  PollStatus pollResponse(String& responseLine);
  void close();
  int32_t rssi() const;

 private:
  void maintainConnectivity();
  void enqueueRx(const String& text);
  bool popRx(String& outText);
  void onWsEvent(WStype_t type, uint8_t* payload, size_t length);

  static constexpr uint8_t kQueueSize = 6;

  Config config_;
  WebSocketsClient wsClient_;
  bool initialized_;
  bool wsConnected_;
  bool requestActive_;
  uint32_t requestStartedMs_;
  uint32_t lastWifiAttemptMs_;
  uint32_t lastWsBeginMs_;

  String rxQueue_[kQueueSize];
  uint8_t rxHead_;
  uint8_t rxTail_;
  uint8_t rxCount_;
};
