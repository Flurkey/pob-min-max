"""Stage copies of a library build, and crafting legality from imported modifiers.

Copies go through the engine library. Legality reads the knowledge import.
This package does not calculate character stats, call a model, or price a craft.
"""

__version__ = "0.1.0"

from pob_progression.crafting import (
    PREFIX_LIMIT,
    RARE_AFFIX_LIMIT,
    SUFFIX_LIMIT,
    CitedMod,
    CraftVerdict,
    ModRef,
    check_craft,
    crafting_cost,
    imported_weights,
)
from pob_progression.errors import CraftingError, ProgressionError
from pob_progression.stages import STAGES, progression_copies

__all__ = [
    "PREFIX_LIMIT",
    "RARE_AFFIX_LIMIT",
    "STAGES",
    "SUFFIX_LIMIT",
    "CitedMod",
    "CraftVerdict",
    "CraftingError",
    "ModRef",
    "ProgressionError",
    "check_craft",
    "crafting_cost",
    "imported_weights",
    "progression_copies",
]
