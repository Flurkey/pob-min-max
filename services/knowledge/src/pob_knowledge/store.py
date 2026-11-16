from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pob_knowledge.errors import KnowledgeError
from pob_knowledge.export import export_checkout
from pob_knowledge.graph import AscendancyInfo, CharacterClass, PassiveGraph, PassiveNode
from pob_knowledge.paths import SOURCE, SOURCE_REPO, KnowledgePaths, resolve_paths


def _now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeStore:
    """SQLite copy of item, gem, and passive-tree data from one PoB checkout."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS imports (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_commit TEXT NOT NULL,
                game_version TEXT NOT NULL,
                tree_version TEXT NOT NULL,
                manifest_version TEXT NOT NULL,
                retrieval_date TEXT NOT NULL,
                retrieved_at TEXT NOT NULL,
                points_json TEXT NOT NULL,
                classes_json TEXT NOT NULL,
                alternates_json TEXT NOT NULL,
                item_base_count INTEGER NOT NULL,
                unique_count INTEGER NOT NULL,
                gem_count INTEGER NOT NULL,
                mod_count INTEGER NOT NULL,
                node_count INTEGER NOT NULL,
                edge_count INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS item_bases (
                import_id TEXT NOT NULL,
                name TEXT NOT NULL,
                item_type TEXT,
                source_path TEXT NOT NULL,
                record_json TEXT NOT NULL,
                PRIMARY KEY (import_id, name)
            );
            CREATE TABLE IF NOT EXISTS unique_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id TEXT NOT NULL,
                name TEXT NOT NULL,
                base_name TEXT NOT NULL,
                category TEXT NOT NULL,
                source_path TEXT NOT NULL,
                raw_text TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS item_mods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id TEXT NOT NULL,
                mod_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                mod_text TEXT NOT NULL,
                record_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS gems (
                import_id TEXT NOT NULL,
                gem_id TEXT NOT NULL,
                name TEXT NOT NULL,
                granted_effect_id TEXT NOT NULL,
                source_path TEXT NOT NULL,
                record_json TEXT NOT NULL,
                PRIMARY KEY (import_id, gem_id)
            );
            CREATE TABLE IF NOT EXISTS passive_nodes (
                import_id TEXT NOT NULL,
                node_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                node_type TEXT NOT NULL,
                ascendancy_name TEXT,
                class_start_index INTEGER,
                source_path TEXT NOT NULL,
                record_json TEXT NOT NULL,
                PRIMARY KEY (import_id, node_id)
            );
            CREATE TABLE IF NOT EXISTS passive_edges (
                import_id TEXT NOT NULL,
                from_id INTEGER NOT NULL,
                to_id INTEGER NOT NULL,
                PRIMARY KEY (import_id, from_id, to_id)
            );
            CREATE INDEX IF NOT EXISTS unique_items_by_name ON unique_items(import_id, name);
            CREATE INDEX IF NOT EXISTS gems_by_name ON gems(import_id, name);
            CREATE INDEX IF NOT EXISTS nodes_by_name ON passive_nodes(import_id, name);
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_search USING fts5(
                kind,
                name,
                body,
                ref UNINDEXED,
                import_id UNINDEXED
            );
            """
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def import_checkout(self, paths: KnowledgePaths | None = None) -> dict:
        paths = paths or resolve_paths()
        retrieved = _now()
        document, commit, manifest = export_checkout(paths)
        import_id = uuid.uuid4().hex
        source_url = f"{SOURCE_REPO}/tree/{commit}"
        provenance = {
            "source": SOURCE,
            "sourceUrl": source_url,
            "sourceCommit": commit,
            "gameVersion": document["treeDisplay"],
            "treeVersion": document["treeVersion"],
            "manifestVersion": manifest,
            "retrievalDate": retrieved.date().isoformat(),
            "retrievedAt": retrieved.isoformat(),
        }
        self._replace()
        self.conn.execute(
            """
            INSERT INTO imports (
                id, source, source_url, source_commit, game_version, tree_version,
                manifest_version, retrieval_date, retrieved_at, points_json,
                classes_json, alternates_json, item_base_count, unique_count,
                gem_count, mod_count, node_count, edge_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                import_id,
                SOURCE,
                source_url,
                commit,
                document["treeDisplay"],
                document["treeVersion"],
                manifest,
                provenance["retrievalDate"],
                provenance["retrievedAt"],
                json.dumps(document["points"]),
                json.dumps(document["classes"]),
                json.dumps(document["alternateAscendancies"]),
                len(document["bases"]),
                len(document["uniques"]),
                len(document["gems"]),
                len(document["mods"]),
                len(document["nodes"]),
                len(document["edges"]),
            ),
        )
        self.conn.executemany(
            """
            INSERT INTO item_bases (import_id, name, item_type, source_path, record_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    import_id,
                    base["name"],
                    base.get("itemType"),
                    base["sourcePath"],
                    json.dumps(base, ensure_ascii=False),
                )
                for base in document["bases"]
            ),
        )
        self.conn.executemany(
            """
            INSERT INTO unique_items (import_id, name, base_name, category, source_path, raw_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    import_id,
                    item["name"],
                    item["baseName"],
                    item["category"],
                    item["sourcePath"],
                    item["rawText"],
                )
                for item in document["uniques"]
            ),
        )
        self.conn.executemany(
            """
            INSERT INTO item_mods (import_id, mod_id, source_path, mod_text, record_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                (
                    import_id,
                    mod["modId"],
                    mod["sourcePath"],
                    "\n".join(mod["lines"]),
                    json.dumps(mod, ensure_ascii=False),
                )
                for mod in document["mods"]
            ),
        )
        self.conn.executemany(
            """
            INSERT INTO gems (import_id, gem_id, name, granted_effect_id, source_path, record_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    import_id,
                    gem["id"],
                    gem["name"],
                    gem["grantedEffectId"],
                    gem["sourcePath"],
                    json.dumps(gem, ensure_ascii=False),
                )
                for gem in document["gems"]
            ),
        )
        self.conn.executemany(
            """
            INSERT INTO passive_nodes (
                import_id, node_id, name, node_type, ascendancy_name,
                class_start_index, source_path, record_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                (
                    import_id,
                    node["id"],
                    node["name"],
                    node["nodeType"],
                    node.get("ascendancyName"),
                    node.get("classStartIndex"),
                    node["sourcePath"],
                    json.dumps(node, ensure_ascii=False),
                )
                for node in document["nodes"]
            ),
        )
        self.conn.executemany(
            """
            INSERT INTO passive_edges (import_id, from_id, to_id) VALUES (?, ?, ?)
            """,
            ((import_id, edge[0], edge[1]) for edge in document["edges"]),
        )
        self._index_search(import_id, document)
        self.conn.commit()
        return self.provenance()

    def provenance(self) -> dict:
        row = self._import_row()
        return {
            "source": row["source"],
            "sourceUrl": row["source_url"],
            "sourceCommit": row["source_commit"],
            "gameVersion": row["game_version"],
            "treeVersion": row["tree_version"],
            "manifestVersion": row["manifest_version"],
            "retrievalDate": row["retrieval_date"],
            "retrievedAt": row["retrieved_at"],
            "counts": {
                "itemBases": row["item_base_count"],
                "uniques": row["unique_count"],
                "gems": row["gem_count"],
                "mods": row["mod_count"],
                "nodes": row["node_count"],
                "edges": row["edge_count"],
            },
        }

    def item_base(self, name: str) -> dict:
        row = self.conn.execute(
            "SELECT record_json, source_path FROM item_bases WHERE import_id = ? AND name = ?",
            (self._import_id(), name),
        ).fetchone()
        if row is None:
            raise KeyError(name)
        return self._public_record(json.loads(row["record_json"]))

    def unique_items(self, name: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT name, base_name, category, source_path, raw_text
            FROM unique_items WHERE import_id = ? AND name = ?
            ORDER BY category, id
            """,
            (self._import_id(), name),
        ).fetchall()
        return [self._public_unique(row) for row in rows]

    def gem(self, name: str) -> dict:
        rows = self.conn.execute(
            "SELECT record_json FROM gems WHERE import_id = ? AND name = ? ORDER BY gem_id",
            (self._import_id(), name),
        ).fetchall()
        if not rows:
            raise KeyError(name)
        if len(rows) > 1:
            raise KnowledgeError(f"More than one gem is named {name}.")
        return self._public_record(json.loads(rows[0]["record_json"]))

    def node(self, node_id: int) -> dict:
        row = self.conn.execute(
            "SELECT record_json FROM passive_nodes WHERE import_id = ? AND node_id = ?",
            (self._import_id(), node_id),
        ).fetchone()
        if row is None:
            raise KeyError(node_id)
        return self._public_record(json.loads(row["record_json"]))

    def mods_with_text(self, text: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT record_json FROM item_mods
            WHERE import_id = ? AND instr(mod_text, ?) > 0
            ORDER BY source_path, mod_id
            """,
            (self._import_id(), text),
        ).fetchall()
        return [self._public_record(json.loads(row["record_json"])) for row in rows]

    def search(self, query: str, limit: int = 20) -> list[dict]:
        phrase = '"' + query.replace('"', " ") + '"'
        rows = self.conn.execute(
            """
            SELECT kind, name, ref FROM knowledge_search
            WHERE import_id = ? AND knowledge_search MATCH ?
            LIMIT ?
            """,
            (self._import_id(), phrase, limit),
        ).fetchall()
        provenance = self._provenance_fields()
        return [
            {"kind": row["kind"], "name": row["name"], "ref": row["ref"], **provenance}
            for row in rows
        ]

    def graph(self) -> PassiveGraph:
        import_id = self._import_id()
        row = self._import_row()
        nodes: dict[int, PassiveNode] = {}
        for item in self.conn.execute(
            "SELECT record_json FROM passive_nodes WHERE import_id = ?",
            (import_id,),
        ):
            record = json.loads(item["record_json"])
            nodes[record["id"]] = PassiveNode(
                node_id=record["id"],
                name=record["name"],
                node_type=record["nodeType"],
                stats=tuple(record["stats"]),
                ascendancy_name=record.get("ascendancyName"),
                class_start_index=record.get("classStartIndex"),
                granted_passive_points=record.get("grantedPassivePoints") or 0,
                multiple_choice_option=bool(record.get("multipleChoiceOption")),
                source_path=record["sourcePath"],
            )
        adjacency: dict[int, set[int]] = {node_id: set() for node_id in nodes}
        for edge in self.conn.execute(
            "SELECT from_id, to_id FROM passive_edges WHERE import_id = ?",
            (import_id,),
        ):
            left, right = edge["from_id"], edge["to_id"]
            if left in adjacency and right in adjacency:
                adjacency[left].add(right)
                adjacency[right].add(left)
        classes = {
            item["name"]: _character_class(item, nodes)
            for item in json.loads(row["classes_json"])
        }
        alternates: dict[str, AscendancyInfo] = {}
        alternate_aliases: dict[str, str] = {}
        for item in json.loads(row["alternates_json"]):
            info = _ascendancy(item, alternate=True)
            alternates[info.ascendancy_id] = info
            alternate_aliases[info.ascendancy_id] = info.ascendancy_id
            alternate_aliases[info.name] = info.ascendancy_id
        points = json.loads(row["points_json"])
        return PassiveGraph(
            nodes=nodes,
            adjacency=adjacency,
            classes=classes,
            alternates=alternates,
            alternate_aliases=alternate_aliases,
            regular_budget=points["total"],
            ascendancy_budget=points["ascendancy"],
            provenance=self._provenance_fields(),
        )

    def _public_record(self, record: dict) -> dict:
        record = dict(record)
        record.update(self._provenance_fields())
        return record

    def _public_unique(self, row: sqlite3.Row) -> dict:
        return self._public_record(
            {
                "name": row["name"],
                "baseName": row["base_name"],
                "category": row["category"],
                "sourcePath": row["source_path"],
                "rawText": row["raw_text"],
            }
        )

    def _provenance_fields(self) -> dict:
        current = self.provenance()
        current.pop("counts", None)
        return current

    def _import_row(self) -> sqlite3.Row:
        row = self.conn.execute("SELECT * FROM imports").fetchone()
        if row is None:
            raise KnowledgeError("No game data has been imported.")
        return row

    def _import_id(self) -> str:
        return self._import_row()["id"]

    def _replace(self) -> None:
        for table in (
            "knowledge_search",
            "passive_edges",
            "passive_nodes",
            "gems",
            "item_mods",
            "unique_items",
            "item_bases",
            "imports",
        ):
            self.conn.execute(f"DELETE FROM {table}")

    def _index_search(self, import_id: str, document: dict) -> None:
        rows: list[tuple] = []
        for base in document["bases"]:
            rows.append(("item-base", base["name"], base.get("itemType") or "", base["name"], import_id))
        for item in document["uniques"]:
            rows.append(("unique", item["name"], item["baseName"], item["name"], import_id))
        for gem in document["gems"]:
            rows.append(("gem", gem["name"], gem.get("tagString") or "", gem["id"], import_id))
        for node in document["nodes"]:
            rows.append(
                (
                    "passive-node",
                    node["name"],
                    "\n".join(node["stats"]),
                    str(node["id"]),
                    import_id,
                )
            )
        for mod in document["mods"]:
            label = mod.get("affix") or mod["modId"]
            rows.append(("mod", label, "\n".join(mod["lines"]), mod["modId"], import_id))
        self.conn.executemany(
            "INSERT INTO knowledge_search (kind, name, body, ref, import_id) VALUES (?, ?, ?, ?, ?)",
            rows,
        )


