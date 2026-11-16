"""Chains and conflicts read from imported unique and modifier rows.

The search does not calculate character stats and it does not call a model.
Every step quotes a line or a group field stored by the knowledge import.
"""

__version__ = "0.1.0"

from pob_discovery.errors import DiscoveryError
from pob_discovery.search import (
    Chain,
    Citation,
    Conflict,
    Discovery,
    assert_known,
    clean_line,
    discover,
)

__all__ = [
    "Chain",
    "Citation",
    "Conflict",
    "Discovery",
    "DiscoveryError",
    "assert_known",
    "clean_line",
    "discover",
]
