from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from pob_knowledge.errors import DisconnectedAllocation, KnowledgeError, PointBudgetExceeded


@dataclass(frozen=True)
class PassiveNode:
    node_id: int
    name: str
    node_type: str
    stats: tuple[str, ...]
    ascendancy_name: str | None
    class_start_index: int | None
    granted_passive_points: int
    multiple_choice_option: bool
    source_path: str


@dataclass(frozen=True)
class AscendancyInfo:
    ascendancy_id: str
    name: str
    start_node_id: int
    alternate: bool


@dataclass
class CharacterClass:
    index: int
    name: str
    start_node_id: int
    ascendancies: dict[str, AscendancyInfo] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)


class PassiveGraph:
    """Passive tree connectivity from the imported tree file.

    An allocation is the set of node ids the caller asked for. The class start
    is always allocated. A selected ascendancy's start is allocated as well.
    Nodes that cannot reach the matching start through that set are rejected.
    Mastery nodes can be allocated beside a connected neighbour, and they do
    not connect other nodes to each other. The point cap is the tree file's
    own `points` table, plus passive points granted by allocated nodes.
    """

    def __init__(
        self,
        *,
        nodes: dict[int, PassiveNode],
        adjacency: dict[int, set[int]],
        classes: dict[str, CharacterClass],
        alternates: dict[str, AscendancyInfo],
        alternate_aliases: dict[str, str],
        regular_budget: int,
        ascendancy_budget: int,
        provenance: dict,
    ):
        self.nodes = nodes
        self._adj = adjacency
        self._classes = classes
        self._alternates = alternates
        self._alternate_aliases = alternate_aliases
        self.regular_budget = regular_budget
        self.ascendancy_budget = ascendancy_budget
        self.provenance = provenance

    def node(self, node_id: int) -> PassiveNode:
        try:
            return self.nodes[node_id]
        except KeyError as exc:
            raise KnowledgeError(f"Unknown passive node {node_id}.") from exc

    def neighbors(self, node_id: int) -> tuple[int, ...]:
        self.node(node_id)
        return tuple(sorted(self._adj.get(node_id, ())))

    def class_start_id(self, class_name: str) -> int:
        return self._class(class_name).start_node_id

    def ascendancy_start_id(self, class_name: str, ascendancy: str) -> int:
        return self._resolve_ascendancy(self._class(class_name), ascendancy).start_node_id

    def allocation_kind(self, node_id: int) -> str:
        node = self.node(node_id)
        if node.node_type in {"ClassStart", "AscendClassStart"}:
            return "free"
        if node.ascendancy_name:
            if node.multiple_choice_option:
                return "free"
            return "ascendancy"
        return "regular"

    def shortest_path(self, class_name: str, node_id: int) -> list[int]:
        """Shortest main-tree path from the class start to a non-ascendancy node.

        Mastery nodes are not used as bridges. The path includes the class start.
        """
        start = self.class_start_id(class_name)
        target = self.node(node_id)
        if target.ascendancy_name:
            raise KnowledgeError(f"Node {node_id} is on the {target.ascendancy_name} ascendancy.")
        if node_id == start:
            return [start]
        previous: dict[int, int | None] = {start: None}
        queue: deque[int] = deque([start])
        while queue:
            current = queue.popleft()
            if self.nodes[current].node_type == "Mastery":
                continue
            for neighbor in self._adj.get(current, ()):
                if neighbor in previous:
                    continue
                other = self.nodes.get(neighbor)
                if other is None or other.ascendancy_name:
                    continue
                if other.node_type == "ClassStart":
                    continue
                previous[neighbor] = current
                if neighbor == node_id:
                    path = [node_id]
                    cursor: int | None = current
                    while cursor is not None:
                        path.append(cursor)
                        cursor = previous[cursor]
                    path.reverse()
                    return path
                queue.append(neighbor)
        raise KnowledgeError(f"Node {node_id} ({target.name}) has no path from the {class_name} start.")

    def validate(
        self,
        class_name: str,
        node_ids: list[int],
        *,
        ascendancy: str | None = None,
    ) -> dict:
        character = self._class(class_name)
        selected = self._resolve_ascendancy(character, ascendancy) if ascendancy else None
        allocated = {character.start_node_id}
        if selected is not None:
            allocated.add(selected.start_node_id)
        requested: list[int] = []
        for raw in node_ids:
            node_id = _require_node_id(raw)
            node = self.node(node_id)
            if node.node_type == "ClassStart" and node_id != character.start_node_id:
                raise DisconnectedAllocation([node_id])
            if node.ascendancy_name:
                if selected is None or node.ascendancy_name != selected.ascendancy_id:
                    label = selected.ascendancy_id if selected else "no ascendancy"
                    raise KnowledgeError(
                        f"Node {node_id} ({node.name}) belongs to {node.ascendancy_name}, "
                        f"which is not the selected ascendancy ({label})."
                    )
            requested.append(node_id)
            allocated.add(node_id)

        main = self._component(
            [character.start_node_id],
            allocated,
            lambda node_id: (
                self.nodes[node_id].ascendancy_name is None
                and (
                    self.nodes[node_id].node_type != "ClassStart"
                    or node_id == character.start_node_id
                )
            ),
        )
        reachable = set(main)
        if selected is not None:
            reachable.update(
                self._component(
                    [selected.start_node_id],
                    allocated,
                    lambda node_id, asc=selected.ascendancy_id: self.nodes[node_id].ascendancy_name == asc,
                )
            )
        disconnected = sorted(allocated - reachable)
        if disconnected:
            raise DisconnectedAllocation(disconnected)

        regular = 0
        ascendancy_points = 0
        extra = 0
        for node_id in allocated:
            kind = self.allocation_kind(node_id)
            if kind == "regular":
                regular += 1
            elif kind == "ascendancy":
                ascendancy_points += 1
            extra += self.nodes[node_id].granted_passive_points
        regular_budget = self.regular_budget + extra
        if regular > regular_budget:
            raise PointBudgetExceeded(
                f"Allocation spends {regular} passive points; this tree allows {regular_budget}."
            )
        if ascendancy_points > self.ascendancy_budget:
            raise PointBudgetExceeded(
                f"Allocation spends {ascendancy_points} ascendancy points; "
                f"this tree allows {self.ascendancy_budget}."
            )
        return {
            "className": character.name,
            "ascendancy": selected.name if selected else None,
            "ascendancyId": selected.ascendancy_id if selected else None,
            "classStartId": character.start_node_id,
            "nodeIds": sorted(allocated),
            "regularPoints": regular,
            "regularBudget": regular_budget,
            "ascendancyPoints": ascendancy_points,
            "ascendancyBudget": self.ascendancy_budget,
            **self.provenance,
        }

    def _class(self, class_name: str) -> CharacterClass:
        try:
            return self._classes[class_name]
        except KeyError as exc:
            raise KnowledgeError(f"Unknown class {class_name}.") from exc

    def _resolve_ascendancy(self, character: CharacterClass, name: str) -> AscendancyInfo:
        canonical = character.aliases.get(name)
        if canonical:
            return character.ascendancies[canonical]
        alternate_id = self._alternate_aliases.get(name)
        if alternate_id:
            return self._alternates[alternate_id]
        raise KnowledgeError(f"{name} is not an ascendancy of {character.name}.")

    def _component(self, seeds: list[int], allocated: set[int], accept) -> set[int]:
        reachable: set[int] = set()
        queue: deque[int] = deque()
        for seed in seeds:
            if seed in allocated and seed not in reachable:
                reachable.add(seed)
                queue.append(seed)
        while queue:
            current = queue.popleft()
            # A mastery can sit on a connected node. It does not join two other nodes.
            if self.nodes[current].node_type == "Mastery":
                continue
            for neighbor in self._adj.get(current, ()):
                if neighbor in reachable or neighbor not in allocated or not accept(neighbor):
                    continue
                reachable.add(neighbor)
                queue.append(neighbor)
        return reachable


def _require_node_id(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise KnowledgeError(f"Passive node id must be an integer, got {value!r}.")
    return value
