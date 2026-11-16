"""Phase 7. Stage copies use the library. Crafting uses imported modifiers."""

import subprocess
from pathlib import Path

import pytest

import pob_progression
from pob_engine.errors import EngineError
from pob_engine.examples import LIFE_PLATE
from pob_engine.paths import resolve_paths as resolve_engine_paths
from pob_engine.service import EngineService
from pob_knowledge.paths import resolve_paths as resolve_knowledge_paths
from pob_knowledge.store import KnowledgeStore
from pob_progression import (
    PREFIX_LIMIT,
    RARE_AFFIX_LIMIT,
    STAGES,
    SUFFIX_LIMIT,
    CraftingError,
    ModRef,
    check_craft,
    crafting_cost,
    imported_weights,
    progression_copies,
)
from pob_progression.crafting import CraftVerdict

# Locks for this pin. The engine still calculates them; these fail the test
# if this checkout returns something else.
BASELINE_LIFE = 60
PLATE_LIFE = 160
EXPLICIT = "Data/ModExplicit.lua"
WATCHER = "Data/Uniques/Special/WatchersEye.lua"
ROUND_AFTER_EFFICIENCY = (
    "output[costName] = m_max(0, output[costName] / costEfficiency)\n"
    "\t\t\t\tif val.upfront and not val.percent then\n"
    "\t\t\t\t\t-- The game stores upfront resource costs as whole numbers after efficiency.\n"
    "\t\t\t\t\toutput[costName] = round(output[costName])"
)
# mod id, group, type, a line that row must contain
LEGAL_PREFIXES = (
    ("IncreasedLife1", "IncreasedLife", "Prefix", "+(10-24) to maximum Life"),
    ("IncreasedMana1", "IncreasedMana", "Prefix", "+(15-19) to maximum Mana"),
    ("IncreasedEnergyShield1", "EnergyShield", "Prefix", "+(1-3) to maximum Energy Shield"),
)
LEGAL_SUFFIXES = (
    ("Strength1", "Strength", "Suffix", "+(8-12) to Strength"),
    ("Dexterity1", "Dexterity", "Suffix", "+(8-12) to Dexterity"),
    ("Intelligence1", "Intelligence", "Suffix", "+(8-12) to Intelligence"),
)
EXTRA_PREFIXES = (
    ("AddedFireDamage1", "FireDamage", "Prefix", "Adds 1 to 2 Fire Damage to Attacks"),
    ("AddedColdDamage1", "ColdDamage", "Prefix", "Adds 1 to 2 Cold Damage to Attacks"),
    ("MovementVelocity1", "MovementVelocity", "Prefix", "10% increased Movement Speed"),
)


@pytest.fixture(scope="module")
def paths():
    return resolve_knowledge_paths()


@pytest.fixture(scope="module")
def store(tmp_path_factory, paths):
    database = tmp_path_factory.mktemp("progression") / "knowledge.sqlite"
    running = KnowledgeStore(database)
    running.import_checkout(paths)
    try:
        yield running
    finally:
        running.close()


@pytest.fixture(scope="module")
def engine():
    running = EngineService.start()
    try:
        yield running
    finally:
        running.close()


def _fixture_xml() -> str:
    return resolve_engine_paths().fixture.read_text(encoding="utf-8")


def _explicit(store, mod_id: str) -> dict:
    rows = [row for row in store.mods_by_id(mod_id) if row["sourcePath"] == EXPLICIT]
    assert len(rows) == 1, mod_id
    return rows[0]


def _ref(mod_id: str) -> ModRef:
    return ModRef(mod_id, EXPLICIT)


def _require_imported(store, spec: tuple[str, str, str, str]) -> dict:
    mod_id, group, mod_type, line = spec
    row = _explicit(store, mod_id)
    assert row["modType"] == mod_type
    assert row["group"] == group
    assert line in row["lines"]
    assert "weightKey" not in row
    assert "weightVal" not in row
    return row


