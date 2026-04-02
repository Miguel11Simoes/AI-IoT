# AI-IoT - Hierarchical Cooperative Cooling Digital Twin

Sistema de arrefecimento cooperativo com controlo distribuído, digital twin 3D e deteção de anomalias por IA.

**Data:** 2026-04-02
**Baseline:** 2 racks reais + 1 CDU + servidor + frontend 3D

---

## Visão Geral

Sistema IoT que coordena o cooling de um cluster de racks através de:
- **Racks Reais:** R00 e R07 (ESP8266) com sensores DS18B20 e heaters
- **CDU (Cooling Distribution Unit):** ESP32-C6 com 2 fans zonais + 2 Peltiers
- **Servidor Central:** Python (`server.py`) com digital twin 2×4 e AI
- **Frontend 3D:** Dashboard interativo em tempo real (Three.js)

---

## Arquitetura

```
┌─────────────┐   ┌─────────────┐
│   Rack R00  │   │   Rack R07  │
│  (ESP8266)  │   │  (ESP8266)  │
│  - DS18B20  │   │  - DS18B20  │
│  - Heater   │   │  - Heater   │
└─────────────┘   └─────────────┘
      ↓ WiFi WS          ↓ WiFi WS
    ┌────────────────────────────┐
    │  Server (Python)            │
    │  - Digital Twin 2×4         │
    │  - AI Anomaly Detection     │
    │  - Thermal Control Logic    │
    └────────────────────────────┘
      ↓ WiFi WS         ↑ WS 8000
┌─────────────────────┐   ┌──────────────┐
│  CDU (ESP32-C6)     │   │  Frontend    │
│  - Fan A / Fan B    │   │  (3D Twin)   │
│  - Peltier A/B      │   │  - Three.js  │
│  - Diss Fans A/B    │   └──────────────┘
└─────────────────────┘
```

---

## Hardware (BOM Resumido)

| Componente | Quantidade | Função |
|------------|------------|--------|
| NodeMCU ESP8266 | 2 | Racks R00, R07 |
| ESP32-C6 DevKitC-1 | 1 | CDU |
| DS18B20 | 2 | Sensores temperatura |
| Resistência 100Ω | 2 | Heaters (1.44W @ 12V) |
| Módulo PWM Fan 5V | 2 | Fans zonais A e B |
| Peltier TEC1-12706 | 2 | Cooling termoelétrico |
| XL4015 Buck | 2 | 12V → 2V para Peltiers |
| IRLZ44N MOSFET | 8 | Switches low-side |
| Ventoinha 12V | 2 | Dissipadores Peltiers |
| PSU 12V 5A | 1 | Alimentação principal |

**Detalhes:** Ver [`docs/guia-hardware.md`](docs/guia-hardware.md)

---

## Quick Start

### 1. Configurar WiFi e Servidor

Editar `platformio.ini`:
```ini
-DWIFI_SSID=\"SuaRedeWiFi\"
-DWIFI_PASSWORD=\"SuaSenha\"
-DSERVER_HOST=\"192.168.1.100\"
```

### 2. Build e Upload do Firmware

**Racks:**
```bash
platformio run -e rack_r00 -t upload
platformio run -e rack_r07 -t upload
```

**CDU:**
```bash
platformio run -e cdu_esp32c6 -t upload
```

Ou usar o script automatizado:
```powershell
.\tools\stage_build.ps1 upload -RackR00Port COM3 -RackR07Port COM5 -CduPort COM4
```

### 3. Arrancar o Servidor

```bash
python server.py --real-racks R00,R07
```

Argumentos opcionais:
- `--host 0.0.0.0` - bind address
- `--port 5000` - TCP edge (racks/CDU)
- `--ui-port 8080` - HTTP UI/API
- `--ws-port 8000` - WebSocket twin (frontend)
- `--edge-ws-port 8765` - WebSocket edge (firmware)
- `--detector zscore` - modo deteção anomalias (zscore|iforest)

### 4. Abrir Dashboard

```
http://localhost:8080
```

---

## Endpoints do Servidor

| Serviço | Porto | Protocolo | Função |
|---------|-------|-----------|--------|
| TCP Edge | 5000 | TCP | Telemetria legacy |
| WS Edge | 8765 | WebSocket | Telemetria racks/CDU |
| WS Twin | 8000 | WebSocket | Stream frontend |
| HTTP API | 8080 | HTTP | Dashboard + REST API |

### API REST

| Endpoint | Descrição |
|----------|-----------|
| `GET /api/health` | Health check |
| `GET /api/state` | Snapshot completo do sistema |
| `GET /api/twin?racks=8` | Estado do digital twin |
| `GET /api/history?rack=R00&points=120` | Histórico rack |
| `GET /api/config` | Configuração do servidor |

---

## Controlo Térmico

### Fans Zonais (CDU)

Controladas por temperatura `t_hot` das racks da zona:

| Temperatura | PWM | Comportamento |
|-------------|-----|---------------|
| < 23.0°C | 0 | Desligada |
| 23.0°C | 50 | Mínimo |
| 26.0°C | ~71 | Proporcional |
| ≥ 30.0°C | 100 | Máximo normal |
| ≥ 38.0°C | 150 | Emergência |

**Zonas:**
- **Zona A:** R00 → Fan A (GPIO10)
- **Zona B:** R07 → Fan B (GPIO7)

### Peltiers (CDU)

| Temperatura | PWM | Comportamento |
|-------------|-----|---------------|
| < 26.5°C | 0 | Desligado |
| 26.5-29.9°C | 128 | Meia intensidade |
| ≥ 30.0°C | 255 | Máximo |
| ≥ 38.0°C | 255 | Emergência |

