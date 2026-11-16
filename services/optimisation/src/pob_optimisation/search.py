"""Hill-climb over equipment and passive candidates.

Each generation tries the remaining candidates on a copy of the current best.
The original library revision is copied once at the start and is never passed
to a mutating tool. Disconnected and over-budget passive sets are rejected by
the imported graph before a copy is kept. Identical trials reuse a cached
engine calculation.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass

from pob_agent.errors import AgentError
from pob_agent.tools import Toolset
from pob_engine.errors import EngineError
from pob_knowledge.errors import DisconnectedAllocation, KnowledgeError, PointBudgetExceeded

from pob_optimisation.cache import CalculationCache, TrialKey
from pob_optimisation.candidates import EquipmentCandidate, PassiveCandidate
from pob_optimisation.errors import OptimisationError
from pob_optimisation.identity import canonical_build
from pob_optimisation.objective import Objective, score_calculation, unmet_constraint

Candidate = EquipmentCandidate | PassiveCandidate
NO_ASCENDANCY = {"", "None", "nil"}


class CancelToken:
    """Set from any thread. The search checks it before each candidate."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()


@dataclass
class SearchRequest:
    revision_id: str
    candidates: tuple[Candidate, ...]
    objective: Objective
    max_iterations: int = 20
    cancel: CancelToken | None = None
    on_trial: Callable[[dict], None] | None = None
    max_passive_points: int | None = None


