"""Score an engine calculation. Missing stats are not treated as zero."""

from __future__ import annotations

from dataclasses import dataclass

from pob_optimisation.errors import OptimisationError


@dataclass(frozen=True)
class StatGoal:
    stat: str
    weight: float = 1.0
    direction: str = "max"

    def __post_init__(self) -> None:
        if not self.stat.strip():
            raise OptimisationError("An objective stat name is empty.")
        if self.direction not in {"max", "min"}:
            raise OptimisationError("An objective direction must be max or min.")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)) or self.weight <= 0:
            raise OptimisationError("An objective weight must be a positive number.")


@dataclass(frozen=True)
class Objective:
    """Weighted sum of engine stats, plus optional hard bounds.

    Weights are positive. Use direction ``min`` when a smaller number is better.
    A build that misses a bound is not adopted. If every evaluated build misses
    a bound, the search says the objective is impossible.
    """

    name: str
    goals: tuple[StatGoal, ...]
    minimums: tuple[tuple[str, float], ...] = ()
    maximums: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise OptimisationError("An objective name is empty.")
        if not self.goals:
            raise OptimisationError("An objective needs at least one stat.")


def score_calculation(calculation: dict, objective: Objective) -> float:
    stats = _engine_stats(calculation)
    total = 0.0
    for goal in objective.goals:
        value = _numeric(stats, goal.stat)
        signed = value if goal.direction == "max" else -value
        total += float(goal.weight) * signed
    return total


def unmet_constraint(calculation: dict, objective: Objective) -> str | None:
    stats = _engine_stats(calculation)
    for stat, floor in objective.minimums:
        value = _numeric(stats, stat)
        if value < floor:
            return f"{stat} is {value}, below the minimum {floor}."
    for stat, cap in objective.maximums:
        value = _numeric(stats, stat)
        if value > cap:
            return f"{stat} is {value}, above the maximum {cap}."
    return None


def _engine_stats(calculation: dict) -> dict:
    if not isinstance(calculation, dict) or calculation.get("source") != "pob-engine":
        raise OptimisationError("Refusing to score a result that did not come from the engine.")
    stats = calculation.get("stats")
    if not isinstance(stats, dict):
        raise OptimisationError("The engine result has no stat table.")
    return stats


def _numeric(stats: dict, stat: str) -> float:
    if stat not in stats:
        raise OptimisationError(f"The engine result has no {stat} stat.")
    value = stats[stat]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OptimisationError(f"The engine {stat} stat is not a number.")
    return float(value)
