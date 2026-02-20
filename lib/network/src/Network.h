#pragma once

#include <Arduino.h>
#include <Ethernet.h>
#include <SPI.h>

class NetworkManager {
 public:
  struct Config {
    uint8_t mac[6];
    IPAddress ip;
    IPAddress dns;
    IPAddress gateway;
    IPAddress subnet;
    IPAddress serverIp;
    uint16_t serverPort;
    uint8_t csPin;
    uint8_t resetPin;
    uint8_t sckPin;
    uint8_t misoPin;
    uint8_t mosiPin;
    uint32_t responseTimeoutMs;
  };

  enum class PollStatus : uint8_t { IDLE, PENDING, COMPLETED, FAILED, TIMEOUT };

  explicit NetworkManager(const Config& config);

  void begin();
  bool ready() const;
  bool linkUp() const;
  bool startRequest(const String& payloadLine);
  PollStatus pollResponse(String& responseLine);
  void close();
  EthernetHardwareStatus hardwareStatus() const;

 private:
  void configureSpi() const;
  void resetW5500() const;

  Config config_;
  EthernetClient client_;
  bool ready_;
  bool active_;
  uint32_t requestStartedMs_;
  String rxBuffer_;
};
