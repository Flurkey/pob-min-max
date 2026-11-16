"""Phase 4 tools. A fake provider chooses the calls. Numbers come from the engine or the import."""

import json
from collections import deque
from pathlib import Path

import pytest

import pob_agent
from pob_agent.errors import AgentError, ProviderError, ToolArgumentError
from pob_agent.provider import (
    LIVE_KINDS,
    LiveProvider,
    ProviderSpec,
    ProviderTurn,
    ToolCall,
    build_http_request,
    render_tools,
)
from pob_agent.session import AgentSession
from pob_agent.tools import Toolset
from pob_engine.errors import EngineError
from pob_engine.examples import LIFE_PLATE
from pob_engine.paths import resolve_paths as resolve_engine_paths
from pob_engine.service import EngineService
from pob_engine.xml_cache import stored_player_stats
from pob_knowledge.errors import DisconnectedAllocation, PointBudgetExceeded
from pob_knowledge.paths import resolve_paths as resolve_knowledge_paths
from pob_knowledge.store import KnowledgeStore

TOOL_NAMES = (
    "import_build",
    "get_build_state",
    "calculate_build",
    "compare_builds",
    "search_unique_items",
    "search_skill_gems",
    "search_passive_nodes",
    "find_passive_path",
    "allocate_passives",
    "equip_item",
    "export_build",
)
FORGED_LIFE = "999999"
UNIQUE_LINE = "{variant:1,3}+1000 to maximum Life"
ROUND_AFTER_EFFICIENCY = (
    "output[costName] = m_max(0, output[costName] / costEfficiency)\n"
    "\t\t\t\tif val.upfront and not val.percent then\n"
    "\t\t\t\t\t-- The game stores upfront resource costs as whole numbers after efficiency.\n"
    "\t\t\t\t\toutput[costName] = round(output[costName])"
)


class ScriptedProvider:
    """Issues a fixed tool sequence. It never writes a calculated Life value."""

    kind = "fake"

    def __init__(self, xml: str, life_node_id: int):
        self.xml = xml
        self.life_node_id = life_node_id
        self.claims: list[str] = []

    def complete(self, messages, tools):
        names = {tool["name"] for tool in tools}
        assert set(TOOL_NAMES) <= names
        results = [json.loads(message.content) for message in messages if message.role == "tool"]
        claim, call = self._step(len(results), results)
        self.claims.append(claim)
        if call is None:
            return ProviderTurn(content=claim)
        return ProviderTurn(content=claim, tool_calls=(call,))

    def _step(self, step: int, results: list[dict]):
        if step == 0:
            return (
                f"The XML cache says Life is {FORGED_LIFE}, so that is the life total.",
                ToolCall("import_build", {"name": "Scripted Scion", "xml": self.xml}, "import"),
            )
        import_id = results[0]["revision"]["id"]
        if step == 1:
            return (
                f"I still say Life is {FORGED_LIFE}.",
                ToolCall("get_build_state", {"revision_id": import_id}, "state"),
            )
        if step == 2:
            return (
                f"Equipping the plate sets Life to {FORGED_LIFE}.",
                ToolCall(
                    "equip_item",
                    {"revision_id": import_id, "text": LIFE_PLATE, "slot": "Body Armour"},
                    "equip",
                ),
            )
        equipped_id = results[2]["revision"]["id"]
        if step == 3:
            return (
                f"Allocating the life node sets Life to {FORGED_LIFE}.",
                ToolCall(
                    "allocate_passives",
                    {"revision_id": equipped_id, "node_id": self.life_node_id},
                    "allocate",
                ),
            )
        allocated_id = results[3]["revision"]["id"]
        if step == 4:
            return (
                "The comparison is whatever I guessed.",
                ToolCall(
                    "compare_builds",
                    {"left_revision_id": import_id, "right_revision_id": allocated_id},
                    "compare",
                ),
            )
        if step == 5:
            return (
                "Recalculate the import.",
                ToolCall("calculate_build", {"revision_id": import_id}, "calc"),
            )
        if step == 6:
            return (
                "Look up a unique.",
                ToolCall("search_unique_items", {"query": "Kaom's Heart", "limit": 5}, "unique"),
            )
        if step == 7:
            return (
                "Look up a gem.",
                ToolCall("search_skill_gems", {"query": "Kinetic Blast", "limit": 5}, "gem"),
            )
        if step == 8:
            return (
                "Look up a node.",
                ToolCall("search_passive_nodes", {"query": str(self.life_node_id), "limit": 5}, "node"),
            )
        if step == 9:
            return (
                "Find the path.",
                ToolCall(
                    "find_passive_path",
                    {"class_name": "Scion", "node_id": self.life_node_id},
                    "path",
                ),
            )
        if step == 10:
            return (
                "Export the edited copy.",
                ToolCall("export_build", {"revision_id": allocated_id}, "export"),
            )
        return ("Done. I do not have a life total of my own.", None)


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
    database = tmp_path_factory.mktemp("agent-knowledge") / "knowledge.sqlite"
    store = KnowledgeStore(database)
    store.import_checkout(paths)
    try:
        yield store
    finally:
        store.close()


