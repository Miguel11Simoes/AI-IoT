# Guia de Hardware - AI-IoT Cooling System

**Data:** 2026-04-02
**Baseline:** 2 racks reais + 1 CDU

---

## 1. Bill of Materials (BOM)

### 1.1 Microcontroladores
- **2x NodeMCU ESP8266** (ESP-12E) - para racks R00 e R07
- **1x ESP32-C6 DevKitC-1** - para CDU

### 1.2 Sensores
- **2x DS18B20** (digital temperature sensor)
- **2x resistor 4.7kΩ** (pull-up para OneWire)

### 1.3 Atuadores e Potência

#### Heaters (Racks)
- **2x resistência cerâmica 100Ω** (1.44W @ 12V)
- **2x MOSFET IRLZ44N** (low-side switch para heaters)

#### Cooling (CDU)
- **2x módulo PWM fan 3-6V** (GND/VCC/S) - Fan A e Fan B
- **2x módulo Peltier TEC1-12706** (12V, ~60W)
- **2x XL4015 DC-DC buck** (12V → ~2V para Peltiers)
- **2x MOSFET IRLZ44N** (low-side switch para Peltiers)
- **2x ventoinha 12V** (dissipadores dos Peltiers)
- **2x MOSFET IRLZ44N** (low-side switch para ventoinhas dos dissipadores)

### 1.4 Resistores e Componentes Passivos
- **8x resistor 100Ω** (proteção de gates dos MOSFETs)
- **8x resistor 12kΩ** (pull-down para gates dos MOSFETs)
- Fios, breadboard/PCB, conectores

### 1.5 Alimentação
- **1x fonte 12V 5A** (PSU principal)
- **1x conversor DC-DC 12V → 5V 3A** (para alimentar fans zonais A e B)

---

## 2. Pinout e Ligações

### 2.1 Racks (R00 e R07) - ESP8266

#### DS18B20 (Sensor de Temperatura)
```
DS18B20 VDD  → ESP8266 3.3V
DS18B20 GND  → ESP8266 GND
DS18B20 DQ   → ESP8266 GPIO4
Resistor 4.7kΩ: 3.3V ↔ GPIO4 (pull-up)
```

#### Heater (Resistência 100Ω)
```
+12V PSU → Heater (+)
Heater (-) → IRLZ44N Drain
IRLZ44N Source → GND
IRLZ44N Gate → resistor 100Ω → ESP8266 GPIO5
Resistor 12kΩ: Gate ↔ GND (pull-down)
```

**Configuração em platformio.ini:**
```ini
-DONE_WIRE_PIN=4
-DHEAT_PIN=5
-DHEATER_RATED_POWER_W=1.44
```

---

### 2.2 CDU (Cooling Distribution Unit) - ESP32-C6

#### Fan A (Zona A)
```
+5V rail → Módulo Fan A VCC
GND rail → Módulo Fan A GND
ESP32-C6 GPIO10 → Módulo Fan A S (sinal PWM)
```

#### Fan B (Zona B)
```
+5V rail → Módulo Fan B VCC
GND rail → Módulo Fan B GND
ESP32-C6 GPIO7 → Módulo Fan B S (sinal PWM)
```

**IMPORTANTE:** As fans zonais devem ser alimentadas a **5V**, não a 12V!

#### Peltier A
```
XL4015-A OUT+ → Peltier A (+)
Peltier A (-) → MOSFET-A Drain
MOSFET-A Source → GND
MOSFET-A Gate → resistor 100Ω → ESP32-C6 GPIO4
Resistor 12kΩ: Gate ↔ GND (pull-down)
```

#### Peltier B
```
XL4015-B OUT+ → Peltier B (+)
Peltier B (-) → MOSFET-B Drain
MOSFET-B Source → GND
MOSFET-B Gate → resistor 100Ω → ESP32-C6 GPIO5
Resistor 12kΩ: Gate ↔ GND (pull-down)
```

#### Ventoinha Dissipador A
```
+12V PSU → Ventoinha A (+)
Ventoinha A (-) → MOSFET-Fan-A Drain
MOSFET-Fan-A Source → GND
MOSFET-Fan-A Gate → resistor 100Ω → ESP32-C6 GPIO18
Resistor 12kΩ: Gate ↔ GND (pull-down)
```

#### Ventoinha Dissipador B
```
+12V PSU → Ventoinha B (+)
Ventoinha B (-) → MOSFET-Fan-B Drain
MOSFET-Fan-B Source → GND
MOSFET-Fan-B Gate → resistor 100Ω → ESP32-C6 GPIO19
Resistor 12kΩ: Gate ↔ GND (pull-down)
```

