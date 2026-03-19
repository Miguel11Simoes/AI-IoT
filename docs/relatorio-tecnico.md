# Relatorio Tecnico

Projeto: AI-IoT Digital Twin para Cooling Cooperativo

## Arquitetura

- `R00` e `R07`: `ESP8266 / ESP-12E` com `DS18B20 + heater`
- `CDU`: `ESP32-C6` com `fanA`, `fanB`, `peltierA`, `peltierB`
- `server.py`: digital twin, AI, comandos, fallback e UI/API

## Racks

Cada rack:

- mede `t_hot_real` com `DS18B20`
- envia apenas telemetria real
- usa `GPIO5` para o driver do heater
- faz seguranca local por temperatura e anomalia
- continua a funcionar mesmo sem o servidor durante o `TTL` remoto

Se existir uma segunda sonda, a rack pode enviar tambem `t_liquid_real`.
Se nao existir, o servidor estima `t_liquid`.

## CDU

O `ESP32-C6` controla:

- `fanA` em `GPIO6`
- `fanB` em `GPIO7`
- `peltierA` em `GPIO18`
- `peltierB` em `GPIO19`

As ventoinhas dos dissipadores das Peltiers nao usam GPIO proprio.
Cada uma liga no mesmo ramo comutado do respetivo Peltier.

## Servidor

O servidor:

- aceita telemetria real de `R00` e `R07`
- estima o resto do twin `2x4`
- calcula `heater_real_w`, `heater_equivalent_w` e `t_virtual`
- gere `real`, `stale` e `simulated`
- envia `rack_cmd` e `cdu_cmd`
- faz deteccao de anomalia com threshold base `80 C`

## Pinagem consolidada

Racks:

- `ONE_WIRE_PIN=4`
- `HEAT_PIN=5`

CDU:

- `CDU_FAN_A_PIN=6`
- `CDU_FAN_B_PIN=7`
- `CDU_PELTIER_A_PIN=18`
- `CDU_PELTIER_B_PIN=19`

## Seguranca eletrica

- `GND` comum em toda a bancada
- `DS18B20` com pull-up `4.7k`
- heater em low-side no driver da rack
- sem cargas `12V` diretamente nos GPIOs
- `XL4015` ajustados para `~2.0V` antes de ligar os Peltiers

## Estado

- baseline atual: `2 racks + 2 fans + 2 Peltiers`
- sem perfis alternativos de deployment no baseline atual
- documentacao alinhada com o hardware atual