@pytest.fixture(scope="module")
def tools(engine, knowledge):
    return Toolset(engine, knowledge)


def _pin(paths):
    return paths.pin


def _forged_xml() -> str:
    original = resolve_engine_paths().fixture.read_text(encoding="utf-8")
    forged = original.replace('stat="Life" value="60"', f'stat="Life" value="{FORGED_LIFE}"', 1)
    assert stored_player_stats(forged)["Life"] == FORGED_LIFE
    return forged


def _step(run: dict, name: str) -> dict:
    matches = [step for step in run["steps"] if step["tool"] == name]
    assert len(matches) == 1
    assert matches[0]["ok"] is True
    return matches[0]


def _revision_ids(service: EngineService, build_id: str) -> list[str]:
    return [row["id"] for row in service.history(build_id)["revisions"]]


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


def test_live_providers_are_described_and_do_not_send():
    sample = [{"name": "import_build", "description": "Import.", "parameters": {"type": "object"}}]
    sent: list[dict] = []

    def transport(request):
        sent.append(request)
        return ProviderTurn(content="not used")

        for kind in LIVE_KINDS:
            rendered = json.dumps(render_tools(kind, sample))
            assert "import_build" in rendered
            if kind == "openai-compatible":
                spec = ProviderSpec(kind=kind, model="local-test", base_url="http://127.0.0.1:9/v1")
            else:
                spec = ProviderSpec(kind=kind, model="local-test")
        provider = LiveProvider(spec, api_key=None if kind == "ollama" else "k" * 12)
        with pytest.raises(ProviderError, match="Refusing to call a model API"):
            provider.complete([], sample)
    assert sent == []
    # The transport stays local. This call builds the request and does not open a socket.
    local = LiveProvider(
        ProviderSpec(kind="ollama", model="local-test"),
        transport=transport,
    )
    assert local.complete([], sample).content == "not used"
    assert sent[0]["url"] == "http://127.0.0.1:11434/api/chat"

    with pytest.raises(ProviderError, match="base URL"):
        ProviderSpec(kind="openai-compatible", model="local-test")

    key = "k" * 12
    openai = build_http_request(
        ProviderSpec(kind="openai", model="local-test"),
        [],
        sample,
        key,
    )
    assert openai["url"] == "https://api.openai.com/v1/chat/completions"
    assert openai["headers"]["Authorization"] == f"Bearer {key}"
    assert key not in json.dumps(openai["json"])

    anthropic = build_http_request(ProviderSpec(kind="anthropic", model="local-test"), [], sample, key)
    assert anthropic["url"] == "https://api.anthropic.com/v1/messages"
    assert anthropic["headers"]["x-api-key"] == key
    assert key not in json.dumps(anthropic["json"])

    gemini = build_http_request(ProviderSpec(kind="gemini", model="local-test"), [], sample, key)
    assert gemini["url"] == "https://generativelanguage.googleapis.com/v1beta/models/local-test:generateContent"
    assert gemini["headers"]["x-goog-api-key"] == key
    assert key not in json.dumps(gemini["json"])
    assert "key=" not in gemini["url"]

    ollama = build_http_request(ProviderSpec(kind="ollama", model="local-test"), [], sample, None)
    assert ollama["url"] == "http://127.0.0.1:11434/api/chat"
    assert "Authorization" not in ollama["headers"]

    compatible = build_http_request(
        ProviderSpec(kind="openai-compatible", model="local-test", base_url="http://127.0.0.1:9/v1"),
        [],
        sample,
        key,
    )
    assert compatible["url"] == "http://127.0.0.1:9/v1/chat/completions"
    with pytest.raises(ProviderError, match="API key"):
        build_http_request(ProviderSpec(kind="openai", model="local-test"), [], sample, None)


