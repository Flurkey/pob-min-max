"""Attribute totals from the engine, and Valdo assumptions from user text.

Attribute numbers come from a library copy calculated by the engine.
Valdo text lists which defensive assumptions it puts aside. An unmapped
line stays uncertain. Neither path calls a model or adds a jewel.
"""

__version__ = "0.1.0"

from pob_endgame.attributes import ATTRIBUTE_STATS, attribute_stack
from pob_endgame.errors import EndgameError
from pob_endgame.valdo import ASSUMPTIONS, assert_no_safety_claim, check_valdo

__all__ = [
    "ASSUMPTIONS",
    "ATTRIBUTE_STATS",
    "EndgameError",
    "assert_no_safety_claim",
    "attribute_stack",
    "check_valdo",
]
