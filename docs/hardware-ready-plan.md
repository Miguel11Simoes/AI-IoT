# Hardware-Ready Plan (Final Target)

This file is the final practical plan aligned with the available hardware:

- `2x ESP32-DEVKITC-V4` as rack nodes (`R00`, `R07`)
- `1x ESP32-C6` as CDU controller (`CDU1`)
- `2x DS18B20` (one per rack, real `T_hot`)
- `2x 12V 20W` heaters (one per rack)
- `2x IRF520` modules for heater switching (slow time-proportioning)
- `2x DFR0332` fan modules for CDU zones A/B
- `1x 12V 5A` PSU

## 1) Firmware roles

- `rack_r00` and `rack_r07`:
  - read DS18B20 (`T_hot`)
  - estimate `T_liquid` when second probe is missing
  - apply heater power with `HEAT_WINDOW_MS=2000` (slow PWM window)
  - send `rack_telemetry` over Wi-Fi WS
  - apply `rack_cmd` from server
- `cdu_esp32c6`:
  - control `fanA_pwm` and `fanB_pwm`
  - send `cdu_telemetry`
  - apply `cdu_cmd`
  - local fallback if server command is stale

## 2) Server role (`server.py`)

- fixed 2x4 digital twin
- only `R00` and `R07` accepted as real rack telemetry
- six remaining racks estimated by spatial + thermal model
- zonal model:
  - zone A: columns 0-1
  - zone B: columns 2-3
  - tracks `t_supply_A`, `t_supply_B`
- sends:
  - `rack_cmd` to racks
  - `cdu_cmd` to CDU
- AI/anomaly:
  - z-score default
  - optional IsolationForest

## 3) Critical control detail for IRF520

Heater output is not high-frequency PWM.  
It is time-proportioning:

- window = 2000 ms
- `heat_pwm=128` means about 50% ON time over the 2 s window
- this avoids stressing IRF520 with fast switching

## 4) PlatformIO targets

- `rack_r00`
- `rack_r07`
- `cdu_esp32c6`

Build:

```bash
platformio run -e rack_r00
platformio run -e rack_r07
```

For `cdu_esp32c6`, use isolated package cache:

```powershell
$env:PLATFORMIO_PACKAGES_DIR = "$PWD\\.pio-cdu-packages"
platformio run -e cdu_esp32c6
```

## 5) Bring-up order

1. Start server:
   - `python server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --edge-ws-port 8765`
2. Validate software only:
   - `python tools/node_simulator.py --host 127.0.0.1 --port 5000 --duration 120`
3. Flash CDU and check telemetry online.
4. Flash `rack_r00` and verify real updates on dashboard.
5. Flash `rack_r07` and verify both corners online.
6. Apply heater step test on `R07` and confirm:
   - zone B fan increases
   - predicted/critical rack updates
   - anomaly logic reacts if threshold crossed

## 6) Wiring constraints

- all grounds must be common (`ESP32`, `ESP32-C6`, `12V PSU`, IRF520 modules)
- DS18B20 requires 4.7k pull-up on DATA
- heater path (low-side): `+12V -> heater -> IRF520 drain`, source to GND
