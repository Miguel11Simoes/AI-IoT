# Guia de Hardware e Ligacoes (AI-IoT)

Estado alinhado com o projeto submetido no RMIC:

- Rack R00 e R07: medicao DS18B20 + carga termica por heater 12V/20W.
- CDU (ESP32-C6): controlo de cooling por fanA/fanB (zonas A/B).
- Servidor: coordena setpoints entre racks e CDU via WebSocket.

## 1) Pinout oficial atual

### Racks (ESP32-DEVKITC-V4)

- `GPIO4` -> DS18B20 `DQ` (1-Wire)
- `3V3` -> DS18B20 `VDD`
- `GND` -> DS18B20 `GND`
- `4.7k` entre `3V3` e `DQ`
- `GPIO18` -> `IN/SIG` do modulo IRF520 (heater)
- `GND ESP32` -> `GND` do IRF520

Notas:
- `FAN_PIN` e `PUMP_PIN` foram removidos da configuracao ativa dos racks.
- O rack nao controla fan/pump fisico no desenho alvo.

### CDU (ESP32-C6)

- `GPIO4` -> entrada `IN/PWM` do driver fan zona A (DFR0332)
- `GPIO5` -> entrada `IN/PWM` do driver fan zona B (DFR0332)
- `GND ESP32-C6` -> `GND` comum dos drivers

## 2) Esboco de ligacoes

```text
                     Wi-Fi WS (porta 8765)

 +------------------+     +------------------+     +------------------+
 | Rack R00 (ESP32) |     | Rack R07 (ESP32) |     | CDU1 (ESP32-C6)  |
 | DS18B20 + Heater |     | DS18B20 + Heater |     | fanA + fanB      |
 +--------+---------+     +--------+---------+     +--------+---------+
          \                        |                       /
           \                       |                      /
            +----------------------+---------------------+
                                   |
                           +-------+-------+
                           |   server.py   |
                           +---------------+
```

## 3) Potencia e GND comum

```text
+12V PSU -> heater R00 (+)
+12V PSU -> heater R07 (+)
+12V PSU -> alimentacao dos drivers de fan do CDU

heater (-) -> IRF520 DRAIN/OUT
IRF520 SOURCE/GND -> GND PSU
ESP32 GPIO18 -> IRF520 IN/SIG
ESP32 GND -> IRF520 GND

Todos os GNDs ligados em comum:
PSU GND + ESP32 R00/R07 GND + ESP32-C6 GND + drivers
```

## 4) Checklist rapido

- Confirmar `ONE_WIRE_PIN=4` e `HEAT_PIN=18` nos racks.
- Confirmar `CDU_FAN_A_PIN=4` e `CDU_FAN_B_PIN=5` no CDU.
- Confirmar resistor de pull-up `4.7k` no DS18B20.
- Confirmar topologia low-side correta do IRF520 para o heater.
- Confirmar GND comum entre todos os MCUs e modulos.

## 5) Nota de controlo

No rack, o heater e controlado por time-proportioning (`HEAT_WINDOW_MS=2000`),
comutando ON/OFF digital para proteger o IRF520.
