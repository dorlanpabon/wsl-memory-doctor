from __future__ import annotations

import os
import tomllib
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(os.environ.get("WSL_MEMORY_DOCTOR_ROOT", Path(__file__).resolve().parents[2]))

DEFAULT_SETTINGS: dict[str, Any] = {
    "profile": {
        "balanceado": {
            "recommended_memory_gb": 12,
            "recommended_processors": 8,
            "recommended_swap_gb": 4,
            "auto_memory_reclaim": "gradual",
            "max_top_processes": 12,
            "container_margin_multiplier": 2.5,
            "min_container_limit_mib": 256,
            "max_container_limit_mib": 2048,
            "high_vmmem_host_ratio": 0.20,
            "high_vmmem_min_gb": 6,
            "high_cache_ratio": 0.20,
            "high_available_ratio": 0.40,
            "possible_leak_growth_ratio": 0.25,
            "possible_leak_stability_tolerance": 0.15,
        }
    },
    "reviews": {
        "service_names": [
            "snapd.service",
            "cloud-init.service",
            "cloud-final.service",
            "cloud-config.service",
            "ModemManager.service",
            "dbus-org.freedesktop.ModemManager1.service",
        ],
        "warning_patterns": [
            "Failed to mount",
            "Failed to translate",
            "bogus",
            "screen size",
        ],
    },
}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_settings(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or PROJECT_ROOT
    config_path = root / "config" / "settings.toml"
    settings = deepcopy(DEFAULT_SETTINGS)
    if config_path.exists():
        with config_path.open("rb") as handle:
            settings = _deep_merge(settings, tomllib.load(handle))
    settings["paths"] = {
        "project_root": str(root),
        "db": str(root / "data" / "telemetry.sqlite3"),
        "reports_dir": str(root / "reports"),
    }
    return settings
