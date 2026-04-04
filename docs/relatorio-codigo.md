# Relatório Técnico - Código do Sistema

**Projeto:** AI-IoT Cooperative Cooling Digital Twin
**Data:** 2026-04-02
**Arquitetura:** 2 racks reais + 6 virtuais + 1 CDU

---

## 1. Visão Geral

O código está organizado em três componentes principais:

1. **Firmware das Racks** (`rack_r00`, `rack_r07`) - ESP8266
2. **Firmware do CDU** (`cdu_esp32c6`) - ESP32-C6
3. **Servidor Central** (`server.py`) - Python 3.11+

---

## 2. Firmware das Racks (ESP8266)

### 2.1 Hardware Controlado
- **Microcontrolador:** ESP8266 (NodeMCU / ESP-12E)
- **Sensor:** DS18B20 em GPIO4 (OneWire)
- **Atuador:** Heater (resistência 100Ω @ 12V) em GPIO5 via MOSFET IRLZ44N
- **Potência nominal:** 1.44W por heater

### 2.2 Funcionalidades Principais

#### Leitura de Temperatura
- Leitura não bloqueante do DS18B20
- Rejeição de valores inválidos (NaN, Inf, -127°C)
- Fallback para modo simulado em caso de falha do sensor
- Intervalo de leitura: 750ms (resolução 12 bits)

#### Controlo do Heater
- **Time-proportioning PWM:** janela de 2000ms
- PWM recebido do servidor: 0-255
- Conversão para duty cycle percentual: `(heat_pwm / 255.0) * 100`
- Cálculo de potência média real: `heater_rated_power_w * (heat_pwm / 255.0)`

#### Telemetria Enviada
```json
{
  "type": "rack_telemetry",
  "id": "R00",
  "t_hot_real_c": 24.5,
  "t_hot_source": "sensor",
  "t_liquid_source": "unavailable",
  "sensor_ok": true,
  "heat_pwm": 180,
  "heater_on": true,
  "heater_rated_power_w": 1.44,
  "heater_avg_power_w": 1.02,
  "rssi": -45
}
```

### 2.3 Modos de Operação
1. **Measured:** Sensor OK → envia `t_hot_real` medido
2. **Sensor Fallback:** Sensor falha → a rack sinaliza `local_anomaly` e corta localmente o heater
3. **Simulated:** Desenvolvimento sem hardware

---

## 3. Firmware do CDU (ESP32-C6)

### 3.1 Hardware Controlado
- **Microcontrolador:** ESP32-C6 DevKitC-1
- **Fan A:** GPIO10 → módulo PWM 5V (GND/VCC/S)
- **Fan B:** GPIO7 → módulo PWM 5V (GND/VCC/S)
- **Peltier A:** GPIO4 → MOSFET IRLZ44N (low-side)
- **Peltier B:** GPIO5 → MOSFET IRLZ44N (low-side)
- **Peltier Fan A:** GPIO18 → MOSFET IRLZ44N (ventoinha do dissipador A)
- **Peltier Fan B:** GPIO19 → MOSFET IRLZ44N (ventoinha do dissipador B)

### 3.2 Lógica de Controlo

#### Fans Zonais (A e B)
- **PWM range no firmware:** 0-255
- **Comando do servidor:** 0-100 em regime normal, 150 em emergência
- **Threshold de ativação:** t_hot ≥ 23.0°C
- **Threshold de desativação:** t_hot < 23.0°C

#### Peltiers (A e B)
- **Controlo no firmware:** PWM 0-255
- **Patamares usados pelo servidor:** 0 / 128 / 255
- **Threshold de ativação:** t_hot ≥ 26.5°C
- **Alimentação:** XL4015 ajustado para ~2.0V

#### Ventoinhas dos Dissipadores
- Acionadas pelo firmware via GPIO18/19
- Ligam automaticamente quando o respetivo Peltier ativa

