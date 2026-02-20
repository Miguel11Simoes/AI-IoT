# AI-IoT Cooperative Cooling (Simulated Liquid)

Software stack for a 2-node cooperative cooling project:

- Node A: ESP32 + W5500
- Node B: RP2040 + W5500
- Cooperative TCP server in Python
- AI anomaly detection (`zscore` default, optional `IsolationForest`)
- Thermal model with virtual pump/flow (no real water required)

## 1. Folder structure

```text
AI-IoT/
  include/
    ProjectConfig.h
  lib/
    sensors/
    control/
    network/
    protocol/
  src/
    main.cpp
  tools/
    node_simulator.py
  platformio.ini
  server.py
  requirements.txt
```

## 2. Firmware environments

- `node_a_esp32`: ESP32 node A
- `node_b_pico`: RP2040 node B

Compile:

```bash
C:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_a_esp32
C:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_b_pico
```

Upload:

```bash
C:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_a_esp32 -t upload
C:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_b_pico -t upload
```

Monitor:

```bash
C:\Users\msmig\.platformio\penv\Scripts\platformio.exe device monitor -b 115200
```

## 3. Software-only validation (before hardware)

Install server dependencies:

```bash
python -m pip install -r requirements.txt
```

Start server (recommended stable mode):

```bash
python server.py --host 0.0.0.0 --port 5000 --detector zscore
```

Optional ML mode:

```bash
python server.py --host 0.0.0.0 --port 5000 --detector iforest
```

Run 2-node simulator in another terminal:

```bash
python tools/node_simulator.py --host 127.0.0.1 --port 5000 --duration 120 --inject-anomaly-after 45
```

Expected behavior:

- both virtual nodes send telemetry each second
- server computes global average and returns cooperative setpoints
- after anomaly injection in node B, detector should flag anomaly and force high cooling command

CSV logs are written to `logs/telemetry_log.csv`.

## 4. Node FSM

Implemented states in `src/main.cpp`:

- `INIT`
- `READ_SENSORS`
- `CONTROL_LOCAL`
- `SEND_DATA`
- `WAIT_SERVER`
- `APPLY_COMMAND`
- `WAIT_NEXT`

No long blocking delays are used in loop scheduling.

## 5. Virtual liquid model

In `lib/sensors/src/Sensors.cpp`, cooling is simulated with:

- `virtual_flow = pump_pwm / 255.0`
- fan and virtual flow impact hot/liquid thermal dynamics
- optional DS18B20 real reading fallback exists when `SIMULATED_COOLING=0`

## 6. Main parameters to tune

Edit `platformio.ini` build flags:

- network: `SERVER_IP_*`, `SERVER_PORT`, `DEVICE_IP_4`
- cycle timing: `CYCLE_INTERVAL_MS`, `NETWORK_TIMEOUT_MS`, `REMOTE_CMD_TTL_MS`
- thermal model: `HEAT_GAIN_C_PER_SEC`, `HOT_TO_LIQUID_COEFF`, `FLOW_COOLING_COEFF`, etc.
- mode: `SIMULATED_COOLING=1` (current default)

## 7. Suggested next step for hardware phase

Set `SIMULATED_COOLING=0` per environment once DS18B20 and MOSFET outputs are wired and validated.
