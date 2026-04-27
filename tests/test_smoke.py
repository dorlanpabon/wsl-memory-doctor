from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SmokeTests(unittest.TestCase):
    def test_module_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "wsl_memory_doctor", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("doctor", result.stdout)

    def test_doctor_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "wsl_memory_doctor", "doctor", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Ejecuta el diagnostico", result.stdout)

    def test_drop_cache_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "wsl_memory_doctor", "drop-cache", "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Vacia el page cache", result.stdout)


if __name__ == "__main__":
    unittest.main()
