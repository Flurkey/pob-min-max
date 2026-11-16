from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BuildStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS revisions (
                id TEXT PRIMARY KEY,
                build_id TEXT NOT NULL,
                parent_id TEXT,
                name TEXT NOT NULL,
                label TEXT NOT NULL,
                xml TEXT NOT NULL,
                created_at TEXT NOT NULL,
                engine_revision TEXT,
                tree_version TEXT
            );
            CREATE TABLE IF NOT EXISTS calculations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                revision_id TEXT NOT NULL,
                calculated_at TEXT NOT NULL,
                engine_revision TEXT NOT NULL,
                tree_version TEXT,
                output_revision INTEGER,
                stats_json TEXT NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS revision_search USING fts5(
                name,
                label,
                revision_id UNINDEXED
            );
            """
        )
        self.conn.commit()

    def create(
        self,
        *,
        name: str,
        xml: str,
        label: str,
        engine_revision: str,
        tree_version: str | None,
        parent_id: str | None = None,
        build_id: str | None = None,
    ) -> dict:
        revision_id = uuid.uuid4().hex
        build_id = build_id or uuid.uuid4().hex
        self.conn.execute(
            """
            INSERT INTO revisions (
                id, build_id, parent_id, name, label, xml, created_at, engine_revision, tree_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (revision_id, build_id, parent_id, name, label, xml, _now(), engine_revision, tree_version),
        )
        self.conn.execute(
            "INSERT INTO revision_search (name, label, revision_id) VALUES (?, ?, ?)",
            (name, label, revision_id),
        )
        self.conn.commit()
        return self.get(revision_id)

    def get(self, revision_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM revisions WHERE id = ?", (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        return dict(row)

    def record_calculation(self, revision_id: str, calculation: dict) -> None:
        self.conn.execute(
            """
            INSERT INTO calculations (
                revision_id, calculated_at, engine_revision, tree_version, output_revision, stats_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                _now(),
                calculation.get("engineRevision") or "",
                calculation.get("treeVersion"),
                calculation.get("outputRevision"),
                json.dumps(calculation.get("stats") or {}),
            ),
        )
        self.conn.commit()

    def latest_cached_stats(self, revision_id: str) -> dict | None:
        row = self.conn.execute(
            """
            SELECT stats_json FROM calculations
            WHERE revision_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (revision_id,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["stats_json"])

    def search(self, query: str) -> list[dict]:
        if not query.strip():
            return []
        rows = self.conn.execute(
            """
            SELECT revisions.*
            FROM revision_search
            JOIN revisions ON revisions.id = revision_search.revision_id
            WHERE revision_search MATCH ?
            ORDER BY revisions.created_at
            """,
            (query,),
        ).fetchall()
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.conn.close()
