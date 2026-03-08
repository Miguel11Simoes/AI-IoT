
#!/usr/bin/env python3
import argparse
import asyncio
import json
import math
import mimetypes
import re
import socket
import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

try:
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover
    np = None

try:
    from sklearn.ensemble import IsolationForest  # type: ignore
except ImportError:  # pragma: no cover
    IsolationForest = None

try:
    from websockets.asyncio.server import serve as ws_serve  # type: ignore
    from websockets.exceptions import ConnectionClosed  # type: ignore
except ImportError:  # pragma: no cover
    try:
        from websockets.server import serve as ws_serve  # type: ignore
        from websockets.exceptions import ConnectionClosed  # type: ignore
    except ImportError:  # pragma: no cover
        ws_serve = None
        ConnectionClosed = Exception


def safe_log(message: str) -> None:
    try:
        print(message, flush=True)
    except OSError:
        pass


def clamp(value: float, min_v: float, max_v: float) -> float:
    return max(min_v, min(max_v, value))


def clamp_pwm(value: float, min_v: int = 0, max_v: int = 255) -> int:
    return int(clamp(float(value), float(min_v), float(max_v)))


class AnomalyDetector:
    def __init__(self, detector_mode: str = "zscore", contamination: float = 0.05, warmup_samples: int = 50):
        self.detector_mode = detector_mode
        self.contamination = contamination
        self.warmup_samples = warmup_samples
        self.buffer: Deque[List[float]] = deque(maxlen=500)
        self.lock = threading.Lock()
        self.model = None
        self.model_ready = False
        self.training = False
        self.ai_enabled = detector_mode == "iforest" and IsolationForest is not None and np is not None

    def detect(self, features: List[float]) -> Tuple[bool, str]:
        with self.lock:
            self.buffer.append(features)
            samples = len(self.buffer)

        if samples < self.warmup_samples:
            return False, "warmup"

        if self.detector_mode == "zscore" or not self.ai_enabled:
            return self._detect_zscore(features), "zscore"

        self._train_async_if_needed()
        if self.model_ready and self.model is not None:
            try:
                return self.model.predict([features])[0] == -1, "isolation_forest"
            except Exception:
                return self._detect_zscore(features), "zscore_fallback"
        return self._detect_zscore(features), "zscore_fallback"

    def _detect_zscore(self, features: List[float]) -> bool:
        with self.lock:
            cols = list(zip(*self.buffer)) if self.buffer else []
        if not cols:
            return False
        for idx, value in enumerate(features):
            col = cols[idx]
            mu = statistics.fmean(col)
            sigma = statistics.pstdev(col) or 1e-6
            if abs((value - mu) / sigma) > 3.2:
                return True
        return False

    def _train_async_if_needed(self) -> None:
        with self.lock:
            if self.training or len(self.buffer) < self.warmup_samples:
                return
            samples = [row[:] for row in self.buffer]
            self.training = True

        def train_worker() -> None:
            try:
                model = IsolationForest(
                    contamination=self.contamination,
                    random_state=42,
                    n_estimators=30,
                    max_samples=min(128, len(samples)),
                    n_jobs=1,
                )
                model.fit(np.asarray(samples, dtype=float))
                with self.lock:
                    self.model = model
                    self.model_ready = True
            except Exception:
                with self.lock:
                    self.model_ready = False
            finally:
                with self.lock:
                    self.training = False

        threading.Thread(target=train_worker, daemon=True).start()


@dataclass
class RackState:
    rack_id: str
    t_hot: float
    t_liquid: float
    fan_pwm: int
    heat_pwm: int
    pump_pwm: int
    rssi: int
    anomaly: bool
    detector: str
    received_ts: float


@dataclass
class CduState:
    cdu_id: str
    fanA_pwm: int
    fanB_pwm: int
    t_supply_A: float
    t_supply_B: float
    received_ts: float

