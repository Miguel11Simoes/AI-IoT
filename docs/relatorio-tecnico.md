# Relatório Técnico: Sistema AI-IoT de Arrefecimento Cooperativo

**Data:** 20 de Fevereiro de 2026  
**Autor:** Sistema AI-IoT  
**Versão:** 1.0

---

## Índice

1. [Objetivo do Projeto](#1-objetivo-do-projeto)
2. [Arquitetura do Sistema](#2-arquitetura-do-sistema)
3. [Implementação Software](#3-implementação-software)
4. [Guia de Implementação Hardware](#4-guia-de-implementação-hardware)
5. [Checklist de Bring-Up](#5-checklist-de-bring-up)
6. [Troubleshooting](#6-troubleshooting)

---

## 1. Objetivo do Projeto

### 1.1 Visão Geral

O projeto **AI-IoT Cooperative Cooling** implementa um sistema distribuído de arrefecimento líquido inteligente, onde múltiplos nós (microcontroladores) colaboram através de um servidor central equipado com deteção de anomalias baseada em IA. O objetivo é otimizar o arrefecimento de forma cooperativa, detetando e respondendo automaticamente a anomalias térmicas antes que se tornem críticas.

### 1.2 Motivação Técnica

Sistemas de arrefecimento tradicionais operam de forma isolada, reagindo apenas a condições locais. Este projeto resolve três problemas fundamentais:

1. **Otimização Global**: Um nó pode estar em stress térmico enquanto outros têm capacidade ociosa. A decisão cooperativa redistribui esforço de arrefecimento.

2. **Deteção Precoce de Falhas**: A IA identifica padrões anómalos (ex: bomba com eficiência reduzida, sensor a degradar-se) antes da falha catastrófica.

3. **Simulação Pré-Hardware**: Todo o sistema funciona em modo simulado, permitindo validação completa de lógica, protocolos e IA antes de comprar componentes físicos.

### 1.3 Casos de Uso

- **Data Centers**: Múltiplos servidores com arrefecimento líquido partilhado
- **Industrial**: Células de fabrico com dissipação térmica variável
- **Investigação**: Validação de algoritmos cooperativos em sistemas embebidos
- **Didático**: Demonstração completa de IoT + IA + controlo em tempo real

### 1.4 Especificações Técnicas

| Componente | Especificação |
|------------|---------------|
| **Nós** | 2 (expandível) |
| **MCU Nó A** | ESP32 (240 MHz, dual-core, WiFi+BT) |
| **MCU Nó B** | RP2040 (133 MHz, dual-core, PIO) |
| **Comunicação** | Ethernet TCP via W5500 SPI |
| **Sensores** | DS18B20 (1-Wire, ±0.5°C) |
| **Atuadores** | MOSFET PWM (ventilador + bomba) |
| **Servidor** | Python 3.8+ com scikit-learn |
| **Ciclo de Controlo** | 1 segundo |
| **Latência Máx** | 1.3 segundos (timeout de rede) |

---

## 2. Arquitetura do Sistema

### 2.1 Arquitetura Geral

```
┌─────────────────────────────────────────────────────────────┐
│                      SERVIDOR PYTHON                         │
│  ┌──────────────┐  ┌────────────────┐  ┌────────────────┐  │
│  │ TCP Server   │  │  Cooperative   │  │   AI Anomaly   │  │
│  │ (asyncio)    │──│  Decision      │──│   Detector     │  │
│  │ Port 5000    │  │  Engine        │  │ (zscore/ML)    │  │
│  └──────────────┘  └────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────┘
           ▲                            ▲
           │ TCP/JSON                   │ TCP/JSON
           │                            │
┌──────────┴─────────┐      ┌──────────┴─────────┐
│    NODE A (ESP32)  │      │   NODE B (RP2040)  │
│                    │      │                    │
│ ┌────────────────┐ │      │ ┌────────────────┐ │
│ │ FSM Controller │ │      │ │ FSM Controller │ │
│ └────────────────┘ │      │ └────────────────┘ │
│ ┌────────────────┐ │      │ ┌────────────────┐ │
│ │ Sensor Manager │ │      │ │ Sensor Manager │ │
│ │  - DS18B20 x2  │ │      │ │  - DS18B20 x2  │ │
│ │  - Thermal Sim │ │      │ │  - Thermal Sim │ │
│ └────────────────┘ │      │ └────────────────┘ │
│ ┌────────────────┐ │      │ ┌────────────────┐ │
│ │Control Manager │ │      │ │Control Manager │ │
│ │  - Local PID   │ │      │ │  - Local PID   │ │
│ │  - Remote Blend│ │      │ │  - Remote Blend│ │
│ │  - Safety      │ │      │ │  - Safety      │ │
│ └────────────────┘ │      │ └────────────────┘ │
│ ┌────────────────┐ │      │ ┌────────────────┐ │
│ │Network (W5500) │ │      │ │Network (W5500) │ │
│ │  - TCP Client  │ │      │ │  - TCP Client  │ │
│ │  - JSON Proto  │ │      │ │  - JSON Proto  │ │
│ └────────────────┘ │      │ └────────────────┘ │
│         │          │      │         │          │
│    ┌────┴────┐     │      │    ┌────┴────┐     │
│    │ FAN PWM │     │      │    │ FAN PWM │     │
│    │ PUMP PWM│     │      │    │ PUMP PWM│     │
│    └─────────┘     │      │    └─────────┘     │
└────────────────────┘      └────────────────────┘
```

### 2.2 Fluxo de Dados (Ciclo de 1 segundo)

```
1. [NODE] READ_SENSORS → DS18B20 ou modelo térmico → T_hot, T_liquid
2. [NODE] CONTROL_LOCAL → PID local calcula fan_pwm, pump_pwm
3. [NODE] SEND_DATA → JSON telemetry via TCP → SERVER
4. [SERVER] Recebe de todos os nós → calcula média global T_hot
5. [SERVER] AI anomaly detection → zscore ou IsolationForest
6. [SERVER] Cooperative decision → setpoints para cada nó
7. [SERVER] Responde JSON comando → target_fan/pump, anomaly flag
8. [NODE] APPLY_COMMAND → blend local (40%) + remote (60%)
9. [NODE] Atualiza PWM → MOSFET → ventilador/bomba
10. [NODE] WAIT_NEXT → aguarda próximo ciclo
```

### 2.3 Protocolo de Comunicação

#### Telemetria (Node → Server)

```json
{
  "id": "A",
  "cycle": 1234,
  "uptime_ms": 1234000,
  "t_hot": 45.8,
  "t_liquid": 38.2,
  "fan_pwm": 180,
  "pump_pwm": 170,
  "virtual_flow": 0.667,
  "sensor_ok": true,
  "sim_mode": true,
  "local_anomaly": false,
  "network_ok": true
}
```

#### Comando (Server → Node)

```json
{
  "target_fan_pwm": 200,
  "target_pump_pwm": 190,
  "global_avg_hot": 47.3,
  "anomaly": false,
  "mode": "cooperative"
}
```

---

## 3. Implementação Software

### 3.1 Estrutura do Projeto

```
AI-IoT/
├── platformio.ini              # Configuração PlatformIO (2 ambientes)
├── include/
│   └── ProjectConfig.h         # Configuração central (rede, pinos, params)
├── lib/
│   ├── sensors/src/
│   │   ├── Sensors.h           # Interface sensor manager
│   │   └── Sensors.cpp         # Modelo térmico + DS18B20
│   ├── control/src/
│   │   ├── Control.h           # Interface controlo
│   │   └── Control.cpp         # PID local + blend remoto + safety
│   ├── network/src/
│   │   ├── Network.h           # Interface rede
│   │   └── Network.cpp         # W5500 Ethernet TCP client
│   └── protocol/src/
│       ├── Protocol.h          # JSON encode/decode
│       └── Protocol.cpp        # ArduinoJson wrapper
├── src/
│   └── main.cpp                # FSM principal do nó
├── tools/
│   └── node_simulator.py       # Simulador software (2 nós virtuais)
├── server.py                   # Servidor cooperativo + AI
├── requirements.txt            # Dependências Python
└── logs/                       # CSV telemetria (criado em runtime)
```

### 3.2 Firmware - Máquina de Estados (main.cpp)

O firmware implementa uma **FSM explícita** com 7 estados:

#### **INIT** (Inicialização)

```cpp
gSensors.begin();     // Configura OneWire, inicializa modelo térmico
gControl.begin();     // Configura PWM pins, valores iniciais mínimos
gNetwork.begin();     // Reset W5500, DHCP/Static IP, verifica link
```

**Transição**: → `READ_SENSORS` após 500ms

#### **READ_SENSORS** (Leitura de Sensores)

```cpp
gLastSensor = gSensors.update(nowMs, fanPwm, pumpPwm);
// Se SIMULATED_COOLING=1: integra equações térmicas
// Se SIMULATED_COOLING=0: lê DS18B20 via OneWire
```

**Modelo Térmico Implementado**:

$$
\frac{dT_{hot}}{dt} = Q_{in} - k_1 \cdot (T_{hot} - T_{liquid}) - k_2 \cdot fan \cdot (T_{hot} - T_{amb}) - k_3 \cdot flow \cdot (T_{hot} - T_{liquid})
$$

$$
\frac{dT_{liquid}}{dt} = k_1 \cdot (T_{hot} - T_{liquid}) + k_4 \cdot flow \cdot (T_{hot} - T_{liquid}) - k_5 \cdot fan \cdot (T_{liquid} - T_{amb})
$$

Onde:
- `Q_in = 2.8 °C/s` (heat gain)
- `k_1 = 0.22` (hot to liquid condução)
- `k_2 = 0.03` (hot to ambient convecção)
- `k_3 = 0.24` (flow cooling)
- `k_4 = 0.45` (flow coupling)
- `k_5 = 0.11` (liquid to ambient)

**Transição**: → `CONTROL_LOCAL`

#### **CONTROL_LOCAL** (Controlo Local)

```cpp
gLastActuation = gControl.compute(tHot, tLiquid, sensorOk, nowMs);
// 1. PID local: fan = f(t_hot, delta_T)
// 2. Deteta anomalias: t_hot > 80°C || dT/dt > 5°C/s
// 3. Proteção crítica: t_hot > 88°C → PWM max
```

**Lógica de Segurança**:
- **Anomalia local**: Sensor falha OU temp > 80°C OU subida > 5°C/s → PWM máximo
- **Crítico**: temp > 88°C → PWM máximo + flag
- **Blend**: Se comando remoto válido: `PWM_final = 0.4*local + 0.6*remote`

**Transição**: → `SEND_DATA`

#### **SEND_DATA** (Envio de Telemetria)

```cpp
gPayload = encodeTelemetryJson(...);  // Serializa JSON
gNetworkOk = gNetwork.startRequest(gPayload);  // TCP connect + send
```

**Transição**: Se sucesso → `WAIT_SERVER`, se falha → `APPLY_COMMAND` (usa local)

#### **WAIT_SERVER** (Aguarda Resposta)

```cpp
PollStatus status = gNetwork.pollResponse(gResponse);
// COMPLETED: parse JSON, extrai setpoints
// TIMEOUT (1.3s): incrementa contador, usa controlo local
// FAILED: erro de conexão, usa controlo local
```

**Parsing de Resposta**:
```cpp
decodeCommandJson(gResponse, gLastCommand);
gControl.setRemoteSetpoints({
  .fanPwm = cmd.targetFanPwm,
  .pumpPwm = cmd.targetPumpPwm,
  .anomaly = cmd.anomaly,
  .valid = true
}, nowMs);
```

**Transição**: → `APPLY_COMMAND`

#### **APPLY_COMMAND** (Aplicar Controlo)

```cpp
gControl.apply(gLastActuation);  // analogWrite(FAN_PIN, pwm)
```

**Transição**: → `WAIT_NEXT`

#### **WAIT_NEXT** (Espera Próximo Ciclo)

```cpp
uint32_t elapsed = nowMs - gCycleStartedMs;
if (elapsed >= CYCLE_INTERVAL_MS) {  // 1000ms
  gState = READ_SENSORS;
}
```

**Estatísticas Impressas** (a cada 60s):
- Ciclos completados
- ACKs recebidos
- Timeouts
- Falhas de rede
- Estado atual de PWM

### 3.3 Biblioteca Sensors (Modelo Térmico)

#### Arquitetura

```cpp
class SensorManager {
  Config config_;              // Parâmetros de simulação
  OneWire oneWire_;            // Bus 1-Wire
  DallasTemperature dallas_;   // Driver DS18B20
  float simulatedHotC_;        // Estado térmico virtual
  float simulatedLiquidC_;     // Estado térmico virtual
  uint32_t lastUpdateMs_;      // Timestamp para dt
};
```

#### Modos de Operação

**1. Modo Simulado** (`SIMULATED_COOLING=1`)

```cpp
SensorReadout updateSimulated(uint32_t nowMs, uint8_t fanPwm, uint8_t pumpPwm) {
  float dtSec = (nowMs - lastUpdateMs_) / 1000.0f;
  // Integração Euler das ODEs
  simulatedHotC_ += dHot * dtSec;
  simulatedLiquidC_ += dLiquid * dtSec;
  // Clamp físico: [T_amb-2, 130°C]
  return {tHotC, tLiquidC, sensorOk:true, virtualFlow};
}
```

**2. Modo Real** (`SIMULATED_COOLING=0`)

```cpp
SensorReadout updateFromHardware(uint32_t nowMs, uint8_t fanPwm, uint8_t pumpPwm) {
  dallas_.requestTemperatures();  // 750ms @ 12-bit
  float hot = dallas_.getTempCByIndex(0);
  float liquid = dallas_.getTempCByIndex(1);
  
  if (validTemperature(hot) && validTemperature(liquid)) {
    return {hot, liquid, sensorOk:true, virtualFlow};
  }
  // FALLBACK: Se sensor falha, usa modelo térmico
  return updateSimulated(nowMs, fanPwm, pumpPwm, sensorOk:false);
}
```

**Vantagens do Fallback**:
- Sistema continua operacional com sensor desconectado
- Debug sem hardware físico
- Transição suave entre simulação e produção

### 3.4 Biblioteca Control (PID + Segurança)

#### Controlo Local

```cpp
uint8_t localFanFromTemp(float tHotC, float tLiquidC) {
  float delta = tHotC - tLiquidC;
  int raw = 90 + (tHotC - 30)*3.5 + delta*3.0;
  return clamp(raw, minFanPwm, maxFanPwm);
}
```

**Estratégia**: PWM base 90 + termo proporcional à temperatura + termo proporcional ao gradiente

#### Deteção de Anomalias

```cpp
float riseRate = (tHotC - lastHotC_) / dtSec;
bool localFault = (!sensorOk) || 
                  (tHotC >= ANOMALY_TEMP_C) ||  // 80°C
                  (riseRate >= MAX_RISE_RATE);   // 5°C/s
```

#### Blend Local + Remoto

```cpp
if (remote.valid && remoteFresh(nowMs)) {
  fan = (localFan * 4 + remoteFan * 6) / 10;  // 40% local, 60% remote
  pump = (localPump * 4 + remotePump * 6) / 10;
}

if (remote.anomaly) {
  fan = maxFanPwm;   // Override: servidor detetou anomalia global
  pump = maxPumpPwm;
}
```

#### Proteção Final

```cpp
if (tHotC >= CRITICAL_TEMP_C) {  // 88°C
  fan = maxFanPwm;
  pump = maxPumpPwm;
  localAnomaly = true;
}
```

**Hierarquia de Segurança**:
1. Crítico local (88°C) → PWM máximo imediato
2. Anomalia local (80°C ou taxa) → PWM máximo
3. Anomalia remota (servidor) → PWM máximo
4. Cooperativo normal → blend 40/60

### 3.5 Biblioteca Network (W5500 TCP)

#### Inicialização

```cpp
void begin() {
  configureSpi();    // ESP32: SPI.begin(sck, miso, mosi, cs)
  resetW5500();      // Hardware reset: LOW 40ms
  
  Ethernet.init(csPin);
  Ethernet.begin(mac, ip, dns, gateway, subnet);
  ready_ = (hardwareStatus() != EthernetNoHardware);
}
```

#### Request Non-Blocking

```cpp
bool startRequest(const String& payload) {
  if (!client_.connect(serverIp, serverPort)) return false;
  
  client_.print(payload);
  client_.print('\n');
  active_ = true;
  requestStartedMs_ = millis();
  return true;
}
```

#### Response Polling

```cpp
PollStatus pollResponse(String& responseLine) {
  while (client_.available() > 0) {
    char ch = client_.read();
    if (ch == '\n') {
      responseLine = rxBuffer_;
      close();
      return COMPLETED;
    }
    rxBuffer_ += ch;
  }
  
  if (millis() - requestStartedMs_ >= TIMEOUT) {
    close();
    return TIMEOUT;
  }
  
  return PENDING;
}
```

**Vantagens**:
- Non-blocking: FSM continua a correr durante espera de rede
- Timeout configurável (1.3s default)
- Buffer limitado (512 bytes) previne overflow
- Deteta desconexão prematura

### 3.6 Servidor Python (server.py)

#### Arquitetura

```python
CooperativeServer:
  - global_state: Dict[node_id, NodeSnapshot]
  - detector: AnomalyDetector (zscore ou IsolationForest)
  - TCP server multithreaded (1 thread por conexão)
  - CSV logger thread-safe
```

#### Detetor de Anomalias

**Modo 1: Z-Score** (default, sem dependências ML)

```python
def _detect_with_zscore(self, features: List[float]) -> bool:
    for idx, value in enumerate(features):
        col = [row[idx] for row in buffer]
        mean = statistics.fmean(col)
        std = statistics.pstdev(col) or 1e-6
        z = abs((value - mean) / std)
        if z > 3.2:  # ~99.9% confidence
            return True
    return False
```

**Features**: `[t_hot, t_liquid, fan_pwm, pump_pwm, virtual_flow]`

**Modo 2: Isolation Forest** (requer scikit-learn)

```python
model = IsolationForest(
    contamination=0.05,  # 5% esperado anómalo
    n_estimators=30,
    max_samples=128,
    random_state=42
)
model.fit(buffer)  # Treino assíncrono
pred = model.predict([features])  # -1 = anomalia
```

**Retreino Adaptativo**:
- Warmup: 50 amostras antes de ativar
- Retreina a cada 10 amostras novas
- Threading: treino não bloqueia deteção
- Fallback: Se treino falha, usa zscore

#### Decisão Cooperativa

```python
def _make_decision(self, payload: dict) -> dict:
    # 1. Remove nós stale (>10s sem update)
    active_nodes = [n for n in global_state.values() 
                    if now - n.received_ts < stale_seconds]
    
    # 2. Calcula média global
    global_avg_hot = mean([n.payload["t_hot"] for n in active_nodes])
    
    # 3. Deteta anomalia
    features = [payload["t_hot"], payload["t_liquid"], 
                payload["fan_pwm"], payload["pump_pwm"], 
                payload["virtual_flow"]]
    anomaly, detector_mode = detector.detect(features)
    
    # 4. Calcula setpoints
    if anomaly:
        mode = "anomaly_response"
        target_fan = 255
        target_pump = 255
    else:
        mode = "cooperative"
        delta = payload["t_hot"] - global_avg_hot
        target_fan = clamp(180 + delta * 5, 70, 255)
        target_pump = clamp(160 + delta * 4, 60, 255)
    
    return {
        "target_fan_pwm": target_fan,
        "target_pump_pwm": target_pump,
        "global_avg_hot": global_avg_hot,
        "anomaly": anomaly,
        "mode": mode
    }
```

**Estratégia Cooperativa**:
- Nó acima da média → aumenta PWM proporcionalmente
- Nó abaixo da média → reduz PWM (economiza energia)
- Anomalia → PWM máximo imediato em todos os nós

#### Logging

```python
CSV fields:
  ts, node, t_hot, t_liquid, fan_pwm, pump_pwm,
  global_avg_hot, target_fan_pwm, target_pump_pwm,
  anomaly, detector, mode
```

**Análise Posterior**:
- Plotar temperatura vs tempo
- Identificar eventos de anomalia
- Validar resposta cooperativa
- Benchmarking de detetores

### 3.7 Simulador (node_simulator.py)

Replica o comportamento do firmware em Python puro para validação sem hardware:

```python
class NodeModel:
    def step(self, dt: float, elapsed: float):
        # Mesmo modelo térmico do firmware
        d_hot = heat_gain - hot_to_ambient - hot_to_liquid - flow_cooling
        d_liquid = hot_to_liquid + flow_cooling - liquid_to_ambient
        self.t_hot += d_hot * dt
        self.t_liquid += d_liquid * dt
    
    def telemetry(self) -> dict:
        # Mesmo formato JSON que firmware
```

**Injeção de Anomalia**:
```python
if elapsed >= anomaly_after:
    self.cooling_fault_scale = 0.6  # Bomba a 60% eficiência
    self.base_heat += 0.6           # Carga extra
```

**Uso**:
```bash
python tools/node_simulator.py \
  --host 127.0.0.1 \
  --port 5000 \
  --duration 120 \
  --inject-anomaly-after 45
```

Simula 2 nós (A e B) por 120 segundos, introduz falha no nó B aos 45s.

### 3.8 Configuração Centralizada (ProjectConfig.h)

Todas as constantes em um único local, sobrescritas por `platformio.ini`:

```cpp
// Rede
#define SERVER_IP_1 192  // Endereço servidor
#define SERVER_PORT 5000

// Hardware
#define W5500_CS_PIN 5
#define ONE_WIRE_PIN 14
#define FAN_PIN 17
#define PUMP_PIN 16

// Timing
#define CYCLE_INTERVAL_MS 1000
#define NETWORK_TIMEOUT_MS 1300
#define REMOTE_CMD_TTL_MS 5000

// Simulação
#define SIMULATED_COOLING 1
#define HEAT_GAIN_C_PER_SEC 2.8
#define HOT_TO_LIQUID_COEFF 0.22
// ... 10+ parâmetros térmicos

// Segurança
#define ANOMALY_TEMP_C 80
#define CRITICAL_TEMP_C 88
```

**Vantagens**:
- Mudança de modo simulado/real: 1 linha
- Tuning de parâmetros sem tocar no código
- Ambientes diferentes (ESP32 vs RP2040) partilham base

---

## 4. Guia de Implementação Hardware

### 4.1 Lista de Materiais (BOM)

#### Nó A (ESP32)

| Quantidade | Componente | Especificação | Notas |
|------------|------------|---------------|-------|
| 1 | ESP32 DevKit | 30-pin, USB-C | Ex: ESP32-WROOM-32 |
| 1 | W5500 Ethernet | SPI, RJ45 | Wiznet oficial |
| 2 | DS18B20 | TO-92, 1-Wire | ±0.5°C, 3.3V |
| 1 | Resistor 4.7kΩ | 1/4W | Pull-up 1-Wire |
| 2 | MOSFET IRLZ44N | N-ch, TO-220, logic-level | RDS(on) < 30mΩ |
| 2 | Resistor 10kΩ | 1/4W | Pull-down gate MOSFET |
| 2 | Diodo 1N4007 | 1A, flyback | Proteção indutiva |
| 1 | Ventilador 12V | PWM 4-pin | Ex: Noctua NF-A12x25 |
| 1 | Bomba 12V | DC brushless | Ex: ‎Alphacool DC-LT 2600 |
| 1 | Fonte 12V 5A | 60W | Alimentação fan+pump |
| 1 | Buck converter 12V→3.3V | 3A | Alimentação ESP32 |
| 1 | Breadboard 830 pontos | - | Prototipagem |
| 20 | Jumper wires | M-M, F-M | Conexões |

#### Nó B (RP2040)

| Quantidade | Componente | Especificação | Notas |
|------------|------------|---------------|-------|
| 1 | Raspberry Pi Pico | RP2040, USB-C | Oficial ou clone |
| 1 | W5500 Ethernet | SPI, RJ45 | Mesmo tipo que nó A |
| 2 | DS18B20 | TO-92, 1-Wire | Mesmos sensores |
| 1 | Resistor 4.7kΩ | 1/4W | Pull-up 1-Wire |
| 2 | MOSFET IRLZ44N | N-ch, TO-220, logic-level | Mesmos MOSFETs |
| 2 | Resistor 10kΩ | 1/4W | Pull-down gate |
| 2 | Diodo 1N4007 | 1A | Proteção |
| 1 | Ventilador 12V | PWM 4-pin | Mesma família |
| 1 | Bomba 12V | DC brushless | Mesma família |
| 1 | Fonte 12V 5A | 60W | Alimentação |
| 1 | Buck converter 12V→3.3V | 3A | Alimentação Pico |
| 1 | Breadboard 830 pontos | - | Prototipagem |
| 20 | Jumper wires | M-M, F-M | Conexões |

#### Componentes Partilhados

| Quantidade | Componente | Especificação | Notas |
|------------|------------|---------------|-------|
| 1 | Switch Ethernet 5-port | Gigabit | Liga ambos os nós + PC |
| 3 | Cabo Ethernet | Cat5e, 1m | Nó A/B + PC |
| 1 | Multímetro | Continuidade, tensão | Debugging |
| 1 | Osciloscópio | Opcional | Debug PWM/SPI |

**Custo Total Estimado**: ~150-200€ (dependendo de fontes)

### 4.2 Pinout e Conexões

#### Nó A: ESP32 + W5500

```
ESP32 DevKit                W5500 Module
=============               ==============
GPIO 5  (CS)     ──────────>  CS
GPIO 4  (RESET)  ──────────>  RST
GPIO 18 (SCK)    ──────────>  SCK
GPIO 19 (MISO)   <──────────  MISO
GPIO 23 (MOSI)   ──────────>  MOSI
3.3V             ──────────>  VCC
GND              ──────────>  GND

GPIO 14 (1-Wire) ────┬──────>  DS18B20 #1 (DQ)
                     │
                     └──────>  DS18B20 #2 (DQ)
                     │
                    [4.7kΩ] (pull-up to 3.3V)

GPIO 17 (FAN)    ──────────>  MOSFET #1 Gate (via 10kΩ to GND)
GPIO 16 (PUMP)   ──────────>  MOSFET #2 Gate (via 10kΩ to GND)

MOSFET #1 Drain  ──────────>  Ventilador 12V (-)
MOSFET #2 Drain  ──────────>  Bomba 12V (-)
12V+             ──────────>  Ventilador (+), Bomba (+)
GND (power)      ──────────>  MOSFET Source, ESP32 GND comum

Buck Converter:
  IN+  ────────────────────>  12V fonte
  IN-  ────────────────────>  GND fonte
  OUT+ ────────────────────>  ESP32 VIN ou 3.3V
  OUT- ────────────────────>  GND comum
```

**Notas Críticas ESP32**:
- **Não** alimentar ESP32 via VIN com 12V se buck não estiver regulado para 5V
- Pinos 3.3V logic-level: usar IRLZ44N (não IRF540) para MOSFETs
- W5500 RST pode usar GPIO 4 (evitar GPIO 2 que afeta boot)
- DS18B20 em paralelo no mesmo pino: usar resistências de pull-up adequadas

#### Nó B: RP2040 + W5500

```
Raspberry Pi Pico           W5500 Module
===============             ==============
GPIO 17 (CS)     ──────────>  CS
GPIO 20 (RESET)  ──────────>  RST
GPIO 18 (SCK)    ──────────>  SCK
GPIO 16 (MISO)   <──────────  MISO
GPIO 19 (MOSI)   ──────────>  MOSI
3V3(OUT)         ──────────>  VCC
GND              ──────────>  GND

GPIO 2  (1-Wire) ────┬──────>  DS18B20 #1 (DQ)
                     │
                     └──────>  DS18B20 #2 (DQ)
                     │
                    [4.7kΩ] (pull-up to 3.3V)

GPIO 11 (FAN)    ──────────>  MOSFET #1 Gate (via 10kΩ to GND)
GPIO 10 (PUMP)   ──────────>  MOSFET #2 Gate (via 10kΩ to GND)

MOSFET #1 Drain  ──────────>  Ventilador 12V (-)
MOSFET #2 Drain  ──────────>  Bomba 12V (-)
12V+             ──────────>  Ventilador (+), Bomba (+)
GND (power)      ──────────>  MOSFET Source, Pico GND comum

Buck Converter:
  IN+  ────────────────────>  12V fonte
  IN-  ────────────────────>  GND fonte
  OUT+ ────────────────────>  Pico VSYS (5V) ou 3V3_EN
  OUT- ────────────────────>  GND comum
```

**Notas Críticas RP2040**:
- Pico pode ser alimentado por VSYS (5V) ou VBUS (USB)
- Não ligar 3.3V externo a 3V3(OUT) - este é saída do regulador
- SPI0 é usado: GP16-19 são hardware SPI pins
- GPIO 2 é seguro para 1-Wire (não interfere com boot)

### 4.3 Esquema de Potência

```
                  ┌──────────────────────────────────────┐
                  │      Fonte 12V 5A (60W)              │
                  └────────┬──────────────────────┬──────┘
                           │                      │
                     12V   │                      │  GND
                           │                      │
              ┌────────────┴────┐    ┌────────────┴──────┐
              │  Buck 12V→3.3V  │    │                   │
              │   (3A para MCU) │    │                   │
              └────────┬─────────┘    │                   │
                       │              │                   │
                  3.3V │              │                   │
                       │              │                   │
            ┌──────────┴──────────┐   │   ┌───────────────┴─────────────┐
            │   ESP32/Pico         │   │   │  MOSFET Power Stage         │
            │   + W5500 + DS18B20  │   │   │  (Fan + Pump drivers)       │
            └──────────────────────┘   │   └─────────────────────────────┘
                       │               │               │
                       └───────────────┴───────────────┘
                              GND comum (star ground)
```

**Regras de Segurança**:
1. **GND Comum**: Todos os GNDs (fonte, MCU, MOSFETs, sensores) conectados em star topology
2. **Diodos Flyback**: 1N4007 em paralelo com cada carga indutiva (fan/pump), cátodo ao +12V
3. **Corrente**: Ventilador ~0.2A, bomba ~1.5A → 12V*2A = 24W por nó → fonte 5A OK
4. **Verificação Continuidade**: Antes de ligar, verificar com multímetro:
   - Sem curto-circuito 12V-GND
   - Sem curto-circuito 3.3V-GND
   - MOSFETs com gate pulled-down (10kΩ)

### 4.4 Circuito MOSFET (Switching PWM)

```
                            12V+
                             │
                             │
                   ┌─────────┴─────────┐
                   │  Ventilador/Bomba  │
                   │      (carga)       │
                   └─────────┬─────────┘
                             │
                             ├─────────┐
                             │    [│◄├ Diodo 1N4007 flyback
                             │         │ (cátodo a 12V+)
                     Drain ──┤         │
                   ┌─────────┴─────────┴───┐
                   │   MOSFET IRLZ44N      │
                   │   (N-channel)         │
                   └─────────┬─────────────┘
                    Source   │
                             │
                  ┌──────────┴──────────┐
                  │                     │
             Gate ├─[10kΩ]── GND   ───┴─── GND (star)
                  │
                  │
        MCU PWM ──┘ (GPIO 17/16 ou 11/10)
        (3.3V logic, frequência 490 Hz Arduino default)
```

**Funcionamento**:
- PWM alto (3.3V) → MOSFET ON → corrente flui pelo drain-source → carga ligada
- PWM baixo (0V) + 10kΩ pull-down → MOSFET OFF → carga desligada
- Duty cycle 50% → carga recebe 50% potência média
- Diodo protege contra voltagem reversa indutiva (back-EMF)

**Escolha IRLZ44N**:
- **Logic-level**: VGS(th) = 1-2V (funciona com 3.3V)
- RDS(on) @ VGS=4V: ~28mΩ → dissipação baixa: P = I²R = 1.5²*0.028 = 63mW
- ID(max) = 35A → margem enorme para 1.5A
- TO-220: pode adicionar dissipador se ambiente quente

**Alternativa**: IRL540N (mais barato, similar performance)

### 4.5 Topologia 1-Wire (DS18B20)

```
                 3.3V
                  │
                  │
                 [4.7kΩ] pull-up
                  │
     ┌────────────┼────────────┐
     │            │            │
   ──┴──        ──┴──        ──┴──
   DS18B20 #1   DS18B20 #2   MCU GPIO (GPIO 14 ou 2)
   (DQ)         (DQ)          (1-Wire bus)
     │            │            │
     └────────────┴────────────┘
                  │
                 GND

DS18B20 pinout (TO-92, frente plana vista de frente):
  1. GND
  2. DQ (data)
  3. VDD (3.3V)
```

**Notas**:
- **Parasitic Mode**: Pode usar 2 fios (GND+DQ) se VDD ligado a GND, mas menos confiável
- **Endereçamento**: Cada DS18B20 tem ROM única de 64-bit
- **Código**: `dallas.getTempCByIndex(0)` acede ao primeiro sensor no bus
- **Troubleshooting**: Se leitura -127°C → sensor desconectado ou pull-up ausente

### 4.6 Setup de Rede Ethernet

```
┌──────────────┐         ┌──────────────┐         ┌──────────────┐
│  Servidor PC │         │  Switch      │         │  Nó A (ESP32)│
│ 192.168.1.10 ├─────────┤  Ethernet    ├─────────┤ 192.168.1.100│
└──────────────┘   eth0  │  5-port      │  eth1   └──────────────┘
                          │              │
                          │              │  eth2   ┌──────────────┐
                          │              ├─────────┤ Nó B (RP2040)│
                          └──────────────┘         │ 192.168.1.101│
                                                   └──────────────┘
```

**Configuração de Rede**:
- **Subnet**: 255.255.255.0 (`/24`)
- **Gateway**: 192.168.1.1 (router opcional)
- **DNS**: 8.8.8.8 (não usado, mas configurado)
- **Servidor**: escutar em `0.0.0.0:5000` (todas interfaces)

**Verificação**:
```bash
# No PC (servidor)
python server.py --host 0.0.0.0 --port 5000 --detector zscore

# Testar conectividade (após nós ligarem)
ping 192.168.1.100
ping 192.168.1.101

# Ver logs do servidor
tail -f logs/telemetry_log.csv
```

### 4.7 Procedimento de Montagem

#### Fase 1: Alimentação Isolada (Teste Buck Converter)

1. **Sem MCU conectado**, ligar buck converter à fonte 12V
2. Ajustar potenciómetro do buck para output **3.3V ± 0.1V** (multímetro)
3. Verificar ripple com osciloscópio < 100mV (opcional)
4. Testar com carga dummy (LED + resistor 330Ω)

#### Fase 2: MCU + W5500 (Teste Ethernet)

1. Conectar MCU ao buck converter (3.3V + GND)
2. Conectar W5500:
   - SPI pins (CS, SCK, MISO, MOSI)
   - RESET pin
   - VCC 3.3V, GND
3. Ligar cabo Ethernet do W5500 ao switch
4. Upload firmware (código de teste):
```cpp
// Verificar apenas NetworkManager::begin()
if (gNetwork.ready()) {
  Serial.println("W5500 OK");
  Serial.println(Ethernet.localIP());
}
```
5. Monitor serial: deve imprimir IP 192.168.1.100/101

#### Fase 3: Sensores 1-Wire (Teste DS18B20)

1. Montar circuito DS18B20:
   - VDD → 3.3V
   - GND → GND
   - DQ → GPIO 14/2 + pull-up 4.7kΩ
2. Upload firmware (código teste):
```cpp
gSensors.begin();
SensorReadout r = gSensors.update(millis(), 0, 0);
Serial.print("Hot: "); Serial.println(r.tHotC);
Serial.print("Liquid: "); Serial.println(r.tLiquidC);
```
3. Verificar temperatura ambiente (~20-25°C)
4. Testar: apertar sensor com dedos → temperatura deve subir

#### Fase 4: MOSFETs + Cargas Dummy (Teste PWM)

1. **Sem ventilador/bomba**, montar MOSFET:
   - Gate → GPIO 17/11 via 10kΩ pull-down a GND
   - Source → GND
   - Drain → LED + resistor 330Ω + 12V (carga dummy)
2. Upload firmware (código teste):
```cpp
analogWrite(FAN_PIN, 128);  // 50% duty
delay(5000);
analogWrite(FAN_PIN, 255);  // 100% duty
```
3. LED deve acender com brilho médio, depois máximo
4. Repetir para PUMP_PIN

#### Fase 5: Integração Completa (Sistema End-to-End)

1. Substituir LED dummy por ventilador 12V real
2. Adicionar diodo 1N4007 flyback (cátodo a 12V+)
3. Substituir segundo LED por bomba 12V
4. Adicionar diodo flyback na bomba
5. Ligar servidor Python no PC
6. Upload firmware completo
7. Verificar no server logs: telemetria a cada 1s

#### Fase 6: Validação Térmica (Teste com Carga Real)

1. Colocar DS18B20 #1 em dissipador térmico com carga (ex: resistor 10W)
2. Colocar DS18B20 #2 em bloco de refrigeração líquido
3. Ligar bomba para circular fluido
4. Observar servidor: temperatura deve estabilizar com PWM cooperativo
5. Introduzir anomalia: desligar bomba manualmente
6. Verificar deteção de anomalia no servidor + PWM máximo

### 4.8 Troubleshooting Hardware

| Sintoma | Causa Provável | Solução |
|---------|----------------|---------|
| W5500 não responde | Fio RESET não ligado ou CS errado | Verificar pinout, medir continuidade |
| IP não obtido | Cabo Ethernet desconectado | `Ethernet.linkStatus()` deve retornar `LinkON` |
| Serial imprime lixo | Baudrate incorreto | Verificar `monitor_speed = 115200` |
| DS18B20 retorna -127°C | Pull-up ausente ou sensor errado | Medir resistência DQ-VDD: deve ser ~4.7kΩ |
| MOSFET sempre ON | Pull-down ausente ou Gate flutuante | Adicionar 10kΩ Gate-GND, medir com multímetro |
| MOSFET não liga | Logic-level errado | Substituir por IRLZ44N, verificar VGS(th) |
| MCU reseta | Corrente insuficiente do buck | Buck de 3A mínimo, verificar voltage drop |
| Ventilador ruidoso | PWM frequência baixa (~490Hz) | Aumentar frequência para 25kHz (código) |
| Pump não funciona | Diodo flyback invertido | Cátodo deve estar a 12V+, ânodo a drain |
| Servidor timeout | Firewall bloqueando porta 5000 | `sudo ufw allow 5000/tcp` (Linux) |

---

## 5. Checklist de Bring-Up

### 5.1 Pré-Validação (Software-Only)

- [ ] **Build Firmware**: `pio run -e node_a_esp32` e `pio run -e node_b_pico` sem erros
- [ ] **Server Dependencies**: `pip install -r requirements.txt` sucesso
- [ ] **Simulação Completa**: 
  ```bash
  python server.py --host 0.0.0.0 --port 5000 --detector zscore &
  python tools/node_simulator.py --host 127.0.0.1 --port 5000 --duration 120 --inject-anomaly-after 45
  ```
  - [ ] Ambos nós A e B conectam
  - [ ] Telemetria a cada 1s visível no servidor
  - [ ] Anomalia detetada após 45s no nó B
  - [ ] CSV `logs/telemetry_log.csv` criado com dados

### 5.2 Hardware - Nó A (ESP32)

#### Alimentação
- [ ] Buck converter regulado para 3.3V ± 0.05V sem carga
- [ ] Buck mantém 3.3V com carga de 500mA (ESP32 + W5500)
- [ ] Fonte 12V entrega 5A sem queda de tensão
- [ ] GND comum verificado com multímetro (continuidade < 1Ω)

#### Ethernet
- [ ] W5500 SPI conectado (CS, SCK, MISO, MOSI verificados com multímetro)
- [ ] RESET pin conectado a GPIO 4
- [ ] LED W5500 "LINK" aceso após ligar cabo Ethernet
- [ ] Firmware imprime: `Network ready: 1` e `IP: 192.168.1.100`

#### Sensores
- [ ] DS18B20 #1 e #2 com pinout correto (VDD, GND, DQ)
- [ ] Pull-up 4.7kΩ medido entre DQ e 3.3V
- [ ] Firmware imprime temperaturas realistas (20-30°C ambiente)
- [ ] Tocar sensor com dedo → temperatura sobe em 2-5s

#### PWM
- [ ] MOSFET #1 (fan): Gate pull-down 10kΩ medido
- [ ] MOSFET #2 (pump): Gate pull-down 10kΩ medido
- [ ] Com carga dummy (LED): PWM 50% → brilho médio, PWM 100% → brilho máximo
- [ ] Diodos flyback orientados corretamente (multímetro modo diodo)

#### Sistema Completo
- [ ] Upload firmware completo: `pio run -e node_a_esp32 -t upload`
- [ ] Monitor serial: FSM imprime estados `READ_SENSORS` → `SEND_DATA` → `WAIT_SERVER`
- [ ] Servidor recebe telemetria: `{"id":"A", "t_hot":25.3, ...}`
- [ ] Ventilador gira (som audível), velocidade varia com PWM
- [ ] Bomba liga (som/vibração), velocidade varia com PWM

### 5.3 Hardware - Nó B (RP2040)

#### Alimentação
- [ ] Buck converter regulado para 3.3V (pode usar mesmo do nó A se capacidade OK)
- [ ] Pico alimentado via VSYS ou USB
- [ ] LED onboard Pico aceso

#### Ethernet
- [ ] W5500 SPI conectado (pinos diferentes do ESP32: verificar pinout)
- [ ] RESET pin conectado a GPIO 20
- [ ] LED W5500 "LINK" aceso
- [ ] Firmware imprime: `IP: 192.168.1.101`

#### Sensores
- [ ] DS18B20 #1 e #2 com pull-up 4.7kΩ em GPIO 2
- [ ] Temperaturas impressas no serial

#### PWM
- [ ] MOSFET fan em GPIO 11, pump em GPIO 10
- [ ] Teste com carga dummy OK

#### Sistema Completo
- [ ] Upload firmware: `pio run -e node_b_pico -t upload`
- [ ] Monitor serial: FSM funcional
- [ ] Servidor recebe telemetria do nó B
- [ ] Ventilador e bomba funcionais

### 5.4 Sistema Cooperativo

#### Comunicação Bidirecional
- [ ] Servidor imprime logs de ambos nós A e B
- [ ] CSV contém linhas de ambos os nós (`node` column = "A" e "B")
- [ ] Nós imprimem: `Server ACK: target_fan=XXX, global_avg=YY.Y`

#### Decisão Cooperativa
- [ ] Modo simulado OFF: `#define SIMULATED_COOLING 0`
- [ ] Aplicar carga térmica assimétrica:
  - Nó A: dissipador térmico com resistor 10W
  - Nó B: sem carga (temperatura ambiente)
- [ ] Após 30s:
  - Nó A: `t_hot` > média global → `target_fan_pwm` alto
  - Nó B: `t_hot` < média global → `target_fan_pwm` baixo
- [ ] Verificar no serial PWM diferentes entre nós

#### Deteção de Anomalia
- [ ] Desconectar bomba do nó A (ou desligar fonte 12V da bomba)
- [ ] Temperatura `t_hot` do nó A sobe rapidamente
- [ ] Servidor deteta: `"anomaly": true` no CSV
- [ ] Ambos os nós recebem comando: `target_fan_pwm=255, target_pump_pwm=255`
- [ ] Nó A imprime: `Local anomaly detected!`

#### Teste de Stress (24h)
- [ ] Sistema funciona continuamente por 24h
- [ ] Verificar CSV: sem gaps de telemetria > 10s
- [ ] Verificar memória MCU: sem leaks (uptime_ms cresce linear)
- [ ] Verificar servidor: sem crashes (excepções no log)

### 5.5 Validação Final

- [ ] **Documentação**: Este relatório revisto e atualizado com fotos do setup
- [ ] **Código Fonte**: Tag `v1.0-hardware-validated` no Git
- [ ] **Logs**: `logs/telemetry_log_24h.csv` anexado
- [ ] **Vídeo Demo**: 2-3 min mostrando:
  - Sistema em funcionamento
  - Injeção de anomalia
  - Resposta cooperativa
  - Dashboard plotando temperatura vs tempo

---

## 6. Troubleshooting

### 6.1 Problemas Comuns de Software

#### Firmware Não Compila

**Erro**: `fatal error: Arduino.h: No such file or directory`

**Solução**:
- Verificar `platform` e `framework` no `platformio.ini`
- Limpar build: `pio run -t clean`
- Reinstalar plataforma: `pio platform install espressif32@6.9.0`

#### W5500 Não Inicializa

**Erro**: `Network ready: 0`

**Causa**: Hardware não detetado no SPI

**Solução**:
1. Verificar `Ethernet.init(CS_PIN)` correto
2. Adicionar delays após reset:
```cpp
digitalWrite(resetPin, LOW);
delay(50);  // Aumentar para 50ms
digitalWrite(resetPin, HIGH);
delay(200); // Aumentar para 200ms
```
3. Testar SPI manualmente:
```cpp
SPI.begin();
pinMode(CS_PIN, OUTPUT);
digitalWrite(CS_PIN, LOW);
SPI.transfer(0x00);  // Read version register
uint8_t ver = SPI.transfer(0x00);
digitalWrite(CS_PIN, HIGH);
Serial.print("W5500 version (esperado 0x04): ");
Serial.println(ver, HEX);
```

#### JSON Parsing Falha

**Erro**: `Command parse failed`

**Causa**: Buffer insuficiente ou JSON malformado

**Solução**:
```cpp
JsonDocument doc;  // ArduinoJson v7: tamanho automático
// Se v6: StaticJsonDocument<512> doc;
```

Verificar no servidor: response termina com `\n`

#### PWM Não Responde

**Sintoma**: `analogWrite()` não muda duty cycle

**Causa Arduino**: Pinos sem suporte PWM

**Solução**:
- ESP32: Usar canais LEDC:
```cpp
ledcSetup(0, 5000, 8);  // canal 0, 5kHz, 8-bit
ledcAttachPin(FAN_PIN, 0);
ledcWrite(0, pwmValue);
```
- RP2040: Pinos 0-29 suportam PWM harware

#### Timeout Constante

**Sintoma**: `Server timeout` a cada ciclo

**Causa**: Latência > 1.3s ou servidor offline

**Solução**:
1. Aumentar timeout:
```cpp
#define NETWORK_TIMEOUT_MS 3000  // 3 segundos
```
2. Verificar ping: `ping 192.168.1.10` deve ser < 10ms
3. Verificar servidor: `netstat -tuln | grep 5000` deve mostrar `LISTEN`

### 6.2 Problemas Comuns de Hardware

#### MCU Não Liga

**Sintoma**: LED power não aceso

**Checklist**:
1. Medir tensão buck output: deve ser 3.3V ± 0.1V
2. Medir corrente: ESP32 ~80mA idle, ~200mA com WiFi (desabilitado aqui)
3. Verificar curto-circuito: desligar tudo, medir resistência 3.3V-GND > 100Ω
4. Capacitor decoupling: adicionar 100µF no buck output se instável

#### W5500 LED Não Acende

**Sintoma**: LED "LINK" apagado mesmo com cabo conectado

**Checklist**:
1. Cabo Ethernet: testar com outro dispositivo
2. Switch: porta com LED aceso?
3. Pinagem RJ45: usar tester de cabo
4. W5500 VCC: medir 3.3V com multímetro
5. W5500 clone: alguns precisam de pull-up externo em pinos específicos

#### DS18B20 Sempre -127°C

**Causa**: Sensor não responde no 1-Wire

**Solução**:
1. Medir resistência pull-up: entre GPIO e 3.3V deve ter ~4.7kΩ
2. Verificar pinout TO-92: flat face forward: GND | DQ | VDD
3. Testar sensor isoladamente:
```cpp
OneWire ow(14);
ow.reset();
ow.write(0xCC);  // Skip ROM
ow.write(0x44);  // Convert T
delay(750);
ow.reset();
ow.write(0xCC);
ow.write(0xBE);  // Read scratchpad
uint8_t data[9];
for (int i = 0; i < 9; i++) data[i] = ow.read();
// data[0] e data[1] são temperatura raw
```
4. Se múltiplos sensores: reduzir pull-up para 2.2kΩ

#### MOSFET Sempre ON

**Sintoma**: Carga sempre ligada mesmo com PWM = 0

**Causa**: Gate flutuante ou pull-down ausente

**Solução**:
1. Desligar MCU, medir resistência Gate-GND: deve ser 10kΩ
2. Medir tensão Gate com MCU OFF: deve ser 0V
3. Se MOSFET P-channel: trocar por N-channel (arquitetura low-side)

#### MOSFET Não Liga

**Sintoma**: Carga sempre desligada mesmo com PWM = 255

**Causa**: MOSFET não é logic-level

**Solução**:
1. Medir VGS: com PWM alto, deve ser ~3.3V
2. Datasheet: VGS(th) < 2.5V? Se não, trocar para IRLZ44N
3. Alternativa: adicionar gate driver (ex: TC4427)

#### Ventilador Ruidoso/Trepida

**Causa**: Frequência PWM baixa (~490Hz) cria vibração audível

**Solução**:
```cpp
// ESP32: aumentar frequência
ledcSetup(0, 25000, 8);  // 25kHz, inaudível

// RP2040: configurar PWM wrap
pwm_set_wrap(slice, 1250);  // 100MHz / 1250 = 80kHz
pwm_set_clkdiv(slice, 1.0f);
```

#### Bomba Não Funciona Mas LED de Teste Sim

**Causa**: Corrente da bomba > corrente do LED

**Solução**:
1. Medir corrente bomba: pode ser 1-2A (LED é ~20mA)
2. Verificar MOSFET RDS(on): P_diss = I²*RDS < 2W
3. Adicionar dissipador térmico no MOSFET
4. Verificar GND: star ground com fio grosso (AWG 18)

### 6.3 Problemas de Servidor Python

#### ModuleNotFoundError: sklearn

**Solução**:
```bash
pip install scikit-learn numpy
# Ou usar apenas zscore (default, sem deps)
python server.py --detector zscore
```

#### Port Already in Use

**Erro**: `OSError: [Errno 98] Address already in use`

**Solução**:
```bash
# Linux/Mac
lsof -i :5000
kill -9 <PID>

# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Ou usar outra porta
python server.py --port 5001
```

#### CSV Não Criado

**Causa**: Permissões ou diretório `logs/` não existe

**Solução**:
```bash
mkdir -p logs
chmod 755 logs
```

#### Anomalia Não Detetada

**Sintoma**: `t_hot` sobe mas `anomaly=false`

**Causa**: Z-score threshold muito alto ou buffer pequeno

**Solução**:
1. Reduzir threshold:
```python
if z > 2.5:  # 98% confidence (era 3.2)
    return True
```
2. Aumentar warmup:
```python
warmup_samples: int = 100  # Era 50
```
3. Verificar features: talvez `t_hot` sozinho não seja suficiente, adicionar `dT/dt`

---

## Apêndices

### A. Glossário Técnico

- **FSM**: Finite State Machine (Máquina de Estados Finitos)
- **PWM**: Pulse Width Modulation (Modulação por Largura de Pulso)
- **TCP**: Transmission Control Protocol (protocolo de transporte confiável)
- **1-Wire**: Protocolo de comunicação serial half-duplex da Dallas/Maxim
- **SPI**: Serial Peripheral Interface (barramento síncrono mestre-escravo)
- **MOSFET**: Metal-Oxide-Semiconductor Field-Effect Transistor
- **Flyback Diode**: Diodo de proteção contra voltagem reversa indutiva
- **Z-score**: Medida estatística de desvio em relação à média (σ)
- **Isolation Forest**: Algoritmo ML de deteção de anomalias baseado em árvores de decisão
- **Buck Converter**: Conversor DC-DC step-down (reduz tensão)

### B. Referências

1. **Datasheets**:
   - [ESP32 Technical Reference](https://www.espressif.com/sites/default/files/documentation/esp32_technical_reference_manual_en.pdf)
   - [RP2040 Datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)
   - [W5500 Datasheet](https://docs.wiznet.io/Product/iEthernet/W5500/datasheet)
   - [DS18B20 Datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/DS18B20.pdf)
   - [IRLZ44N Datasheet](https://www.infineon.com/dgdl/irlz44npbf.pdf)

2. **Bibliotecas**:
   - [Arduino Ethernet Library](https://www.arduino.cc/reference/en/libraries/ethernet/)
   - [DallasTemperature](https://github.com/milesburton/Arduino-Temperature-Control-Library)
   - [ArduinoJson](https://arduinojson.org/)
   - [scikit-learn](https://scikit-learn.org/stable/modules/outlier_detection.html)

3. **Protocolos**:
   - [1-Wire Protocol Specification](https://www.analog.com/en/technical-articles/1wire-communication-through-software.html)
   - [JSON Specification (RFC 8259)](https://datatracker.ietf.org/doc/html/rfc8259)

### C. Histórico de Versões

| Versão | Data       | Mudanças                                      |
|--------|------------|-----------------------------------------------|
| 1.0    | 2026-02-20 | Versão inicial pré-hardware                   |

### D. Licença

Este projeto está sob licença MIT. Consulte `LICENSE` para detalhes.

---

**Fim do Relatório Técnico**

Para questões ou suporte, contactar via GitHub Issues ou email do projeto.
