"""Defensive assumptions a user-supplied Valdo modifier puts aside.

Each line is matched against phrases that contradict a defensive assumption
of the build calculation. A line that matches none of those phrases is
uncertain. This module does not calculate a map, and it does not produce a
safety verdict.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

from pob_endgame.errors import EndgameError

# Generated text is checked against these words. User-supplied modifier text
# is stored separately and is not rewritten.
_SAFETY_WORD = re.compile(r"\b(?:safe|safely|safety|guaranteed|guarantee|guarantees)\b", re.IGNORECASE)
_SAFETY_KEY = frozenset(
    {"safe", "safely", "safety", "guaranteed", "guarantee", "guarantees", "verdict"}
)

ASSUMPTIONS: dict[str, str] = {
    "maximum-resistances": "Maximum resistances are the values in the build calculation.",
    "resistances": "Resistances apply as in the build calculation, with no extra curse or penetration.",
    "armour": "Armour is the value in the build calculation.",
    "physical-damage-reduction": "Physical damage reduction is the value in the build calculation.",
    "evasion": "Evasion applies to attacks as in the build calculation.",
    "energy-shield": "Energy Shield is the value in the build calculation.",
    "life": "Maximum life is the value in the build calculation.",
    "block": "Block chance applies as in the build calculation.",
    "spell-suppression": "Spell suppression applies as in the build calculation.",
    "flasks": "Flasks can be used and can gain charges as configured on the build.",
    "leech": "Leech applies as in the build calculation.",
    "recovery": "Life, mana, and Energy Shield recovery apply as in the build calculation.",
    "damage-taken-as": "Incoming damage keeps the types assumed by the build calculation.",
    "ailments": "Ailments on the character are only those configured on the build.",
    "incoming-crits": "Incoming critical strikes follow the build calculation.",
}

_UNCERTAIN_REASON = (
    "This modifier is not mapped to a defensive assumption. "
    "Its effect on the build calculation is uncertain."
)

_MONSTER_LINE = re.compile(
    r"^\s*(?:monsters?|unique bosses?|bosses?|rare monsters?)\b",
    re.IGNORECASE,
)
_PLAYER_WORD = re.compile(r"\b(?:players?|you)\b", re.IGNORECASE)
_MAXIMUM_RESIST = re.compile(r"\bmax(?:imum)? resistances?\b", re.IGNORECASE)
_RESISTANCE_SHIFT = re.compile(
    r"\b(?:cursed with|are cursed|penetrat\w+|ignores? .{0,40}resistances?)\b"
    r"|\b-?\d+% to (?:all |fire |cold |lightning |chaos )?(?:elemental )?resistances?\b",
    re.IGNORECASE,
)
_EXTRA_DAMAGE = re.compile(
    r"\b(?:as extra|damage taken as|damage as (?:fire|cold|lightning|chaos))\b",
    re.IGNORECASE,
)
_CRIT = re.compile(r"\bcritical strikes?\b|\balways crit", re.IGNORECASE)
_CRUSHED = re.compile(r"\bcrushed\b", re.IGNORECASE)
_AILMENT = re.compile(
    r"\b(?:players?|you) are (?:frozen|shocked|ignited|chilled|poisoned|bleeding)\b"
    r"|\balways (?:freeze|ignite|shock|poison|bleed|chill)s?\b",
    re.IGNORECASE,
)
_CANNOT_EVADE = re.compile(
    r"\b(?:hits? can(?:not|'t) be evaded|always hit)\b",
    re.IGNORECASE,
)
_QUOTE_KEYS = frozenset({"modifier"})


def check_valdo(text: str | Sequence[str]) -> dict:
    """List invalidated defensive assumptions for modifier text the user supplied."""
    supplied = _lines(text)
    invalidated: list[dict] = []
    uncertain: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for index, line in enumerate(supplied):
        matched = _assumptions_for(line)
        if not matched:
            uncertain.append(
                {
                    "modifierIndex": index,
                    "modifier": line,
                    "reason": _UNCERTAIN_REASON,
                }
            )
            continue
        for assumption_id in matched:
            key = (assumption_id, index)
            if key in seen:
                continue
            seen.add(key)
            invalidated.append(
                {
                    "id": assumption_id,
                    "assumption": ASSUMPTIONS[assumption_id],
                    "modifierIndex": index,
                    "modifier": line,
                }
            )
    result = {
        "supplied": list(supplied),
        "invalidated": invalidated,
        "uncertain": uncertain,
        "engineCalculated": False,
    }
    assert_no_safety_claim(result)
    return result


def assert_no_safety_claim(result: dict) -> None:
    """Reject a result that states a safety verdict.

    The supplied modifier lines are the user's text. Every other string is
    this module's wording and must not call the map safe or guaranteed.
    """
    if not isinstance(result, dict):
        raise EndgameError("A Valdo result must not say the map is safe.")
    supplied = result.get("supplied")
    if not isinstance(supplied, list) or not all(isinstance(line, str) for line in supplied):
        raise EndgameError("A Valdo result must quote the supplied modifier.")
    for key in result:
        if not isinstance(key, str) or key.casefold() in _SAFETY_KEY or _SAFETY_WORD.search(key):
            raise EndgameError("A Valdo result must not say the map is safe.")
    _scan_rows(result.get("invalidated"), supplied, require_assumption=True)
    _scan_rows(result.get("uncertain"), supplied, require_assumption=False)
    for key, value in result.items():
        if key in {"supplied", "invalidated", "uncertain"}:
            continue
        _reject_safety_value(value)


def _lines(text: str | Sequence[str]) -> tuple[str, ...]:
    if isinstance(text, str):
        raw = text.splitlines()
    elif isinstance(text, Sequence) and not isinstance(text, (bytes, bytearray)):
        raw = list(text)
    else:
        raise EndgameError("A Valdo check needs the modifier text.")
    lines: list[str] = []
    for line in raw:
        if not isinstance(line, str):
            raise EndgameError("A Valdo check needs the modifier text.")
        cleaned = line.strip()
        if cleaned:
            lines.append(cleaned)
    if not lines:
        raise EndgameError("A Valdo check needs the modifier text.")
    return tuple(lines)


def _assumptions_for(line: str) -> tuple[str, ...]:
    found: list[str] = []

    def add(assumption_id: str) -> None:
        if assumption_id not in found:
            found.append(assumption_id)

    monster_only = _MONSTER_LINE.search(line) is not None and _PLAYER_WORD.search(line) is None
    if _EXTRA_DAMAGE.search(line):
        add("damage-taken-as")
    if _CRIT.search(line):
        add("incoming-crits")
    if _AILMENT.search(line):
        add("ailments")
    if _CANNOT_EVADE.search(line):
        add("evasion")
    if not monster_only and _MAXIMUM_RESIST.search(line):
        add("maximum-resistances")
    elif _RESISTANCE_SHIFT.search(line):
        add("resistances")
    if monster_only:
        return tuple(found)

    if re.search(r"\bno armour\b|\bless armour\b|\breduced armour\b", line, re.IGNORECASE):
        add("armour")
    if _CRUSHED.search(line) or re.search(r"\bphysical damage reduction\b", line, re.IGNORECASE):
        add("physical-damage-reduction")
    if re.search(
        r"\bno evasion\b|\bless evasion\b|\breduced evasion\b|\bcannot evade\b",
        line,
        re.IGNORECASE,
    ):
        add("evasion")
    if re.search(
        r"\bno energy shield\b|\bless energy shield\b|\breduced energy shield\b",
        line,
        re.IGNORECASE,
    ) and not re.search(r"\brecovery\b|\brecharge\b|\bregenerat", line, re.IGNORECASE):
        add("energy-shield")
    if re.search(r"\bmaximum life\b|\bno life\b", line, re.IGNORECASE) and not re.search(
        r"\brecovery\b|\bleech\b|\bregenerat",
        line,
        re.IGNORECASE,
    ):
        add("life")
    if re.search(r"\bblock\b", line, re.IGNORECASE):
        add("block")
    if re.search(r"\bspell suppression\b|\bcannot suppress\b", line, re.IGNORECASE):
        add("spell-suppression")
    if re.search(r"\bflasks?\b", line, re.IGNORECASE):
        add("flasks")
    if re.search(r"\bleech\b", line, re.IGNORECASE):
        add("leech")
    if re.search(
        r"\brecovery\b|\bregenerat|\brecharge\b",
        line,
        re.IGNORECASE,
    ):
        add("recovery")
    return tuple(found)


def _scan_rows(rows, supplied: list[str], *, require_assumption: bool) -> None:
    if not isinstance(rows, list):
        raise EndgameError("A Valdo result must not say the map is safe.")
    for row in rows:
        if not isinstance(row, dict):
            raise EndgameError("A Valdo result must not say the map is safe.")
        index = row.get("modifierIndex")
        if isinstance(index, bool) or not isinstance(index, int):
            raise EndgameError("A Valdo result must quote the supplied modifier.")
        if index < 0 or index >= len(supplied) or row.get("modifier") != supplied[index]:
            raise EndgameError("A Valdo result must quote the supplied modifier.")
        for key, value in row.items():
            if key in _QUOTE_KEYS or key == "modifierIndex":
                continue
            if not isinstance(key, str) or key.casefold() in _SAFETY_KEY or _SAFETY_WORD.search(key):
                raise EndgameError("A Valdo result must not say the map is safe.")
            _reject_safety_value(value)
        if require_assumption and row.get("assumption") not in ASSUMPTIONS.values():
            raise EndgameError("A Valdo result must name a defensive assumption.")


def _reject_safety_value(value) -> None:
    if isinstance(value, str):
        if _SAFETY_WORD.search(value):
            raise EndgameError("A Valdo result must not say the map is safe.")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or key.casefold() in _SAFETY_KEY or _SAFETY_WORD.search(key):
                raise EndgameError("A Valdo result must not say the map is safe.")
            _reject_safety_value(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_safety_value(item)
