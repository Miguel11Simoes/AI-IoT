#include "Network.h"

NetworkManager::NetworkManager(const Config& config)
    : config_(config), client_(), ready_(false), active_(false), requestStartedMs_(0), rxBuffer_() {}

void NetworkManager::configureSpi() const {
#if defined(ARDUINO_ARCH_ESP32)
  SPI.begin(config_.sckPin, config_.misoPin, config_.mosiPin, config_.csPin);
#else
  SPI.begin();
#endif
}

void NetworkManager::resetW5500() const {
  pinMode(config_.resetPin, OUTPUT);
  digitalWrite(config_.resetPin, HIGH);
  delay(2);
  digitalWrite(config_.resetPin, LOW);
  delay(40);
  digitalWrite(config_.resetPin, HIGH);
  delay(120);
}

void NetworkManager::begin() {
  configureSpi();
  resetW5500();

  Ethernet.init(config_.csPin);
  Ethernet.begin(config_.mac, config_.ip, config_.dns, config_.gateway, config_.subnet);
  ready_ = (hardwareStatus() != EthernetNoHardware);
}

bool NetworkManager::ready() const { return ready_; }

bool NetworkManager::linkUp() const {
  const EthernetLinkStatus link = Ethernet.linkStatus();
  if (link == Unknown) {
    return ready_;
  }
  return link == LinkON;
}

bool NetworkManager::startRequest(const String& payloadLine) {
  if (!ready_ || active_) {
    return false;
  }
  if (!linkUp()) {
    return false;
  }

  if (!client_.connect(config_.serverIp, config_.serverPort)) {
    return false;
  }

  client_.print(payloadLine);
  client_.print('\n');
  active_ = true;
  requestStartedMs_ = millis();
  rxBuffer_.remove(0);
  return true;
}

NetworkManager::PollStatus NetworkManager::pollResponse(String& responseLine) {
  if (!active_) {
    return PollStatus::IDLE;
  }

  while (client_.available() > 0) {
    const char ch = static_cast<char>(client_.read());
    if (ch == '\r') {
      continue;
    }
    if (ch == '\n') {
      if (rxBuffer_.length() == 0) {
        continue;
      }
      responseLine = rxBuffer_;
      close();
      return PollStatus::COMPLETED;
    }
    rxBuffer_ += ch;
    if (rxBuffer_.length() > 512) {
      rxBuffer_.remove(0);
    }
  }

  if (millis() - requestStartedMs_ >= config_.responseTimeoutMs) {
    close();
    return PollStatus::TIMEOUT;
  }

  if (!client_.connected()) {
    if (rxBuffer_.length() > 0) {
      responseLine = rxBuffer_;
      close();
      return PollStatus::COMPLETED;
    }
    close();
    return PollStatus::FAILED;
  }

  return PollStatus::PENDING;
}

void NetworkManager::close() {
  if (client_.connected()) {
    client_.stop();
  }
  active_ = false;
  requestStartedMs_ = 0;
}

EthernetHardwareStatus NetworkManager::hardwareStatus() const { return Ethernet.hardwareStatus(); }
