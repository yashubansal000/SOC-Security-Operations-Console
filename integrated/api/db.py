"""Shared DB helpers for the API layer."""

from __future__ import annotations

import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "data" / "processed" / "rca.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def write_audit(conn: sqlite3.Connection, actor: str, action: str,
                incident_id: int | None = None, details: str = "") -> None:
    """Append a row to the audit trail. Every mutating action MUST call this."""
    conn.execute(
        "INSERT INTO audit_log (actor, action, incident_id, details) VALUES (?, ?, ?, ?)",
        (actor, action, incident_id, details),
    )
    conn.commit()
