from __future__ import annotations

import json
import re
from typing import Any


SIZE_UNITS = {
    "B": 1,
    "KB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
}


def strip_control_chars(text: str) -> str:
    return text.replace("\x00", "").replace("\ufeff", "")


def parse_json_document(text: str) -> Any:
    clean = strip_control_chars(text).strip()
    if not clean:
        return []
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        items = []
        for line in clean.splitlines():
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
        return items


def parse_wsl_list(text: str) -> list[dict[str, Any]]:
    clean = strip_control_chars(text)
    distros: list[dict[str, Any]] = []
    pattern = re.compile(
        r"^(?P<default>\*)?\s*(?P<name>.+?)\s{2,}(?P<state>Running|Stopped|Installing|Uninstalling)\s{2,}(?P<version>\d+)$"
    )
    for raw_line in clean.splitlines():
        line = raw_line.strip()
        if not line or line.upper().startswith("NAME"):
            continue
        match = pattern.match(line)
        if not match:
            continue
        distros.append(
            {
                "name": match.group("name").strip(),
                "state": match.group("state"),
                "version": int(match.group("version")),
                "is_default": bool(match.group("default")),
            }
        )
    return distros


def parse_meminfo(text: str) -> dict[str, int]:
    info: dict[str, int] = {}
    for line in strip_control_chars(text).splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        match = re.search(r"(\d+)", value)
        if match:
            info[key.strip()] = int(match.group(1)) * 1024
    return info


def parse_service_list(text: str) -> list[dict[str, str]]:
    services: list[dict[str, str]] = []
    for raw_line in strip_control_chars(text).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("UNIT FILE") or line.startswith("0 unit files") or line.endswith("listed."):
            continue
        parts = line.split()
        if len(parts) >= 2:
            services.append({"name": parts[0], "state": parts[1]})
    return services


def parse_process_table(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw_line in strip_control_chars(text).splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("PID") or line == "UNSUPPORTED_PS":
            continue
        parts = line.split(None, 6)
        if len(parts) < 4:
            continue
        row: dict[str, Any] = {
            "pid": _to_int(parts[0]),
            "ppid": _to_int(parts[1]) if len(parts) > 1 else 0,
            "command": parts[2] if len(parts) > 2 else "",
        }
        if len(parts) > 5:
            row["rss_bytes"] = _to_int(parts[5]) * 1024
        if len(parts) > 6:
            row["args"] = parts[6]
        rows.append(row)
    rows.sort(key=lambda item: item.get("rss_bytes", 0), reverse=True)
    return rows


def parse_size_to_bytes(value: str) -> int:
    clean = value.strip()
    if not clean or clean in {"--", "0"}:
        return 0
    match = re.match(r"(?P<number>\d+(?:[.,]\d+)?)\s*(?P<unit>[A-Za-z]+)", clean)
    if not match:
        return 0
    number = float(match.group("number").replace(",", "."))
    unit = match.group("unit").upper()
    multiplier = SIZE_UNITS.get(unit)
    if multiplier is None:
        return 0
    return int(number * multiplier)


def parse_container_stats(text: str) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    raw_rows = parse_json_document(text)
    if isinstance(raw_rows, dict):
        rows = [raw_rows]
    else:
        rows = raw_rows
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = row.get("Name") or row.get("Names") or row.get("Container")
        if isinstance(name, list):
            name = name[0] if name else ""
        if not name:
            continue
        raw_memory_usage = row.get("MemUsage") or row.get("Mem Usage") or ""
        if isinstance(raw_memory_usage, (int, float)):
            used_bytes = int(raw_memory_usage)
            limit_bytes = int(row.get("MemLimit") or 0)
        else:
            used, _, limit = str(raw_memory_usage).partition("/")
            used_bytes = parse_size_to_bytes(used)
            limit_bytes = parse_size_to_bytes(limit)
        stats[name] = {
            "cpu_percent": _to_float(row.get("CPUPerc") or row.get("CPU") or "0"),
            "memory_usage_bytes": used_bytes,
            "memory_limit_bytes": limit_bytes,
            "memory_percent": _to_float(row.get("MemPerc") or row.get("MEM %") or "0"),
        }
    return stats


def extract_warning_lines(text: str, patterns: list[str]) -> list[str]:
    warnings: list[str] = []
    for raw_line in strip_control_chars(text).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(pattern.lower() in line.lower() for pattern in patterns):
            warnings.append(line)
    return warnings


def _to_int(value: Any) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(str(value).replace("%", "").replace(",", ".").strip())
    except (TypeError, ValueError):
        return 0.0