def test_rare_slot_rule_matches_the_pinned_item_code(paths):
    item = (paths.src / "Classes" / "Item.lua").read_text(encoding="utf-8")
    rare_limit = (
        'self.affixLimit = (((self.type == "Jewel" and not '
        '(self.base.subType == "Abyss" and self.corrupted)) or self.type == "Graft") and 4 or 6)'
    )
    assert rare_limit in item
    tab = (paths.src / "Classes" / "ItemsTab.lua").read_text(encoding="utf-8")
    assert "local prefixLimit = item.prefixes.limit or (item.affixLimit / 2)" in tab
    assert "if mod.group and not allowDuplicateGroups then" in tab
    assert RARE_AFFIX_LIMIT == 6
    assert PREFIX_LIMIT == 3
    assert SUFFIX_LIMIT == 3


def test_three_prefixes_and_three_suffixes_are_legal(store, paths):
    specs = LEGAL_PREFIXES + LEGAL_SUFFIXES
    for spec in specs:
        row = _require_imported(store, spec)
        assert row["sourceCommit"] == paths.pin["commit"]
    verdict = check_craft(store, [_ref(spec[0]) for spec in specs])
    assert verdict.legal is True
    assert verdict.rarity == "rare"
    assert verdict.reasons == ()
    assert verdict.prefix_count == PREFIX_LIMIT
    assert verdict.suffix_count == SUFFIX_LIMIT
    assert "cost" not in CraftVerdict.__dataclass_fields__
    assert "weight" not in CraftVerdict.__dataclass_fields__
    assert len(verdict.mods) == 6
    for cited, spec in zip(verdict.mods, specs, strict=True):
        row = _explicit(store, spec[0])
        assert cited.mod_id == row["modId"]
        assert cited.source_path == row["sourcePath"]
        assert cited.mod_type == row["modType"]
        assert cited.group == row["group"]
        assert spec[3] in cited.lines
        assert cited.lines == tuple(line for line in row["lines"] if isinstance(line, str))


def test_shared_group_is_rejected_when_the_row_has_one(store):
    left = _require_imported(store, LEGAL_SUFFIXES[0])
    right = _explicit(store, "Strength2")
    assert right["modType"] == "Suffix"
    assert right["group"] == left["group"] == "Strength"
    verdict = check_craft(store, [_ref("Strength1"), _ref("Strength2")])
    assert verdict.legal is False
    assert verdict.suffix_count == 2
    assert verdict.suffix_count <= verdict.suffix_limit
    assert verdict.prefix_count == 0
    assert any(
        reason == "Modifiers Strength1, Strength2 share group Strength in Data/ModExplicit.lua."
        for reason in verdict.reasons
    )
    different = check_craft(store, [_ref("Strength1"), _ref("Dexterity1")])
    assert different.legal is True
    assert different.reasons == ()

    full = LEGAL_PREFIXES + (
        ("Strength1", "Strength", "Suffix", "+(8-12) to Strength"),
        ("Strength2", "Strength", "Suffix", "+(13-17) to Strength"),
        LEGAL_SUFFIXES[1],
    )
    _require_imported(store, full[4])
    crowded = check_craft(store, [_ref(spec[0]) for spec in full])
    assert crowded.prefix_count == 3
    assert crowded.suffix_count == 3
    assert crowded.legal is False
    assert any("share group Strength" in reason for reason in crowded.reasons)
    assert not any("six-mod rare is impossible" in reason for reason in crowded.reasons)


