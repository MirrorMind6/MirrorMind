"""
Dual-trigger event detection and 60-second window extraction.

Logic
-----
  A real event requires BOTH sensors to agree within LEAD_WINDOW seconds:
    • PIR column      > 0   (motion detected)
    • thermal_trigger == 1  (grid temperature delta above threshold)

  Once both fire, we extract the next RECORD_DURATION rows as the
  "recording window" and build an EventWindow from them.

  Consecutive triggers within COOLDOWN_TICKS of each other are
  merged into one event (prevents double-counting a single person).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


LEAD_WINDOW      = 5     # seconds: max gap between PIR and thermal trigger
RECORD_DURATION  = 60    # seconds of data captured per event
COOLDOWN_TICKS   = 30    # minimum gap between separate events (seconds)


@dataclass
class EventWindow:
    event_id:       int
    trigger_time:   float          # timestamp of dual trigger
    pir_lead_s:     float          # how many seconds PIR fired before thermal
    duration_s:     float
    rows:           pd.DataFrame   # the 60-second slice of the merged DataFrame

    # Derived stats filled by analyse()
    peak_temp:      float = 0.0
    ambient_temp:   float = 0.0
    temp_delta:     float = 0.0    # peak − ambient
    temp_slope:     float = 0.0    # °C/s trend over window
    max_occupancy:  int   = 0
    hotspot_stable: bool  = False  # hotspot centroid stays within 5 px
    notes:          list[str] = field(default_factory=list)


def find_dual_triggers(df: pd.DataFrame) -> list[EventWindow]:
    """
    Scan a merged DataFrame for dual-trigger events.

    Returns one EventWindow per confirmed event, with the 60-second
    data window attached.
    """
    events: list[EventWindow] = []
    last_event_end = -COOLDOWN_TICKS   # prevent clustering at t=0

    pir_last_high = {}    # track when PIR last went high

    i = 0
    while i < len(df):
        row = df.iloc[i]
        t   = float(row["timestamp"])

        # Track PIR rising edge
        if row["pir"] > 0:
            if "pir" not in pir_last_high:
                pir_last_high["pir"] = t
        else:
            pir_last_high.pop("pir", None)

        # Check for dual trigger
        if row["thermal_trigger"] == 1 and "pir" in pir_last_high:
            pir_time  = pir_last_high["pir"]
            lead_time = t - pir_time   # how early PIR fired vs thermal

            if lead_time <= LEAD_WINDOW and t - last_event_end >= COOLDOWN_TICKS:
                # Extract recording window
                window_mask = (df["timestamp"] >= t) & (df["timestamp"] < t + RECORD_DURATION)
                window_df   = df[window_mask].copy()

                event = EventWindow(
                    event_id=len(events),
                    trigger_time=t,
                    pir_lead_s=round(lead_time, 2),
                    duration_s=float(window_df["timestamp"].max() - t),
                    rows=window_df,
                )
                _analyse_window(event)
                events.append(event)

                last_event_end = t + RECORD_DURATION
                pir_last_high.clear()

        i += 1

    return events


def _analyse_window(event: EventWindow) -> None:
    """Fill derived stats on an EventWindow in-place."""
    df = event.rows
    if df.empty:
        return

    event.peak_temp    = float(df["grid_peak"].max())
    event.ambient_temp = float(df["ambient_temp"].mean())
    event.temp_delta   = round(event.peak_temp - event.ambient_temp, 2)
    event.max_occupancy = int(df["occupancy"].max())

    # Temperature trend (slope)
    if len(df) >= 3:
        ts   = df["timestamp"].values.astype(float)
        vals = df["grid_peak"].values.astype(float)
        # simple linear regression
        t_c  = ts - ts.mean()
        event.temp_slope = round(
            float(np.dot(t_c, vals) / (np.dot(t_c, t_c) + 1e-9)), 4
        )

    # Hotspot centroid stability
    cx = df["hotspot_cx"].dropna()
    cy = df["hotspot_cy"].dropna()
    if len(cx) >= 5:
        spread = float(cx.std() ** 2 + cy.std() ** 2) ** 0.5
        event.hotspot_stable = spread < 5.0

    # Human-readable narrative
    event.notes.append(_describe_arrival(event))
    event.notes.append(_describe_behaviour(event))
    occupancy_note = _describe_occupancy(event)
    if occupancy_note:
        event.notes.append(occupancy_note)


def _describe_arrival(event: EventWindow) -> str:
    """First-person arrival observation."""
    if event.temp_slope > 0.05:
        return "I picked up someone entering the space — their heat signature built up as they came in."
    elif event.temp_slope < -0.05:
        return "I caught someone on their way out — their heat signature was already fading when I started recording."
    else:
        return "I detected someone entering the area."


def _describe_behaviour(event: EventWindow) -> str:
    """First-person behaviour + intent inference."""
    duration = int(event.duration_s)
    if event.hotspot_stable and event.temp_slope >= -0.01:
        return (
            f"They stopped and held their position for the full {duration} seconds. "
            f"That kind of stillness usually means they were focused on something — "
            f"working, waiting, or paying attention to something in that spot."
        )
    elif event.hotspot_stable and event.temp_slope < -0.01:
        return (
            f"They stayed in one place but their presence gradually faded over {duration} seconds. "
            f"They were likely wrapping something up before leaving."
        )
    elif not event.hotspot_stable and event.temp_slope > 0.01:
        return (
            f"They kept moving throughout the {duration} seconds and the space kept warming up. "
            f"Looks like they were actively doing something — setting up, searching, or working."
        )
    else:
        return (
            f"They moved around during the {duration}-second window. "
            f"Probably just passing through or getting settled."
        )


def _describe_occupancy(event: EventWindow) -> str:
    """First-person occupancy note, or empty string if just one person."""
    if event.max_occupancy >= 3:
        return "I counted what looked like three or more people — this was a group, not an individual."
    elif event.max_occupancy == 2:
        return "I picked up a second heat source too, so there were likely two people here at the same time."
    return ""


def summarise_events(events: list[EventWindow]) -> pd.DataFrame:
    """
    Convert a list of EventWindows into a compact summary DataFrame —
    one row per event, mirroring what gets written to events.jsonl on the Pi.
    """
    if not events:
        return pd.DataFrame()

    rows = []
    for e in events:
        rows.append({
            "event_id":       e.event_id,
            "trigger_time_s": e.trigger_time,
            "pir_lead_s":     e.pir_lead_s,
            "duration_s":     e.duration_s,
            "peak_temp":      e.peak_temp,
            "ambient_temp":   e.ambient_temp,
            "temp_delta":     e.temp_delta,
            "temp_slope":     e.temp_slope,
            "max_occupancy":  e.max_occupancy,
            "hotspot_stable": e.hotspot_stable,
            "notes":          " | ".join(e.notes),
        })
    return pd.DataFrame(rows)