class Optimiser:
    def __init__(self, tools: Toolset):
        self.tools = tools
        self.cache = CalculationCache()
        self._graph = None

    def calculate(self, revision_id: str) -> dict:
        """Engine calculation for one revision, served from the cache when the build matches."""
        row = self._revision(revision_id)
        build_hash, profile = canonical_build(row["xml"])
        engine_revision = self.tools.engine.process.revision
        cached = self.cache.lookup_build(build_hash, engine_revision, profile)
        if cached is not None:
            return cached
        result = self.tools.invoke("calculate_build", {"revision_id": revision_id})
        calculation = _require_calculation(result.get("calculation"))
        _require_same_revision(calculation, engine_revision)
        child_hash, child_profile = canonical_build(self._revision(revision_id)["xml"])
        self.cache.store(
            build_hash=child_hash,
            engine_revision=calculation["engineRevision"],
            profile=child_profile,
            calculation=calculation,
            revision_id=revision_id,
        )
        return calculation

    def search(self, request: SearchRequest) -> dict:
        self._validate(request)
        original = self._revision(request.revision_id)
        original_xml = original["xml"]
        copied = self.tools.engine.copy(original["build_id"], request.revision_id)
        working_id = copied["revision"]["id"]
        if working_id == request.revision_id:
            raise OptimisationError("The working copy is the original revision.")
        if self._revision(request.revision_id)["xml"] != original_xml:
            raise OptimisationError("Copying the build changed the original revision.")

        state = self.tools.invoke("get_build_state", {"revision_id": working_id})
        baseline = _require_calculation(state.get("calculation"))
        summary = state.get("summary") or {}
        class_name = summary.get("className")
        if not class_name:
            raise OptimisationError("The engine did not report a class.")
        ascendancy = summary.get("ascendClassName")
        if ascendancy in NO_ASCENDANCY:
            ascendancy = None
        expected_tree = self.tools.knowledge.provenance()["treeVersion"]
        if summary.get("treeVersion") != expected_tree:
            raise OptimisationError(
                f"The build tree is {summary.get('treeVersion')}, and the imported passive graph is {expected_tree}."
            )
        engine_revision = baseline.get("engineRevision") or ""
        _require_same_revision(baseline, self.tools.engine.process.revision)
        baseline_score = score_calculation(baseline, request.objective)
        self._remember(working_id, baseline, trial=None)

        current_id = working_id
        current_calculation = baseline
        current_score = baseline_score
        applied: set[str] = set()
        skipped: set[str] = set()
        trials: list[dict] = []
        adopted: list[dict] = []
        iterations = 0
        stopped = "exhausted"
        sequence = 0

        while True:
            if request.cancel is not None and request.cancel.cancelled():
                stopped = "cancelled"
                break
            pending = [
                (index, candidate)
                for index, candidate in enumerate(request.candidates)
                if candidate.key not in applied and candidate.key not in skipped
            ]
            if not pending:
                stopped = "exhausted"
                break
            generation: list[dict] = []
            halted = False
            for index, candidate in pending:
                if request.cancel is not None and request.cancel.cancelled():
                    stopped = "cancelled"
                    halted = True
                    break
                if iterations >= request.max_iterations:
                    stopped = "max_iterations"
                    halted = True
                    break
                iterations += 1
                sequence += 1
                trial = self._evaluate(
                    request,
                    candidate,
                    index=index,
                    sequence=sequence,
                    parent_id=current_id,
                    parent_score=current_score,
                    original_id=request.revision_id,
                    class_name=class_name,
                    ascendancy=ascendancy,
                    engine_revision=engine_revision,
                )
                generation.append(trial)
                trials.append(trial)
                score = trial["score"]
                # A candidate that does not beat this parent is not tried again. One that
                # does is retried on the next parent, because the edits interact.
                if trial["status"] != "accepted" or not isinstance(score, (int, float)) or score <= current_score:
                    skipped.add(candidate.key)
                if request.on_trial is not None:
                    request.on_trial(trial)
            chosen = _best_accepted(generation, current_score)
            if chosen is not None:
                current_id = chosen["revisionId"]
                current_calculation = chosen["calculation"]
                current_score = chosen["score"]
                applied.add(chosen["candidateKey"])
                adopted.append(chosen)
            if halted:
                break
            if chosen is None:
                stopped = "no_improvement"
                break

        if self._revision(request.revision_id)["xml"] != original_xml:
            raise OptimisationError("The search changed the original revision.")
        failure = unmet_constraint(current_calculation, request.objective)
        steps = [_public_step(None, "baseline", working_id, baseline, baseline_score, cached=False)]
        steps.extend(_public_step_from_trial(trial) for trial in adopted)
        return {
            "source": "pob-engine",
            "stopped": stopped,
            "impossible": failure is not None,
            "constraint": failure,
            "objective": _public_objective(request.objective),
            "engineRevision": engine_revision,
            "treeVersion": baseline.get("treeVersion"),
            "manifestVersion": baseline.get("manifestVersion"),
            "originalRevisionId": request.revision_id,
            "workingCopyRevisionId": working_id,
            "iterations": iterations,
            "maxIterations": request.max_iterations,
            "maxPassivePoints": request.max_passive_points,
            "baseline": {
                "revisionId": working_id,
                "calculation": baseline,
                "score": baseline_score,
                "summary": summary,
            },
            "best": {
                "revisionId": current_id,
                "calculation": current_calculation,
                "score": current_score,
                "appliedCandidateIds": [trial["candidateId"] for trial in adopted],
                "copiedFromRevisionId": request.revision_id,
                "workingCopyRevisionId": working_id,
            },
            "steps": steps,
            "ranking": _ranking(baseline, baseline_score, working_id, trials),
            "trials": [_public_trial(trial) for trial in trials],
            "rejected": [
                _public_trial(trial) for trial in trials if trial["status"] != "accepted"
            ],
            "cache": self.cache.snapshot(),
        }

    def _validate(self, request: SearchRequest) -> None:
        if not request.revision_id or not str(request.revision_id).strip():
            raise OptimisationError("revision_id is required.")
        if (
            isinstance(request.max_iterations, bool)
            or not isinstance(request.max_iterations, int)
            or request.max_iterations < 1
        ):
            raise OptimisationError("max_iterations must be an integer of at least 1.")
        if request.max_passive_points is not None and (
            isinstance(request.max_passive_points, bool)
            or not isinstance(request.max_passive_points, int)
            or request.max_passive_points < 0
        ):
            raise OptimisationError("max_passive_points must be a non-negative integer.")
        if not request.objective.goals:
            raise OptimisationError("An objective needs at least one stat.")
        ids = [candidate.candidate_id for candidate in request.candidates]
        if len(ids) != len(set(ids)):
            raise OptimisationError("candidate_id values must be unique.")

    def _evaluate(
        self,
        request: SearchRequest,
        candidate: Candidate,
        *,
        index: int,
        sequence: int,
        parent_id: str,
        parent_score: float,
        original_id: str,
        class_name: str,
        ascendancy: str | None,
        engine_revision: str,
    ) -> dict:
        if parent_id == original_id:
            raise OptimisationError("Refusing to edit the original revision.")
        parent_hash, profile = canonical_build(self._revision(parent_id)["xml"])
        cached = self.cache.lookup_trial(parent_hash, candidate.key, engine_revision, profile)
        if cached is not None:
            calculation, revision_id = cached
            failure = unmet_constraint(calculation, request.objective)
            if failure is not None:
                return _trial(
                    candidate,
                    index,
                    sequence,
                    status="rejected",
                    reason=failure,
                    kind_reason="constraint",
                    cached=True,
                    parent_id=parent_id,
                    revision_id=revision_id,
                    calculation=calculation,
                    score=score_calculation(calculation, request.objective),
                )
            return _trial(
                candidate,
                index,
                sequence,
                status="accepted",
                reason=None,
                kind_reason=None,
                cached=True,
                parent_id=parent_id,
                revision_id=revision_id,
                calculation=calculation,
                score=score_calculation(calculation, request.objective),
            )

        if isinstance(candidate, PassiveCandidate):
            refusal = self._refuse_passive(
                candidate,
                class_name=class_name,
                ascendancy=ascendancy,
                max_passive_points=request.max_passive_points,
            )
            if refusal is not None:
                return _trial(
                    candidate,
                    index,
                    sequence,
                    status="rejected",
                    reason=refusal[1],
                    kind_reason=refusal[0],
                    cached=False,
                    parent_id=parent_id,
                    revision_id=None,
                    calculation=None,
                    score=None,
                )

        parent_xml = self._revision(parent_id)["xml"]
        try:
            result = self._apply(parent_id, candidate)
        except DisconnectedAllocation as exc:
            self._require_unchanged(parent_id, parent_xml)
            return _rejected_exception(candidate, index, sequence, parent_id, "disconnected", exc)
        except PointBudgetExceeded as exc:
            self._require_unchanged(parent_id, parent_xml)
            return _rejected_exception(candidate, index, sequence, parent_id, "point_budget", exc)
        except (EngineError, AgentError, KnowledgeError) as exc:
            self._require_unchanged(parent_id, parent_xml)
            return _rejected_exception(candidate, index, sequence, parent_id, "invalid", exc)
        self._require_unchanged(parent_id, parent_xml)

        if result.get("copiedFromRevisionId") != parent_id:
            raise OptimisationError("The tool did not copy the revision it was given.")
        revision_id = (result.get("revision") or {}).get("id")
        if not revision_id or revision_id in {parent_id, original_id}:
            raise OptimisationError("The tool did not return a new revision.")
        calculation = _require_calculation(result.get("calculation"))
        _require_same_revision(calculation, engine_revision)
        self._remember(
            revision_id,
            calculation,
            trial=(parent_hash, candidate.key, engine_revision, profile),
        )
        failure = unmet_constraint(calculation, request.objective)
        score = score_calculation(calculation, request.objective)
        status = "rejected" if failure is not None else "accepted"
        return _trial(
            candidate,
            index,
            sequence,
            status=status,
            reason=failure,
            kind_reason="constraint" if failure is not None else None,
            cached=False,
            parent_id=parent_id,
            revision_id=revision_id,
            calculation=calculation,
            score=score,
            summary=result.get("summary"),
            equipment=result.get("equipment"),
            passive=result.get("passive"),
        )

    def _apply(self, parent_id: str, candidate: Candidate) -> dict:
        if isinstance(candidate, EquipmentCandidate):
            arguments: dict = {"revision_id": parent_id, "text": candidate.text}
            if candidate.slot is not None:
                arguments["slot"] = candidate.slot
            return self.tools.invoke("equip_item", arguments)
        arguments = {"revision_id": parent_id}
        if candidate.node_ids:
            arguments["node_ids"] = list(candidate.node_ids)
            if candidate.node_id is not None:
                arguments["node_id"] = candidate.node_id
        else:
            arguments["node_id"] = candidate.node_id
        return self.tools.invoke("allocate_passives", arguments)

    def _refuse_passive(
        self,
        candidate: PassiveCandidate,
        *,
        class_name: str,
        ascendancy: str | None,
        max_passive_points: int | None,
    ) -> tuple[str, str] | None:
        graph = self._passive_graph()
        try:
            if candidate.node_ids:
                nodes = [node_id for node_id in candidate.node_ids if node_id != graph.class_start_id(class_name)]
                if candidate.node_id is not None and candidate.node_id not in candidate.node_ids:
                    return ("invalid", "node_id is not in node_ids.")
            else:
                if candidate.node_id is None:
                    return ("invalid", "A passive candidate needs node_id or node_ids.")
                path = graph.shortest_path(class_name, candidate.node_id)
                nodes = path[1:]
            checked = graph.validate(class_name, nodes, ascendancy=ascendancy)
        except DisconnectedAllocation as exc:
            return ("disconnected", str(exc))
        except PointBudgetExceeded as exc:
            return ("point_budget", str(exc))
        except KnowledgeError as exc:
            return ("invalid", str(exc))
        if max_passive_points is not None and checked["regularPoints"] > max_passive_points:
            return (
                "point_budget",
                f"Allocation spends {checked['regularPoints']} passive points; "
                f"the search budget is {max_passive_points}.",
            )
        return None

    def _remember(self, revision_id: str, calculation: dict, trial: TrialKey | None) -> None:
        build_hash, profile = canonical_build(self._revision(revision_id)["xml"])
        self.cache.store(
            build_hash=build_hash,
            engine_revision=calculation["engineRevision"],
            profile=profile,
            calculation=calculation,
            revision_id=revision_id,
            trial=trial,
        )

    def _passive_graph(self):
        if self._graph is None:
            self._graph = self.tools.knowledge.graph()
        return self._graph

    def _require_unchanged(self, revision_id: str, xml: str) -> None:
        if self._revision(revision_id)["xml"] != xml:
            raise OptimisationError("The search changed a revision it was only reading.")

    def _revision(self, revision_id: str) -> dict:
        try:
            return self.tools.engine.store.get(revision_id)
        except KeyError as exc:
            raise OptimisationError(f"Unknown revision {revision_id}.") from exc


