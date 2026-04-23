"""
Dataset fusion demo.

Merges FIR thermal + UCI occupancy data, detects dual-trigger events,
simulates a 60-second recording window per event, and prints summaries
that mirror exactly what the Pi would log to events.jsonl.

Run:
    python dataset_demo.py
"""

from __future__ import annotations

from src.datasets import merge_datasets
from src.dual_trigger import find_dual_triggers, summarise_events


def _bar(value: float, width: int = 20, vmin: float = 0.0, vmax: float = 1.0) -> str:
    filled = int(round((value - vmin) / (vmax - vmin + 1e-9) * width))
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def print_event(event, idx: int, total: int) -> None:
    e = event
    print(f"\n{'─'*60}")
    print(f"  Event {idx + 1}/{total}  │  t = {e.trigger_time:.0f}s")
    print(f"{'─'*60}")
    print(f"  PIR lead time  : {e.pir_lead_s:.1f}s before thermal confirmed")
    print(f"  Duration       : {e.duration_s:.0f}s recorded")
    print(f"  Peak temp      : {e.peak_temp:.1f}°C  (+{e.temp_delta:.1f}°C above ambient)")
    print(f"  Temp trend     : {e.temp_slope:+.3f}°C/s  "
          f"{'↑ heating' if e.temp_slope > 0.01 else ('↓ cooling' if e.temp_slope < -0.01 else '→ stable')}")
    print(f"  Max occupancy  : {e.max_occupancy} person(s)")
    print(f"  Hotspot motion : {'stationary' if e.hotspot_stable else 'moving'}")

    # Mini temperature timeline bar chart
    temps = e.rows["grid_peak"].values
    t_min, t_max = float(temps.min()), float(temps.max())
    print(f"\n  Temperature over 60s  ({t_min:.1f}°C → {t_max:.1f}°C)")
    step = max(1, len(temps) // 20)
    for i in range(0, len(temps), step):
        bar = _bar(temps[i], width=24, vmin=t_min - 1, vmax=t_max + 1)
        print(f"    t+{i:3.0f}s  {bar}  {temps[i]:.1f}°C")

    print(f"\n  Summary notes:")
    for note in e.notes:
        print(f"    → {note}")


def print_calibration_insights(events) -> None:
    if not events:
        return

    leads   = [e.pir_lead_s   for e in events]
    deltas  = [e.temp_delta    for e in events]
    slopes  = [e.temp_slope    for e in events]

    print(f"\n{'═'*60}")
    print("  CALIBRATION INSIGHTS  (what to put in config.yml)")
    print(f"{'═'*60}")
    print(f"\n  From {len(events)} dual-trigger events:\n")

    print(f"  confirm_window_s")
    print(f"    PIR fires {min(leads):.1f}–{max(leads):.1f}s before thermal (mean {sum(leads)/len(leads):.1f}s)")
    print(f"    → set confirm_window_s: {max(leads) + 1.0:.1f}")

    print(f"\n  THERMAL_POINT range (18.0, 42.0 currently)")
    print(f"    Observed delta above ambient: {min(deltas):.1f}–{max(deltas):.1f}°C")
    print(f"    Ambient mean: {sum(e.ambient_temp for e in events)/len(events):.1f}°C")
    print(f"    → detection threshold looks {'OK' if min(deltas) >= 3.5 else 'too high — lower THERMAL_DELTA_THRESHOLD'}")

    print(f"\n  temp_slope distribution")
    print(f"    {min(slopes):+.3f} to {max(slopes):+.3f}°C/s across events")
    print(f"    → events with slope > +0.05°C/s are actively heating (person arriving)")
    print(f"    → events with slope < -0.05°C/s are cooling (person leaving)")

    stationary = sum(1 for e in events if e.hotspot_stable)
    print(f"\n  Hotspot stability")
    print(f"    {stationary}/{len(events)} events had a stationary heat source")
    print(f"    → {'good signal for person-vs-object classification' if stationary > 0 else 'all sources moved — adjust min_pixels threshold'}")
    print()


def main() -> None:
    print("═" * 60)
    print("  Dual-Trigger Dataset Fusion Demo")
    print("═" * 60)

    print("\n[1/3] Merging FIR + UCI datasets …")
    df = merge_datasets(n_seconds=600)
    print(f"      {len(df)} rows, {int(df['timestamp'].max())}s of data")
    print(f"      Dual triggers in raw data: {int(df['dual_trigger'].sum())}")

    print("\n[2/3] Detecting events (PIR + thermal within 5s of each other) …")
    events = find_dual_triggers(df)
    print(f"      {len(events)} confirmed dual-trigger event(s) found")

    if not events:
        print("\nNo events detected — try lowering THERMAL_DELTA_THRESHOLD in datasets.py")
        return

    print("\n[3/3] Event summaries (what would be logged to events.jsonl on the Pi):")
    for i, event in enumerate(events):
        print_event(event, i, len(events))

    summary_df = summarise_events(events)
    print(f"\n\nSummary table:")
    print(summary_df[[
        "event_id", "trigger_time_s", "pir_lead_s",
        "peak_temp", "temp_delta", "temp_slope",
        "max_occupancy", "hotspot_stable",
    ]].to_string(index=False))

    print_calibration_insights(events)


if __name__ == "__main__":
    main()
