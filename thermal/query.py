"""
Query the thermal event log.

Examples
--------
    python query.py                          # list all events
    python query.py --date 2025-04-06        # events on a specific day
    python query.py --date 2025-04           # events in a month
    python query.py --last 5                 # five most recent events
    python query.py --date 2025-04-06 --full # include full hotspot data
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EVENTS_LOG = Path("data/events.jsonl")


def load_events(log_path: Path = EVENTS_LOG) -> list[dict]:
    if not log_path.exists():
        return []
    events = []
    with log_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return events


def filter_by_date(events: list[dict], date_prefix: str) -> list[dict]:
    """
    Filter by ISO timestamp prefix, e.g. "2025-04-06" or "2025-04".
    Timestamps in the log are like "20250406T143022" so we normalise both.
    """
    # Support both YYYYMMDD and YYYY-MM-DD input formats
    prefix = date_prefix.replace("-", "")
    return [e for e in events if e.get("timestamp_iso", "").startswith(prefix)]


def format_event(event: dict, full: bool = False) -> str:
    ts  = event.get("timestamp_iso", "?")
    # Pretty-print YYYYMMDDTHHMMSS → YYYY-MM-DD HH:MM:SS
    if len(ts) == 15 and "T" in ts:
        d, t = ts.split("T")
        ts = f"{d[:4]}-{d[4:6]}-{d[6:]}  {t[:2]}:{t[2:4]}:{t[4:]}"

    dur     = event.get("duration_s", 0)
    peak    = event.get("peak_temp", "?")
    ambient = event.get("ambient_temp", "?")
    slope   = event.get("temp_slope", 0)
    hs      = event.get("hotspots", [])
    narr    = event.get("narrative", "")

    direction = "rising" if slope > 0.005 else ("falling" if slope < -0.005 else "stable")
    lines = [
        f"  {ts}  │  {dur:.0f}s  │  peak {peak}°C  ambient {ambient}°C  "
        f"trend {slope:+.3f}°C/s ({direction})  │  hotspots: {len(hs)}",
    ]
    if narr:
        lines.append(f"    → {narr}")
    if full and hs:
        for i, h in enumerate(hs):
            lines.append(
                f"    HS{i+1}: peak={h['peak_temp']}°C  "
                f"slope={h['temp_slope']:+.4f}°C/s  "
                f"centroid=({h['centroid_x']:.0f},{h['centroid_y']:.0f})  "
                f"seen {h['first_seen_s']:.1f}s–{h['last_seen_s']:.1f}s"
            )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query thermal event log")
    parser.add_argument("--date",   help="Filter by date prefix e.g. 2025-04-06 or 2025-04")
    parser.add_argument("--last",   type=int, help="Show N most recent events")
    parser.add_argument("--full",   action="store_true", help="Show hotspot detail")
    parser.add_argument("--quota",  action="store_true", help="Show today's token usage")
    args = parser.parse_args()

    if args.quota:
        from src.analyze import quota_status
        s = quota_status()
        print(f"\nToken quota  [{s['date']}]")
        print(f"  Used:      {s['tokens_used']:,} / {s['limit']:,}")
        print(f"  Remaining: {s['tokens_remaining']:,}")
        print(f"  API calls: {s['calls']}")
        print(f"  Enabled:   {s['enabled']}\n")
        return

    events = load_events()
    if not events:
        print("No events logged yet. Run runner.py to start monitoring.")
        return

    if args.date:
        events = filter_by_date(events, args.date)
        if not events:
            print(f"No events found for date prefix '{args.date}'.")
            return

    if args.last:
        events = events[-args.last:]

    label = f"date={args.date}" if args.date else ("all" if not args.last else f"last {args.last}")
    print(f"\nThermal Events  [{label}]  —  {len(events)} result(s)\n")
    print("─" * 80)
    for e in events:
        print(format_event(e, full=args.full))
    print("─" * 80)
    print(f"\nLog: {EVENTS_LOG.resolve()}\n")


if __name__ == "__main__":
    main()
