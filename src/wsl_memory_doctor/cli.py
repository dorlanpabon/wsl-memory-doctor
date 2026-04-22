from __future__ import annotations

import argparse
from pathlib import Path

from .analyzer import analyze_snapshot
from .collectors import collect_snapshot
from .config import PROJECT_ROOT, load_settings
from .reporting import render_console_summary, render_history, render_markdown, write_reports
from .storage import load_latest_run, load_runs_since, save_run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wsl_memory_doctor", description="Diagnostico local de memoria para WSL, Docker y Podman.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "snapshot",
        help="Captura un snapshot, lo analiza y lo guarda.",
        description="Captura un snapshot, lo analiza y lo guarda.",
    )
    subparsers.add_parser(
        "doctor",
        help="Ejecuta el diagnostico completo y genera reportes.",
        description="Ejecuta el diagnostico completo y genera reportes.",
    )

    history_parser = subparsers.add_parser(
        "history",
        help="Muestra tendencia historica de snapshots guardados.",
        description="Muestra tendencia historica de snapshots guardados.",
    )
    history_parser.add_argument("--window", default="24h", help="Ventana: 1h, 24h, 7d, 168h.")

    export_parser = subparsers.add_parser(
        "export",
        help="Exporta el ultimo snapshot guardado.",
        description="Exporta el ultimo snapshot guardado.",
    )
    export_parser.add_argument("--format", choices=["json", "md"], default="md")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(PROJECT_ROOT)
    db_path = Path(settings["paths"]["db"])
    report_dir = Path(settings["paths"]["reports_dir"])

    if args.command in {"snapshot", "doctor"}:
        history = load_runs_since(db_path, hours=24 * 7)
        snapshot = collect_snapshot(settings)
        analysis = analyze_snapshot(snapshot, history, settings)
        save_run(db_path, snapshot, analysis)
        write_reports(report_dir, snapshot, analysis)
        output = render_markdown(snapshot, analysis) if args.command == "doctor" else render_console_summary(snapshot, analysis)
        print(output)
        return 0

    if args.command == "history":
        hours = parse_window_to_hours(args.window)
        runs = load_runs_since(db_path, hours=hours)
        print(render_history(runs, args.window))
        return 0

    if args.command == "export":
        latest = load_latest_run(db_path)
        if latest is None:
            print("No hay snapshots guardados todavía.")
            return 1
        write_reports(report_dir, latest["snapshot"], latest["analysis"])
        if args.format == "json":
            print((report_dir / "latest.json").read_text(encoding="utf-8"))
        else:
            print((report_dir / "latest.md").read_text(encoding="utf-8"))
        return 0

    parser.print_help()
    return 1


def parse_window_to_hours(value: str) -> int:
    clean = value.strip().lower()
    if clean.endswith("h"):
        return int(clean[:-1])
    if clean.endswith("d"):
        return int(clean[:-1]) * 24
    raise ValueError(f"Ventana no soportada: {value}")