def test_six_prefixes_and_a_four_two_split_are_impossible(store):
    six_specs = LEGAL_PREFIXES + EXTRA_PREFIXES
    for spec in six_specs:
        _require_imported(store, spec)
    six = check_craft(store, [_ref(spec[0]) for spec in six_specs])
    assert six.legal is False
    assert six.prefix_count == 6
    assert six.suffix_count == 0
    assert any(
        "A six-mod rare is impossible with 6 prefixes and 0 suffixes." in reason
        for reason in six.reasons
    )
    assert any("A rare allows 3 prefixes. This selection has 6." in reason for reason in six.reasons)
    assert all("1000" not in reason for reason in six.reasons)

    split_specs = LEGAL_PREFIXES + EXTRA_PREFIXES[:1] + LEGAL_SUFFIXES[:2]
    split = check_craft(store, [_ref(spec[0]) for spec in split_specs])
    assert split.prefix_count == 4
    assert split.suffix_count == 2
    assert len(split.mods) == 6
    assert split.legal is False
    assert any(
        "A six-mod rare is impossible with 4 prefixes and 2 suffixes." in reason
        for reason in split.reasons
    )
    assert any("A rare allows 3 prefixes. This selection has 4." in reason for reason in split.reasons)


def test_missing_type_unknown_mod_and_a_duplicate_fail_closed(store):
    rows = store.mods_by_id("ClarityReducedManaCost")
    assert len(rows) == 1
    watcher = rows[0]
    assert watcher["sourcePath"] == WATCHER
    assert "modType" not in watcher
    assert "-(10-5) to Total Mana Cost of Skills while affected by Clarity" in watcher["lines"]
    untyped = check_craft(store, [ModRef("ClarityReducedManaCost", WATCHER)])
    assert untyped.legal is False
    assert untyped.mods[0].mod_type is None
    assert untyped.prefix_count == 0
    assert untyped.suffix_count == 0
    assert any("no explicit prefix or suffix type" in reason for reason in untyped.reasons)

    with pytest.raises(CraftingError, match="not in the imported data"):
        check_craft(store, [ModRef("NotARealMod", EXPLICIT)])
    with pytest.raises(CraftingError, match="not in the imported data"):
        check_craft(store, [ModRef("Strength1", "Data/ModFlask.lua")])
    with pytest.raises(CraftingError, match="Only a rare"):
        check_craft(store, [_ref("Strength1")], rarity="magic")

    duplicate = check_craft(store, [_ref("Strength1"), _ref("Strength1")])
    assert duplicate.legal is False
    assert duplicate.suffix_count == 2
    assert any(
        "Modifier Strength1 in Data/ModExplicit.lua is selected 2 times." in reason
        for reason in duplicate.reasons
    )
    assert not any("share group" in reason for reason in duplicate.reasons)


def test_missing_weights_and_cost_fail_closed(store, paths):
    row = _require_imported(store, LEGAL_SUFFIXES[0])
    source = (paths.src / "Data" / "ModExplicit.lua").read_text(encoding="utf-8")
    start = source.index('["Strength1"]')
    chunk = source[start : source.index("\n", start)]
    assert "weightKey" in chunk
    assert "weightVal" in chunk
    assert "weightKey" not in row
    assert "weightVal" not in row
    with pytest.raises(CraftingError, match="no weights in the imported data"):
        imported_weights(store, [ModRef("Strength1", EXPLICIT)])
    with pytest.raises(CraftingError, match="no prices"):
        crafting_cost(store, [ModRef("Strength1", EXPLICIT)])
    watcher = store.mods_by_id("ClarityReducedManaCost")[0]
    assert "weightKey" not in watcher
    with pytest.raises(CraftingError, match="no weights"):
        imported_weights(store, [ModRef(watcher["modId"], watcher["sourcePath"])])


