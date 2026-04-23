"""
Extrapolate thermal data over time:
  - temperature_trend   : linear regression on a scalar time-series
  - forecast_hotspots   : predict peak temp N steps ahead per hotspot
  - spatial_upsample    : bicubic / RBF upsampling of a low-res thermal frame
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.interpolate import RectBivariateSpline
from sklearn.linear_model import LinearRegression


@dataclass
class TrendResult:
    slope: float          # °C per second
    intercept: float      # °C at t=0
    r_squared: float
    timestamps: np.ndarray
    values: np.ndarray
    fitted: np.ndarray


@dataclass
class HotspotForecast:
    hotspot_index: int    # which hotspot (ranked by peak temp in first frame)
    last_known_temp: float
    forecast_temps: np.ndarray   # predicted peak temps
    forecast_times: np.ndarray   # corresponding timestamps
    trend: TrendResult


def temperature_trend(
    timestamps: list[float] | np.ndarray,
    values: list[float] | np.ndarray,
) -> TrendResult:
    """
    Fit a linear trend to a scalar temperature time-series.

    Parameters
    ----------
    timestamps : 1-D array of time values in seconds
    values     : 1-D array of temperatures in °C

    Returns
    -------
    TrendResult with slope (°C/s), intercept, R², fitted values, and raw data.
    """
    t = np.asarray(timestamps, dtype=np.float64).reshape(-1, 1)
    v = np.asarray(values, dtype=np.float64)

    model = LinearRegression().fit(t, v)
    fitted = model.predict(t)
    ss_res = float(np.sum((v - fitted) ** 2))
    ss_tot = float(np.sum((v - v.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0

    return TrendResult(
        slope=float(model.coef_[0]),
        intercept=float(model.intercept_),
        r_squared=r2,
        timestamps=np.asarray(timestamps, dtype=np.float64),
        values=v,
        fitted=fitted.astype(np.float64),
    )


def forecast_hotspots(
    hotspot_series: list[list],
    n_steps: int = 10,
    dt: float = 0.1,
    n_hotspots: int = 2,
) -> list[HotspotForecast]:
    """
    Forecast peak temperature for the top-N hotspots.

    hotspot_series  : output of extract.build_hotspot_series()
    n_steps         : how many future time steps to predict
    dt              : seconds per step (should match capture fps)
    n_hotspots      : number of hotspots to track (ranked by first-frame peak)

    Strategy: align hotspots across frames by tracking the closest centroid
    to the previous frame's position, then fit a linear trend and extrapolate.
    """
    if not hotspot_series or not hotspot_series[0]:
        return []

    # Seed tracking positions from the first frame
    seed_hotspots = hotspot_series[0][:n_hotspots]
    tracks: list[dict] = [
        {"cx": h.centroid_x, "cy": h.centroid_y, "times": [], "peaks": []}
        for h in seed_hotspots
    ]

    for frame_hotspots in hotspot_series:
        for track in tracks:
            if not frame_hotspots:
                continue
            # Nearest centroid matching
            dists = [
                (h.centroid_x - track["cx"]) ** 2 + (h.centroid_y - track["cy"]) ** 2
                for h in frame_hotspots
            ]
            best = frame_hotspots[int(np.argmin(dists))]
            track["cx"] = best.centroid_x
            track["cy"] = best.centroid_y
            track["times"].append(best.timestamp)
            track["peaks"].append(best.peak_temp)

    forecasts: list[HotspotForecast] = []
    for idx, track in enumerate(tracks):
        if len(track["times"]) < 2:
            continue
        trend = temperature_trend(track["times"], track["peaks"])
        last_t = track["times"][-1]
        future_times = np.array([last_t + dt * (i + 1) for i in range(n_steps)])
        future_temps = trend.slope * future_times + trend.intercept

        forecasts.append(HotspotForecast(
            hotspot_index=idx,
            last_known_temp=track["peaks"][-1],
            forecast_temps=future_temps,
            forecast_times=future_times,
            trend=trend,
        ))

    return forecasts


def spatial_upsample(
    frame,
    scale: int = 4,
    method: str = "bicubic",
):
    """
    Spatially upsample a low-resolution thermal frame.

    Parameters
    ----------
    frame  : ThermalFrame
    scale  : integer upscaling factor (e.g. 4 → 4× resolution)
    method : "bicubic" (default) or "rbf" (slower, smoother for very low-res)

    Returns
    -------
    New ThermalFrame with upsampled data.
    """
    from .ingest import ThermalFrame  # local import to avoid circular

    data = frame.data.astype(np.float64)
    h, w = data.shape
    new_h, new_w = h * scale, w * scale

    if method == "rbf":
        y_old = np.arange(h, dtype=np.float64)
        x_old = np.arange(w, dtype=np.float64)
        spline = RectBivariateSpline(y_old, x_old, data)
        y_new = np.linspace(0, h - 1, new_h)
        x_new = np.linspace(0, w - 1, new_w)
        upsampled = spline(y_new, x_new).astype(np.float32)
    else:
        import cv2
        upsampled = cv2.resize(
            data.astype(np.float32), (new_w, new_h),
            interpolation=cv2.INTER_CUBIC,
        )

    return ThermalFrame(
        data=upsampled,
        timestamp=frame.timestamp,
        frame_index=frame.frame_index,
        metadata={**frame.metadata, "upscaled_by": scale, "method": method},
    )