---

## Estrutura do Projeto

```
AI-IoT/
├── src/
│   └── main.cpp              # Entry point (rack/CDU via build flags)
├── lib/
│   ├── control/              # PID, PWM, time-proportioning
│   ├── network/              # WiFi, WebSocket client
│   ├── protocol/             # JSON telemetry encoding
│   └── sensors/              # DS18B20, virtual sensors
├── include/
│   └── ProjectConfig.h       # Configuração global
├── platformio.ini            # Build configs (rack_r00, rack_r07, cdu_esp32c6)
├── server.py                 # Servidor central (twin + AI)
├── twin3d/
│   ├── index.html            # Frontend 3D
│   ├── main.js               # Three.js logic
│   └── style.css
├── tools/
│   ├── stage_build.ps1       # Script build/upload completo
│   └── cdu_build.ps1         # Script build CDU isolado
└── docs/
    ├── relatorio-codigo.md   # Documentação completa do código
    └── guia-hardware.md      # Guia de montagem e pinout
```

---

## Firmware - Pinout

### Racks (ESP8266)
- **GPIO4:** DS18B20 DQ (OneWire)
- **GPIO5:** Heater (MOSFET gate)

### CDU (ESP32-C6)
- **GPIO10:** Fan A (módulo PWM 5V)
- **GPIO7:** Fan B (módulo PWM 5V)
- **GPIO4:** Peltier A (MOSFET gate)
- **GPIO5:** Peltier B (MOSFET gate)
- **GPIO18:** Ventoinha Dissipador A (MOSFET gate)
- **GPIO19:** Ventoinha Dissipador B (MOSFET gate)

---

## Digital Twin

O servidor mantém um **twin 2×4** (8 racks):
- **2 racks reais:** R00, R07 (telemetria física)
- **6 racks virtuais:** R01-R06 (modelo térmico)

### Estados de Racks

| Estado | Condição | Fonte de Dados |
|--------|----------|----------------|
| **real** | telemetria < 8s | Sensor físico |
| **stale** | 8s < telemetria < 12s | Blend real → virtual |
| **simulated** | telemetria > 12s | Modelo virtual |

### Deteção de Anomalias

**Modos disponíveis:**
- `zscore` (padrão): z-score > 3.2 em features [t_hot, t_liquid, heat_pwm]
- `iforest`: Isolation Forest (requer `numpy` + `scikit-learn`)

**Ação em anomalia:**
- Se `t_hot >= 26°C` → fan = 150 PWM (emergência)
- Se `t_hot < 26°C` → anomalia ignorada (falso positivo)

---

## Desenvolvimento

### Dependências Python

```bash
pip install websockets
pip install numpy scikit-learn  # opcional, para iforest
```

### Build Completo

```powershell
.\tools\stage_build.ps1 build
```

### Upload Seletivo

```bash
platformio run -e rack_r00 -t upload
platformio run -e cdu_esp32c6 -t upload --upload-port COM4
```

### Monitor Serial

```bash
platformio device monitor -e rack_r00
```

---

## Troubleshooting

### Racks não conectam ao servidor
- Verificar SSID/password em `platformio.ini`
- Verificar `SERVER_HOST` correto (IP do PC onde corre `server.py`)
- Confirmar que servidor está a correr: `python server.py`

### DS18B20 retorna -127°C
- Pull-up 4.7kΩ em falta (entre VDD e DQ)
- Sensor mal conectado
- GPIO errado (deve ser GPIO4)

### Fans não ligam
- Verificar alimentação: **5V** (não 12V!)
- Confirmar GPIOs: Fan A = GPIO10, Fan B = GPIO7
- Verificar temperatura: fans só ligam se `t_hot >= 23°C`

### Peltier sobreaquece
- XL4015 ajustado para tensão muito alta (deve ser ~2.0V)
- Verificar ventoinhas dos dissipadores (GPIO18/19)
- Desligar imediatamente se demasiado quente

---

## Documentação Completa

- **[Relatório de Código](docs/relatorio-codigo.md)** - Arquitetura software detalhada
- **[Guia de Hardware](docs/guia-hardware.md)** - Pinout, BOM, montagem e troubleshooting

---

## Estado Atual (2026-04-02)

### ✅ Implementado
- [x] 2 racks reais (R00, R07) com telemetria funcional
- [x] CDU com 2 fans zonais + 2 Peltiers + 2 ventoinhas dissipadores
- [x] Servidor com digital twin 2×4 e controlo térmico
- [x] Frontend 3D com visualização em tempo real
- [x] Deteção de anomalias (zscore/iforest)
- [x] Estimação de `t_liquid` quando sensor indisponível
- [x] Controlo de fans: PWM 0-100 (threshold 23°C)
- [x] Controlo de Peltiers: PWM 0/128/255 (threshold 26.5°C)
- [x] Fallback automático: real → stale → simulated

### 🔧 Próximos Passos
- [ ] Calibração fina dos thresholds térmicos em ambiente real
- [ ] Tuning dos coeficientes do modelo virtual
- [ ] Logging de métricas para análise offline (CSV/InfluxDB)
- [ ] Dashboard de eficiência energética

---

## Licença

[Especificar licença se aplicável]

---

## Contactos

**Projeto:** AI-IoT Cooperative Cooling Twin
**Instituição:** [Universidade/Empresa]
**Data:** 2026-04-02

---

**Desenvolvido com:** PlatformIO, Arduino Framework, Python, Three.js
