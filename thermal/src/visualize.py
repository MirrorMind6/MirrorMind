"""
Render thermal frames as heatmaps and plot temperature trends.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import cv2


# Matplotlib colormaps that read well for thermal data
COLORMAPS = {
    "iron":    "inferno",
    "rainbow": "jet",
    "grayscale": "gray",
    "cool":    "cool",
}


def render_heatmap(
    frame,
    colormap: str = "iron",
    temp_min: float | None = None,
    temp_max: float | None = None,
    overlay_hotspots: list | None = None,
    figsize: tuple[float, float] = (8, 6),
) -> plt.Figure:
    """
    Render a ThermalFrame as a colour-mapped heatmap.

    Parameters
    ----------
    frame            : ThermalFrame
    colormap         : one of the COLORMAPS keys, or any matplotlib cmap name
    temp_min/max     : clamp range; defaults to frame min/max
    overlay_hotspots : list of Hotspot objects to annotate on the image
    """
    cmap = COLORMAPS.get(colormap, colormap)
    vmin = temp_min if temp_min is not None else float(frame.data.min())
    vmax = temp_max if temp_max is not None else float(frame.data.max())

    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(frame.data, cmap=cmap, vmin=vmin, vmax=vmax, origin="upper")
    cbar = fig.colorbar(im, ax=ax, label="Temperature (°C)")
    ax.set_title(f"Frame {frame.frame_index}  |  t = {frame.timestamp:.2f}s")
    ax.set_xlabel("x (px)")
    ax.set_ylabel("y (px)")

    if overlay_hotspots:
        for hs in overlay_hotspots:
            ax.plot(hs.centroid_x, hs.centroid_y, "w+", markersize=10, markeredgewidth=2)
            ax.annotate(
                f"{hs.peak_temp:.1f}°C",
                xy=(hs.centroid_x, hs.centroid_y),
                xytext=(5, -12),
                textcoords="offset points",
                color="white",
                fontsize=8,
            )

    fig.tight_layout()
    return fig


def save_heatmap_sequence(
    frames,
    output_dir: str | Path,
    colormap: str = "iron",
    temp_min: float | None = None,
    temp_max: float | None = None,
    hotspot_series: list[list] | None = None,
) -> list[Path]:
    """
    Save every frame in *frames* as a PNG heatmap into *output_dir*.

    Returns the list of written file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use a consistent temperature scale across the whole sequence
    if temp_min is None:
        temp_min = min(float(f.data.min()) for f in frames)
    if temp_max is None:
        temp_max = max(float(f.data.max()) for f in frames)

    paths: list[Path] = []
    for i, frame in enumerate(frames):
        hotspots = hotspot_series[i] if hotspot_series else None
        fig = render_heatmap(
            frame,
            colormap=colormap,
            temp_min=temp_min,
            temp_max=temp_max,
            overlay_hotspots=hotspots,
        )
        out_path = output_dir / f"frame_{i:04d}.png"
        fig.savefig(out_path, dpi=100)
        plt.close(fig)
        paths.append(out_path)

    return paths


def plot_trend(
    trend,
    forecast: "HotspotForecast | None" = None,
    title: str = "Temperature Trend",
    figsize: tuple[float, float] = (10, 4),
) -> plt.Figure:
    """
    Plot a TrendResult with optional HotspotForecast.

    Parameters
    ----------
    trend    : TrendResult from extrapolate.temperature_trend
    forecast : HotspotForecast (optional) — draws the predicted continuation
    """
    fig, ax = plt.subplots(figsize=figsize)

    ax.scatter(trend.timestamps, trend.values, s=12, alpha=0.6, color="steelblue", label="Observed")
    ax.plot(trend.timestamps, trend.fitted, color="steelblue", linewidth=1.5,
            label=f"Fit  (slope={trend.slope:+.3f} °C/s, R²={trend.r_squared:.3f})")

    if forecast is not None:
        ax.plot(
            np.concatenate([[trend.timestamps[-1]], forecast.forecast_times]),
            np.concatenate([[trend.values[-1]], forecast.forecast_temps]),
            "--", color="tomato", linewidth=1.5, label="Forecast",
        )
        ax.axvline(trend.timestamps[-1], color="gray", linestyle=":", linewidth=1)

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Peak Temperature (°C)")
    ax.set_title(title)
    ax.legend()
    fig.tight_layout()
    return fig


def plot_stats_series(stats_series, figsize: tuple[float, float] = (10, 4)) -> plt.Figure:
    """Plot min/mean/max temperature over time for a sequence."""
    times = [s.timestamp for s in stats_series]
    fig, ax = plt.subplots(figsize=figsize)
    ax.fill_between(times, [s.min_temp for s in stats_series],
                    [s.max_temp for s in stats_series], alpha=0.2, label="min–max range")
    ax.plot(times, [s.mean_temp for s in stats_series], label="mean", linewidth=1.5)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Temperature (°C)")
    ax.set_title("Frame Temperature Statistics")
    ax.legend()
    fig.tight_layout()
    return fig
