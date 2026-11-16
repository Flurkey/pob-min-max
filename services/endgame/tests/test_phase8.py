"""Phase 8. Attribute totals come from the engine. Valdo text has no safety verdict."""

import json
import re
import subprocess
from pathlib import Path

import pytest

import pob_endgame
from pob_endgame import (
    ASSUMPTIONS,
    ATTRIBUTE_STATS,
    EndgameError,
    assert_no_safety_claim,
    attribute_stack,
    check_valdo,
)
from pob_engine.examples import LIFE_PLATE
from pob_engine.paths import resolve_paths
from pob_engine.service import EngineService

# Locks for this pin. The engine still calculates them.
BASELINE_LIFE = 60
PLATE_LIFE = 160
BASELINE_ATTRIBUTES = {"Str": 20, "Dex": 20, "Int": 20}
FORGED_STAT = "999999"
ROUND_AFTER_EFFICIENCY = (
    "output[costName] = m_max(0, output[costName] / costEfficiency)\n"
    "\t\t\t\tif val.upfront and not val.percent then\n"
    "\t\t\t\t\t-- The game stores upfront resource costs as whole numbers after efficiency.\n"
    "\t\t\t\t\toutput[costName] = round(output[costName])"
)
_SAFETY_WORD = re.compile(r"\b(?:safe|safely|safety|guaranteed|guarantee|guarantees)\b", re.IGNORECASE)

VALDO_LINES = (
    "Players have -20% to all maximum Resistances",
    "Players have no Armour",
    "Players have 40% less Evasion",
    "Players have no Energy Shield",
    "Players are Crushed",
    "Players are Cursed with Elemental Weakness",
    "Players cannot gain Flask Charges",
    "Players cannot Leech Life or Mana",
    "Players have 90% less Recovery Rate of Life and Energy Shield",
    "Players have 60% less Maximum Life",
    "Players cannot Block",
    "Players have no Spell Suppression",
    "Monsters deal 100% of Physical Damage as Extra Chaos Damage",
    "Monsters always Ignite",
    "Monsters' hits cannot be Evaded",
    "Monsters always deal Critical Strikes",
    "Monsters have 50% increased Area of Effect",
    "This map is guaranteed safe",
)
VALDO_EXPECTED = (
    ("maximum-resistances",),
    ("armour",),
    ("evasion",),
    ("energy-shield",),
    ("physical-damage-reduction",),
    ("resistances",),
    ("flasks",),
    ("leech",),
    ("recovery",),
    ("life",),
    ("block",),
    ("spell-suppression",),
    ("damage-taken-as",),
    ("ailments",),
    ("evasion",),
    ("incoming-crits",),
    (),
    (),
)


@pytest.fixture(scope="module")
def paths():
    return resolve_paths()


@pytest.fixture(scope="module")
def engine():
    running = EngineService.start()
    try:
        yield running
    finally:
        running.close()


def _fixture_xml() -> str:
    return resolve_paths().fixture.read_text(encoding="utf-8")


def _forge_cached_stats(xml: str) -> str:
    """Rewrite the saved stat cache. The engine is not allowed to read it back."""
    replacements = {
        'stat="Life" value="60"': 'stat="Life" value="999999"',
        'stat="Str" value="20"': 'stat="Str" value="999999"',
        'stat="Dex" value="20"': 'stat="Dex" value="999999"',
        'stat="Int" value="20"': 'stat="Int" value="999999"',
    }
    forged = xml
    for old, new in replacements.items():
        assert forged.count(old) == 1, old
        forged = forged.replace(old, new, 1)
    return forged


def _assessment_text(result: dict) -> str:
    parts = [str(result["engineCalculated"])]
    for row in result["invalidated"]:
        parts.append(row["id"])
        parts.append(row["assumption"])
    for row in result["uncertain"]:
        parts.append(row["reason"])
    return "\n".join(parts)


