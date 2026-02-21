#include "EdgeNetwork.h"

EdgeNetworkManager::EdgeNetworkManager(const Config& config)
    : config_(config),
      wsClient_(),
      initialized_(false),
      wsConnected_(false),
      requestActive_(false),
      requestStartedMs_(0),
      lastWifiAttemptMs_(0),
      lastWsBeginMs_(0),
      rxHead_(0),
      rxTail_(0),
      rxCount_(0) {}

void EdgeNetworkManager::begin() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

  lastWifiAttemptMs_ = 0;
  lastWsBeginMs_ = 0;
  maintainConnectivity();

  wsClient_.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
    this->onWsEvent(type, payload, length);
  });
  wsClient_.setReconnectInterval(2000);

  initialized_ = true;
}

bool EdgeNetworkManager::ready() const { return initialized_; }

bool EdgeNetworkManager::linkUp() const { return WiFi.status() == WL_CONNECTED && wsConnected_; }

void EdgeNetworkManager::maintainConnectivity() {
  const uint32_t now = millis();
  if (WiFi.status() != WL_CONNECTED) {
    if (now - lastWifiAttemptMs_ >= 3000) {
      WiFi.begin(config_.wifiSsid, config_.wifiPassword);
      lastWifiAttemptMs_ = now;
    }
    return;
  }

  if (now - lastWsBeginMs_ >= 3000) {
    wsClient_.begin(config_.serverHost, config_.edgeWsPort, config_.edgeWsPath);
    lastWsBeginMs_ = now;
  }
}

bool EdgeNetworkManager::startRequest(const String& payloadLine) {
  if (!initialized_) {
    return false;
  }

  maintainConnectivity();
  wsClient_.loop();
  if (!linkUp()) {
    return false;
  }
  if (requestActive_) {
    return false;
  }

  String payload = payloadLine;
  wsClient_.sendTXT(payload);
  requestActive_ = true;
  requestStartedMs_ = millis();
  return true;
}

EdgeNetworkManager::PollStatus EdgeNetworkManager::pollResponse(String& responseLine) {
  if (!initialized_) {
    return PollStatus::FAILED;
  }

  maintainConnectivity();
  wsClient_.loop();

  if (!requestActive_) {
    return PollStatus::IDLE;
  }

  if (!linkUp()) {
    requestActive_ = false;
    return PollStatus::FAILED;
  }

  if (popRx(responseLine)) {
    requestActive_ = false;
    requestStartedMs_ = 0;
    return PollStatus::COMPLETED;
  }

  if (millis() - requestStartedMs_ >= config_.responseTimeoutMs) {
    requestActive_ = false;
    requestStartedMs_ = 0;
    return PollStatus::TIMEOUT;
  }

  return PollStatus::PENDING;
}

void EdgeNetworkManager::close() {
  requestActive_ = false;
  requestStartedMs_ = 0;
  rxHead_ = 0;
  rxTail_ = 0;
  rxCount_ = 0;
}

int32_t EdgeNetworkManager::rssi() const {
  if (WiFi.status() == WL_CONNECTED) {
    return WiFi.RSSI();
  }
  return -127;
}

void EdgeNetworkManager::enqueueRx(const String& text) {
  if (rxCount_ >= kQueueSize) {
    rxHead_ = (rxHead_ + 1) % kQueueSize;
    rxCount_--;
  }
  rxQueue_[rxTail_] = text;
  rxTail_ = (rxTail_ + 1) % kQueueSize;
  rxCount_++;
}

bool EdgeNetworkManager::popRx(String& outText) {
  if (rxCount_ == 0) {
    return false;
  }
  outText = rxQueue_[rxHead_];
  rxHead_ = (rxHead_ + 1) % kQueueSize;
  rxCount_--;
  return true;
}

void EdgeNetworkManager::onWsEvent(WStype_t type, uint8_t* payload, size_t length) {
  switch (type) {
    case WStype_CONNECTED:
      wsConnected_ = true;
      break;

    case WStype_DISCONNECTED:
      wsConnected_ = false;
      break;

    case WStype_TEXT: {
      String text;
      text.reserve(length + 1);
      for (size_t i = 0; i < length; ++i) {
        text += static_cast<char>(payload[i]);
      }
      enqueueRx(text);
      break;
    }

    default:
      break;
  }
}
