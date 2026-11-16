"""Phase 5 search. The Scion fixture is calculated by the pinned engine."""

import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path

import pytest

import pob_optimisation
from pob_agent.tools import Toolset
from pob_engine.examples import LIFE_PLATE
from pob_engine.paths import resolve_paths as resolve_engine_paths
from pob_engine.service import EngineService
from pob_knowledge.paths import resolve_paths as resolve_knowledge_paths
from pob_knowledge.store import KnowledgeStore
from pob_optimisation.candidates import (
    EquipmentCandidate,
    PassiveCandidate,
    equipment_candidates_from_uniques,
    passive_candidates_for_text,
)
from pob_optimisation.errors import OptimisationError
from pob_optimisation.identity import canonical_build
from pob_optimisation.objective import Objective, StatGoal, score_calculation
from pob_optimisation.search import CancelToken, Optimiser, SearchRequest

PLAIN_PLATE = """Rarity: Rare
Plain Plate
Glorious Plate
"""
UNKNOWN_BASE = """Rarity: Rare
Nope
Not A Real Base
"""
ROUND_AFTER_EFFICIENCY = (
    "output[costName] = m_max(0, output[costName] / costEfficiency)\n"
    "\t\t\t\tif val.upfront and not val.percent then\n"
    "\t\t\t\t\t-- The game stores upfront resource costs as whole numbers after efficiency.\n"
    "\t\t\t\t\toutput[costName] = round(output[costName])"
)
LIFE = Objective("life", (StatGoal("Life"),))


@pytest.fixture(scope="module")
def paths():
    return resolve_knowledge_paths()


@pytest.fixture(scope="module")
def engine():
    running = EngineService.start()
    try:
        yield running
    finally:
        running.close()


@pytest.fixture(scope="module")
def knowledge(tmp_path_factory, paths):
    database = tmp_path_factory.mktemp("optimisation-knowledge") / "knowledge.sqlite"
    store = KnowledgeStore(database)
    store.import_checkout(paths)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture(scope="module")
def tools(engine, knowledge):
    return Toolset(engine, knowledge)


def _fixture_xml() -> str:
    return resolve_engine_paths().fixture.read_text(encoding="utf-8")


def _life(calculation: dict) -> float:
    assert calculation["source"] == "pob-engine"
    assert calculation["ignoredStoredPlayerStat"] is True
    return calculation["stats"]["Life"]


def _objective() -> Objective:
    return LIFE


def _import(tools: Toolset, name: str) -> tuple[str, str, str]:
    xml = _fixture_xml()
    imported = tools.invoke("import_build", {"name": name, "xml": xml})
    revision_id = imported["revision"]["id"]
    build_id = imported["build"]["id"]
    assert tools.engine.store.get(revision_id)["xml"] == xml
    return xml, revision_id, build_id


def _allocated(xml: str) -> set[int]:
    root = ET.fromstring(xml)
    specs = root.findall("./Tree/Spec")
    assert specs
    raw = specs[0].attrib.get("nodes", "")
    return {int(part) for part in raw.split(",") if part.strip().isdigit()}


def _connected_regular(graph, class_name: str, count: int) -> list[int]:
    start = graph.class_start_id(class_name)
    seen = {start}
    queue: deque[int] = deque([start])
    picked: list[int] = []
    while queue and len(picked) < count:
        current = queue.popleft()
        if graph.nodes[current].node_type == "Mastery":
            continue
        for neighbor in graph.neighbors(current):
            if neighbor in seen:
                continue
            node = graph.nodes[neighbor]
            if node.ascendancy_name or node.node_type == "ClassStart" or node.granted_passive_points:
                continue
            seen.add(neighbor)
            if graph.allocation_kind(neighbor) == "regular":
                picked.append(neighbor)
            if node.node_type != "Mastery":
                queue.append(neighbor)
            if len(picked) >= count:
                break
    return picked


def _count_requests(engine: EngineService):
    actions: list[str] = []
    original = engine.process.request

    def counting(action, timeout=60, **params):
        actions.append(action)
        return original(action, timeout=timeout, **params)

    engine.process.request = counting
    return actions, original