def test_attribute_stack_reports_the_engine_and_leaves_the_import(engine, paths):
    assert paths.pin["measured"]["baselineLife"] == BASELINE_LIFE
    assert paths.pin["measured"]["lifeAfterFlat100"] == PLATE_LIFE
    original = _fixture_xml()
    imported = engine.import_xml(original, "Phase 8 Scion")
    import_id = imported["revision"]["id"]
    build_id = imported["build"]["id"]
    assert imported["calculation"]["source"] == "pob-engine"
    assert imported["calculation"]["stats"]["Life"] == BASELINE_LIFE
    assert engine.store.get(import_id)["xml"] == original

    result = attribute_stack(engine, build_id, import_id)
    copy = result["copy"]["revision"]
    copy_id = copy["id"]
    assert result["sourceBuildId"] == build_id
    assert result["parentId"] == import_id
    assert result["savedRevisionId"] == import_id
    assert copy["buildId"] != build_id
    assert copy["parentId"] == import_id
    assert copy["status"] == "saved"
    assert copy["label"] == "attributes"
    assert result["copy"]["build"]["name"] == "Phase 8 Scion (attributes)"
    assert result["copy"]["build"]["savedRevisionId"] == copy_id
    assert engine.store.get(copy_id)["xml"] == original
    assert engine.store.get(import_id)["xml"] == original
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id
    source_ids = {row["id"] for row in engine.history(build_id)["revisions"]}
    assert import_id in source_ids
    assert copy_id not in source_ids

    fresh_copy = engine.calculate(copy_id)
    fresh_import = engine.calculate(import_id)
    assert result["calculation"]["source"] == "pob-engine"
    assert result["calculation"]["ignoredStoredPlayerStat"] is True
    assert result["calculation"]["stats"] == fresh_copy["stats"]
    assert result["calculation"]["engineRevision"] == fresh_copy["engineRevision"]
    assert result["calculation"]["engineRevision"] == paths.pin["commit"]
    assert result["attributes"] == BASELINE_ATTRIBUTES
    for name in ATTRIBUTE_STATS:
        assert name in fresh_copy["stats"]
        assert result["attributes"][name] == fresh_copy["stats"][name]
        assert result["attributes"][name] == fresh_import["stats"][name]
        assert result["attributes"][name] == BASELINE_ATTRIBUTES[name]
        assert result["attributes"][name] != int(FORGED_STAT)
    assert fresh_import["stats"]["Life"] == BASELINE_LIFE
    assert engine.store.get(import_id)["xml"] == original

    forged_xml = _forge_cached_stats(original)
    assert 'stat="Str" value="999999"' in forged_xml
    assert 'stat="Life" value="999999"' in forged_xml
    forged = engine.import_xml(forged_xml, "Phase 8 forged cache")
    forged_id = forged["revision"]["id"]
    forged_build = forged["build"]["id"]
    forged_report = attribute_stack(engine, forged_build, forged_id)
    forged_copy = forged_report["copy"]["revision"]["id"]
    forged_engine = engine.calculate(forged_copy)
    assert forged_report["calculation"]["source"] == "pob-engine"
    assert forged_report["calculation"]["stats"] == forged_engine["stats"]
    for name in ATTRIBUTE_STATS:
        assert forged_report["attributes"][name] == forged_engine["stats"][name]
        assert forged_report["attributes"][name] != int(FORGED_STAT)
    assert forged_engine["stats"]["Life"] == BASELINE_LIFE
    assert engine.store.get(forged_id)["xml"] == forged_xml
    assert engine.store.get(import_id)["xml"] == original
    assert engine.calculate(import_id)["stats"]["Life"] == BASELINE_LIFE

    equipped = engine.equip(copy_id, LIFE_PLATE, "Body Armour")
    assert equipped["revision"]["buildId"] == copy["buildId"]
    assert equipped["calculation"]["source"] == "pob-engine"
    assert equipped["calculation"]["stats"]["Life"] == PLATE_LIFE
    assert engine.store.get(import_id)["xml"] == original
    assert engine.store.get(copy_id)["xml"] == original
    assert engine.calculate(import_id)["stats"]["Life"] == BASELINE_LIFE
    assert engine.calculate(import_id)["stats"]["Str"] == result["attributes"]["Str"]


