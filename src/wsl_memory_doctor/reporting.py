from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_reports(report_dir: Path, snapshot: dict[str, Any], analysis: dict[str, Any]) -> tuple[Path, Path]:
    report_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = report_dir / "latest.md"
    json_path = report_dir / "latest.json"
    markdown_path.write_text(render_markdown(snapshot, analysis), encoding="utf-8")
    json_path.write_text(
        json.dumps({"snapshot": snapshot, "analysis": analysis}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return markdown_path, json_path


def render_markdown(snapshot: dict[str, Any], analysis: dict[str, Any]) -> str:
    lines = [
        "# wsl-memory-doctor",
        "",
        f"- Fecha: {snapshot['meta']['created_at']}",
        f"- Clasificación: **{analysis['classification']}**",
        f"- Score de salud: **{analysis['score']}/100**",
        f"- Conclusión: {analysis['conclusion']}",
        "",
        "## Hallazgos",
    ]
    for finding in analysis["findings"]:
        lines.append(f"- [{finding['severity']}] {finding['title']}: {finding['detail']}")
    if not analysis["findings"]:
        lines.append("- Sin hallazgos relevantes.")

    lines.extend(["", "## Qué puedo apagar ya"])
    for item in analysis["recommendations"]["apagar_ya"]:
        lines.append(f"- {item['title']}: `{item['command']}`. {item['detail']}")
    if not analysis["recommendations"]["apagar_ya"]:
        lines.append("- No hay acciones inmediatas sugeridas.")

    lines.extend(["", "## Qué debo reconfigurar"])
    for item in analysis["recommendations"]["reconfigurar"]:
        lines.append(f"- {item['title']}: `{item['command']}`. {item['detail']}")
    if not analysis["recommendations"]["reconfigurar"]:
        lines.append("- No hay cambios de configuración urgentes.")

    lines.extend(["", "## Qué es normal"])
    for item in analysis["recommendations"]["normal"]:
        lines.append(f"- {item}")
    if not analysis["recommendations"]["normal"]:
        lines.append("- No hay notas de normalidad destacadas.")

    metrics = analysis["metrics"]
    lines.extend(
        [
            "",
            "## Evidencia clave",
            f"- RAM host: {_fmt_gib(metrics['host_total_memory_bytes'])}",
            f"- `vmmem`: {_fmt_gib(metrics['vmmem_bytes'])}",
            f"- Caché WSL estimada: {_fmt_gib(metrics['cached_bytes'])}",
            f"- Disponible en WSL: {_fmt_gib(metrics['available_bytes'])}",
            f"- Memoria observada en contenedores: {_fmt_gib(metrics['total_container_memory_bytes'])}",
            f"- Contenedores sin límite: {metrics['unlimited_container_count']}",
        ]
    )
    warnings = snapshot["host"].get("warnings", [])
    if warnings:
        lines.extend(["", "## Advertencias capturadas"])
        for warning in warnings:
            lines.append(f"- {warning}")

    lines.extend(["", "## Propuesta de `.wslconfig`", "```ini", analysis["wslconfig_diff"], "```"])
    return "\n".join(lines) + "\n"


def render_console_summary(snapshot: dict[str, Any], analysis: dict[str, Any]) -> str:
    findings = ", ".join(finding["title"] for finding in analysis["findings"][:4]) or "sin hallazgos"
    return (
        f"{analysis['classification']} | score {analysis['score']}/100 | "
        f"{analysis['conclusion']} | hallazgos: {findings}"
    )


def render_history(runs: list[dict[str, Any]], window_label: str) -> str:
    if not runs:
        return f"No hay snapshots guardados para la ventana {window_label}."
    last = runs[-1]
    first = runs[0]
    first_vmmem = int((first["snapshot"]["host"].get("vmmem_process") or {}).get("WorkingSetBytes") or 0)
    last_vmmem = int((last["snapshot"]["host"].get("vmmem_process") or {}).get("WorkingSetBytes") or 0)
    delta = last_vmmem - first_vmmem
    lines = [
        f"Historial {window_label}",
        f"- Muestras: {len(runs)}",
        f"- Primera clasificación: {first['analysis']['classification']}",
        f"- Última clasificación: {last['analysis']['classification']}",
        f"- `vmmem` inicio: {_fmt_gib(first_vmmem)}",
        f"- `vmmem` fin: {_fmt_gib(last_vmmem)}",
        f"- Delta: {_fmt_gib(delta)}",
    ]
    return "\n".join(lines)


def _fmt_gib(value: int) -> str:
    if value <= 0:
        return "0.00 GiB"
    return f"{value / (1024**3):.2f} GiB"
