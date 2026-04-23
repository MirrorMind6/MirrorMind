"""
Raspberry Pi event-driven thermal monitoring loop.

State machine
─────────────
  IDLE       → Poll PIR only (cheap). Thermal camera is off.
  TRIGGERED  → PIR fired. Spin up thermal + proximity + BME280.
               Run fusion for up to CONFIRM_WINDOW seconds to confirm
               a real event (not a false positive).
  RECORDING  → Confirmed. Record thermal frames + sensor data for
               RECORD_DURATION seconds.
  COOLDOWN   → Recording done. Save compact clip + event log entry.
               Brief pause before returning to IDLE.

Storage strategy
─────────────────
  • Thermal clips   → data/clips/<timestamp>.npz   (~400 KB per 60 s clip at 4 fps)
  • Event log       → data/events.jsonl             (one JSON line per event, ~200 B)
  • Raw frames are float16 (halves storage vs float32 with <0.1 °C precision loss).
  • No PNG/video files are written unless --save-png is passed.

Swapping mock → real hardware
──────────────────────────────
  Change USE_MOCK = False at the top of this file.
  Make sure the Adafruit + RPi.GPIO libraries are installed (requirements-pi.txt).
"""

from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from dataclasses import asdict, dataclass
from enum import Enum, auto
from pathlib import Path

import numpy as np

from src.fusion import FusionBuffer, Decision
from src.extract import find_hotspots
from src.ingest import ThermalFrame
from src.analyze import analyze_clip, add_narrative, ClipSummary

# ── Hardware selection ────────────────────────────────────────────────────────
USE_MOCK = True   # ← flip to False when running on real Pi hardware

if USE_MOCK:
    from src.hardware import MockPIR as PIR
    from src.hardware import MockMLX90640 as ThermalCam
    from src.hardware import MockVL53L0X as Proximity
    from src.hardware import MockBME280 as Humidity
else:
    from src.hardware import PIRDriver as PIR            # type: ignore[assignment]
    from src.hardware import MLX90640Driver as ThermalCam  # type: ignore[assignment]
    from src.hardware import VL53L0XDriver as Proximity  # type: ignore[assignment]
    from src.hardware import BME280Driver as Humidity    # type: ignore[assignment]

# ── Tunable parameters ────────────────────────────────────────────────────────
PIR_POLL_HZ      = 10      # how often to check PIR in IDLE (per second)
THERMAL_FPS      = 4       # thermal frames per second during capture
CONFIRM_WINDOW   = 3.0     # seconds of fusion to confirm an event isn't noise
RECORD_DURATION  = 60.0    # seconds of thermal clip to record per event
COOLDOWN_SECS    = 5.0     # pause between events

DATA_DIR         = Path("data")
CLIPS_DIR        = DATA_DIR / "clips"
EVENTS_LOG       = DATA_DIR / "events.jsonl"


# ── State machine ─────────────────────────────────────────────────────────────

class State(Enum):
    IDLE       = auto()
    TRIGGERED  = auto()
    RECORDING  = auto()
    COOLDOWN   = auto()


@dataclass
class EventRecord:
    timestamp_iso: str
    duration_s: float
    peak_temp: float
    mean_temp: float
    decision: str
    confidence: float
    dominant_sensor: str
    clip_file: str
    notes: list[str]


# ── Main runner ───────────────────────────────────────────────────────────────

