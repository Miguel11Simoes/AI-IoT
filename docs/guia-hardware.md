# Guia de Hardware e Ligacoes (AI-IoT)

Estado alinhado com o projeto submetido no RMIC:

- Rack R00 e R07: medicao DS18B20 + carga termica por heater 12V/20W.
- CDU (ESP32-C6): controlo de cooling por fanA/fanB (zonas A/B), Peltier A/B e
  ventoinhas de dissipador quente dos Peltiers.
- Servidor: coordena setpoints entre racks e CDU via WebSocket.

## 1) Pinout oficial atual

### Racks (ESP8266 ESP-12E)

- `GPIO4` -> DS18B20 `DQ` (1-Wire)
- `3V3`  -> DS18B20 `VDD`
- `GND`  -> DS18B20 `GND`
- `4.7k` entre `3V3` e `DQ`
- `GPIO5` -> `IN/SIG` do modulo IRF520 (heater)
- `GND ESP8266` -> `GND` do IRF520

Notas:
- `FAN_PIN` e `PUMP_PIN` foram removidos da configuracao ativa dos racks.
- O rack nao controla cooling local fisico no desenho alvo.

### CDU (ESP32-C6) — stage1 (1 rack, 1 Peltier)

- `GPIO6`  -> PWM do driver fan zona A (DFR0332 ou equivalente)
- `GPIO18` -> sinal de enable do modulo Peltier A (active-high)
- `GPIO20` -> sinal de enable da ventoinha de dissipador quente do Peltier A (active-high)
- `GND ESP32-C6` -> `GND` comum dos drivers

### CDU (ESP32-C6) — full (2 racks, 2 Peltiers)

- `GPIO6`  -> PWM driver fan zona A
- `GPIO7`  -> PWM driver fan zona B
- `GPIO18` -> enable Peltier A
- `GPIO19` -> enable Peltier B
- `GPIO20` -> enable ventoinha dissipador quente Peltier A
- `GPIO21` -> enable ventoinha dissipador quente Peltier B
- `GND ESP32-C6` -> `GND` comum

## 2) Esboco de ligacoes

```text
                     Wi-Fi WS (porta 8765)

 +----------------------+   +----------------------+   +----------------------+
 | Rack R00 (ESP8266)   |   | Rack R07 (ESP8266)   |   | CDU1 (ESP32-C6)      |
 | DS18B20 + Heater     |   | DS18B20 + Heater     |   | fanA/B + peltierA/B  |
 +----------+-----------+   +----------+-----------+   +----------+-----------+
            \                          |                          /
             \                         |                         /
              +------------------------+------------------------+
                                       |
                               +-------+-------+
                               |   server.py   |
                               +---------------+
```

## 3) Potencia e GND comum

```text
+12V PSU -> heater R00 (+)
+12V PSU -> heater R07 (+)
+12V PSU -> alimentacao dos drivers de fan e Peltier do CDU

heater (-) -> IRF520 DRAIN/OUT
IRF520 SOURCE/GND -> GND PSU
ESP8266 GPIO5 -> IRF520 IN/SIG
ESP8266 GND -> IRF520 GND

Peltier A (+) -> saida do driver Peltier A
Peltier A (-) -> GND comum
Peltier fan (+) -> fonte propria ou saida de driver digital
ESP32-C6 GPIO20 -> enable ventoinha dissipador Peltier A

Todos os GNDs ligados em comum:
PSU GND + ESP8266 R00/R07 GND + ESP32-C6 GND + drivers
```

## 4) Checklist rapido

- Confirmar `ONE_WIRE_PIN=4` e `HEAT_PIN=5` nos racks.
- Confirmar `CDU_FAN_A_PIN=6` (stage1) ou `CDU_FAN_A_PIN=6`, `CDU_FAN_B_PIN=7` (full).
- Confirmar `CDU_PELTIER_A_PIN=18`, `CDU_PELTIER_FAN_A_PIN=20` (stage1).
- Confirmar resistor de pull-up `4.7k` no DS18B20.
- Confirmar topologia low-side correta do IRF520 para o heater.
- Confirmar driver de corrente adequado para o Peltier (carga ~6A).
- Confirmar GND comum entre todos os MCUs e modulos.

## 5) Nota de controlo

No rack, o heater e controlado por time-proportioning (`HEAT_WINDOW_MS=2000`),
comutando ON/OFF digital para proteger o IRF520.

No CDU, a ventoinha de dissipador quente do Peltier (`peltierFanA/B`) liga e desliga
automaticamente em sincronia com o modulo Peltier respetivo, sem necessitar de comando
separado do servidor.
