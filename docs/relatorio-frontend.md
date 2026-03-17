# Relatorio Frontend

Projeto: Twin 3D para AI-IoT
Revisao: 2026-03-17

## 1) Objetivo

Apresentar o estado do twin de 8 racks em tempo real, destacando:

- temperatura hot/liquid
- estado de anomalia
- racks reais vs sinteticos
- estado do CDU (fanA/fanB, peltierA/peltierB, supply)

## 2) Fonte de dados

Dados consumidos do servidor:

- stream WebSocket (`twin_state`) via `ws://` ou `wss://` (detetado automaticamente
  a partir do protocolo da pagina)
- endpoints HTTP de snapshot/historico (quando usados)

## 3) Campos relevantes por rack

Usados no frontend:

- `label`
- `is_real`
- `temp_hot`
- `temp_liquid`
- `heat_pwm`
- `heater_on`
- `anomaly`
- `status`
- `target_heat_pwm`

Campos legados preservados por compatibilidade visual:

- `fan_pwm` (0 em racks reais no baseline atual)
- `target_fan_pwm` (0)

## 4) Campos relevantes de CDU

- `fanA_pwm`
- `fanB_pwm`
- `peltierA_on`
- `peltierB_on`
- `t_supply_A`
- `t_supply_B`
- `cmd_fanA_pwm`
- `cmd_fanB_pwm`
- `t_supply_target`

Nota: a ventoinha do dissipador de cada Peltier nao e reportada separadamente ao servidor,
porque segue por hardware o mesmo ramo de potencia do modulo Peltier respetivo.

## 5) Semantica visual recomendada

- racks reais (`R00`, `R07`) com badge `REAL`
- racks sinteticos com badge `MODEL`
- mapa de cor por `temp_hot`
- alerta visual por `anomaly=true`
- painel CDU separado do painel de racks
- indicar estado Peltier A/B (ligado/desligado) no painel CDU

## 6) Alinhamento com arquitetura atual

No frontend, cooling de rack nao e mostrado como atuacao fisica local.
A atuacao fisica de cooling esta concentrada no CDU.
O `handleTwinMessage` tem null guard em `payload.racks` — mensagens sem esse campo
nao causam crash.

## 7) Validacao

Checklist:

- confirmar que `R00` e `R07` entram como `is_real=true`
- confirmar racks restantes como sinteticos
- confirmar fanA/fanB do CDU variam com carga termica
- confirmar racks mostram `target_heat_pwm` coerente
- confirmar peltierA_on muda para true quando supply excede setpoint + 3 deg C
- confirmar ligacao WS usa `ws://` em HTTP e `wss://` em HTTPS
