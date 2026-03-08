# Relatorio Frontend

Projeto: Twin 3D para AI-IoT
Revisao: 2026-03-05

## 1) Objetivo

Apresentar o estado do twin de 8 racks em tempo real, destacando:

- temperatura hot/liquid
- estado de anomalia
- racks reais vs sinteticos
- estado do CDU (fanA/fanB e supply)

## 2) Fonte de dados

Dados consumidos do servidor:

- stream WebSocket (`twin_state`)
- endpoints HTTP de snapshot/historico (quando usados)

## 3) Campos relevantes por rack

Usados no frontend:

- `label`
- `is_real`
- `temp_hot`
- `temp_liquid`
- `heat_pwm`
- `anomaly`
- `status`
- `target_heat_pwm`

Campos legados preservados por compatibilidade visual:

- `fan_pwm` (0 em racks reais no baseline atual)
- `pump_pwm` (0 em racks reais no baseline atual)
- `target_fan_pwm` (0)
- `target_pump_pwm` (0)

## 4) Campos relevantes de CDU

- `fanA_pwm`
- `fanB_pwm`
- `t_supply_A`
- `t_supply_B`
- `cmd_fanA_pwm`
- `cmd_fanB_pwm`
- `t_supply_target`

## 5) Semantica visual recomendada

- racks reais (`R00`, `R07`) com badge `REAL`
- racks sinteticos com badge `MODEL`
- mapa de cor por `temp_hot`
- alerta visual por `anomaly=true`
- painel CDU separado do painel de racks

## 6) Alinhamento com arquitetura atual

No frontend, cooling de rack nao e mostrado como atuacao fisica local.
A atuacao fisica de cooling esta concentrada no CDU.

## 7) Validacao

Checklist:

- confirmar que `R00` e `R07` entram como `is_real=true`
- confirmar racks restantes como sinteticos
- confirmar fanA/fanB do CDU variam com carga termica
- confirmar racks mostram `target_heat_pwm` coerente
