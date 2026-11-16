class KnowledgeError(RuntimeError):
    """The knowledge import or passive graph rejected a request."""


class DisconnectedAllocation(KnowledgeError):
    """The allocated nodes do not connect to the class start."""

    def __init__(self, node_ids: list[int]):
        self.node_ids = node_ids
        shown = ", ".join(str(node_id) for node_id in node_ids[:12])
        extra = "" if len(node_ids) <= 12 else f" (+{len(node_ids) - 12} more)"
        super().__init__(f"Allocation is disconnected from the class start: {shown}{extra}")


class PointBudgetExceeded(KnowledgeError):
    """The allocation spends more points than the tree data allows."""
