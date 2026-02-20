#!/usr/bin/env python3
import argparse
import json
import random
import socket
import time
from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class NodeModel:
    node_id: str
    base_heat: float
    t_hot: float
    t_liquid: float
    fan_pwm: int
    pump_pwm: int
    anomaly_after: Optional[float] = None
    cooling_fault_scale: float = 1.0
    anomaly_applied: bool = False

    def step(self, dt: float, elapsed: float) -> None:
        if self.anomaly_after is not None and (not self.anomaly_applied) and elapsed >= self.anomaly_after:
            self.cooling_fault_scale = 0.6
            self.base_heat += 0.6
            self.anomaly_applied = True

        fan = self.fan_pwm / 255.0
        flow = self.pump_pwm / 255.0
        noise = random.uniform(-0.04, 0.04)

        hot_minus_liquid = self.t_hot - self.t_liquid
        hot_minus_ambient = self.t_hot - 26.0
        liquid_minus_ambient = self.t_liquid - 26.0

        heat_gain = self.base_heat + noise
        hot_to_liquid = 0.22 * hot_minus_liquid
        hot_to_ambient = 0.03 * (0.2 + fan * self.cooling_fault_scale) * hot_minus_ambient
        flow_cooling = 0.24 * flow * self.cooling_fault_scale * hot_minus_liquid
        liquid_to_ambient = 0.11 * (0.2 + fan * self.cooling_fault_scale) * liquid_minus_ambient

        d_hot = heat_gain - hot_to_ambient - hot_to_liquid - (0.45 * flow_cooling)
        d_liquid = hot_to_liquid + flow_cooling - liquid_to_ambient

        self.t_hot += d_hot * dt
        self.t_liquid += d_liquid * dt

        if self.t_liquid >= self.t_hot:
            self.t_liquid = self.t_hot - 0.1

        self.t_hot = max(20.0, min(130.0, self.t_hot))
        self.t_liquid = max(20.0, min(120.0, self.t_liquid))

    def telemetry(self, cycle: int, uptime_ms: int) -> dict:
        return {
            "id": self.node_id,
            "cycle": cycle,
            "uptime_ms": uptime_ms,
            "t_hot": round(self.t_hot, 3),
            "t_liquid": round(self.t_liquid, 3),
            "fan_pwm": int(self.fan_pwm),
            "pump_pwm": int(self.pump_pwm),
            "virtual_flow": round(self.pump_pwm / 255.0, 4),
            "sensor_ok": True,
            "sim_mode": True,
            "local_anomaly": False,
            "network_ok": True,
        }

    def apply_command(self, response: dict) -> None:
        self.fan_pwm = int(max(0, min(255, response.get("target_fan_pwm", self.fan_pwm))))
        self.pump_pwm = int(max(0, min(255, response.get("target_pump_pwm", self.pump_pwm))))


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
            response_line = recv_line(conn)
            if not response_line:
                return False, {}, "empty response"
            return True, json.loads(response_line), ""
    except Exception as exc:
        return False, {}, str(exc)


def run_simulation(nodes, host: str, port: int, interval_s: float, duration_s: float) -> None:
    started = time.time()
    next_tick = started
    cycle = 0

    while True:
        now = time.time()
        elapsed = now - started
        if elapsed >= duration_s:
            break
        if now < next_tick:
            time.sleep(min(0.02, next_tick - now))
            continue

        for model in nodes:
            model.step(interval_s, elapsed)
            payload = model.telemetry(cycle=cycle, uptime_ms=int(elapsed * 1000))
            ok, response, error = send_once(host, port, payload)
            if ok:
                model.apply_command(response)
                mode = response.get("mode", "n/a")
                anomaly = response.get("anomaly", False)
                avg = response.get("global_avg_hot", 0.0)
                print(
                    f"[{model.node_id}] cycle={cycle:04d} "
                    f"T_hot={model.t_hot:6.2f} T_liq={model.t_liquid:6.2f} "
                    f"fan={model.fan_pwm:3d} pump={model.pump_pwm:3d} "
                    f"avg={avg:6.2f} mode={mode} anomaly={anomaly}"
                )
            else:
                print(f"[{model.node_id}] cycle={cycle:04d} network error ({error})")

        cycle += 1
        next_tick += interval_s


def main() -> None:
    parser = argparse.ArgumentParser(description="Software-only simulator for AI-IoT nodes")
    parser.add_argument("--host", default="127.0.0.1", help="server host")
    parser.add_argument("--port", default=5000, type=int, help="server port")
    parser.add_argument("--interval", default=1.0, type=float, help="telemetry interval in seconds")
    parser.add_argument("--duration", default=120.0, type=float, help="simulation duration in seconds")
    parser.add_argument(
        "--inject-anomaly-after",
        default=45.0,
        type=float,
        help="seconds after start to inject cooling fault into node B",
    )
    args = parser.parse_args()

    node_a = NodeModel(node_id="A", base_heat=2.8, t_hot=39.0, t_liquid=33.0, fan_pwm=120, pump_pwm=110)
    node_b = NodeModel(
        node_id="B",
        base_heat=3.0,
        t_hot=41.0,
        t_liquid=34.5,
        fan_pwm=130,
        pump_pwm=120,
        anomaly_after=args.inject_anomaly_after,
    )

    run_simulation([node_a, node_b], args.host, args.port, args.interval, args.duration)
    print("simulation complete")


if __name__ == "__main__":
    main()
