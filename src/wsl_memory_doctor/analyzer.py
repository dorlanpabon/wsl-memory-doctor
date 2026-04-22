from __future__ import annotations

import math
from typing import Any


GIB = 1024**3
MIB = 1024**2


def analyze_snapshot(
    snapshot: dict[str, Any],
    history: list[dict[str, Any]],
    settings: dict[str, Any],
) -> dict[str, Any]:
    profile = settings["profile"]["balanceado"]
    host = snapshot["host"]
    wsl = snapshot["wsl"]
    runtimes = snapshot["runtimes"]
    findings: list[dict[str, Any]] = []
    recommendations = {"apagar_ya": [], "reconfigurar": [], "normal": []}

    total_memory = int(host.get("total_memory_bytes") or 0)
    vmmem_process = host.get("vmmem_process") or {}
    vmmem_bytes = int(vmmem_process.get("WorkingSetBytes") or 0)
    global_meminfo = wsl.get("global_meminfo") or {}
    mem_total = int(global_meminfo.get("MemTotal") or 0)
    mem_available = int(global_meminfo.get("MemAvailable") or 0)
    cached_bytes = int(global_meminfo.get("Cached") or 0) + int(global_meminfo.get("Buffers") or 0) + int(global_meminfo.get("SReclaimable") or 0)

    docker = runtimes.get("docker", {})
    podman = runtimes.get("podman", {})
    all_containers = docker.get("containers", []) + podman.get("containers", [])
    total_container_memory = sum(int(container.get("stats", {}).get("memory_usage_bytes") or 0) for container in all_containers)
    unlimited_containers = [container for container in all_containers if int(container.get("limits", {}).get("memory_bytes") or 0) == 0]
    running_distro_names = {
        distro["name"]
        for distro in wsl.get("distros", [])
        if distro.get("state", "").lower() == "running"
    }
    docker_active = bool(docker.get("containers")) or "docker-desktop" in running_distro_names
    podman_active = bool(podman.get("containers")) or "podman-machine-default" in running_distro_names

    high_vmmem_threshold = max(int(total_memory * profile["high_vmmem_host_ratio"]), int(profile["high_vmmem_min_gb"] * GIB))
    high_vmmem = vmmem_bytes >= high_vmmem_threshold
    high_cache = mem_total > 0 and cached_bytes / mem_total >= profile["high_cache_ratio"]
    high_available = mem_total > 0 and mem_available / mem_total >= profile["high_available_ratio"]
    cache_retention = high_vmmem and high_cache and high_available
    wslconfig = host.get("wslconfig") or {}
    wsl2_cfg = wslconfig.get("wsl2", {})
    experimental_cfg = wslconfig.get("experimental", {})

    if high_vmmem:
        findings.append(
            _finding(
                "high_vmmem",
                "high",
                "vmmem alto",
                f"`vmmem` está usando {fmt_gib(vmmem_bytes)} sobre {fmt_gib(total_memory)} del host.",
            )
        )

    if docker_active and podman_active:
        findings.append(
            _finding(
                "double_runtime",
                "high",
                "Docker y Podman activos al mismo tiempo",
                "Hay dos backends WSL activos y ambos pueden retener memoria en la VM compartida.",
            )
        )
        recommendations["apagar_ya"].append(
            {
                "title": "Parar el runtime que no estés usando",
                "command": "podman machine stop",
                "detail": "Si hoy tu flujo principal está en Docker/Supabase, apaga Podman primero y vuelve a medir.",
            }
        )
        recommendations["apagar_ya"].append(
            {
                "title": "Cerrar WSL después de cambios",
                "command": "wsl --shutdown",
                "detail": "Reinicia la VM compartida para forzar reclamación de memoria tras detener runtimes.",
            }
        )

    missing_limits = [key for key in ("memory", "processors", "swap") if key not in wsl2_cfg]
    if missing_limits:
        findings.append(
            _finding(
                "missing_wsl_limits",
                "medium",
                ".wslconfig incompleto",
                f"Faltan límites globales en `.wslconfig`: {', '.join(missing_limits)}.",
            )
        )

    auto_reclaim = str(experimental_cfg.get("autoMemoryReclaim", "")).strip()
    if not auto_reclaim or auto_reclaim.lower() == "disabled":
        findings.append(
            _finding(
                "missing_auto_memory_reclaim",
                "medium",
                "WSL sin `autoMemoryReclaim` efectivo",
                "WSL puede retener caché en memoria aunque la carga real ya haya bajado.",
            )
        )

    if unlimited_containers:
        findings.append(
            _finding(
                "unlimited_containers",
                "high",
                "Contenedores sin límite de memoria",
                f"Hay {len(unlimited_containers)} contenedores activos sin `mem_limit` ni `docker update --memory`.",
            )
        )
        for container in unlimited_containers:
            limit_mib = suggest_container_limit_mib(container, profile)
            runtime = "docker" if container in docker.get("containers", []) else "podman"
            command = (
                f"{runtime} update --memory {limit_mib}m {container['name']}"
                if runtime == "docker"
                else f"podman update --memory {limit_mib}m {container['name']}"
            )
            recommendations["reconfigurar"].append(
                {
                    "title": f"Limitar {container['name']}",
                    "command": command,
                    "detail": f"Uso actual observado: {fmt_mib(container.get('stats', {}).get('memory_usage_bytes', 0))}. Ajusta luego el compose para persistirlo.",
                }
            )

    review_service_names = set(settings["reviews"]["service_names"])
    review_services = []
    for distro in wsl.get("distros", []):
        if distro.get("name", "").lower().startswith(("docker-desktop", "podman-machine-default")):
            continue
        review_services.extend(service["name"] for service in distro.get("enabled_services", []) if service["name"] in review_service_names)
    if review_services:
        findings.append(
            _finding(
                "review_services",
                "medium",
                "Servicios persistentes en Ubuntu",
                f"Conviene revisar servicios habilitados que suelen sobrar en WSL: {', '.join(sorted(set(review_services)))}.",
            )
        )
        distro_name = next(
            (distro["name"] for distro in wsl.get("distros", []) if distro.get("name") not in {"docker-desktop", "podman-machine-default"}),
            "Ubuntu",
        )
        recommendations["reconfigurar"].append(
            {
                "title": "Auditar servicios persistentes",
                "command": f'wsl -d {distro_name} -e sh -lc "systemctl status snapd.service cloud-init.service ModemManager.service"',
                "detail": "Valida cuáles realmente necesitas antes de deshabilitarlos.",
            }
        )

    warnings = host.get("warnings", [])
    if warnings:
        findings.append(
            _finding(
                "wsl_warnings",
                "medium",
                "Advertencias de host/WSL",
                "WSL está devolviendo advertencias de montaje o traducción de rutas que conviene limpiar.",
            )
        )
        recommendations["reconfigurar"].append(
            {
                "title": "Revisar PATH heredado a WSL",
                "command": r"[Environment]::GetEnvironmentVariable('Path','User')",
                "detail": "Busca rutas redundantes o problemáticas que WSL intenta traducir al iniciar.",
            }
        )

    if cache_retention:
        findings.append(
            _finding(
                "cache_retention",
                "medium",
                "Patrón de retención de caché",
                f"WSL muestra {fmt_gib(mem_available)} disponibles y {fmt_gib(cached_bytes)} en caché; eso parece más retención que consumo activo puro.",
            )
        )
        recommendations["normal"].append(
            "Es normal que WSL 2 conserve page cache. Si la memoria disponible dentro de WSL sigue alta, no es una fuga por sí sola."
        )

    if host.get("docker_settings", {}).get("useResourceSaver", False):
        recommendations["normal"].append(
            "Docker Desktop ya tiene `useResourceSaver=true`; en WSL eso ayuda más al CPU que a la RAM."
        )

    leak_suspected = _detect_possible_leak(history, profile)
    classification = "normal"
    conclusion = "No hay suficiente evidencia de fuga."
    if leak_suspected:
        classification = "posible fuga"
        conclusion = "La tendencia histórica sugiere crecimiento sostenido con carga relativamente estable."
    elif docker_active and podman_active and high_vmmem:
        classification = "sobrecarga por runtimes"
        conclusion = "El consumo apunta primero a dos runtimes activos y a contenedores sin límites, no a una fuga inmediata."
    elif cache_retention:
        classification = "retención de caché"
        conclusion = "El patrón dominante es caché retenida por WSL más que memoria activa irrecuperable."
    elif findings:
        classification = "normal"
        conclusion = "Hay oportunidades claras de optimización, pero no una fuga evidente con la foto actual."

    penalties = {"high": 18, "medium": 10, "low": 4}
    score = max(0, 100 - sum(penalties[item["severity"]] for item in findings))

    recommendations["reconfigurar"].insert(
        0,
        {
            "title": "Propuesta balanceada para `.wslconfig`",
            "command": "wsl --shutdown",
            "detail": "Aplica la propuesta, guarda el archivo y luego reinicia WSL para medir otra vez.",
        },
    )

    return {
        "classification": classification,
        "conclusion": conclusion,
        "score": score,
        "metrics": {
            "host_total_memory_bytes": total_memory,
            "vmmem_bytes": vmmem_bytes,
            "cached_bytes": cached_bytes,
            "available_bytes": mem_available,
            "total_container_memory_bytes": total_container_memory,
            "unlimited_container_count": len(unlimited_containers),
            "docker_active": docker_active,
            "podman_active": podman_active,
            "high_vmmem": high_vmmem,
            "cache_retention": cache_retention,
        },
        "findings": findings,
        "recommendations": recommendations,
        "wslconfig_diff": build_wslconfig_diff(wslconfig, profile),
    }


