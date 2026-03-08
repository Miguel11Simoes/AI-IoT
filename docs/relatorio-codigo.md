# Relatório Técnico de Código — AI-IoT Cooperative Cooling Digital Twin

> **Objetivo**: Documentar de forma detalhada e completa como funciona cada ficheiro deste repositório, com excertos de código anotados e explicações simplificadas. Nenhuma parte do runtime fica por explicar.

---

## Índice

1. [Visão Geral da Arquitetura](#1-visão-geral-da-arquitetura)
2. [Configuração de Build — `platformio.ini`](#2-configuração-de-build--platformioini)
3. [Cabeçalho de Configuração — `include/ProjectConfig.h`](#3-cabeçalho-de-configuração--includeprojectconfigh)
4. [Sensores — `lib/sensors/src/Sensors.cpp`](#4-sensores--libsensorssrcsensorscpp)
5. [Controlo — `lib/control/src/Control.cpp`](#5-controlo--libcontrolsrccontrolcpp)
6. [Rede Edge — `lib/network/src/EdgeNetwork.cpp`](#6-rede-edge--libnetworksrcedgenetworkcpp)
7. [Protocolo — `lib/protocol/src/Protocol.cpp`](#7-protocolo--libprotocolsrcprotocolcpp)
8. [Firmware Principal — `src/main.cpp`](#8-firmware-principal--srcmaincpp)
   - 8.1 [Firmware do Rack (ROLE\_RACK)](#81-firmware-do-rack-role_rack)
   - 8.2 [Firmware da CDU (ROLE\_CDU)](#82-firmware-da-cdu-role_cdu)
9. [Servidor Central — `server.py`](#9-servidor-central--serverpy)
   - 9.1 [Imports e Utilitários](#91-imports-e-utilitários)
   - 9.2 [Deteção de Anomalias — `AnomalyDetector`](#92-deteção-de-anomalias--anomalydetector)
   - 9.3 [Estruturas de Dados — `RackState` e `CduState`](#93-estruturas-de-dados--rackstate-e-cdustate)
   - 9.4 [Núcleo do Modelo Térmico — `DigitalTwinCore`](#94-núcleo-do-modelo-térmico--digitaltwincore)
   - 9.5 [Servidor TCP Legado — `TcpTelemetryServer`](#95-servidor-tcp-legado--tcptelemetryserver)
   - 9.6 [Serviço HTTP — `TwinRequestHandler` e `WebService`](#96-serviço-http--twinrequesthandler-e-webservice)
   - 9.7 [Serviços WebSocket — `WebSocketServices`](#97-serviços-websocket--websocketservices)
   - 9.8 [Ponto de Entrada — `main()`](#98-ponto-de-entrada--main)
10. [Frontend 3D — `twin3d/`](#10-frontend-3d--twin3d)
    - 10.1 [Estrutura HTML — `index.html`](#101-estrutura-html--indexhtml)
    - 10.2 [Estilos — `styles.css`](#102-estilos--stylescss)
    - 10.3 [Motor 3D — `main.js`](#103-motor-3d--mainjs)
11. [Simulador de Nós — `tools/node_simulator.py`](#11-simulador-de-nós--toolsnode_simulatorpy)
12. [Script de Build CDU — `tools/cdu_build.ps1`](#12-script-de-build-cdu--toolscdu_buildps1)
13. [Dependências Python — `requirements.txt`](#13-dependências-python--requirementstxt)
14. [Fluxo de Dados Completo](#14-fluxo-de-dados-completo)

---

## 1. Visão Geral da Arquitetura

O projeto implementa um **digital twin térmico** para um pequeno data center com arrefecimento cooperativo líquido simulado. A arquitetura tem três camadas:

```
┌─────────────────────────────────────────────────────────┐
│  Dispositivos Edge (ESP32)                              │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────┐  │
│  │ Rack R00     │   │ Rack R07     │   │  CDU       │  │
│  │ (ESP32dev)   │   │ (ESP32dev)   │   │ (ESP32-C6) │  │
│  └──────┬───────┘   └──────┬───────┘   └─────┬──────┘  │
│         └─────────WebSocket (port 8765)───────┘         │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│  Servidor Central (server.py)                           │
│  ┌─────────────────────────────────────────────────┐    │
│  │  DigitalTwinCore (modelo 2×4 = 8 racks)        │    │
│  │  AnomalyDetector (zscore / IsolationForest)    │    │
│  └─────────────────────────────────────────────────┘    │
│  TCP :5000  │  HTTP :8080  │  WS-twin :8000  │          │
│                 WS-edge :8765                            │
└─────────────────────────┬───────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────┐
│  Dashboard 3D (twin3d/ → HTTP :8080)                    │
│  three.js + GLB + WebSocket :8000                       │
└─────────────────────────────────────────────────────────┘
```

**Racks reais**: apenas `R00` e `R07` enviam telemetria física.  
**Racks virtuais**: `R01`–`R06` existem apenas no modelo matemático do servidor, estimados por interpolação do campo térmico entre R00 e R07.  
**CDU**: Uma Cooling Distribution Unit com dois circuladores independentes (zona A e zona B), controlada pelo ESP32-C6.

---

## 2. Configuração de Build — `platformio.ini`

O ficheiro `platformio.ini` é a raiz de toda a compilação firmware. Define três targets independentes e partilha parâmetros comuns via `[env]`.

### Secção `[env]` — parâmetros globais

```ini
[env]
platform = espressif32@6.9.0
framework = arduino
monitor_speed = 115200
lib_deps =
  bblanchon/ArduinoJson@^7.1.0
  links2004/WebSockets@^2.6.1
build_flags =
  -DWIFI_SSID=\"CHANGE_ME_SSID\"
  -DWIFI_PASSWORD=\"CHANGE_ME_PASS\"
  -DSERVER_HOST=\"192.168.1.10\"
  -DEDGE_WS_PORT=8765
  -DCYCLE_INTERVAL_MS=1000
  -DNETWORK_TIMEOUT_MS=1500
  -DREMOTE_CMD_TTL_MS=5000
  ...
```

Todos os parâmetros são passados como macros de pré-processador (`-D`). Isto significa que **não há ficheiros de configuração separados**: tudo está no `platformio.ini` e é compilado diretamente no binário. Para mudar o SSID ou o IP do servidor, edita-se esta secção e recompila.

| Macro | Valor padrão | Significado |
|---|---|---|
| `WIFI_SSID` | `CHANGE_ME_SSID` | Rede Wi-Fi a associar |
| `SERVER_HOST` | `192.168.1.10` | IP do servidor Python |
| `EDGE_WS_PORT` | `8765` | Porta WebSocket do servidor para edges |
| `CYCLE_INTERVAL_MS` | `1000` | Período do ciclo de telemetria (ms) |
| `REMOTE_CMD_TTL_MS` | `5000` | Tempo antes de o comando remoto expirar |
| `ANOMALY_TEMP_C` | `80` | Temperatura que dispara anomalia local |
| `CRITICAL_TEMP_C` | `88` | Temperatura que corta o aquecimento |
| `HEAT_WINDOW_MS` | `2000` | Janela de time-proportioning do heater |

### Target `rack_r00` e `rack_r07`

```ini
[env:rack_r00]
board = esp32dev
build_flags =
  ${env.build_flags}
  -DDEVICE_ROLE=1
  -DNODE_ID=\"RACK_A\"
  -DRACK_ID=\"R00\"
  -DONE_WIRE_PIN=4
  -DHEAT_PIN=18
```

`DEVICE_ROLE=1` seleciona o código de rack dentro de `src/main.cpp`. Os dois racks usam o mesmo binário base mas com IDs diferentes (`R00` vs `R07`). As bibliotecas `OneWire` e `DallasTemperature` são incluídas aqui (não no CDU).

### Target `cdu_esp32c6`

```ini
[env:cdu_esp32c6]
platform = https://github.com/pioarduino/platform-espressif32.git#55.03.37
board = esp32-c6-devkitc-1
lib_ignore =
  control
  sensors
build_flags =
  ${env.build_flags}
  -DDEVICE_ROLE=2
  -DCDU_FAN_A_PIN=4
  -DCDU_FAN_B_PIN=5
```

O ESP32-C6 usa uma **plataforma e toolchain separadas** para evitar conflitos com o ESP32 clássico (que usa Xtensa; o C6 usa RISC-V). As bibliotecas `control` e `sensors` são ignoradas porque a CDU não mede temperatura interna nem controla heaters — só move fans.

---

## 3. Cabeçalho de Configuração — `include/ProjectConfig.h`

Este ficheiro faz a ponte entre as macros do compilador e as structs C++ usadas no código.

### Guards e papéis

```cpp
#ifndef DEVICE_ROLE
#define DEVICE_ROLE 1          // Padrão a rack se não definido
#endif
#define ROLE_RACK 1
#define ROLE_CDU  2
```

Cada macro de `platformio.ini` tem um `#ifndef` correspondente para que o ficheiro compile mesmo sem o `platformio.ini` (útil em IDEs genéricos).

### Struct `RackNodeConfig`

```cpp
struct RackNodeConfig {
  const char* nodeId;
  const char* rackId;
  const char* wifiSsid;
  const char* serverHost;
  uint16_t edgeWsPort;
  uint8_t  oneWirePin;
  uint8_t  heatPin;
  uint32_t cycleIntervalMs;
  uint32_t remoteCmdTtlMs;
  bool     simulatedCooling;
  float    heatGainCPerSec;
  float    anomalyTempC;
  float    criticalTempC;
  uint16_t heatWindowMs;
  // ... e mais 8 coeficientes térmicos
};
```

A função `loadRackConfig()` preenche esta struct com os valores das macros em tempo de compilação:

```cpp
inline RackNodeConfig loadRackConfig() {
  RackNodeConfig cfg{};
  cfg.nodeId          = NODE_ID;
  cfg.rackId          = RACK_ID;
  cfg.simulatedCooling = (SIMULATED_COOLING != 0);
  cfg.anomalyTempC    = static_cast<float>(ANOMALY_TEMP_C);
  // ...
  return cfg;
}
```

### Struct `CduConfig`

Versão simplificada para o CDU — contém apenas Wi-Fi, servidor, pinos dos fans e temporizadores. Não tem coeficientes térmicos porque a CDU não simula temperatura.

---

## 4. Sensores — `lib/sensors/src/Sensors.cpp`

O `SensorManager` tem dois modos de operação exclusivos, selecionados por `config_.simulationMode`.

### Modo Simulado (`simulationMode = true`)

Implementa um modelo térmico de dois compartimentos acoplados: **hot** (ar quente saindo dos servidores) e **liquid** (fluido de arrefecimento).

```cpp
// Ganho de calor pelo heater
const float heatGain = config_.heatGainCPerSec * (0.45f + heatNorm * 1.2f);

// Transferências de calor (perda do hot)
const float hotToLiquid    = config_.hotToLiquidCoeff * hotMinusLiquid;
const float hotToAmbient   = config_.hotToAmbientCoeff * (0.2f + fanNorm) * hotMinusAmbient;
const float flowCooling    = config_.flowCoolingCoeff  * flowNorm * hotMinusLiquid;
const float liquidToAmbient = config_.liquidToAmbientCoeff * (0.2f + fanNorm) * liquidMinusAmbient;

// Equações diferenciais (Euler explícito)
const float dHot    = heatGain - hotToAmbient - hotToLiquid - (0.45f * flowCooling);
const float dLiquid = hotToLiquid + flowCooling - liquidToAmbient;

simulatedHotC_    += dHot    * dtSec;
simulatedLiquidC_ += dLiquid * dtSec;
```

A física é simplificada mas realista:
- `heatGain` cresce linearmente com o PWM do heater
- `hotToAmbient` aumenta com o fan (convecção forçada)
- `flowCooling` aumenta com o caudal da bomba

### Modo Hardware (`simulationMode = false`) com DS18B20

```cpp
dallas_.requestTemperatures();
const float hot    = dallas_.getTempCByIndex(0);
const float liquid = dallas_.getTempCByIndex(1);

const bool hotValid    = validTemperature(hot);
const bool liquidValid = validTemperature(liquid);
```

Se apenas **uma sonda** estiver ligada (situação comum na bancada), o código **estima** `t_liquid` como estado virtual amortecido:

```cpp
if (hotValid && !liquidValid) {
    float targetDelta = 4.8f - (1.7f * flowNorm) - (0.9f * fanNorm);
    targetDelta = clampFloat(targetDelta, 2.0f, 8.5f);
    const float targetLiquid = simulatedHotC_ - targetDelta;
    simulatedLiquidC_ += (targetLiquid - simulatedLiquidC_) * 0.22f;  // filtro IIR
}
```

O delta entre hot e liquid é tipicamente 4-5°C, ajustado pelo caudal e pelo fan. O filtro IIR (coef. 0.22) suaviza a estimativa.

### Validação de temperatura

```cpp
bool SensorManager::validTemperature(float value) const {
    if (value <= -100.0f || value >= 130.0f) return false;
    if (value == DEVICE_DISCONNECTED_C)      return false;
    return true;
}
```

`DEVICE_DISCONNECTED_C` é a constante da biblioteca DallasTemperature para sonda desligada (-127°C).

---

## 5. Controlo — `lib/control/src/Control.cpp`

O `ControlManager` decide o PWM do heater em cada ciclo, combinando lógica local com setpoints remotos.

### Cálculo do PWM local

```cpp
uint8_t ControlManager::localHeatFromTemp(float tHotC, float tLiquidC) const {
    const float delta = tHotC - tLiquidC;
    const int raw = static_cast<int>(190.0f - (tHotC - 40.0f) * 4.0f - delta * 2.5f);
    return clampPwm(raw, config_.minHeatPwm, config_.maxHeatPwm);
}
```

A fórmula é uma lei linear: o PWM base é 190, reduzido 4 unidades por cada grau acima de 40°C (hot) e 2.5 unidades por cada grau de diferença hot-liquid. Quanto mais quente, menos carga térmica.

### Deteção de falha local e proteções

```cpp
const float riseRate = (tHotC - lastHotC_) / dtSec;  // °C/s

const bool localFault = (!sensorOk)
    || (tHotC >= config_.anomalyTempC)          // > 80°C
    || (riseRate >= config_.maxRiseRateCPerSec); // > 5°C/s

if (localFault) {
    out.localAnomaly = true;
    heat = config_.minHeatPwm;  // corta heater
}
```

Três gatilhos independentes que cortam o aquecimento:
1. Sonda avariada (`sensorOk = false`)
2. Temperatura acima de `anomalyTempC` (80°C)
3. Subida demasiado rápida (> 5°C/s indica falha ou fuga)

### Blend com setpoint remoto

```cpp
if (remote_.valid && remoteFresh(nowMs)) {
    // Blend 40% local + 60% remoto
    const int blendedHeat = (heat * 4 + remote_.heatPwm * 6) / 10;
    heat = clampPwm(blendedHeat, min, max);
    out.usedRemote = true;

    if (remote_.anomaly) {
        heat = config_.minHeatPwm;  // servidor diz anomalia global → corta
    }
}
```

O servidor tem mais peso (60%) que o controlo local (40%). Se o servidor sinalizar anomalia global, o heater é cortado independentemente da temperatura local.

### Temperatura crítica (último recurso)

```cpp
if (tHotC >= config_.criticalTempC) {   // 88°C
    heat = config_.minHeatPwm;
    out.localAnomaly = true;
}
```

### Atuação por Time-Proportioning

O heater **não usa PWM hardware** (sinal rápido a dezenas de kHz). Em vez disso, usa uma janela de tempo (`heatWindowMs = 2000ms`):

```cpp
void ControlManager::service(uint32_t nowMs) {
    const uint16_t windowMs = config_.heatWindowMs;  // 2000ms
    const uint32_t elapsed = nowMs - heatWindowStartMs_;
    if (elapsed >= windowMs) {
        heatWindowStartMs_ = nowMs - (elapsed % windowMs);
    }

    // heat=255 → ON 2000ms de 2000ms (100%)
    // heat=128 → ON 1004ms de 2000ms (50%)
    // heat=0   → ON 0ms de 2000ms (0%)
    const uint32_t onMs =
        (static_cast<uint32_t>(appliedHeatPwm_) * windowMs) / 255UL;
    const bool shouldBeOn = (nowMs - heatWindowStartMs_) < onMs;

    if (shouldBeOn != heaterOn_) {
        heaterOn_ = shouldBeOn;
        digitalWrite(config_.heatPin, heaterOn_ ? HIGH : LOW);
    }
}
```

Este método protege o IRF520 (MOSFET de potência) de comutações rápidas que gerariam calor excessivo na porta. Com uma janela de 2 segundos, o MOSFET comuta apenas ≤30 vezes por minuto.

---

## 6. Rede Edge — `lib/network/src/EdgeNetwork.cpp`

O `EdgeNetworkManager` gere a ligação Wi-Fi e WebSocket de forma não-bloqueante.

### Inicialização e reconexão automática

```cpp
void EdgeNetworkManager::begin() {
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.persistent(false);      // não guarda credenciais na flash
    maintainConnectivity();

    wsClient_.onEvent([this](WStype_t type, uint8_t* payload, size_t length) {
        this->onWsEvent(type, payload, length);
    });
    wsClient_.setReconnectInterval(2000);
}
```

O `maintainConnectivity()` é chamado em cada ciclo — se o Wi-Fi cair, tenta reconectar a cada 3s; se o WS cair, tenta reconectar a cada 3s.

### Modelo request/response não-bloqueante

O firmware **não bloqueia** à espera da resposta. Em vez disso, usa um modelo de polling por estados:

```cpp
// Inicia envio (não bloqueia)
bool EdgeNetworkManager::startRequest(const String& payload) {
    wsClient_.sendTXT(payload);
    requestActive_ = true;
    requestStartedMs_ = millis();
    return true;
}

// Polling chamado em cada loop()
PollStatus EdgeNetworkManager::pollResponse(String& responseLine) {
    wsClient_.loop();           // processa eventos WS

    if (popRx(responseLine))    // resposta chegou?
        return PollStatus::COMPLETED;

    if (millis() - requestStartedMs_ >= config_.responseTimeoutMs)
        return PollStatus::TIMEOUT;     // 1500ms sem resposta

    return PollStatus::PENDING;         // ainda à espera
}
```

### Fila circular de receção

```cpp
static constexpr int kQueueSize = 4;
String rxQueue_[kQueueSize];

void EdgeNetworkManager::enqueueRx(const String& text) {
    // Se a fila estiver cheia, descarta o mais antigo (head)
    if (rxCount_ >= kQueueSize) {
        rxHead_ = (rxHead_ + 1) % kQueueSize;
        rxCount_--;
    }
    rxQueue_[rxTail_] = text;
    rxTail_ = (rxTail_ + 1) % kQueueSize;
    rxCount_++;
}
```

A fila circular com 4 slots garante que mensagens recebidas fora de ordem ou em burst não bloqueiam o firmware.

---

## 7. Protocolo — `lib/protocol/src/Protocol.cpp`

Serialização e deserialização JSON usando ArduinoJson v7.

### Telemetria do Rack → Servidor

```cpp
String encodeRackTelemetryJson(const RackTelemetryMessage& message) {
    JsonDocument doc;
    doc["type"]          = "rack_telemetry";
    doc["id"]            = message.rackId;     // "R00" ou "R07"
    doc["t_hot"]         = message.tHotC;      // temperatura hot (°C)
    doc["t_liquid"]      = message.tLiquidC;   // temperatura liquid (°C)
    doc["fan_local_pwm"] = message.fanLocalPwm; // sempre 0 (sem fan local)
    doc["heat_pwm"]      = message.heatPwm;    // PWM atual do heater
    doc["pump_v"]        = message.pumpV;      // sempre 0 (sem bomba local)
    doc["rssi"]          = message.rssi;       // sinal Wi-Fi (dBm)
    doc["local_anomaly"] = message.localAnomaly; // bool
    doc["ts"]            = message.tsMs;       // timestamp millis()
    // ...
}
```

### Comando do Servidor → Rack

```cpp
bool decodeRackCommandJson(const String& responseLine, RackCommandMessage& out) {
    // Aceita tanto "heat_pwm" (modo WS) como "target_heat_pwm" (modo TCP legacy)
    out.heatPwm = clampByte(doc["heat_pwm"] | doc["target_heat_pwm"] | 0);
    out.anomaly = doc["anomaly"] | false;
    // ...
}
```

A dupla leitura `doc["heat_pwm"] | doc["target_heat_pwm"]` garante compatibilidade com ambos os formatos de resposta do servidor (TCP legado e WebSocket edge).

### Telemetria CDU e Comando CDU

Estrutura análoga para a CDU: envia `type: "cdu_telemetry"` com `fanA_pwm`, `fanB_pwm`, `t_supply_A`, `t_supply_B`; recebe `fanA_pwm`, `fanB_pwm`, `t_supply_target`.

---

## 8. Firmware Principal — `src/main.cpp`

Um único ficheiro com dois firmwares completos, separados por `#if DEVICE_ROLE == ROLE_RACK`.

### 8.1 Firmware do Rack (ROLE_RACK)

#### Máquina de Estados (FSM)

```cpp
enum class NodeState : uint8_t {
    INIT,           // inicializa todos os subsistemas
    READ_SENSORS,   // lê/simula temperaturas
    CONTROL_LOCAL,  // calcula PWM + compõe telemetria
    SEND_DATA,      // envia JSON via WebSocket
    WAIT_SERVER,    // aguarda resposta (polling não-bloqueante)
    APPLY_COMMAND,  // aplica setpoint remoto ao controlo
    WAIT_NEXT       // espera até completar o ciclo de 1s
};
```

#### Ciclo completo (1 iteração = 1 segundo)

**INIT** → inicializa sensores, controlo, rede; passa para READ_SENSORS.

**READ_SENSORS**:
```cpp
gLastSensor = gSensors.update(nowMs, 0, gControl.heatPwm(), 0);
```
Lê ou simula as temperaturas. Passa o PWM atual do heater ao simulador para que o modelo térmico seja coerente.

**CONTROL_LOCAL**:
```cpp
gLastActuation = gControl.compute(gLastSensor.tHotC, gLastSensor.tLiquidC,
                                   gLastSensor.sensorOk, nowMs);
gControl.apply(gLastActuation, nowMs);

// Monta telemetria
telemetry.tHotC        = gLastSensor.tHotC;
telemetry.heatPwm      = gLastActuation.heatPwm;
telemetry.localAnomaly = gLastActuation.localAnomaly;
```

**SEND_DATA**: envia o JSON. Se a rede falhar, vai direto para WAIT_NEXT (perde o ciclo mas não bloqueia).

**WAIT_SERVER**: polling não-bloqueante. O `loop()` continua a ser chamado enquanto aguarda, garantindo que `gControl.service()` continua a atuar o heater:

```cpp
void loop() {
    if (gControlReady) {
        gControl.service(nowMs);   // SEMPRE chamado, independente do estado
    }
    switch (gState) { ... }
}
```

**APPLY_COMMAND**:
```cpp
if (gCommandFresh && gLastCommand.valid) {
    ControlManager::RemoteSetpoints remote{};
    remote.valid   = true;
    remote.heatPwm = gLastCommand.heatPwm;
    remote.anomaly = gLastCommand.anomaly;
    gControl.setRemoteSetpoints(remote, nowMs);
}
```

**WAIT_NEXT**: aguarda até `cycleIntervalMs` (1000ms) desde o início do ciclo.

#### Relatório periódico

A cada 3s, imprime estatísticas na UART:
```
[STAT] cycle=42 t_hot=52.34 t_liquid=47.18 heat=156 ack=40 timeout=2 fail=0 mode=heat-only-co-op
```

### 8.2 Firmware da CDU (ROLE_CDU)

FSM mais simples: `INIT → SEND_DATA → WAIT_SERVER → APPLY_CMD → WAIT_NEXT`.

#### Rampa de fan

Os PWM dos fans **não saltam** diretamente para o target — usam a função `rampPwm()`:

```cpp
uint8_t rampPwm(uint8_t current, uint8_t target, uint8_t step = 5) {
    if (current < target) return min(current + step, target);
    if (current > target) return max(current - step, target);
    return current;
}

// Em cada loop(), antes da FSM:
gFanACurrent = rampPwm(gFanACurrent, gFanATarget, 4);  // 4 PWM/loop
analogWrite(gConfig.fanAPin, gFanACurrent);
```

Com `step=4` e `CYCLE_INTERVAL_MS=1000`, o fan demora ~60 ciclos (60s) a ir de 0 a 255. Isto evita picos de corrente e ruído acústico.

#### Temperatura virtual de supply

```cpp
void updateVirtualSupply(float dtSec) {
    const float coolA = (gFanACurrent / 255.0f) * 1.8f;
    const float loadA = 1.3f;  // carga fixa assumida
    gSupplyA += (loadA - coolA) * 0.12f * dtSec;
    gSupplyA = constrain(gSupplyA, 22.0f, 45.0f);
}
```

Estima a temperatura da água de supply como função da potência de arrefecimento vs carga. Envia este valor ao servidor para alimentar o modelo térmico global.

#### Fallback local

Se o comando remoto ficar stale (mais de `remoteCmdTtlMs` = 5s sem atualização):
```cpp
void applyFallbackIfStale(uint32_t nowMs) {
    if (nowMs - gLastCmdMs <= gConfig.remoteCmdTtlMs) return;
    const float err = (gSupplyA + gSupplyB) * 0.5f - gSupplyTarget;
    const int correction = static_cast<int>(err * 15.0f);
    gFanATarget = constrain(160 + correction, 120, 220);
}
```

O CDU mantém a temperatura de supply perto do target (29.5°C por defeito) usando um controlador proporcional local.

---

## 9. Servidor Central — `server.py`

O servidor tem 956 linhas e cobre quatro responsabilidades: modelo térmico, deteção de anomalias, receção de telemetria, e serviço de API/UI.

### 9.1 Imports e Utilitários

```python
try:
    import numpy as np
except ImportError:
    np = None

try:
    from sklearn.ensemble import IsolationForest
except ImportError:
    IsolationForest = None

try:
    from websockets.asyncio.server import serve as ws_serve
    ...
except ImportError:
    try:
        from websockets.server import serve as ws_serve   # websockets < 14
        ...
    except ImportError:
        ws_serve = None
```

Todos os imports opcionais têm duplo fallback. O servidor funciona sem `numpy`, `scikit-learn` ou `websockets` — cai para zscore e TCP apenas. A tentativa de importar `websockets.asyncio.server` (v14+) antes de `websockets.server` (v10–13) garante compatibilidade com múltiplas versões.

```python
def clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))

def clamp_pwm(value: float, min_v: int = 0, max_v: int = 255) -> int:
    return int(clamp(float(value), float(min_v), float(max_v)))
```

Funções auxiliares thread-safe (imutáveis) usadas em todo o código.

### 9.2 Deteção de Anomalias — `AnomalyDetector`

Classe com dois modos: **zscore** (padrão, sem dependências) e **iforest** (IsolationForest, requer numpy + scikit-learn).

```python
class AnomalyDetector:
    def __init__(self, detector_mode, contamination=0.05, warmup_samples=50):
        self.buffer = deque(maxlen=500)   # janela deslizante de 500 amostras
        self.warmup_samples = warmup_samples
        self.ai_enabled = detector_mode == "iforest" and IsolationForest is not None
```

#### Z-score

```python
def _detect_zscore(self, features: List[float]) -> bool:
    cols = list(zip(*self.buffer))   # transpõe: lista de colunas
    for idx, value in enumerate(features):
        col = cols[idx]
        mu    = statistics.fmean(col)
        sigma = statistics.pstdev(col) or 1e-6
        if abs((value - mu) / sigma) > 3.2:   # threshold 3.2σ
            return True
    return False
```

Para cada feature (t_hot, t_liquid, heat_pwm), calcula média e desvio padrão do historial. Se qualquer feature desviar mais de 3.2 sigma, é anomalia. Threshold de 3.2 (em vez do clássico 3.0) reduz falsos positivos.

#### IsolationForest assíncrono

```python
def _train_async_if_needed(self) -> None:
    def train_worker() -> None:
        model = IsolationForest(
            contamination=self.contamination,    # 5% esperado de anomalias
            n_estimators=30,                      # 30 árvores (leve)
            max_samples=min(128, len(samples)),
        )
        model.fit(np.asarray(samples))
        with self.lock:
            self.model = model
            self.model_ready = True

    threading.Thread(target=train_worker, daemon=True).start()
```

O treino ocorre numa thread separada (não bloqueia o loop principal). Enquanto o modelo não está pronto, usa zscore como fallback. Re-treina quando o buffer acumula novas amostras.

### 9.3 Estruturas de Dados — `RackState` e `CduState`

```python
@dataclass
class RackState:
    rack_id: str
    t_hot:   float
    t_liquid: float
    fan_pwm: int
    heat_pwm: int
    pump_pwm: int
    rssi: int
    anomaly: bool
    detector: str    # "zscore" ou "isolation_forest"
    received_ts: float

@dataclass
class CduState:
    cdu_id: str
    fanA_pwm: int
    fanB_pwm: int
    t_supply_A: float
    t_supply_B: float
    received_ts: float
```

Dataclasses imutáveis (são substituídas inteiras, não mutadas). O campo `received_ts` é usado para detetar dados stale (mais velhos que `stale_seconds = 8s`).

### 9.4 Núcleo do Modelo Térmico — `DigitalTwinCore`

A classe central. Tem estado global protegido por `threading.Lock()` porque é acedida por múltiplas threads (TCP, WS-edge, HTTP).

#### Estado inicial

```python
self.racks_real: Dict[str, RackState] = {}
self.real_rack_ids = {"R00", "R07"}   # ÚNICO PONTO DE VERDADE

self.hot    = [55.0] * 8   # temperaturas hot dos 8 racks
self.liquid = [50.0] * 8
self.heat   = [140] * 8    # PWM do heater de cada rack
self.anomaly = [False] * 8

# Coeficientes do modelo
self.k_heat      = 0.020   # ganho de calor por unit de heat_pwm
self.k_zone_fan  = 0.240   # arrefecimento por fan
self.k_cool      = 0.085   # arrefecimento da CDU
self.alpha_supply = 0.016  # dinâmica da temperatura de supply
self.beta_rack    = 0.17   # inércia térmica do rack
```

#### Método `_update_model(now)` — coração do sistema

Chamado em cada mensagem recebida. Atualiza todos os 8 racks com base nos dados reais disponíveis.

**Passo 1: âncoras do campo térmico**
```python
r00 = self.racks_real.get("R00")
r07 = self.racks_real.get("R07")
t00 = r00.t_hot if (r00 and self._fresh(r00.received_ts, now)) else self.hot[0]
t07 = r07.t_hot if (r07 and self._fresh(r07.received_ts, now)) else self.hot[7]
```

Se os dados de R00/R07 estiverem stale, usa a estimativa anterior do modelo — o sistema não "colapsa" por falta de dados.

**Passo 2: atualização por rack**
```python
for idx in range(8):
    label = f"R{idx:02d}"
    row, col = divmod(idx, 4)   # layout 2x4
    w = (row + col / 3) / 2     # peso de interpolação [0, 1]
    field = (1 - w) * t00 + w * t07   # campo térmico interpolado

    real = self.racks_real.get(label)
    if real and self._fresh(real.received_ts, now):
        # Rack real: usa dados directos
        self.hot[idx] = real.t_hot
        continue

    # Rack virtual: modelo térmico
    q_heat = self.k_heat * self.heat[idx]
    q_rej  = self.k_zone_fan * (fan_pwm/255) * max(0, self.hot[idx] - zone_supply)
    nxt    = self.hot[idx] + self.beta_rack * (q_heat - q_rej) * dt
               + 0.18 * (field - self.hot[idx]) * dt   # pull para o campo
    self.hot[idx] = clamp(nxt, 25, 95)
```

O termo `0.18 * (field - self.hot[idx]) * dt` é o "pull" do campo térmico interpolado: mesmo os racks virtuais são influenciados pela temperatura dos dois extremos reais.

**Passo 3: atualização da CDU**
```python
maxA = max(self.hot[i] for i in range(8) if self._zone(i) == "A")  # racks 0,1,4,5
fanA_cmd = clamp_pwm(95 + 5.2 * (maxA - 65.0), 80, 255)
# Se algum rack ≥ 78°C → fan máximo
if max(self.hot) >= 78.0:
    fanA_cmd = fanB_cmd = 255
```

O comando da CDU é calculado a partir da temperatura máxima em cada zona. A lei é linear: por cada grau acima de 65°C, o fan aumenta 5.2 PWM.

**Passo 4: KPIs globais**
```python
trend = self._trend(now)         # °C/min nos últimos 45s
pred5 = avg_hot + trend * 5.0    # previsão a 5 minutos

risk = 0.52 * (critical_temp - 42) / 36    # componente de temperatura
     + 0.33 * (anomaly_count / 8)           # componente de anomalias
     + 0.15 * abs(trend) / 6               # componente de tendência
```

`anomaly_risk_pct` combina três fatores ponderados. Se não houver anomalias ativas, o risco é multiplicado por 0.6 (penaliza menos situações de estabilidade).

#### Zonas A e B

```python
def _zone(self, idx: int) -> str:
    return "A" if idx % 4 < 2 else "B"
    # idx 0,1,4,5 → zona A (fan A, supply A)
    # idx 2,3,6,7 → zona B (fan B, supply B)
```

Layout físico do data center:
```
Coluna:   0   1   2   3
Linha 0: [A] [A] [B] [B]   → R00 R01 R02 R03
Linha 1: [A] [A] [B] [B]   → R04 R05 R06 R07
```

#### Processamento de mensagens

```python
def process_message(self, payload, source="tcp"):
    msg_type = payload.get("type", "")

    if msg_type == "cdu_telemetry":
        # Atualiza CduState, corre modelo, retorna cdu_cmd

    if msg_type == "rack_telemetry":
        rid = self._normalize_id(payload["id"])
        if rid not in self.real_rack_ids:
            return {"ok": False, "error": "rack id not allowed"}  # rejeita nós desconhecidos
        # Deteção de anomalia AI
        ai_anom, detector_name = self.detector.detect([t_hot, t_liquid, heat_pwm])
        anomaly = local_anomaly or ai_anom or (t_hot >= 85.0)
        # Atualiza RackState, corre modelo, retorna rack_cmd
```

O alias map permite que os ESP32 enviem `id: "A"` ou `id: "RACK_A"` e o servidor normaliza para `"R00"`:
```python
self.alias = {"A": "R00", "NODE_A": "R00", "B": "R07", "NODE_B": "R07"}
```

### 9.5 Servidor TCP Legado — `TcpTelemetryServer`

Escuta na porta 5000 (padrão). Cada cliente TCP é tratado numa thread separada.

```python
def _handle_client(self, conn, addr):
    conn.settimeout(2.0)
    raw  = self._recv_line(conn)      # lê até '\n'
    msg  = json.loads(raw)
    resp = self.core.process_message(msg, source="tcp")
    conn.sendall((json.dumps(resp) + "\n").encode())
```

Protocolo simples: **uma linha JSON → uma linha JSON de resposta**. A conexão fecha depois. Compatível com `tools/node_simulator.py` e qualquer cliente TCP simples (netcat, etc.).

### 9.6 Serviço HTTP — `TwinRequestHandler` e `WebService`

Handler HTTP multi-threaded que serve ficheiros estáticos e endpoints de API.

| Endpoint | Método | Resposta |
|---|---|---|
| `GET /api/health` | GET | `{"ok": true, "time_ms": ...}` |
| `GET /api/state` | GET | Snapshot do dashboard (nós reais + stats) |
| `GET /api/twin?racks=8` | GET | Estado completo do twin (8 racks + CDU + globais) |
| `GET /api/history?rack=R00&points=120` | GET | Histórico de 120 amostras de R00 |
| `GET /api/config` | GET | Configuração de WS para o frontend |
| `GET /twin3d/...` | GET | Ficheiros estáticos da UI |

```python
def _serve_static(self, raw_path):
    # Proteção de path traversal
    root   = self.project_root.resolve()
    target = (root / rel_path).resolve()
    if root not in target.parents:
        self.send_error(403, "forbidden")
        return
    # Serve o ficheiro
    payload = target.read_bytes()
    self.send_response(200)
```

### 9.7 Serviços WebSocket — `WebSocketServices`

Dois servidores WebSocket independentes, correndo no mesmo event loop asyncio:

**WS-twin** (porta 8000): push periódico para o dashboard.
```python
async def _twin_handler(self, websocket):
    while not self.stop_event.is_set():
        await websocket.send(json.dumps(self.core.get_twin_payload()))
        await asyncio.sleep(0.5)   # 2 updates/segundo
```

**WS-edge** (porta 8765): request/response para os ESP32.
```python
async def _edge_handler(self, websocket):
    async for raw in websocket:
        msg  = json.loads(raw)
        resp = self.core.process_message(msg, source="edge_ws")
        await websocket.send(json.dumps(resp))
```

O WS-edge é **bidirecional síncrono**: o ESP32 envia telemetria e aguarda a resposta antes de avançar. O WS-twin é **push unidirecional** para o frontend.

### 9.8 Ponto de Entrada — `main()`

```python
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host",       default="0.0.0.0")
    parser.add_argument("--port",       default=5000,  type=int)  # TCP
    parser.add_argument("--ui-port",    default=8080,  type=int)  # HTTP
    parser.add_argument("--ws-port",    default=8000,  type=int)  # WS-twin
    parser.add_argument("--edge-ws-port", default=8765, type=int) # WS-edge
    parser.add_argument("--detector",   default="zscore", choices=["zscore","iforest"])
    parser.add_argument("--no-ui",      action="store_true")
    parser.add_argument("--no-ws",      action="store_true")
    parser.add_argument("--no-tcp",     action="store_true")
```

Flags de disable (`--no-ui`, `--no-ws`, `--no-tcp`) permitem executar apenas o subconjunto necessário. Por exemplo, para testar só a API sem UI: `python server.py --no-ui`.

Sequência de arranque:
1. Cria `AnomalyDetector` e `DigitalTwinCore`
2. Inicia `WebService` (HTTP) numa thread daemon
3. Inicia `WebSocketServices` (twin + edge) numa thread daemon com event loop asyncio
4. Corre `TcpTelemetryServer.serve_forever()` na thread principal (bloqueante)
5. `KeyboardInterrupt` → shutdown ordenado de todos os serviços

---

## 10. Frontend 3D — `twin3d/`

### 10.1 Estrutura HTML — `index.html`

Divide o ecrã em duas secções:

```html
<div id="app-shell">
  <section id="viewport">
    <canvas id="twin-canvas"></canvas>              <!-- Three.js renderiza aqui -->
    <div id="connection-pill" class="offline">...</div>  <!-- indicador WS -->
  </section>

  <aside id="side-panel">
    <!-- KPIs: avg_hot, max_hot, critical_rack, total_cooling_power -->
    <!-- AI Monitor: status, confidence, trend, prediction 5min, anomaly risk -->
    <!-- CDU Plant: supply A/B, fan A/B -->
    <!-- Tabela de racks: label, status, temp, barra, fan, pump, mode -->
  </aside>
</div>
```

### 10.2 Estilos — `styles.css`

Define um tema escuro de data center (fundo `#0b1520`, acentos em azul `#2e8bcf`). Destaques:

- `.status-dot.critical` → vermelho pulsante com `@keyframes pulse`
- `.temp-fill` → barra de temperatura com gradiente `blue → orange → red`
- `.status-pill.critical` → pill vermelha; `.nominal` → verde
- Responsivo: em ecrãs estreitos, o painel desliza por baixo do viewport

### 10.3 Motor 3D — `main.js`

#### Configuração Three.js

```javascript
renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.96;

// Pós-processamento: bloom emissivo para o efeito térmico
composer = new EffectComposer(renderer);
composer.addPass(new RenderPass(scene, camera));
bloomPass = new UnrealBloomPass(
    new THREE.Vector2(w, h), 0.28, 0.58, 0.26  // strength, radius, threshold
);
composer.addPass(bloomPass);
```

#### Carregamento e clonagem do modelo GLB

```javascript
loader.load("/rack/data_center_rack.glb", (gltf) => {
    const base = gltf.scene;
    // Normaliza: centra e escala para 2.2m de altura
    base.position.sub(center);
    const scale = 2.2 / size.y;
    base.scale.setScalar(scale);

    // Clona 8 vezes, posiciona em grid 2×4
    rackSlots.forEach((slot, idx) => {
        const { rack, heatMeshes, haloLight, criticalMarker } = cloneRackModel(base, idx);
        slot.group = rack;
        rackRoot.add(rack);
    });
});
```

#### Seleção de meshes térmicas

```javascript
// Procura por nome: meshes com "server|slot|bay|blade" mas não "frame|outer|shell"
const looksInner = /(server|slot|bay|unit|blade|front|panel)/.test(lname)
    && !/(frame|outer|shell|rack|cage|back|side)/.test(lname);
```

Se nenhum mesh for identificado por nome, usa heurística geométrica: os 45% de meshes com `centerZ` mais alto (mais frontais) excluindo o maior (provavelmente o chassis).

#### Gradiente de cor por temperatura

```javascript
function thermalGradient(temp) {
    const t = tempRatio(temp);   // normaliza [30°C, 85°C] → [0, 1]
    if (t < 0.33)       // frio: azul → ciano
        color.setRGB(0.24 - t*0.12, 0.55 + t*0.82, 1.0 - t*1.15);
    else if (t < 0.66)  // médio: amarelo → laranja
        color.setRGB(0.2 + p*0.8, 0.9 - p*0.4, 0.15 + p*0.05);
    else                // quente: laranja → vermelho
        color.setRGB(1.0, 0.5 - p*0.3, 0.2 - p*0.1);
}
```

#### Animação por frame (`applyRackVisual`)

```javascript
function applyRackVisual(slot, dtSec, nowSec) {
    // Interpolação suave das temperaturas (filtro low-pass)
    slot.currentHot += (slot.targetHot - slot.currentHot) * min(1, dtSec * 2.4);

    // Pulsação de anomalia
    const anomalyPulse = slot.anomaly
        ? 0.24 + Math.sin(nowSec * 6.0 + slot.id) * 0.08
        : 0.0;

    // Aplica cor emissiva e intensidade ao bloom
    slot.heatMeshes.forEach((mesh) => {
        mat.emissive.copy(slot.currentColor);
        mat.emissiveIntensity = slot.currentIntensity;
    });

    // Rack anómalo flutua levemente
    slot.group.position.y = slot.anomaly
        ? 0.03 + Math.sin(nowSec * 4.8 + slot.id) * 0.012
        : 0;

    // Marcador laranja pulsante no rack crítico
    if (slot.isCritical) {
        mat.opacity = 0.42 + Math.sin(nowSec * 4.8 + slot.id) * 0.16;
    }
}
```

#### Ligação de dados (WebSocket com fallback polling)

```javascript
async function loadRuntimeConfig() {
    const cfg = await fetch("/api/config").then(r => r.json());
    wsConfig.port    = cfg.ws_port;     // normalmente 8000
    wsConfig.enabled = cfg.ws_enabled;
}

function connectWebSocket() {
    socket = new WebSocket(`ws://${wsConfig.host}:${wsConfig.port}`);

    socket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        handleTwinMessage(payload);   // atualiza 3D + painel
    };

    socket.onclose = () => {
        startPolling();               // fallback: GET /api/twin a cada 1s
        reconnectTimer = setTimeout(connectWebSocket, 1200);
    };
}
```

O frontend lê primeiro `/api/config` para saber a porta WS correta (pode ser diferente do padrão). Se o WS fechar, ativa polling HTTP automático e tenta reconectar.

---

## 11. Simulador de Nós — `tools/node_simulator.py`

Corre em Python sem hardware, simulando R00, R07 e CDU1 via TCP (porta 5000).

### Modelo térmico `RackModel.step()`

```python
def step(self, dt, elapsed, supply):
    heat_gain  = self.base_heat * (0.45 + heat * 1.2) + noise
    hot_to_liq = 0.22 * (self.t_hot - self.t_liquid)
    forced_rej = (0.05 + 0.25 * fan) * self.fault_scale * (self.t_hot - supply)
    flow_rej   = 0.16 * flow * self.fault_scale * (self.t_hot - supply)

    d_hot    = heat_gain - hot_to_liq - forced_rej - flow_rej
    d_liquid = hot_to_liq - 0.18 * flow * (self.t_liquid - supply)
```

Física idêntica à do firmware em modo simulado. O `fault_scale` começa em 1.0 e baixa para 0.6 quando o rack entra em fault, reduzindo a capacidade de arrefecimento.

### Injeção de anomalia

```python
rack_b = RackModel("R07", ..., anomaly_after=45.0)

# Em step():
if self.anomaly_after and not self.anomaly_applied and elapsed >= self.anomaly_after:
    self.fault_scale = 0.6       # arrefecimento degradado
    self.base_heat += 0.8        # carga térmica aumentada
    self.anomaly_applied = True
```

45 segundos após o início da simulação, R07 entra em fault. Isto testa a deteção de anomalia do servidor e a resposta cooperativa (R00 deve receber comando para aumentar a própria carga).

### Ciclo de simulação

```python
for rack in (rack_a, rack_b):
    ok, response, error = send_once(host, port, rack.telemetry(now_ms))
    if ok:
        rack.apply_command(response)   # atualiza fan/heat/pump com o comando recebido
```

O simulador aplica os comandos recebidos ao seu modelo interno — a simulação é **closed-loop**: o servidor influencia o comportamento futuro do simulador.

---

## 12. Script de Build CDU — `tools/cdu_build.ps1`

```powershell
# Isola o cache do ESP32-C6 para evitar conflitos com o ESP32 clássico
$env:PLATFORMIO_PACKAGES_DIR = ".pio-cdu-packages"
pio run -e cdu_esp32c6
```

O ESP32-C6 (RISC-V) e o ESP32 clássico (Xtensa) usam toolchains completamente diferentes. Se ambos partilhassem a pasta `.pio`, poderia haver conflitos de cache. Este script isola o build do CDU numa pasta dedicada.

---

## 13. Dependências Python — `requirements.txt`

```
websockets
numpy
scikit-learn
```

Todas opcionais para o funcionamento mínimo do servidor:
- `websockets`: habilita WS-twin e WS-edge (sem ele, só TCP + HTTP funcionam)
- `numpy` + `scikit-learn`: habilita IsolationForest (sem eles, usa zscore)

Instalar: `pip install -r requirements.txt`

---

## 14. Fluxo de Dados Completo

### Ciclo normal de rack (1s)

```
ESP32 (R00)                      server.py
─────────────────────────────────────────────────────
1. Lê DS18B20 (ou simula)
2. Calcula heat_pwm local
3. Serializa JSON:
   {"type":"rack_telemetry","id":"R00",
    "t_hot":52.3,"t_liquid":47.1,
    "heat_pwm":156,"rssi":-48,...}
4. WS.sendTXT() ──────────────────► WS-edge (:8765)
                                    process_message()
                                    ├─ normaliza ID → R00
                                    ├─ valida: R00 ∈ {R00,R07} ✓
                                    ├─ AnomalyDetector.detect([52.3,47.1,156])
                                    ├─ atualiza racks_real["R00"]
                                    ├─ _update_model(now) → todos os 8 racks
                                    └─ retorna rack_cmds["R00"]
5. ◄────────────────────────────── {"type":"rack_cmd","heat_pwm":148,
                                    "anomaly":false,"mode":"heat-only-co-op",...}
6. Aplica remote setpoint (60%)
7. Atua heater (time-proportioning)
8. Aguarda 1s → próximo ciclo
```

### Atualização do dashboard (500ms)

```
server.py                         browser (twin3d)
─────────────────────────────────────────────────────
WS-twin (:8000) ──────────────► socket.onmessage()
get_twin_payload()                handleTwinMessage(payload)
├─ 8 racks (real + virtual)       ├─ updatePanel() → KPIs
├─ CDU state                      ├─ rackSlots[i].targetHot = rack.temp_hot
└─ global KPIs                    └─ applyRackVisual() em cada frame:
                                      cor emissiva + bloom + halo + marker
```

### Sequência de anomalia

```
1. rack_b.t_hot > 80°C
2. ESP32 R07: localAnomaly=true, heat_pwm=0
3. Servidor: ai_anom=true (zscore desvio > 3.2σ)
4. anomaly=true → anomalies_total++
5. rack_cmds["R07"] = {"mode":"guard","heat_pwm":80,"anomaly":true}
6. cdu_cmd = {"fanA_pwm":255,"fanB_pwm":255}  (emergência)
7. global_state.anomaly_risk_pct → alto
8. Frontend: rack R07 pisca vermelho, marcador laranja no chão, CDU fans=255
9. ESP32 R07 aplica remote setpoint: heat cortado
10. Temperatura começa a baixar
11. Depois de ~60s sem anomalia: zscore normaliza, risk baixa 40%
```

---

*Relatório gerado em 2026-03-08. Cobre 100% do código de runtime do repositório AI-IoT.*
