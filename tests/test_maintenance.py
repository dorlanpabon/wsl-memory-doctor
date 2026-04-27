from __future__ import annotations

import unittest

from wsl_memory_doctor.maintenance import choose_drop_cache_distro, map_drop_cache_mode


class MaintenanceTests(unittest.TestCase):
    def test_choose_default_user_distro(self) -> None:
        distros = [
            {"name": "docker-desktop", "state": "Running", "is_default": False},
            {"name": "Ubuntu-20.04", "state": "Running", "is_default": True},
            {"name": "podman-machine-default", "state": "Stopped", "is_default": False},
        ]
        self.assertEqual(choose_drop_cache_distro(distros, None), "Ubuntu-20.04")

    def test_choose_explicit_user_distro(self) -> None:
        distros = [
            {"name": "Ubuntu-20.04", "state": "Running", "is_default": True},
            {"name": "Alpine", "state": "Stopped", "is_default": False},
        ]
        self.assertEqual(choose_drop_cache_distro(distros, "Alpine"), "Alpine")

    def test_reject_system_distro(self) -> None:
        distros = [
            {"name": "docker-desktop", "state": "Running", "is_default": False},
            {"name": "Ubuntu-20.04", "state": "Running", "is_default": True},
        ]
        with self.assertRaises(ValueError):
            choose_drop_cache_distro(distros, "docker-desktop")

    def test_mode_mapping(self) -> None:
        self.assertEqual(map_drop_cache_mode("pagecache"), 1)
        self.assertEqual(map_drop_cache_mode("dentries"), 2)
        self.assertEqual(map_drop_cache_mode("all"), 3)


if __name__ == "__main__":
    unittest.main()
