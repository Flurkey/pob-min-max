"""Cache of engine calculations.

A hit is an earlier result from this process. The key is the canonical build
hash, the PoB revision, and the configuration profile. The cache never stores
a table that did not come from the engine.
"""

from __future__ import annotations

from pob_optimisation.errors import OptimisationError

CacheKey = tuple[str, str, str]
TrialKey = tuple[str, str, str, str]


class CalculationCache:
    def __init__(self) -> None:
        self._builds: dict[CacheKey, dict] = {}
        self._trials: dict[TrialKey, dict] = {}
        self.hits = 0
        self.misses = 0

    def lookup_build(self, build_hash: str, engine_revision: str, profile: str) -> dict | None:
        found = self._builds.get((build_hash, engine_revision, profile))
        if found is None:
            return None
        self.hits += 1
        return _copy_calculation(found)

    def lookup_trial(
        self,
        parent_hash: str,
        candidate_key: str,
        engine_revision: str,
        profile: str,
    ) -> tuple[dict, str] | None:
        found = self._trials.get((parent_hash, candidate_key, engine_revision, profile))
        if found is None:
            return None
        self.hits += 1
        return _copy_calculation(found["calculation"]), found["revisionId"]

    def store(
        self,
        *,
        build_hash: str,
        engine_revision: str,
        profile: str,
        calculation: dict,
        revision_id: str,
        trial: TrialKey | None = None,
    ) -> None:
        if calculation.get("source") != "pob-engine" or "stats" not in calculation:
            raise OptimisationError("Refusing to cache a result that did not come from the engine.")
        if not engine_revision:
            raise OptimisationError("Refusing to cache a result with no PoB revision.")
        stored = {
            "calculation": _copy_calculation(calculation),
            "revisionId": revision_id,
        }
        self._builds[(build_hash, engine_revision, profile)] = stored["calculation"]
        if trial is not None:
            self._trials[trial] = stored
        self.misses += 1

    def snapshot(self) -> dict:
        return {"hits": self.hits, "misses": self.misses}


def _copy_calculation(calculation: dict) -> dict:
    stats = calculation.get("stats")
    copied = dict(calculation)
    if isinstance(stats, dict):
        copied["stats"] = dict(stats)
    return copied
