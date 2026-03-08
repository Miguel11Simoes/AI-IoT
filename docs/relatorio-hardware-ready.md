# Relatorio Hardware-Ready

Projeto: AI-IoT Hierarchical Cooperative Cooling Twin
Data: 2026-03-05

## 1) Resumo executivo

O repositorio foi alinhado com o projeto submetido no RMIC:

- Racks fisicos (`R00`, `R07`) fazem medicao termica e atuacao de heater.
- CDU (`ESP32-C6`) faz o controlo de cooling por fans zonais.
- Servidor coordena setpoints e mantem twin 2x4 com 6 racks sinteticos.

## 2) Incoerencia identificada

Estado anterior do codigo:

- racks tinham atuacao local de `fan` e `pump`
- servidor gerava `rack_cmd` com `fan_local_pwm` e `pump_v`

Incoerencia com o formulario RMIC:

- BOM e descricao do projeto definem rack com `DS18B20 + heater`
- cooling fisico representado por fans do CDU

## 3) Correcao aplicada

### Firmware de rack

- removida atuacao fisica local de fan/pump no `ControlManager`
- mantido controlo de heater com janela temporal (`HEAT_WINDOW_MS`)
- telemetria de `fan_local_pwm` e `pump_v` mantida apenas por compatibilidade, sempre em `0`

### Configuracao

- removidos `FAN_PIN` e `PUMP_PIN` ativos dos ambientes `rack_r00` e `rack_r07` em `platformio.ini`
- `RackNodeConfig` agora usa apenas pinos necessarios para o rack alvo (`ONE_WIRE_PIN`, `HEAT_PIN`)

### Servidor

- modelo termico dos racks passou a usar cooling zonal do CDU
- `rack_cmd` passou para semantica `heat-only` (fan/pump locais em 0)
- snapshot e comandos preservam campos legados para compatibilidade de frontend

## 4) Arquitetura resultante

- Rack R00/R07:
  - sensor: DS18B20
  - atuador: heater 12V/20W via IRF520
- CDU:
  - atuadores: fanA/fanB via DFR0332
- Servidor:
  - AI + twin + coordenacao de setpoints

## 5) Impacto

Beneficios:

- coerencia entre codigo e proposta academica
- simplificacao da cablagem dos racks
- separacao clara de responsabilidades (rack aquece/mede, CDU arrefece)

Compatibilidade:

- protocolo JSON e frontend mantidos funcionais
- campos legados de fan/pump no rack continuam presentes, com valor 0

## 6) Estado

- arquitetura: alinhada com RMIC
- documentacao `docs/`: atualizada para o novo baseline
- validacao local: analise estatica/sintaxe executada