def test_agent_package_does_not_embed_oracles_or_call_a_model_api():
    root = Path(pob_agent.__file__).resolve().parent
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    for token in ("urlopen", "httpx", "requests", "http.client", "socket."):
        assert token not in text
    for token in (FORGED_LIFE, UNIQUE_LINE, "KineticBlast", "5% increased maximum Life"):
        assert token not in text


def test_pinned_cost_round_is_still_in_the_checkout(paths):
    offence = (paths.src / "Modules" / "CalcOffence.lua").read_text(encoding="utf-8")
    assert offence.count(ROUND_AFTER_EFFICIENCY) == 2


def test_invalid_tool_arguments_do_not_mutate_the_import(engine, knowledge, tools):
    pin = _pin(resolve_knowledge_paths())
    forged = _forged_xml()
    imported = tools.invoke("import_build", {"name": "Guarded Scion", "xml": forged})
    import_id = imported["revision"]["id"]
    build_id = imported["build"]["id"]
    before = _revision_ids(engine, build_id)
    assert imported["calculation"]["source"] == "pob-engine"
    assert imported["calculation"]["stats"]["Life"] == pin["measured"]["baselineLife"]
    assert stored_player_stats(engine.store.get(import_id)["xml"])["Life"] == FORGED_LIFE

    with pytest.raises(ToolArgumentError):
        tools.invoke("equip_item", {"revision_id": import_id, "text": ""})
    with pytest.raises(ToolArgumentError):
        tools.invoke("equip_item", {"revision_id": import_id, "text": LIFE_PLATE, "slot": "  "})
    with pytest.raises(ToolArgumentError):
        tools.invoke("allocate_passives", {"revision_id": import_id, "node_id": str(pin["measured"]["lifeNodeId"])})
    with pytest.raises(ToolArgumentError):
        tools.invoke("allocate_passives", {"revision_id": import_id})
    with pytest.raises(ToolArgumentError):
        tools.invoke("search_skill_gems", {"query": "   "})
    with pytest.raises(ToolArgumentError, match="Unknown tool"):
        tools.invoke("invent_stat", {"life": FORGED_LIFE})
    with pytest.raises(AgentError, match="Unknown revision"):
        tools.invoke("calculate_build", {"revision_id": "missing"})

    with pytest.raises(DisconnectedAllocation):
        tools.invoke(
            "allocate_passives",
            {"revision_id": import_id, "node_ids": [pin["measured"]["lifeNodeId"]]},
        )
    with pytest.raises(PointBudgetExceeded):
        tools.invoke(
            "allocate_passives",
            {"revision_id": import_id, "node_ids": _connected_regular(knowledge.graph(), "Scion", 124)},
        )
    with pytest.raises(EngineError):
        tools.invoke(
            "equip_item",
            {
                "revision_id": import_id,
                "text": "Rarity: Rare\nNope\nNot A Real Base\n",
                "slot": "Body Armour",
            },
        )

    assert _revision_ids(engine, build_id) == before
    assert engine.store.get(import_id)["xml"] == forged
    assert engine.calculate(import_id)["stats"]["Life"] == pin["measured"]["baselineLife"]
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id


