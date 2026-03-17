# AI-IoT - Hierarchical Cooperative Cooling Twin

Arquitetura final suportada:

- `1` ou `2` racks reais configuraveis: `R00` agora, `R00 + R07` depois (`ESP8266MOD/ESP-12E`)
- `6` racks virtuais estimadas no servidor (`2x4`)
- `1` CDU (`ESP32-C6`) com duas zonas (`fanA`, `fanB`) e `2` saidas Peltier
- servidor central (`server.py`) com modelo térmico zonal + AI + setpoints
- frontend 3D único em `twin3d/`

## BOM mínimo alvo

- `2x` ESP32-DEVKITC-V4 (racks)
- `1x` ESP32-C6 DevKitC-1 (CDU)
- `2x` DS18B20 (1 por rack)
- `2x` resistência `12V 20W` (1 por rack)
- `2x` módulo IRF520 (heater low-side)
- `2x` fan module DFR0332 (CDU zona A/B)
- `1x` fonte `12V 5A`

Nota de segurança: o heater usa `time-proportioning` com janela de `2s` (`HEAT_WINDOW_MS=2000`), não PWM rápido.

Update target:

- racks migradas para `ESP8266MOD / ESP-12E`
- servidor pode arrancar com apenas `R00` real e mais tarde aceitar `R00,R07`
- CDU passa a ter `fanA/fanB` + `peltierA/peltierB`

Hardware note:

- os Peltiers `2V 8.5A` precisam de driver de potencia e alimentacao dedicada; nao ligar diretamente ao `ESP32-C6`

Stage plan:

- agora: `R00 + fanA + peltierA`
- depois: `R00 + R07 + fanA + fanB + peltierA + peltierB`

Nota de cablagem:

- cada ventoinha do dissipador da Peltier liga no mesmo ramo de potencia do respetivo Peltier
- nao existe GPIO nem MOSFET dedicado para `peltier fan`
- quando `peltierA` liga, a sua ventoinha liga por hardware; o mesmo para `peltierB`

Peltier BOM minimo (2 canais):

- `1x` fonte DC de potencia com folga (`5V/10A` ou `12V/5A`)
- `2x` buck DC-DC ajustavel com limite de corrente, configurados para `2.0V`, `>=10A` continuos
- `2x` MOSFET logic-level / driver DC (`3.3V gate`, `>=15A`)
- `2x` dissipador + ventoinha para o lado quente
- pasta termica, fixacao mecanica, cabos grossos e fusivel

## Topologia runtime

```text
R00 / R07 (Wi-Fi WS) ----\
                          +--> server.py (estado global + AI + controlo)
CDU ESP32-C6 (Wi-Fi WS) --/

server.py -> HTTP 8080 + WS twin 8000 + WS edge 8765 + TCP edge 5000
```

## Endpoints

- `TCP edge`: `5000`
- `WS twin (dashboard)`: `8000`
- `WS edge (firmware)`: `8765`
- `HTTP UI/API`: `8080`

## Correr servidor

Arranque inicial com uma rack real:

```bash
python server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --edge-ws-port 8765 --detector zscore --real-racks R00
```

Quando adicionares a segunda rack:

```bash
python server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --edge-ws-port 8765 --detector zscore --real-racks R00,R07
```

Abrir dashboard:

```text
http://127.0.0.1:8080/twin3d/index.html
```

## Teste sem hardware

```bash
python tools/node_simulator.py --host 127.0.0.1 --port 5000 --duration 180 --interval 1 --inject-anomaly-after 45
```

## Targets PlatformIO

- `rack_r00` (`ESP8266MOD / ESP-12E`, rack `R00`)
- `rack_r07` (`ESP8266MOD / ESP-12E`, rack `R07`)
- `cdu_esp32c6` (`ESP32-C6`, `CDU1`, stage1: `fanA + peltierA`)
- `cdu_esp32c6_full` (`ESP32-C6`, `CDU1`, stage final: `fanA + fanB + 2x Peltier`)

Build:

```bash
platformio run -e rack_r00
platformio run -e rack_r07
```

For `ESP32-C6` use an isolated packages cache (avoids package conflicts with ESP32 legacy toolchain):

```powershell
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"
platformio run -e cdu_esp32c6
platformio run -e cdu_esp32c6_full
```

Or run:

```powershell
.\tools\cdu_build.ps1
.\tools\cdu_build.ps1 build full
```

Upload:

```bash
platformio run -e rack_r00 -t upload
platformio run -e rack_r07 -t upload
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"; platformio run -e cdu_esp32c6 -t upload
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"; platformio run -e cdu_esp32c6_full -t upload
```

Or:

```powershell
.\tools\cdu_build.ps1 upload
.\tools\cdu_build.ps1 upload full
```

## Configuração obrigatória

Editar `platformio.ini`:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `SERVER_HOST` (IP do PC com `server.py`)
- pinos conforme a tua cablagem (`ONE_WIRE_PIN`, `HEAT_PIN`, `CDU_FAN_A_PIN`, `CDU_FAN_B_PIN`, `CDU_PELTIER_A_PIN`, `CDU_PELTIER_B_PIN`, etc.)
- para racks `ESP8266`, a configuracao base usa `GPIO4` no DS18B20 e `GPIO5` no heater

## Hardware-ready workflow

Stage 1 (`1 rack + 1 fan + 1 Peltier`):

```powershell
python server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --edge-ws-port 8765 --detector zscore --real-racks R00 --heater-equivalent-target-w 20 --heater-default-power-w 1.44 --virtual-ambient-c 26
.\tools\stage_build.ps1 build stage1
.\tools\stage_build.ps1 upload stage1 -RackR00Port COM3 -CduPort COM4
```

Stage full (`2 racks + 2 fans + 2 Peltiers`):

```powershell
python server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --edge-ws-port 8765 --detector zscore --real-racks R00,R07 --heater-equivalent-target-w 20 --heater-default-power-w 1.44 --virtual-ambient-c 26
.\tools\stage_build.ps1 build full
.\tools\stage_build.ps1 upload full -RackR00Port COM3 -RackR07Port COM5 -CduPort COM4
```

If you only want the CDU:

```powershell
.\tools\cdu_build.ps1 build stage1
.\tools\cdu_build.ps1 upload full -UploadPort COM4
```

## Pre-upload checklist

- `platformio.ini` has the correct `WIFI_SSID`, `WIFI_PASSWORD` and `SERVER_HOST`
- rack heater power matches reality (`HEATER_RATED_POWER_W=1.44` for the current `100 ohm @ 12V` prototype)
- `rack_r00` and `rack_r07` pinout matches the wiring (`GPIO4` DS18B20, `GPIO5` heater in the current base profile)
- `cdu_esp32c6` is used for `stage1` (`fanA + peltierA`)
- `cdu_esp32c6_full` is only used when `fanB` and `peltierB` are really wired
- each Peltier fan is wired to the same switched power branch as its Peltier, with no dedicated GPIO
- server `--real-racks` matches the hardware currently connected

## Bring-up checklist

1. Start `server.py`.
2. Open `http://127.0.0.1:8080/twin3d/index.html`.
3. Power the CDU and confirm `CDU Plant` is online.
4. Power `R00` and confirm it appears as `real`.
5. If `R00` drops, confirm it moves through `stale` and then `simulated`.
6. For full deployment, power `R07` and confirm the same transition logic independently.
7. Check that the table shows `T_real`, `T_virtual`, `heater real`, `heater eq`, and the expected `source_status`.