def _ascendancy(item: dict, *, alternate: bool) -> AscendancyInfo:
    if "startNodeId" not in item:
        raise KnowledgeError(f"Ascendancy {item.get('id')} has no start node in the tree.")
    return AscendancyInfo(
        ascendancy_id=item["id"],
        name=item["name"],
        start_node_id=item["startNodeId"],
        alternate=alternate,
    )


def _character_class(item: dict, nodes: dict[int, PassiveNode]) -> CharacterClass:
    starts = [
        node.node_id
        for node in nodes.values()
        if node.node_type == "ClassStart" and node.class_start_index == item["index"]
    ]
    if len(starts) != 1:
        raise KnowledgeError(f"Class {item['name']} has {len(starts)} start nodes.")
    start = starts[0]
    ascendancies: dict[str, AscendancyInfo] = {}
    aliases: dict[str, str] = {}
    for ascendancy in item["ascendancies"]:
        info = _ascendancy(ascendancy, alternate=False)
        ascendancies[info.ascendancy_id] = info
        aliases[info.ascendancy_id] = info.ascendancy_id
        aliases[info.name] = info.ascendancy_id
    return CharacterClass(
        index=item["index"],
        name=item["name"],
        start_node_id=start,
        ascendancies=ascendancies,
        aliases=aliases,
    )
