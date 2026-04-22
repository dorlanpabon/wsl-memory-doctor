from __future__ import annotations

import unittest
from copy import deepcopy

from wsl_memory_doctor.analyzer import analyze_snapshot
from wsl_memory_doctor.config import load_settings


def make_snapshot() -> dict:
    return {
        "meta": {"created_at": "2026-04-22T12:00:00+00:00"},
        "host": {
            "total_memory_bytes": 32 * 1024**3,
            "vmmem_process": {"WorkingSetBytes": int(9.0 * 1024**3)},
            "wslconfig": {"wsl2": {}, "experimental": {}},
            "docker_settings": {"useResourceSaver": True},
            "warnings": ["wsl: Failed to mount E:\\"],
        },
        "wsl": {
            "global_meminfo": {
                "MemTotal": 16 * 1024**3,
                "MemAvailable": int(12.5 * 1024**3),
                "Cached": int(4.7 * 1024**3),
                "Buffers": int(1.3 * 1024**3),
                "SReclaimable": int(0.4 * 1024**3),
            },
            "distros": [
                {
                    "name": "Ubuntu-20.04",
                    "state": "Running",
                    "enabled_services": [
                        {"name": "snapd.service", "state": "enabled"},
                        {"name": "dbus-org.freedesktop.ModemManager1.service", "state": "enabled"},
                    ],
                },
                {"name": "docker-desktop", "state": "Running", "enabled_services": []},
                {"name": "podman-machine-default", "state": "Running", "enabled_services": []},
            ],
        },
        "runtimes": {
            "docker": {
                "containers": [
                    {
                        "name": "supabase_db",
                        "limits": {"memory_bytes": 0},
                        "stats": {"memory_usage_bytes": 150 * 1024**2},
                    }
                ]
            },
            "podman": {
                "containers": [
                    {
                        "name": "localstack-main",
                        "limits": {"memory_bytes": 0},
                        "stats": {"memory_usage_bytes": 430 * 1000**2},
                    }
                ]
            },
        },
    }


class AnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = load_settings()

    def test_detects_expected_findings(self) -> None:
        analysis = analyze_snapshot(make_snapshot(), [], self.settings)
        codes = {finding["code"] for finding in analysis["findings"]}
        self.assertIn("high_vmmem", codes)
        self.assertIn("double_runtime", codes)
        self.assertIn("unlimited_containers", codes)
        self.assertIn("missing_wsl_limits", codes)
        self.assertIn("missing_auto_memory_reclaim", codes)
        self.assertIn("wsl_warnings", codes)
        self.assertEqual(analysis["classification"], "sobrecarga por runtimes")

    def test_prefers_cache_retention_when_no_double_runtime(self) -> None:
        snapshot = make_snapshot()
        snapshot["wsl"]["distros"] = [snapshot["wsl"]["distros"][0]]
        snapshot["runtimes"]["podman"]["containers"] = []
        analysis = analyze_snapshot(snapshot, [], self.settings)
        self.assertEqual(analysis["classification"], "retención de caché")

    def test_possible_leak_with_history(self) -> None:
        base = make_snapshot()
        earlier = deepcopy(base)
        earlier["host"]["vmmem_process"]["WorkingSetBytes"] = 4 * 1024**3
        earlier_analysis = {
            "metrics": {
                "total_container_memory_bytes": 600 * 1024**2,
                "cache_retention": False,
            }
        }
        history = [
            {"snapshot": earlier, "analysis": earlier_analysis},
            {"snapshot": earlier, "analysis": earlier_analysis},
            {"snapshot": base, "analysis": {"metrics": {"total_container_memory_bytes": 620 * 1024**2, "cache_retention": False}}},
        ]
        snapshot = make_snapshot()
        snapshot["wsl"]["global_meminfo"]["Cached"] = 256 * 1024**2
        snapshot["wsl"]["global_meminfo"]["Buffers"] = 64 * 1024**2
        snapshot["wsl"]["global_meminfo"]["SReclaimable"] = 64 * 1024**2
        analysis = analyze_snapshot(snapshot, history, self.settings)
        self.assertEqual(analysis["classification"], "posible fuga")


if __name__ == "__main__":
    unittest.main()
