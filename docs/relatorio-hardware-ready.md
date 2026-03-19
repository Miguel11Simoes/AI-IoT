# Relatorio Hardware-Ready

Projeto: AI-IoT Hierarchical Cooperative Cooling Twin
Data: 2026-03-18

## 1) Resumo

O projeto esta alinhado para o deployment atual:

- `R00` e `R07` em `NodeMCU / ESP8266`
- `1` CDU em `ESP32-C6`
- `2` heaters de rack
- `2` fans zonais
- `2` Peltiers
- `2` ventoinhas de dissipador das Peltiers, sem GPIO dedicado

## 2) BOM atual

- `2x` NodeMCU / ESP8266 (`board = esp12e`)
- `1x` ESP32-C6 DevKitC-1
- `2x` DS18B20
- `2x` resistencias ceramicas `100 ohm`
- `2x` drivers low-side para os heaters das racks
- `4x` IRLZ44N no CDU
- `2x` XL4015 ajustados para `~2.0V`
- `2x` modulos Peltier
- `2x` ventoinhas `12V` do CDU
- `2x` ventoinhas de dissipador das Peltiers
- `1x` fonte `12V 5A`

## 3) Arquitetura resultante

- Rack R00/R07:
  - sensor: `DS18B20` em `GPIO4`
  - atuador: resistencia `100 ohm` a `12V` via driver low-side em `GPIO5`
- CDU:
  - `fanA` em `GPIO6`
  - `fanB` em `GPIO7`
  - `peltierA` em `GPIO18`
  - `peltierB` em `GPIO19`
- Servidor:
  - twin `2x4`
  - AI
  - fallback `real -> stale -> simulated`

## 4) Pressupostos de montagem

- os `4x IRLZ44N` sao usados apenas no `CDU`
- os heaters das racks usam os drivers proprios das racks
- as ventoinhas dos dissipadores das Peltiers ligam no mesmo ramo de potencia do respetivo Peltier
- a montagem atual usa os dois canais do `CDU`

## 5) Esquema unico de bancada

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
| D2/GPIO4 <-    |              | D2/GPIO4 <-    |              | GPIO7  -> fanB  |
| DS18B20 DQ     |              | DS18B20 DQ     |              | GPIO18 -> PeltA |
| D1/GPIO5 ->    |              | D1/GPIO5 ->    |              | GPIO19 -> PeltB |
| heater driver  |              | heater driver  |              | GND comum       |
+-------+--------+              +-------+--------+              +-------+--------+
        |                               |                               |
        ------------------------ GND COMUM -------------------------------
                                      |
                               +------+------+
                               | PSU 12V 5A  |
                               +------+------+
                                      |
        +-----------------------------+------------------------------+
        |                             |                              |
     +12V heater R00              +12V heater R07                 +12V CDU
        |                             |                              |
  +-----v-----+                 +-----v-----+                +------v------------------+
  | Resistor  |                 | Resistor  |                | Distribuicao CDU 12V    |
  | 100 ohm   |                 | 100 ohm   |                | +12V -> fanA +          |
  +-----+-----+                 +-----+-----+                | +12V -> fanB +          |
        |                             |                      | +12V -> XL4015 A IN+    |
        |                             |                      | +12V -> XL4015 B IN+    |
        |                             |                      | +12V -> Peltier fan A + |
        |                             |                      | +12V -> Peltier fan B + |
  +-----v------+                +-----v------+                +------------+------------+
  | Heater drv |                | Heater drv |                             |
  | rack R00   |                | rack R07   |                             |
  | in <- D1   |                | in <- D1   |                 +-----------v------------+
  | src -> GND |                | src -> GND |                 | IRLZ44N #1 fanA       |
  +------------+                +------------+                 | gate <- GPIO6         |
                                                               | drain <- fanA -       |
                                                               | source -> GND         |
                                                               +-----------------------+

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
                                     +------v------+
                                     | Peltier B   |
                                     | + <- OUT+   |
                                     | - <- OUT-   |
                                     +-------------+
```

## 6) Ligacoes fio-a-fio

### Rack R00

- ligar `DS18B20 VDD` ao `3V3` da `NodeMCU R00`
- ligar `DS18B20 GND` ao `GND` da `NodeMCU R00`
- ligar `DS18B20 DQ` ao `D2 / GPIO4`
- ligar `4.7k` entre `3V3` e `DQ`
- ligar `D1 / GPIO5` ao `IN/SIG` do driver do heater
- ligar `GND` da `NodeMCU R00` ao `GND` do driver do heater
- ligar `+12V` ao primeiro terminal da resistencia `100 ohm`
- ligar o segundo terminal da resistencia ao `DRAIN/OUT` do driver do heater
- ligar `SOURCE/GND` do driver ao `GND comum`

### Rack R07

- repetir a mesma topologia de `R00`

### CDU fanA

- `GPIO6` -> resistor `100..220 ohm` -> gate do `IRLZ44N #1`
- `10k` entre gate e `GND`
- source -> `GND comum`
- `fanA -` -> drain
- `fanA +` -> `+12V`

### CDU fanB

- `GPIO7` -> resistor `100..220 ohm` -> gate do `IRLZ44N #2`
- `10k` entre gate e `GND`
- source -> `GND comum`
- `fanB -` -> drain
- `fanB +` -> `+12V`

### Peltier A

- ajustar `XL4015 A` para `~2.0V`
- `GPIO18` -> resistor `100..220 ohm` -> gate do `IRLZ44N #3`
- `10k` entre gate e `GND`
- source -> `GND comum`
- `XL4015 A IN-` -> drain
- `peltier fan A -` -> drain
- `XL4015 A IN+` -> `+12V`
- `peltier fan A +` -> `+12V`
- `XL4015 A OUT+` -> `Peltier A +`
- `XL4015 A OUT-` -> `Peltier A -`

### Peltier B

- ajustar `XL4015 B` para `~2.0V`
- `GPIO19` -> resistor `100..220 ohm` -> gate do `IRLZ44N #4`
- `10k` entre gate e `GND`
- source -> `GND comum`
- `XL4015 B IN-` -> drain
- `peltier fan B -` -> drain
- `XL4015 B IN+` -> `+12V`
- `peltier fan B +` -> `+12V`
- `XL4015 B OUT+` -> `Peltier B +`
- `XL4015 B OUT-` -> `Peltier B -`

## 7) Regras de seguranca

- todos os `GND` ficam em comum
- nao ligar cargas `12V` diretamente aos GPIOs
- ajustar os `XL4015` sem o Peltier ligado
- confirmar polaridade das Peltiers antes do primeiro teste

## 8) Estado

- arquitetura: alinhada com o deployment atual
- documentacao: sincronizada com `2 racks + 1 CDU`
- validacao final pendente: upload real e bancada fisica
