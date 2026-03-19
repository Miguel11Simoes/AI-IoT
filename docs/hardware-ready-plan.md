# Hardware-Ready Plan

## Objetivo

Fechar o deployment atual:

- `2` racks reais: `R00` e `R07`
- `1` CDU real: `fanA`, `fanB`, `peltierA`, `peltierB`
- `6` racks sinteticas no servidor

## Firmware por papel

### rack_r00 / rack_r07

- le `DS18B20` de forma assincrona
- rejeita `NaN`, `Inf` e leituras invalidas
- controla apenas o heater local
- envia telemetria real
- aplica `rack_cmd`

### cdu_esp32c6

- controla `fanA_pwm` em `GPIO6`
- controla `fanB_pwm` em `GPIO7`
- controla `peltierA_on` em `GPIO18`
- controla `peltierB_on` em `GPIO19`
- envia `cdu_telemetry`
- aplica `cdu_cmd`
- usa fallback local se o comando remoto ficar stale

## Papel do servidor

- aceita telemetria real de `R00` e `R07`
- estima `t_liquid` quando a rack nao a mede
- calcula `heater_real_w`, `heater_equivalent_w` e `t_virtual`
- mantem fallback `real -> stale -> simulated` por rack
- gera comandos para as duas racks e para o CDU

## Constrangimentos eletricos

- `GND` comum entre PSU, racks, CDU e drivers
- `DS18B20` com `4.7k` pull-up
- heater em low-side no driver da rack
- cada Peltier com `1x XL4015`
- cada ventoinha de dissipador da Peltier liga no mesmo ramo comutado do respetivo Peltier

## Build e deploy

```powershell
.\tools\stage_build.ps1 build
.\tools\stage_build.ps1 upload -RackR00Port COM3 -RackR07Port COM5 -CduPort COM4
```

Build manual do CDU:

```powershell
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"
platformio run -e cdu_esp32c6
```

## Bring-up

1. Arrancar `server.py`.
2. Abrir o dashboard.
3. Ligar o `CDU`.
4. Ligar `R00`.
5. Ligar `R07`.
6. Confirmar `real` nas duas racks.
7. Confirmar `stale -> simulated` quando uma rack desliga.