**Configuração em platformio.ini:**
```ini
-DCDU_FAN_A_PIN=10
-DCDU_FAN_B_PIN=7
-DCDU_PELTIER_A_PIN=4
-DCDU_PELTIER_B_PIN=5
-DCDU_PELTIER_FAN_A_PIN=18
-DCDU_PELTIER_FAN_B_PIN=19
-DCDU_PELTIER_ACTIVE_HIGH=1
```

---

## 3. Diagrama de Potência

### 3.1 PSU Principal (12V 5A)

```
+12V ──┬─→ Heater R00 (+)
       ├─→ Heater R07 (+)
       ├─→ XL4015-A IN+
       ├─→ XL4015-B IN+
       ├─→ Ventoinha Dissipador A (+)
       ├─→ Ventoinha Dissipador B (+)
       └─→ Conversor DC-DC 12V→5V IN+

GND ───┴─→ Todos os GND (comum)
```

### 3.2 Rail 5V (para Fans Zonais)

```
Conversor 12V→5V OUT+ ──┬─→ Fan A VCC
                        └─→ Fan B VCC
```

### 3.3 XL4015 (Buck Converters para Peltiers)

**ATENÇÃO:** Ajustar tensão de saída para **~2.0V** antes de conectar os Peltiers!

```
XL4015-A: 12V IN → ~2.0V OUT → Peltier A
XL4015-B: 12V IN → ~2.0V OUT → Peltier B
```

**Ajuste:**
1. Desligar Peltier
2. Ligar PSU 12V no XL4015
3. Medir tensão de saída com multímetro
4. Ajustar potenciómetro do XL4015 até ler ~2.0V
5. Só depois conectar o Peltier

---

## 4. Esquema de Controlo Low-Side

Todos os atuadores usam **MOSFET low-side switching**:

```
+V_power (12V ou 5V)
   ↓
[Carga: heater/fan/Peltier]
   ↓
Drain ← [MOSFET IRLZ44N] → Source
           ↑ Gate           ↓
         100Ω              GND
           ↑
        ESP GPIO
           ↓
         12kΩ → GND (pull-down)
```

**Lógica:**
- GPIO HIGH → MOSFET ON → carga ativa
- GPIO LOW → MOSFET OFF → carga desligada

---

## 5. Checklist de Montagem

### 5.1 Antes de Ligar

- [ ] Todos os GND estão conectados num ponto comum
- [ ] Pull-ups 4.7kΩ instalados nos DS18B20
- [ ] Pull-downs 12kΩ instalados em todos os gates dos MOSFETs
- [ ] Resistores de proteção 100Ω em série com todos os gates
- [ ] XL4015 ajustados para ~2.0V (verificar com multímetro)
- [ ] Fans zonais A e B alimentadas a **5V**, não 12V
- [ ] Peltiers desconectados durante ajuste dos XL4015

### 5.2 Teste Inicial (sem carga)

1. Ligar PSU 12V
2. Verificar tensão no rail 5V: ~5.0V
3. Verificar tensões XL4015-A e XL4015-B: ~2.0V
4. Desligar PSU

### 5.3 Teste com Carga

1. Conectar todos os atuadores
2. Carregar firmware nas racks: `rack_r00`, `rack_r07`
3. Carregar firmware no CDU: `cdu_esp32c6`
4. Arrancar servidor: `python server.py --real-racks R00,R07`
5. Ligar PSU 12V
6. Verificar no monitor serial que as racks conectam ao servidor
7. Verificar no dashboard 3D que as temperaturas são lidas
8. Testar comando manual das fans (via API REST se necessário)

---

## 6. Troubleshooting

### 6.1 DS18B20 Não Lê

- **Sintoma:** `t_hot_real = -127.0` ou `sensor_ok = false`
- **Causas:**
  - Pull-up 4.7kΩ em falta
  - Sensor mal conectado
  - GPIO errado (deve ser GPIO4)
- **Solução:** Verificar ligações e pull-up

### 6.2 Heater Não Aquece

- **Sintoma:** `heat_pwm > 0` mas resistência fria
- **Causas:**
  - MOSFET não comuta (gate desconectado)
  - GND não comum
  - Resistência de proteção 100Ω em falta
- **Solução:** Medir tensão gate-source do MOSFET com multímetro

### 6.3 Fans Não Ligam