### 3.3 Telemetria Enviada
```json
{
  "type": "cdu_telemetry",
  "id": "CDU1",
  "fanA_pwm": 75,
  "fanB_pwm": 0,
  "peltierA_pwm": 128,
  "peltierB_pwm": 0,
  "peltierA_on": true,
  "peltierB_on": false,
  "t_supply_A": 28.5,
  "t_supply_B": 29.0
}
```

### 3.4 Comandos Recebidos
```json
{
  "type": "cdu_cmd",
  "fanA_pwm": 80,
  "fanB_pwm": 0,
  "peltierA_pwm": 128,
  "peltierB_pwm": 0,
  "peltierA_on": true,
  "peltierB_on": false,
  "t_supply_target": 29.5
}
```

---

## 4. Servidor Central (server.py)

### 4.1 Arquitetura

```
┌─────────────────────────────────────────┐
│         DigitalTwinCore                 │
│  - Estado real das racks (R00, R07)     │
│  - Modelo virtual (8 racks: 2x4)        │
│  - Deteção de anomalias (zscore/iforest)│
│  - Cálculo de comandos CDU              │
└─────────────────────────────────────────┘
         ↓              ↓              ↓
    ┌────────┐    ┌──────────┐   ┌───────────┐
    │ TCP    │    │ WebSocket│   │ HTTP API  │
    │ :5000  │    │ :8000    │   │ :8080     │
    │ (edge) │    │ (twin UI)│   │ (REST)    │
    └────────┘    └──────────┘   └───────────┘
```

### 4.2 Funções de Controlo Térmico

#### `_cooling_fan_cmd(hot_c, anomaly, previous_pwm)`

Controlo das fans zonais do CDU.

**Lógica atualizada (2026-04-02):**
```python
if hot_c < 23.0:
    return 0  # Desligada (ignora anomalia)
if anomaly or hot_c >= 38.0:
    return 150  # Emergência
if hot_c >= 30.0:
    return 100  # Máximo normal
# Entre 23-30°C: proporcional
return int(50 + ((hot_c - 23.0) / 7.0) * 50)  # 50-100 PWM
```

| Temperatura | PWM | Comportamento |
|-------------|-----|---------------|
| < 23.0°C | 0 | Desligada |
| 23.0°C | 50 | Mínimo |
| 26.0°C | ~71 | Proporcional |
| 28.0°C | ~86 | Proporcional |
| ≥ 30.0°C | 100 | Máximo normal |
| ≥ 38.0°C | 150 | Emergência |

#### `_cooling_peltier_cmd(hot_c, anomaly, previous_pwm)`

Controlo dos Peltiers (PWM 0-255).

**Lógica atualizada (2026-04-02):**
```python
if hot_c < 26.5:
    return 0  # Desligado
if anomaly or hot_c >= 38.0:
    return 255  # Emergência
if hot_c < 30.0:
    return 128  # Meia intensidade
return 255  # Máximo
```

| Temperatura | PWM | Comportamento |
|-------------|-----|---------------|
| < 26.5°C | 0 | Desligado |
| 26.5-29.9°C | 128 | Meia intensidade |
| ≥ 30.0°C | 255 | Máximo |
| ≥ 38.0°C | 255 | Emergência |

### 4.3 Modelo Virtual

O servidor mantém um **digital twin 2x4** com:
- 2 racks reais: **R00** (zona A) e **R07** (zona B)
- 6 racks virtuais: R01-R06

#### Física Simplificada
```python
# Rack virtual
vhot_next = vhot + (q_heat - q_cool - q_reject) * dt
vliq_next = vliq + (q_hot_to_liq - q_liq_reject) * dt

# Supply zones
supply_A = supply_A + (q_heat_A - q_fan_A - q_peltier_A) * dt
supply_B = supply_B + (q_heat_B - q_fan_B - q_peltier_B) * dt
```

### 4.4 Deteção de Anomalias

#### Modos Disponíveis
1. **zscore** (padrão): z-score > 3.2 → anomalia
2. **iforest**: Isolation Forest (requer sklearn + numpy)

#### Features Usadas
- `t_hot_real`
- `t_liquid_effective`
- `heat_pwm`

