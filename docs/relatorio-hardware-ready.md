# Relatorio Hardware-Ready

Projeto: AI-IoT Hierarchical Cooperative Cooling Twin
Data: 2026-03-17

## 1) Resumo executivo

O repositorio foi alinhado com o projeto submetido no RMIC:

- Racks fisicos (`R00`, `R07`) fazem medicao termica e atuacao de heater.
- CDU (`ESP32-C6`) faz o controlo de cooling por fans zonais e modulos Peltier.
- As ventoinhas dos dissipadores das Peltiers seguem o mesmo ramo eletrico dos respetivos
  canais Peltier, sem GPIO ou MOSFET dedicados no firmware.
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
- removidos canais dedicados para as ventoinhas das Peltiers no firmware
- ventoinhas de Peltier passam a seguir o mesmo ramo de potencia do modulo respetivo
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
  - canais B desativados (255)
- CDU full (ESP32-C6):
  - fanA: GPIO6, fanB: GPIO7
  - peltierA: GPIO18, peltierB: GPIO19
- Servidor:
  - AI + twin + coordenacao de setpoints

## 4.1) Pressupostos de montagem

- os `4x IRLZ44N` sao usados apenas no `CDU`
- os `heaters` das racks continuam com os drivers proprios nas racks
- as ventoinhas dos dissipadores das Peltiers ligam no mesmo canal de potencia do respetivo Peltier
- `stage1` usa apenas o canal `A`

## 4.2) Esquema unico de bancada

```text
                                  +----------------------+
                                  |      PC / Server     |
                                  |  server.py + UI/WS   |
                                  +----------+-----------+
                                             |
                                           Wi-Fi
                                             |
        -----------------------------------------------------------------
        |                               |                               |
        |                               |                               |
+-------+--------+              +-------+--------+              +-------+--------+
| Rack R00       |              | Rack R07       |              | CDU ESP32-C6   |
| NodeMCU ESP8266|              | NodeMCU ESP8266|              |                 |
| board=esp12e   |              | board=esp12e   |              | GPIO6  -> fanA  |
|                |              |                |              | GPIO7  -> fanB  |
| D2/GPIO4 <-    |              | D2/GPIO4 <-    |              | GPIO18 -> PeltA |
| DS18B20 DQ     |              | DS18B20 DQ     |              | GPIO19 -> PeltB |
| D1/GPIO5 ->    |              | D1/GPIO5 ->    |              | GND comum       |
| heater driver  |              | heater driver  |              +-------+--------+
+-------+--------+              +-------+--------+                      |
        |                               |                               |
        |                               |                               |
        |                               |                               |
        ------------------------ GND COMUM -------------------------------
                                      |
                               +------+------+
                               | PSU 12V 5A  |
                               +------+------+
                                      |
        +-----------------------------+------------------------------+
        |                             |                              |
        |                             |                              |
     +12V heater R00              +12V heater R07                 +12V CDU
        |                             |                              |
        |                             |                              |
  +-----v-----+                 +-----v-----+                +------v------------------+
  | Resistor  |                 | Resistor  |                | Distribuicao CDU 12V    |
  | 100 ohm   |                 | 100 ohm   |                |                          |
  +-----+-----+                 +-----+-----+                | +12V -> fanA +          |
        |                             |                      | +12V -> fanB +          |
        |                             |                      | +12V -> XL4015 A IN+    |
        |                             |                      | +12V -> XL4015 B IN+    |
        |                             |                      | +12V -> Peltier fan A + |
        |                             |                      | +12V -> Peltier fan B + |
        |                             |                      +------------+-------------+
        |                             |                                   |
        |                             |                                   |
  +-----v------+                +-----v------+                 +----------v----------+
  | Heater drv |                | Heater drv |                 | IRLZ44N #1 fanA     |
  | rack R00   |                | rack R07   |                 | gate <- GPIO6       |
  | in <- D1   |                | in <- D1   |                 | drain <- fanA -     |
  | src -> GND |                | src -> GND |                 | source -> GND       |
  +------------+                +------------+                 +---------------------+

                                                           +-------------------------+
                                                           | IRLZ44N #2 fanB         |
                                                           | gate <- GPIO7           |
                                                           | drain <- fanB -         |
                                                           | source -> GND           |
                                                           +-------------------------+

                                                           +-------------------------+
                                                           | IRLZ44N #3 Peltier A    |
                                                           | gate <- GPIO18          |
                                                           | drain <- XL4015 A IN-   |
                                                           | drain <- Peltier fan A -|
                                                           | source -> GND           |
                                                           +-----------+-------------+
                                                                       |
                                            +--------------------------+------------------+
                                            |                                             |
                                     +------v------+                               +------v------+
                                     | XL4015 A    |                               | Peltier fan A|
                                     | IN+ <- 12V  |                               | + <- 12V     |
                                     | IN- <- #3   |                               | - <- drain #3|
                                     | OUT+ -> ~2V |                               +-------------+
                                     | OUT- -> Pelt|
                                     +------+------+
                                            |
                                            |
                                     +------v------+
                                     | Peltier A   |
                                     | + <- OUT+   |
                                     | - <- OUT-   |
                                     +-------------+

                                                           +-------------------------+
                                                           | IRLZ44N #4 Peltier B    |
                                                           | gate <- GPIO19          |
                                                           | drain <- XL4015 B IN-   |
                                                           | drain <- Peltier fan B -|
                                                           | source -> GND           |
                                                           +-----------+-------------+
                                                                       |
                                            +--------------------------+------------------+
                                            |                                             |
                                     +------v------+                               +------v------+
                                     | XL4015 B    |                               | Peltier fan B|
                                     | IN+ <- 12V  |                               | + <- 12V     |
                                     | IN- <- #4   |                               | - <- drain #4|
                                     | OUT+ -> ~2V |                               +-------------+
                                     | OUT- -> Pelt|
                                     +------+------+
                                            |
                                            |
                                     +------v------+
                                     | Peltier B   |
                                     | + <- OUT+   |
                                     | - <- OUT-   |
                                     +-------------+
```

