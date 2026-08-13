from __future__ import annotations

import sqlite3
from pathlib import Path

from .runtime import ExecutionResult


class SQLiteRunStore:
    """Small durable run store with one transaction per checkpoint."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS taskprint_runs (
                    run_id TEXT PRIMARY KEY,
                    workflow TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def save(self, result: ExecutionResult) -> None:
        updated_at = (result.ended_at or result.started_at).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO taskprint_runs
                    (run_id, workflow, fingerprint, status, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    status=excluded.status,
                    updated_at=excluded.updated_at,
                    payload=excluded.payload
                """,
                (
                    result.run_id,
                    result.workflow,
                    result.fingerprint,
                    result.status.value,
                    updated_at,
                    result.model_dump_json(),
                ),
            )

    def load(self, run_id: str) -> ExecutionResult | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM taskprint_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
        return ExecutionResult.model_validate_json(row[0]) if row else None

    def list(self, *, limit: int = 100) -> list[ExecutionResult]:
        if not 1 <= limit <= 10_000:
            raise ValueError("limit must be between 1 and 10000")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM taskprint_runs ORDER BY updated_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [ExecutionResult.model_validate_json(row[0]) for row in rows]