#### Lógica de Guard
```python
# Guard primário na receção da telemetria real
ai_anom, detector = detector.detect([t_hot, t_liquid, heat_pwm])
ai_guard = ai_anom and (t_hot >= 26.0)
anomaly = local_anomaly or ai_guard or (t_hot >= 80.0)

# Guard secundário durante a atualização do modelo virtual
thermal_virtual_guard = (virtual_hot >= 75.0) and (t_hot_real >= 26.0)
rack_anomaly = real.anomaly or thermal_virtual_guard
```

### 4.5 Fallback de Racks

| Estado | Condição | Comportamento |
|--------|----------|---------------|
| **real** | telemetria < 8s | Usa `t_hot_real` |
| **stale** | 8s < telemetria < 12s | Blend real → virtual |
| **simulated** | telemetria > 12s | Usa modelo virtual |

### 4.6 Estimação de t_liquid

Quando a rack não envia `t_liquid_real`, o servidor estima com curva empírica:

```python
curve = [
    (20.0, 40.0),  # t_hot=20 → t_liquid_est=40
    (23.0, 65.0),
    (27.0, 72.0),
    (28.0, 75.0),
    (29.0, 80.0),
    (31.0, 88.0)
]
```

### 4.7 Cálculo de Potências

#### Heater Real
```python
heater_real_w = heater_rated_power_w * (heat_pwm / 255.0)
```

#### Heater Equivalente
```python
scale = heater_target_w / heater_rated_power_w
heater_equivalent_w = heater_real_w * scale
```

#### Métrica Agregada de Cooling
```python
power_index = (fanA_pwm + fanB_pwm) / 510.0
peltier_factor = (peltierA_pwm + peltierB_pwm) / 255.0
cooling_metric = power_index * 2.4 + peltier_factor * 0.0095
```

Os campos `total_cooling_power_kw` e `power_index_kw` expostos pelo dashboard usam esta métrica agregada do servidor; não correspondem a uma medição elétrica direta em tempo real.

---

## 5. Frontend (twin3d/)

