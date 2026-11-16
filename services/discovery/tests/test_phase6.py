"""Phase 6 reads chains and conflicts from the imported unique and modifier rows."""

import re
from collections import defaultdict
from pathlib import Path

import pytest

import pob_discovery
from pob_discovery import (
    Citation,
    DiscoveryError,
    assert_known,
    clean_line,
    discover,
)
from pob_knowledge.paths import resolve_paths
from pob_knowledge.store import KnowledgeStore


@pytest.fixture(scope="module")
def paths():
    return resolve_paths()


@pytest.fixture(scope="module")
def store(tmp_path_factory, paths):
    database = tmp_path_factory.mktemp("discovery") / "knowledge.sqlite"
    running = KnowledgeStore(database)
    running.import_checkout(paths)
    try:
        yield running
    finally:
        running.close()


@pytest.fixture(scope="module")
def found(store):
    return discover(store)


@pytest.fixture(scope="module")
def indexed(store):
    uniques = defaultdict(list)
    for row in store.all_uniques():
        uniques[(row["name"], row["sourcePath"])].append(row)
    mods = defaultdict(list)
    for row in store.all_mods():
        mods[(row["modId"], row["sourcePath"])].append(row)
    return uniques, mods


def _mod_text(row: dict) -> str:
    return "\n".join(line for line in row["lines"] if isinstance(line, str))


def _assert_cited(indexed, step: Citation) -> dict:
    uniques, mods = indexed
    if step.kind == "unique":
        rows = uniques.get((step.name, step.source_path))
        assert rows, f"{step.name} is not an imported unique"
        match = next((row for row in rows if step.excerpt in row["rawText"]), None)
        assert match is not None, f"{step.name} does not contain the cited excerpt"
        return match
    if step.kind == "mod":
        rows = mods.get((step.name, step.source_path))
        assert rows, f"{step.name} is not an imported modifier"
        match = next((row for row in rows if step.excerpt in _mod_text(row)), None)
        assert match is not None, f"{step.name} does not contain the cited excerpt"
        return match
    raise AssertionError(step.kind)


def test_package_does_not_calculate_or_call_a_model():
    root = Path(pob_discovery.__file__).resolve().parent
    text = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py")).casefold()
    for banned in ("pob_engine", "openai", "anthropic", "httpx", "urllib", "requests"):
        assert banned not in text


def test_every_chain_cites_imported_text(found, indexed):
    assert found.chains
    links = {chain.link for chain in found.chains}
    assert links == {"also-applies", "for-every", "per-stat", "grants"}
    assert any(chain.steps[0].name != chain.steps[1].name for chain in found.chains)
    for chain in found.chains:
        assert len(chain.steps) >= 2
        assert chain.via.casefold() in chain.reason.casefold()
        rows = [_assert_cited(indexed, step) for step in chain.steps]
        assert rows
        needle = chain.via.casefold()
        for step in chain.steps:
            assert needle in step.excerpt.casefold()
        source = clean_line(chain.steps[0].excerpt)
        consumer = clean_line(chain.steps[1].excerpt)
        via = re.escape(chain.via)
        if chain.link == "also-applies":
            assert re.search(rf"\b(?:increased|reduced)\s+{via}\b", source, re.IGNORECASE)
            assert re.search(r"\balso apply to\b", consumer, re.IGNORECASE)
        elif chain.link == "for-every":
            assert re.search(rf"\b(?:increased|reduced|to)\s+{via}\b", source, re.IGNORECASE)
            assert re.search(rf"\bfor every\s+\d+%\s+your\s+{via}\s+is\b", consumer, re.IGNORECASE)
        elif chain.link == "per-stat":
            assert re.search(rf"\b(?:increased|reduced|to)\s+{via}\b", source, re.IGNORECASE)
            assert re.search(rf"\bper\s+\d+\s+{via}\b", consumer, re.IGNORECASE)
        else:
            assert re.search(r"\b(?:grants|triggers?) level \d+", source, re.IGNORECASE)
            assert (
                re.search(
                    rf"\bwhile (?:affected by|you are using|using) {via}$",
                    consumer,
                    re.IGNORECASE,
                )
                or re.match(rf"affected by {via}$", consumer, re.IGNORECASE)
                or re.match(rf"{via} has\b", consumer, re.IGNORECASE)
            )


def test_unknown_citation_is_rejected(store, found):
    real = found.chains[0].steps[0]
    assert_known(store, found.chains[0].steps)
    with pytest.raises(DiscoveryError, match="not an imported unique"):
        assert_known(
            store,
            (
                Citation(
                    kind="unique",
                    name="Not A Real Unique",
                    source_path=real.source_path,
                    excerpt=real.excerpt,
                ),
            ),
        )
    with pytest.raises(DiscoveryError, match="not an imported modifier"):
        assert_known(
            store,
            (
                Citation(
                    kind="mod",
                    name="NotARealMod",
                    source_path="Data/ModExplicit.lua",
                    excerpt="+(8-12) to Dexterity",
                ),
            ),
        )
    with pytest.raises(DiscoveryError, match="Unknown citation kind"):
        Citation(
            kind="gem",
            name="Kinetic Blast",
            source_path="Data/Gems.lua",
            excerpt="Kinetic Blast",
        )
    with pytest.raises(DiscoveryError, match="empty"):
        assert_known(store, ())