## 4.3) Ligacoes fio-a-fio

### Rack R00

- ligar `DS18B20 VDD` ao `3V3` da `NodeMCU R00`
- ligar `DS18B20 GND` ao `GND` da `NodeMCU R00`
- ligar `DS18B20 DQ` ao `D2 / GPIO4` da `NodeMCU R00`
- ligar um resistor `4.7k` entre `3V3` e `DQ`
- ligar `D1 / GPIO5` da `NodeMCU R00` ao `IN/SIG` do driver do `heater R00`
- ligar `GND` da `NodeMCU R00` ao `GND` do driver do `heater R00`
- ligar `+12V` ao primeiro terminal da resistencia `100 ohm` de `R00`
- ligar o segundo terminal da resistencia `100 ohm` ao `DRAIN/OUT` do driver do `heater R00`
- ligar `SOURCE/GND` do driver do `heater R00` ao `GND comum`

### Rack R07

- ligar `DS18B20 VDD` ao `3V3` da `NodeMCU R07`
- ligar `DS18B20 GND` ao `GND` da `NodeMCU R07`
- ligar `DS18B20 DQ` ao `D2 / GPIO4` da `NodeMCU R07`
- ligar um resistor `4.7k` entre `3V3` e `DQ`
- ligar `D1 / GPIO5` da `NodeMCU R07` ao `IN/SIG` do driver do `heater R07`
- ligar `GND` da `NodeMCU R07` ao `GND` do driver do `heater R07`
- ligar `+12V` ao primeiro terminal da resistencia `100 ohm` de `R07`
- ligar o segundo terminal da resistencia `100 ohm` ao `DRAIN/OUT` do driver do `heater R07`
- ligar `SOURCE/GND` do driver do `heater R07` ao `GND comum`

### CDU fanA com IRLZ44N #1

- ligar `GPIO6` do `ESP32-C6` ao `gate` do `IRLZ44N #1` atraves de resistor `100 a 220 ohm`
- ligar um resistor `10k` entre `gate` e `GND`
- ligar `source` do `IRLZ44N #1` ao `GND comum`
- ligar o `-` da `fanA` ao `drain` do `IRLZ44N #1`
- ligar o `+` da `fanA` ao `+12V`

### CDU fanB com IRLZ44N #2

- ligar `GPIO7` do `ESP32-C6` ao `gate` do `IRLZ44N #2` atraves de resistor `100 a 220 ohm`
- ligar um resistor `10k` entre `gate` e `GND`
- ligar `source` do `IRLZ44N #2` ao `GND comum`
- ligar o `-` da `fanB` ao `drain` do `IRLZ44N #2`
- ligar o `+` da `fanB` ao `+12V`

### Peltier A com IRLZ44N #3 e XL4015 A

- ajustar o `XL4015 A` para `~2.0V` antes de ligar o `Peltier A`
- ligar `GPIO18` do `ESP32-C6` ao `gate` do `IRLZ44N #3` atraves de resistor `100 a 220 ohm`
- ligar um resistor `10k` entre `gate` e `GND`
- ligar `source` do `IRLZ44N #3` ao `GND comum`
- ligar `IN-` do `XL4015 A` ao `drain` do `IRLZ44N #3`
- ligar o `-` da `peltier fan A` ao `drain` do `IRLZ44N #3`
- ligar `IN+` do `XL4015 A` ao `+12V`
- ligar o `+` da `peltier fan A` ao `+12V`
- ligar `OUT+` do `XL4015 A` ao `+` do `Peltier A`
- ligar `OUT-` do `XL4015 A` ao `-` do `Peltier A`

### Peltier B com IRLZ44N #4 e XL4015 B

- ajustar o `XL4015 B` para `~2.0V` antes de ligar o `Peltier B`
- ligar `GPIO19` do `ESP32-C6` ao `gate` do `IRLZ44N #4` atraves de resistor `100 a 220 ohm`
- ligar um resistor `10k` entre `gate` e `GND`
- ligar `source` do `IRLZ44N #4` ao `GND comum`
- ligar `IN-` do `XL4015 B` ao `drain` do `IRLZ44N #4`
- ligar o `-` da `peltier fan B` ao `drain` do `IRLZ44N #4`
- ligar `IN+` do `XL4015 B` ao `+12V`
- ligar o `+` da `peltier fan B` ao `+12V`
- ligar `OUT+` do `XL4015 B` ao `+` do `Peltier B`
- ligar `OUT-` do `XL4015 B` ao `-` do `Peltier B`

### GND comum

- ligar ao mesmo `GND comum` a fonte `12V`, `ESP32-C6`, `NodeMCU R00`, `NodeMCU R07`, drivers dos heaters e `sources` dos `4 IRLZ44N`

### Sequencia de montagem

- `stage1`: montar apenas `R00`, `fanA`, `IRLZ44N #1`, `IRLZ44N #3`, `XL4015 A`, `Peltier A` e `peltier fan A`
- `full`: acrescentar `R07`, `fanB`, `IRLZ44N #2`, `IRLZ44N #4`, `XL4015 B`, `Peltier B` e `peltier fan B`

## 5) Impacto

Beneficios:

- coerencia entre codigo e proposta academica
- simplificacao da cablagem dos racks
- simplificacao da cablagem do CDU (4 canais de comutacao: fanA, fanB, peltierA, peltierB)
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