### 5.1 Tecnologias
- **Three.js** para renderização 3D
- **WebSocket** para updates em tempo real (ws://server:8000)
- **Vanilla JS** (sem frameworks)

### 5.2 Visualização
- Grid 2x4 com racks
- Cores indicam temperatura: azul (frio) → amarelo → vermelho (quente)
- Labels mostram:
  - ID da rack
  - Temperatura hot/liquid
  - Estado: real/stale/simulated
  - Sensor status

### 5.3 Endpoints UI
- `http://server:8080/` → Dashboard 3D
- `ws://server:8000` → Stream de estado do twin
- `http://server:8080/api/state` → Snapshot JSON
- `http://server:8080/api/history?rack=R00&points=120` → Histórico

---

## 6. Build e Deploy

### 6.1 Configuração (platformio.ini)

**Racks:**
```ini
[env:rack_r00]
platform = espressif8266
board = esp12e
build_flags =
  -DNODE_ID=\"RACK_A\"
  -DRACK_ID=\"R00\"
```

**CDU:**
```ini
[env:cdu_esp32c6]
platform = https://github.com/pioarduino/platform-espressif32.git#55.03.37
board = esp32-c6-devkitc-1
build_flags =
  -DCDU_FAN_A_PIN=10
  -DCDU_FAN_B_PIN=7
  -DCDU_PELTIER_A_PIN=4
  -DCDU_PELTIER_B_PIN=5
  -DCDU_PELTIER_FAN_A_PIN=18
  -DCDU_PELTIER_FAN_B_PIN=19
```

### 6.2 Scripts de Build

**Build completo:**
```powershell
.\tools\stage_build.ps1 build
```

**Build isolado CDU:**
```powershell
.\tools\cdu_build.ps1 build
```

**Upload:**
```powershell
.\tools\stage_build.ps1 upload -RackR00Port COM3 -RackR07Port COM5 -CduPort COM4
```

### 6.3 Arranque do Servidor

```bash
python server.py --real-racks R00,R07
```

**Argumentos principais:**
- `--host 0.0.0.0` - bind do TCP edge
- `--port 5000` - TCP edge
- `--ui-host 0.0.0.0` - bind HTTP UI
- `--ui-port 8080` - HTTP UI
- `--ws-host 0.0.0.0` - bind WS twin
- `--ws-port 8000` - WS twin
- `--edge-ws-host 0.0.0.0` - bind WS edge
- `--edge-ws-port 8765` - WS edge (para firmware)
- `--detector zscore` - modo de deteção
- `--real-racks R00,R07` - racks reais esperadas

---

## 7. Fluxo de Dados

### 7.1 Ciclo Completo (1 segundo)

```
1. Racks medem t_hot → enviam telemetria via WS
   ↓
2. Servidor recebe, atualiza DigitalTwinCore
   ↓
3. Servidor calcula comandos CDU (_cooling_fan_cmd, _cooling_peltier_cmd)
   ↓
4. Servidor envia cdu_cmd via WS
   ↓
5. CDU aplica PWM nas fans/Peltiers
   ↓
6. CDU mede t_supply → envia telemetria
   ↓
7. Servidor atualiza modelo virtual
   ↓
8. Frontend recebe twin_state via WS e renderiza
```

### 7.2 Exemplo de Rack Command

```json
{
  "type": "rack_cmd",
  "id": "R00",
  "heat_pwm": 220,
  "fan_local_pwm": 0,
  "mode": "heat-only-co-op",
  "anomaly": false
}
```

---

## 8. Estado Atual (2026-04-02)

### 8.1 Deployment Baseline
- ✅ 2 racks reais (R00, R07)
- ✅ 1 CDU (ESP32-C6)
- ✅ 2 fans zonais (A, B) com PWM 0-100 nominal e 150 em emergência
- ✅ 2 Peltiers (A, B) com PWM 0/128/255
- ✅ 2 ventoinhas dos dissipadores (acionadas automaticamente com os Peltiers)
- ✅ Servidor com twin 2x4
- ✅ Frontend 3D funcional
- ✅ Deteção de anomalias zscore

### 8.2 Correções Recentes

**Controlo de Fans:**
- Antes: ligavam com anomalia mesmo a t_hot baixo
- Agora: `if hot_c < 23.0: return 0` (ignora anomalia)

**Controlo de Peltiers:**
- PWM diferenciado: 0 (off) / 128 (meia) / 255 (máximo)
- Threshold ajustado: 26.5°C (antes 27.0°C)

### 8.3 Próximos Passos
- [ ] Calibração fina dos thresholds térmicos
- [ ] Tuning dos coeficientes do modelo virtual
- [ ] Logging de métricas para análise offline
- [ ] Dashboard de performance energético

---

## 9. Referências Técnicas

### 9.1 Bibliotecas Usadas

**Firmware:**
- Arduino Framework
- ArduinoJson 7.1.0
- WebSockets 2.7.3
- OneWire 2.3.8
- DallasTemperature 4.0.5

**Servidor:**
- Python 3.11+
- websockets
- numpy (opcional)
- scikit-learn (opcional)

### 9.2 Protocolos de Comunicação
- **TCP:** server.py:5000 (legacy edge)
- **WebSocket:** server.py:8765 (edge firmware)
- **WebSocket:** server.py:8000 (twin UI)
- **HTTP:** server.py:8080 (REST API + static files)

### 9.3 Estrutura de Pastas

```
AI-IoT/
├── src/
│   └── main.cpp           # Entry point (rack/CDU selecionado por build_flags)
├── lib/
│   ├── control/           # Controlo térmico local, PWM, time-proportioning
│   ├── network/           # WiFi, WebSocket
│   ├── protocol/          # JSON encoding/decoding
│   └── sensors/           # DS18B20, sensores virtuais
├── include/
│   └── ProjectConfig.h    # Configuração global
├── server.py              # Servidor central
├── twin3d/                # Frontend 3D
├── tools/                 # Scripts de build/upload
└── docs/                  # Documentação
```

---

**Fim do Relatório**
