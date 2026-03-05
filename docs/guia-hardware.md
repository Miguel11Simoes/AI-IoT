# Guia de Hardware e Ligacoes (AI-IoT)

Este guia foi montado a partir do firmware e da configuracao atual do projeto:

- `platformio.ini`
- `include/ProjectConfig.h`
- `lib/control/src/Control.cpp`
- `lib/sensors/src/Sensors.cpp`
- `src/main.cpp`

## 1) Escopo hardware-ready

Topologia alvo do projeto:

- 2 racks reais: `R00` e `R07` (ESP32-DEVKITC-V4)
- 1 CDU real: `CDU1` (ESP32-C6 DevKitC-1)
- servidor central via Wi-Fi WebSocket

## 2) Pinout oficial (estado atual)

### 2.1 Racks `rack_r00` e `rack_r07` (ESP32-DEVKITC-V4)

Pinos definidos em `platformio.ini`:

- `ONE_WIRE_PIN = GPIO4`
- `FAN_PIN = GPIO17`
- `HEAT_PIN = GPIO18`
- `PUMP_PIN = GPIO16`

### 2.2 CDU `cdu_esp32c6` (ESP32-C6)

Pinos definidos em `platformio.ini`:

- `CDU_FAN_A_PIN = GPIO4`
- `CDU_FAN_B_PIN = GPIO5`

## 3) Esboco global de ligacoes

```text
                        Wi-Fi WS (porta 8765)

   +-------------------+      +-------------------+      +--------------------+
   | Rack R00 (ESP32)  |      | Rack R07 (ESP32)  |      | CDU1 (ESP32-C6)    |
   | DS18B20 + atuacao |      | DS18B20 + atuacao |      | fanA + fanB zonas  |
   +---------+---------+      +---------+---------+      +---------+----------+
             \                        |                           /
              \                       |                          /
               +----------------------+-------------------------+
                                      |
                              +-------+-------+
                              |   server.py   |
                              | (PC/RPi host) |
                              +---------------+
```

```text
                    Alimentacao 12V (com GND comum em estrela)

                       +-------------------+
                       | PSU 12V / 5A      |
                       +----+---------+----+
                            |         |
                           +12V      GND -----------------------------+
                            |                                         |
          +-----------------+--------------------+                    |
          |                 |                    |                    |
      Heaters 12V       Drivers FAN/PUMP      Drivers CDU         ESP32 GND
       (R00/R07)          (R00/R07)            (A/B)             ESP32-C6 GND
          |                 |                    |                    |
          +-----------------+--------------------+--------------------+
                                   (todos no mesmo GND)
```

## 4) Ligacoes detalhadas por no

## 4.1 Rack R00 (igual para R07)

### Sinais de controlo e sensor

```text
ESP32 R00/R07                    Dispositivo
---------------------------------------------------------------
GPIO4   (ONE_WIRE_PIN)      ->   DS18B20 DQ
3V3                          ->   DS18B20 VDD
GND                          ->   DS18B20 GND
3V3 --[4.7k]--+              ->   pull-up no barramento 1-Wire
              +---- GPIO4

GPIO17 (FAN_PIN)             ->   IN/PWM do driver da ventoinha local
GPIO16 (PUMP_PIN)            ->   IN/PWM do driver da bomba local
GPIO18 (HEAT_PIN)            ->   IN/SIG do modulo IRF520 (heater)
GND ESP32                    ->   GND dos drivers/modulos
```

### Caminho de potencia do heater (IRF520 em low-side)

```text
+12V PSU  ----->  Heater (+)
Heater (-) ----->  IRF520 DRAIN/OUT
IRF520 SOURCE/GND -----> GND PSU
ESP32 GPIO18 -----> IRF520 IN/SIG
ESP32 GND   -----> IRF520 GND
```

Notas:

- O firmware nao usa PWM rapido no heater. Usa time-proportioning em janela de 2s (`HEAT_WINDOW_MS=2000`).
- Manter GND comum entre ESP32, IRF520 e fonte 12V.

## 4.2 CDU1 (ESP32-C6)

```text
ESP32-C6 CDU1                    Dispositivo
---------------------------------------------------------------
GPIO4  (CDU_FAN_A_PIN)      ->   IN/PWM do driver DFR0332 zona A
GPIO5  (CDU_FAN_B_PIN)      ->   IN/PWM do driver DFR0332 zona B
GND                          ->   GND comum dos drivers
12V PSU                      ->   alimentacao dos drivers/fans (lado potencia)
```

## 5) Esboco completo de todas as ligacoes (resumo)

```text
RACK R00 (ESP32)                             RACK R07 (ESP32)
-----------------                            -----------------
GPIO4  -> DS18B20 DQ                         GPIO4  -> DS18B20 DQ
3V3/GND -> DS18B20 VDD/GND                   3V3/GND -> DS18B20 VDD/GND
GPIO17 -> Driver FAN IN/PWM                  GPIO17 -> Driver FAN IN/PWM
GPIO16 -> Driver PUMP IN/PWM                 GPIO16 -> Driver PUMP IN/PWM
GPIO18 -> IRF520 IN/SIG                      GPIO18 -> IRF520 IN/SIG
GND    -> drivers/IRF520 GND                 GND    -> drivers/IRF520 GND

PSU +12V -> heater(+), fan drivers, pump drivers, CDU fan drivers
PSU GND  -> ESP32 GND, ESP32-C6 GND, IRF520 GND, drivers GND (comum)

CDU1 (ESP32-C6)
---------------
GPIO4 -> DFR0332 A IN/PWM -> Fans zona A
GPIO5 -> DFR0332 B IN/PWM -> Fans zona B
GND   -> GND comum
```

## 6) Checklist de validacao eletrica (antes de ligar)

- Confirmar `ONE_WIRE_PIN=4`, `FAN_PIN=17`, `HEAT_PIN=18`, `PUMP_PIN=16`.
- Confirmar `CDU_FAN_A_PIN=4`, `CDU_FAN_B_PIN=5`.
- Confirmar resistor pull-up `4.7k` entre `3V3` e `DQ` do DS18B20.
- Confirmar todos os GNDs em comum (fonte + ESP32 + ESP32-C6 + modulos).
- Confirmar polaridade da fonte 12V e ausencia de curto entre `+12V` e `GND`.
- Confirmar heater no ramo low-side do IRF520 (nao ligar heater direto ao GPIO).

## 7) Notas praticas

- Se o rack estiver com `SIMULATED_COOLING=0` (estado atual), o DS18B20 deve estar ligado e funcional.
- Se houver apenas 1 DS18B20 por rack, o firmware estima `T_liquid` automaticamente.
- Para fan/pump locais, usar sempre driver de potencia apropriado (nao ligar carga 12V direto ao GPIO).
