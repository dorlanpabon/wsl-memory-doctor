from __future__ import annotations

import unittest

from wsl_memory_doctor.parsers import parse_container_stats, parse_meminfo, parse_wsl_list


class ParserTests(unittest.TestCase):
    def test_parse_wsl_list(self) -> None:
        raw = "\x00*\x00 Ubuntu-20.04          Running         2\r\n  docker-desktop       Running         2\r\n  Alpine               Stopped         2\r\n"
        parsed = parse_wsl_list(raw)
        self.assertEqual(parsed[0]["name"], "Ubuntu-20.04")
        self.assertTrue(parsed[0]["is_default"])
        self.assertEqual(parsed[1]["name"], "docker-desktop")
        self.assertEqual(parsed[2]["state"], "Stopped")

    def test_parse_meminfo(self) -> None:
        raw = "MemTotal:       16332992 kB\nMemAvailable:   13279316 kB\nCached:          4774812 kB\n"
        parsed = parse_meminfo(raw)
        self.assertEqual(parsed["MemTotal"], 16332992 * 1024)
        self.assertEqual(parsed["Cached"], 4774812 * 1024)

    def test_parse_container_stats(self) -> None:
        raw = (
            '{"Name":"supabase_db","CPUPerc":"0.04%","MemUsage":"154.6MiB / 15.58GiB","MemPerc":"0.97%"}\n'
            '{"Name":"localstack-main","CPUPerc":"5.30%","MemUsage":"432.4MB / 16.72GB","MemPerc":"2.59%"}\n'
        )
        parsed = parse_container_stats(raw)
        self.assertIn("supabase_db", parsed)
        self.assertGreater(parsed["supabase_db"]["memory_usage_bytes"], 150 * 1024 * 1024)
        self.assertGreater(parsed["localstack-main"]["memory_limit_bytes"], 16 * 1000 * 1000 * 1000)

    def test_parse_container_stats_numeric(self) -> None:
        raw = '{"Name":"localstack-main","CPU":5.29,"MemUsage":432373760,"MemLimit":16724983808,"MemPerc":2.58}'
        parsed = parse_container_stats(raw)
        self.assertEqual(parsed["localstack-main"]["memory_usage_bytes"], 432373760)
        self.assertEqual(parsed["localstack-main"]["memory_limit_bytes"], 16724983808)


if __name__ == "__main__":
    unittest.main()
