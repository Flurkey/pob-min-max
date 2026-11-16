from __future__ import annotations

import tempfile
import threading
from pathlib import Path

from pob_engine.compare import compare_calculations
from pob_engine.errors import EngineError
from pob_engine.paths import resolve_paths
from pob_engine.process import PobProcess
from pob_engine.store import BuildStore


def public_calculation(calc: dict) -> dict:
    if calc.get("source") != "pob-engine":
        raise EngineError("Refusing to publish a result that did not come from the engine.")
    return {
        "source": "pob-engine",
        "ignoredStoredPlayerStat": True,
        "engineRevision": calc.get("engineRevision"),
        "manifestVersion": calc.get("manifestVersion"),
        "treeVersion": calc.get("treeVersion"),
        "level": calc.get("level"),
        "outputRevision": calc.get("outputRevision"),
        "stats": calc["stats"],
    }


class EngineService:
    def __init__(self, process: PobProcess, store: BuildStore):
        self.process = process
        self.store = store
        self._loaded: str | None = None
        self._lock = threading.RLock()

    @classmethod
    def start(cls, store_path: Path | None = None) -> EngineService:
        paths = resolve_paths()
        process = PobProcess.start(paths)
        if store_path is None:
            store_path = Path(tempfile.mkdtemp(prefix="pob-store-")) / "builds.db"
        return cls(process, BuildStore(store_path))

    def close(self) -> None:
        self.process.close()
        self.store.close()

    def engine_info(self) -> dict:
        info = dict(self.process.info)
        info["engineRevision"] = self.process.revision
        info["pinnedCommit"] = self.process.paths.pin["commit"]
        info["revisionMatchesPin"] = self.process.revision == self.process.paths.pin["commit"]
        return info

    def _fresh(self) -> dict:
        calc = self.process.request("calculate")
        calc["engineRevision"] = self.process.revision
        calc["manifestVersion"] = self.process.info.get("versionNumber")
        return calc

    def _load(self, revision_id: str) -> dict:
        row = self.store.get(revision_id)
        if self._loaded != revision_id:
            self.process.request("import_xml", xml=row["xml"], name=row["name"])
            self._loaded = revision_id
        return row

    def _restore(self, row: dict) -> None:
        self.process.request("import_xml", xml=row["xml"], name=row["name"])
        self._loaded = row["id"]

    def import_xml(self, xml: str, name: str) -> dict:
        with self._lock:
            info = self.process.request("import_xml", xml=xml, name=name)
            calc = self._fresh()
            revision = self.store.create(
                name=name,
                xml=xml,
                label="import",
                engine_revision=self.process.revision,
                tree_version=calc.get("treeVersion"),
            )
            self.store.record_calculation(revision["id"], calc)
            self._loaded = revision["id"]
            return {
                "revision": _public_revision(revision),
                "info": info,
                "calculation": public_calculation(calc),
            }

    def calculate(self, revision_id: str) -> dict:
        with self._lock:
            self._load(revision_id)
            calc = self._fresh()
            self.store.record_calculation(revision_id, calc)
            return public_calculation(calc)

    def equip(self, revision_id: str, text: str, slot: str | None) -> dict:
        with self._lock:
            parent = self._load(revision_id)
            try:
                equipped = self.process.request("equip_item", text=text, slot=slot)
                exported = self.process.request("export_xml")
            except EngineError:
                self._restore(parent)
                raise
            xml = exported["xml"]
            child = self.store.create(
                name=parent["name"],
                xml=xml,
                label="equipment",
                parent_id=parent["id"],
                build_id=parent["build_id"],
                engine_revision=self.process.revision,
                tree_version=parent.get("tree_version"),
            )
            self._loaded = child["id"]
            calc = self._fresh()
            child = self.store.get(child["id"])
            self.store.record_calculation(child["id"], calc)
            comparison = self.compare(parent["id"], child["id"])
            return {
                "revision": _public_revision(child),
                "parentId": parent["id"],
                "equipment": equipped,
                "calculation": public_calculation(calc),
                "comparison": comparison,
            }

    def allocate(self, revision_id: str, node_id: int | None = None) -> dict:
        with self._lock:
            parent = self._load(revision_id)
            try:
                params = {} if node_id is None else {"nodeId": node_id}
                allocated = self.process.request("allocate_node", **params)
                exported = self.process.request("export_xml")
            except EngineError:
                self._restore(parent)
                raise
            child = self.store.create(
                name=parent["name"],
                xml=exported["xml"],
                label="passive",
                parent_id=parent["id"],
                build_id=parent["build_id"],
                engine_revision=self.process.revision,
                tree_version=parent.get("tree_version"),
            )
            self._loaded = child["id"]
            calc = self._fresh()
            self.store.record_calculation(child["id"], calc)
            comparison = self.compare(parent["id"], child["id"])
            return {
                "revision": _public_revision(child),
                "parentId": parent["id"],
                "passive": allocated,
                "calculation": public_calculation(calc),
                "comparison": comparison,
            }

    def compare(self, left_id: str, right_id: str) -> dict:
        with self._lock:
            self._load(left_id)
            left = self._fresh()
            self._loaded = None
            self._load(right_id)
            right = self._fresh()
            return compare_calculations(left, right, left_id, right_id)

    def export_xml(self, revision_id: str) -> str:
        with self._lock:
            self._load(revision_id)
            return self.process.request("export_xml")["xml"]

    def search(self, query: str) -> list[dict]:
        return [_public_revision(row) for row in self.store.search(query)]


def _public_revision(row: dict) -> dict:
    return {
        "id": row["id"],
        "buildId": row["build_id"],
        "parentId": row["parent_id"],
        "name": row["name"],
        "label": row["label"],
        "createdAt": row["created_at"],
        "engineRevision": row["engine_revision"],
        "treeVersion": row["tree_version"],
    }
