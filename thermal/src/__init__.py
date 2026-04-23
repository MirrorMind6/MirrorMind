from .ingest import generate_sequence, load_frame, load_sequence
from .extract import frame_stats, find_hotspots, extract_roi
from .extrapolate import temperature_trend, forecast_hotspots, spatial_upsample
from .visualize import render_heatmap, plot_trend, save_heatmap_sequence
from .fusion import (
    SensorReading, SensorType, FusionBuffer, FusionEvent, Decision,
    generate_sensor_stream,
)
