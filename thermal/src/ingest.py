"""
Load thermal frames from disk or generate synthetic sequences for testing.

A thermal frame is a 2-D float32 numpy array where each value is degrees Celsius.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

import numpy as np
import cv2


@dataclass
class ThermalFrame:
    data: np.ndarray          # shape (H, W), dtype float32, values in °C
    timestamp: float          # seconds since sequence start
    frame_index: int
    metadata: dict = field(default_factory=dict)

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

class HeatSource:
    """A Gaussian heat blob that can drift and pulse over time."""

    def __init__(
        self,
        cx: float, cy: float,
        peak_temp: float,
        sigma: float,
        drift_x: float = 0.0,
        drift_y: float = 0.0,
        pulse_amplitude: float = 0.0,
        pulse_period: float = 10.0,
    ):
        self.cx = cx
        self.cy = cy
        self.peak_temp = peak_temp
        self.sigma = sigma
        self.drift_x = drift_x
        self.drift_y = drift_y
        self.pulse_amplitude = pulse_amplitude
        self.pulse_period = pulse_period

    def temperature_at(self, xs: np.ndarray, ys: np.ndarray, t: float) -> np.ndarray:
        cx = self.cx + self.drift_x * t
        cy = self.cy + self.drift_y * t
        peak = self.peak_temp + self.pulse_amplitude * np.sin(2 * np.pi * t / self.pulse_period)
        dist2 = (xs - cx) ** 2 + (ys - cy) ** 2
        return peak * np.exp(-dist2 / (2 * self.sigma ** 2))


def generate_sequence(
    n_frames: int = 60,
    width: int = 320,
    height: int = 240,
    fps: float = 10.0,
    ambient_temp: float = 22.0,
    noise_std: float = 0.3,
    sources: list[HeatSource] | None = None,
    seed: int | None = 42,
) -> list[ThermalFrame]:
    """
    Generate a synthetic thermal sequence.

    If *sources* is None, two heat sources with slight drift are created
    automatically — useful for quick smoke-tests.
    """
    rng = np.random.default_rng(seed)

    if sources is None:
        sources = [
            HeatSource(
                cx=width * 0.35, cy=height * 0.4,
                peak_temp=18.0, sigma=30.0,
                drift_x=0.4, drift_y=0.15,
                pulse_amplitude=3.0, pulse_period=8.0,
            ),
            HeatSource(
                cx=width * 0.7, cy=height * 0.6,
                peak_temp=12.0, sigma=20.0,
                drift_x=-0.2, drift_y=0.05,
                pulse_amplitude=1.5, pulse_period=12.0,
            ),
        ]

    xs, ys = np.meshgrid(np.arange(width, dtype=np.float32),
                         np.arange(height, dtype=np.float32))
    frames: list[ThermalFrame] = []

    for i in range(n_frames):
        t = i / fps
        frame = np.full((height, width), ambient_temp, dtype=np.float32)
        for src in sources:
            frame += src.temperature_at(xs, ys, t).astype(np.float32)
        frame += rng.normal(0.0, noise_std, frame.shape).astype(np.float32)
        frames.append(ThermalFrame(data=frame, timestamp=t, frame_index=i))

    return frames


# ---------------------------------------------------------------------------
# File-based loading  (16-bit PNG / TIFF → °C, or raw CSV grid)
# ---------------------------------------------------------------------------

# Linear mapping constants for 16-bit radiometric PNGs (e.g. FLIR Lepton).
# pixel_value = (temp_celsius + OFFSET) * SCALE
_RADIOMETRIC_SCALE = 100.0
_RADIOMETRIC_OFFSET = 273.15   # stored as Kelvin * 100


def load_frame(path: str | Path, fps: float = 10.0, frame_index: int = 0) -> ThermalFrame:
    """
    Load a single thermal frame from disk.

    Supported formats
    -----------------
    * 16-bit PNG / TIFF  — interpreted as (value / scale) - offset  → °C
    * 8-bit PNG / JPEG   — pixel values linearly mapped to [0, 100] °C
    * .npy               — raw float32 array already in °C
    * .csv               — comma-separated float grid in °C
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".npy":
        data = np.load(path).astype(np.float32)
    elif suffix == ".csv":
        data = np.loadtxt(path, delimiter=",", dtype=np.float32)
    else:
        img = cv2.imread(str(path), cv2.IMREAD_ANYDEPTH | cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(f"Cannot read image: {path}")
        if img.dtype == np.uint16:
            data = (img.astype(np.float32) / _RADIOMETRIC_SCALE) - _RADIOMETRIC_OFFSET
        else:
            data = img.astype(np.float32) / 255.0 * 100.0

    return ThermalFrame(
        data=data,
        timestamp=frame_index / fps,
        frame_index=frame_index,
        metadata={"source": str(path)},
    )


def load_sequence(
    directory: str | Path,
    pattern: str = "*",
    fps: float = 10.0,
) -> list[ThermalFrame]:
    """
    Load all matching files in *directory* sorted by name.

    Example
    -------
    >>> frames = load_sequence("data/run01", pattern="*.png", fps=9.0)
    """
    directory = Path(directory)
    paths = sorted(directory.glob(pattern))
    if not paths:
        raise FileNotFoundError(f"No files matching '{pattern}' in {directory}")
    return [load_frame(p, fps=fps, frame_index=i) for i, p in enumerate(paths)]


def iter_sequence(frames: list[ThermalFrame]) -> Iterator[ThermalFrame]:
    """Yield frames one by one — convenient for streaming pipelines."""
    yield from frames
