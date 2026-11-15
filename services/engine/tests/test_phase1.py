import json
import re

import pytest
from fastapi.testclient import TestClient

from pob_engine.api import create_app
from pob_engine.errors import EngineError
from pob_engine.examples import LIFE_PLATE
from pob_engine.paths import resolve_paths
from pob_engine.xml_cache import stored_player_stats

# Measured against PathOfBuilding dev e5917f81 on 2026-11-15. The assertions
# below still execute the engine; these numbers only lock that revision.
BASELINE_LIFE = 60
PLATE_LIFE = 160
PASSIVE_LIFE = 256
LIFE_NODE_ID = 15073


def _fixture_xml() -> str:
    return resolve_paths().fixture.read_text(encoding="utf-8")


def _spec_nodes(xml: str) -> set[str]:
    match = re.search(r'<Spec\b[^>]*\snodes="([^"]*)"', xml)
    assert match, "exported build has no passive spec"
    return set(match.group(1).split(","))


def test_running_engine_matches_the_pinned_revision(service):
    paths = resolve_paths()
    info = service.engine_info()
    assert info["engineRevision"] == paths.pin["commit"]
    assert info["revisionMatchesPin"] is True
    assert info["latestTreeVersion"] == "3_30"
    assert info["latestTreeDisplay"] == "3.30"
    assert info["versionNumber"] == "2.67.2"
    assert info["devMode"] is True
    assert info["className"] == "Scion"


def test_stored_player_stat_is_not_used_as_the_calculation(service):
    original = _fixture_xml()
    assert stored_player_stats(original)["Life"] == "60"
    forged = original.replace('stat="Life" value="60"', 'stat="Life" value="999999"', 1)
    assert stored_player_stats(forged)["Life"] == "999999"
    imported = service.import_xml(forged, "Forged Scion")
    assert imported["calculation"]["source"] == "pob-engine"
    assert imported["calculation"]["ignoredStoredPlayerStat"] is True
    assert imported["calculation"]["stats"]["Life"] == BASELINE_LIFE
    assert imported["calculation"]["level"] == 1
    assert imported["calculation"]["treeVersion"] == "3_30"


def test_poisoned_calculation_cache_is_not_returned(service):
    imported = service.import_xml(_fixture_xml(), "Cache Scion")
    revision_id = imported["revision"]["id"]
    service.store.conn.execute(
        "UPDATE calculations SET stats_json = ? WHERE revision_id = ?",
        (json.dumps({"Life": 1}), revision_id),
    )
    service.store.conn.commit()
    assert service.store.latest_cached_stats(revision_id)["Life"] == 1
    fresh = service.calculate(revision_id)
    assert fresh["stats"]["Life"] == BASELINE_LIFE


def test_equipment_passive_compare_and_export_round_trip(service):
    imported = service.import_xml(_fixture_xml(), "Scion baseline")
    parent_id = imported["revision"]["id"]
    assert imported["calculation"]["stats"]["Life"] == BASELINE_LIFE

    equipped = service.equip(parent_id, LIFE_PLATE, "Body Armour")
    assert equipped["equipment"]["baseName"] == "Glorious Plate"
    assert equipped["equipment"]["slot"] == "Body Armour"
    assert "+100 to maximum Life" in equipped["equipment"]["explicitLines"]
    assert equipped["calculation"]["stats"]["Life"] == PLATE_LIFE
    assert equipped["comparison"]["source"] == "pob-engine"
    assert equipped["comparison"]["focus"]["Life"] == {
        "left": BASELINE_LIFE,
        "right": PLATE_LIFE,
        "delta": 100,
    }

    allocated = service.allocate(equipped["revision"]["id"])
    assert allocated["passive"]["id"] == LIFE_NODE_ID
    assert allocated["passive"]["name"] == "Life"
    assert "maximum Life" in allocated["passive"]["text"]
    assert allocated["passive"]["allocatedAfter"] > allocated["passive"]["allocatedBefore"]
    assert allocated["calculation"]["stats"]["Life"] == PASSIVE_LIFE
    assert allocated["comparison"]["focus"]["Life"]["delta"] == PASSIVE_LIFE - PLATE_LIFE
    assert allocated["calculation"]["level"] >= 1

    xml = service.export_xml(allocated["revision"]["id"])
    assert xml.startswith("<?xml")
    assert "<PathOfBuilding>" in xml
    assert "Glorious Plate" in xml
    assert "+100 to maximum Life" in xml
    assert str(LIFE_NODE_ID) in _spec_nodes(xml)
    assert 'stat="Life" value="999999"' not in xml

    reloaded = service.import_xml(xml, "Round trip")
    assert reloaded["calculation"]["stats"]["Life"] == PASSIVE_LIFE
    assert float(stored_player_stats(xml)["Life"]) == PASSIVE_LIFE
    assert reloaded["calculation"]["engineRevision"] == resolve_paths().pin["commit"]


def test_invalid_item_and_unknown_passive_roll_back(service):
    imported = service.import_xml(_fixture_xml(), "Rollback Scion")
    revision_id = imported["revision"]["id"]
    with pytest.raises(EngineError, match="item base"):
        service.equip(
            revision_id,
            "Rarity: Rare\nNope\nNot A Real Base\n--------\n+10 to maximum Life\n",
            "Body Armour",
        )
    assert service.calculate(revision_id)["stats"]["Life"] == BASELINE_LIFE
    with pytest.raises(EngineError, match="not found"):
        service.allocate(revision_id, node_id=999999999)
    assert service.calculate(revision_id)["stats"]["Life"] == BASELINE_LIFE
    assert service.store.get(revision_id)["label"] == "import"


def test_build_search_uses_sqlite_fts(service):
    imported = service.import_xml(_fixture_xml(), "Searchable Scion")
    found = service.search("Searchable")
    assert imported["revision"]["id"] in {row["id"] for row in found}


def test_http_api_imports_equips_and_exports(service):
    forged = _fixture_xml().replace('stat="Life" value="60"', 'stat="Life" value="999999"', 1)
    with TestClient(create_app(service)) as client:
        health = client.get("/api/engine")
        assert health.status_code == 200
        assert health.json()["latestTreeVersion"] == "3_30"
        assert health.json()["revisionMatchesPin"] is True

        created = client.post("/api/builds", json={"name": "API Scion", "xml": forged})
        assert created.status_code == 200
        body = created.json()
        assert body["calculation"]["stats"]["Life"] == BASELINE_LIFE
        revision_id = body["revision"]["id"]

        equipped = client.post(
            f"/api/builds/{revision_id}/equipment",
            json={"text": LIFE_PLATE, "slot": "Body Armour"},
        )
        assert equipped.status_code == 200
        assert equipped.json()["calculation"]["stats"]["Life"] == PLATE_LIFE

        exported = client.get(f"/api/builds/{equipped.json()['revision']['id']}/export")
        assert exported.status_code == 200
        assert "Glorious Plate" in exported.json()["xml"]

        missing = client.post("/api/builds/does-not-exist/calculate")
        assert missing.status_code == 404
