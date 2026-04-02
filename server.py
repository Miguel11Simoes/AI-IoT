
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
import os
from collections import deque
from contextlib import AsyncExitStack
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Deque, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

np = None
IsolationForest = None

def _try_import_ai() -> None:
    global np, IsolationForest
    if os.environ.get("AI_DISABLE_NUMPY", "0") == "1":
        return
    if np is not None or IsolationForest is not None:
        return
    try:
        import numpy as _np  # type: ignore
        from sklearn.ensemble import IsolationForest as _IsolationForest  # type: ignore
        np = _np
        IsolationForest = _IsolationForest
    except Exception:
        np = None
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


def finite_float(value, default: Optional[float] = None) -> Optional[float]:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(result):
        return default
    return result


def finite_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def parse_real_rack_ids(raw_value: str) -> List[str]:
    rack_ids = []
    seen = set()
    for token in raw_value.split(","):
        rack_id = token.strip().upper()
        if not rack_id:
            continue
        if not re.match(r"^R\d{2}$", rack_id):
            raise ValueError(f"invalid rack id in --real-racks: {rack_id}")
        if rack_id in seen:
            continue
        seen.add(rack_id)
        rack_ids.append(rack_id)
    if not rack_ids:
        raise ValueError("--real-racks must include at least one rack id")
    return rack_ids


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
        if detector_mode == "iforest":
            _try_import_ai()
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
    t_hot_real: float
    t_liquid_real: Optional[float]
    t_liquid_effective: float
    t_hot_source: str
    t_liquid_source: str
    telemetry_mode: str
    sensor_ok: bool
    fan_pwm: int
    heat_pwm: int
    heater_on: bool
    heater_rated_power_w: float
    heater_avg_power_w: float
    rssi: int
    anomaly: bool
    detector: str
    device_ts_ms: int
    received_ts: float


@dataclass
class CduState:
    cdu_id: str
    fanA_pwm: int
    fanB_pwm: int
    peltierA_on: bool
    peltierB_on: bool
    t_supply_A: float
    t_supply_B: float
    received_ts: float

