"""Equipment and passive candidates.

Passive candidates are ordered by the imported graph: shorter main-tree path
from the class start, then lower node id. Equipment text is the caller's item
text or unique text imported from the checkout. Nothing here is a stat.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pob_knowledge.errors import KnowledgeError
from pob_knowledge.graph import PassiveGraph

from pob_optimisation.errors import OptimisationError

_SKIPPED_NODE_TYPES = {"ClassStart", "AscendClassStart", "Mastery"}


@dataclass(frozen=True)
class EquipmentCandidate:
    candidate_id: str
    text: str
    slot: str | None = None
    label: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise OptimisationError("candidate_id is empty.")
        if not self.text.strip():
            raise OptimisationError("Item text is empty.")
        if self.slot is not None and not self.slot.strip():
            raise OptimisationError("Item slot is empty.")

    @property
    def kind(self) -> str:
        return "equipment"

    @property
    def key(self) -> str:
        return _key(
            {
                "kind": self.kind,
                "slot": None if self.slot is None else self.slot.strip(),
                "text": self.text.strip(),
            }
        )


@dataclass(frozen=True)
class PassiveCandidate:
    candidate_id: str
    node_id: int | None = None
    node_ids: tuple[int, ...] = ()
    label: str = ""

    def __post_init__(self) -> None:
        if not self.candidate_id.strip():
            raise OptimisationError("candidate_id is empty.")
        if self.node_id is None and not self.node_ids:
            raise OptimisationError("A passive candidate needs node_id or node_ids.")
        _require_node(self.node_id, "node_id")
        for node_id in self.node_ids:
            _require_node(node_id, "node_ids")

    @property
    def kind(self) -> str:
        return "passive"

    @property
    def key(self) -> str:
        return _key(
            {
                "kind": self.kind,
                "nodeId": self.node_id,
                "nodeIds": list(self.node_ids),
            }
        )


def passive_candidates_for_text(
    graph: PassiveGraph,
    class_name: str,
    text: str,
    *,
    limit: int,
) -> list[PassiveCandidate]:
    """Main-tree nodes whose stat text contains ``text``, nearest first."""
    needle = text.strip().casefold()
    if not needle:
        raise OptimisationError("Passive candidate text is empty.")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise OptimisationError("Passive candidate limit must be an integer of at least 1.")
    found: list[tuple[int, int, str]] = []
    for node in graph.nodes.values():
        if node.ascendancy_name or node.node_type in _SKIPPED_NODE_TYPES:
            continue
        blob = "\n".join(node.stats).casefold()
        if needle not in blob:
            continue
        try:
            path = graph.shortest_path(class_name, node.node_id)
        except KnowledgeError:
            continue
        found.append((len(path), node.node_id, node.name))
    found.sort()
    return [
        PassiveCandidate(candidate_id=f"passive-{node_id}", node_id=node_id, label=name)
        for _length, node_id, name in found[:limit]
    ]


def equipment_candidates_from_uniques(
    items: list[dict],
    *,
    limit: int,
    slot: str | None = None,
) -> list[EquipmentCandidate]:
    """One candidate per imported unique, in name order. The text is the import's raw text."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise OptimisationError("Unique candidate limit must be an integer of at least 1.")
    if slot is not None and not slot.strip():
        raise OptimisationError("Item slot is empty.")
    ordered = sorted(
        items,
        key=lambda item: (
            str(item.get("name") or ""),
            str(item.get("baseName") or ""),
            str(item.get("sourcePath") or ""),
        ),
    )
    candidates: list[EquipmentCandidate] = []
    for index, item in enumerate(ordered):
        raw = item.get("rawText")
        if not isinstance(raw, str) or not raw.strip():
            continue
        name = str(item.get("name") or "unique")
        candidates.append(
            EquipmentCandidate(
                candidate_id=f"unique-{index}-{name}",
                text=raw,
                slot=slot,
                label=name,
            )
        )
        if len(candidates) >= limit:
            break
    return candidates


def _key(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _require_node(node_id: int | None, label: str) -> None:
    if node_id is None:
        return
    if isinstance(node_id, bool) or not isinstance(node_id, int):
        raise OptimisationError(f"{label} must be an integer.")
