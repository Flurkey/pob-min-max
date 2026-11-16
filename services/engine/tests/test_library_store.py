import pytest

from pob_engine.store import BuildStore


def test_drafts_do_not_replace_the_stored_revision(tmp_path):
    store = BuildStore(tmp_path / "library.sqlite")
    original_xml = "<PathOfBuilding><Build className=\"Scion\"/></PathOfBuilding>"
    saved = store.create(
        name="Library Scion",
        xml=original_xml,
        label="import",
        engine_revision="e5917f81",
        tree_version="3_30",
        status="saved",
    )
    draft_xml = "<PathOfBuilding><Build className=\"Scion\"/><Items>edited</Items></PathOfBuilding>"
    draft = store.create(
        name="Library Scion",
        xml=draft_xml,
        label="equipment",
        parent_id=saved["id"],
        build_id=saved["build_id"],
        engine_revision="e5917f81",
        tree_version="3_30",
        status="draft",
    )

    assert store.get(saved["id"])["xml"] == original_xml
    assert store.get_build(saved["build_id"])["saved_revision_id"] == saved["id"]
    assert draft["status"] == "draft"
    assert draft["id"] != saved["id"]

    stored = store.create(
        name="Library Scion",
        xml=draft_xml,
        label="save",
        parent_id=draft["id"],
        build_id=saved["build_id"],
        engine_revision="e5917f81",
        tree_version="3_30",
        status="saved",
    )
    assert store.get(saved["id"])["xml"] == original_xml
    assert store.get(draft["id"])["xml"] == draft_xml
    assert store.get_build(saved["build_id"])["saved_revision_id"] == stored["id"]

    history = store.list_revisions(saved["build_id"])
    assert [row["label"] for row in history] == ["import", "equipment", "save"]
    assert store.list_builds("Library")[0]["id"] == saved["build_id"]
    assert store.list_builds("100%") == []

    leaf = store.create(
        name="Library Scion",
        xml=original_xml,
        label="copy",
        parent_id=saved["id"],
        build_id=saved["build_id"],
        engine_revision="e5917f81",
        tree_version="3_30",
        status="draft",
    )
    store.delete_draft(leaf["id"])
    assert store.get(saved["id"])["xml"] == original_xml
    with pytest.raises(KeyError):
        store.get(leaf["id"])
    with pytest.raises(ValueError, match="stored build"):
        store.delete_draft(stored["id"])
    with pytest.raises(ValueError, match="unsaved working copy"):
        store.delete_draft(saved["id"])
    with pytest.raises(ValueError, match="later revisions"):
        store.delete_draft(draft["id"])
    store.close()