def test_excerpt_must_belong_to_the_cited_row(store, found):
    donor = next(step for chain in found.chains for step in chain.steps if step.kind == "unique")
    host = None
    for chain in found.chains:
        for step in chain.steps:
            if step.kind != "unique" or step.name == donor.name:
                continue
            rows = store.unique_items(step.name)
            owned = [row for row in rows if row["sourcePath"] == step.source_path]
            if owned and donor.excerpt not in owned[0]["rawText"]:
                host = step
                break
        if host is not None:
            break
    assert host is not None
    forged = Citation(
        kind="unique",
        name=host.name,
        source_path=host.source_path,
        excerpt=donor.excerpt,
    )
    with pytest.raises(DiscoveryError, match="not an imported unique"):
        assert_known(store, (forged,))


def test_status_conflict_is_in_the_import(found, indexed):
    status = [conflict for conflict in found.conflicts if conflict.kind == "status"]
    assert status
    for conflict in status:
        assert len(conflict.steps) == 2
        _assert_cited(indexed, conflict.steps[0])
        _assert_cited(indexed, conflict.steps[1])
        ban = clean_line(conflict.steps[0].excerpt)
        need = clean_line(conflict.steps[1].excerpt)
        via = re.escape(conflict.via)
        assert re.match(rf"(?:you )?cannot be {via}$", ban, re.IGNORECASE)
        assert re.search(rf"\bwhile {via}\b", need, re.IGNORECASE)
        assert conflict.via.casefold() in conflict.steps[0].excerpt.casefold()
        assert conflict.via.casefold() in conflict.steps[1].excerpt.casefold()


def test_mod_group_conflict_uses_the_group_field(found, indexed):
    grouped = [conflict for conflict in found.conflicts if conflict.kind == "mod-group"]
    assert grouped
    for conflict in grouped:
        assert len(conflict.steps) >= 2
        assert len({step.name for step in conflict.steps}) >= 2
        sources = set()
        for step in conflict.steps:
            row = _assert_cited(indexed, step)
            assert row.get("group") == conflict.via
            sources.add(step.source_path)
            assert step.excerpt in _mod_text(row)
        assert sources == {conflict.steps[0].source_path}


def test_variant_and_version_conflicts_quote_the_unique(found, indexed):
    variants = [conflict for conflict in found.conflicts if conflict.kind == "variant"]
    versions = [conflict for conflict in found.conflicts if conflict.kind == "version"]
    assert variants
    assert versions
    for conflict in variants:
        assert len(conflict.steps) >= 2
        row = None
        for step in conflict.steps:
            row = _assert_cited(indexed, step)
            assert step.name == conflict.via
            assert clean_line(step.excerpt).startswith("Variant:")
            assert step.excerpt in row["rawText"]
        assert row is not None
        assert "Has Alt Variant:" not in row["rawText"]
    for conflict in versions:
        assert len(conflict.steps) >= 2
        for step in conflict.steps:
            row = _assert_cited(indexed, step)
            assert step.name == conflict.via
            assert clean_line(step.excerpt).startswith("Version:")
            assert step.excerpt in row["rawText"]


def test_aura_disable_conflict_names_two_imported_mods(found, indexed):
    disabled = [conflict for conflict in found.conflicts if conflict.kind == "aura-disabled"]
    assert disabled
    for conflict in disabled:
        assert len(conflict.steps) == 2
        ban = _assert_cited(indexed, conflict.steps[0])
        need = _assert_cited(indexed, conflict.steps[1])
        assert ban["modId"] != need["modId"] or ban["sourcePath"] != need["sourcePath"]
        ban_line = clean_line(conflict.steps[0].excerpt)
        need_line = clean_line(conflict.steps[1].excerpt)
        match = re.match(r"aura skills other than (.+) are disabled$", ban_line, re.IGNORECASE)
        assert match is not None
        assert match.group(1).casefold() != conflict.via.casefold()
        via = re.escape(conflict.via)
        assert re.search(
            rf"\bwhile (?:affected by|you are using|using) {via}$",
            need_line,
            re.IGNORECASE,
        ) or re.match(rf"affected by {via}$", need_line, re.IGNORECASE)


def test_minion_stat_is_not_the_characters_stat(found, indexed):
    # Imported minion lines are real. They do not establish the character's stat.
    _uniques, mods = indexed
    assert any(
        re.search(r"minions have\b.*\bincreased cast speed\b", _mod_text(row), re.IGNORECASE)
        for rows in mods.values()
        for row in rows
    )
    for chain in found.chains:
        if chain.link == "grants":
            continue
        source = clean_line(chain.steps[0].excerpt)
        assert not re.match(r"(?:minions|allies|totems|golems) have\b", source, re.IGNORECASE)


def test_cited_rows_keep_the_pin(found, indexed, paths):
    chain = next(item for item in found.chains if item.link == "grants")
    for step in chain.steps:
        row = _assert_cited(indexed, step)
        assert row["source"] == "PathOfBuildingCommunity/PathOfBuilding"
        assert row["sourceCommit"] == paths.pin["commit"]
        assert row["treeVersion"] == paths.pin["latestTreeVersion"]
    group = next(item for item in found.conflicts if item.kind == "mod-group")
    row = _assert_cited(indexed, group.steps[0])
    assert row["sourceCommit"] == paths.pin["commit"]
