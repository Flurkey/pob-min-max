import json
import subprocess
from collections import deque
from dataclasses import replace
from datetime import datetime, timezone

import pytest

from pob_knowledge.errors import DisconnectedAllocation, KnowledgeError, PointBudgetExceeded
from pob_knowledge.paths import assert_checkout_matches_pin, resolve_paths
from pob_knowledge.store import KnowledgeStore

# Counts and stat lines read from the pinned checkout. They fail if the importer
# drops records or substitutes a different tree. They are not values the store invents.
PINNED_COUNTS = {
    "itemBases": 1106,
    "uniques": 1318,
    "gems": 824,
    "mods": 24336,
    "nodes": 2916,
    "edges": 3275,
}
LIFE_NODE_ID = 15073
LIFE_STAT = "5% increased maximum Life"


@pytest.fixture(scope="module")
def paths():
    return resolve_paths()


@pytest.fixture(scope="module")
def store(tmp_path_factory, paths):
    database = tmp_path_factory.mktemp("knowledge") / "knowledge.sqlite"
    running = KnowledgeStore(database)
    running.import_checkout(paths)
    try:
        yield running
    finally:
        running.close()


@pytest.fixture(scope="module")
def graph(store):
    return store.graph()


def _provenance(record: dict, paths) -> None:
    pin = paths.pin
    assert record["source"] == "PathOfBuildingCommunity/PathOfBuilding"
    assert record["sourceCommit"] == pin["commit"]
    assert record["sourceUrl"] == f"https://github.com/PathOfBuildingCommunity/PathOfBuilding/tree/{pin['commit']}"
    assert record["gameVersion"] == pin["latestTreeDisplay"] == "3.30"
    assert record["treeVersion"] == pin["latestTreeVersion"] == "3_30"
    assert record["manifestVersion"] == pin["manifestVersion"] == "2.67.2"
    assert record["gameVersion"] != record["manifestVersion"]
    assert record["retrievalDate"] == datetime.now(timezone.utc).date().isoformat()


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


def _ascendancy_order(graph, class_name: str, ascendancy: str) -> list[int]:
    start = graph.ascendancy_start_id(class_name, ascendancy)
    ascendancy_id = graph.nodes[start].ascendancy_name
    seen = {start}
    queue: deque[int] = deque([start])
    order: list[int] = []
    while queue:
        current = queue.popleft()
        if graph.nodes[current].node_type == "Mastery":
            continue
        for neighbor in graph.neighbors(current):
            if neighbor in seen:
                continue
            node = graph.nodes[neighbor]
            if node.ascendancy_name != ascendancy_id:
                continue
            seen.add(neighbor)
            order.append(neighbor)
            if node.node_type != "Mastery":
                queue.append(neighbor)
    return order


def test_checkout_matches_the_pin_and_a_different_commit_is_refused(paths):
    assert_checkout_matches_pin(paths)
    forged = replace(paths, pin={**paths.pin, "commit": "0" * 40})
    with pytest.raises(KnowledgeError, match="does not match the pin"):
        assert_checkout_matches_pin(forged)


def test_import_records_provenance_and_the_pinned_counts(store, paths):
    record = store.provenance()
    _provenance(record, paths)
    assert record["counts"] == PINNED_COUNTS


def test_item_base_and_unique_come_from_the_checkout(store, paths):
    plate = store.item_base("Glorious Plate")
    _provenance(plate, paths)
    assert plate["sourcePath"] == "Data/Bases/body.lua"
    assert plate["itemType"] == "Body Armour"
    assert plate["req"] == {"level": 68, "str": 191}
    assert plate["armour"] == {"ArmourBaseMin": 776, "ArmourBaseMax": 892}
    assert "implicit" not in plate

    hearts = store.unique_items("Kaom's Heart")
    assert len(hearts) == 1
    heart = hearts[0]
    _provenance(heart, paths)
    assert heart["baseName"] == "Glorious Plate"
    assert heart["sourcePath"] == "Data/Uniques/body.lua"
    assert "{variant:1,3}+1000 to maximum Life" in heart["rawText"]

    with pytest.raises(KeyError):
        store.item_base("Not A Real Glorious Plate")
    assert store.unique_items("Not A Real Glorious Plate") == []