def test_build_hash_ignores_the_stat_cache_and_keeps_the_profile():
    xml = _fixture_xml()
    digest, profile = canonical_build(xml)
    assert canonical_build(xml) == (digest, profile)
    forged = xml.replace('stat="Life" value="60"', 'stat="Life" value="999999"', 1)
    assert forged != xml
    assert canonical_build(forged) == (digest, profile)
    retargeted = xml.replace('nodes="58833"', 'nodes="58833,1"', 1)
    assert canonical_build(retargeted)[0] != digest
    reconfigured = xml.replace('name="enemyLevel" number="84"', 'name="enemyLevel" number="83"', 1)
    changed_hash, changed_profile = canonical_build(reconfigured)
    assert changed_hash == digest
    assert changed_profile != profile


def test_score_uses_only_an_engine_stat_table():
    with pytest.raises(OptimisationError, match="did not come from the engine"):
        score_calculation({"source": "guess", "stats": {"Life": 1}}, _objective())
    with pytest.raises(OptimisationError):
        EquipmentCandidate("plate", "  ", slot="Body Armour")
    with pytest.raises(OptimisationError):
        PassiveCandidate("node")


def test_candidate_generation_uses_the_import(knowledge, paths):
    pin = paths.pin
    graph = knowledge.graph()
    life_id = pin["measured"]["lifeNodeId"]
    first = passive_candidates_for_text(graph, "Scion", "maximum Life", limit=400)
    second = passive_candidates_for_text(graph, "Scion", "maximum Life", limit=400)
    assert [candidate.node_id for candidate in first] == [candidate.node_id for candidate in second]
    assert first
    found = next(candidate for candidate in first if candidate.node_id == life_id)
    assert found.label == pin["measured"]["lifeNodeName"]
    lengths = [len(graph.shortest_path("Scion", candidate.node_id)) for candidate in first]
    assert lengths == sorted(lengths)
    for left, right in zip(first, first[1:]):
        left_length = len(graph.shortest_path("Scion", left.node_id))
        right_length = len(graph.shortest_path("Scion", right.node_id))
        if left_length == right_length:
            assert left.node_id < right.node_id

    heart = knowledge.unique_items("Kaom's Heart")[0]
    equipment = equipment_candidates_from_uniques([heart], limit=3, slot="Body Armour")
    assert len(equipment) == 1
    assert equipment[0].text == heart["rawText"]
    assert equipment[0].slot == "Body Armour"
    assert equipment[0].label == "Kaom's Heart"
    assert heart["sourceCommit"] == pin["commit"]


def test_duplicate_ids_and_the_iteration_limit_are_rejected(tools):
    plate = EquipmentCandidate("plate", LIFE_PLATE, slot="Body Armour")
    with pytest.raises(OptimisationError, match="unique"):
        Optimiser(tools).search(
            SearchRequest(
                revision_id="not-used",
                candidates=(plate, EquipmentCandidate("plate", LIFE_PLATE, slot="Body Armour")),
                objective=_objective(),
            )
        )
    with pytest.raises(OptimisationError, match="max_iterations"):
        Optimiser(tools).search(
            SearchRequest(revision_id="not-used", candidates=(), objective=_objective(), max_iterations=0)
        )
    with pytest.raises(OptimisationError, match="Unknown revision"):
        Optimiser(tools).search(
            SearchRequest(revision_id="missing", candidates=(), objective=_objective())
        )


