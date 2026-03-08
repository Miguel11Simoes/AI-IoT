# Relatorio Tecnico

Projeto: AI-IoT Digital Twin para Cooling Cooperativo
Data de revisao: 2026-03-05

## 1) Arquitetura tecnica final

## 1.1 Dispositivos

- Rack R00 (ESP32-DEVKITC-V4)
- Rack R07 (ESP32-DEVKITC-V4)
- CDU1 (ESP32-C6 DevKitC-1)
- Servidor (`server.py`)
- Frontend 3D (`twin3d/`)

## 1.2 Papel de cada no

Racks:
- medir temperatura (`t_hot`) com DS18B20
- estimar `t_liquid` quando existe apenas 1 sonda
- aplicar comando de heater

CDU:
- controlar fans de zona A/B por PWM
- reportar estado de supply

Servidor:
- fundir telemetria real + modelo sintetico
- gerar `rack_cmd` e `cdu_cmd`
- executar deteccao de anomalias

## 2) Comunicacao

Transporte principal: WebSocket.

- firmware edge <-> servidor: `edge ws` (porta 8765)
- frontend <-> servidor: `twin ws` (porta 8000)
- UI/API: HTTP 8080
- compatibilidade legada: TCP 5000

## 3) Protocolo

## 3.1 rack_telemetry

Campos principais:
- `type`, `id`, `t_hot`, `t_liquid`, `heat_pwm`, `rssi`, `local_anomaly`, `ts`

Campos legados mantidos para compatibilidade:
- `fan_local_pwm` (fixo 0)
- `pump_v` (fixo 0)

## 3.2 rack_cmd

Campos principais:
- `type`, `id`, `heat_pwm`, `anomaly`, `mode`

Campos legados:
- `fan_local_pwm` (0)
- `pump_v` (0)

## 3.3 cdu_telemetry / cdu_cmd

- `fanA_pwm`, `fanB_pwm`
- `t_supply_A`, `t_supply_B`
- `t_supply_target`, `fallback_target`

## 4) Modelo termico no servidor

- layout fixo 2x4
- R00 e R07 reais quando online
- restantes racks por estimacao espacial/termica
- cooling dos racks sinteticos depende dos fans de zona do CDU

## 5) Controlo

## 5.1 Rack

- politica local para heater baseada em temperatura
- blending com `heat_pwm` remoto do servidor
- protecao por anomalia/temperatura critica
- atuacao do heater em time-proportioning (janela em ms)

## 5.2 CDU

- setpoint zonal vindo do servidor
- fallback local se comando remoto stale

## 6) Pinagem consolidada

Racks:
- `ONE_WIRE_PIN=4`
- `HEAT_PIN=18`

CDU:
- `CDU_FAN_A_PIN=4`
- `CDU_FAN_B_PIN=5`

## 7) Seguranca eletrica

- GND comum em toda a bancada
- DS18B20 com resistor de 4.7k pull-up
- heater no IRF520 em low-side
- sem ligacao direta de cargas 12V aos GPIOs

## 8) Alinhamento com RMIC

Coerente com o formulario submetido:
- racks com sensor + heater
- cooling fisico no CDU
- coordenacao central via servidor

## 9) Limites atuais

- com 1 DS18B20 por rack, `t_liquid` e estimado
- medidas de supply podem ser virtuais se nao houver sensorizacao adicional no CDU

## 10) Estado final

- firmware e servidor atualizados para arquitetura-alvo
- docs sincronizadas com o baseline tecnico atual