def test_skill_gems_keep_their_granted_effects(store, paths):
    kinetic = store.gem("Kinetic Blast")
    _provenance(kinetic, paths)
    assert kinetic["sourcePath"] == "Data/Gems.lua"
    assert kinetic["id"] == "Metadata/Items/Gems/SkillGemKineticBlast"
    assert kinetic["grantedEffectId"] == "KineticBlast"
    assert kinetic["tagString"] == "Attack, Projectile, AoE"
    assert kinetic["reqInt"] == 100
    effect = kinetic["grantedEffect"]
    assert effect["sourcePath"] == "Data/Skills/act_int.lua"
    assert effect["description"].startswith("Fires a projectile from a Wand")
    assert {"Attack", "Projectile", "Area"} <= set(effect["skillTypes"])
    assert effect["weaponTypes"] == ["Wand"]
    assert effect["support"] is False
    level_one = next(level for level in effect["levels"] if level["level"] == 1)
    level_twenty = next(level for level in effect["levels"] if level["level"] == 20)
    assert level_one["levelRequirement"] == 28
    assert level_one["cost"] == {"Mana": 6}
    assert level_twenty["levelRequirement"] == 70

    inspiration = store.gem("Inspiration")
    assert inspiration["grantedEffect"]["support"] is True
    assert inspiration["reqStr"] == 60
    assert inspiration["tagString"] == "Critical, Support"
    assert "support_inspiration_mana_cost_+%_final" in inspiration["grantedEffect"]["stats"]
    assert inspiration["grantedEffect"]["sourcePath"] == "Data/Skills/sup_str.lua"

    with pytest.raises(KeyError):
        store.gem("Not A Real Gem")


def test_watchers_eye_mod_text_is_imported(store, paths):
    text = "-(10-5) to Total Mana Cost of Skills while affected by Clarity"
    mods = store.mods_with_text(text)
    assert len(mods) == 1
    mod = mods[0]
    _provenance(mod, paths)
    assert mod["sourcePath"] == "Data/Uniques/Special/WatchersEye.lua"
    assert mod["modId"] == "ClarityReducedManaCost"
    assert text in mod["lines"]


def test_passive_node_and_search_use_the_tree_file(store, graph, paths):
    life = store.node(LIFE_NODE_ID)
    _provenance(life, paths)
    assert life["name"] == "Life"
    assert life["stats"] == [LIFE_STAT]
    assert life["sourcePath"] == f"TreeData/{paths.pin['latestTreeVersion']}/tree.lua"
    assert graph.node(LIFE_NODE_ID).stats == (LIFE_STAT,)

    found = store.search("Kinetic Blast")
    assert any(row["kind"] == "gem" and row["name"] == "Kinetic Blast" for row in found)
    _provenance(found[0], paths)
    bases = store.search("Glorious Plate")
    assert any(row["kind"] == "item-base" and row["name"] == "Glorious Plate" for row in bases)


