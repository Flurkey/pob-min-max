"""Typed tools. Character numbers come from the engine. Catalogue rows come from the import."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from pob_agent.errors import AgentError, ToolArgumentError
from pob_engine.errors import EngineError
from pob_engine.service import EngineService
from pob_knowledge.errors import KnowledgeError
from pob_knowledge.store import KnowledgeStore


class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ImportBuild(_Args):
    name: str = Field(min_length=1, max_length=200)
    xml: str = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("name is empty")
        return text


class RevisionOnly(_Args):
    revision_id: str = Field(min_length=1)


class CompareBuilds(_Args):
    left_revision_id: str = Field(min_length=1)
    right_revision_id: str = Field(min_length=1)


class SearchQuery(_Args):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=25)

    @field_validator("query")
    @classmethod
    def not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("query is empty")
        return text


class FindPassivePath(_Args):
    class_name: str = Field(min_length=1)
    node_id: int

    @field_validator("class_name")
    @classmethod
    def class_not_blank(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("class_name is empty")
        return text


class AllocatePassives(_Args):
    revision_id: str = Field(min_length=1)
    node_id: int | None = None
    node_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def has_target(self) -> AllocatePassives:
        if self.node_id is None and not self.node_ids:
            raise ValueError("node_id or node_ids is required")
        return self


class EquipItem(_Args):
    revision_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    slot: str | None = None

    @field_validator("slot")
    @classmethod
    def slot_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            raise ValueError("slot is empty")
        return text


@dataclass(frozen=True)
class _Tool:
    name: str
    description: str
    model: type[BaseModel]
    handler: Callable[[Any], dict]


class Toolset:
    """The tools a model is allowed to call.

    equip_item and allocate_passives copy the given revision and edit the copy.
    The caller's revision row is not updated.
    """

    def __init__(self, engine: EngineService, knowledge: KnowledgeStore):
        self.engine = engine
        self.knowledge = knowledge
        self._graph_cache = None
        self._tools = {tool.name: tool for tool in self._define()}

    def schemas(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.model.model_json_schema(),
            }
            for tool in self._tools.values()
        ]

    def invoke(self, name: str, arguments: dict) -> dict:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolArgumentError(f"Unknown tool {name}.")
        if not isinstance(arguments, dict):
            raise ToolArgumentError("Tool arguments must be an object.")
        try:
            parsed = tool.model.model_validate(arguments)
        except ValidationError as exc:
            message = exc.errors()[0]["msg"] if exc.errors() else str(exc)
            raise ToolArgumentError(message) from exc
        try:
            return tool.handler(parsed)
        except KeyError as exc:
            missing = exc.args[0] if exc.args else "record"
            raise AgentError(f"Unknown revision {missing}.") from exc

    def _define(self) -> list[_Tool]:
        return [
            _Tool(
                "import_build",
                "Import Path of Building XML into the library. The calculation is a fresh "
                "engine result. Stored PlayerStat values are not used.",
                ImportBuild,
                self.import_build,
            ),
            _Tool(
                "get_build_state",
                "Return a fresh engine calculation and the equipment summary for one revision. "
                "Does not modify the build and does not return the XML cache.",
                RevisionOnly,
                self.get_build_state,
            ),
            _Tool(
                "calculate_build",
                "Recalculate one stored revision with the Path of Building engine.",
                RevisionOnly,
                self.calculate_build,
            ),
            _Tool(
                "compare_builds",
                "Recalculate two revisions and return the engine's deltas.",
                CompareBuilds,
                self.compare_builds,
            ),
            _Tool(
                "search_unique_items",
                "Search unique item text imported from the pinned Path of Building data. "
                "Each hit includes its source commit and raw text.",
                SearchQuery,
                self.search_unique_items,
            ),
            _Tool(
                "search_skill_gems",
                "Search skill gems imported from the pinned Path of Building data.",
                SearchQuery,
                self.search_skill_gems,
            ),
            _Tool(
                "search_passive_nodes",
                "Search passive nodes imported from the pinned tree. A numeric query is a node id.",
                SearchQuery,
                self.search_passive_nodes,
            ),
            _Tool(
                "find_passive_path",
                "Shortest main-tree path from the class start to a node, using the imported graph. "
                "Does not allocate the path.",
                FindPassivePath,
                self.find_passive_path,
            ),
            _Tool(
                "allocate_passives",
                "Allocate passives on a new working copy of the revision. The revision you pass "
                "is not modified. node_id allocates that node and the engine's path from the class "
                "start. node_ids is an exact set: it is rejected when it does not connect to the "
                "class start or when it spends more points than the tree file allows.",
                AllocatePassives,
                self.allocate_passives,
            ),
            _Tool(
                "equip_item",
                "Equip item text on a new working copy of the revision. The revision you pass "
                "is not modified. The calculation is a fresh engine result.",
                EquipItem,
                self.equip_item,
            ),
            _Tool(
                "export_build",
                "Export Path of Building XML from the engine. PlayerStat tags in that file are a "
                "save cache. A later import still has to be calculated.",
                RevisionOnly,
                self.export_build,
            ),
        ]

    def import_build(self, args: ImportBuild) -> dict:
        result = self.engine.import_xml(args.xml, args.name)
        result["source"] = "pob-engine"
        return result

    def get_build_state(self, args: RevisionOnly) -> dict:
        result = self.engine.inspect(args.revision_id)
        result["source"] = "pob-engine"
        return result

    def calculate_build(self, args: RevisionOnly) -> dict:
        calculation = self.engine.calculate(args.revision_id)
        return {"source": "pob-engine", "revisionId": args.revision_id, "calculation": calculation}

    def compare_builds(self, args: CompareBuilds) -> dict:
        return self.engine.compare(args.left_revision_id, args.right_revision_id)

    def search_unique_items(self, args: SearchQuery) -> dict:
        names = _unique_names(self._hits("unique", args.query, args.limit))
        if not names:
            names = [args.query]
        items: list[dict] = []
        for name in names:
            for record in self.knowledge.unique_items(name):
                items.append(record)
                if len(items) >= args.limit:
                    break
            if len(items) >= args.limit:
                break
        return {"source": "pob-knowledge", "query": args.query, "items": items}

    def search_skill_gems(self, args: SearchQuery) -> dict:
        names = _unique_names(self._hits("gem", args.query, args.limit))
        gems: list[dict] = []
        try:
            gems.append(self.knowledge.gem(args.query))
        except KeyError:
            pass
        except KnowledgeError:
            pass
        for name in names:
            if any(gem["name"] == name for gem in gems):
                continue
            try:
                gems.append(self.knowledge.gem(name))
            except KeyError:
                continue
            except KnowledgeError:
                continue
            if len(gems) >= args.limit:
                break
        return {"source": "pob-knowledge", "query": args.query, "gems": gems[: args.limit]}

    def search_passive_nodes(self, args: SearchQuery) -> dict:
        if args.query.isdigit():
            try:
                nodes = [self.knowledge.node(int(args.query))]
            except KeyError:
                nodes = []
            return {"source": "pob-knowledge", "query": args.query, "nodes": nodes}
        nodes = []
        for hit in self._hits("passive-node", args.query, args.limit):
            nodes.append(self.knowledge.node(int(hit["ref"])))
        return {"source": "pob-knowledge", "query": args.query, "nodes": nodes}

    def find_passive_path(self, args: FindPassivePath) -> dict:
        graph = self._graph()
        path = graph.shortest_path(args.class_name, args.node_id)
        nodes = []
        for node_id in path:
            node = graph.node(node_id)
            nodes.append(
                {
                    "id": node.node_id,
                    "name": node.name,
                    "nodeType": node.node_type,
                    "stats": list(node.stats),
                }
            )
        return {
            **graph.provenance,
            "source": "pob-knowledge",
            "className": args.class_name,
            "nodeIds": path,
            "nodes": nodes,
        }

    def allocate_passives(self, args: AllocatePassives) -> dict:
        summary = self._summary(args.revision_id)
        targets = self._allocation_targets(summary["className"], args)

        def apply(copy_id: str) -> dict:
            current = copy_id
            result = None
            for node_id in targets:
                result = self.engine.allocate(current, node_id)
                current = result["revision"]["id"]
            if result is None:
                raise AgentError("Nothing was allocated.")
            return result

        return self._mutate(args.revision_id, apply)

    def equip_item(self, args: EquipItem) -> dict:
        return self._mutate(
            args.revision_id,
            lambda copy_id: self.engine.equip(copy_id, args.text, args.slot),
        )

    def export_build(self, args: RevisionOnly) -> dict:
        xml = self.engine.export_xml(args.revision_id)
        return {"source": "pob-engine", "revisionId": args.revision_id, "xml": xml}

    def _summary(self, revision_id: str) -> dict:
        self._revision(revision_id)
        inspected = self.engine.inspect(revision_id)
        summary = inspected["summary"]
        class_name = summary.get("className")
        if not class_name:
            raise AgentError("The engine did not report a class.")
        expected = self.knowledge.provenance()["treeVersion"]
        actual = summary.get("treeVersion")
        if actual != expected:
            raise AgentError(
                f"The build tree is {actual}, and the imported passive graph is {expected}."
            )
        return summary

    def _allocation_targets(self, class_name: str, args: AllocatePassives) -> list[int]:
        graph = self._graph()
        start = graph.class_start_id(class_name)
        if args.node_ids:
            requested = [node_id for node_id in args.node_ids if node_id != start]
            if args.node_id is not None and args.node_id not in args.node_ids and args.node_id != start:
                raise ToolArgumentError("node_id is not in node_ids.")
            if not requested:
                raise ToolArgumentError("The class start is already allocated.")
            graph.validate(class_name, requested)
            return requested
        if args.node_id is None:
            raise ToolArgumentError("node_id or node_ids is required.")
        if isinstance(args.node_id, bool) or not isinstance(args.node_id, int):
            raise ToolArgumentError("node_id must be an integer.")
        if args.node_id == start:
            raise ToolArgumentError("The class start is already allocated.")
        path = graph.shortest_path(class_name, args.node_id)
        graph.validate(class_name, path[1:])
        return [args.node_id]

    def _mutate(self, revision_id: str, apply: Callable[[str], dict]) -> dict:
        # Copy first so the caller's row, including an original import, is never the edited parent.
        row = self._revision(revision_id)
        copied = self.engine.copy(row["build_id"], revision_id)
        copy_id = copied["revision"]["id"]
        try:
            result = apply(copy_id)
        except Exception:
            self._discard_unused_copy(copy_id)
            raise
        result = dict(result)
        result["copiedFromRevisionId"] = revision_id
        result["workingCopyRevisionId"] = copy_id
        return result

    def _discard_unused_copy(self, copy_id: str) -> None:
        try:
            self.engine.discard(copy_id)
        except EngineError as exc:
            if "later revisions" not in str(exc):
                raise

    def _revision(self, revision_id: str) -> dict:
        try:
            return self.engine.store.get(revision_id)
        except KeyError as exc:
            raise AgentError(f"Unknown revision {revision_id}.") from exc

    def _graph(self):
        if self._graph_cache is None:
            self._graph_cache = self.knowledge.graph()
        return self._graph_cache

    def _hits(self, kind: str, query: str, limit: int) -> list[dict]:
        try:
            return self.knowledge.search(query, limit=limit, kind=kind)
        except sqlite3.OperationalError as exc:
            raise ToolArgumentError(f"Search query was rejected: {exc}") from exc


def _unique_names(hits: list[dict]) -> list[str]:
    names: list[str] = []
    for hit in hits:
        if hit["name"] not in names:
            names.append(hit["name"])
    return names
