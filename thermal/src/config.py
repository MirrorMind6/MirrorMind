"""
Load and expose config.yml as a simple namespace.
Falls back to safe defaults if the file is missing.
"""

from __future__ import annotations

from pathlib import Path

try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

_DEFAULTS = {
    "hardware":   {"use_mock": True, "thermal_fps": 4, "pir_poll_hz": 10},
    "detection":  {"warn_threshold": 0.55, "alert_threshold": 0.72,
                   "confirm_window_s": 3.0, "cooldown_s": 5.0},
    "recording":  {"duration_s": 60.0, "save_png": False},
    "quota":      {"enabled": True, "daily_token_limit": 10000,
                   "max_input_tokens": 400, "max_output_tokens": 150},
    "storage":    {"data_dir": "data", "clips_dir": "data/clips",
                   "events_log": "data/events.jsonl",
                   "token_usage_file": "data/token_usage.json"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load(path: str | Path = "config.yml") -> dict:
    cfg = dict(_DEFAULTS)
    path = Path(path)
    if path.exists() and _HAS_YAML:
        with path.open() as f:
            user_cfg = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, user_cfg)
    return cfg


# Module-level singleton — import this everywhere
CFG = load()