def test_search_finds_the_plate_and_the_life_node(engine, knowledge, tools, paths):
    pin = paths.pin["measured"]
    baseline_life = pin["baselineLife"]
    plate_life = pin["lifeAfterFlat100"]
    allocated_life = pin["lifeAfterNode"]
    life_id = pin["lifeNodeId"]
    xml, import_id, build_id = _import(tools, "Search Scion")
    graph = knowledge.graph()
    generated = passive_candidates_for_text(graph, "Scion", "maximum Life", limit=400)
    life_node = next(candidate for candidate in generated if candidate.node_id == life_id)
    candidates = (
        EquipmentCandidate("not-a-base", UNKNOWN_BASE, slot="Body Armour", label="unknown"),
        PassiveCandidate("disconnected", node_ids=(life_id,), label="disconnected"),
        PassiveCandidate(
            "over-budget",
            node_ids=tuple(_connected_regular(graph, "Scion", 124)),
            label="over-budget",
        ),
        EquipmentCandidate("plain-plate", PLAIN_PLATE, slot="Body Armour", label="plain"),
        EquipmentCandidate("glorious-plate", LIFE_PLATE, slot="Body Armour", label="Glorious Plate"),
        EquipmentCandidate("plate-again", LIFE_PLATE, slot="Body Armour", label="Glorious Plate again"),
        PassiveCandidate("life-node", node_id=life_node.node_id, label=life_node.label),
    )
    optimiser = Optimiser(tools)
    actions, original_request = _count_requests(engine)
    try:
        result = optimiser.search(
            SearchRequest(
                revision_id=import_id,
                candidates=candidates,
                objective=_objective(),
                max_iterations=20,
            )
        )
    finally:
        engine.process.request = original_request

    assert result["source"] == "pob-engine"
    assert result["stopped"] in {"exhausted", "no_improvement"}
    assert result["impossible"] is False
    assert result["engineRevision"] == paths.pin["commit"]
    assert result["originalRevisionId"] == import_id
    assert result["iterations"] < 20
    assert engine.store.get(import_id)["xml"] == xml
    assert engine.store.get(result["workingCopyRevisionId"])["xml"] == xml
    assert engine.store.get(result["workingCopyRevisionId"])["status"] == "draft"
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id

    assert _life(result["baseline"]["calculation"]) == baseline_life
    assert _life(result["steps"][0]["calculation"]) == baseline_life
    assert _life(result["best"]["calculation"]) == allocated_life
    assert _life(result["steps"][-1]["calculation"]) == allocated_life
    assert result["best"]["revisionId"] != import_id
    assert set(result["best"]["appliedCandidateIds"]) >= {"glorious-plate", "life-node"}

    plate = next(
        trial
        for trial in result["trials"]
        if trial["candidateId"] == "glorious-plate"
        and trial["parentRevisionId"] == result["workingCopyRevisionId"]
    )
    assert plate["cached"] is False
    assert plate["status"] == "accepted"
    assert _life(plate["calculation"]) == plate_life
    assert plate["calculation"]["engineRevision"] == paths.pin["commit"]
    assert plate["equipment"]["baseName"] == "Glorious Plate"
    assert any("+100 to maximum Life" in str(line) for line in plate["equipment"]["explicitLines"])
    again = next(trial for trial in result["trials"] if trial["candidateId"] == "plate-again")
    assert again["cached"] is True
    assert again["revisionId"] == plate["revisionId"]
    assert again["calculation"]["stats"] == plate["calculation"]["stats"]

    scores = [row["score"] for row in result["ranking"]]
    assert scores == sorted(scores, reverse=True)
    assert result["ranking"][0]["revisionId"] == result["best"]["revisionId"]
    for row in result["ranking"]:
        assert row["calculation"]["source"] == "pob-engine"
        assert row["score"] == row["calculation"]["stats"]["Life"]
    assert plate_life in {row["calculation"]["stats"]["Life"] for row in result["ranking"]}
    assert allocated_life in {row["calculation"]["stats"]["Life"] for row in result["ranking"]}

    best_xml = engine.store.get(result["best"]["revisionId"])["xml"]
    assert "+100 to maximum Life" in best_xml
    assert "Glorious Plate" in best_xml
    assert life_id in _allocated(best_xml)
    assert "Glorious Plate" not in xml
    assert life_id not in _allocated(xml)

    rejected = {trial["candidateId"]: trial for trial in result["rejected"]}
    assert rejected["disconnected"]["rejection"] == "disconnected"
    assert rejected["disconnected"]["revisionId"] is None
    assert rejected["over-budget"]["rejection"] == "point_budget"
    assert rejected["over-budget"]["revisionId"] is None
    assert rejected["not-a-base"]["rejection"] == "invalid"
    assert rejected["not-a-base"]["revisionId"] is None

    uncached_equipment = [
        trial for trial in result["trials"] if trial["kind"] == "equipment" and not trial["cached"]
    ]
    applied_passives = [
        trial
        for trial in result["trials"]
        if trial["kind"] == "passive" and trial["revisionId"] and not trial["cached"]
    ]
    assert actions.count("equip_item") == len(uncached_equipment)
    assert actions.count("allocate_node") == len(applied_passives)
    assert result["cache"]["hits"] >= 1
    assert result["cache"]["misses"] >= 1

    hits = optimiser.cache.hits
    cached = optimiser.calculate(import_id)
    assert optimiser.cache.hits == hits + 1
    fresh = engine.calculate(import_id)
    assert cached["source"] == "pob-engine"
    assert cached["stats"] == fresh["stats"]
    assert cached["engineRevision"] == fresh["engineRevision"]
    assert fresh["stats"]["Life"] == baseline_life
    assert engine.store.get(import_id)["xml"] == xml

    weighted = score_calculation(
        result["best"]["calculation"],
        Objective("life-and-es", (StatGoal("Life", 1), StatGoal("EnergyShield", 0.5))),
    )
    stats = result["best"]["calculation"]["stats"]
    assert weighted == stats["Life"] + 0.5 * stats["EnergyShield"]

    compared = tools.invoke(
        "compare_builds",
        {"left_revision_id": import_id, "right_revision_id": result["best"]["revisionId"]},
    )
    focus = compared["focus"]["Life"]
    assert compared["source"] == "pob-engine"
    assert focus == {"left": baseline_life, "right": allocated_life, "delta": allocated_life - baseline_life}
    assert engine.store.get(import_id)["xml"] == xml
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id


