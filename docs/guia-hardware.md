# Guia de Hardware e Ligacoes

Estado atual do projeto:

- `R00` e `R07` usam `NodeMCU / ESP8266 (ESP-12E)`
- cada rack tem `1x DS18B20` e `1x resistencia 100 ohm`
- o `CDU` usa `ESP32-C6` com `fanA`, `fanB`, `peltierA` e `peltierB`
- cada ventoinha de dissipador da Peltier segue o mesmo ramo comutado do respetivo Peltier

## Pinout

### Racks

- `GPIO4` -> `DS18B20 DQ`
- `3V3` -> `DS18B20 VDD`
- `GND` -> `DS18B20 GND`
- `4.7k` entre `3V3` e `DQ`
- `GPIO5` -> `IN/SIG` do driver low-side do heater

### CDU

- `GPIO6` -> `fanA`
- `GPIO7` -> `fanB`
- `GPIO18` -> `peltierA`
- `GPIO19` -> `peltierB`

## Potencia

```text
+12V PSU -> heater R00 (+)
+12V PSU -> heater R07 (+)
+12V PSU -> fanA (+)
+12V PSU -> fanB (+)
+12V PSU -> XL4015 A IN+
+12V PSU -> XL4015 B IN+
+12V PSU -> peltier fan A (+)
+12V PSU -> peltier fan B (+)
```

Ligacoes low-side:

```text
heater (-) -> driver heater rack -> GND
fanA (-)   -> IRLZ44N #1 -> GND
fanB (-)   -> IRLZ44N #2 -> GND
XL4015 A IN- + peltier fan A (-) -> IRLZ44N #3 -> GND
XL4015 B IN- + peltier fan B (-) -> IRLZ44N #4 -> GND
```

## Regras importantes

- todos os `GND` ficam em comum
- as racks so aquecem e medem
- o `CDU` faz todo o cooling fisico
- `t_liquid` passa a ser estimada no servidor quando nao existe segunda sonda
- os `XL4015` devem ser ajustados para `~2.0V` antes de ligar os Peltiers

## Checklist rapido

- confirmar `ONE_WIRE_PIN=4` e `HEAT_PIN=5`
- confirmar `CDU_FAN_A_PIN=6`, `CDU_FAN_B_PIN=7`
- confirmar `CDU_PELTIER_A_PIN=18`, `CDU_PELTIER_B_PIN=19`
- confirmar pull-up `4.7k` no `DS18B20`
- confirmar `GND` comum entre PSU, racks, CDU e drivers
