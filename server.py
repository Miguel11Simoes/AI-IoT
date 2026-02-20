#!/usr/bin/env python3
import argparse
import csv
import json
import socket
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple

try:
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover
    np = None

try:
    from sklearn.ensemble import IsolationForest  # type: ignore
except ImportError:  # pragma: no cover
    IsolationForest = None


@dataclass
class NodeSnapshot:
    payload: dict
    received_ts: float


class AnomalyDetector:
    def __init__(
        self,
        contamination: float = 0.05,
        warmup_samples: int = 50,
        retrain_every: int = 10,
        detector_mode: str = "zscore",
    ):
        self.contamination = contamination
        self.warmup_samples = warmup_samples
        self.retrain_every = retrain_every
        self.detector_mode = detector_mode
        self.buffer: Deque[List[float]] = deque(maxlen=400)
        self.samples_since_train = 0
        self.model = None
        self.model_ready = False
        self.training = False
        self.lock = threading.Lock()
        self.ai_enabled = detector_mode == "iforest" and IsolationForest is not None and np is not None

    def detect(self, features: List[float]) -> Tuple[bool, str]:
        with self.lock:
            self.buffer.append(features)
            buffer_len = len(self.buffer)

        if buffer_len < self.warmup_samples:
            return False, "warmup"

        if self.detector_mode == "zscore":
            return self._detect_with_zscore(features), "zscore"

        self._schedule_training_if_needed()

        if self.ai_enabled and self.model_ready:
            with self.lock:
                model = self.model
                self.samples_since_train += 1
            if model is not None:
                try:
                    pred = model.predict([features])[0]
                    return pred == -1, "isolation_forest"
                except Exception:
                    return self._detect_with_zscore(features), "zscore_recover"

        return self._detect_with_zscore(features), "zscore_fallback"

    def _schedule_training_if_needed(self) -> None:
        if not self.ai_enabled:
            return

        with self.lock:
            if self.training:
                return
            if self.model_ready and self.samples_since_train < self.retrain_every:
                return
            samples = [row[:] for row in self.buffer]
            self.training = True

        t = threading.Thread(target=self._train_worker, args=(samples,), daemon=True)
        t.start()

    def _train_worker(self, samples: List[List[float]]) -> None:
        try:
            max_samples = min(len(samples), 128)
            model = IsolationForest(
                contamination=self.contamination,
                random_state=42,
                n_estimators=30,
                max_samples=max_samples,
                n_jobs=1,
            )
            model.fit(np.asarray(samples, dtype=float))
            with self.lock:
                self.model = model
                self.model_ready = True
                self.samples_since_train = 0
        except Exception:
            with self.lock:
                self.model_ready = False
        finally:
            with self.lock:
                self.training = False

    def _detect_with_zscore(self, features: List[float]) -> bool:
        with self.lock:
            columns = list(zip(*self.buffer))
        for idx, value in enumerate(features):
            col = columns[idx]
            mean_val = statistics.fmean(col)
            std_val = statistics.pstdev(col) or 1e-6
            z = abs((value - mean_val) / std_val)
            if z > 3.2:
                return True
        return False


