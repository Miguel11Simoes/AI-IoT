#!/usr/bin/env python3
import argparse
import json
import random
import socket
import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class RackModel:
    rack_id: str
    base_heat: float
    t_hot: float
    t_liquid: float
    fan_pwm: int
    heat_pwm: int
    anomaly_after: Optional[float] = None
    fault_scale: float = 1.0
    anomaly_applied: bool = False

    def step(self, dt: float, elapsed: float, supply: float) -> None:
        if self.anomaly_after is not None and (not self.anomaly_applied) and elapsed >= self.anomaly_after:
            self.fault_scale = 0.6
            self.base_heat += 0.8
            self.anomaly_applied = True

        fan = self.fan_pwm / 255.0
        heat = self.heat_pwm / 255.0

        noise = random.uniform(-0.03, 0.03)
        hot_minus_liquid = self.t_hot - self.t_liquid
        hot_minus_supply = self.t_hot - supply

        heat_gain = self.base_heat * (0.45 + heat * 1.2) + noise
        hot_to_liquid = 0.22 * hot_minus_liquid
        forced_reject = (0.05 + 0.25 * fan) * self.fault_scale * hot_minus_supply

        d_hot = heat_gain - hot_to_liquid - forced_reject
        d_liquid = hot_to_liquid - 0.08 * (self.t_liquid - supply)

        self.t_hot += d_hot * dt
        self.t_liquid += d_liquid * dt

        if self.t_liquid >= self.t_hot:
            self.t_liquid = self.t_hot - 0.1

        self.t_hot = max(20.0, min(120.0, self.t_hot))
        self.t_liquid = max(20.0, min(110.0, self.t_liquid))

    def telemetry(self, now_ms: int) -> dict:
        heater_rated_power_w = 20.0
        return {
            "type": "rack_telemetry",
            "id": self.rack_id,
            "t_hot_real_c": round(self.t_hot, 3),
            "t_liquid_real_c": round(self.t_liquid, 3),
            "t_hot_source": "simulated",
            "t_liquid_source": "simulated",
            "telemetry_mode": "simulated",
            "sensor_ok": True,
            "t_hot": round(self.t_hot, 3),
            "t_liquid": round(self.t_liquid, 3),
            "fan_local_pwm": int(self.fan_pwm),
            "heat_pwm": int(self.heat_pwm),
            "heater_on": bool(self.heat_pwm > 0),
            "heater_rated_power_w": heater_rated_power_w,
            "heater_avg_power_w": round(heater_rated_power_w * (self.heat_pwm / 255.0), 3),
            "rssi": -48 if self.rack_id == "R00" else -53,
            "local_anomaly": False,
            "ts": now_ms,
        }

    def apply_command(self, response: dict) -> None:
        self.fan_pwm = int(max(0, min(255, response.get("fan_local_pwm", response.get("target_fan_pwm", self.fan_pwm)))))
        self.heat_pwm = int(max(0, min(255, response.get("heat_pwm", response.get("target_heat_pwm", self.heat_pwm)))))


@dataclass
class CduModel:
    cdu_id: str
    fanA_pwm: int = 150
    fanB_pwm: int = 150
    peltierA_on: bool = False
    peltierB_on: bool = False
    t_supply_A: float = 29.5
    t_supply_B: float = 30.0

    def step(self, dt: float) -> None:
        cool_a = (self.fanA_pwm / 255.0) * 1.9 + (0.95 if self.peltierA_on else 0.0)
        cool_b = (self.fanB_pwm / 255.0) * 1.9 + (0.95 if self.peltierB_on else 0.0)
        self.t_supply_A += (1.35 - cool_a) * 0.11 * dt
        self.t_supply_B += (1.35 - cool_b) * 0.11 * dt
        self.t_supply_A = max(22.0, min(45.0, self.t_supply_A))
        self.t_supply_B = max(22.0, min(45.0, self.t_supply_B))

    def telemetry(self, now_ms: int) -> dict:
        return {
            "type": "cdu_telemetry",
            "id": self.cdu_id,
            "fanA_pwm": int(self.fanA_pwm),
            "fanB_pwm": int(self.fanB_pwm),
            "peltierA_on": bool(self.peltierA_on),
            "peltierB_on": bool(self.peltierB_on),
            "t_supply_A": round(self.t_supply_A, 3),
            "t_supply_B": round(self.t_supply_B, 3),
            "ts": now_ms,
        }

    def apply_command(self, response: dict) -> None:
        self.fanA_pwm = int(max(0, min(255, response.get("fanA_pwm", self.fanA_pwm))))
        self.fanB_pwm = int(max(0, min(255, response.get("fanB_pwm", self.fanB_pwm))))
        self.peltierA_on = bool(response.get("peltierA_on", self.peltierA_on))
        self.peltierB_on = bool(response.get("peltierB_on", self.peltierB_on))