def test_stage_copies_leave_the_imported_build(engine, paths):
    assert paths.pin["measured"]["baselineLife"] == BASELINE_LIFE
    assert paths.pin["measured"]["lifeAfterFlat100"] == PLATE_LIFE
    original = _fixture_xml()
    imported = engine.import_xml(original, "Phase 7 Scion")
    import_id = imported["revision"]["id"]
    build_id = imported["build"]["id"]
    assert imported["calculation"]["source"] == "pob-engine"
    assert imported["calculation"]["stats"]["Life"] == BASELINE_LIFE
    assert engine.store.get(import_id)["xml"] == original

    with pytest.raises(EngineError, match="needs a name"):
        engine.library_copy(build_id, import_id, name="  ", label="campaign")
    assert engine.store.get(import_id)["xml"] == original
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id

    other = engine.import_xml(original, "Phase 7 other")
    with pytest.raises(EngineError, match="different build"):
        engine.library_copy(build_id, other["revision"]["id"], name="Nope", label="campaign")
    assert engine.store.get(import_id)["xml"] == original

    assert STAGES == ("campaign", "early maps", "endgame")
    result = progression_copies(engine, build_id, import_id)
    assert result["sourceBuildId"] == build_id
    assert result["parentId"] == import_id
    assert result["savedRevisionId"] == import_id
    assert [stage["stage"] for stage in result["stages"]] == list(STAGES)
    copy_ids = []
    copy_builds = []
    for stage in result["stages"]:
        revision = stage["revision"]
        assert revision["id"] not in copy_ids
        assert revision["buildId"] != build_id
        assert revision["buildId"] not in copy_builds
        assert revision["parentId"] == import_id
        assert revision["status"] == "saved"
        assert revision["label"] == stage["stage"]
        assert stage["build"]["id"] == revision["buildId"]
        assert stage["build"]["savedRevisionId"] == revision["id"]
        assert stage["build"]["name"] == f"Phase 7 Scion ({stage['stage']})"
        assert engine.store.get(revision["id"])["xml"] == original
        copy_ids.append(revision["id"])
        copy_builds.append(revision["buildId"])

    assert engine.store.get(import_id)["xml"] == original
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id
    source_history = {row["id"] for row in engine.history(build_id)["revisions"]}
    assert import_id in source_history
    assert not source_history & set(copy_ids)
    names = {row["name"] for row in engine.library()}
    for stage_name in STAGES:
        assert f"Phase 7 Scion ({stage_name})" in names

    assert engine.calculate(import_id)["stats"]["Life"] == BASELINE_LIFE
    campaign_id = copy_ids[0]
    campaign_build = copy_builds[0]
    campaign_calc = engine.calculate(campaign_id)
    assert campaign_calc["source"] == "pob-engine"
    assert campaign_calc["stats"]["Life"] == BASELINE_LIFE
    assert engine.store.get(import_id)["xml"] == original

    equipped = engine.equip(campaign_id, LIFE_PLATE, "Body Armour")
    assert equipped["revision"]["buildId"] == campaign_build
    assert equipped["revision"]["status"] == "draft"
    assert equipped["build"]["savedRevisionId"] == campaign_id
    assert equipped["calculation"]["source"] == "pob-engine"
    assert equipped["calculation"]["stats"]["Life"] == PLATE_LIFE
    assert engine.store.get(import_id)["xml"] == original
    assert engine.store.get_build(build_id)["saved_revision_id"] == import_id
    assert engine.calculate(import_id)["stats"]["Life"] == BASELINE_LIFE
    assert engine.store.get(campaign_id)["xml"] == original
    assert engine.store.get(copy_ids[1])["xml"] == original
    assert engine.store.get(copy_ids[2])["xml"] == original

    again = progression_copies(engine, build_id)
    assert again["savedRevisionId"] == import_id
    assert {stage["revision"]["id"] for stage in again["stages"]}.isdisjoint(copy_ids)
    assert engine.store.get(import_id)["xml"] == original
    assert engine.calculate(import_id)["stats"]["Life"] == BASELINE_LIFE


def test_package_does_not_invent_weights_or_drop_the_cost_round(store, paths):
    assert store.provenance()["sourceCommit"] == paths.pin["commit"]
    root = Path(pob_progression.__file__).resolve().parent
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    folded = text.casefold()
    for token in ("openai", "anthropic", "httpx", "urllib", "requests", "poe.ninja", "pathofexile.com"):
        assert token not in folded
    assert "1000" not in text
    offence = (paths.src / "Modules" / "CalcOffence.lua").read_text(encoding="utf-8")
    assert offence.count(ROUND_AFTER_EFFICIENCY) == 2
    status = subprocess.run(
        ["git", "-C", str(paths.checkout), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout.strip() == ""
