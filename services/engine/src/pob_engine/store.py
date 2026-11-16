from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BuildStore:
    """SQLite library of builds and immutable revisions.

    A revision row is written once. Later edits insert a new row. The build's
    saved_revision_id is the stored original, and it moves only when a revision
    is created with status "saved".
    """

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS builds (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                saved_revision_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS revisions (
                id TEXT PRIMARY KEY,
                build_id TEXT NOT NULL,
                parent_id TEXT,
                name TEXT NOT NULL,
                label TEXT NOT NULL,
                xml TEXT NOT NULL,
                created_at TEXT NOT NULL,
                engine_revision TEXT,
                tree_version TEXT,
                status TEXT NOT NULL DEFAULT 'saved'
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
            CREATE INDEX IF NOT EXISTS revisions_by_build ON revisions(build_id, created_at);
            """
        )
        self._ensure_column("revisions", "status", "TEXT NOT NULL DEFAULT 'saved'")
        self.conn.commit()

    def _ensure_column(self, table: str, column: str, ddl: str) -> None:
        existing = {row[1] for row in self.conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

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
        status: str | None = None,
    ) -> dict:
        if status is None:
            status = "draft" if parent_id else "saved"
        if status not in {"saved", "draft"}:
            raise ValueError(f"Unknown revision status {status}")
        revision_id = uuid.uuid4().hex
        now = _now()
        build_id = build_id or uuid.uuid4().hex
        if self._build_row(build_id) is None:
            self.conn.execute(
                """
                INSERT INTO builds (id, name, saved_revision_id, created_at, updated_at)
                VALUES (?, ?, NULL, ?, ?)
                """,
                (build_id, name, now, now),
            )
        self.conn.execute(
            """
            INSERT INTO revisions (
                id, build_id, parent_id, name, label, xml, created_at,
                engine_revision, tree_version, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                build_id,
                parent_id,
                name,
                label,
                xml,
                now,
                engine_revision,
                tree_version,
                status,
            ),
        )
        self.conn.execute(
            "INSERT INTO revision_search (name, label, revision_id) VALUES (?, ?, ?)",
            (name, label, revision_id),
        )
        if status == "saved":
            self.conn.execute(
                "UPDATE builds SET saved_revision_id = ?, updated_at = ?, name = ? WHERE id = ?",
                (revision_id, now, name, build_id),
            )
        self.conn.commit()
        return self.get(revision_id)

    def get(self, revision_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM revisions WHERE id = ?", (revision_id,)).fetchone()
        if row is None:
            raise KeyError(revision_id)
        return dict(row)

    def get_build(self, build_id: str) -> dict:
        row = self._build_row(build_id)
        if row is None:
            raise KeyError(build_id)
        return row

    def _build_row(self, build_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM builds WHERE id = ?", (build_id,)).fetchone()
        if row is None:
            return None
        return dict(row)

    def list_builds(self, query: str = "") -> list[dict]:
        sql = """
            SELECT
                builds.id,
                builds.name,
                builds.saved_revision_id,
                builds.created_at,
                builds.updated_at,
                revisions.label AS saved_label,
                revisions.tree_version,
                revisions.engine_revision
            FROM builds
            LEFT JOIN revisions ON revisions.id = builds.saved_revision_id
        """
        parameters: tuple = ()
        text = query.strip()
        if text:
            sql += " WHERE builds.name LIKE ? ESCAPE '\\'"
            parameters = (f"%{_like(text)}%",)
        sql += " ORDER BY builds.updated_at DESC"
        return [dict(row) for row in self.conn.execute(sql, parameters)]

    def list_revisions(self, build_id: str) -> list[dict]:
        if self._build_row(build_id) is None:
            raise KeyError(build_id)
        rows = self.conn.execute(
            """
            SELECT * FROM revisions
            WHERE build_id = ?
            ORDER BY created_at, rowid
            """,
            (build_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def delete_draft(self, revision_id: str) -> dict:
        row = self.get(revision_id)
        build = self.get_build(row["build_id"])
        if build["saved_revision_id"] == revision_id:
            raise ValueError("The stored build cannot be discarded.")
        if row["status"] != "draft":
            raise ValueError("Only an unsaved working copy can be discarded.")
        child = self.conn.execute(
            "SELECT id FROM revisions WHERE parent_id = ?",
            (revision_id,),
        ).fetchone()
        if child is not None:
            raise ValueError("This working copy has later revisions.")
        self.conn.execute("DELETE FROM revision_search WHERE revision_id = ?", (revision_id,))
        self.conn.execute("DELETE FROM calculations WHERE revision_id = ?", (revision_id,))
        self.conn.execute("DELETE FROM revisions WHERE id = ?", (revision_id,))
        self.conn.commit()
        return row

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


def _like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
