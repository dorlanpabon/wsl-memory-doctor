from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .parsers import parse_meminfo, parse_wsl_list
from .shell import run_command, run_powershell


GIB = 1024**3
SYSTEM_DISTROS = {"docker-desktop", "podman-machine-default"}
DROP_MODE_VALUES = {"pagecache": 1, "dentries": 2, "all": 3}


@dataclass(slots=True)
class DropCacheResult:
    distro: str
    mode: str
    before_meminfo: dict[str, int]
    after_meminfo: dict[str, int]
    before_vmmem_bytes: int
    after_vmmem_bytes: int
    stderr_lines: list[str]


def drop_wsl_cache(distro: str | None, mode: str, wait_seconds: float) -> DropCacheResult:
    distros = list_wsl_distros()
    target = choose_drop_cache_distro(distros, distro)
    drop_value = map_drop_cache_mode(mode)
    before_meminfo = read_wsl_meminfo(target)
    before_vmmem_bytes = read_host_vmmem_bytes()

    result = run_command(
        [
            "wsl",
            "-d",
            target,
            "-u",
            "root",
            "-e",
            "sh",
            "-lc",
            f"sync && printf '%s\\n' {drop_value} > /proc/sys/vm/drop_caches",
        ],
        timeout=60,
    )
    stderr_lines = [line.strip() for line in result.stderr.splitlines() if line.strip()]
    if result.returncode != 0:
        message = stderr_lines[-1] if stderr_lines else "No se pudo ejecutar drop_caches."
        raise RuntimeError(message)

    if wait_seconds > 0:
        time.sleep(wait_seconds)

    after_meminfo = read_wsl_meminfo(target)
    after_vmmem_bytes = read_host_vmmem_bytes()
    return DropCacheResult(
        distro=target,
        mode=mode,
        before_meminfo=before_meminfo,
        after_meminfo=after_meminfo,
        before_vmmem_bytes=before_vmmem_bytes,
        after_vmmem_bytes=after_vmmem_bytes,
        stderr_lines=stderr_lines,
    )


def list_wsl_distros() -> list[dict[str, Any]]:
    result = run_command(["wsl", "-l", "-v"], timeout=30)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "No se pudo listar WSL.")
    distros = parse_wsl_list(result.stdout)
    if not distros:
        raise RuntimeError("No se encontraron distros WSL.")
    return distros


def choose_drop_cache_distro(distros: list[dict[str, Any]], explicit_distro: str | None) -> str:
    known_names = {str(item.get("name", "")) for item in distros}
    if explicit_distro:
        if explicit_distro not in known_names:
            raise ValueError(f"La distro '{explicit_distro}' no existe en WSL.")
        if explicit_distro in SYSTEM_DISTROS:
            raise ValueError(f"La distro '{explicit_distro}' es una distro de sistema. Usa una distro de usuario.")
        return explicit_distro

    user_distros = [item for item in distros if item.get("name") not in SYSTEM_DISTROS]
    if not user_distros:
        raise ValueError("No hay distros de usuario disponibles para vaciar cache.")

    default_distro = next((item for item in user_distros if item.get("is_default")), None)
    if default_distro is not None:
        return str(default_distro["name"])

    running_distro = next((item for item in user_distros if str(item.get("state", "")).lower() == "running"), None)
    if running_distro is not None:
        return str(running_distro["name"])

    return str(user_distros[0]["name"])


def map_drop_cache_mode(mode: str) -> int:
    if mode not in DROP_MODE_VALUES:
        raise ValueError(f"Modo no soportado: {mode}")
    return DROP_MODE_VALUES[mode]


def read_wsl_meminfo(distro: str) -> dict[str, int]:
    result = run_command(
        [
            "wsl",
            "-d",
            distro,
            "-e",
            "sh",
            "-lc",
            "grep -E '^(MemTotal|MemFree|MemAvailable|Buffers|Cached|SReclaimable):' /proc/meminfo",
        ],
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"No se pudo leer /proc/meminfo en {distro}.")
    return parse_meminfo(result.stdout)


def read_host_vmmem_bytes() -> int:
    result = run_powershell(
        "$p = Get-Process -Name vmmem,vmmemWSL -ErrorAction SilentlyContinue | "
        "Sort-Object WorkingSet64 -Descending | Select-Object -First 1 -ExpandProperty WorkingSet64; "
        "if ($p) { Write-Output $p } else { Write-Output 0 }",
        timeout=20,
    )
    try:
        return int((result.stdout or "0").strip())
    except ValueError:
        return 0


def render_drop_cache_report(result: DropCacheResult) -> str:
    before_cache = estimate_cache_bytes(result.before_meminfo)
    after_cache = estimate_cache_bytes(result.after_meminfo)
    before_available = int(result.before_meminfo.get("MemAvailable") or 0)
    after_available = int(result.after_meminfo.get("MemAvailable") or 0)

    lines = [
        f"Drop cache ejecutado en `{result.distro}` con modo `{result.mode}`.",
        f"- Cache WSL antes: {fmt_gib(before_cache)}",
        f"- Cache WSL despues: {fmt_gib(after_cache)}",
        f"- Disponible antes: {fmt_gib(before_available)}",
        f"- Disponible despues: {fmt_gib(after_available)}",
        f"- vmmem antes: {fmt_gib(result.before_vmmem_bytes)}",
        f"- vmmem despues: {fmt_gib(result.after_vmmem_bytes)}",
    ]
    if result.after_vmmem_bytes >= result.before_vmmem_bytes:
        lines.append("- Nota: limpiar el page cache no siempre baja `vmmem` enseguida; WSL puede retener memoria hasta un `wsl --shutdown` o `autoMemoryReclaim`.")
    if result.stderr_lines:
        lines.append("- Advertencias capturadas:")
        lines.extend(f"  {line}" for line in result.stderr_lines[:4])
    return "\n".join(lines)


def estimate_cache_bytes(meminfo: dict[str, int]) -> int:
    return int(meminfo.get("Cached") or 0) + int(meminfo.get("Buffers") or 0) + int(meminfo.get("SReclaimable") or 0)


def fmt_gib(value: int) -> str:
    if value <= 0:
        return "0.00 GiB"
    return f"{value / GIB:.2f} GiB"
