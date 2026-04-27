from __future__ import annotations

import json
import os
import tomllib
from tomllib import TOMLDecodeError
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT
from .parsers import (
    extract_warning_lines,
    parse_container_stats,
    parse_json_document,
    parse_meminfo,
    parse_process_table,
    parse_relaxed_wslconfig,
    parse_service_list,
    strip_control_chars,
    parse_wsl_list,
)
from .shell import command_exists, run_command, run_powershell


def collect_snapshot(settings: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    host = collect_host(settings, warnings)
    wsl = collect_wsl(settings, warnings)
    runtimes = collect_runtimes(warnings)
    host["warnings"] = sorted(set(warnings))
    return {
        "meta": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "project_root": str(PROJECT_ROOT),
            "profile": "balanceado",
        },
        "host": host,
        "wsl": wsl,
        "runtimes": runtimes,
    }


def collect_host(settings: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    max_top = settings["profile"]["balanceado"]["max_top_processes"]
    total_memory_result = run_powershell(
        "$item = Get-CimInstance Win32_ComputerSystem | "
        "Select-Object @{Name='TotalPhysicalMemory';Expression={[int64]$_.TotalPhysicalMemory}}; "
        "$item | ConvertTo-Json -Compress"
    )
    total_memory = parse_json_document(total_memory_result.stdout) or {}
    process_result = run_powershell(
        "$items = Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object "
        f"-First {max_top} Name,Id,"
        "@{Name='WorkingSetBytes';Expression={[int64]$_.WorkingSet64}},"
        "@{Name='PrivateMemoryBytes';Expression={[int64]$_.PrivateMemorySize64}},CPU; "
        "$items | ConvertTo-Json -Compress"
    )
    top_processes = parse_json_document(process_result.stdout) or []
    if isinstance(top_processes, dict):
        top_processes = [top_processes]

    wsl_status = run_command(["wsl", "--status"])
    wsl_version = run_command(["wsl", "--version"])
    warnings.extend(extract_warning_lines(wsl_status.stderr, settings["reviews"]["warning_patterns"]))
    warnings.extend(extract_warning_lines(wsl_version.stderr, settings["reviews"]["warning_patterns"]))

    wslconfig_path = Path.home() / ".wslconfig"
    wslconfig_raw = ""
    wslconfig: dict[str, Any] = {}
    if wslconfig_path.exists():
        wslconfig_raw = wslconfig_path.read_text(encoding="utf-8", errors="replace")
        try:
            with wslconfig_path.open("rb") as handle:
                wslconfig = tomllib.load(handle)
        except TOMLDecodeError:
            wslconfig = parse_relaxed_wslconfig(wslconfig_raw)
            warnings.append("`.wslconfig` usa sintaxis flexible de WSL; se aplico parser tolerante para leerla.")

    docker_settings_path = Path(os.environ.get("APPDATA", "")) / "Docker" / "settings.json"
    docker_settings = {}
    if docker_settings_path.exists():
        docker_settings = json.loads(docker_settings_path.read_text(encoding="utf-8", errors="replace"))

    vmmem = next(
        (
            process
            for process in top_processes
            if str(process.get("Name", "")).lower() in {"vmmem", "vmmemwsl"}
        ),
        None,
    )
    return {
        "total_memory_bytes": int(total_memory.get("TotalPhysicalMemory", 0)),
        "logical_cpu_count": os.cpu_count() or 0,
        "top_processes": top_processes,
        "vmmem_process": vmmem,
        "wsl_status": strip_control_chars(wsl_status.stdout).strip(),
        "wsl_version": strip_control_chars(wsl_version.stdout).strip(),
        "wslconfig": wslconfig,
        "wslconfig_path": str(wslconfig_path),
        "wslconfig_raw": wslconfig_raw,
        "docker_settings": docker_settings,
        "docker_settings_path": str(docker_settings_path),
        "path_entries": [entry for entry in os.environ.get("PATH", "").split(";") if entry],
    }


def collect_wsl(settings: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
    list_result = run_command(["wsl", "-l", "-v"])
    warnings.extend(extract_warning_lines(list_result.stderr, settings["reviews"]["warning_patterns"]))
    distros = parse_wsl_list(list_result.stdout)
    distro_details = []
    global_meminfo: dict[str, int] = {}

    for distro in distros:
        detail = {"name": distro["name"], "state": distro["state"], "version": distro["version"]}
        if distro["state"].lower() == "running":
            meminfo_result = run_command(
                [
                    "wsl",
                    "-d",
                    distro["name"],
                    "-e",
                    "sh",
                    "-lc",
                    "grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapCached|Active|Inactive|Shmem|Slab|SReclaimable):' /proc/meminfo",
                ],
                timeout=45,
            )
            ps_result = run_command(
                [
                    "wsl",
                    "-d",
                    distro["name"],
                    "-e",
                    "sh",
                    "-lc",
                    "if ps -eo pid,ppid,comm,%mem,%cpu,rss,args --sort=-rss >/dev/null 2>&1; then "
                    "ps -eo pid,ppid,comm,%mem,%cpu,rss,args --sort=-rss | head -n 16; "
                    "elif ps -o pid,ppid,comm,rss,args >/dev/null 2>&1; then "
                    "ps -o pid,ppid,comm,rss,args | head -n 16; "
                    "else echo UNSUPPORTED_PS; fi",
                ],
                timeout=45,
            )
            services_result = run_command(
                [
                    "wsl",
                    "-d",
                    distro["name"],
                    "-e",
                    "sh",
                    "-lc",
                    "if command -v systemctl >/dev/null 2>&1; then "
                    "systemctl list-unit-files --type=service --state=enabled --no-pager | head -n 40; "
                    "fi",
                ],
                timeout=45,
            )
            warnings.extend(extract_warning_lines(meminfo_result.stderr, settings["reviews"]["warning_patterns"]))
            warnings.extend(extract_warning_lines(ps_result.stderr, settings["reviews"]["warning_patterns"]))
            warnings.extend(extract_warning_lines(services_result.stderr, settings["reviews"]["warning_patterns"]))
            detail["meminfo"] = parse_meminfo(meminfo_result.stdout)
            detail["top_processes"] = parse_process_table(ps_result.stdout)
            detail["enabled_services"] = parse_service_list(services_result.stdout)
            if not global_meminfo and detail["meminfo"]:
                global_meminfo = detail["meminfo"]
        distro_details.append(detail)

    return {"distros": distro_details, "global_meminfo": global_meminfo}


def collect_runtimes(warnings: list[str]) -> dict[str, Any]:
    return {
        "docker": collect_runtime("docker", warnings),
        "podman": collect_runtime("podman", warnings),
    }


def collect_runtime(binary: str, warnings: list[str]) -> dict[str, Any]:
    if not command_exists(binary):
        return {"available": False, "containers": [], "stats": {}, "errors": []}

    errors: list[str] = []
    ps_result = run_command([binary, "ps", "--format", "{{json .}}"], timeout=30)
    if ps_result.returncode != 0:
        errors.append(ps_result.stderr.strip())
    container_rows = parse_json_document(ps_result.stdout) if ps_result.stdout.strip() else []
    if isinstance(container_rows, dict):
        container_rows = [container_rows]

    stats_result = run_command([binary, "stats", "--no-stream", "--format", "{{json .}}"], timeout=45)
    if stats_result.returncode != 0 and stats_result.stderr.strip():
        errors.append(stats_result.stderr.strip())
    stats = parse_container_stats(stats_result.stdout)

    container_ids = [row.get("ID") or row.get("Id") for row in container_rows if row.get("ID") or row.get("Id")]
    inspect_rows = []
    if container_ids:
        inspect_result = run_command([binary, "inspect", *container_ids], timeout=45)
        if inspect_result.returncode != 0 and inspect_result.stderr.strip():
            errors.append(inspect_result.stderr.strip())
        inspect_rows = parse_json_document(inspect_result.stdout) if inspect_result.stdout.strip() else []

    warnings.extend(line for line in errors if line)
    limits_by_name = {}
    for row in inspect_rows:
        name = normalize_container_name(row.get("Name") or row.get("Names") or row.get("Config", {}).get("Hostname"))
        host_config = row.get("HostConfig", {}) if isinstance(row, dict) else {}
        limits_by_name[name] = {
            "memory_bytes": int(host_config.get("Memory") or 0),
            "memory_swap_bytes": int(host_config.get("MemorySwap") or 0),
            "nano_cpus": int(host_config.get("NanoCpus") or 0),
        }

    containers = []
    for row in container_rows:
        name = normalize_container_name(row.get("Names") or row.get("Name") or row.get("Container"))
        if not name:
            continue
        containers.append(
            {
                "id": row.get("ID") or row.get("Id") or "",
                "name": name,
                "image": row.get("Image") or row.get("ImageName") or "",
                "status": row.get("Status") or row.get("State") or "",
                "running_for": row.get("RunningFor") or row.get("RunningForHuman") or "",
                "limits": limits_by_name.get(name, {"memory_bytes": 0, "memory_swap_bytes": 0, "nano_cpus": 0}),
                "stats": stats.get(name, {}),
            }
        )

    return {"available": True, "containers": containers, "stats": stats, "errors": [error for error in errors if error]}


def normalize_container_name(value: Any) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    return str(value or "").lstrip("/")
