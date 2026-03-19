# Relatorio de Codigo

Projeto: AI-IoT Cooperative Cooling Digital Twin
Data: 2026-03-18

## 1) Visao geral

O codigo esta organizado em tres blocos:

- firmware das racks (`rack_r00`, `rack_r07`)
- firmware do `CDU` (`cdu_esp32c6`)
- servidor central (`server.py`) com UI e digital twin

## 2) Firmware das racks

Cada rack:

- corre em `ESP8266 / ESP-12E`
- le `DS18B20` em `GPIO4`
- comanda o heater em `GPIO5`
- envia telemetria real ao servidor
- recebe `rack_cmd` com o `heat_pwm`

Pontos importantes no codigo:

- leitura `DS18B20` nao bloqueante
- rejeicao de `NaN` e `Inf`
- `remote anomaly` propagada na telemetria
- time-proportioning para o heater

## 3) Firmware do CDU

O `ESP32-C6` controla:

- `fanA` em `GPIO6`
- `fanB` em `GPIO7`
- `peltierA` em `GPIO18`
- `peltierB` em `GPIO19`

As ventoinhas dos dissipadores das Peltiers nao existem como canais logicos no firmware.
Elas ligam no mesmo ramo comutado do respetivo Peltier.

## 4) Servidor

O `server.py` faz:

- ingestao de telemetria
- digital twin `2x4`
- deteccao de anomalias
- calculo de `heater_real_w`
- calculo de `heater_equivalent_w`
- calculo de `t_virtual`
- fallback por rack: `real -> stale -> simulated`

Quando uma rack nao fornece `t_liquid_real`, o servidor estima esse valor localmente.

## 5) Frontend

O frontend em `twin3d/`:

- abre `ws://` ou `wss://` automaticamente
- mostra `T_real`, `T_virtual` e `source_status`
- representa as racks reais e sinteticas no twin

## 6) Build e scripts

Targets ativos:

- `rack_r00`
- `rack_r07`
- `cdu_esp32c6`

Scripts:

- `tools/stage_build.ps1` -> build/upload do deployment atual
- `tools/cdu_build.ps1` -> build/upload isolado do `CDU`

## 7) Estado atual

O codigo ja esta alinhado com:

- `2` racks reais
- `1` `CDU`
- `2` fans zonais
- `2` Peltiers
- `2` ventoinhas de dissipador ligadas por hardware aos ramos dos Peltiers

Nao existem perfis alternativos de deployment no baseline atual.
