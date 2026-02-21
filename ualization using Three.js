warning: in the working copy of 'README.md', CRLF will be replaced by LF the next time Git touches it
[1mdiff --git a/README.md b/README.md[m
[1mindex 480344f..d4d5271 100644[m
[1m--- a/README.md[m
[1m+++ b/README.md[m
[36m@@ -1,123 +1,102 @@[m
[31m-# AI-IoT Cooperative Cooling (Simulated Liquid)[m
[32m+[m[32m# AI-IoT - Cooperative Cooling + 3D Twin[m
 [m
[31m-Software stack for a 2-node cooperative cooling project:[m
[32m+[m[32mThis folder contains the complete software stack for your project:[m
 [m
[31m-- Node A: ESP32 + W5500[m
[31m-- Node B: RP2040 + W5500[m
[31m-- Cooperative TCP server in Python[m
[31m-- AI anomaly detection (`zscore` default, optional `IsolationForest`)[m
[31m-- Thermal model with virtual pump/flow (no real water required)[m
[32m+[m[32m- MCU firmware for 2 nodes (`ESP32` + `RP2040`) with Ethernet W5500[m
[32m+[m[32m- Python cooperative server (global state + anomaly detection)[m
[32m+[m[32m- Centralized 3D digital twin using your GLB model (`rack/data_center_rack.glb`)[m
[32m+[m[32m- Real-time WebSocket stream for live thermal updates[m
 [m
[31m-## 1. Folder structure[m
[32m+[m[32mThere is no `dashboard/` folder. The frontend is under `twin3d/`.[m
[32m+[m
[32m+[m[32m## Project structure[m
 [m
 ```text[m
 AI-IoT/[m
   include/[m
[31m-    ProjectConfig.h[m
   lib/[m
[31m-    sensors/[m
[31m-    control/[m
[31m-    network/[m
[31m-    protocol/[m
   src/[m
[31m-    main.cpp[m
[32m+[m[32m  rack/[m
[32m+[m[32m    data_center_rack.glb[m
[32m+[m[32m  twin3d/[m
[32m+[m[32m    index.html[m
[32m+[m[32m    styles.css[m
[32m+[m[32m    main.js[m
   tools/[m
     node_simulator.py[m
[31m-  platformio.ini[m
   server.py[m
[32m+[m[32m  platformio.ini[m
   requirements.txt[m
 ```[m
 [m
[31m-## 2. Firmware environments[m
[31m-[m
[31m-- `node_a_esp32`: ESP32 node A[m
[31m-- `node_b_pico`: RP2040 node B[m
[31m-[m
[31m-Compile:[m
[32m+[m[32m## Architecture[m
 [m
[31m-```bash[m
[31m-C:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_a_esp32[m
[31m-C:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_b_pico[m
[32m+[m[32m```text[m
[32m+[m[32mMCUs -> TCP telemetry (5000) -> Python server -> WebSocket (8000) -> 3D twin[m
[32m+[m[32m                                       \-> HTTP API/static (8080)[m
 ```[m
 [m
[31m-Upload:[m
[32m+[m[32m## 1) Install Python dependencies[m
 [m
 ```bash[m
[31m-C:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_a_esp32 -t upload[m
[31m-C:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_b_pico -t upload[m
[32m+[m[32mpython -m pip install -r requirements.txt[m
 ```[m
 [m
[31m-Monitor:[m
[32m+[m[32m## 2) Run the cooperative server + 3D twin backend[m
 [m
 ```bash[m
[31m-C:\Users\msmig\.platformio\penv\Scripts\platformio.exe device monitor -b 115200[m
[32m+[m[32mpython server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --detector zscore[m
 ```[m
 [m
[31m-## 3. Software-only validation (before hardware)[m
[31m-[m
[31m-Install server dependencies:[m
[32m+[m[32mOptional AI model mode:[m
 [m
 ```bash[m
[31m-python -m pip install -r requirements.txt[m
[32m+[m[32mpython server.py --host 0.0.0.0 --port 5000 --ui-port 8080 --ws-port 8000 --detector iforest[m
 ```[m
 [m
[31m-Start server (recommended stable mode):[m
[32m+[m[32mOpen the twin:[m
 [m
[31m-```bash[m
[31m-python server.py --host 0.0.0.0 --port 5000 --detector zscore[m
[32m+[m[32m```text[m
[32m+[m[32mhttp://localhost:8080[m
 ```[m
 [m
[31m-Optional ML mode:[m
[32m+[m[32m## 3) Validate software only (without hardware)[m
 [m
[31m-```bash[m
[31m-python server.py --host 0.0.0.0 --port 5000 --detector iforest[m
[31m-```[m
[31m-[m
[31m-Run 2-node simulator in another terminal:[m
[32m+[m[32mRun node simulator while server is active:[m
 [m
 ```bash[m
 python tools/node_simulator.py --host 127.0.0.1 --port 5000 --duration 120 --inject-anomaly-after 45[m
 ```[m
 [m
[31m-Expected behavior:[m
[31m-[m
[31m-- both virtual nodes send telemetry each second[m
[31m-- server computes global average and returns cooperative setpoints[m
[31m-- after anomaly injection in node B, detector should flag anomaly and force high cooling command[m
[31m-[m
[31m-CSV logs are written to `logs/telemetry_log.csv`.[m
[31m-[m
[31m-## 4. Node FSM[m
[32m+[m[32m## 4) Compile firmware[m
 [m
[31m-Implemented states in `src/main.cpp`:[m
[32m+[m[32mESP32 node A:[m
 [m
[31m-- `INIT`[m
[31m-- `READ_SENSORS`[m
[31m-- `CONTROL_LOCAL`[m
[31m-- `SEND_DATA`[m
[31m-- `WAIT_SERVER`[m
[31m-- `APPLY_COMMAND`[m
[31m-- `WAIT_NEXT`[m
[31m-[m
[31m-No long blocking delays are used in loop scheduling.[m
[32m+[m[32m```bash[m
[32m+[m[32mC:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_a_esp32[m
[32m+[m[32m```[m
 [m
[31m-## 5. Virtual liquid model[m
[32m+[m[32mRP2040 node B:[m
 [m
[31m-In `lib/sensors/src/Sensors.cpp`, cooling is simulated with:[m
[32m+[m[32m```bash[m
[32m+[m[32mC:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_b_pico[m
[32m+[m[32m```[m
 [m
[31m-- `virtual_flow = pump_pwm / 255.0`[m
[31m-- fan and virtual flow impact hot/liquid thermal dynamics[m
[31m-- optional DS18B20 real reading fallback exists when `SIMULATED_COOLING=0`[m
[32m+[m[32mUpload:[m
 [m
[31m-## 6. Main parameters to tune[m
[32m+[m[32m```bash[m
[32m+[m[32mC:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_a_esp32 -t upload[m
[32m+[m[32mC:\Users\msmig\.platformio\penv\Scripts\platformio.exe run -e node_b_pico -t upload[m
[32m+[m[32m```[m
 [m
[31m-Edit `platformio.ini` build flags:[m
[32m+[m[32m## API endpoints[m
 [m
[31m-- network: `SERVER_IP_*`, `SERVER_PORT`, `DEVICE_IP_4`[m
[31m-- cycle timing: `CYCLE_INTERVAL_MS`, `NETWORK_TIMEOUT_MS`, `REMOTE_CMD_TTL_MS`[m
[31m-- thermal model: `HEAT_GAIN_C_PER_SEC`, `HOT_TO_LIQUID_COEFF`, `FLOW_COOLING_COEFF`, etc.[m
[31m-- mode: `SIMULATED_COOLING=1` (current default)[m
[32m+[m[32m- `GET /api/health`[m
[32m+[m[32m- `GET /api/config`[m
[32m+[m[32m- `GET /api/state`[m
[32m+[m[32m- `GET /api/history?node=A&points=120`[m
[32m+[m[32m- `GET /api/twin?racks=8`[m
 [m
[31m-## 7. Suggested next step for hardware phase[m
[32m+[m[32mWebSocket:[m
 [m
[31m-Set `SIMULATED_COOLING=0` per environment once DS18B20 and MOSFET outputs are wired and validated.[m
[32m+[m[32m- `ws://localhost:8000`[m