class DigitalTwinCore:
    ROWS = 2
    COLS = 4
    COUNT = 8

    def __init__(
        self,
        detector: AnomalyDetector,
        stale_seconds: float,
        history_limit: int,
        real_rack_ids: List[str],
        heater_equivalent_target_w: float = 1.44,
        heater_default_power_w: float = 1.44,
        virtual_ambient_c: float = 26.0,
        stale_transition_seconds: float = 4.0,
        anomaly_temp_c: float = 80.0,
    ):
        self.detector = detector
        self.stale_seconds = stale_seconds
        self.history_limit = history_limit

        self.lock = threading.Lock()
        self.started_ts = time.time()
        self.messages_total = 0
        self.anomalies_total = 0

        self.racks_real: Dict[str, RackState] = {}
        self.real_rack_ids = set(real_rack_ids)
        self.cdu_state: Optional[CduState] = None

        initial_hot = float(virtual_ambient_c)
        initial_liquid = self._estimate_server_liquid(0, initial_hot, time.time())
        self.hot = [initial_hot] * self.COUNT
        self.liquid = [initial_liquid] * self.COUNT
        self.virtual_hot = [initial_hot] * self.COUNT
        self.virtual_liquid = [initial_liquid] * self.COUNT
        self.fan = [0] * self.COUNT
        self.heat = [0] * self.COUNT
        self.anomaly = [False] * self.COUNT
        self.heater_real_w = [0.0] * self.COUNT
        self.heater_equivalent_w = [0.0] * self.COUNT
        self.heater_scale = [1.0] * self.COUNT
        self.virtual_seeded = [False] * self.COUNT

        self.supply_A = 29.0
        self.supply_B = 30.0
        self.last_model_ts = time.time()
        self.heater_equivalent_target_w = max(1.0, float(heater_equivalent_target_w))
        self.heater_default_power_w = max(0.1, float(heater_default_power_w))
        self.virtual_ambient_c = float(virtual_ambient_c)
        self.stale_transition_seconds = max(0.0, float(stale_transition_seconds))
        self.anomaly_temp_c = float(anomaly_temp_c)

        self.rack_cmds: Dict[str, dict] = {}
        self.cdu_cmd = {
            "type": "cdu_cmd",
            "id": "CDU1",
            "fanA_pwm": 0,
            "fanB_pwm": 0,
            "peltierA_on": False,
            "peltierB_on": False,
            "fallback_target": "maintain_supply",
            "t_supply_target": 29.5,
        }

        self.global_state = {
            "avg_hot": 0.0,
            "max_hot": 0.0,
            "critical_rack": sorted(self.real_rack_ids)[0],
            "critical_temp": 0.0,
            "heater_equivalent_target_w": round(self.heater_equivalent_target_w, 3),
            "anomaly_temp_c": round(self.anomaly_temp_c, 3),
            "stale_transition_seconds": round(self.stale_transition_seconds, 3),
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
            "fanA_pwm": 0,
            "fanB_pwm": 0,
            "peltierA_on": False,
            "peltierB_on": False,
        }
        self.avg_history: Deque[Tuple[float, float]] = deque(maxlen=1200)
        self.power_history: Deque[Tuple[float, float]] = deque(maxlen=9000)
        self.rack_history: Dict[str, Deque[dict]] = {}

        self.alias = {"A": "R00", "NODE_A": "R00", "B": "R07", "NODE_B": "R07"}

        # Simplified thermal model coefficients
        self.k_heat = 0.020
        self.k_heat_equiv = (self.k_heat * 255.0) / self.heater_equivalent_target_w
        self.k_zone_fan = 0.240
        self.k_cool = 0.085
        self.k_peltier = 8.2
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

    @staticmethod
    def _infer_telemetry_mode(hot_source: str, liquid_source: str, sensor_ok: bool) -> str:
        hot = str(hot_source or "").strip().lower()
        liquid = str(liquid_source or "").strip().lower()
        if hot == "fallback_simulated":
            return "sensor_fallback"
        if hot == "simulated" and liquid == "simulated":
            return "simulated" if sensor_ok else "sensor_fallback"
        if hot == "sensor" and liquid == "server_estimated":
            return "measured_hot_server_estimated_liquid"
        if hot == "sensor" and liquid == "unavailable":
            return "measured_hot_only"
        if hot == "sensor" and liquid == "sensor":
            return "measured"
        return "legacy"

    def _zone_fan_pwm(self, idx: int, now: float) -> int:
        zone = self._zone(idx)
        if self.cdu_state and self._fresh(self.cdu_state.received_ts, now):
            return self.cdu_state.fanA_pwm if zone == "A" else self.cdu_state.fanB_pwm
        return int(self.cdu_cmd["fanA_pwm"] if zone == "A" else self.cdu_cmd["fanB_pwm"])

    def _estimate_server_liquid(
        self,
        idx: int,
        hot_c: float,
        now: float,
        seed_liquid: Optional[float] = None,
    ) -> float:
        curve = (
            (20.0, 40.0),
            (23.0, 65.0),
            (27.0, 72.0),
            (28.0, 75.0),
            (29.0, 80.0),
            (31.0, 88.0),
        )

        if hot_c <= curve[0][0]:
            x0, y0 = curve[0]
            x1, y1 = curve[1]
        elif hot_c >= curve[-1][0]:
            x0, y0 = curve[-2]
            x1, y1 = curve[-1]
        else:
            x0, y0, x1, y1 = curve[0][0], curve[0][1], curve[1][0], curve[1][1]
            for i in range(len(curve) - 1):
                ax, ay = curve[i]
                bx, by = curve[i + 1]
                if ax <= hot_c <= bx:
                    x0, y0, x1, y1 = ax, ay, bx, by
                    break

        if abs(x1 - x0) < 1e-6:
            return float(y0)
        alpha = (hot_c - x0) / (x1 - x0)
        return float(y0 + alpha * (y1 - y0))

    def _append_hist(self, rack_id: str, item: dict) -> None:
        q = self.rack_history.setdefault(rack_id, deque(maxlen=self.history_limit))
        q.append(item)

    def _heater_scale_factor(self, rated_power_w: float) -> float:
        rated = rated_power_w if rated_power_w > 0.0 else self.heater_default_power_w
        return max(1.0, self.heater_equivalent_target_w / max(0.1, rated))

    def _heater_real_power_w(self, heat_pwm: int, rated_power_w: float, reported_avg_w: float) -> float:
        rated = rated_power_w if rated_power_w > 0.0 else self.heater_default_power_w
        if reported_avg_w > 0.0:
            return max(0.0, reported_avg_w)
        return rated * (float(heat_pwm) / 255.0)

    def _heater_equivalent_power_w(self, heat_pwm: int, rated_power_w: float, reported_avg_w: float) -> Tuple[float, float, float]:
        real_w = self._heater_real_power_w(heat_pwm, rated_power_w, reported_avg_w)
        scale = self._heater_scale_factor(rated_power_w)
        return real_w, real_w * scale, scale

    @staticmethod
    def _blend_value(start: float, end: float, alpha: float) -> float:
        return start + (end - start) * clamp(alpha, 0.0, 1.0)

    @staticmethod
    def _blend_int(start: int, end: int, alpha: float) -> int:
        return int(round(DigitalTwinCore._blend_value(float(start), float(end), alpha)))

    def _display_rack_actuation(
        self,
        idx: int,
        real: Optional[RackState],
        source_status: str,
        source_blend: float,
    ) -> Tuple[int, int, bool, bool]:
        if source_status == "real" and real is not None:
            return int(real.fan_pwm), int(real.heat_pwm), bool(real.heater_on), bool(real.anomaly)
        if source_status == "stale" and real is not None:
            fan_pwm = self._blend_int(int(real.fan_pwm), int(self.fan[idx]), source_blend)
            heat_pwm = self._blend_int(int(real.heat_pwm), int(self.heat[idx]), source_blend)
            heater_on = heat_pwm > 0
            anomaly = bool(real.anomaly or self.anomaly[idx])
            return fan_pwm, heat_pwm, heater_on, anomaly
        fan_pwm = int(self.fan[idx])
        heat_pwm = int(self.heat[idx])
        heater_on = heat_pwm > 0
        anomaly = bool(self.anomaly[idx])
        return fan_pwm, heat_pwm, heater_on, anomaly

    def _simulated_rack_values(self, label: str, idx: int) -> Tuple[float, float]:
        if label in self.real_rack_ids and self.virtual_seeded[idx]:
            return self.virtual_hot[idx], self.virtual_liquid[idx]
        return self.hot[idx], self.liquid[idx]

    @staticmethod
    def _state_has_valid_sensor(state: Optional["RackState"]) -> bool:
        if state is None or not state.sensor_ok:
            return False
        source = str(state.t_hot_source or "").strip().lower()
        return source == "sensor"

    def _rack_source_info(self, label: str, now: float) -> Tuple[str, float, Optional[float], bool]:
        configured_real = label in self.real_rack_ids
        if not configured_real:
            return "simulated", 1.0, None, False

        state = self.racks_real.get(label)
        if state is None:
            return "simulated", 1.0, None, True

        age = max(0.0, now - state.received_ts)
        if age <= self.stale_seconds:
            if self._state_has_valid_sensor(state):
                return "real", 0.0, age, True
            return "simulated", 1.0, age, True

        if self.stale_transition_seconds > 0.0:
            stale_age = age - self.stale_seconds
            if stale_age <= self.stale_transition_seconds and self._state_has_valid_sensor(state):
                blend = stale_age / self.stale_transition_seconds
                return "stale", blend, age, True

        return "simulated", 1.0, age, True

    def _anchor_temp(self, rack_id: str, fallback_idx: int, now: float) -> Optional[float]:
        state = self.racks_real.get(rack_id)
        if state and self._fresh(state.received_ts, now) and self._state_has_valid_sensor(state):
            idx = self._label_to_idx(rack_id)
            if idx is not None and self.virtual_seeded[idx]:
                return self.virtual_hot[idx]
            return state.t_hot_real
        if rack_id in self.real_rack_ids:
            idx = self._label_to_idx(rack_id)
            if idx is not None and self.virtual_seeded[idx]:
                return self.virtual_hot[idx]
            return self.hot[fallback_idx]
        return None

    def _zone_has_anomaly(self, zone: str) -> bool:
        return any(self.anomaly[idx] for idx in range(self.COUNT) if self._zone(idx) == zone)

    def _zone_enabled(self, zone: str) -> bool:
        if zone == "A":
            return "R00" in self.real_rack_ids
        if zone == "B":
            return "R07" in self.real_rack_ids
        return False

    def _grid_pos(self, idx: int) -> Tuple[int, int]:
        return divmod(idx, self.COLS)

    def _simulated_hot_target(self, idx: int, now: float) -> float:
        base = self.virtual_ambient_c
        row, col = self._grid_pos(idx)
        target = base
        anchors: List[Tuple[int, float]] = []
        for rack_id in sorted(self.real_rack_ids):
            state = self.racks_real.get(rack_id)
            if state is None or not self._fresh(state.received_ts, now):
                continue
            if not self._state_has_valid_sensor(state):
                continue
            anchor_idx = self._label_to_idx(rack_id)
            if anchor_idx is None:
                continue
            anchors.append((anchor_idx, float(state.t_hot_real)))

        if not anchors:
            return clamp(base + 0.4 * math.sin(now * 0.17 + idx), base - 1.0, base + 2.0)

        min_anchor = min(temp for _, temp in anchors)
        max_anchor = max(temp for _, temp in anchors)
        for anchor_idx, anchor_hot in anchors:
            arow, acol = self._grid_pos(anchor_idx)
            dist = math.hypot(float(row - arow), float(col - acol))
            weight = 1.0 / (1.0 + 0.6 * dist * dist)
            # Let nearby simulated racks drift above or below ambient depending
            # on the closest real rack temperatures, instead of pinning them at
            # ambient whenever the real racks are cooler than 26 C.
            target += (anchor_hot - base) * weight

        return clamp(target, min(base, min_anchor), max(base, max_anchor))

    @staticmethod
    def _zone_rack_id(zone: str) -> Optional[str]:
        if zone == "A":
            return "R00"
        if zone == "B":
            return "R07"
        return None

    def _zone_real_state(self, zone: str, now: float) -> Optional["RackState"]:
        rack_id = self._zone_rack_id(zone)
        if rack_id is None or rack_id not in self.real_rack_ids:
            return None
        state = self.racks_real.get(rack_id)
        if state is None or not self._fresh(state.received_ts, now):
            return None
        if not self._state_has_valid_sensor(state):
            return None
        return state

    def _cooling_fan_cmd(self, hot_c: float, anomaly: bool, previous_pwm: int) -> int:
        # REGRA ABSOLUTA: se temperatura real < 23, fan SEMPRE desligada
        if hot_c < 23.0:
            return 0
        # Emergência: anomalia ou >= 38°C
        if anomaly or hot_c >= 38.0:
            return 150
        # Máximo normal: >= 30°C
        if hot_c >= 30.0:
            return 100
        # Entre 23-30°C: PWM proporcional (50 mínimo, 100 máximo)
        # 23°C -> 50, 30°C -> 100
        return clamp_pwm(int(round(50.0 + ((hot_c - 23.0) / 7.0) * 50.0)), 50, 100)

    def _cooling_peltier_cmd(self, hot_c: float, anomaly: bool, previous_pwm: int) -> int:
        # REGRA ABSOLUTA: se temperatura real < 26.5, Peltier SEMPRE desligado
        if hot_c < 26.5:
            return 0
        # Emergência ou >= 38°C: máximo
        if anomaly or hot_c >= 38.0:
            return 255
        # Entre 26.5-29.9°C: meia intensidade
        if hot_c < 30.0:
            return 128
        # >= 30°C: full
        return 255

    def _rack_heat_cmd(self, idx: int, now: float) -> int:
        # Mantem o heater no maximo quase sempre, mas introduz quedas curtas
        # e desencontradas por rack para criar diferencas termicas entre zonas.
        phase = (int(now // 4.0) + idx * 2) % 5
        return 220 if phase == 0 else 255

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

    def _step_virtual_rack(
        self,
        idx: int,
        dt: float,
        zone_supply: float,
        zone_fan: int,
        field_temp: float,
        heat_equivalent_w: float,
        measured_hot: Optional[float] = None,
        measured_liquid: Optional[float] = None,
        anchor_strength: float = 0.0,
    ) -> None:
        if not self.virtual_seeded[idx]:
            seed_hot = measured_hot if measured_hot is not None else self.hot[idx]
            seed_liq = measured_liquid if measured_liquid is not None else self.liquid[idx]
            self.virtual_hot[idx] = clamp(seed_hot, self.virtual_ambient_c - 2.0, 120.0)
            self.virtual_liquid[idx] = clamp(
                seed_liq,
                self.virtual_ambient_c - 2.0,
                self.virtual_hot[idx] - 0.1,
            )
            self.virtual_seeded[idx] = True

        vhot = self.virtual_hot[idx]
        vliq = self.virtual_liquid[idx]
        q_heat = self.k_heat_equiv * heat_equivalent_w
        q_rej = self.k_zone_fan * (zone_fan / 255.0) * max(0.0, vhot - zone_supply)
        hot_to_liquid = 0.23 * max(0.0, vhot - vliq)
        liquid_rej = (0.06 + 0.18 * (zone_fan / 255.0)) * max(0.0, vliq - zone_supply)

        vhot += (self.beta_rack * (q_heat - q_rej) - 0.09 * hot_to_liquid + 0.10 * (field_temp - vhot)) * dt
        vliq += (0.14 * hot_to_liquid - 0.08 * liquid_rej) * dt

        if measured_hot is not None and anchor_strength > 0.0:
            vhot += (measured_hot - vhot) * anchor_strength * dt
            vhot = max(vhot, measured_hot)
        if measured_liquid is not None and anchor_strength > 0.0:
            vliq += (measured_liquid - vliq) * anchor_strength * dt
            vliq = max(vliq, measured_liquid)

        min_hot = max(self.virtual_ambient_c - 2.0, zone_supply - 6.0)
        min_liquid = max(self.virtual_ambient_c - 2.0, zone_supply - 7.0)
        vhot = clamp(vhot, min_hot, 125.0)
        vliq = clamp(vliq, min_liquid, vhot - 0.1)

        self.virtual_hot[idx] = vhot
        self.virtual_liquid[idx] = vliq

    def _update_model(self, now: float) -> None:
        dt = clamp(now - self.last_model_ts, 0.05, 2.0)
        self.last_model_ts = now

        t00 = self._anchor_temp("R00", 0, now)
        t07 = self._anchor_temp("R07", self.COUNT - 1, now)
        if t00 is None and t07 is None:
            t00 = self.hot[0]
            t07 = self.hot[self.COUNT - 1]
        elif t00 is None:
            t00 = t07
        elif t07 is None:
            t07 = t00

        if self.cdu_state and self._fresh(self.cdu_state.received_ts, now):
            fanA_meas = self.cdu_state.fanA_pwm
            fanB_meas = self.cdu_state.fanB_pwm
            peltierA_meas = bool(self.cdu_state.peltierA_on)
            peltierB_meas = bool(self.cdu_state.peltierB_on)
            self.supply_A = clamp(self.cdu_state.t_supply_A, 18.0, 45.0)
            self.supply_B = clamp(self.cdu_state.t_supply_B, 18.0, 45.0)
        else:
            fanA_meas = int(self.cdu_cmd["fanA_pwm"])
            fanB_meas = int(self.cdu_cmd["fanB_pwm"])
            peltierA_meas = bool(self.cdu_cmd["peltierA_on"])
            peltierB_meas = bool(self.cdu_cmd["peltierB_on"])

        zoneA_enabled = self._zone_enabled("A")
        zoneB_enabled = self._zone_enabled("B")

        for idx in range(self.COUNT):
            label = self._idx_to_label(idx)
            row, col = divmod(idx, self.COLS)
            w = (row + col / (self.COLS - 1)) / self.ROWS
            field = (1.0 - w) * t00 + w * t07

            zone = self._zone(idx)
            zone_enabled = zoneA_enabled if zone == "A" else zoneB_enabled
            zone_supply = self.supply_A if zone == "A" else self.supply_B
            zone_fan = fanA_meas if zone == "A" else fanB_meas
            real = self.racks_real.get(label)
            if real and self._fresh(real.received_ts, now) and not self._state_has_valid_sensor(real):
                target_hot = self._simulated_hot_target(idx, now)
                self.hot[idx] = clamp(self.hot[idx] + (target_hot - self.hot[idx]) * 0.65 * dt, 22.0, 50.0)
                self.liquid[idx] = self._estimate_server_liquid(idx, self.hot[idx], now, self.liquid[idx])
                self.virtual_hot[idx] = self.hot[idx]
                self.virtual_liquid[idx] = self.liquid[idx]
                self.virtual_seeded[idx] = True
                self.fan[idx] = 0
                self.heat[idx] = 0
                self.heater_real_w[idx] = 0.0
                self.heater_equivalent_w[idx] = 0.0
                self.heater_scale[idx] = self._heater_scale_factor(self.heater_default_power_w)
                self.anomaly[idx] = False
                continue
            if real and self._fresh(real.received_ts, now) and self._state_has_valid_sensor(real):
                self.hot[idx] = real.t_hot_real
                self.liquid[idx] = real.t_liquid_effective
                self.fan[idx] = real.fan_pwm
                self.heat[idx] = real.heat_pwm
                real_w, equiv_w, scale = self._heater_equivalent_power_w(
                    real.heat_pwm,
                    real.heater_rated_power_w,
                    real.heater_avg_power_w,
                )
                self.heater_real_w[idx] = real_w
                self.heater_equivalent_w[idx] = equiv_w
                self.heater_scale[idx] = scale
                anchor_strength = clamp(0.28 / scale, 0.02, 0.28)
                self._step_virtual_rack(
                    idx,
                    dt,
                    zone_supply,
                    zone_fan,
                    field,
                    equiv_w,
                    measured_hot=real.t_hot_real,
                    measured_liquid=real.t_liquid_real,
                    anchor_strength=anchor_strength,
                )
                thermal_virtual_guard = self.virtual_hot[idx] >= 75.0 and real.t_hot_real >= 26.0
                self.anomaly[idx] = bool(real.anomaly or thermal_virtual_guard)
                continue

            if not zone_enabled:
                target_hot = self._simulated_hot_target(idx, now)
                self.hot[idx] = clamp(self.hot[idx] + (target_hot - self.hot[idx]) * 0.55 * dt, 22.0, 45.0)
                self.liquid[idx] = self._estimate_server_liquid(idx, self.hot[idx], now, self.liquid[idx])
                self.virtual_hot[idx] = self.hot[idx]
                self.virtual_liquid[idx] = self.liquid[idx]
                self.virtual_seeded[idx] = True
                self.fan[idx] = 0
                self.heat[idx] = 0
                self.heater_real_w[idx] = 0.0
                self.heater_equivalent_w[idx] = 0.0
                self.heater_scale[idx] = self._heater_scale_factor(self.heater_default_power_w)
                self.anomaly[idx] = False
                continue

            target_hot = self._simulated_hot_target(idx, now)
            self.hot[idx] = clamp(self.hot[idx] + (target_hot - self.hot[idx]) * 0.55 * dt, 22.0, 50.0)
            self.liquid[idx] = self._estimate_server_liquid(idx, self.hot[idx], now, self.liquid[idx])
            self.fan[idx] = 0
            self.heat[idx] = 0
            self.heater_real_w[idx] = 0.0
            self.heater_equivalent_w[idx] = 0.0
            self.heater_scale[idx] = self._heater_scale_factor(self.heater_default_power_w)
            self.virtual_hot[idx] = self.hot[idx]
            self.virtual_liquid[idx] = self.liquid[idx]
            self.virtual_seeded[idx] = True
            self.anomaly[idx] = False

        effective_hot = []
        effective_liquid = []
        for idx in range(self.COUNT):
            label = self._idx_to_label(idx)
            simulated_hot, simulated_liquid = self._simulated_rack_values(label, idx)
            if label in self.real_rack_ids and self.virtual_seeded[idx]:
                effective_hot.append(simulated_hot)
                effective_liquid.append(simulated_liquid)
            else:
                effective_hot.append(self.hot[idx])
                effective_liquid.append(self.liquid[idx])

        maxA = max(effective_hot[i] for i in range(self.COUNT) if self._zone(i) == "A")
        maxB = max(effective_hot[i] for i in range(self.COUNT) if self._zone(i) == "B")
        qinA = sum(self.k_heat_equiv * self.heater_equivalent_w[i] for i in range(self.COUNT) if self._zone(i) == "A")
        qinB = sum(self.k_heat_equiv * self.heater_equivalent_w[i] for i in range(self.COUNT) if self._zone(i) == "B")
        peltier_coolA = self.k_peltier if peltierA_meas else 0.0
        peltier_coolB = self.k_peltier if peltierB_meas else 0.0

        self.supply_A = clamp(self.supply_A + self.alpha_supply * (qinA - self.k_cool * fanA_meas - peltier_coolA) * dt, 18.0, 45.0)
        self.supply_B = clamp(self.supply_B + self.alpha_supply * (qinB - self.k_cool * fanB_meas - peltier_coolB) * dt, 18.0, 45.0)

        zoneA_real = self._zone_real_state("A", now)
        zoneB_real = self._zone_real_state("B", now)
        zoneA_anomaly = self._zone_has_anomaly("A")
        zoneB_anomaly = self._zone_has_anomaly("B")
        peltierA_cmd = int(self.cdu_cmd.get("peltierA_pwm", 255 if self.cdu_cmd.get("peltierA_on", False) else 0))
        peltierB_cmd = int(self.cdu_cmd.get("peltierB_pwm", 255 if self.cdu_cmd.get("peltierB_on", False) else 0))
        fanA_prev = int(self.cdu_cmd.get("fanA_pwm", 0))
        fanB_prev = int(self.cdu_cmd.get("fanB_pwm", 0))
        if zoneA_real is not None:
            fanA_cmd = self._cooling_fan_cmd(zoneA_real.t_hot_real, zoneA_anomaly, fanA_prev)
            peltierA_cmd = self._cooling_peltier_cmd(zoneA_real.t_hot_real, zoneA_anomaly, peltierA_cmd)
        else:
            fanA_cmd = 0
            peltierA_cmd = 0
        if zoneB_real is not None:
            fanB_cmd = self._cooling_fan_cmd(zoneB_real.t_hot_real, zoneB_anomaly, fanB_prev)
            peltierB_cmd = self._cooling_peltier_cmd(zoneB_real.t_hot_real, zoneB_anomaly, peltierB_cmd)
        else:
            fanB_cmd = 0
            peltierB_cmd = 0
        if not zoneA_enabled:
            peltierA_cmd = 0
            self.supply_A = clamp(self.supply_A + (29.0 - self.supply_A) * 0.20 * dt, 18.0, 45.0)
        if not zoneB_enabled:
            peltierB_cmd = 0
            self.supply_B = clamp(self.supply_B + (29.0 - self.supply_B) * 0.20 * dt, 18.0, 45.0)

        self.cdu_cmd = {
            "type": "cdu_cmd",
            "id": "CDU1",
            "fanA_pwm": fanA_cmd,
            "fanB_pwm": fanB_cmd,
            "peltierA_pwm": peltierA_cmd,
            "peltierB_pwm": peltierB_cmd,
            "peltierA_on": peltierA_cmd > 0,
            "peltierB_on": peltierB_cmd > 0,
            "fallback_target": "maintain_supply",
            "t_supply_target": round((self.supply_A + self.supply_B) / 2.0, 2),
        }

        for idx in range(self.COUNT):
            label = self._idx_to_label(idx)
            real = self.racks_real.get(label)
            sensor_fallback = bool(real and self._fresh(real.received_ts, now) and not self._state_has_valid_sensor(real))
            if sensor_fallback:
                self.rack_cmds[label] = {
                    "type": "rack_cmd",
                    "id": label,
                    "fan_local_pwm": 0,
                    "heat_pwm": 0,
                    "mode": "sensor_fallback",
                    "anomaly": False,
                }
                continue
            real_guard_temp = (
                float(real.t_hot_real)
                if real and self._fresh(real.received_ts, now) and self._state_has_valid_sensor(real)
                else float(effective_hot[idx])
            )
            t = effective_hot[idx]
            guard = self.anomaly[idx] or real_guard_temp >= 75.0
            fan_cmd = 0
            heat_cmd = self._rack_heat_cmd(idx, now)
            self.rack_cmds[label] = {
                "type": "rack_cmd",
                "id": label,
                "fan_local_pwm": fan_cmd,
                "heat_pwm": heat_cmd,
                "mode": "guard" if guard else "heat-only-co-op",
                "anomaly": guard,
            }

        avg_hot = statistics.fmean(effective_hot)
        critical_idx = max(range(self.COUNT), key=lambda i: effective_hot[i])
        critical_temp = effective_hot[critical_idx]
        anomaly_count = sum(1 for i in range(self.COUNT) if self.anomaly[i])

        self.avg_history.append((now, float(avg_hot)))
        trend = self._trend(now)
        pred5 = max(20.0, avg_hot + trend * 5.0)

        power_idx = (fanA_cmd + fanB_cmd) / 510.0
        peltier_power_kw = 0.0095 * ((float(peltierA_cmd) + float(peltierB_cmd)) / 255.0)
        power_kw = round(power_idx * 2.4 + peltier_power_kw, 3)
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
            "heater_equivalent_target_w": round(self.heater_equivalent_target_w, 3),
            "virtual_ambient_c": round(self.virtual_ambient_c, 3),
            "stale_transition_seconds": round(self.stale_transition_seconds, 3),
            "cluster_heater_real_w": round(sum(self.heater_real_w), 4),
            "cluster_heater_equivalent_w": round(sum(self.heater_equivalent_w), 4),
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
            "peltierA_pwm": peltierA_cmd,
            "peltierB_pwm": peltierB_cmd,
            "peltierA_on": peltierA_cmd > 0,
            "peltierB_on": peltierB_cmd > 0,
        }

    def _legacy_response(self, cmd: dict, avg_hot: float) -> dict:
        return {
            "ok": True,
            "target_fan_pwm": int(cmd.get("fan_local_pwm", 0)),
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
            t_supply_a = finite_float(payload.get("t_supply_A", self.supply_A), self.supply_A)
            t_supply_b = finite_float(payload.get("t_supply_B", self.supply_B), self.supply_B)
            with self.lock:
                self.cdu_state = CduState(
                    cdu_id=str(payload.get("id", "CDU1") or "CDU1"),
                    fanA_pwm=clamp_pwm(payload.get("fanA_pwm", 160)),
                    fanB_pwm=clamp_pwm(payload.get("fanB_pwm", 160)),
                    peltierA_on=bool(payload.get("peltierA_on", False)),
                    peltierB_on=bool(payload.get("peltierB_on", False)),
                    t_supply_A=t_supply_a,
                    t_supply_B=t_supply_b,
                    received_ts=now,
                )
                self.messages_total += 1
                self._update_model(now)
                cmd = dict(self.cdu_cmd)
                cmd["server_time_ms"] = int(now * 1000)
                return cmd

        if msg_type == "rack_telemetry" or ("id" in payload and ("t_hot" in payload or "t_hot_real_c" in payload)):
            rid = self._normalize_id(str(payload.get("id", "")))
            if rid is None:
                return {"ok": False, "error": "invalid rack id"}
            if rid not in self.real_rack_ids:
                return {"ok": False, "error": f"rack id {rid} not allowed for real telemetry"}
            now = time.time()
            fan_pwm = clamp_pwm(payload.get("fan_local_pwm", 0))
            heat_pwm = clamp_pwm(payload.get("heat_pwm", 140))
            t_hot = finite_float(payload.get("t_hot_real_c", payload.get("t_hot")), None)
            if t_hot is None:
                return {"ok": False, "error": "invalid t_hot_real_c"}
            t_hot_source = str(payload.get("t_hot_source", "legacy")).strip().lower() or "legacy"
            t_liquid_source = str(payload.get("t_liquid_source", "legacy")).strip().lower() or "legacy"
            raw_liquid = payload.get("t_liquid_real_c", payload.get("t_liquid"))
            if t_liquid_source in ("unavailable", "missing", "none", "null"):
                raw_liquid = None
            t_liquid_real = None
            if raw_liquid is not None:
                t_liquid_real = finite_float(raw_liquid, None)
                if t_liquid_real is None:
                    return {"ok": False, "error": "invalid t_liquid_real_c"}
            sensor_ok = bool(payload.get("sensor_ok", True))
            telemetry_mode = str(payload.get("telemetry_mode", "")).strip().lower()
            local_anomaly = bool(payload.get("local_anomaly", False))
            heater_on = bool(payload.get("heater_on", heat_pwm > 0))
            heater_rated_power_w = finite_float(payload.get("heater_rated_power_w", 0.0), 0.0) or 0.0
            heater_avg_power_w = finite_float(
                payload.get(
                    "heater_avg_power_w",
                    heater_rated_power_w * (float(heat_pwm) / 255.0) if heater_rated_power_w > 0.0 else 0.0,
                ),
                0.0,
            )
            heater_real_w, heater_equivalent_w, heater_scale = self._heater_equivalent_power_w(
                heat_pwm,
                heater_rated_power_w,
                heater_avg_power_w,
            )
            device_ts_ms = finite_int(payload.get("ts", int(now * 1000)), int(now * 1000))
            idx = self._label_to_idx(rid)
            seed_liquid = None
            if idx is not None:
                seed_liquid = self.virtual_liquid[idx] if self.virtual_seeded[idx] else self.liquid[idx]
            if t_liquid_real is None and idx is not None:
                t_liquid = self._estimate_server_liquid(idx, t_hot, now, seed_liquid)
                t_liquid_source = "server_estimated"
                if t_hot_source == "sensor" and sensor_ok:
                    telemetry_mode = "measured_hot_server_estimated_liquid"
            else:
                t_liquid = t_liquid_real if t_liquid_real is not None else max(20.0, t_hot - 5.0)
            if not telemetry_mode:
                telemetry_mode = self._infer_telemetry_mode(t_hot_source, t_liquid_source, sensor_ok)

            ai_anom, detector_name = self.detector.detect([t_hot, t_liquid, float(heat_pwm)])
            ai_guard = bool(ai_anom and t_hot >= 26.0)
            anomaly = bool(local_anomaly or ai_guard or t_hot >= self.anomaly_temp_c)

            with self.lock:
                self.racks_real[rid] = RackState(
                    rack_id=rid,
                    t_hot_real=t_hot,
                    t_liquid_real=t_liquid_real,
                    t_liquid_effective=t_liquid,
                    t_hot_source=t_hot_source,
                    t_liquid_source=t_liquid_source,
                    telemetry_mode=telemetry_mode,
                    sensor_ok=sensor_ok,
                    fan_pwm=fan_pwm,
                    heat_pwm=heat_pwm,
                    heater_on=heater_on,
                    heater_rated_power_w=heater_rated_power_w,
                    heater_avg_power_w=heater_avg_power_w,
                    rssi=finite_int(payload.get("rssi", -60), -60),
                    anomaly=anomaly,
                    detector=detector_name,
                    device_ts_ms=device_ts_ms,
                    received_ts=now,
                )
                self.messages_total += 1
                if anomaly:
                    self.anomalies_total += 1
                self._append_hist(
                    rid,
                    {
                        "ts_ms": int(now * 1000),
                        "device_ts_ms": device_ts_ms,
                        "t_hot": t_hot,
                        "t_liquid": t_liquid,
                        "t_hot_real_c": t_hot,
                        "t_liquid_real_c": t_liquid_real,
                        "t_hot_source": t_hot_source,
                        "t_liquid_source": t_liquid_source,
                        "telemetry_mode": telemetry_mode,
                        "sensor_ok": sensor_ok,
                        "fan_local_pwm": fan_pwm,
                        "heat_pwm": heat_pwm,
                        "heater_on": heater_on,
                        "heater_rated_power_w": round(heater_rated_power_w, 4),
                        "heater_avg_power_w": round(heater_avg_power_w, 4),
                        "heater_real_w": round(heater_real_w, 4),
                        "heater_equivalent_w": round(heater_equivalent_w, 4),
                        "heater_scale_factor": round(heater_scale, 4),
                        "anomaly": anomaly,
                        "detector": detector_name,
                    },
                )
                self._update_model(now)
                hist_queue = self.rack_history.get(rid)
                idx = self._label_to_idx(rid)
                if hist_queue and idx is not None:
                    hist_queue[-1].update(
                        {
                            "t_hot_virtual_c": round(self.virtual_hot[idx], 4),
                            "t_liquid_virtual_c": round(self.virtual_liquid[idx], 4),
                            "heater_real_w": round(self.heater_real_w[idx], 4),
                            "heater_equivalent_w": round(self.heater_equivalent_w[idx], 4),
                            "heater_scale_factor": round(self.heater_scale[idx], 4),
                        }
                    )
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
                valid_real = self._state_has_valid_sensor(real)
                source_status, source_blend, telemetry_age_s, configured_real = self._rack_source_info(label, now)
                is_real = source_status == "real"
                cmd = self.rack_cmds.get(
                    label,
                    {
                        "fan_local_pwm": self.fan[idx],
                        "heat_pwm": self.heat[idx],
                        "mode": "heat-only-co-op",
                        "anomaly": self.anomaly[idx],
                    },
                )

                simulated_hot, simulated_liq = self._simulated_rack_values(label, idx)
                last_real_hot = float(real.t_hot_real) if valid_real and real else None
                last_real_liq = float(real.t_liquid_real) if valid_real and real and real.t_liquid_real is not None else None
                if source_status == "real" and real:
                    t_hot = float(real.t_hot_real)
                    t_liq = float(real.t_liquid_effective)
                elif source_status == "stale" and real:
                    t_hot = self._blend_value(float(real.t_hot_real), float(simulated_hot), source_blend)
                    t_liq = self._blend_value(float(real.t_liquid_effective), float(simulated_liq), source_blend)
                else:
                    t_hot = float(simulated_hot)
                    t_liq = float(simulated_liq)

                fan_pwm, heat_pwm, heater_on, anomaly = self._display_rack_actuation(idx, real, source_status, source_blend)

                racks.append(
                    {
                        "rack_id": idx,
                        "label": label,
                        "node_id": label if configured_real else None,
                        "configured_real": configured_real,
                        "is_real": is_real,
                        "online": is_real,
                        "source_status": source_status,
                        "source_blend": round(source_blend, 4),
                        "telemetry_age_ms": int(telemetry_age_s * 1000) if telemetry_age_s is not None else None,
                        "stale_after_ms": int(self.stale_seconds * 1000),
                        "simulated_after_ms": int((self.stale_seconds + self.stale_transition_seconds) * 1000),
                        "temp_hot": round(t_hot, 3),
                        "temp_liquid": round(t_liq, 3),
                        "temp_hot_real": round(last_real_hot, 3) if last_real_hot is not None else None,
                        "temp_liquid_real": round(last_real_liq, 3) if last_real_liq is not None else None,
                        "temp_hot_virtual": round(self.virtual_hot[idx], 3),
                        "temp_liquid_virtual": round(t_liq, 3),
                        "fan_pwm": fan_pwm,
                        "heat_pwm": heat_pwm,
                        "sensor_ok": bool(real.sensor_ok) if real else False,
                        "telemetry_mode": real.telemetry_mode if real else "modeled",
                        "t_hot_source": real.t_hot_source if real else "modeled",
                        "t_liquid_source": real.t_liquid_source if real else "modeled",
                        "heater_on": heater_on,
                        "heater_rated_power_w": round(real.heater_rated_power_w, 4) if real else 0.0,
                        "heater_avg_power_w": round(real.heater_avg_power_w, 4) if real else 0.0,
                        "heater_real_w": round(self.heater_real_w[idx], 4),
                        "heater_equivalent_w": round(self.heater_equivalent_w[idx], 4),
                        "heater_scale_factor": round(self.heater_scale[idx], 4),
                        "target_fan_pwm": int(cmd.get("fan_local_pwm", fan_pwm)),
                        "target_heat_pwm": int(cmd.get("heat_pwm", heat_pwm)),
                        "mode": cmd.get("mode", "co-op") if configured_real else "heat-only-co-op",
                        "detector": real.detector if real else "derived",
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
                "peltierA_on": self.cdu_state.peltierA_on if cdu_online and self.cdu_state else bool(self.cdu_cmd["peltierA_on"]),
                "peltierB_on": self.cdu_state.peltierB_on if cdu_online and self.cdu_state else bool(self.cdu_cmd["peltierB_on"]),
                "t_supply_A": round(self.supply_A, 3),
                "t_supply_B": round(self.supply_B, 3),
                "cmd_fanA_pwm": int(self.cdu_cmd["fanA_pwm"]),
                "cmd_fanB_pwm": int(self.cdu_cmd["fanB_pwm"]),
                "cmd_peltierA_on": bool(self.cdu_cmd["peltierA_on"]),
                "cmd_peltierB_on": bool(self.cdu_cmd["peltierB_on"]),
                "t_supply_target": self.cdu_cmd["t_supply_target"],
            }

            g = dict(self.global_state)
            stale_nodes = sum(1 for rack in racks if rack["source_status"] == "stale")
            simulated_nodes = sum(1 for rack in racks if rack["source_status"] == "simulated")
            g.update(
                {
                    "active_nodes": sum(1 for rack in racks if rack["is_real"]),
                    "stale_nodes": stale_nodes,
                    "simulated_nodes": simulated_nodes,
                    "configured_real_racks": sorted(self.real_rack_ids),
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
            nodes = {}
            node_ids = sorted(set(self.racks_real.keys()) | set(self.real_rack_ids))
            for rid in node_ids:
                idx = self._label_to_idx(rid)
                if idx is None:
                    continue
                state = self.racks_real.get(rid)
                valid_real = self._state_has_valid_sensor(state)
                source_status, source_blend, telemetry_age_s, configured_real = self._rack_source_info(rid, now)
                sim_hot, sim_liq = self._simulated_rack_values(rid, idx)
                if state is not None and source_status == "real":
                    display_hot = state.t_hot_real
                    display_liq = state.t_liquid_effective
                elif state is not None and source_status == "stale":
                    display_hot = self._blend_value(state.t_hot_real, sim_hot, source_blend)
                    display_liq = self._blend_value(state.t_liquid_effective, sim_liq, source_blend)
                else:
                    display_hot = sim_hot
                    display_liq = sim_liq
                fan_pwm, heat_pwm, heater_on, anomaly = self._display_rack_actuation(idx, state, source_status, source_blend)
                nodes[rid] = {
                    "id": rid,
                    "configured_real": configured_real,
                    "online": source_status == "real",
                    "source_status": source_status,
                    "source_blend": round(source_blend, 4),
                    "age_ms": int((telemetry_age_s or 0.0) * 1000) if telemetry_age_s is not None else None,
                    "stale_after_ms": int(self.stale_seconds * 1000),
                    "simulated_after_ms": int((self.stale_seconds + self.stale_transition_seconds) * 1000),
                    "device_ts_ms": state.device_ts_ms if state is not None else None,
                    "t_hot": round(display_hot, 3),
                    "t_liquid": round(display_liq, 3),
                    "t_hot_real": state.t_hot_real if valid_real and state is not None else None,
                    "t_liquid_real": state.t_liquid_real if valid_real and state is not None else None,
                    "t_hot_virtual": self.virtual_hot[idx],
                    "t_liquid_virtual": display_liq,
                    "t_hot_source": state.t_hot_source if state is not None else "modeled",
                    "t_liquid_source": state.t_liquid_source if state is not None else "modeled",
                    "telemetry_mode": state.telemetry_mode if state is not None else "modeled",
                    "sensor_ok": state.sensor_ok if state is not None else False,
                    "fan_local_pwm": fan_pwm,
                    "heat_pwm": heat_pwm,
                    "heater_on": heater_on,
                    "heater_rated_power_w": state.heater_rated_power_w if state is not None else 0.0,
                    "heater_avg_power_w": state.heater_avg_power_w if state is not None else 0.0,
                    "heater_real_w": self.heater_real_w[idx],
                    "heater_equivalent_w": self.heater_equivalent_w[idx],
                    "heater_scale_factor": self.heater_scale[idx],
                    "rssi": state.rssi if state is not None else None,
                    "detector": state.detector if state is not None else "derived",
                    "anomaly": anomaly,
                }
        return {
            "server_time_ms": int(now * 1000),
            "uptime_s": round(now - self.started_ts, 2),
            "active_nodes": sum(1 for node in nodes.values() if node["online"]),
            "stale_nodes": sum(1 for node in nodes.values() if node["source_status"] == "stale"),
            "simulated_nodes": sum(1 for node in nodes.values() if node["source_status"] == "simulated"),
            "configured_real_racks": sorted(self.real_rack_ids),
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
                    "real_rack_ids": sorted(self.core.real_rack_ids),
                    "stale_transition_seconds": self.core.stale_transition_seconds,
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
        async with AsyncExitStack() as stack:
            enabled = False
            if self.twin_enabled:
                await stack.enter_async_context(
                    ws_serve(
                        self._twin_handler,
                        self.twin_host,
                        self.twin_port,
                        ping_interval=20,
                        ping_timeout=20,
                        process_request=self._permissive_process_request,
                    )
                )
                safe_log(f"[ws-twin] serving on ws://{self.twin_host}:{self.twin_port}")
                enabled = True
            if self.edge_enabled:
                await stack.enter_async_context(
                    ws_serve(
                        self._edge_handler,
                        self.edge_host,
                        self.edge_port,
                        ping_interval=20,
                        ping_timeout=20,
                        process_request=self._permissive_process_request,
                    )
                )
                safe_log(f"[ws-edge] serving on ws://{self.edge_host}:{self.edge_port}")
                enabled = True
            if not enabled:
                return
            while not self.stop_event.is_set():
                await asyncio.sleep(0.2)

    async def _permissive_process_request(self, connection, request):
        """Accept WebSocket connections regardless of Connection header value."""
        return None

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
    parser.add_argument("--real-racks", default="R00,R07", help="comma-separated real rack ids, e.g. R00,R07")
    parser.add_argument("--heater-equivalent-target-w", default=1.44, type=float, help="virtual heater target power per rack; defaults to the real 1.44 W heater")
    parser.add_argument("--heater-default-power-w", default=1.44, type=float, help="default physical heater rated power when rack telemetry omits it")
    parser.add_argument("--virtual-ambient-c", default=26.0, type=float, help="ambient baseline for the virtual rack model")
    parser.add_argument("--anomaly-temp-c", default=80.0, type=float, help="rack anomaly threshold used by the server")
    parser.add_argument("--stale-transition-seconds", default=4.0, type=float, help="seconds to blend from last real telemetry to simulated values after stale timeout")

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
    real_rack_ids = parse_real_rack_ids(args.real_racks)
    core = DigitalTwinCore(
        detector,
        args.stale_seconds,
        max(60, args.history_limit),
        real_rack_ids,
        args.heater_equivalent_target_w,
        args.heater_default_power_w,
        args.virtual_ambient_c,
        args.stale_transition_seconds,
        args.anomaly_temp_c,
    )

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