- **Sintoma:** `fanA_pwm > 0` mas ventoinha parada
- **Causas:**
  - Alimentação errada (verificar se é 5V, não 12V)
  - GPIO errado (Fan A = GPIO10, Fan B = GPIO7)
  - Módulo PWM danificado
- **Solução:** Medir tensão VCC do módulo; testar com ventoinha diferente

### 6.4 Peltier Sobreaquece

- **Sintoma:** Peltier queima ou aquece excessivamente
- **Causas:**
  - XL4015 ajustado para tensão muito alta (>3V)
  - Dissipador sem ventoinha funcional
  - Corrente excessiva
- **Solução:**
  - Desligar imediatamente
  - Reajustar XL4015 para ~2.0V
  - Verificar ventoinhas dos dissipadores (GPIO18/19)

### 6.5 ESP32-C6 Não Arranca

- **Sintoma:** LED de alimentação OK mas sem output serial
- **Causas:**
  - Firmware build com plataforma errada
  - USB-Serial não configurado
- **Solução:**
  - Rebuild com `platformio run -e cdu_esp32c6`
  - Verificar settings de boot no ESP32-C6

---

## 7. Manutenção Preventiva

### 7.1 Semanal
- Verificar temperaturas típicas no dashboard
- Confirmar que fans ligam quando t_hot > 23°C
- Verificar RSSI das racks (deve estar > -70 dBm)

### 7.2 Mensal
- Limpar dissipadores dos Peltiers (pó acumulado)
- Verificar aperto das ligações elétricas
- Verificar se XL4015 mantêm tensão estável (~2.0V)

### 7.3 Trimestral
- Substituir pasta térmica nos Peltiers se necessário
- Testar MOSFETs com carga máxima (15 min contínuos)
- Recalibrar thresholds térmicos no servidor se comportamento mudar

---

## 8. Especificações Elétricas

| Componente | Tensão Típica | Corrente Típica | Potência |
|------------|---------------|-----------------|----------|
| Heater 100Ω @ 12V | 12V | 120 mA | 1.44W |
| Peltier TEC1-12706 @ 2V | 2V | ~300 mA | ~0.6W |
| Fan Zonal (módulo PWM) | 5V | 100-300 mA | 0.5-1.5W |
| Ventoinha Dissipador | 12V | 100-200 mA | 1.2-2.4W |
| ESP8266 (NodeMCU) | 3.3V | 80-170 mA | 0.3-0.6W |
| ESP32-C6 DevKitC-1 | 3.3V | 100-250 mA | 0.4-0.8W |

**Consumo Total Estimado (worst case):**
- Heaters: 2 × 1.44W = **2.88W**
- Peltiers: 2 × 0.6W = **1.2W**
- Fans Zonais: 2 × 1.5W = **3W**
- Ventoinhas Dissipadores: 2 × 2.4W = **4.8W**
- MCUs: **1.4W**
- **Total: ~13.3W** (@ 12V PSU → ~1.1A)

**PSU Recomendada:** 12V 5A (60W) para margem de segurança.

---

## 9. Fotografias/Diagramas (Referência)

_[Esta secção pode ser preenchida com fotografias reais da montagem]_

### 9.1 Layout Sugerido

```
┌─────────────┐   ┌─────────────┐
│   Rack R00  │   │   Rack R07  │
│  (ESP8266)  │   │  (ESP8266)  │
│             │   │             │
│  DS18B20    │   │  DS18B20    │
│  Heater     │   │  Heater     │
└─────────────┘   └─────────────┘
        ↓ WiFi          ↓ WiFi
    ┌──────────────────────┐
    │  Server (Python)     │
    │  Digital Twin + AI   │
    └──────────────────────┘
        ↓ WiFi
┌─────────────────────────────┐
│        CDU (ESP32-C6)       │
│                             │
│  Fan A    Fan B             │
│  Peltier A  Peltier B       │
│  Diss Fan A  Diss Fan B     │
└─────────────────────────────┘
```

---

## 10. Referências de Datasheets

- **DS18B20:** https://datasheets.maximintegrated.com/en/ds/DS18B20.pdf
- **IRLZ44N:** https://www.infineon.com/dgdl/irlz44n.pdf
- **TEC1-12706:** [Generic Peltier datasheet]
- **XL4015:** [Generic DC-DC buck datasheet]
- **ESP8266:** https://www.espressif.com/sites/default/files/documentation/0a-esp8266ex_datasheet_en.pdf
- **ESP32-C6:** https://www.espressif.com/sites/default/files/documentation/esp32-c6_datasheet_en.pdf

---

**Fim do Guia de Hardware**
