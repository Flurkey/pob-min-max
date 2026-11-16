"""Deterministic search over library copies.

The search does not calculate character stats. It copies a stored revision,
applies equipment and passive candidates through the agent tools, and ranks
the engine's calculations.
"""

__version__ = "0.1.0"

from pob_optimisation.cache import CalculationCache
from pob_optimisation.candidates import (
    EquipmentCandidate,
    PassiveCandidate,
    equipment_candidates_from_uniques,
    passive_candidates_for_text,
)
from pob_optimisation.errors import OptimisationError
from pob_optimisation.objective import Objective, StatGoal, score_calculation
from pob_optimisation.search import CancelToken, Optimiser, SearchRequest

__all__ = [
    "CalculationCache",
    "CancelToken",
    "EquipmentCandidate",
    "Objective",
    "OptimisationError",
    "Optimiser",
    "PassiveCandidate",
    "SearchRequest",
    "StatGoal",
    "equipment_candidates_from_uniques",
    "passive_candidates_for_text",
    "score_calculation",
]