def test_max_iterations_stops_before_the_life_node(engine, tools, paths):
    pin = paths.pin["measured"]
    xml, import_id, build_id = _import(tools, "Limited Scion")
    result = Optimiser(tools).search(
        SearchRequest(
            revision_id=import_id,
            candidates=(
                EquipmentCandidate("glorious-plate", LIFE_PLATE, slot="Body Armour", label="Glorious Plate"),
                PassiveCandidate("life-node", node_id=pin["lifeNodeId"], label=pin["lifeNodeName"]),
            ),
            objective=_objective(),
            max_iterations=1,
        )
    )
    assert result["stopped"] == "max_iterations"
    assert result["iterations"] == 1
    assert result["best"]["appliedCandidateIds"] == ["glorious-plate"]
    assert _life(result["baseline"]["calculation"]) == pin["baselineLife"]
    assert _life(result["best"]["calculation"]) == pin["lifeAfterFlat100"]
    assert all(trial["candidateId"] != "life-node" for trial in result["trials"])
    assert pin["lifeNodeId"] not in _allocated(engine.store.get(result["best"]["revisionId"])["xml"])
    assert engine.store.get(import_id)["xml"] == xml
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id


def test_cancel_before_the_first_candidate_leaves_the_import(engine, tools, paths):
    pin = paths.pin["measured"]
    xml, import_id, build_id = _import(tools, "Cancelled Scion")
    token = CancelToken()
    token.cancel()
    result = Optimiser(tools).search(
        SearchRequest(
            revision_id=import_id,
            candidates=(
                EquipmentCandidate("glorious-plate", LIFE_PLATE, slot="Body Armour", label="Glorious Plate"),
            ),
            objective=_objective(),
            cancel=token,
        )
    )
    assert result["stopped"] == "cancelled"
    assert result["iterations"] == 0
    assert result["trials"] == []
    assert result["best"]["appliedCandidateIds"] == []
    assert _life(result["best"]["calculation"]) == pin["baselineLife"]
    assert "Glorious Plate" not in engine.store.get(result["best"]["revisionId"])["xml"]
    assert engine.store.get(import_id)["xml"] == xml
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id


