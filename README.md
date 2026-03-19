# AI-IoT - Hierarchical Cooperative Cooling Twin

Arquitetura atual:

- `2` racks reais: `R00` e `R07` em `NodeMCU / ESP8266 (ESP-12E)`
- `6` racks sinteticas no servidor para completar o twin `2x4`
- `1` CDU em `ESP32-C6` com `fanA`, `fanB`, `peltierA` e `peltierB`
- `server.py` como coordenador central, digital twin e AI
- UI 3D em `twin3d/`

## BOM atual

- `2x` NodeMCU / ESP8266 (`board = esp12e`)
- `1x` ESP32-C6 DevKitC-1
- `2x` DS18B20
- `2x` resistencias ceramicas `100 ohm` (`~1.44W @ 12V`)
- `2x` drivers low-side para os heaters das racks
- `4x` IRLZ44N no CDU
- `2x` XL4015 ajustados para `~2.0V`
- `2x` modulos Peltier
- `2x` ventoinhas `12V` do CDU (`fanA`, `fanB`)
- `2x` ventoinhas de dissipador das Peltiers
- `1x` fonte `12V 5A`

Notas de hardware:

- as ventoinhas dos dissipadores das Peltiers ligam no mesmo ramo comutado do respetivo Peltier
- nao existe GPIO nem MOSFET dedicado para `peltier fan`
- os GPIOs do `ESP32-C6` apenas comandam `fanA`, `fanB`, `peltierA` e `peltierB`

## Topologia runtime

```text
R00 / R07 (Wi-Fi WS) ----\
                          +--> server.py (twin + AI + controlo)
CDU ESP32-C6 (Wi-Fi WS) --/

server.py -> HTTP 8080 + WS twin 8000 + WS edge 8765 + TCP edge 5000
```

## Endpoints

- `TCP edge`: `5000`
- `WS twin`: `8000`
- `WS edge`: `8765`
- `HTTP UI/API`: `8080`

## Servidor

Arranque normal com as duas racks reais:

```bash
python server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --edge-ws-port 8765 --detector zscore --real-racks R00,R07
```

Fallback temporario para uma rack apenas:

```bash
python server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --edge-ws-port 8765 --detector zscore --real-racks R00
```

Dashboard:

```text
http://127.0.0.1:8080/twin3d/index.html
```

## Firmware e build

Targets PlatformIO:

- `rack_r00`
- `rack_r07`
- `cdu_esp32c6`

Build dos racks:

```bash
platformio run -e rack_r00
platformio run -e rack_r07
```

Build do CDU com cache isolada:

```powershell
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"
platformio run -e cdu_esp32c6
```

Ou:

```powershell
.\tools\cdu_build.ps1 build
```

Build completo do deployment atual:

```powershell
.\tools\stage_build.ps1 build
```

Upload:

```powershell
.\tools\stage_build.ps1 upload -RackR00Port COM3 -RackR07Port COM5 -CduPort COM4
```

## Pinout de referencia

Racks:

- `GPIO4` -> `DS18B20 DQ`
- `GPIO5` -> driver do heater

CDU:

- `GPIO6` -> `fanA`
- `GPIO7` -> `fanB`
- `GPIO18` -> `peltierA`
- `GPIO19` -> `peltierB`

## Modelo de dados

- a rack envia apenas telemetria real: `t_hot_real`, `heater_on`, `heat_pwm`, `sensor_ok`
- se houver segunda sonda, pode tambem enviar `t_liquid_real`
- o servidor estima `t_liquid` quando ela nao existe
- o servidor calcula `heater_real_w`, `heater_equivalent_w` e `t_virtual`
- se uma rack desaparecer, o servidor transita `real -> stale -> simulated`

## Checklist rapido

- preencher `WIFI_SSID`, `WIFI_PASSWORD` e `SERVER_HOST` em `platformio.ini`
- confirmar `HEATER_RATED_POWER_W=1.44` para as resistencias `100 ohm @ 12V`
- confirmar `GPIO4` e `GPIO5` nas duas racks
- confirmar `GPIO6`, `GPIO7`, `GPIO18` e `GPIO19` no CDU
- ajustar os dois `XL4015` para `~2.0V` antes de ligar os Peltiers
- garantir `GND` comum entre PSU, racks, CDU e drivers
