# Hardware-Ready Plan (Alinhado com RMIC)

## Objetivo

Implementar a arquitetura final:

- 2 racks reais (`R00`, `R07`) com `DS18B20 + heater`.
- 1 CDU real (`ESP32-C6`) com `fanA/fanB`, `peltierA/peltierB` e ventoinhas de dissipador.
- 6 racks restantes sinteticos no servidor.

## 1) Firmware por papel

### rack_r00 / rack_r07

- le `DS18B20` de forma assincrona (conversao nao bloqueante)
- rejeita leituras NaN/Inf ou fora de [-100, 130] deg C
- estima `t_liquid` quando existe apenas 1 sensor
- controla apenas `heater` (`HEAT_PIN=5`)
- envia `rack_telemetry`
- aplica `rack_cmd` (heat-first)

### cdu_esp32c6 (stage1)

- controla `fanA_pwm` (GPIO6)
- controla `peltierA_on` (GPIO18)
- ventoinha de dissipador quente `peltierFanA` (GPIO20) segue estado do peltierA
- envia `cdu_telemetry`
- aplica `cdu_cmd`
- fallback local proporcional se comando ficar stale
- canais B desativados (255)

### cdu_esp32c6_full

- igual a stage1 com canais B ativos:
  - `fanB_pwm` (GPIO7)
  - `peltierB_on` (GPIO19)
  - `peltierFanB` (GPIO21)

## 2) Papel do servidor

- aceita telemetria real apenas de `R00` e `R07`
- atualiza twin 2x4 (8 racks)
- gera comandos de heater para racks
- gera comandos de cooling zonal para CDU (fans + Peltier)
- executa deteccao de anomalias (zscore / iforest)
- anomaly threshold alinhado com firmware: `--anomaly-temp-c` default 80 deg C

## 3) Constrangimentos eletricos

- GND comum entre PSU, racks, CDU e drivers
- DS18B20 com pull-up 4.7k
- heater em low-side no IRF520
- Peltier com driver de corrente adequado (~6A por modulo)
- sem cooling local fisico nos racks

## 4) Build e deploy

### Racks (ESP8266 ESP-12E)

```bash
platformio run -e rack_r00
platformio run -e rack_r07
```

Ou usar `default_envs = rack_r00` e correr `platformio run` simples.

### CDU stage1

```powershell
.\tools\stage_build.ps1 build stage1
```

### CDU full

```powershell
.\tools\stage_build.ps1 build full
```

### CDU (manual, com packages dir isolado)

```powershell
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\.pio-cdu-packages"
platformio run -e cdu_esp32c6
```

## 5) Bring-up

1. Arrancar `server.py`.
2. Ligar CDU e validar `cdu_telemetry` + fans a responder.
3. Verificar que peltierA liga quando supply excede setpoint + 3 deg C.
4. Verificar que peltierFanA liga/desliga em sincronia com peltierA.
5. Ligar R00 e validar leitura DS18B20 + heater cmd.
6. Ligar R07 e validar resposta zonal A/B no CDU.
7. Confirmar twin com R00/R07 reais e restantes sinteticos.
8. Testar fallback: desligar servidor -> CDU deve manter supply por controlo local.
