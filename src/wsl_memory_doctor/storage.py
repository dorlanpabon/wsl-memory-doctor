from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                analysis_json TEXT NOT NULL
            )
            """
        )
        connection.commit()


def save_run(db_path: Path, snapshot: dict[str, Any], analysis: dict[str, Any]) -> int:
    init_db(db_path)
    created_at = snapshot["meta"]["created_at"]
    with sqlite3.connect(db_path) as connection:
        cursor = connection.execute(
            "INSERT INTO snapshots (created_at, snapshot_json, analysis_json) VALUES (?, ?, ?)",
            (created_at, json.dumps(snapshot), json.dumps(analysis)),
        )
        connection.commit()
        return int(cursor.lastrowid)


def load_latest_run(db_path: Path) -> dict[str, Any] | None:
    if not db_path.exists():
        return None
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT id, created_at, snapshot_json, analysis_json FROM snapshots ORDER BY id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "created_at": row[1],
        "snapshot": json.loads(row[2]),
        "analysis": json.loads(row[3]),
    }


def load_runs_since(db_path: Path, hours: int) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at, snapshot_json, analysis_json
            FROM snapshots
            WHERE created_at >= ?
            ORDER BY id ASC
            """,
            (since.isoformat(),),
        ).fetchall()
    return [
        {
            "id": row[0],
            "created_at": row[1],
            "snapshot": json.loads(row[2]),
            "analysis": json.loads(row[3]),
        }
        for row in rows
    ]