def test_valdo_lists_invalidated_assumptions_and_marks_the_rest_uncertain():
    result = check_valdo("\n".join(VALDO_LINES))
    assert_no_safety_claim(result)
    assert result["supplied"] == list(VALDO_LINES)
    assert result["engineCalculated"] is False
    assert "verdict" not in result
    assert "safe" not in result
    assert "guaranteed" not in result
    by_index: dict[int, list[str]] = {}
    for row in result["invalidated"]:
        by_index.setdefault(row["modifierIndex"], []).append(row["id"])
        assert row["assumption"] == ASSUMPTIONS[row["id"]]
        assert row["modifier"] == VALDO_LINES[row["modifierIndex"]]
        assert _SAFETY_WORD.search(row["assumption"]) is None
        assert _SAFETY_WORD.search(row["id"]) is None
    uncertain = {row["modifierIndex"]: row for row in result["uncertain"]}
    for index, expected in enumerate(VALDO_EXPECTED):
        if expected:
            assert tuple(by_index[index]) == expected
            assert index not in uncertain
        else:
            assert index not in by_index
            assert uncertain[index]["modifier"] == VALDO_LINES[index]
            assert uncertain[index]["reason"].endswith("uncertain.")
            assert _SAFETY_WORD.search(uncertain[index]["reason"]) is None
    assert _SAFETY_WORD.search(_assessment_text(result)) is None

    current = check_valdo("Players have -20% to all Resistances")
    assert [row["id"] for row in current["invalidated"]] == ["resistances"]
    assert current["uncertain"] == []
    armour = check_valdo(["Players have 40% less Armour", "Monsters have 50% increased Armour"])
    assert [row["id"] for row in armour["invalidated"]] == ["armour"]
    assert armour["invalidated"][0]["modifier"] == "Players have 40% less Armour"
    assert armour["uncertain"][0]["modifier"] == "Monsters have 50% increased Armour"
    assert_no_safety_claim(current)
    assert_no_safety_claim(armour)


def test_valdo_result_that_says_the_map_is_safe_is_rejected():
    samples = [
        "Players have no Armour",
        "Monsters have 50% increased Area of Effect",
        "This map is guaranteed safe",
        "The map is safe",
        list(VALDO_LINES),
    ]
    for sample in samples:
        result = check_valdo(sample)
        assert_no_safety_claim(result)
        assert result["engineCalculated"] is False
        assert "verdict" not in result
        assert _SAFETY_WORD.search(_assessment_text(result)) is None
        encoded = json.dumps(
            {
                "invalidated": [
                    {"id": row["id"], "assumption": row["assumption"]}
                    for row in result["invalidated"]
                ],
                "uncertain": [{"reason": row["reason"]} for row in result["uncertain"]],
                "engineCalculated": result["engineCalculated"],
            }
        )
        assert _SAFETY_WORD.search(encoded) is None

    supplied = ["Players have no Armour"]
    quoted = {
        "id": "armour",
        "assumption": ASSUMPTIONS["armour"],
        "modifierIndex": 0,
        "modifier": supplied[0],
    }
    for verdict in ("safe", "The map is safe", "guaranteed", "guaranteed safe"):
        with pytest.raises(EndgameError, match="must not say the map is safe"):
            assert_no_safety_claim(
                {
                    "supplied": supplied,
                    "invalidated": [quoted],
                    "uncertain": [],
                    "engineCalculated": False,
                    "verdict": verdict,
                }
            )
    with pytest.raises(EndgameError, match="must not say the map is safe"):
        assert_no_safety_claim(
            {
                "supplied": supplied,
                "invalidated": [{**quoted, "assumption": "The map is safe."}],
                "uncertain": [],
                "engineCalculated": False,
            }
        )
    with pytest.raises(EndgameError, match="needs the modifier text"):
        check_valdo("")
    with pytest.raises(EndgameError, match="needs the modifier text"):
        check_valdo("  \n\t")
    with pytest.raises(EndgameError, match="needs the modifier text"):
        check_valdo(["Players have no Armour", 1])


def test_package_does_not_call_a_model_or_drop_the_cost_round(paths):
    assert paths.pin["commit"] == "e5917f81fd64c10d9bc816c410da395ed18e57ba"
    root = Path(pob_endgame.__file__).resolve().parent
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    folded = text.casefold()
    for token in ("openai", "anthropic", "httpx", "urllib", "requests", "poe.ninja", "pathofexile.com"):
        assert token not in folded
    assert "999999" not in text
    offence = (paths.src / "Modules" / "CalcOffence.lua").read_text(encoding="utf-8")
    assert offence.count(ROUND_AFTER_EFFICIENCY) == 2
    status = subprocess.run(
        ["git", "-C", str(paths.src.parent), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip() == ""