def _require_calculation(calculation: object) -> dict:
    if not isinstance(calculation, dict) or calculation.get("source") != "pob-engine":
        raise OptimisationError("The tool did not return an engine calculation.")
    if not isinstance(calculation.get("stats"), dict):
        raise OptimisationError("The engine result has no stat table.")
    return calculation


def _require_same_revision(calculation: dict, engine_revision: str) -> None:
    if calculation.get("engineRevision") != engine_revision:
        raise OptimisationError("The engine revision changed during the search.")


def _best_accepted(generation: list[dict], parent_score: float) -> dict | None:
    feasible = [
        trial
        for trial in generation
        if trial["status"] == "accepted" and trial["score"] is not None and trial["score"] > parent_score
    ]
    if not feasible:
        return None
    return min(feasible, key=lambda trial: (-trial["score"], trial["index"]))


def _trial(
    candidate: Candidate,
    index: int,
    sequence: int,
    *,
    status: str,
    reason: str | None,
    kind_reason: str | None,
    cached: bool,
    parent_id: str,
    revision_id: str | None,
    calculation: dict | None,
    score: float | None,
    summary: dict | None = None,
    equipment: dict | None = None,
    passive: dict | None = None,
) -> dict:
    return {
        "candidateId": candidate.candidate_id,
        "candidateKey": candidate.key,
        "kind": candidate.kind,
        "label": candidate.label,
        "index": index,
        "sequence": sequence,
        "status": status,
        "reason": reason,
        "rejection": kind_reason,
        "cached": cached,
        "parentRevisionId": parent_id,
        "revisionId": revision_id,
        "calculation": calculation,
        "score": score,
        "summary": summary,
        "equipment": equipment,
        "passive": passive,
    }


