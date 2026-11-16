from __future__ import annotations

import tempfile
import threading
import xml.etree.ElementTree as ET
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
            store_path = Path(tempfile.mkdtemp(prefix="pob-store-")) / "builds.sqlite"
        try:
            _reject_pob_save_location(store_path, paths.src, process.user_dir)
        except EngineError:
            process.close()
            raise
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
                status="saved",
            )
            self.store.record_calculation(revision["id"], calc)
            self._loaded = revision["id"]
            return {
                "revision": _public_revision(revision),
                "build": _public_build(self.store.get_build(revision["build_id"])),
                "info": info,
                "calculation": public_calculation(calc),
                "summary": _public_summary(self.process.request("summary")),
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
                child = self._store_draft(
                    parent,
                    xml=exported["xml"],
                    label="equipment",
                    tree_version=parent.get("tree_version"),
                )
            except EngineError:
                self._restore(parent)
                raise
            self._loaded = child["id"]
            calc = self._fresh()
            child = self.store.get(child["id"])
            self.store.record_calculation(child["id"], calc)
            comparison = self.compare(parent["id"], child["id"])
            return {
                "revision": _public_revision(child),
                "build": _public_build(self.store.get_build(parent["build_id"])),
                "parentId": parent["id"],
                "equipment": equipped,
                "calculation": public_calculation(calc),
                "comparison": comparison,
                "summary": _public_summary(self.process.request("summary")),
            }

    def allocate(self, revision_id: str, node_id: int | None = None) -> dict:
        with self._lock:
            parent = self._load(revision_id)
            try:
                params = {} if node_id is None else {"nodeId": node_id}
                allocated = self.process.request("allocate_node", **params)
                exported = self.process.request("export_xml")
                child = self._store_draft(
                    parent,
                    xml=exported["xml"],
                    label="passive",
                    tree_version=parent.get("tree_version"),
                )
            except EngineError:
                self._restore(parent)
                raise
            self._loaded = child["id"]
            calc = self._fresh()
            self.store.record_calculation(child["id"], calc)
            comparison = self.compare(parent["id"], child["id"])
            return {
                "revision": _public_revision(child),
                "build": _public_build(self.store.get_build(parent["build_id"])),
                "parentId": parent["id"],
                "passive": allocated,
                "calculation": public_calculation(calc),
                "comparison": comparison,
                "summary": _public_summary(self.process.request("summary")),
            }

    def copy(self, build_id: str, revision_id: str | None = None) -> dict:
        """Working copy of a stored revision. The saved head does not move."""
        with self._lock:
            build = self.store.get_build(build_id)
            source_id = revision_id or build.get("saved_revision_id")
            if not source_id:
                raise EngineError("This build has no stored revision to copy.")
            source = self.store.get(source_id)
            if source["build_id"] != build_id:
                raise EngineError("That revision belongs to a different build.")
            child = self.store.create(
                name=source["name"],
                xml=source["xml"],
                label="copy",
                parent_id=source["id"],
                build_id=source["build_id"],
                engine_revision=source.get("engine_revision") or self.process.revision,
                tree_version=source.get("tree_version"),
                status="draft",
            )
            return {
                "revision": _public_revision(child),
                "parentId": source["id"],
                "build": _public_build(self.store.get_build(build_id)),
            }

    def library_copy(
        self,
        build_id: str,
        revision_id: str | None = None,
        *,
        name: str,
        label: str,
    ) -> dict:
        """A new library build whose saved revision is a copy of this one.

        The source build's saved revision id and XML are not updated.
        """
        cleaned_name = name.strip()
        cleaned_label = label.strip()
        if not cleaned_name or len(cleaned_name) > 200:
            raise EngineError("A library copy needs a name.")
        if not cleaned_label or len(cleaned_label) > 80:
            raise EngineError("A library copy needs a label.")
        with self._lock:
            source_build = self.store.get_build(build_id)
            source_id = revision_id or source_build.get("saved_revision_id")
            if not source_id:
                raise EngineError("This build has no stored revision to copy.")
            source = self.store.get(source_id)
            if source["build_id"] != build_id:
                raise EngineError("That revision belongs to a different build.")
            saved_before = source_build.get("saved_revision_id")
            xml_before = source["xml"]
            # Omit build_id so the store inserts a new build. Passing the source
            # id would move that build's saved revision.
            child = self.store.create(
                name=cleaned_name,
                xml=xml_before,
                label=cleaned_label,
                parent_id=source["id"],
                engine_revision=source.get("engine_revision") or self.process.revision,
                tree_version=source.get("tree_version"),
                status="saved",
            )
            if child["build_id"] == build_id:
                raise EngineError("A library copy must be its own build.")
            if self.store.get(source_id)["xml"] != xml_before:
                raise EngineError("A library copy changed the source XML.")
            if self.store.get_build(build_id)["saved_revision_id"] != saved_before:
                raise EngineError("A library copy moved the stored revision.")
            return {
                "revision": _public_revision(self.store.get(child["id"])),
                "parentId": source["id"],
                "build": _public_build(self.store.get_build(child["build_id"])),
                "sourceBuild": _public_build(self.store.get_build(build_id)),
            }

    def save(self, revision_id: str) -> dict:
        """Store a new saved revision. Earlier revision rows are left as they were."""
        with self._lock:
            source = self._load(revision_id)
            build = self.store.get_build(source["build_id"])
            if build.get("saved_revision_id") == source["id"]:
                raise EngineError("This revision is already the stored build.")
            exported = self.process.request("export_xml")
            xml = exported["xml"]
            require_pob_xml(xml)
            saved = self.store.create(
                name=source["name"],
                xml=xml,
                label="save",
                parent_id=source["id"],
                build_id=source["build_id"],
                engine_revision=self.process.revision,
                tree_version=source.get("tree_version"),
                status="saved",
            )
            self._loaded = None
            stored = self.store.get(saved["id"])
            self._restore(stored)
            calc = self._fresh()
            self.store.record_calculation(stored["id"], calc)
            return {
                "revision": _public_revision(self.store.get(stored["id"])),
                "build": _public_build(self.store.get_build(source["build_id"])),
                "savedFromId": source["id"],
                "calculation": public_calculation(calc),
                "summary": _public_summary(self.process.request("summary")),
            }

    def discard(self, revision_id: str) -> dict:
        """Delete one leaf working copy. Saved revisions stay."""
        with self._lock:
            try:
                row = self.store.delete_draft(revision_id)
            except ValueError as exc:
                raise EngineError(str(exc)) from exc
            if self._loaded == revision_id:
                self._loaded = None
            return {
                "discardedId": revision_id,
                "build": _public_build(self.store.get_build(row["build_id"])),
            }

    def inspect(self, revision_id: str) -> dict:
        with self._lock:
            row = self._load(revision_id)
            calc = self._fresh()
            self.store.record_calculation(revision_id, calc)
            summary = self.process.request("summary")
            build = self.store.get_build(row["build_id"])
            return {
                "revision": _public_revision(row),
                "build": _public_build(build),
                "saved": row["id"] == build.get("saved_revision_id"),
                "calculation": public_calculation(calc),
                "summary": _public_summary(summary),
            }

    def library(self, query: str = "") -> list[dict]:
        return [_public_build(row) for row in self.store.list_builds(query)]

    def history(self, build_id: str) -> dict:
        build = self.store.get_build(build_id)
        revisions = [_public_revision(row) for row in self.store.list_revisions(build_id)]
        return {"build": _public_build(build), "revisions": revisions}

    def _store_draft(self, parent: dict, *, xml: str, label: str, tree_version: str | None) -> dict:
        require_pob_xml(xml)
        return self.store.create(
            name=parent["name"],
            xml=xml,
            label=label,
            parent_id=parent["id"],
            build_id=parent["build_id"],
            engine_revision=self.process.revision,
            tree_version=tree_version,
            status="draft",
        )

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
        "status": row.get("status") or "saved",
        "createdAt": row["created_at"],
        "engineRevision": row["engine_revision"],
        "treeVersion": row["tree_version"],
    }


