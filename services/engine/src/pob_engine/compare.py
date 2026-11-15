from __future__ import annotations

ENGINE_SOURCE = "pob-engine"

FOCUS_STATS = (
    "Life",
    "LifeUnreserved",
    "EnergyShield",
    "Mana",
    "Str",
    "Dex",
    "Int",
    "Armour",
    "Evasion",
    "Ward",
    "TotalDPS",
    "FullDPS",
)


def _require_engine(calc: dict, side: str) -> dict[str, float]:
    if calc.get("source") != ENGINE_SOURCE:
        raise ValueError(f"{side} stats are not a fresh Path of Building calculation")
    stats = calc.get("stats")
    if not isinstance(stats, dict):
        raise ValueError(f"{side} calculation has no stat table")
    return stats


def compare_calculations(left: dict, right: dict, left_id: str, right_id: str) -> dict:
    left_stats = _require_engine(left, "left")
    right_stats = _require_engine(right, "right")
    changed = []
    for key in sorted(set(left_stats) | set(right_stats)):
        before = left_stats.get(key)
        after = right_stats.get(key)
        if before == after:
            continue
        delta = None
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = after - before
        changed.append({"stat": key, "left": before, "right": after, "delta": delta})

    focus = {}
    for key in FOCUS_STATS:
        if key not in left_stats and key not in right_stats:
            continue
        before = left_stats.get(key)
        after = right_stats.get(key)
        delta = None
        if isinstance(before, (int, float)) and isinstance(after, (int, float)):
            delta = after - before
        focus[key] = {"left": before, "right": after, "delta": delta}

    return {
        "source": ENGINE_SOURCE,
        "leftRevisionId": left_id,
        "rightRevisionId": right_id,
        "leftLevel": left.get("level"),
        "rightLevel": right.get("level"),
        "engineRevision": right.get("engineRevision"),
        "treeVersion": right.get("treeVersion"),
        "focus": focus,
        "changedCount": len(changed),
        "changed": changed,
    }