def build_wslconfig_diff(wslconfig: dict[str, Any], profile: dict[str, Any]) -> str:
    current_wsl2 = wslconfig.get("wsl2", {})
    current_experimental = wslconfig.get("experimental", {})
    lines = ["--- actual", "+++ propuesta", "[wsl2]"]
    for key, value in (
        ("memory", f"{profile['recommended_memory_gb']}GB"),
        ("processors", profile["recommended_processors"]),
        ("swap", f"{profile['recommended_swap_gb']}GB"),
    ):
        current = current_wsl2.get(key)
        if current != value:
            lines.append(f"-{key}={current}" if current not in {None, ''} else f"# {key} no definido")
            lines.append(f"+{key}={value}")
    lines.append("[experimental]")
    proposed_reclaim = profile["auto_memory_reclaim"]
    current_reclaim = current_experimental.get("autoMemoryReclaim")
    if current_reclaim != proposed_reclaim:
        lines.append(
            f"-autoMemoryReclaim={current_reclaim}" if current_reclaim not in {None, ''} else "# autoMemoryReclaim no definido"
        )
        lines.append(f"+autoMemoryReclaim={proposed_reclaim}")
    return "\n".join(lines)


def suggest_container_limit_mib(container: dict[str, Any], profile: dict[str, Any]) -> int:
    current = int(container.get("stats", {}).get("memory_usage_bytes") or 0)
    multiplier = float(profile["container_margin_multiplier"])
    minimum = int(profile["min_container_limit_mib"])
    maximum = int(profile["max_container_limit_mib"])
    suggested = max(minimum, math.ceil((current / MIB) * multiplier / 64) * 64)
    return min(maximum, suggested)


