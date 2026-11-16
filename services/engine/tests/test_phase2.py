import re
import subprocess
import xml.etree.ElementTree as ET

import pytest
from fastapi.testclient import TestClient

from pob_engine.api import create_app
from pob_engine.errors import EngineError
from pob_engine.examples import LIFE_PLATE
from pob_engine.paths import resolve_paths
from pob_engine.service import require_pob_xml

# Same pin locks as Phase 1. The test still runs the engine; these numbers only
# fail the build if this checkout calculates something else.
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


def test_library_ignores_path_of_building_save_files(service):
    decoy_dir = service.process.user_dir / "Builds"
    decoy_dir.mkdir(parents=True, exist_ok=True)
    (decoy_dir / "Decoy.xml").write_text("<PathOfBuilding><Build className=\"Decoy\"/></PathOfBuilding>", encoding="utf-8")
    pob_src = resolve_paths().src.resolve()
    library = service.store.path.resolve()
    assert library.suffix == ".sqlite"
    assert service.process.user_dir.resolve() not in library.parents
    assert pob_src not in library.parents
    assert all(row["name"] != "Decoy" for row in service.library())

    status = subprocess.run(
        ["git", "-C", str(pob_src.parent), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip() == ""


def test_import_edit_recalculate_save_and_export(service):
    original = _fixture_xml()
    imported = service.import_xml(original, "Phase 2 Scion")
    import_id = imported["revision"]["id"]
    build_id = imported["build"]["id"]
    assert imported["build"]["savedRevisionId"] == import_id
    assert imported["revision"]["status"] == "saved"
    assert imported["calculation"]["source"] == "pob-engine"
    assert imported["calculation"]["stats"]["Life"] == BASELINE_LIFE
    assert imported["summary"]["source"] == "pob-engine"
    assert imported["summary"]["className"] == "Scion"
    assert service.store.get(import_id)["xml"] == original

    with pytest.raises(EngineError, match="already the stored"):
        service.save(import_id)
    assert service.store.get(import_id)["xml"] == original

    copied = service.copy(build_id, import_id)
    copy_id = copied["revision"]["id"]
    assert copied["revision"]["status"] == "draft"
    assert copied["build"]["savedRevisionId"] == import_id
    assert service.store.get(copy_id)["xml"] == original
    assert service.store.get(import_id)["xml"] == original

    equipped = service.equip(copy_id, LIFE_PLATE, "Body Armour")
    equip_id = equipped["revision"]["id"]
    assert equipped["revision"]["status"] == "draft"
    assert equipped["build"]["savedRevisionId"] == import_id
    assert equipped["calculation"]["stats"]["Life"] == PLATE_LIFE
    assert equipped["comparison"]["source"] == "pob-engine"
    assert equipped["comparison"]["focus"]["Life"]["delta"] == PLATE_LIFE - BASELINE_LIFE
    assert any(item["baseName"] == "Glorious Plate" for item in equipped["summary"]["equipped"])
    assert service.store.get(import_id)["xml"] == original
    assert service.store.get(copy_id)["xml"] == original
    assert service.calculate(import_id)["stats"]["Life"] == BASELINE_LIFE

    allocated = service.allocate(equip_id)
    passive_id = allocated["revision"]["id"]
    assert allocated["passive"]["id"] == LIFE_NODE_ID
    assert allocated["calculation"]["stats"]["Life"] == PASSIVE_LIFE
    assert allocated["build"]["savedRevisionId"] == import_id
    assert service.store.get(import_id)["xml"] == original
    equip_xml = service.store.get(equip_id)["xml"]

    inspected = service.inspect(import_id)
    assert inspected["saved"] is True
    assert inspected["calculation"]["source"] == "pob-engine"
    assert inspected["calculation"]["stats"]["Life"] == BASELINE_LIFE
    assert inspected["summary"]["className"] == "Scion"
    assert inspected["summary"]["equipped"] == []

    edited = service.inspect(passive_id)
    assert edited["saved"] is False
    assert edited["calculation"]["stats"]["Life"] == PASSIVE_LIFE
    assert isinstance(edited["summary"]["allocatedPoints"], int)
    assert any(item["baseName"] == "Glorious Plate" for item in edited["summary"]["equipped"])

    saved = service.save(passive_id)
    saved_id = saved["revision"]["id"]
    assert saved["build"]["savedRevisionId"] == saved_id
    assert saved["savedFromId"] == passive_id
    assert saved["calculation"]["source"] == "pob-engine"
    assert saved["calculation"]["stats"]["Life"] == PASSIVE_LIFE
    assert service.store.get(import_id)["xml"] == original
    assert service.store.get(equip_id)["xml"] == equip_xml
    assert service.store.get(passive_id)["xml"] != original
    assert service.store.get_build(build_id)["saved_revision_id"] == saved_id

    labels = [row["label"] for row in service.history(build_id)["revisions"]]
    assert labels == ["import", "copy", "equipment", "passive", "save"]

    compared = service.compare(import_id, saved_id)
    assert compared["source"] == "pob-engine"
    assert compared["focus"]["Life"] == {
        "left": BASELINE_LIFE,
        "right": PASSIVE_LIFE,
        "delta": PASSIVE_LIFE - BASELINE_LIFE,
    }

    exported = service.export_xml(saved_id)
    require_pob_xml(exported)
    root = ET.fromstring(exported)
    assert root.tag == "PathOfBuilding"
    assert "Glorious Plate" in exported
    assert "+100 to maximum Life" in exported
    assert str(LIFE_NODE_ID) in _spec_nodes(exported)
    assert service.store.get(import_id)["xml"] == original
    assert service.store.get(saved_id)["xml"] != ""

    reloaded = service.import_xml(exported, "Phase 2 export")
    assert reloaded["calculation"]["stats"]["Life"] == saved["calculation"]["stats"]["Life"]
    assert reloaded["calculation"]["stats"]["Life"] == PASSIVE_LIFE

    extra = service.copy(build_id)
    assert extra["build"]["savedRevisionId"] == saved_id
    discarded = service.discard(extra["revision"]["id"])
    assert discarded["build"]["savedRevisionId"] == saved_id
    assert service.store.get(import_id)["xml"] == original
    with pytest.raises(EngineError, match="stored build"):
        service.discard(saved_id)
    with pytest.raises(EngineError, match="unsaved working copy"):
        service.discard(import_id)


def test_http_library_history_save_and_export(service):
    with TestClient(create_app(service)) as client:
        created = client.post("/api/builds", json={"name": "HTTP library", "xml": _fixture_xml()})
        assert created.status_code == 200
        body = created.json()
        build_id = body["build"]["id"]
        import_id = body["revision"]["id"]
        assert body["calculation"]["stats"]["Life"] == BASELINE_LIFE

        listed = client.get("/api/library", params={"q": "HTTP library"})
        assert listed.status_code == 200
        payload = listed.json()
        assert payload["storage"] == "sqlite"
        assert payload["builds"][0]["savedRevisionId"] == import_id

        copied = client.post(f"/api/library/{build_id}/copies", json={"revisionId": import_id})
        assert copied.status_code == 200
        copy_id = copied.json()["revision"]["id"]
        assert copied.json()["build"]["savedRevisionId"] == import_id

        equipped = client.post(
            f"/api/builds/{copy_id}/equipment",
            json={"text": LIFE_PLATE, "slot": "Body Armour"},
        )
        assert equipped.status_code == 200
        equip_body = equipped.json()
        assert equip_body["build"]["savedRevisionId"] == import_id
        assert equip_body["calculation"]["stats"]["Life"] == PLATE_LIFE

        history = client.get(f"/api/library/{build_id}")
        assert history.status_code == 200
        assert [row["label"] for row in history.json()["revisions"]] == ["import", "copy", "equipment"]

        saved = client.post(f"/api/builds/{equip_body['revision']['id']}/save")
        assert saved.status_code == 200
        saved_body = saved.json()
        assert saved_body["build"]["savedRevisionId"] == saved_body["revision"]["id"]
        assert saved_body["calculation"]["stats"]["Life"] == PLATE_LIFE

        blocked = client.post(f"/api/builds/{import_id}/discard")
        assert blocked.status_code == 400

        exported = client.get(f"/api/builds/{saved_body['revision']['id']}/export")
        assert exported.status_code == 200
        xml = exported.json()["xml"]
        assert ET.fromstring(xml).tag == "PathOfBuilding"
        assert "Glorious Plate" in xml

        inspected = client.post(f"/api/builds/{import_id}/inspect")
        assert inspected.status_code == 200
        assert inspected.json()["calculation"]["stats"]["Life"] == BASELINE_LIFE
        assert inspected.json()["saved"] is False
        current = client.post(f"/api/builds/{saved_body['revision']['id']}/inspect")
        assert current.status_code == 200
        assert current.json()["saved"] is True
        assert current.json()["calculation"]["stats"]["Life"] == PLATE_LIFE

        compared = client.post(
            "/api/compare",
            json={"leftRevisionId": import_id, "rightRevisionId": saved_body["revision"]["id"]},
        )
        assert compared.status_code == 200
        assert compared.json()["source"] == "pob-engine"
        assert compared.json()["focus"]["Life"]["delta"] == PLATE_LIFE - BASELINE_LIFE
