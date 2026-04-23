"""
Thermal pipeline demo.

Generates a synthetic thermal sequence, extracts hotspots, extrapolates
temperature trends, and saves heatmap images + trend charts to ./output/.
"""

from pathlib import Path

from src.ingest import generate_sequence
from src.extract import build_stats_series, build_hotspot_series
from src.extrapolate import temperature_trend, forecast_hotspots
from src.visualize import save_heatmap_sequence, plot_trend, plot_stats_series

OUTPUT_DIR = Path("output")


def main() -> None:
    print("=== Thermal Pipeline Demo ===\n")

    # 1. Ingest ---------------------------------------------------------------
    print("[1/4] Generating synthetic sequence  (60 frames, 320×240) …")
    frames = generate_sequence(n_frames=60, width=320, height=240, fps=10.0, seed=42)
    print(f"      {len(frames)} frames generated.\n")

    # 2. Extract --------------------------------------------------------------
    print("[2/4] Extracting stats and hotspots …")
    stats = build_stats_series(frames)
    hotspot_series = build_hotspot_series(frames, threshold_percentile=90, min_pixels=8)

    first_hotspots = hotspot_series[0]
    print(f"      Frame 0  |  temp range: {stats[0].min_temp:.1f}–{stats[0].max_temp:.1f} °C")
    print(f"      Hotspots detected in frame 0: {len(first_hotspots)}")
    for hs in first_hotspots[:3]:
        print(f"        → peak {hs.peak_temp:.1f}°C  at ({hs.centroid_x:.0f}, {hs.centroid_y:.0f})  "
              f"[{hs.pixel_count} px]")
    print()

    # 3. Extrapolate ----------------------------------------------------------
    print("[3/4] Extrapolating temperature trends …")
    mean_times = [s.timestamp for s in stats]
    mean_temps = [s.mean_temp for s in stats]
    global_trend = temperature_trend(mean_times, mean_temps)
    print(f"      Global mean trend:  {global_trend.slope:+.4f} °C/s  "
          f"(R² = {global_trend.r_squared:.4f})")

    forecasts = forecast_hotspots(hotspot_series, n_steps=20, dt=0.1, n_hotspots=2)
    for fc in forecasts:
        direction = "rising" if fc.trend.slope > 0 else "falling"
        print(f"      Hotspot #{fc.hotspot_index}: last {fc.last_known_temp:.1f}°C  →  "
              f"forecast in 2s: {fc.forecast_temps[-1]:.1f}°C  ({direction})")
    print()

    # 4. Visualise ------------------------------------------------------------
    print("[4/4] Saving output …")
    OUTPUT_DIR.mkdir(exist_ok=True)

    # Save first and last frame heatmap only (full sequence can be slow)
    for idx in [0, 29, 59]:
        from src.visualize import render_heatmap
        fig = render_heatmap(
            frames[idx],
            overlay_hotspots=hotspot_series[idx][:3],
            temp_min=stats[0].min_temp,
            temp_max=max(s.max_temp for s in stats),
        )
        path = OUTPUT_DIR / f"heatmap_frame{idx:04d}.png"
        fig.savefig(path, dpi=120)
        import matplotlib.pyplot as plt
        plt.close(fig)
        print(f"      Saved {path}")

    # Stats trend chart
    fig_stats = plot_stats_series(stats)
    fig_stats.savefig(OUTPUT_DIR / "stats_trend.png", dpi=120)
    import matplotlib.pyplot as plt
    plt.close(fig_stats)
    print(f"      Saved {OUTPUT_DIR / 'stats_trend.png'}")

    # Per-hotspot forecast charts
    for fc in forecasts:
        fig_fc = plot_trend(
            fc.trend,
            forecast=fc,
            title=f"Hotspot #{fc.hotspot_index} — Temperature Forecast",
        )
        path = OUTPUT_DIR / f"hotspot_{fc.hotspot_index}_forecast.png"
        fig_fc.savefig(path, dpi=120)
        plt.close(fig_fc)
        print(f"      Saved {path}")

    print("\nDone. All output written to ./output/")


def fusion_demo() -> None:
    """
    Demonstrate the sensor-fusion pipeline with a synthetic stream.

    No camera frames involved — just lightweight data points from a
    few thermal spots, a humidity sensor, and a motion sensor.
    """
    from src.fusion import FusionBuffer, generate_sensor_stream, Decision

    print("=== Sensor Fusion Demo ===\n")
    print("Generating 100-tick stream (anomaly starts at tick 60) …\n")

    stream = generate_sensor_stream(n_ticks=100, dt=0.5, anomaly_start=60, seed=7)
    buf = FusionBuffer(window_size=20, thresholds=(0.55, 0.72))

    prev_decision = None
    for tick, readings in enumerate(stream):
        for r in readings:
            buf.push(r)
        buf.commit(timestamp=tick * 0.5)
        event = buf.evaluate()

        if event.decision != prev_decision:
            print(f"  t={tick * 0.5:5.1f}s  [{event.decision.value.upper():7s}]  "
                  f"score={event.confidence:.2f}  dominant={event.dominant_sensor}"
                  + (f"  ← {'; '.join(event.notes)}" if event.notes else ""))
            prev_decision = event.decision

    print("\nFusion demo complete.\n")


if __name__ == "__main__":
    main()
    print()
    fusion_demo()