def test_passive_graph_rejects_disconnected_allocations(graph):
    start = graph.class_start_id("Scion")
    assert graph.nodes[start].class_start_index == 0
    assert graph.nodes[start].node_type == "ClassStart"
    assert LIFE_NODE_ID not in graph.neighbors(start)

    empty = graph.validate("Scion", [])
    assert empty["regularPoints"] == 0
    assert empty["classStartId"] == start

    neighbor = next(node_id for node_id in graph.neighbors(start) if graph.allocation_kind(node_id) == "regular")
    connected = graph.validate("Scion", [neighbor])
    assert connected["regularPoints"] == 1

    path = graph.shortest_path("Scion", LIFE_NODE_ID)
    assert path[0] == start
    assert path[-1] == LIFE_NODE_ID
    assert len(path) > 2
    allocated = graph.validate("Scion", path[1:])
    assert allocated["regularPoints"] == len(path) - 1
    assert LIFE_NODE_ID in allocated["nodeIds"]

    without_bridge = [node_id for node_id in path[1:] if node_id != path[-2]]
    assert not any(node_id in without_bridge for node_id in graph.neighbors(LIFE_NODE_ID))
    with pytest.raises(DisconnectedAllocation):
        graph.validate("Scion", without_bridge)
    with pytest.raises(DisconnectedAllocation):
        graph.validate("Scion", [LIFE_NODE_ID])

    start_neighbors = set(graph.neighbors(start))
    pair = None
    for node_id, node in graph.nodes.items():
        if node.ascendancy_name or node.node_type == "ClassStart" or node_id in start_neighbors:
            continue
        for other in graph.neighbors(node_id):
            other_node = graph.nodes[other]
            if other_node.ascendancy_name or other_node.node_type != "Normal":
                continue
            if other in start_neighbors or other == start:
                continue
            pair = (node_id, other)
            break
        if pair:
            break
    assert pair is not None
    with pytest.raises(DisconnectedAllocation):
        graph.validate("Scion", list(pair))

    mastery = next(
        node.node_id
        for node in graph.nodes.values()
        if node.node_type == "Mastery" and node.ascendancy_name is None and node.node_id not in start_neighbors
    )
    with pytest.raises(DisconnectedAllocation):
        graph.validate("Scion", [mastery])

    with pytest.raises(KnowledgeError, match="Unknown passive node"):
        graph.validate("Scion", [999_999_999])
    with pytest.raises(KnowledgeError, match="integer"):
        graph.validate("Scion", ["15073"])


def test_passive_graph_enforces_the_tree_point_budget(graph):
    assert graph.regular_budget == 123
    assert graph.ascendancy_budget == 8
    regular = _connected_regular(graph, "Scion", 124)
    assert len(regular) == 124
    with pytest.raises(PointBudgetExceeded, match="124 passive points"):
        graph.validate("Scion", regular)
    allowed = graph.validate("Scion", regular[:123])
    assert allowed["regularPoints"] == 123
    assert allowed["regularBudget"] == 123

    order = _ascendancy_order(graph, "Marauder", "Juggernaut")
    prefixes: dict[int, list[int]] = {}
    spent = 0
    for index, node_id in enumerate(order, start=1):
        if graph.allocation_kind(node_id) == "ascendancy":
            spent += 1
            prefixes.setdefault(spent, order[:index])
    assert graph.validate("Marauder", prefixes[8], ascendancy="Juggernaut")["ascendancyPoints"] == 8
    with pytest.raises(PointBudgetExceeded, match="9 ascendancy points"):
        graph.validate("Marauder", prefixes[9], ascendancy="Juggernaut")

    start = graph.ascendancy_start_id("Marauder", "Juggernaut")
    distant = next(node_id for node_id in prefixes[9] if node_id not in graph.neighbors(start))
    with pytest.raises(DisconnectedAllocation):
        graph.validate("Marauder", [distant], ascendancy="Juggernaut")
    with pytest.raises(KnowledgeError, match="not the selected ascendancy"):
        graph.validate("Marauder", [distant])
    with pytest.raises(KnowledgeError, match="not an ascendancy of Witch"):
        graph.validate("Witch", [], ascendancy="Juggernaut")


def test_import_does_not_modify_the_checkout_or_the_cost_round(store, paths):
    # The fixture has already imported. The checkout is still the pinned tree.
    assert store.provenance()["sourceCommit"] == paths.pin["commit"]
    status = subprocess.run(
        ["git", "-C", str(paths.checkout), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip() == ""
    offence = (paths.src / "Modules" / "CalcOffence.lua").read_text(encoding="utf-8")
    round_after_efficiency = (
        "output[costName] = m_max(0, output[costName] / costEfficiency)\n"
        "\t\t\t\tif val.upfront and not val.percent then\n"
        "\t\t\t\t\t-- The game stores upfront resource costs as whole numbers after efficiency.\n"
        "\t\t\t\t\toutput[costName] = round(output[costName])"
    )
    assert offence.count(round_after_efficiency) == 2


def test_manifest_version_is_read_from_the_checkout(paths):
    pin = json.loads(paths.pin_path.read_text(encoding="utf-8"))
    assert pin["commit"].startswith("e5917f81")
    assert pin["manifestVersion"] == "2.67.2"
    assert pin["latestTreeVersion"] == "3_30"