def _detect_possible_leak(history: list[dict[str, Any]], profile: dict[str, Any]) -> bool:
    if len(history) < 3:
        return False
    recent = history[-min(len(history), 8) :]
    first = recent[0]["snapshot"]["host"].get("vmmem_process") or {}
    last = recent[-1]["snapshot"]["host"].get("vmmem_process") or {}
    first_bytes = int(first.get("WorkingSetBytes") or 0)
    last_bytes = int(last.get("WorkingSetBytes") or 0)
    if first_bytes <= 0 or last_bytes <= 0:
        return False
    growth_ratio = (last_bytes - first_bytes) / first_bytes
    if growth_ratio < profile["possible_leak_growth_ratio"]:
        return False
    first_containers = recent[0]["analysis"]["metrics"].get("total_container_memory_bytes", 0)
    last_containers = recent[-1]["analysis"]["metrics"].get("total_container_memory_bytes", 0)
    stable_workload = first_containers == 0 or abs(last_containers - first_containers) / max(first_containers, 1) <= profile["possible_leak_stability_tolerance"]
    cache_retention = recent[-1]["analysis"]["metrics"].get("cache_retention", False)
    return stable_workload and not cache_retention


def _finding(code: str, severity: str, title: str, detail: str) -> dict[str, str]:
    return {"code": code, "severity": severity, "title": title, "detail": detail}


def fmt_gib(value: int) -> str:
    if value <= 0:
        return "0.00 GiB"
    return f"{value / GIB:.2f} GiB"


def fmt_mib(value: int) -> str:
    if value <= 0:
        return "0 MiB"
    return f"{value / MIB:.0f} MiB"
