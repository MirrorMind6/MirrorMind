"""
Post-recording analysis pipeline.

After a 60-second clip is captured:
  1. Load the .npz file.
  2. Run hotspot detection + trend analysis on every frame.
  3. Build a compact ClipSummary (structured data, ~1 KB).
  4. Optionally send the summary to Claude for a natural-language narrative.
  5. Return the summary — the caller deletes the raw clip.
"""

from __future__ import annotations

import os
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from .extract import find_hotspots, frame_stats
from .extrapolate import temperature_trend
from .ingest import ThermalFrame


# ── Summary dataclass ─────────────────────────────────────────────────────────

@dataclass
class HotspotSummary:
    first_seen_s: float
    last_seen_s: float
    peak_temp: float
    mean_peak_temp: float
    centroid_x: float
    centroid_y: float
    temp_slope: float          # °C / second (positive = heating up)


@dataclass
class ClipSummary:
    timestamp_iso: str
    duration_s: float
    n_frames: int
    fps: float
    ambient_temp: float        # mean of frame minimums
    peak_temp: float
    mean_temp: float
    temp_slope: float          # overall scene trend °C/s
    hotspots: list[HotspotSummary]
    narrative: str = ""        # filled by Claude if API key is available
    analysis_duration_s: float = 0.0


# ── Local analysis ────────────────────────────────────────────────────────────

def analyze_clip(clip_path: str | Path) -> ClipSummary:
    """
    Load a saved .npz clip, run local analysis, and return a ClipSummary.
    Does not delete the file — caller decides when to remove it.
    """
    clip_path = Path(clip_path)
    t_start = time.monotonic()

    data = np.load(clip_path)
    raw_frames: np.ndarray = data["frames"].astype(np.float32)   # (N, H, W)
    timestamps: np.ndarray = data["timestamps"].astype(np.float64)

    n_frames, h, w = raw_frames.shape
    duration = float(timestamps[-1] - timestamps[0]) if n_frames > 1 else 0.0
    fps = n_frames / max(duration, 1e-3)

    frames = [
        ThermalFrame(data=raw_frames[i], timestamp=float(timestamps[i]), frame_index=i)
        for i in range(n_frames)
    ]

    # Per-frame stats
    stats_list = [frame_stats(f) for f in frames]
    all_means  = [s.mean_temp for s in stats_list]
    all_mins   = [s.min_temp  for s in stats_list]
    all_maxes  = [s.max_temp  for s in stats_list]
    ts_arr     = [s.timestamp for s in stats_list]

    global_trend = temperature_trend(ts_arr, all_means)

    # Track top-2 hotspots across the clip
    hotspot_tracks: dict[int, dict] = {}   # label_id → track data
    for i, frame in enumerate(frames):
        for hs in find_hotspots(frame, threshold_percentile=88, min_pixels=4)[:2]:
            tid = _nearest_track(hotspot_tracks, hs.centroid_x, hs.centroid_y, threshold=6.0)
            if tid is None:
                tid = len(hotspot_tracks)
                hotspot_tracks[tid] = {
                    "times":  [], "peaks": [],
                    "cx": [], "cy": [],
                    "first_seen": hs.timestamp,
                }
            track = hotspot_tracks[tid]
            track["times"].append(hs.timestamp)
            track["peaks"].append(hs.peak_temp)
            track["cx"].append(hs.centroid_x)
            track["cy"].append(hs.centroid_y)
            track["last_seen"] = hs.timestamp

    hs_summaries: list[HotspotSummary] = []
    for track in hotspot_tracks.values():
        if len(track["times"]) < 3:
            continue
        trend = temperature_trend(track["times"], track["peaks"])
        hs_summaries.append(HotspotSummary(
            first_seen_s=track["first_seen"],
            last_seen_s=track["last_seen"],
            peak_temp=max(track["peaks"]),
            mean_peak_temp=float(np.mean(track["peaks"])),
            centroid_x=float(np.mean(track["cx"])),
            centroid_y=float(np.mean(track["cy"])),
            temp_slope=round(trend.slope, 4),
        ))

    hs_summaries.sort(key=lambda h: h.peak_temp, reverse=True)

    return ClipSummary(
        timestamp_iso=clip_path.stem,
        duration_s=round(duration, 2),
        n_frames=n_frames,
        fps=round(fps, 2),
        ambient_temp=round(float(np.mean(all_mins)), 2),
        peak_temp=round(float(max(all_maxes)), 2),
        mean_temp=round(float(np.mean(all_means)), 2),
        temp_slope=round(global_trend.slope, 4),
        hotspots=hs_summaries,
        analysis_duration_s=round(time.monotonic() - t_start, 3),
    )


def _nearest_track(
    tracks: dict,
    cx: float,
    cy: float,
    threshold: float,
) -> int | None:
    best_id, best_dist = None, float("inf")
    for tid, track in tracks.items():
        if not track["cx"]:
            continue
        dx = track["cx"][-1] - cx
        dy = track["cy"][-1] - cy
        d = (dx * dx + dy * dy) ** 0.5
        if d < best_dist:
            best_dist, best_id = d, tid
    return best_id if best_dist < threshold else None


# ── Claude narrative (optional) ───────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a concise thermal-sensor analyst. "
    "Given structured data from a 60-second thermal camera clip, "
    "write a 2-3 sentence plain-English summary describing what likely happened: "
    "presence detected, temperature trends, and any anomalies. "
    "Be factual and brief. Do not repeat raw numbers unless they add insight."
)


def add_narrative(summary: ClipSummary) -> ClipSummary:
    """
    Call the Claude API to add a natural-language narrative to the summary.
    Requires ANTHROPIC_API_KEY in the environment. Safe to skip if unavailable.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        summary.narrative = "(narrative unavailable — set ANTHROPIC_API_KEY)"
        return summary

    import urllib.request

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 200,
        "system": _SYSTEM_PROMPT,
        "messages": [{
            "role": "user",
            "content": json.dumps({
                "duration_s": summary.duration_s,
                "ambient_temp": summary.ambient_temp,
                "peak_temp": summary.peak_temp,
                "mean_temp": summary.mean_temp,
                "temp_slope_c_per_s": summary.temp_slope,
                "hotspots": [asdict(h) for h in summary.hotspots],
            }),
        }],
    }

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type":    "application/json",
            "x-api-key":       api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
            summary.narrative = body["content"][0]["text"].strip()
    except Exception as exc:
        summary.narrative = f"(narrative error: {exc})"

    return summary