class CooperativeServer:
    def __init__(
        self,
        host: str,
        port: int,
        stale_seconds: float,
        log_path: Path,
        detector: AnomalyDetector,
    ):
        self.host = host
        self.port = port
        self.stale_seconds = stale_seconds
        self.log_path = log_path
        self.detector = detector
        self.state_lock = threading.Lock()
        self.global_state: Dict[str, NodeSnapshot] = {}
        self.log_lock = threading.Lock()
        self._ensure_log_file()

    def _ensure_log_file(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if self.log_path.exists():
            return
        with self.log_path.open("w", newline="", encoding="utf-8") as fp:
            writer = csv.writer(fp)
            writer.writerow(
                [
                    "ts",
                    "node",
                    "t_hot",
                    "t_liquid",
                    "fan_pwm",
                    "pump_pwm",
                    "global_avg_hot",
                    "target_fan_pwm",
                    "target_pump_pwm",
                    "anomaly",
                    "detector",
                    "mode",
                ]
            )

    def serve_forever(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(16)
        print(f"[server] listening on {self.host}:{self.port}", flush=True)
        if not self.detector.ai_enabled and self.detector.detector_mode == "iforest":
            print(
                "[server] iforest requested but dependencies are missing, fallback to zscore",
                flush=True,
            )
        print(f"[server] detector mode: {self.detector.detector_mode}", flush=True)
        try:
            while True:
                conn, addr = sock.accept()
                t = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                t.start()
        except KeyboardInterrupt:
            print("\n[server] shutdown requested", flush=True)
        finally:
            sock.close()

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        with conn:
            try:
                conn.settimeout(2.0)
                raw_line = self._recv_line(conn)
                if not raw_line:
                    try:
                        conn.sendall(b"{\"ok\":false,\"error\":\"empty_payload\"}\n")
                    except Exception:
                        pass
                    return

                try:
                    message = json.loads(raw_line)
                    parsed = self._parse_message(message)
                except Exception as exc:
                    response = {"ok": False, "error": f"invalid payload: {exc}"}
                    conn.sendall((json.dumps(response) + "\n").encode("utf-8"))
                    return

                node_id = parsed["id"]
                now = time.time()
                with self.state_lock:
                    self.global_state[node_id] = NodeSnapshot(payload=parsed, received_ts=now)
                    active = self._active_nodes_locked(now)
                    global_avg_hot = self._compute_global_avg_hot(active)

                features = [
                    parsed["t_hot"],
                    parsed["t_liquid"],
                    parsed["fan_pwm"],
                    parsed["pump_pwm"],
                    parsed["virtual_flow"],
                ]
                ai_anomaly, detector_name = self.detector.detect(features)
                local_anomaly = bool(parsed.get("local_anomaly", False))
                anomaly = ai_anomaly or local_anomaly

                target_fan, target_pump, mode = self._compute_setpoints(parsed, global_avg_hot, anomaly)
                response = {
                    "ok": True,
                    "target_fan_pwm": target_fan,
                    "target_pump_pwm": target_pump,
                    "global_avg_hot": round(global_avg_hot, 3),
                    "anomaly": anomaly,
                    "detector": detector_name,
                    "mode": mode,
                    "server_time_ms": int(now * 1000),
                }
                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))

                self._append_log(
                    node=node_id,
                    t_hot=parsed["t_hot"],
                    t_liquid=parsed["t_liquid"],
                    fan_pwm=parsed["fan_pwm"],
                    pump_pwm=parsed["pump_pwm"],
                    global_avg_hot=global_avg_hot,
                    target_fan=target_fan,
                    target_pump=target_pump,
                    anomaly=anomaly,
                    detector=detector_name,
                    mode=mode,
                )

                print(
                    f"[rx] node={node_id} t_hot={parsed['t_hot']:.2f} "
                    f"t_liquid={parsed['t_liquid']:.2f} avg={global_avg_hot:.2f} "
                    f"fan={target_fan} pump={target_pump} anomaly={anomaly} ({detector_name})",
                    flush=True,
                )
            except Exception as exc:
                fallback = {
                    "ok": False,
                    "target_fan_pwm": 255,
                    "target_pump_pwm": 255,
                    "global_avg_hot": 0.0,
                    "anomaly": True,
                    "mode": "server_error",
                    "error": str(exc),
                }
                try:
                    conn.sendall((json.dumps(fallback) + "\n").encode("utf-8"))
                except Exception:
                    pass
                print(f"[server] handler error from {addr}: {exc}", flush=True)

    def _parse_message(self, message: dict) -> dict:
        node_id = str(message["id"]).strip()
        if not node_id:
            raise ValueError("missing id")

        parsed = {
            "id": node_id,
            "cycle": int(message.get("cycle", 0)),
            "uptime_ms": int(message.get("uptime_ms", 0)),
            "t_hot": float(message["t_hot"]),
            "t_liquid": float(message["t_liquid"]),
            "fan_pwm": int(message.get("fan_pwm", 0)),
            "pump_pwm": int(message.get("pump_pwm", 0)),
            "virtual_flow": float(message.get("virtual_flow", 0.0)),
            "sensor_ok": bool(message.get("sensor_ok", True)),
            "sim_mode": bool(message.get("sim_mode", False)),
            "local_anomaly": bool(message.get("local_anomaly", False)),
        }
        return parsed

    def _active_nodes_locked(self, now: float) -> Dict[str, NodeSnapshot]:
        active = {}
        stale_keys: List[str] = []
        for node_id, snap in self.global_state.items():
            if now - snap.received_ts <= self.stale_seconds:
                active[node_id] = snap
            else:
                stale_keys.append(node_id)
        for key in stale_keys:
            self.global_state.pop(key, None)
        return active

    @staticmethod
    def _compute_global_avg_hot(active: Dict[str, NodeSnapshot]) -> float:
        if not active:
            return 0.0
        values = [snap.payload["t_hot"] for snap in active.values()]
        return float(sum(values) / len(values))

    @staticmethod
    def _compute_setpoints(parsed: dict, global_avg_hot: float, anomaly: bool) -> Tuple[int, int, str]:
        if anomaly:
            return 255, 255, "anomaly_guard"

        t_hot = parsed["t_hot"]
        t_liquid = parsed["t_liquid"]
        delta = t_hot - t_liquid
        temp_error = max(0.0, t_hot - 35.0)
        global_error = max(0.0, global_avg_hot - 42.0)

        fan = 85 + temp_error * 4.2 + delta * 2.4 + global_error * 1.8
        pump = 75 + temp_error * 3.6 + delta * 1.8 + global_error * 2.3

        imbalance = t_hot - global_avg_hot
        if imbalance > 2.0:
            fan += 24
            pump += 20
        elif imbalance < -2.0:
            fan -= 12
            pump -= 10

        fan = max(70, min(255, int(fan)))
        pump = max(60, min(255, int(pump)))
        return fan, pump, "cooperative"

    def _append_log(
        self,
        node: str,
        t_hot: float,
        t_liquid: float,
        fan_pwm: int,
        pump_pwm: int,
        global_avg_hot: float,
        target_fan: int,
        target_pump: int,
        anomaly: bool,
        detector: str,
        mode: str,
    ) -> None:
        with self.log_lock:
            with self.log_path.open("a", newline="", encoding="utf-8") as fp:
                writer = csv.writer(fp)
                writer.writerow(
                    [
                        int(time.time() * 1000),
                        node,
                        f"{t_hot:.4f}",
                        f"{t_liquid:.4f}",
                        fan_pwm,
                        pump_pwm,
                        f"{global_avg_hot:.4f}",
                        target_fan,
                        target_pump,
                        int(anomaly),
                        detector,
                        mode,
                    ]
                )

    @staticmethod
    def _recv_line(conn: socket.socket, max_bytes: int = 4096) -> str:
        data = bytearray()
        while len(data) < max_bytes:
            try:
                chunk = conn.recv(min(512, max_bytes - len(data)))
            except socket.timeout:
                break
            if not chunk:
                break
            line_break = chunk.find(b"\n")
            if line_break >= 0:
                data.extend(chunk[:line_break])
                break
            data.extend(chunk)
        return data.decode("utf-8", errors="replace").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-IoT cooperative cooling server")
    parser.add_argument("--host", default="0.0.0.0", help="bind interface")
    parser.add_argument("--port", default=5000, type=int, help="TCP port")
    parser.add_argument("--stale-seconds", default=8.0, type=float, help="node timeout window")
    parser.add_argument("--log-path", default="logs/telemetry_log.csv", help="csv output file")
    parser.add_argument("--contamination", default=0.05, type=float, help="anomaly contamination rate")
    parser.add_argument("--warmup-samples", default=50, type=int, help="samples before anomaly detection")
    parser.add_argument(
        "--detector",
        default="zscore",
        choices=["zscore", "iforest"],
        help="anomaly detector algorithm",
    )
    args = parser.parse_args()

    detector = AnomalyDetector(
        contamination=args.contamination,
        warmup_samples=args.warmup_samples,
        detector_mode=args.detector,
    )
    server = CooperativeServer(
        host=args.host,
        port=args.port,
        stale_seconds=args.stale_seconds,
        log_path=Path(args.log_path),
        detector=detector,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