def _public_build(row: dict) -> dict:
    return {
        "id": row["id"],
        "name": row["name"],
        "savedRevisionId": row.get("saved_revision_id"),
        "createdAt": row["created_at"],
        "updatedAt": row["updated_at"],
        "savedLabel": row.get("saved_label"),
        "treeVersion": row.get("tree_version"),
        "engineRevision": row.get("engine_revision"),
    }


def _public_summary(summary: dict) -> dict:
    equipped = summary.get("equipped") or []
    items = []
    for item in equipped:
        if not isinstance(item, dict):
            continue
        items.append(
            {
                "slot": item.get("slot"),
                "name": item.get("name"),
                "baseName": item.get("baseName"),
            }
        )
    return {
        "source": "pob-engine",
        "className": summary.get("className"),
        "ascendClassName": summary.get("ascendClassName"),
        "level": summary.get("level"),
        "treeVersion": summary.get("buildTreeVersion"),
        "treeDisplay": summary.get("buildTreeDisplay"),
        "allocatedPoints": summary.get("allocatedPoints"),
        "equipped": items,
    }


def require_pob_xml(xml: str) -> None:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise EngineError(f"Export is not valid XML: {exc}") from exc
    if root.tag != "PathOfBuilding":
        raise EngineError("Export root is not PathOfBuilding.")


def _reject_pob_save_location(store_path: Path, pob_src: Path, user_dir: Path) -> None:
    resolved = store_path.resolve()
    forbidden = [pob_src.resolve(), user_dir.resolve()]
    for root in forbidden:
        if resolved == root or root in resolved.parents:
            raise EngineError(
                "The build library must be a local SQLite file, not a Path of Building save directory."
            )

