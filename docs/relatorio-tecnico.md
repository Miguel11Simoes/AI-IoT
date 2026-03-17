# Relatorio Tecnico

Projeto: AI-IoT Digital Twin para Cooling Cooperativo
Data de revisao: 2026-03-17

## 1) Arquitetura tecnica final

## 1.1 Dispositivos

- Rack R00 (ESP8266 ESP-12E)
- Rack R07 (ESP8266 ESP-12E)
- CDU1 (ESP32-C6 DevKitC-1)
- Servidor (`server.py`)
- Frontend 3D (`twin3d/`)

## 1.2 Papel de cada no

Racks:
- medir temperatura (`t_hot`) com DS18B20 (conversao assincrona, nao bloqueante)
- estimar `t_liquid` quando existe apenas 1 sonda
- aplicar comando de heater (time-proportioning)
- rejeitar leituras NaN/Inf ou fora do intervalo valido

CDU:
- controlar fans de zona A/B por PWM (com rampa suave)
- controlar modulos Peltier A/B (on/off)
- as ventoinhas do dissipador dos Peltiers seguem por hardware o mesmo ramo de potencia
- reportar estado de supply (temperatura virtual)
- fallback local se comando remoto ficar stale

Servidor:
- fundir telemetria real + modelo sintetico
- gerar `rack_cmd` e `cdu_cmd`
- executar deteccao de anomalias (zscore / IsolationForest)
- threshold de anomalia configuravel via `--anomaly-temp-c` (default 80 deg C)
- blend coerente de todos os actuadores (fan/heat/heater_on/anomaly) durante transicao stale
- validar floats recebidos (rejeita NaN/Inf em t_hot_real_c e outros campos)

## 2) Comunicacao

Transporte principal: WebSocket.

- firmware edge <-> servidor: `edge ws` (porta 8765)
- frontend <-> servidor: `twin ws` (porta 8000)
- UI/API: HTTP 8080
- compatibilidade legada: TCP 5000

## 3) Protocolo

## 3.1 rack_telemetry

Campos principais:
- `type`, `id`, `t_hot`, `t_hot_real_c`, `t_liquid`, `heat_pwm`, `heater_on`,
  `local_anomaly`, `sensor_ok`, `telemetry_mode`, `rssi`, `ts`

Campos legados mantidos para compatibilidade:
- `fan_local_pwm` (fixo 0)

## 3.2 rack_cmd

Campos principais:
- `type`, `id`, `heat_pwm`, `anomaly`, `mode`

Campos legados:
- `fan_local_pwm` (0)

## 3.3 cdu_telemetry / cdu_cmd

- `fanA_pwm`, `fanB_pwm`
- `peltierA_on`, `peltierB_on`
- `t_supply_A`, `t_supply_B`
- `t_supply_target` (opcional; firmware so atualiza target se campo presente e finito)

## 4) Modelo termico no servidor

- layout fixo 2x4
- R00 e R07 reais quando online
- restantes racks por estimacao espacial/termica
- cooling dos racks sinteticos depende dos fans de zona do CDU

## 5) Controlo

## 5.1 Rack

- politica local para heater baseada em temperatura
- blending com `heat_pwm` remoto do servidor (40% local + 60% remoto)
- protecao por anomalia/temperatura critica
- remote anomaly propaga `localAnomaly=true` na telemetria
- atuacao do heater em time-proportioning (janela em ms)
- leitura DS18B20 assincrona: firmware dispara conversao e so le apos janela de tempo (~187ms)

## 5.2 CDU

- setpoint zonal de fan vindo do servidor
- Peltier A/B ligados quando temperatura de supply excede setpoint + 3 deg C
- ventoinhas de dissipador dos Peltiers ligam pelo mesmo ramo de potencia do modulo respetivo
- fallback local proporcional se comando remoto stale
- supply target so atualizado quando campo presente no comando e valor finito

## 6) Pinagem consolidada

Racks (ESP8266 ESP-12E):
- `ONE_WIRE_PIN=4` (DS18B20 DQ)
- `HEAT_PIN=5` (IRF520 heater)

CDU stage1 (ESP32-C6, 1 rack):
- `CDU_FAN_A_PIN=6`
- `CDU_PELTIER_A_PIN=18`
- canais B desativados (255)

CDU full (ESP32-C6, 2 racks):
- `CDU_FAN_A_PIN=6`, `CDU_FAN_B_PIN=7`
- `CDU_PELTIER_A_PIN=18`, `CDU_PELTIER_B_PIN=19`

## 7) Seguranca eletrica

- GND comum em toda a bancada
- DS18B20 com resistor de 4.7k pull-up
- heater no IRF520 em low-side
- sem ligacao direta de cargas 12V aos GPIOs

## 8) Alinhamento com RMIC

Coerente com o formulario submetido:
- racks com sensor + heater
- cooling fisico no CDU (fans zonais + Peltier)
- coordenacao central via servidor

## 9) Limites atuais

- com 1 DS18B20 por rack, `t_liquid` e estimado
- medidas de supply sao virtuais (sem sensor de temperatura de agua no CDU)
- Peltier sem feedback de temperatura propria

## 10) Estado final

- firmware e servidor atualizados para arquitetura-alvo
- todos os bugs HIGH de robustez corrigidos:
  - DS18B20 nao bloqueante
  - NaN rejeitado em Sensors.cpp e server.py
  - anomaly threshold alinhado entre firmware (80) e servidor (--anomaly-temp-c 80)
  - CDU t_supply_target com flag hasSupplyTarget
  - remote anomaly propaga localAnomaly em Control.cpp
  - stale blend coerente para todos os actuadores
  - AsyncExitStack no arranque dos dois servicos WebSocket
  - simulador respeita ok:false
  - frontend usa ws:// ou wss:// consoante protocolo da pagina
  - null guard em payload.racks.forEach
  - $pioArgs em stage_build.ps1 (nao sobrescreve variavel automatica PowerShell)
- pinagem correta definida em platformio.ini
- docs sincronizadas com o baseline tecnico atual