def test_fake_provider_results_come_from_the_engine_and_the_import(engine, knowledge, tools, paths):
    pin = _pin(paths)
    life_node_id = pin["measured"]["lifeNodeId"]
    baseline = pin["measured"]["baselineLife"]
    plate_life = pin["measured"]["lifeAfterFlat100"]
    allocated_life = pin["measured"]["lifeAfterNode"]
    forged = _forged_xml()
    provider = ScriptedProvider(forged, life_node_id)
    run = AgentSession(tools, provider).run("Improve this Scion.", max_steps=12)

    assert run["message"] == "Done. I do not have a life total of my own."
    assert run["steps"] and all(step["ok"] for step in run["steps"])
    assert any(FORGED_LIFE in claim for claim in provider.claims)
    assert [step["tool"] for step in run["steps"]] == [
        "import_build",
        "get_build_state",
        "equip_item",
        "allocate_passives",
        "compare_builds",
        "calculate_build",
        "search_unique_items",
        "search_skill_gems",
        "search_passive_nodes",
        "find_passive_path",
        "export_build",
    ]

    imported = _step(run, "import_build")
    state = _step(run, "get_build_state")
    equipped = _step(run, "equip_item")
    allocated = _step(run, "allocate_passives")
    compared = _step(run, "compare_builds")
    recalculated = _step(run, "calculate_build")
    export = _step(run, "export_build")

    import_id = imported["result"]["revision"]["id"]
    equipped_id = equipped["result"]["revision"]["id"]
    allocated_id = allocated["result"]["revision"]["id"]
    assert stored_player_stats(forged)["Life"] == FORGED_LIFE
    assert engine.store.get(import_id)["xml"] == forged
    assert stored_player_stats(engine.store.get(import_id)["xml"])["Life"] == FORGED_LIFE

    for step in (imported, state, recalculated):
        calculation = step["result"]["calculation"]
        assert calculation["source"] == "pob-engine"
        assert calculation["ignoredStoredPlayerStat"] is True
        assert calculation["stats"]["Life"] == baseline
        assert calculation["stats"]["Life"] != int(FORGED_LIFE)
        assert calculation["engineRevision"] == pin["commit"]
        assert FORGED_LIFE not in json.dumps(step["result"])
    assert state["result"]["summary"]["className"] == "Scion"
    assert "xml" not in state["result"]
    assert recalculated["result"]["calculation"]["stats"] == engine.calculate(import_id)["stats"]

    assert equipped["result"]["copiedFromRevisionId"] == import_id
    assert equipped["result"]["build"]["savedRevisionId"] == import_id
    assert equipped["result"]["calculation"]["source"] == "pob-engine"
    assert equipped["result"]["calculation"]["stats"]["Life"] == plate_life
    assert equipped["result"]["calculation"]["stats"] == engine.calculate(equipped_id)["stats"]
    assert equipped["result"]["comparison"]["source"] == "pob-engine"
    assert any(item["baseName"] == "Glorious Plate" for item in equipped["result"]["summary"]["equipped"])
    assert engine.store.get(equipped["result"]["workingCopyRevisionId"])["xml"] == forged
    assert FORGED_LIFE not in equipped["arguments"]["text"]
    assert str(plate_life) not in equipped["arguments"]["text"]

    assert allocated["result"]["copiedFromRevisionId"] == equipped_id
    assert allocated["result"]["build"]["savedRevisionId"] == import_id
    assert allocated["result"]["passive"]["id"] == life_node_id
    assert allocated["result"]["calculation"]["source"] == "pob-engine"
    assert allocated["result"]["calculation"]["stats"]["Life"] == allocated_life
    assert allocated["result"]["calculation"]["stats"] == engine.calculate(allocated_id)["stats"]
    assert engine.store.get(import_id)["xml"] == forged
    assert engine.store.get(equipped_id)["xml"] == engine.store.get(allocated["result"]["workingCopyRevisionId"])["xml"]
    assert engine.store.get(allocated_id)["xml"] != forged
    assert str(life_node_id) not in equipped["arguments"]["text"]

    focus = compared["result"]["focus"]["Life"]
    assert compared["result"]["source"] == "pob-engine"
    assert focus == {"left": baseline, "right": allocated_life, "delta": allocated_life - baseline}
    assert compared["arguments"]["left_revision_id"] == import_id
    assert compared["arguments"]["right_revision_id"] == allocated_id

    heart = knowledge.unique_items("Kaom's Heart")[0]
    hearts = _step(run, "search_unique_items")["result"]["items"]
    found_heart = next(item for item in hearts if item["name"] == "Kaom's Heart")
    assert found_heart["rawText"] == heart["rawText"]
    assert found_heart["sourceCommit"] == pin["commit"]
    assert found_heart["sourcePath"] == "Data/Uniques/body.lua"
    assert UNIQUE_LINE in found_heart["rawText"]
    assert UNIQUE_LINE in (paths.src / "Data" / "Uniques" / "body.lua").read_text(encoding="utf-8")
    assert UNIQUE_LINE not in json.dumps(_step(run, "search_unique_items")["arguments"])

    gem = knowledge.gem("Kinetic Blast")
    gems = _step(run, "search_skill_gems")["result"]["gems"]
    found_gem = next(item for item in gems if item["name"] == "Kinetic Blast")
    assert found_gem["id"] == gem["id"] == "Metadata/Items/Gems/SkillGemKineticBlast"
    assert found_gem["grantedEffectId"] == gem["grantedEffectId"]
    assert found_gem["grantedEffect"]["description"] == gem["grantedEffect"]["description"]
    assert found_gem["sourceCommit"] == pin["commit"]
    assert "KineticBlast" not in json.dumps(_step(run, "search_skill_gems")["arguments"])

    node = knowledge.node(life_node_id)
    found_node = _step(run, "search_passive_nodes")["result"]["nodes"][0]
    assert found_node["id"] == node["id"]
    assert found_node["stats"] == node["stats"]
    assert found_node["sourcePath"] == node["sourcePath"]
    assert found_node["sourceCommit"] == pin["commit"]

    graph = knowledge.graph()
    path = _step(run, "find_passive_path")["result"]
    assert path["source"] == "pob-knowledge"
    assert path["sourceCommit"] == pin["commit"]
    assert path["nodeIds"] == graph.shortest_path("Scion", life_node_id)
    assert path["nodeIds"][0] == graph.class_start_id("Scion")
    assert path["nodeIds"][-1] == life_node_id
    assert path["nodes"][-1]["stats"] == node["stats"]

    xml = export["result"]["xml"]
    assert export["result"]["source"] == "pob-engine"
    assert "<PathOfBuilding" in xml
    assert FORGED_LIFE not in xml
    assert "Glorious Plate" in xml
    reloaded = tools.invoke("import_build", {"name": "Exported copy", "xml": xml})
    assert reloaded["calculation"]["source"] == "pob-engine"
    assert reloaded["calculation"]["stats"]["Life"] == allocated_life
    assert reloaded["calculation"]["stats"]["Life"] == engine.calculate(allocated_id)["stats"]["Life"]
    assert engine.store.get(import_id)["xml"] == forged
    assert engine.store.get_build(imported["result"]["build"]["id"])["saved_revision_id"] == import_id