def _rejected_exception(
    candidate: Candidate,
    index: int,
    sequence: int,
    parent_id: str,
    rejection: str,
    exc: Exception,
) -> dict:
    return _trial(
        candidate,
        index,
        sequence,
        status="rejected",
        reason=str(exc),
        kind_reason=rejection,
        cached=False,
        parent_id=parent_id,
        revision_id=None,
        calculation=None,
        score=None,
    )


def _public_trial(trial: dict) -> dict:
    return {key: value for key, value in trial.items() if key != "candidateKey"}


def _public_step(
    candidate_id: str | None,
    label: str,
    revision_id: str,
    calculation: dict,
    score: float,
    *,
    cached: bool,
) -> dict:
    return {
        "candidateId": candidate_id,
        "label": label,
        "revisionId": revision_id,
        "calculation": calculation,
        "score": score,
        "cached": cached,
    }


def _public_step_from_trial(trial: dict) -> dict:
    return _public_step(
        trial["candidateId"],
        trial["label"],
        trial["revisionId"],
        trial["calculation"],
        trial["score"],
        cached=trial["cached"],
    )


def _ranking(baseline: dict, baseline_score: float, working_id: str, trials: list[dict]) -> list[dict]:
    rows = [
        {
            "candidateId": None,
            "label": "baseline",
            "revisionId": working_id,
            "calculation": baseline,
            "score": baseline_score,
            "sequence": 0,
            "cached": False,
        }
    ]
    for trial in trials:
        if trial["status"] != "accepted" or trial["calculation"] is None or trial["score"] is None:
            continue
        rows.append(
            {
                "candidateId": trial["candidateId"],
                "label": trial["label"],
                "revisionId": trial["revisionId"],
                "calculation": trial["calculation"],
                "score": trial["score"],
                "sequence": trial["sequence"],
                "cached": trial["cached"],
            }
        )
    rows.sort(key=lambda row: (-row["score"], row["sequence"]))
    return rows


def _public_objective(objective: Objective) -> dict:
    return {
        "name": objective.name,
        "goals": [
            {"stat": goal.stat, "weight": goal.weight, "direction": goal.direction}
            for goal in objective.goals
        ],
        "minimums": [{"stat": stat, "minimum": floor} for stat, floor in objective.minimums],
        "maximums": [{"stat": stat, "maximum": cap} for stat, cap in objective.maximums],
    }