class ThermalRunner:

    def __init__(self, save_png: bool = False, verbose: bool = True):
        self._save_png = save_png
        self._verbose  = verbose
        self._running  = True
        CLIPS_DIR.mkdir(parents=True, exist_ok=True)
        DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    def run(self) -> None:
        signal.signal(signal.SIGINT,  self._stop)
        signal.signal(signal.SIGTERM, self._stop)

        self._log("Starting thermal monitor  (USE_MOCK={})".format(USE_MOCK))

        pir = PIR(sensor_id="motion_0")

        while self._running:
            # ── IDLE: only the PIR is active ──────────────────────────
            self._log("STATE → IDLE  (polling PIR …)")
            triggered = self._idle_loop(pir)
            if not triggered:
                break   # SIGINT during idle

            # ── TRIGGERED: spin up the rest of the sensors ────────────
            self._log("PIR fired — spinning up sensors …")
            with (
                ThermalCam(sensor_id="mlx_0") as cam,
                Proximity(sensor_id="proximity_0") as prox,
                Humidity(sensor_id="humidity_0") as bme,
            ):
                buf = FusionBuffer(window_size=20, thresholds=(0.55, 0.72))
                confirmed = self._confirm_loop(cam, prox, bme, buf)

                if not confirmed:
                    self._log("Event not confirmed — returning to IDLE.")
                    continue

                # ── RECORDING ─────────────────────────────────────────
                self._log(f"Confirmed! Recording {RECORD_DURATION:.0f}s clip …")
                record = self._record_loop(cam, prox, bme, buf)

            # ── COOLDOWN: analyse → summarise → delete clip → rest ────
            summary = self._analyse(record.clip_file)
            self._persist_summary(summary)
            self._log(f"STATE → COOLDOWN ({COOLDOWN_SECS}s)")
            self._sleep(COOLDOWN_SECS)

        self._log("Runner stopped.")

    # ------------------------------------------------------------------
    # State implementations

    def _idle_loop(self, pir) -> bool:
        """Block until PIR triggers or runner is stopped."""
        interval = 1.0 / PIR_POLL_HZ
        while self._running:
            reading = pir.read()
            if reading.value > 0.5:
                return True
            time.sleep(interval)
        return False

    def _confirm_loop(self, cam, prox, bme, buf: FusionBuffer) -> bool:
        """
        Capture sensor data for CONFIRM_WINDOW seconds.
        Returns True if the fusion score crosses WARNING threshold.
        """
        deadline = time.monotonic() + CONFIRM_WINDOW
        interval = 1.0 / THERMAL_FPS
        while time.monotonic() < deadline and self._running:
            t0 = time.monotonic()
            for r in [cam.read(), prox.read(), bme.read()]:
                buf.push(r)
            buf.commit()
            event = buf.evaluate()
            if event.decision in (Decision.WARNING, Decision.ALERT):
                return True
            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))
        return False

    def _record_loop(self, cam, prox, bme, buf: FusionBuffer) -> EventRecord:
        """
        Record RECORD_DURATION seconds of thermal frames + sensor data.
        Returns an EventRecord with clip path and stats.
        """
        frames_data: list[np.ndarray] = []
        timestamps:  list[float]      = []
        interval  = 1.0 / THERMAL_FPS
        deadline  = time.monotonic() + RECORD_DURATION
        start_iso = time.strftime("%Y%m%dT%H%M%S")
        peak_temp = -999.0
        temp_sum  = 0.0
        n_frames  = 0

        while time.monotonic() < deadline and self._running:
            t0 = time.monotonic()
            thermal_reading = cam.read()
            for r in [thermal_reading, prox.read(), bme.read()]:
                buf.push(r)
            snap = buf.commit(timestamp=time.monotonic())

            grid: np.ndarray = thermal_reading.metadata.get("grid")
            if grid is not None:
                frames_data.append(grid.astype(np.float16))  # compact storage
                timestamps.append(thermal_reading.timestamp)
                peak_temp = max(peak_temp, float(grid.max()))
                temp_sum += float(grid.mean())
                n_frames += 1

            elapsed = time.monotonic() - t0
            time.sleep(max(0.0, interval - elapsed))

        final_event = buf.evaluate()
        clip_name   = f"{start_iso}.npz"
        clip_path   = CLIPS_DIR / clip_name

        if frames_data:
            np.savez_compressed(
                clip_path,
                frames=np.stack(frames_data),           # shape: (N, 24, 32) float16
                timestamps=np.array(timestamps),
            )
            size_kb = clip_path.stat().st_size / 1024
            self._log(f"Clip saved → {clip_path}  ({size_kb:.1f} KB, {n_frames} frames)")

        if self._save_png:
            self._export_png_frames(frames_data, timestamps, start_iso)

        return EventRecord(
            timestamp_iso=start_iso,
            duration_s=RECORD_DURATION,
            peak_temp=round(peak_temp, 2),
            mean_temp=round(temp_sum / max(n_frames, 1), 2),
            decision=final_event.decision.value,
            confidence=round(final_event.confidence, 3),
            dominant_sensor=final_event.dominant_sensor,
            clip_file=str(clip_path),
            notes=final_event.notes,
        )

    # ------------------------------------------------------------------
    # Analysis + persistence

    def _analyse(self, clip_file: str) -> ClipSummary:
        clip_path = Path(clip_file)
        if not clip_path.exists():
            self._log("No clip file to analyse.")
            from src.analyze import ClipSummary
            return ClipSummary(
                timestamp_iso="unknown", duration_s=0, n_frames=0,
                fps=0, ambient_temp=0, peak_temp=0, mean_temp=0,
                temp_slope=0, hotspots=[],
            )

        self._log("Analysing clip …")
        summary = analyze_clip(clip_path)
        summary = add_narrative(summary)
        self._log(f"Narrative: {summary.narrative}")

        # Delete the raw clip — only the summary is kept
        clip_path.unlink()
        self._log(f"Raw clip deleted → {clip_path.name}")
        return summary

    def _persist_summary(self, summary: ClipSummary) -> None:
        from dataclasses import asdict
        with EVENTS_LOG.open("a") as f:
            f.write(json.dumps(asdict(summary)) + "\n")
        self._log(
            f"Event logged → peak={summary.peak_temp}°C  "
            f"slope={summary.temp_slope:+.3f}°C/s  "
            f"hotspots={len(summary.hotspots)}"
        )

    # ------------------------------------------------------------------
    # Optional PNG export (debugging only — costs disk space)

    def _export_png_frames(
        self,
        frames: list[np.ndarray],
        timestamps: list[float],
        tag: str,
    ) -> None:
        from src.ingest import ThermalFrame
        from src.visualize import render_heatmap
        import matplotlib.pyplot as plt

        png_dir = CLIPS_DIR / f"{tag}_png"
        png_dir.mkdir(exist_ok=True)
        vmin = min(f.min() for f in frames)
        vmax = max(f.max() for f in frames)
        for i, (grid, ts) in enumerate(zip(frames, timestamps)):
            frame = ThermalFrame(data=grid.astype(np.float32), timestamp=ts, frame_index=i)
            fig = render_heatmap(frame, temp_min=float(vmin), temp_max=float(vmax))
            fig.savefig(png_dir / f"{i:04d}.png", dpi=80)
            plt.close(fig)
        self._log(f"PNG frames saved → {png_dir}/")

    # ------------------------------------------------------------------

    def _sleep(self, seconds: float) -> None:
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and self._running:
            time.sleep(0.1)

    def _stop(self, *_) -> None:
        self._log("\nShutting down …")
        self._running = False

    def _log(self, msg: str) -> None:
        if self._verbose:
            print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Thermal monitoring runner")
    parser.add_argument("--save-png",  action="store_true",
                        help="Also export PNG frames per clip (debug, uses more disk)")
    parser.add_argument("--quiet",     action="store_true")
    args = parser.parse_args()

    ThermalRunner(save_png=args.save_png, verbose=not args.quiet).run()


if __name__ == "__main__":
    main()
