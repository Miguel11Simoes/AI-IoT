# Hardware-Ready Plan (Alinhado com RMIC)

## Objetivo

Implementar a arquitetura final:

- 2 racks reais (`R00`, `R07`) com `DS18B20 + heater`.
- 1 CDU real (`ESP32-C6`) com `fanA/fanB` zonais.
- 6 racks restantes sinteticos no servidor.

## 1) Firmware por papel

### rack_r00 / rack_r07

- le `DS18B20` (`t_hot`)
- estima `t_liquid` quando existe apenas 1 sensor
- controla apenas `heater` (`HEAT_PIN`)
- envia `rack_telemetry`
- aplica `rack_cmd` (heat-first)

### cdu_esp32c6

- controla `fanA_pwm` e `fanB_pwm`
- envia `cdu_telemetry`
- aplica `cdu_cmd`
- fallback local se comando ficar stale

## 2) Papel do servidor

- aceita telemetria real apenas de `R00` e `R07`
- atualiza twin 2x4 (8 racks)
- gera comandos de heater para racks
- gera comandos de cooling zonal para CDU
- executa deteccao de anomalias (zscore / iforest)

## 3) Constrangimentos eletricos

- GND comum entre PSU, racks, CDU e drivers
- DS18B20 com pull-up 4.7k
- heater em low-side no IRF520
- sem fan/pump local fisico nos racks

## 4) Build e deploy

### Racks

```bash
platformio run -e rack_r00
platformio run -e rack_r07
```

### CDU

```powershell
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"
platformio run -e cdu_esp32c6
```

## 5) Bring-up

1. Arrancar `server.py`.
2. Ligar CDU e validar `cdu_telemetry`.
3. Ligar R00 e validar leitura DS18B20 + heater cmd.
4. Ligar R07 e validar resposta zonal A/B no CDU.
5. Confirmar twin com R00/R07 reais e restantes sinteticos.