class DigitalTwinCore:
    ROWS = 2
    COLS = 4
    COUNT = 8

    def __init__(self, detector: AnomalyDetector, stale_seconds: float, history_limit: int):
        self.detector = detector
        self.stale_seconds = stale_seconds
        self.history_limit = history_limit

        self.lock = threading.Lock()
        self.started_ts = time.time()
        self.messages_total = 0
        self.anomalies_total = 0

        self.racks_real: Dict[str, RackState] = {}
        self.real_rack_ids = {"R00", "R07"}
        self.cdu_state: Optional[CduState] = None

        self.hot = [55.0] * self.COUNT
        self.liquid = [50.0] * self.COUNT
        self.fan = [0] * self.COUNT
        self.heat = [140] * self.COUNT
        self.pump = [0] * self.COUNT
        self.anomaly = [False] * self.COUNT

        self.supply_A = 29.0
        self.supply_B = 30.0
        self.last_model_ts = time.time()

        self.rack_cmds: Dict[str, dict] = {}
        self.cdu_cmd = {
            "type": "cdu_cmd",
            "id": "CDU1",
            "fanA_pwm": 160,
            "fanB_pwm": 160,
            "fallback_target": "maintain_supply",
            "t_supply_target": 29.5,
        }

        self.global_state = {
            "avg_hot": 0.0,
            "max_hot": 0.0,
            "critical_rack": "R00",
            "critical_temp": 0.0,
            "anomaly_racks": 0,
            "ai_status": "nominal",
            "ai_confidence": 0.6,
            "trend_c_per_min": 0.0,
            "predicted_hot_5m": 0.0,
            "total_cooling_power_kw": 0.0,
            "power_index_kw": 0.0,
            "power_basis": "cluster_total",
            "power_delta_pct_1h": 0.0,
            "power_delta_ready": False,
            "anomaly_risk_pct": 0.0,
            "thermal_stability_pct": 100.0,
            "t_supply_A": self.supply_A,
            "t_supply_B": self.supply_B,
            "fanA_pwm": 160,
            "fanB_pwm": 160,
        }

        self.avg_history: Deque[Tuple[float, float]] = deque(maxlen=1200)
        self.power_history: Deque[Tuple[float, float]] = deque(maxlen=9000)
        self.rack_history: Dict[str, Deque[dict]] = {}

        self.alias = {"A": "R00", "NODE_A": "R00", "B": "R07", "NODE_B": "R07"}

        # Simplified thermal model coefficients
        self.k_heat = 0.020
        self.k_zone_fan = 0.240
        self.k_cool = 0.085
        self.alpha_supply = 0.016
        self.beta_rack = 0.17

    def _idx_to_label(self, idx: int) -> str:
        return f"R{idx:02d}"

    def _label_to_idx(self, label: str) -> Optional[int]:
        m = re.match(r"^R(\d{2})$", label)
        if not m:
            return None
        idx = int(m.group(1))
        return idx if 0 <= idx < self.COUNT else None

    def _zone(self, idx: int) -> str:
        return "A" if idx % self.COLS < 2 else "B"

    def _fresh(self, ts: float, now: float) -> bool:
        return (now - ts) <= self.stale_seconds

    def _normalize_id(self, raw_id: str) -> Optional[str]:
        x = raw_id.strip().upper()
        if not x:
            return None
        if x in self.alias:
            return self.alias[x]
        idx = self._label_to_idx(x)
        if idx is None:
            return None
        return self._idx_to_label(idx)

    @staticmethod
    def _status(temp_hot: float, anomaly: bool) -> str:
        if anomaly or temp_hot >= 75.0:
            return "critical"
        if temp_hot >= 60.0:
            return "warning"
        return "normal"

    def _append_hist(self, rack_id: str, item: dict) -> None:
        q = self.rack_history.setdefault(rack_id, deque(maxlen=self.history_limit))
        q.append(item)

    def _trend(self, now: float) -> float:
        pts = [p for p in self.avg_history if now - p[0] <= 45.0]
        if len(pts) < 6:
            return 0.0
        dt = pts[-1][0] - pts[0][0]
        if dt < 12.0:
            return 0.0
        return float(clamp((pts[-1][1] - pts[0][1]) * 60.0 / dt, -8.0, 8.0))

    def _power_delta(self, now: float, power_kw: float) -> Tuple[float, bool]:
        self.power_history.append((now, power_kw))
        pts = [p for p in self.power_history if now - p[0] <= 3600.0]
        if len(pts) < 2:
            return 0.0, False
        ref_n = max(1, min(len(pts), len(pts) // 4 or 1))
        ref = statistics.fmean(v for _, v in pts[:ref_n])
        if ref <= 0.01:
            return 0.0, False
        return ((power_kw - ref) / ref) * 100.0, len(pts) >= 12

    def _update_model(self, now: float) -> None:
        dt = clamp(now - self.last_model_ts, 0.05, 2.0)
        self.last_model_ts = now

        r00 = self.racks_real.get("R00")
        r07 = self.racks_real.get("R07")
        t00 = r00.t_hot if (r00 and self._fresh(r00.received_ts, now)) else self.hot[0]
        t07 = r07.t_hot if (r07 and self._fresh(r07.received_ts, now)) else self.hot[7]

        if self.cdu_state and self._fresh(self.cdu_state.received_ts, now):
            fanA_meas = self.cdu_state.fanA_pwm
            fanB_meas = self.cdu_state.fanB_pwm
            self.supply_A = clamp(self.cdu_state.t_supply_A, 20.0, 45.0)
            self.supply_B = clamp(self.cdu_state.t_supply_B, 20.0, 45.0)
        else:
            fanA_meas = int(self.cdu_cmd["fanA_pwm"])
            fanB_meas = int(self.cdu_cmd["fanB_pwm"])

        for idx in range(self.COUNT):
            label = self._idx_to_label(idx)
            row, col = divmod(idx, self.COLS)
            w = (row + col / (self.COLS - 1)) / self.ROWS
            field = (1.0 - w) * t00 + w * t07

            real = self.racks_real.get(label)
            if real and self._fresh(real.received_ts, now):
                self.hot[idx] = real.t_hot
                self.liquid[idx] = real.t_liquid
                self.fan[idx] = 0
                self.heat[idx] = real.heat_pwm
                self.pump[idx] = 0
                self.anomaly[idx] = real.anomaly
                continue

            zone_supply = self.supply_A if self._zone(idx) == "A" else self.supply_B
            zone_fan = fanA_meas if self._zone(idx) == "A" else fanB_meas
            q_heat = self.k_heat * self.heat[idx]
            q_rej = self.k_zone_fan * (zone_fan / 255.0) * max(0.0, self.hot[idx] - zone_supply)
            nxt = self.hot[idx] + self.beta_rack * (q_heat - q_rej) * dt + 0.18 * (field - self.hot[idx]) * dt
            self.hot[idx] = clamp(nxt, 25.0, 95.0)
            self.liquid[idx] = clamp(self.hot[idx] - (4.4 + 0.8 * math.sin(now * 0.35 + idx)), 22.0, self.hot[idx] - 0.1)
            self.fan[idx] = 0
            self.pump[idx] = 0
            self.heat[idx] = clamp_pwm(170 - max(0.0, self.hot[idx] - 55.0) * 3.7, 60, 220)
            self.anomaly[idx] = self.hot[idx] >= 75.0

        maxA = max(self.hot[i] for i in range(self.COUNT) if self._zone(i) == "A")
        maxB = max(self.hot[i] for i in range(self.COUNT) if self._zone(i) == "B")
        qinA = sum(self.k_heat * self.heat[i] for i in range(self.COUNT) if self._zone(i) == "A")
        qinB = sum(self.k_heat * self.heat[i] for i in range(self.COUNT) if self._zone(i) == "B")

        self.supply_A = clamp(self.supply_A + self.alpha_supply * (qinA - self.k_cool * fanA_meas) * dt, 22.0, 45.0)
        self.supply_B = clamp(self.supply_B + self.alpha_supply * (qinB - self.k_cool * fanB_meas) * dt, 22.0, 45.0)

        fanA_cmd = clamp_pwm(95 + 5.2 * (maxA - 65.0), 80, 255)
        fanB_cmd = clamp_pwm(95 + 5.2 * (maxB - 65.0), 80, 255)
        if max(self.hot) >= 78.0:
            fanA_cmd = 255
            fanB_cmd = 255

        self.cdu_cmd = {
            "type": "cdu_cmd",
            "id": "CDU1",
            "fanA_pwm": fanA_cmd,
            "fanB_pwm": fanB_cmd,
            "fallback_target": "maintain_supply",
            "t_supply_target": round((self.supply_A + self.supply_B) / 2.0, 2),
        }

        for idx in range(self.COUNT):
            label = self._idx_to_label(idx)
            zone_supply = self.supply_A if self._zone(idx) == "A" else self.supply_B
            t = self.hot[idx]
            guard = self.anomaly[idx] or t >= 75.0
            fan_cmd = 0
            pump_cmd = 0
            heat_cmd = clamp_pwm(180 - 4.5 * (t - 55.0), 60, 220)
            if guard:
                heat_cmd = 80
            self.rack_cmds[label] = {
                "type": "rack_cmd",
                "id": label,
                "fan_local_pwm": fan_cmd,
                "heat_pwm": heat_cmd,
                "pump_v": pump_cmd,
                "mode": "guard" if guard else "heat-only-co-op",
                "anomaly": guard,
            }

        avg_hot = statistics.fmean(self.hot)
        critical_idx = max(range(self.COUNT), key=lambda i: self.hot[i])
        critical_temp = self.hot[critical_idx]
        anomaly_count = sum(1 for i in range(self.COUNT) if self.anomaly[i])

        self.avg_history.append((now, float(avg_hot)))
        trend = self._trend(now)
        pred5 = max(20.0, avg_hot + trend * 5.0)

        power_idx = (fanA_cmd + fanB_cmd) / 510.0
        power_kw = round(power_idx * 2.4, 3)
        pdelta, pdelta_ready = self._power_delta(now, power_kw)

        confidence = round(min(0.99, 0.58 + 0.35 * clamp((critical_temp - 35.0) / 45.0, 0.0, 1.0)), 3)
        risk = round(clamp(0.52 * clamp((critical_temp - 42.0) / 36.0, 0.0, 1.0) + 0.33 * (anomaly_count / self.COUNT) + 0.15 * clamp(abs(trend) / 6.0, 0.0, 1.0), 0.01, 0.99) * 100.0, 2)
        if anomaly_count == 0:
            risk = round(risk * 0.6, 2)

        self.global_state = {
            "avg_hot": round(avg_hot, 3),
            "max_hot": round(critical_temp, 3),
            "critical_rack": self._idx_to_label(critical_idx),
            "critical_temp": round(critical_temp, 3),
            "anomaly_racks": anomaly_count,
            "ai_status": "anomaly_detected" if anomaly_count > 0 else "nominal",
            "ai_confidence": confidence,
            "trend_c_per_min": round(trend, 3),
            "predicted_hot_5m": round(pred5, 3),
            "total_cooling_power_kw": power_kw,
            "power_index_kw": power_kw,
            "power_basis": "cluster_total",
            "power_delta_pct_1h": round(pdelta, 3),
            "power_delta_ready": bool(pdelta_ready),
            "anomaly_risk_pct": risk,
            "thermal_stability_pct": round(max(0.0, 100.0 - risk), 2),
            "t_supply_A": round(self.supply_A, 3),
            "t_supply_B": round(self.supply_B, 3),
            "fanA_pwm": fanA_cmd,
            "fanB_pwm": fanB_cmd,
        }

    def _legacy_response(self, cmd: dict, avg_hot: float) -> dict:
        return {
            "ok": True,
            "target_fan_pwm": int(cmd.get("fan_local_pwm", 0)),
            "target_pump_pwm": int(cmd.get("pump_v", 0)),
            "target_heat_pwm": int(cmd.get("heat_pwm", 120)),
            "global_avg_hot": round(avg_hot, 3),
            "anomaly": bool(cmd.get("anomaly", False)),
            "mode": cmd.get("mode", "co-op"),
            "server_time_ms": int(time.time() * 1000),
        }

    def process_message(self, payload: dict, source: str = "tcp") -> dict:
        if not isinstance(payload, dict):
            return {"ok": False, "error": "payload must be object"}

        msg_type = str(payload.get("type", "")).strip()
        if msg_type == "cdu_telemetry":
            now = time.time()
            with self.lock:
                self.cdu_state = CduState(
                    cdu_id=str(payload.get("id", "CDU1") or "CDU1"),
                    fanA_pwm=clamp_pwm(payload.get("fanA_pwm", 160)),
                    fanB_pwm=clamp_pwm(payload.get("fanB_pwm", 160)),
                    t_supply_A=float(payload.get("t_supply_A", self.supply_A)),
                    t_supply_B=float(payload.get("t_supply_B", self.supply_B)),
                    received_ts=now,
                )
                self.messages_total += 1
                self._update_model(now)
                cmd = dict(self.cdu_cmd)
                cmd["server_time_ms"] = int(now * 1000)
                return cmd

        if msg_type == "rack_telemetry" or ("id" in payload and "t_hot" in payload):
            rid = self._normalize_id(str(payload.get("id", "")))
            if rid is None:
                return {"ok": False, "error": "invalid rack id"}
            if rid not in self.real_rack_ids:
                return {"ok": False, "error": f"rack id {rid} not allowed for real telemetry"}
            now = time.time()
            fan_pwm = 0
            heat_pwm = clamp_pwm(payload.get("heat_pwm", 140))
            pump_pwm = 0
            t_hot = float(payload.get("t_hot", 0.0))
            t_liquid = float(payload.get("t_liquid", max(20.0, t_hot - 5.0)))
            local_anomaly = bool(payload.get("local_anomaly", False))

            ai_anom, detector_name = self.detector.detect([t_hot, t_liquid, float(heat_pwm)])
            anomaly = bool(local_anomaly or ai_anom or t_hot >= 85.0)

            with self.lock:
                self.racks_real[rid] = RackState(
                    rack_id=rid,
                    t_hot=t_hot,
                    t_liquid=t_liquid,
                    fan_pwm=fan_pwm,
                    heat_pwm=heat_pwm,
                    pump_pwm=pump_pwm,
                    rssi=int(payload.get("rssi", -60)),
                    anomaly=anomaly,
                    detector=detector_name,
                    received_ts=now,
                )
                self.messages_total += 1
                if anomaly:
                    self.anomalies_total += 1
                self._append_hist(
                    rid,
                    {
                        "ts_ms": int(now * 1000),
                        "t_hot": t_hot,
                        "t_liquid": t_liquid,
                        "fan_local_pwm": fan_pwm,
                        "heat_pwm": heat_pwm,
                        "pump_v": pump_pwm,
                        "anomaly": anomaly,
                        "detector": detector_name,
                    },
                )
                self._update_model(now)
                cmd = dict(self.rack_cmds.get(rid, self._legacy_response({}, 0.0)))
                cmd["global_avg_hot"] = self.global_state["avg_hot"]
                cmd["server_time_ms"] = int(now * 1000)

            if source == "tcp":
                return self._legacy_response(cmd, float(cmd.get("global_avg_hot", 0.0)))
            return cmd

        return {"ok": False, "error": "unsupported message type"}

    def get_history(self, rack_id: str, points: int = 120) -> dict:
        rid = self._normalize_id(rack_id) or rack_id
        with self.lock:
            queue = self.rack_history.get(rid, deque())
            data = list(queue)[-points:]
        return {"rack": rid, "points": data, "count": len(data)}

    def get_twin_payload(self, rack_count: int = 8) -> dict:
        now = time.time()
        count = max(2, min(self.COUNT, rack_count))
        with self.lock:
            self._update_model(now)
            racks = []
            for idx in range(count):
                label = self._idx_to_label(idx)
                real = self.racks_real.get(label)
                is_real = bool(real and self._fresh(real.received_ts, now))
                cmd = self.rack_cmds.get(
                    label,
                    {
                        "fan_local_pwm": self.fan[idx],
                        "heat_pwm": self.heat[idx],
                        "pump_v": self.pump[idx],
                        "mode": "heat-only-co-op",
                        "anomaly": self.anomaly[idx],
                    },
                )

                fan_pwm = int(real.fan_pwm) if is_real and real else int(self.fan[idx])
                heat_pwm = int(real.heat_pwm) if is_real and real else int(self.heat[idx])
                pump_pwm = int(real.pump_pwm) if is_real and real else int(self.pump[idx])
                t_hot = float(real.t_hot) if is_real and real else float(self.hot[idx])
                t_liq = float(real.t_liquid) if is_real and real else float(self.liquid[idx])
                anomaly = bool(real.anomaly) if is_real and real else bool(self.anomaly[idx])

                racks.append(
                    {
                        "rack_id": idx,
                        "label": label,
                        "node_id": label if is_real else None,
                        "is_real": is_real,
                        "online": True,
                        "temp_hot": round(t_hot, 3),
                        "temp_liquid": round(t_liq, 3),
                        "fan_pwm": fan_pwm,
                        "heat_pwm": heat_pwm,
                        "pump_pwm": pump_pwm,
                        "target_fan_pwm": int(cmd.get("fan_local_pwm", fan_pwm)),
                        "target_heat_pwm": int(cmd.get("heat_pwm", heat_pwm)),
                        "target_pump_pwm": int(cmd.get("pump_v", pump_pwm)),
                        "virtual_flow": round(pump_pwm / 255.0, 4),
                        "mode": cmd.get("mode", "co-op") if is_real else "heat-only-co-op",
                        "detector": real.detector if is_real and real else "derived",
                        "anomaly": anomaly,
                        "status": self._status(t_hot, anomaly),
                    }
                )

            cdu_online = bool(self.cdu_state and self._fresh(self.cdu_state.received_ts, now))
            cdu = {
                "id": self.cdu_state.cdu_id if cdu_online and self.cdu_state else "CDU1",
                "online": cdu_online,
                "fanA_pwm": self.cdu_state.fanA_pwm if cdu_online and self.cdu_state else int(self.cdu_cmd["fanA_pwm"]),
                "fanB_pwm": self.cdu_state.fanB_pwm if cdu_online and self.cdu_state else int(self.cdu_cmd["fanB_pwm"]),
                "t_supply_A": round(self.supply_A, 3),
                "t_supply_B": round(self.supply_B, 3),
                "cmd_fanA_pwm": int(self.cdu_cmd["fanA_pwm"]),
                "cmd_fanB_pwm": int(self.cdu_cmd["fanB_pwm"]),
                "t_supply_target": self.cdu_cmd["t_supply_target"],
            }

            g = dict(self.global_state)
            g.update(
                {
                    "active_nodes": sum(1 for rack in racks if rack["is_real"]),
                    "messages_total": self.messages_total,
                    "anomalies_total": self.anomalies_total,
                    "detector_mode": self.detector.detector_mode,
                    "cdu_online": cdu_online,
                }
            )

            return {"type": "twin_state", "timestamp_ms": int(now * 1000), "global": g, "cdu": cdu, "racks": racks}

    def get_dashboard_snapshot(self) -> dict:
        now = time.time()
        with self.lock:
            self._update_model(now)
            nodes = {
                rid: {
                    "id": rid,
                    "online": self._fresh(state.received_ts, now),
                    "age_ms": int((now - state.received_ts) * 1000),
                    "t_hot": state.t_hot,
                    "t_liquid": state.t_liquid,
                    "fan_local_pwm": state.fan_pwm,
                    "heat_pwm": state.heat_pwm,
                    "pump_v": state.pump_pwm,
                    "rssi": state.rssi,
                    "detector": state.detector,
                    "anomaly": state.anomaly,
                }
                for rid, state in self.racks_real.items()
            }
        return {
            "server_time_ms": int(now * 1000),
            "uptime_s": round(now - self.started_ts, 2),
            "active_nodes": sum(1 for node in nodes.values() if node["online"]),
            "messages_total": self.messages_total,
            "anomalies_total": self.anomalies_total,
            "detector_mode": self.detector.detector_mode,
            "global": self.global_state,
            "nodes": nodes,
        }

class TcpTelemetryServer:
    def __init__(self, core: DigitalTwinCore, host: str, port: int):
        self.core = core
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._stop = threading.Event()

    def serve_forever(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen(16)
        sock.settimeout(1.0)
        self._sock = sock
        safe_log(f"[edge-tcp] listening on {self.host}:{self.port}")
        try:
            while not self._stop.is_set():
                try:
                    conn, addr = sock.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break
                threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True).start()
        finally:
            try:
                sock.close()
            except OSError:
                pass
            self._sock = None

    def shutdown(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass

    def _handle_client(self, conn: socket.socket, addr: Tuple[str, int]) -> None:
        with conn:
            try:
                conn.settimeout(2.0)
                raw = self._recv_line(conn)
                if not raw:
                    conn.sendall(b"{\"ok\":false,\"error\":\"empty_payload\"}\n")
                    return
                msg = json.loads(raw)
                resp = self.core.process_message(msg, source="tcp")
                conn.sendall((json.dumps(resp) + "\n").encode("utf-8"))
            except Exception as exc:
                try:
                    conn.sendall((json.dumps({"ok": False, "error": str(exc)}) + "\n").encode("utf-8"))
                except Exception:
                    pass
                safe_log(f"[edge-tcp] handler error from {addr}: {exc}")

    @staticmethod
    def _recv_line(conn: socket.socket, max_bytes: int = 8192) -> str:
        data = bytearray()
        while len(data) < max_bytes:
            chunk = conn.recv(min(512, max_bytes - len(data)))
            if not chunk:
                break
            pos = chunk.find(b"\n")
            if pos >= 0:
                data.extend(chunk[:pos])
                break
            data.extend(chunk)
        return data.decode("utf-8", errors="replace").strip()


class TwinRequestHandler(BaseHTTPRequestHandler):
    core: DigitalTwinCore
    project_root: Path
    ui_entry: str
    ws_host: str
    ws_port: int
    edge_ws_host: str
    edge_ws_port: int
    ws_enabled: bool
    edge_ws_enabled: bool
    ws_rack_count: int

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._send_json({"ok": True, "time_ms": int(time.time() * 1000)})
            return
        if parsed.path == "/api/state":
            self._send_json(self.core.get_dashboard_snapshot())
            return
        if parsed.path == "/api/twin":
            q = parse_qs(parsed.query)
            raw = q.get("racks", ["8"])[0]
            try:
                count = max(2, min(8, int(raw)))
            except ValueError:
                count = 8
            self._send_json(self.core.get_twin_payload(count))
            return
        if parsed.path == "/api/history":
            q = parse_qs(parsed.query)
            rack = (q.get("rack", ["R00"])[0] or "R00").strip().upper()
            raw = q.get("points", ["120"])[0]
            try:
                points = max(10, min(1000, int(raw)))
            except ValueError:
                points = 120
            self._send_json(self.core.get_history(rack, points))
            return
        if parsed.path == "/api/config":
            self._send_json(
                {
                    "ws_host": self.ws_host,
                    "ws_port": self.ws_port,
                    "ws_enabled": self.ws_enabled,
                    "ws_rack_count": self.ws_rack_count,
                    "edge_ws_host": self.edge_ws_host,
                    "edge_ws_port": self.edge_ws_port,
                    "edge_ws_enabled": self.edge_ws_enabled,
                }
            )
            return
        self._serve_static(parsed.path)

    def _serve_static(self, raw_path: str) -> None:
        rel_path = self.ui_entry if raw_path in ("/", "") else raw_path.lstrip("/")
        root = self.project_root.resolve()
        target = (root / rel_path).resolve()
        if root not in target.parents and target != root:
            self.send_error(403, "forbidden")
            return
        if not target.exists() or not target.is_file():
            self.send_error(404, "not found")
            return

        content_type, _ = mimetypes.guess_type(str(target))
        payload = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, obj: dict) -> None:
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class WebService:
    def __init__(self, core: DigitalTwinCore, host: str, port: int, project_root: Path, ui_entry: str, ws_host: str, ws_port: int, edge_ws_host: str, edge_ws_port: int, ws_enabled: bool, edge_ws_enabled: bool, ws_rack_count: int):
        handler = type("TwinHandler", (TwinRequestHandler,), {})
        handler.core = core
        handler.project_root = project_root
        handler.ui_entry = ui_entry
        handler.ws_host = ws_host
        handler.ws_port = ws_port
        handler.edge_ws_host = edge_ws_host
        handler.edge_ws_port = edge_ws_port
        handler.ws_enabled = ws_enabled
        handler.edge_ws_enabled = edge_ws_enabled
        handler.ws_rack_count = ws_rack_count
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread is not None:
            self.thread.join(timeout=2.0)


class WebSocketServices:
    def __init__(self, core: DigitalTwinCore, twin_host: str, twin_port: int, edge_host: str, edge_port: int, rack_count: int, interval_ms: int, twin_enabled: bool, edge_enabled: bool):
        self.core = core
        self.twin_host = twin_host
        self.twin_port = twin_port
        self.edge_host = edge_host
        self.edge_port = edge_port
        self.rack_count = rack_count
        self.interval_ms = interval_ms
        self.twin_enabled = twin_enabled
        self.edge_enabled = edge_enabled
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if ws_serve is None or (not self.twin_enabled and not self.edge_enabled):
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=3.0)

    def _run(self) -> None:
        asyncio.run(self._run_async())

    async def _run_async(self) -> None:
        ctxs = []
        if self.twin_enabled:
            ctxs.append(ws_serve(self._twin_handler, self.twin_host, self.twin_port, ping_interval=20, ping_timeout=20))
        if self.edge_enabled:
            ctxs.append(ws_serve(self._edge_handler, self.edge_host, self.edge_port, ping_interval=20, ping_timeout=20))
        if not ctxs:
            return

        for ctx in ctxs:
            await ctx.__aenter__()
        try:
            if self.twin_enabled:
                safe_log(f"[ws-twin] serving on ws://{self.twin_host}:{self.twin_port}")
            if self.edge_enabled:
                safe_log(f"[ws-edge] serving on ws://{self.edge_host}:{self.edge_port}")
            while not self.stop_event.is_set():
                await asyncio.sleep(0.2)
        finally:
            for ctx in reversed(ctxs):
                await ctx.__aexit__(None, None, None)

    async def _twin_handler(self, websocket) -> None:
        try:
            while not self.stop_event.is_set():
                await websocket.send(json.dumps(self.core.get_twin_payload(self.rack_count)))
                await asyncio.sleep(self.interval_ms / 1000.0)
        except ConnectionClosed:
            return

    async def _edge_handler(self, websocket) -> None:
        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                    resp = self.core.process_message(msg, source="edge_ws")
                except Exception as exc:
                    resp = {"ok": False, "error": str(exc)}
                await websocket.send(json.dumps(resp))
        except ConnectionClosed:
            return


def main() -> None:
    parser = argparse.ArgumentParser(description="AI-IoT hierarchical cooling twin server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default=5000, type=int)
    parser.add_argument("--stale-seconds", default=8.0, type=float)
    parser.add_argument("--history-limit", default=360, type=int)
    parser.add_argument("--detector", default="zscore", choices=["zscore", "iforest"])
    parser.add_argument("--contamination", default=0.05, type=float)
    parser.add_argument("--warmup-samples", default=50, type=int)

    parser.add_argument("--ui-host", default="0.0.0.0")
    parser.add_argument("--ui-port", default=8080, type=int)
    parser.add_argument("--ui-entry", default="twin3d/index.html")

    parser.add_argument("--ws-host", default="0.0.0.0")
    parser.add_argument("--ws-port", default=8000, type=int)
    parser.add_argument("--edge-ws-host", default="0.0.0.0")
    parser.add_argument("--edge-ws-port", default=8765, type=int)
    parser.add_argument("--ws-rack-count", default=8, type=int)
    parser.add_argument("--ws-interval-ms", default=500, type=int)

    parser.add_argument("--no-ui", action="store_true")
    parser.add_argument("--no-ws", action="store_true")
    parser.add_argument("--no-edge-ws", action="store_true")
    parser.add_argument("--no-tcp", action="store_true")
    args = parser.parse_args()

    detector = AnomalyDetector(args.detector, args.contamination, args.warmup_samples)
    core = DigitalTwinCore(detector, args.stale_seconds, max(60, args.history_limit))

    project_root = Path(__file__).resolve().parent
    rack_count = max(2, min(8, args.ws_rack_count))
    interval_ms = max(150, min(3000, args.ws_interval_ms))

    ws_available = ws_serve is not None
    twin_enabled = ws_available and (not args.no_ws)
    edge_enabled = ws_available and (not args.no_edge_ws)

    ui_service: Optional[WebService] = None
    if not args.no_ui:
        entry = project_root / args.ui_entry
        if not entry.exists():
            raise FileNotFoundError(f"ui entry not found: {entry}")
        ui_service = WebService(core, args.ui_host, args.ui_port, project_root, args.ui_entry, args.ws_host, args.ws_port, args.edge_ws_host, args.edge_ws_port, twin_enabled, edge_enabled, rack_count)
        ui_service.start()
        safe_log(f"[ui] HTTP serving on http://{args.ui_host}:{args.ui_port}")

    ws_services = WebSocketServices(core, args.ws_host, args.ws_port, args.edge_ws_host, args.edge_ws_port, rack_count, interval_ms, twin_enabled, edge_enabled)
    ws_services.start()

    tcp_server: Optional[TcpTelemetryServer] = None
    if not args.no_tcp:
        tcp_server = TcpTelemetryServer(core, args.host, args.port)

    try:
        if tcp_server is not None:
            tcp_server.serve_forever()
        else:
            safe_log("[edge-tcp] disabled")
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        safe_log("\n[server] shutdown requested")
    finally:
        if tcp_server is not None:
            tcp_server.shutdown()
        ws_services.stop()
        if ui_service is not None:
            ui_service.stop()


if __name__ == "__main__":
    main()