def test_cancel_between_candidates_does_not_continue(engine, tools, paths):
    pin = paths.pin["measured"]
    xml, import_id, build_id = _import(tools, "Interrupted Scion")
    token = CancelToken()

    def stop(_trial: dict) -> None:
        token.cancel()

    result = Optimiser(tools).search(
        SearchRequest(
            revision_id=import_id,
            candidates=(
                PassiveCandidate("disconnected", node_ids=(pin["lifeNodeId"],), label="disconnected"),
                EquipmentCandidate("glorious-plate", LIFE_PLATE, slot="Body Armour", label="Glorious Plate"),
            ),
            objective=_objective(),
            cancel=token,
            on_trial=stop,
        )
    )
    assert result["stopped"] == "cancelled"
    assert result["iterations"] == 1
    assert [trial["candidateId"] for trial in result["trials"]] == ["disconnected"]
    assert result["rejected"][0]["rejection"] == "disconnected"
    assert result["best"]["appliedCandidateIds"] == []
    assert _life(result["best"]["calculation"]) == pin["baselineLife"]
    assert engine.store.get(import_id)["xml"] == xml
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id


def test_passive_point_budget_rejects_the_life_path(engine, tools, paths):
    pin = paths.pin["measured"]
    xml, import_id, build_id = _import(tools, "Budget Scion")
    result = Optimiser(tools).search(
        SearchRequest(
            revision_id=import_id,
            candidates=(
                EquipmentCandidate("glorious-plate", LIFE_PLATE, slot="Body Armour", label="Glorious Plate"),
                PassiveCandidate("life-node", node_id=pin["lifeNodeId"], label=pin["lifeNodeName"]),
            ),
            objective=_objective(),
            max_passive_points=1,
        )
    )
    assert result["stopped"] in {"exhausted", "no_improvement"}
    assert result["best"]["appliedCandidateIds"] == ["glorious-plate"]
    assert _life(result["best"]["calculation"]) == pin["lifeAfterFlat100"]
    rejected = next(trial for trial in result["rejected"] if trial["candidateId"] == "life-node")
    assert rejected["rejection"] == "point_budget"
    assert "search budget" in rejected["reason"]
    assert rejected["revisionId"] is None
    assert pin["lifeNodeId"] not in _allocated(engine.store.get(result["best"]["revisionId"])["xml"])
    assert engine.store.get(import_id)["xml"] == xml
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id


def test_an_unreachable_life_minimum_is_reported(engine, tools, paths):
    pin = paths.pin["measured"]
    xml, import_id, build_id = _import(tools, "Impossible Scion")
    objective = Objective("life", (StatGoal("Life"),), minimums=(("Life", 1_000_000),))
    result = Optimiser(tools).search(
        SearchRequest(
            revision_id=import_id,
            candidates=(
                EquipmentCandidate("glorious-plate", LIFE_PLATE, slot="Body Armour", label="Glorious Plate"),
            ),
            objective=objective,
        )
    )
    assert result["impossible"] is True
    assert result["constraint"]
    assert result["best"]["appliedCandidateIds"] == []
    assert _life(result["best"]["calculation"]) == pin["baselineLife"]
    plate = next(trial for trial in result["trials"] if trial["candidateId"] == "glorious-plate")
    assert plate["status"] == "rejected"
    assert plate["rejection"] == "constraint"
    assert _life(plate["calculation"]) == pin["lifeAfterFlat100"]
    assert engine.store.get(import_id)["xml"] == xml
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id


def test_package_does_not_call_a_model_or_drop_the_cost_round(paths):
    root = Path(pob_optimisation.__file__).resolve().parent
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for token in ("urlopen", "httpx", "requests", "http.client", "socket.", "openai", "anthropic", "api_key"):
        assert token not in text
    for token in ("999999", "lifeAfterNode", "15073"):
        assert token not in text
    offence = (paths.src / "Modules" / "CalcOffence.lua").read_text(encoding="utf-8")
    assert offence.count(ROUND_AFTER_EFFICIENCY) == 2
