"""
Dataset loader and merger for FIR Action Dataset + UCI Room Occupancy.

Since the datasets are from different labs/hardware, we align them on a
synthetic shared timeline — treating every occupancy→present transition in
UCI as simultaneous with a person appearing in the FIR thermal grid.

Real dataset locations (download once and point DATA_DIR at them):
  FIR Action Dataset  → https://github.com/visiongo-kr/FIR-Image-Action-Dataset
  UCI Room Occupancy  → https://archive.ics.uci.edu/dataset/864/room+occupancy+estimation

If neither is present on disk, synthetic versions that exactly mirror
their column schemas and statistical profiles are generated automatically.

Output
------
merge_datasets() → pandas DataFrame with one row per second:

  timestamp       float   seconds from t=0
  # --- from UCI ---
  pir             float   0/1 — presence signal derived from occupancy changes
  occupancy       int     0-3 people count
  ambient_temp    float   °C
  humidity        float   %RH
  co2             float   ppm
  light           float   lux
  # --- from FIR thermal grid ---
  grid_mean       float   mean temperature of 32×24 grid  (°C)
  grid_peak       float   max temperature of grid (°C)
  grid_above_amb  float   grid_peak − ambient_temp (°C above room)
  hotspot_count   int     number of detected hotspots
  hotspot_cx      float   centroid x of largest hotspot (or NaN)
  hotspot_cy      float   centroid y of largest hotspot (or NaN)
  thermal_trigger int     1 when grid_above_amb crosses detection threshold
  # --- ground truth ---
  occupied        int     1/0 from UCI occupancy > 0
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .ingest import ThermalFrame
from .extract import find_hotspots

# ── Configurable paths ────────────────────────────────────────────────────────
FIR_DATA_DIR = Path("data/fir_dataset")
UCI_DATA_DIR = Path("data/uci_occupancy")

# Thermal detection threshold: degrees above ambient to flag a hotspot
THERMAL_DELTA_THRESHOLD = 4.0   # °C


# ═══════════════════════════════════════════════════════════════════════════
# Real dataset loaders
# ═══════════════════════════════════════════════════════════════════════════

def load_uci(directory: Path = UCI_DATA_DIR) -> pd.DataFrame:
    """
    Load UCI Room Occupancy CSV files.

    Expected columns (from the dataset):
      date, S1_Temp, S2_Temp, S3_Temp, S4_Temp,
      S1_Light, S2_Light, S3_Light, S4_Light,
      S1_Sound, S2_Sound, S3_Sound, S4_Sound,
      S5_CO2, S5_CO2_Slope, S6_PIR, S7_PIR, Room_Occupancy_Count
    """
    csv_files = sorted(directory.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {directory}")

    frames = []
    for f in csv_files:
        df = pd.read_csv(f, parse_dates=["date"])
        frames.append(df)
    raw = pd.concat(frames).sort_values("date").reset_index(drop=True)

    out = pd.DataFrame()
    out["timestamp"]    = (raw["date"] - raw["date"].iloc[0]).dt.total_seconds()
    out["occupancy"]    = raw["Room_Occupancy_Count"].astype(int)
    out["occupied"]     = (out["occupancy"] > 0).astype(int)
    out["pir"]          = (raw[["S6_PIR", "S7_PIR"]].max(axis=1) > 0).astype(float)
    out["ambient_temp"] = raw[["S1_Temp", "S2_Temp", "S3_Temp", "S4_Temp"]].mean(axis=1)
    out["light"]        = raw[["S1_Light", "S2_Light", "S3_Light", "S4_Light"]].mean(axis=1)
    out["co2"]          = raw["S5_CO2"]
    out["humidity"]     = raw.get("S1_Humidity", pd.Series(np.nan, index=raw.index))
    return out


def load_fir(directory: Path = FIR_DATA_DIR, ambient_col: pd.Series | None = None) -> pd.DataFrame:
    """
    Load FIR Action Dataset CSV files.

    Each CSV row is one frame: 768 columns of float temperatures (32×24)
    plus optional metadata columns (timestamp, label, etc.).
    Detects hotspots per frame and produces scalar features.
    """
    csv_files = sorted(directory.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {directory}")

    rows = []
    t = 0.0
    for f in csv_files:
        raw = pd.read_csv(f, header=None)
        temp_cols = raw.shape[1]
        # Support 768-column (pure grid) or wider files with metadata appended
        grid_cols = min(temp_cols, 768)
        for i, row in raw.iterrows():
            grid = row.values[:grid_cols].astype(np.float32).reshape(24, 32)
            frame = ThermalFrame(data=grid, timestamp=t, frame_index=i)
            hotspots = find_hotspots(frame, threshold_percentile=88, min_pixels=3)
            rows.append({
                "timestamp":   t,
                "grid_mean":   float(grid.mean()),
                "grid_peak":   float(grid.max()),
                "hotspot_count": len(hotspots),
                "hotspot_cx":  hotspots[0].centroid_x if hotspots else np.nan,
                "hotspot_cy":  hotspots[0].centroid_y if hotspots else np.nan,
            })
            t += 0.1   # assume 10 fps if no timestamp column

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# Synthetic generators  (used when real data isn't on disk)
# ═══════════════════════════════════════════════════════════════════════════

def _synthetic_uci(n_seconds: int = 600, seed: int = 42) -> pd.DataFrame:
    """Synthetic UCI-schema data with 3 presence events."""
    rng = np.random.default_rng(seed)
    ts  = np.arange(n_seconds, dtype=float)

    occupancy   = np.zeros(n_seconds, dtype=int)
    ambient     = rng.normal(21.5, 0.3, n_seconds)
    humidity    = rng.normal(47.0, 1.0, n_seconds)
    co2         = rng.normal(450,  20,  n_seconds)
    light       = rng.normal(200,  30,  n_seconds)
    pir         = np.zeros(n_seconds)

    # Three presence events: t=60, t=250, t=450 — each lasts ~90s
    events = [(60, 150), (250, 340), (450, 540)]
    for start, end in events:
        occupancy[start:end] = rng.integers(1, 3, size=end - start)
        pir[max(0, start - 2): end + 5] = 1.0
        ambient[start:end] += rng.uniform(0.3, 0.8, end - start)
        co2[start:end]     += rng.uniform(20, 60, end - start)

    return pd.DataFrame({
        "timestamp":    ts,
        "occupancy":    occupancy,
        "occupied":     (occupancy > 0).astype(int),
        "pir":          pir,
        "ambient_temp": ambient,
        "humidity":     humidity,
        "co2":          co2,
        "light":        light,
    })


def _synthetic_fir(n_seconds: int = 600, seed: int = 42) -> pd.DataFrame:
    """Synthetic FIR-schema data aligned with _synthetic_uci events."""
    rng  = np.random.default_rng(seed)
    ts   = np.arange(n_seconds, dtype=float)
    rows = []

    # Same events as UCI but thermal lags PIR by ~2 seconds
    events = [(62, 150), (252, 340), (452, 540)]

    xs, ys = np.meshgrid(np.arange(32, dtype=np.float32),
                         np.arange(24, dtype=np.float32))

    for t in range(n_seconds):
        ambient = 21.5 + rng.normal(0, 0.3)
        grid    = np.full((24, 32), ambient, dtype=np.float32)

        # Add body-heat blob during events
        in_event = any(s <= t < e for s, e in events)
        if in_event:
            cx   = 16.0 + rng.normal(0, 1)
            cy   = 10.0 + rng.normal(0, 1)
            peak = rng.uniform(10.0, 14.0)
            dist2 = (xs - cx) ** 2 + (ys - cy) ** 2
            grid += (peak * np.exp(-dist2 / (2 * 3.5 ** 2))).astype(np.float32)

        grid += rng.normal(0, 0.35, grid.shape).astype(np.float32)

        frame    = ThermalFrame(data=grid, timestamp=float(t), frame_index=t)
        hotspots = find_hotspots(frame, threshold_percentile=88, min_pixels=3)

        rows.append({
            "timestamp":     float(t),
            "grid_mean":     float(grid.mean()),
            "grid_peak":     float(grid.max()),
            "hotspot_count": len(hotspots),
            "hotspot_cx":    hotspots[0].centroid_x if hotspots else np.nan,
            "hotspot_cy":    hotspots[0].centroid_y if hotspots else np.nan,
        })

    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════════════════════════════
# Merge
# ═══════════════════════════════════════════════════════════════════════════

def merge_datasets(
    n_seconds: int = 600,
    seed: int = 42,
    fir_dir:  Path = FIR_DATA_DIR,
    uci_dir:  Path = UCI_DATA_DIR,
) -> pd.DataFrame:
    """
    Load (or generate) both datasets and return a merged DataFrame
    aligned on a shared 1-second time grid.

    Falls back to synthetic data if real files aren't present.
    """
    # UCI
    try:
        uci = load_uci(uci_dir)
        print("[datasets] Loaded real UCI occupancy data.")
    except FileNotFoundError:
        print("[datasets] UCI data not found — using synthetic.")
        uci = _synthetic_uci(n_seconds, seed)

    # FIR
    try:
        fir = load_fir(fir_dir)
        print("[datasets] Loaded real FIR thermal data.")
    except FileNotFoundError:
        print("[datasets] FIR data not found — using synthetic.")
        fir = _synthetic_fir(n_seconds, seed)

    # Resample both to integer-second ticks
    uci["tick"] = uci["timestamp"].round().astype(int)
    fir["tick"] = fir["timestamp"].round().astype(int)

    uci_r = uci.groupby("tick").agg({
        "occupancy":    "max",
        "occupied":     "max",
        "pir":          "max",
        "ambient_temp": "mean",
        "humidity":     "mean",
        "co2":          "mean",
        "light":        "mean",
    }).reset_index().rename(columns={"tick": "timestamp"})

    fir_r = fir.groupby("tick").agg({
        "grid_mean":     "mean",
        "grid_peak":     "max",
        "hotspot_count": "max",
        "hotspot_cx":    "mean",
        "hotspot_cy":    "mean",
    }).reset_index().rename(columns={"tick": "timestamp"})

    merged = pd.merge(uci_r, fir_r, on="timestamp", how="inner")

    # Derived columns
    merged["grid_above_amb"]   = merged["grid_peak"] - merged["ambient_temp"]
    merged["thermal_trigger"]  = (
        merged["grid_above_amb"] >= THERMAL_DELTA_THRESHOLD
    ).astype(int)
    merged["dual_trigger"]     = (
        (merged["pir"] > 0) & (merged["thermal_trigger"] > 0)
    ).astype(int)

    return merged.sort_values("timestamp").reset_index(drop=True)
