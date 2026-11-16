"""Legality of explicit rare modifiers against the imported modifier rows.

A normal rare (not a jewel and not a graft) has six explicit slots. Path of
Building splits that limit in half, so the item can hold 3 prefixes and 3
suffixes. Item.lua sets the six-slot limit. ItemsTab.lua excludes a modifier
whose group is already on the item, unless the item allows duplicate groups.
A group is that exclusivity only when the imported row has one, and only
inside one modifier file, because each file is its own affix list.

Weights are read from the imported row. This import does not store them.
A missing weight is an error. Nothing here fills one in, and nothing here
turns a weight into a price.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from pob_progression.errors import CraftingError

# Item.lua, rarity RARE, when the item is not a jewel or a graft.
RARE_AFFIX_LIMIT = 6
# ItemsTab.lua: prefixLimit = item.prefixes.limit or (item.affixLimit / 2).
PREFIX_LIMIT = RARE_AFFIX_LIMIT // 2
SUFFIX_LIMIT = RARE_AFFIX_LIMIT // 2
_EXPLICIT_TYPES = {"Prefix", "Suffix"}


@dataclass(frozen=True)
class ModRef:
    mod_id: str
    source_path: str


@dataclass(frozen=True)
class CitedMod:
    mod_id: str
    source_path: str
    mod_type: str | None
    group: str | None
    affix: str | None
    lines: tuple[str, ...]


@dataclass(frozen=True)
class CraftVerdict:
    legal: bool
    rarity: str
    prefix_count: int
    suffix_count: int
    prefix_limit: int
    suffix_limit: int
    reasons: tuple[str, ...]
    mods: tuple[CitedMod, ...]


def check_craft(store, mods: list[ModRef] | tuple[ModRef, ...], *, rarity: str = "rare") -> CraftVerdict:
    """Accept a rare only when the imported types and groups fit the slot rules."""
    if rarity != "rare":
        raise CraftingError("Only a rare's explicit prefix and suffix limits are checked.")
    if not isinstance(mods, (list, tuple)):
        raise CraftingError("A craft needs a list of imported modifiers.")
    cited = tuple(_cite(store, ref) for ref in mods)
    reasons: list[str] = []
    reasons.extend(_duplicate_rows(cited))
    reasons.extend(_untyped(cited))
    prefix_count = sum(1 for mod in cited if mod.mod_type == "Prefix")
    suffix_count = sum(1 for mod in cited if mod.mod_type == "Suffix")
    if prefix_count > PREFIX_LIMIT:
        reasons.append(
            f"A rare allows {PREFIX_LIMIT} prefixes. This selection has {prefix_count}."
        )
    if suffix_count > SUFFIX_LIMIT:
        reasons.append(
            f"A rare allows {SUFFIX_LIMIT} suffixes. This selection has {suffix_count}."
        )
    if len(cited) > RARE_AFFIX_LIMIT:
        reasons.append(
            f"A rare has at most {RARE_AFFIX_LIMIT} explicit modifiers. "
            f"This selection has {len(cited)}."
        )
    if len(cited) == RARE_AFFIX_LIMIT and (prefix_count != PREFIX_LIMIT or suffix_count != SUFFIX_LIMIT):
        reasons.append(
            f"A six-mod rare is impossible with {prefix_count} prefixes and "
            f"{suffix_count} suffixes. The imported types allow "
            f"{PREFIX_LIMIT} prefixes and {SUFFIX_LIMIT} suffixes."
        )
    reasons.extend(_group_conflicts(cited))
    return CraftVerdict(
        legal=not reasons,
        rarity="rare",
        prefix_count=prefix_count,
        suffix_count=suffix_count,
        prefix_limit=PREFIX_LIMIT,
        suffix_limit=SUFFIX_LIMIT,
        reasons=tuple(reasons),
        mods=cited,
    )


def imported_weights(store, mods: list[ModRef] | tuple[ModRef, ...]) -> tuple[dict, ...]:
    """Return weightKey and weightVal stored on each imported row.

    Raises CraftingError when a row has no usable weights. An empty list, a
    missing field, or a key list that does not match the value list is not
    usable. No default weight is substituted.
    """
    if not isinstance(mods, (list, tuple)) or not mods:
        raise CraftingError("Weights need at least one imported modifier.")
    found = []
    for ref in mods:
        row = _row(store, ref)
        weights = _weights(row)
        found.append(
            {
                "modId": row["modId"],
                "sourcePath": row["sourcePath"],
                "weightKey": weights[0],
                "weightVal": weights[1],
            }
        )
    return tuple(found)


def crafting_cost(*_args, **_kwargs) -> None:
    """Prices are not in the imported data. Cost is not estimated from weights."""
    raise CraftingError("Crafting cost is not estimated. The imported data has no prices.")


def _cite(store, ref: ModRef) -> CitedMod:
    row = _row(store, ref)
    mod_type = row.get("modType")
    if not isinstance(mod_type, str):
        mod_type = None
    group = row.get("group")
    if not isinstance(group, str) or not group.strip():
        group = None
    else:
        group = group.strip()
    affix = row.get("affix") if isinstance(row.get("affix"), str) else None
    lines = tuple(line for line in row.get("lines") or [] if isinstance(line, str))
    return CitedMod(
        mod_id=row["modId"],
        source_path=row["sourcePath"],
        mod_type=mod_type,
        group=group,
        affix=affix,
        lines=lines,
    )


def _row(store, ref: ModRef) -> dict:
    if not isinstance(ref, ModRef) or not ref.mod_id.strip() or not ref.source_path.strip():
        raise CraftingError("A modifier needs an imported id and source path.")
    matches = [
        row
        for row in store.mods_by_id(ref.mod_id)
        if row.get("sourcePath") == ref.source_path
    ]
    if not matches:
        raise CraftingError(
            f"Modifier {ref.mod_id} in {ref.source_path} is not in the imported data."
        )
    if len(matches) > 1:
        raise CraftingError(
            f"Modifier {ref.mod_id} in {ref.source_path} matches more than one imported row."
        )
    return matches[0]


def _duplicate_rows(mods: tuple[CitedMod, ...]) -> list[str]:
    seen: dict[tuple[str, str], int] = defaultdict(int)
    for mod in mods:
        seen[(mod.mod_id, mod.source_path)] += 1
    reasons = []
    for (mod_id, source_path), count in sorted(seen.items()):
        if count > 1:
            reasons.append(
                f"Modifier {mod_id} in {source_path} is selected {count} times."
            )
    return reasons


def _untyped(mods: tuple[CitedMod, ...]) -> list[str]:
    reasons = []
    for mod in mods:
        if mod.mod_type not in _EXPLICIT_TYPES:
            reasons.append(
                f"Modifier {mod.mod_id} in {mod.source_path} has no explicit "
                "prefix or suffix type in the import."
            )
    return reasons


def _group_conflicts(mods: tuple[CitedMod, ...]) -> list[str]:
    # The same imported row twice is a duplicate selection, not a second group.
    grouped: dict[tuple[str, str], set[str]] = defaultdict(set)
    for mod in mods:
        if mod.group is None:
            continue
        grouped[(mod.source_path, mod.group)].add(mod.mod_id)
    reasons = []
    for (source_path, group), ids in sorted(grouped.items()):
        if len(ids) < 2:
            continue
        names = ", ".join(sorted(ids))
        reasons.append(f"Modifiers {names} share group {group} in {source_path}.")
    return reasons


def _weights(row: dict) -> tuple[list[str], list[int | float]]:
    key = row.get("weightKey")
    val = row.get("weightVal")
    if (
        isinstance(key, list)
        and isinstance(val, list)
        and key
        and len(key) == len(val)
        and all(isinstance(item, str) and item.strip() for item in key)
        and all(isinstance(item, (int, float)) and not isinstance(item, bool) for item in val)
    ):
        return list(key), list(val)
    raise CraftingError(
        f"Modifier {row.get('modId')} has no weights in the imported data. "
        "Refusing to estimate a weight."
    )
