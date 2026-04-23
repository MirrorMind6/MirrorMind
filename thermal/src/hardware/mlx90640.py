"""
MLX90640 32×24 thermal camera driver.

Real driver
-----------
Requires an MLX90640 breakout wired to the Pi's I2C bus (SDA=GPIO2, SCL=GPIO3)
and the Adafruit CircuitPython library:

    pip install adafruit-circuitpython-mlx90640

Mock driver
-----------
MockMLX90640 generates a realistic 32×24 temperature grid using the same
Gaussian heat-source model as src/ingest.py — no hardware required.

Usage
-----
    # Simulation (no hardware)
    cam = MockMLX90640(sensor_id="mlx_0", n_sources=2)

    # Real Pi hardware (swap in when ready)
    # cam = MLX90640Driver(sensor_id="mlx_0", refresh_rate=4)

    with cam:
        reading = cam.read()   # → SensorReading with 32×24 float array in metadata
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ..fusion import SensorReading, SensorType
from .base import SensorDriver


# ---------------------------------------------------------------------------
# Real hardware driver (Pi only)
# ---------------------------------------------------------------------------

class MLX90640Driver(SensorDriver):
    """
    Live MLX90640 driver — runs on Raspberry Pi with the sensor wired to I2C.

    TO ENABLE ON PI:
      1. Enable I2C: sudo raspi-config → Interface Options → I2C → Yes
      2. pip install adafruit-circuitpython-mlx90640
      3. Replace MockMLX90640 with MLX90640Driver in runner.py
    """

    def __init__(self, sensor_id: str = "mlx_0", refresh_rate: int = 4):
        super().__init__(sensor_id)
        self._refresh_rate = refresh_rate
        self._sensor = None
        self._connect()

    def _connect(self):
        try:
            import board
            import busio
            import adafruit_mlx90640
            i2c = busio.I2C(board.SCL, board.SDA, frequency=400_000)
            self._sensor = adafruit_mlx90640.MLX90640(i2c)
            self._sensor.refresh_rate = getattr(
                adafruit_mlx90640.RefreshRate, f"REFRESH_{self._refresh_rate}HZ"
            )
        except Exception as exc:
            raise RuntimeError(
                "MLX90640 not found. Check I2C wiring and that "
                "adafruit-circuitpython-mlx90640 is installed."
            ) from exc

    def read(self) -> SensorReading:
        frame = [0.0] * 768   # 32 × 24
        self._sensor.getFrame(frame)
        grid = np.array(frame, dtype=np.float32).reshape(24, 32)
        mean_temp = float(grid.mean())
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=SensorType.THERMAL_POINT,
            value=mean_temp,
            timestamp=time.monotonic(),
            unit="°C",
            metadata={"grid": grid, "shape": (24, 32)},
        )

    def close(self):
        self._sensor = None


# ---------------------------------------------------------------------------
# Mock driver
# ---------------------------------------------------------------------------

@dataclass
class _MockSource:
    cx: float
    cy: float
    peak: float
    sigma: float
    drift_x: float
    drift_y: float
    pulse_amp: float
    pulse_period: float


class MockMLX90640(SensorDriver):
    """
    Simulated MLX90640 — produces a realistic 32×24 thermal grid.

    Parameters
    ----------
    n_sources    : number of Gaussian heat sources in the scene
    ambient_temp : background temperature in °C
    noise_std    : sensor noise standard deviation in °C
    anomaly_after: seconds after start when a hot source ramps up
                   (simulates a person entering the frame)
    seed         : RNG seed for reproducibility
    """

    WIDTH  = 32
    HEIGHT = 24

    def __init__(
        self,
        sensor_id: str = "mlx_0",
        n_sources: int = 1,
        ambient_temp: float = 22.0,
        noise_std: float = 0.4,
        anomaly_after: float = 15.0,
        seed: int = 42,
    ):
        super().__init__(sensor_id)
        self._ambient = ambient_temp
        self._noise_std = noise_std
        self._anomaly_after = anomaly_after
        self._start = time.monotonic()
        self._rng = np.random.default_rng(seed)

        # Fixed heat sources (e.g. background electronics)
        self._sources = [
            _MockSource(
                cx=self.WIDTH  * self._rng.uniform(0.2, 0.8),
                cy=self.HEIGHT * self._rng.uniform(0.2, 0.8),
                peak=float(self._rng.uniform(3.0, 8.0)),
                sigma=float(self._rng.uniform(2.0, 4.0)),
                drift_x=float(self._rng.uniform(-0.02, 0.02)),
                drift_y=float(self._rng.uniform(-0.01, 0.01)),
                pulse_amp=float(self._rng.uniform(0.5, 1.5)),
                pulse_period=float(self._rng.uniform(8.0, 15.0)),
            )
            for _ in range(n_sources)
        ]

        # The "person" source — starts cold, heats up after anomaly_after seconds
        self._person = _MockSource(
            cx=self.WIDTH * 0.5,
            cy=self.HEIGHT * 0.4,
            peak=0.0,       # starts absent
            sigma=3.5,
            drift_x=0.0,
            drift_y=0.0,
            pulse_amp=0.3,
            pulse_period=6.0,
        )

        xs, ys = np.meshgrid(
            np.arange(self.WIDTH, dtype=np.float32),
            np.arange(self.HEIGHT, dtype=np.float32),
        )
        self._xs = xs
        self._ys = ys

    def _gaussian(self, src: _MockSource, t: float) -> np.ndarray:
        cx = src.cx + src.drift_x * t
        cy = src.cy + src.drift_y * t
        peak = src.peak + src.pulse_amp * np.sin(2 * np.pi * t / src.pulse_period)
        dist2 = (self._xs - cx) ** 2 + (self._ys - cy) ** 2
        return peak * np.exp(-dist2 / (2 * src.sigma ** 2))

    def read(self) -> SensorReading:
        t = time.monotonic() - self._start
        grid = np.full((self.HEIGHT, self.WIDTH), self._ambient, dtype=np.float32)

        for src in self._sources:
            grid += self._gaussian(src, t).astype(np.float32)

        # Person arrives after anomaly_after seconds; body temp ramps toward +14°C
        if t >= self._anomaly_after:
            ramp = min((t - self._anomaly_after) * 0.8, 14.0)
            self._person.peak = ramp
            grid += self._gaussian(self._person, t).astype(np.float32)

        grid += self._rng.normal(0, self._noise_std, grid.shape).astype(np.float32)

        mean_temp = float(grid.mean())
        return SensorReading(
            sensor_id=self.sensor_id,
            sensor_type=SensorType.THERMAL_POINT,
            value=mean_temp,
            timestamp=time.monotonic(),
            unit="°C",
            metadata={"grid": grid, "shape": (self.HEIGHT, self.WIDTH)},
        )