def recv_line(conn: socket.socket, timeout_s: float = 3.0) -> str:
    conn.settimeout(timeout_s)
    data = bytearray()
    while True:
        chunk = conn.recv(1)
        if not chunk:
            break
        if chunk == b"\n":
            break
        data.extend(chunk)
    return data.decode("utf-8", errors="replace").strip()


def send_once(host: str, port: int, payload: dict) -> Tuple[bool, dict, str]:
    try:
        with socket.create_connection((host, port), timeout=3.0) as conn:
            conn.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            line = recv_line(conn)
            if not line:
                return False, {}, "empty response"
            response = json.loads(line)
            if isinstance(response, dict) and response.get("ok") is False:
                return False, response, str(response.get("error", "server rejected request"))
            return True, response, ""
    except Exception as exc:
        return False, {}, str(exc)


def run_simulation(host: str, port: int, interval_s: float, duration_s: float, anomaly_after: float) -> None:
    rack_a = RackModel("R00", base_heat=2.7, t_hot=40.0, t_liquid=34.0, fan_pwm=130, heat_pwm=150)
    rack_b = RackModel("R07", base_heat=3.1, t_hot=42.0, t_liquid=35.5, fan_pwm=138, heat_pwm=156, anomaly_after=anomaly_after)
    cdu = CduModel("CDU1")

    start = time.time()
    tick = start
    cycle = 0
    while True:
        now = time.time()
        elapsed = now - start
        if elapsed >= duration_s:
            break
        if now < tick:
            time.sleep(min(0.02, tick - now))
            continue

        dt = interval_s
        cdu.step(dt)
        rack_a.step(dt, elapsed, cdu.t_supply_A)
        rack_b.step(dt, elapsed, cdu.t_supply_B)

        now_ms = int(now * 1000)
        for rack in (rack_a, rack_b):
            ok, response, error = send_once(host, port, rack.telemetry(now_ms))
            if ok:
                rack.apply_command(response)
                print(
                    f"[{rack.rack_id}] cycle={cycle:04d} hot={rack.t_hot:6.2f} "
                    f"liq={rack.t_liquid:6.2f} fan={rack.fan_pwm:3d} heat={rack.heat_pwm:3d}"
                )
            else:
                print(f"[{rack.rack_id}] cycle={cycle:04d} network error ({error})")

        ok, response, error = send_once(host, port, cdu.telemetry(now_ms))
        if ok:
            cdu.apply_command(response)
            print(
                f"[CDU] cycle={cycle:04d} fanA={cdu.fanA_pwm:3d} fanB={cdu.fanB_pwm:3d} "
                f"peltierA={int(cdu.peltierA_on)} peltierB={int(cdu.peltierB_on)} "
                f"supplyA={cdu.t_supply_A:5.2f} supplyB={cdu.t_supply_B:5.2f}"
            )
        else:
            print(f"[CDU] cycle={cycle:04d} network error ({error})")

        cycle += 1
        tick += interval_s


def main() -> None:
    parser = argparse.ArgumentParser(description="Software-only simulator for 2 racks + CDU")
    parser.add_argument("--host", default="127.0.0.1", help="server host")
    parser.add_argument("--port", default=5000, type=int, help="server port")
    parser.add_argument("--interval", default=1.0, type=float, help="telemetry interval in seconds")
    parser.add_argument("--duration", default=120.0, type=float, help="simulation duration in seconds")
    parser.add_argument("--inject-anomaly-after", default=45.0, type=float, help="seconds before rack R07 fault")
    args = parser.parse_args()

    run_simulation(args.host, args.port, args.interval, args.duration, args.inject_anomaly_after)
    print("simulation complete")


if __name__ == "__main__":
    main()
