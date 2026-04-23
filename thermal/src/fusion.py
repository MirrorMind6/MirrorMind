"""
Sensor fusion layer.

Instead of processing full video frames, this module works with lightweight
*data points* sampled from a small set of fixed sensor positions plus any
number of auxiliary sensors (humidity, proximity, motion, etc.).

The pipeline:
  1. Each tick, collect one SensorReading per sensor node.
  2. Accumulate readings into a FusionBuffer.
  3. Call FusionBuffer.evaluate() to get a FusionEvent with a decision +
     confidence score derived from the fused signal.

This keeps retained data tiny: O(window_size × n_sensors) floats rather
than O(window_size × H × W) pixels.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np
from sklearn.linear_model import LinearRegression


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class SensorType(str, Enum):
    THERMAL_POINT = "thermal_point"   # temperature at a fixed spatial point
    HUMIDITY      = "humidity"
    PROXIMITY     = "proximity"       # distance (cm)
    MOTION        = "motion"          # binary or 0–1 magnitude
    AMBIENT_LIGHT = "ambient_light"
    CUSTOM        = "custom"


@dataclass
class SensorReading:
    sensor_id: str
    sensor_type: SensorType
    value: float
    timestamp: float = field(default_factory=time.monotonic)
    unit: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class FusionSnapshot:
    """One instant in time: a dict of sensor_id → value, all normalised [0, 1]."""
    timestamp: float
    readings: dict[str, float]       # normalised values
    raw: dict[str, float]            # original values before normalisation


class Decision(str, Enum):
    NORMAL   = "normal"
    WARNING  = "warning"
    ALERT    = "alert"
    UNKNOWN  = "unknown"


@dataclass
class FusionEvent:
    decision: Decision
    confidence: float          # 0–1
    timestamp: float
    dominant_sensor: str       # which sensor drove the decision
    snapshot: FusionSnapshot
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

# Expected operating ranges per sensor type: (min, max)
_DEFAULT_RANGES: dict[SensorType, tuple[float, float]] = {
    SensorType.THERMAL_POINT: (18.0, 42.0),    # °C  — room temp to above body temp
    SensorType.HUMIDITY:      (0.0, 100.0),    # %RH
    SensorType.PROXIMITY:     (0.0, 400.0),    # cm
    SensorType.MOTION:        (0.0, 1.0),
    SensorType.AMBIENT_LIGHT: (0.0, 10000.0),  # lux
    SensorType.CUSTOM:        (0.0, 1.0),
}


def normalise(value: float, sensor_type: SensorType,
              range_override: tuple[float, float] | None = None) -> float:
    lo, hi = range_override or _DEFAULT_RANGES[sensor_type]
    return float(np.clip((value - lo) / (hi - lo + 1e-9), 0.0, 1.0))


# ---------------------------------------------------------------------------
# Fusion buffer
# ---------------------------------------------------------------------------

class FusionBuffer:
    """
    Sliding-window buffer that accumulates SensorReadings and evaluates them.

    Parameters
    ----------
    window_size    : number of snapshots to retain for trend analysis
    sensor_ranges  : optional per-sensor (min, max) overrides for normalisation
    thresholds     : (warning_score, alert_score) for the fusion score in [0,1]
    """

    def __init__(
        self,
        window_size: int = 30,
        sensor_ranges: dict[str, tuple[float, float]] | None = None,
        thresholds: tuple[float, float] = (0.55, 0.75),
    ):
        self.window_size = window_size
        self.sensor_ranges = sensor_ranges or {}
        self.warn_threshold, self.alert_threshold = thresholds
        self._buffer: deque[FusionSnapshot] = deque(maxlen=window_size)
        self._pending: dict[str, SensorReading] = {}
        self._sensor_types: dict[str, SensorType] = {}

    # ------------------------------------------------------------------
    # Ingest

    def push(self, reading: SensorReading) -> None:
        """Accept a new sensor reading. Call commit() to finalise a snapshot."""
        self._pending[reading.sensor_id] = reading
        self._sensor_types[reading.sensor_id] = reading.sensor_type

    def commit(self, timestamp: float | None = None) -> FusionSnapshot | None:
        """
        Freeze the current pending readings as one snapshot and add it to
        the buffer. Returns None if no pending readings exist.
        """
        if not self._pending:
            return None
        ts = timestamp or time.monotonic()
        raw = {sid: r.value for sid, r in self._pending.items()}
        normalised = {
            sid: normalise(
                r.value,
                r.sensor_type,
                self.sensor_ranges.get(sid),
            )
            for sid, r in self._pending.items()
        }
        snap = FusionSnapshot(timestamp=ts, readings=normalised, raw=raw)
        self._buffer.append(snap)
        self._pending.clear()
        return snap

    # ------------------------------------------------------------------
    # Evaluate

    def evaluate(self) -> FusionEvent:
        """
        Compute a fusion score from the current buffer and return a FusionEvent.

        Fusion strategy
        ---------------
        * Weighted mean of the latest normalised sensor values.
        * Thermal-point sensors get double weight (primary signal).
        * A rising trend over the window adds a momentum bonus.
        * The final score maps to NORMAL / WARNING / ALERT.
        """
        if not self._buffer:
            snap = FusionSnapshot(timestamp=time.monotonic(), readings={}, raw={})
            return FusionEvent(
                decision=Decision.UNKNOWN,
                confidence=0.0,
                timestamp=snap.timestamp,
                dominant_sensor="none",
                snapshot=snap,
                notes=["Buffer is empty"],
            )

        latest = self._buffer[-1]

        # --- Weighted score from latest snapshot ---
        weights: dict[str, float] = {}
        for sid, stype in self._sensor_types.items():
            if stype == SensorType.THERMAL_POINT:
                weights[sid] = 2.0
            elif stype == SensorType.MOTION:
                weights[sid] = 1.5
            else:
                weights[sid] = 1.0

        total_w = 0.0
        weighted_sum = 0.0
        for sid, norm_val in latest.readings.items():
            w = weights.get(sid, 1.0)
            weighted_sum += norm_val * w
            total_w += w

        base_score = weighted_sum / total_w if total_w > 0 else 0.0

        # --- Trend momentum bonus ---
        trend_bonus = 0.0
        if len(self._buffer) >= 3:
            trend_bonus = self._compute_trend_bonus()

        score = float(np.clip(base_score + trend_bonus, 0.0, 1.0))

        # --- Dominant sensor (highest normalised contribution) ---
        dominant = max(latest.readings, key=lambda s: latest.readings[s] * weights.get(s, 1.0),
                       default="none")

        # --- Decision ---
        notes: list[str] = []
        if score >= self.alert_threshold:
            decision = Decision.ALERT
            notes.append(f"Score {score:.2f} ≥ alert threshold {self.alert_threshold}")
        elif score >= self.warn_threshold:
            decision = Decision.WARNING
            notes.append(f"Score {score:.2f} ≥ warning threshold {self.warn_threshold}")
        else:
            decision = Decision.NORMAL

        if trend_bonus > 0.05:
            notes.append(f"Rising trend contributing +{trend_bonus:.2f} to score")

        return FusionEvent(
            decision=decision,
            confidence=score,
            timestamp=latest.timestamp,
            dominant_sensor=dominant,
            snapshot=latest,
            notes=notes,
        )

    def _compute_trend_bonus(self) -> float:
        """Linear slope of the mean sensor score over the window, capped at 0.15."""
        times = np.array([s.timestamp for s in self._buffer]).reshape(-1, 1)
        means = np.array([
            np.mean(list(s.readings.values())) if s.readings else 0.0
            for s in self._buffer
        ])
        if (times.max() - times.min()) < 1e-6:
            return 0.0
        slope = float(LinearRegression().fit(times, means).coef_[0])
        return float(np.clip(slope * 10.0, 0.0, 0.15))   # only rising trend counts


# ---------------------------------------------------------------------------
# Synthetic sensor stream generator (for testing without hardware)
# ---------------------------------------------------------------------------

def generate_sensor_stream(
    n_ticks: int = 100,
    dt: float = 0.5,
    n_thermal_points: int = 4,
    include_humidity: bool = True,
    include_motion: bool = True,
    anomaly_start: int = 60,
    seed: int = 42,
) -> list[list[SensorReading]]:
    """
    Produce a synthetic multi-sensor stream.

    Each tick contains one reading per enabled sensor.  An anomaly
    (rising temperature + motion trigger) starts at *anomaly_start*.

    Returns a list of ticks; each tick is a list of SensorReadings.
    """
    rng = np.random.default_rng(seed)
    stream: list[list[SensorReading]] = []

    base_temps = rng.uniform(20.0, 28.0, n_thermal_points)

    for tick in range(n_ticks):
        t = tick * dt
        readings: list[SensorReading] = []
        in_anomaly = tick >= anomaly_start
        ramp = (tick - anomaly_start) * 0.4 if in_anomaly else 0.0

        for i in range(n_thermal_points):
            noise = float(rng.normal(0, 0.3))
            temp = base_temps[i] + ramp + noise
            readings.append(SensorReading(
                sensor_id=f"thermal_{i}",
                sensor_type=SensorType.THERMAL_POINT,
                value=temp,
                timestamp=t,
                unit="°C",
            ))

        if include_humidity:
            hum = 45.0 + float(rng.normal(0, 2))
            readings.append(SensorReading(
                sensor_id="humidity_0",
                sensor_type=SensorType.HUMIDITY,
                value=hum,
                timestamp=t,
                unit="%RH",
            ))

        if include_motion:
            motion = 0.8 if in_anomaly and rng.random() > 0.3 else float(rng.random() * 0.15)
            readings.append(SensorReading(
                sensor_id="motion_0",
                sensor_type=SensorType.MOTION,
                value=motion,
                timestamp=t,
            ))

        stream.append(readings)

    return stream
