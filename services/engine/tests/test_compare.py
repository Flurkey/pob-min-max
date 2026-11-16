import pytest

from pob_engine.compare import compare_calculations


def test_compare_rejects_stats_that_did_not_come_from_the_engine():
    fresh = {"source": "pob-engine", "stats": {"Life": 60}, "level": 1}
    cached = {"source": "xml-player-stat", "stats": {"Life": 999999}}
    with pytest.raises(ValueError, match="not a fresh"):
        compare_calculations(cached, fresh, "left", "right")


def test_compare_reports_the_engine_delta():
    left = {"source": "pob-engine", "stats": {"Life": 60, "Mana": 40}, "level": 1, "engineRevision": "abc", "treeVersion": "3_30"}
    right = {"source": "pob-engine", "stats": {"Life": 160, "Mana": 40}, "level": 1, "engineRevision": "abc", "treeVersion": "3_30"}
    result = compare_calculations(left, right, "a", "b")
    assert result["source"] == "pob-engine"
    assert result["focus"]["Life"]["delta"] == 100
    assert result["changedCount"] == 1
    assert result["changed"][0]["stat"] == "Life"
