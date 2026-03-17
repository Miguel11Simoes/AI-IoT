# Relatorio Hardware-Ready

Projeto: AI-IoT Hierarchical Cooperative Cooling Twin
Data: 2026-03-17

## 1) Resumo executivo

O repositorio foi alinhado com o projeto submetido no RMIC:

- Racks fisicos (`R00`, `R07`) fazem medicao termica e atuacao de heater.
- CDU (`ESP32-C6`) faz o controlo de cooling por fans zonais, modulos Peltier e ventoinhas
  de dissipador quente dos Peltiers.
- Servidor coordena setpoints e mantem twin 2x4 com 6 racks sinteticos.

## 2) Incoerencia identificada (corrigida)

Estado anterior do codigo:

- racks tinham atuacao local de cooling
- servidor gerava `rack_cmd` com campos legados adicionais
- anomaly threshold hardcoded a 85 deg C no servidor, enquanto firmware usava 80 deg C
- DS18B20 com leitura bloqueante (~187ms)
- CDU sem controlo de Peltier nem ventoinhas de dissipador
- `t_supply_target` aceite sem validar presenca nem finitude

Incoerencia com o formulario RMIC:

- BOM e descricao do projeto definem rack com `DS18B20 + heater`
- cooling fisico representado por fans + Peltier do CDU
- rack so aquece e mede; nao arrefece localmente

## 3) Correcao aplicada

### Firmware de rack

- removida atuacao fisica local de cooling no `ControlManager`
- mantido controlo de heater com janela temporal (`HEAT_WINDOW_MS`)
- telemetria reduzida ao estado termico real e ao heater
- DS18B20 passou para conversao assincrona (nao bloqueante)
- validacao de NaN/Inf em `validTemperature()`
- remote anomaly agora propaga `localAnomaly=true` na telemetria

### Firmware CDU

- adicionados canais Peltier A/B (`CDU_PELTIER_A_PIN`, `CDU_PELTIER_B_PIN`)
- adicionadas ventoinhas de dissipador quente (`CDU_PELTIER_FAN_A_PIN`, `CDU_PELTIER_FAN_B_PIN`)
- ventoinhas de Peltier seguem o estado on/off do modulo respetivo
- `t_supply_target` so atualizado quando campo presente no comando e valor finito

### Configuracao

- removidos `FAN_PIN` e `PUMP_PIN` ativos dos ambientes `rack_r00` e `rack_r07`
- `default_envs = rack_r00` (evita build acidental do CDU sem packages dir isolado)
- pinagem final definida em `platformio.ini` para `cdu_esp32c6` (stage1) e `cdu_esp32c6_full`

### Servidor

- anomaly threshold alinhado: `--anomaly-temp-c` default 80 deg C (igual ao firmware)
- validacao de NaN/Inf em telemetria recebida (`finite_float`)
- stale blend coerente: fan/heat/heater_on/anomaly transicionam junto com temperaturas
- cleanup com `AsyncExitStack` garante encerramento correto dos dois servicos WebSocket

### Frontend

- `ws://` vs `wss://` detectado automaticamente a partir do protocolo da pagina
- null guard em `payload.racks.forEach` evita crash em mensagens malformadas

## 4) Arquitetura resultante

- Rack R00/R07 (ESP8266 ESP-12E):
  - sensor: DS18B20 (GPIO4)
  - atuador: heater 12V via IRF520 (GPIO5)
- CDU stage1 (ESP32-C6):
  - fanA: GPIO6
  - peltierA: GPIO18
  - peltierFanA: GPIO20
  - canais B desativados (255)
- CDU full (ESP32-C6):
  - fanA: GPIO6, fanB: GPIO7
  - peltierA: GPIO18, peltierB: GPIO19
  - peltierFanA: GPIO20, peltierFanB: GPIO21
- Servidor:
  - AI + twin + coordenacao de setpoints

## 5) Impacto

Beneficios:

- coerencia entre codigo e proposta academica
- simplificacao da cablagem dos racks
- separacao clara de responsabilidades (rack aquece/mede, CDU arrefece)
- robustez aumentada (sem bloqueio de loop, sem NaN no pipeline, thresholds alinhados)

Compatibilidade:

- protocolo JSON e frontend mantidos funcionais
- sem campos de bomba no protocolo das racks

## 6) Estado

- arquitetura: alinhada com RMIC
- firmware: compilado e verificado para rack_r00, rack_r07, cdu_esp32c6, cdu_esp32c6_full
- servidor: smoke test end-to-end via TCP passado
- documentacao `docs/`: atualizada para o baseline tecnico atual
- validacao pendente: upload real, ligacao Wi-Fi, hardware fisico na bancada
