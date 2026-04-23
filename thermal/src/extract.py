"""
Extract temperature features from individual thermal frames.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import maximum_filter, label, center_of_mass


@dataclass
class FrameStats:
    min_temp: float
    max_temp: float
    mean_temp: float
    std_temp: float
    frame_index: int
    timestamp: float


@dataclass
class Hotspot:
    """A detected heat region in a single frame."""
    label_id: int
    peak_temp: float
    mean_temp: float
    centroid_x: float   # pixel column
    centroid_y: float   # pixel row
    pixel_count: int
    frame_index: int
    timestamp: float


def frame_stats(frame) -> FrameStats:
    """Compute basic temperature statistics for a ThermalFrame."""
    d = frame.data
    return FrameStats(
        min_temp=float(d.min()),
        max_temp=float(d.max()),
        mean_temp=float(d.mean()),
        std_temp=float(d.std()),
        frame_index=frame.frame_index,
        timestamp=frame.timestamp,
    )


def find_hotspots(
    frame,
    threshold_percentile: float = 90.0,
    neighborhood_size: int = 15,
    min_pixels: int = 5,
) -> list[Hotspot]:
    """
    Detect connected hot regions in a thermal frame.

    Parameters
    ----------
    threshold_percentile
        Pixels above this percentile of the frame are considered hot.
    neighborhood_size
        Size of the window used for local-maximum suppression.
    min_pixels
        Discard blobs smaller than this many pixels.

    Returns
    -------
    List of Hotspot objects sorted by peak temperature descending.
    """
    data = frame.data
    threshold = float(np.percentile(data, threshold_percentile))
    hot_mask = data >= threshold

    # Suppress to local maxima so nearby hot regions don't merge
    local_max = maximum_filter(data, size=neighborhood_size) == data
    seed_mask = hot_mask & local_max

    # Grow regions from seeds using the hot_mask
    labeled, n_regions = label(hot_mask)

    hotspots: list[Hotspot] = []
    for region_id in range(1, n_regions + 1):
        region_mask = labeled == region_id
        if region_mask.sum() < min_pixels:
            continue
        region_data = data[region_mask]
        ys, xs = np.where(region_mask)
        cy, cx = center_of_mass(region_mask)
        hotspots.append(Hotspot(
            label_id=region_id,
            peak_temp=float(region_data.max()),
            mean_temp=float(region_data.mean()),
            centroid_x=float(cx),
            centroid_y=float(cy),
            pixel_count=int(region_mask.sum()),
            frame_index=frame.frame_index,
            timestamp=frame.timestamp,
        ))

    hotspots.sort(key=lambda h: h.peak_temp, reverse=True)
    return hotspots


def extract_roi(frame, x: int, y: int, w: int, h: int):
    """
    Return a cropped ThermalFrame for the given bounding box.

    Origin (x, y) is the top-left corner; w and h are width and height.
    """
    from .ingest import ThermalFrame  # local import to avoid circular
    cropped = frame.data[y: y + h, x: x + w].copy()
    return ThermalFrame(
        data=cropped,
        timestamp=frame.timestamp,
        frame_index=frame.frame_index,
        metadata={**frame.metadata, "roi": (x, y, w, h)},
    )


def build_stats_series(frames) -> list[FrameStats]:
    """Convenience: compute FrameStats for every frame in a sequence."""
    return [frame_stats(f) for f in frames]


def build_hotspot_series(frames, **kwargs) -> list[list[Hotspot]]:
    """Convenience: detect hotspots for every frame in a sequence."""
    return [find_hotspots(f, **kwargs) for f in frames]
