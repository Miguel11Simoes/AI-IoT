# AI-IoT - Hierarchical Cooperative Cooling Twin

Arquitetura final suportada:

- `2` racks reais: `R00` e `R07` (`ESP32-DEVKITC-V4`)
- `6` racks virtuais estimadas no servidor (`2x4`)
- `1` CDU (`ESP32-C6`) com duas zonas (`fanA`, `fanB`)
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

```bash
python server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --edge-ws-port 8765 --detector zscore
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

- `rack_r00` (`ESP32-DEVKITC-V4`, rack `R00`)
- `rack_r07` (`ESP32-DEVKITC-V4`, rack `R07`)
- `cdu_esp32c6` (`ESP32-C6`, `CDU1`)

Build:

```bash
platformio run -e rack_r00
platformio run -e rack_r07
```

For `ESP32-C6` use an isolated packages cache (avoids package conflicts with ESP32 legacy toolchain):

```powershell
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"
platformio run -e cdu_esp32c6
```

Or run:

```powershell
.\tools\cdu_build.ps1
```

Upload:

```bash
platformio run -e rack_r00 -t upload
platformio run -e rack_r07 -t upload
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"; platformio run -e cdu_esp32c6 -t upload
```

Or:

```powershell
.\tools\cdu_build.ps1 upload
```

## Configuração obrigatória

Editar `platformio.ini`:

- `WIFI_SSID`
- `WIFI_PASSWORD`
- `SERVER_HOST` (IP do PC com `server.py`)
- pinos conforme a tua cablagem (`ONE_WIRE_PIN`, `HEAT_PIN`, `CDU_FAN_A_PIN`, `CDU_FAN_B_PIN`, etc.)
