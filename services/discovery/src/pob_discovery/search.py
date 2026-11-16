"""Find chains and conflicts in imported unique and modifier text.

A chain is an ordered pair of lines. Both lines contain one phrase, and that
phrase is copied from the import. The first line establishes it (a grant, an
increase, or a reduction). The second line uses it (a condition, "also apply",
"for every", or "per"). A conflict quotes either a shared modifier ``group``,
two Variant or Version headers, a status line against a line that requires
that status, or an aura-disable line against a line that requires a different
aura. Nothing here adds a modifier the import does not already contain.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pob_knowledge.store import KnowledgeStore

from pob_discovery.errors import DiscoveryError

_CHAIN_LINKS = frozenset({"also-applies", "for-every", "per-stat", "grants"})
_CONFLICT_KINDS = frozenset(
    {"mod-group", "variant", "version", "status", "aura-disabled"}
)

_TAG = re.compile(r"\{[^{}]*\}")
_ALSO = re.compile(
    r"^(?:increases and reductions|modifiers) to (?:your )?(.+?) also apply to (?:your )?(.+?)"
    r"(?: at \d+% of their value)?$",
    re.IGNORECASE,
)
_FOR_EVERY = re.compile(
    r"\bfor every\s+\d+%\s+your\s+(.+?)\s+is\b",
    re.IGNORECASE,
)
_PER_STAT = re.compile(
    r"\bper\s+\d+\s+([A-Z][A-Za-z']+(?:\s+[A-Z][A-Za-z']+){0,3})\b"
)
_GRANT = re.compile(r"^grants level \d+ (.+?)(?: skill)?$", re.IGNORECASE)
_TRIGGER = re.compile(r"^triggers? level \d+ (.+?) when\b", re.IGNORECASE)
_PROHIBIT = re.compile(
    r"^(?:you )?cannot be ([a-z]+(?: [a-z]+)?)$",
    re.IGNORECASE,
)
_AURA_OFF = re.compile(r"^aura skills other than (.+?) are disabled$", re.IGNORECASE)
_WHILE = re.compile(
    r"\bwhile (?:affected by|you are using|using) (.+)$",
    re.IGNORECASE,
)
_AFFECTED_LINE = re.compile(r"^affected by (.+)$", re.IGNORECASE)
_TRAIL = r"(?=$|[,.:;]|\s+(?:while|if|on|to|with|against|per|for|when|you|and)\b)"
# A stat on minions, allies, or totems is not the character's stat. "You and
# nearby Allies" still includes the character, so a leading "you" keeps the line.
_OTHER_SUBJECT = re.compile(r"\b(?:minions?|allies|totems?|summoned|golems?)\b", re.IGNORECASE)
_YOU = re.compile(r"\byou\b", re.IGNORECASE)
_PER_LINE_SKIP = ("radius", "allocated", "unallocated", "passive")
_PER_PHRASE_STOP = frozenset(
    {
        "second",
        "seconds",
        "level",
        "enemy",
        "enemies",
        "hit",
        "hits",
        "kill",
        "kills",
        "recently",
        "charge",
        "charges",
        "skill",
        "skills",
        "point",
        "points",
        "metre",
        "metres",
        "meter",
        "meters",
        "stack",
        "stacks",
        "projectile",
        "projectiles",
        "curse",
        "curses",
        "spell",
        "spells",
        "attack",
        "attacks",
        "time",
        "times",
    }
)


@dataclass(frozen=True)
class Citation:
    """One imported unique or one imported modifier line."""

    kind: str
    name: str
    source_path: str
    excerpt: str

    def __post_init__(self) -> None:
        if self.kind not in {"unique", "mod"}:
            raise DiscoveryError(f"Unknown citation kind {self.kind}.")
        if not self.name.strip() or not self.source_path.strip() or not self.excerpt.strip():
            raise DiscoveryError("A citation needs a name, source path, and excerpt.")


@dataclass(frozen=True)
class Chain:
    """Two cited lines joined by a phrase that appears in both."""

    link: str
    via: str
    steps: tuple[Citation, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.link not in _CHAIN_LINKS:
            raise DiscoveryError(f"Unknown chain link {self.link}.")
        if len(self.steps) < 2:
            raise DiscoveryError("A chain needs two cited steps.")
        if not self.via.strip():
            raise DiscoveryError("A chain needs the shared phrase.")


@dataclass(frozen=True)
class Conflict:
    """Cited rows that the imported text or a group field puts against each other."""

    kind: str
    via: str
    steps: tuple[Citation, ...]
    reason: str

    def __post_init__(self) -> None:
        if self.kind not in _CONFLICT_KINDS:
            raise DiscoveryError(f"Unknown conflict kind {self.kind}.")
        if len(self.steps) < 2:
            raise DiscoveryError("A conflict needs two cited steps.")
        if not self.via.strip():
            raise DiscoveryError("A conflict needs the shared field or phrase.")


@dataclass(frozen=True)
class Discovery:
    chains: tuple[Chain, ...]
    conflicts: tuple[Conflict, ...]


@dataclass(frozen=True)
class _Line:
    citation: Citation
    cleaned: str


def clean_line(line: str) -> str:
    """Drop Path of Building ``{variant}`` and ``{tags}`` markers."""
    previous = None
    text = line.strip()
    while text != previous:
        previous = text
        text = _TAG.sub("", text).strip()
    return text


def assert_known(store: KnowledgeStore, steps: Iterable[Citation]) -> None:
    """Raise when a step's name or excerpt is not in the imported database."""
    found = False
    for step in steps:
        found = True
        if step.kind == "unique":
            rows = store.unique_items(step.name)
            if not any(
                row["sourcePath"] == step.source_path and step.excerpt in row["rawText"]
                for row in rows
            ):
                raise DiscoveryError(
                    f"{step.name} is not an imported unique with that excerpt."
                )
        else:
            rows = store.mods_by_id(step.name)
            if not any(
                row["sourcePath"] == step.source_path
                and step.excerpt in "\n".join(row.get("lines") or [])
                for row in rows
            ):
                raise DiscoveryError(
                    f"{step.name} is not an imported modifier with that excerpt."
                )
    if not found:
        raise DiscoveryError("A citation list is empty.")


def discover(store: KnowledgeStore) -> Discovery:
    """Search the current knowledge import. Citations that miss the import raise."""
    uniques = store.all_uniques()
    mods = store.all_mods()
    lines = _lines(uniques, mods)
    catalogue = _catalogue(uniques, mods)
    chains = _chains(lines)
    conflicts = _conflicts(uniques, mods, lines)
    for chain in chains:
        _require_phrase(chain)
        _require_in_catalogue(catalogue, chain.steps)
    for conflict in conflicts:
        _require_in_catalogue(catalogue, conflict.steps)
    return Discovery(chains=tuple(chains), conflicts=tuple(conflicts))


def _lines(uniques: Sequence[dict], mods: Sequence[dict]) -> list[_Line]:
    found: list[_Line] = []
    for item in uniques:
        for raw in str(item["rawText"]).splitlines():
            if not raw.strip():
                continue
            found.append(
                _Line(
                    citation=Citation(
                        kind="unique",
                        name=item["name"],
                        source_path=item["sourcePath"],
                        excerpt=raw,
                    ),
                    cleaned=clean_line(raw),
                )
            )
    for mod in mods:
        raw_lines = mod.get("lines") or []
        if not isinstance(raw_lines, list):
            continue
        for raw in raw_lines:
            if not isinstance(raw, str) or not raw.strip():
                continue
            found.append(
                _Line(
                    citation=Citation(
                        kind="mod",
                        name=mod["modId"],
                        source_path=mod["sourcePath"],
                        excerpt=raw,
                    ),
                    cleaned=clean_line(raw),
                )
            )
    return found


def _catalogue(uniques: Sequence[dict], mods: Sequence[dict]) -> dict[tuple[str, str, str], list[str]]:
    # One unique name can be several rows in the same file (Doryani's Delusion
    # is one name on several bases). Keep every row.
    texts: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for item in uniques:
        texts[("unique", item["name"], item["sourcePath"])].append(item["rawText"])
    for mod in mods:
        raw_lines = mod.get("lines") or []
        if not isinstance(raw_lines, list):
            continue
        texts[("mod", mod["modId"], mod["sourcePath"])].append(
            "\n".join(line for line in raw_lines if isinstance(line, str))
        )
    return texts


def _require_in_catalogue(
    catalogue: dict[tuple[str, str, str], list[str]],
    steps: Sequence[Citation],
) -> None:
    for step in steps:
        texts = catalogue.get((step.kind, step.name, step.source_path), [])
        if not any(step.excerpt in text for text in texts):
            raise DiscoveryError(
                f"{step.kind} {step.name} does not contain the cited excerpt."
            )


def _require_phrase(chain: Chain) -> None:
    needle = chain.via.casefold()
    if len(needle) < 3:
        raise DiscoveryError(f"Shared phrase {chain.via!r} is too short to cite.")
    for step in chain.steps:
        if needle not in step.excerpt.casefold():
            raise DiscoveryError(
                f"Chain phrase {chain.via!r} is not in the cited text of {step.name}."
            )


def _chains(lines: Sequence[_Line]) -> list[Chain]:
    also: list[tuple[_Line, str]] = []
    every: list[tuple[_Line, str]] = []
    per: list[tuple[_Line, str]] = []
    grants: list[tuple[_Line, str]] = []
    for line in lines:
        also_stat = _also_stat(line.cleaned)
        if also_stat:
            also.append((line, also_stat))
        every_stat = _for_every_stat(line.cleaned)
        if every_stat:
            every.append((line, every_stat))
        per_stat = _per_stat(line.cleaned)
        if per_stat:
            per.append((line, per_stat))
        granted = _granted_name(line.cleaned)
        if granted:
            grants.append((line, granted))

    stats: dict[str, str] = {}
    for _line, stat in (*also, *every, *per):
        stats.setdefault(stat.casefold(), stat)
    providers = _providers(lines, list(stats.values())) if stats else {}

    found: list[Chain] = []
    seen: set[tuple] = set()
    for line, stat in also:
        for provider in providers.get(stat.casefold(), []):
            if provider[0] not in {"increased", "reduced"}:
                continue
            _add_chain(
                found,
                seen,
                link="also-applies",
                via=stat,
                source=provider[1],
                consumer=line,
                reason=f"The second line says increases and reductions to {stat} also apply.",
            )
    for line, stat in every:
        for provider in providers.get(stat.casefold(), []):
            if provider[0] not in {"increased", "reduced", "to"}:
                continue
            _add_chain(
                found,
                seen,
                link="for-every",
                via=stat,
                source=provider[1],
                consumer=line,
                reason=f"The second line scales for every percent of {stat}.",
            )
    for line, stat in per:
        for provider in providers.get(stat.casefold(), []):
            if provider[0] not in {"increased", "reduced", "to"}:
                continue
            _add_chain(
                found,
                seen,
                link="per-stat",
                via=stat,
                source=provider[1],
                consumer=line,
                reason=f"The second line scales per {stat}.",
            )
    by_effect: dict[str, list[_Line]] = defaultdict(list)
    for line, effect in grants:
        by_effect[effect.casefold()].append(line)
    if by_effect:
        for line in lines:
            folded = line.cleaned.casefold()
            if "while " not in folded and " has " not in folded and not folded.startswith("affected by "):
                continue
            for key, sources in by_effect.items():
                if key not in folded:
                    continue
                effect = _effect_in_line(key, sources[0], line.cleaned)
                if effect is None:
                    continue
                for source in sources:
                    _add_chain(
                        found,
                        seen,
                        link="grants",
                        via=effect,
                        source=source,
                        consumer=line,
                        reason=f"The first line grants {effect} and the second line names {effect}.",
                    )
    found.sort(key=_chain_sort)
    return found


def _effect_in_line(key: str, sample: _Line, cleaned: str) -> str | None:
    """Return the grant's spelling when ``cleaned`` is a condition on that effect."""
    effect = _granted_name(sample.cleaned)
    if effect is None or effect.casefold() != key:
        return None
    if effect.casefold() not in cleaned.casefold():
        return None
    if _GRANT.match(cleaned) or _TRIGGER.match(cleaned):
        return None
    pattern = re.escape(effect)
    if re.search(rf"\bwhile (?:affected by|you are using|using) {pattern}$", cleaned, re.IGNORECASE):
        return effect
    if re.match(rf"affected by {pattern}$", cleaned, re.IGNORECASE):
        return effect
    if re.match(rf"{pattern} has\b", cleaned, re.IGNORECASE):
        return effect
    return None


def _add_chain(
    found: list[Chain],
    seen: set[tuple],
    *,
    link: str,
    via: str,
    source: _Line,
    consumer: _Line,
    reason: str,
) -> None:
    if source.citation == consumer.citation:
        return
    if via.casefold() not in source.citation.excerpt.casefold():
        return
    if via.casefold() not in consumer.citation.excerpt.casefold():
        return
    key = (
        link,
        via.casefold(),
        source.citation.kind,
        source.citation.name,
        source.citation.source_path,
        source.citation.excerpt,
        consumer.citation.excerpt,
    )
    if key in seen:
        return
    seen.add(key)
    found.append(
        Chain(
            link=link,
            via=via,
            steps=(source.citation, consumer.citation),
            reason=reason,
        )
    )


def _providers(lines: Sequence[_Line], stats: list[str]) -> dict[str, list[tuple[str, _Line]]]:
    ordered = sorted(stats, key=len, reverse=True)
    pattern = re.compile(
        r"\b(increased|reduced|more|less|to)\s+("
        + "|".join(re.escape(stat) for stat in ordered)
        + ")"
        + _TRAIL,
        re.IGNORECASE,
    )
    canonical = {stat.casefold(): stat.casefold() for stat in stats}
    found: dict[str, list[tuple[str, _Line]]] = defaultdict(list)
    for line in lines:
        if _ALSO.match(line.cleaned):
            continue
        for match in pattern.finditer(line.cleaned):
            verb = match.group(1).casefold()
            stat = canonical.get(match.group(2).casefold())
            if stat is None or verb == "more" or verb == "less":
                continue
            if _other_subject(line.cleaned, match.start()):
                continue
            found[stat].append((verb, line))
    return found


def _other_subject(cleaned: str, start: int) -> bool:
    prefix = cleaned[:start]
    if not _OTHER_SUBJECT.search(prefix):
        return False
    return _YOU.search(prefix) is None


def _also_stat(cleaned: str) -> str | None:
    match = _ALSO.match(cleaned)
    if not match:
        return None
    stat = match.group(1).strip()
    if len(stat) < 3:
        return None
    return stat


def _for_every_stat(cleaned: str) -> str | None:
    match = _FOR_EVERY.search(cleaned)
    if not match:
        return None
    stat = match.group(1).strip()
    if len(stat) < 3:
        return None
    return stat


def _per_stat(cleaned: str) -> str | None:
    folded = cleaned.casefold()
    if any(word in folded for word in _PER_LINE_SKIP):
        return None
    match = _PER_STAT.search(cleaned)
    if not match:
        return None
    stat = match.group(1).strip()
    if stat.casefold() in _PER_PHRASE_STOP or len(stat) < 4:
        return None
    return stat


def _granted_name(cleaned: str) -> str | None:
    match = _GRANT.match(cleaned) or _TRIGGER.match(cleaned)
    if not match:
        return None
    name = match.group(1).strip()
    name = name.split(",", 1)[0].strip()
    if name.casefold().endswith(" skill"):
        name = name[: -len(" skill")].strip()
    if len(name) < 3:
        return None
    return name


def _conflicts(
    uniques: Sequence[dict],
    mods: Sequence[dict],
    lines: Sequence[_Line],
) -> list[Conflict]:
    found = [
        *_group_conflicts(mods),
        *_header_conflicts(uniques, "Variant", "variant"),
        *_header_conflicts(uniques, "Version", "version"),
        *_status_conflicts(lines),
        *_aura_conflicts(lines),
    ]
    found.sort(key=_conflict_sort)
    return found


def _group_conflicts(mods: Sequence[dict]) -> list[Conflict]:
    # ItemsTab:UpdateAffixControl drops a modifier once its group is already
    # on the item. The group field is that exclusivity, scoped to one mod file
    # because each file is its own affix list.
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for mod in mods:
        group = mod.get("group")
        raw_lines = mod.get("lines") or []
        if not isinstance(group, str) or not group.strip():
            continue
        if not isinstance(raw_lines, list) or not any(isinstance(line, str) and line.strip() for line in raw_lines):
            continue
        grouped[(mod["sourcePath"], group)].append(mod)
    found: list[Conflict] = []
    for (source_path, group), members in grouped.items():
        if len(members) < 2:
            continue
        members = sorted(members, key=lambda mod: mod["modId"])
        steps = tuple(
            Citation(
                kind="mod",
                name=mod["modId"],
                source_path=source_path,
                excerpt="\n".join(line for line in mod["lines"] if isinstance(line, str)),
            )
            for mod in members
        )
        found.append(
            Conflict(
                kind="mod-group",
                via=group,
                steps=steps,
                reason=f"These modifiers share group {group}.",
            )
        )
    return found


def _header_conflicts(uniques: Sequence[dict], header: str, kind: str) -> list[Conflict]:
    prefix = f"{header}:"
    found: list[Conflict] = []
    for item in uniques:
        raw_lines = [line for line in str(item["rawText"]).splitlines() if line.strip()]
        cleaned = [clean_line(line) for line in raw_lines]
        if header == "Variant" and any(line.startswith("Has Alt Variant:") for line in cleaned):
            # Item.lua keeps variantAlt beside variant, so those headers are
            # not a single choice.
            continue
        chosen = [
            raw
            for raw, text in zip(raw_lines, cleaned, strict=True)
            if text.startswith(prefix)
        ]
        if len(chosen) < 2:
            continue
        steps = tuple(
            Citation(
                kind="unique",
                name=item["name"],
                source_path=item["sourcePath"],
                excerpt=raw,
            )
            for raw in chosen
        )
        label = "Variant" if header == "Variant" else "Version"
        found.append(
            Conflict(
                kind=kind,
                via=item["name"],
                steps=steps,
                reason=f"{item['name']} lists more than one {label}.",
            )
        )
    return found


def _status_conflicts(lines: Sequence[_Line]) -> list[Conflict]:
    prohibitions: list[tuple[_Line, str]] = []
    for line in lines:
        match = _PROHIBIT.match(line.cleaned)
        if match:
            prohibitions.append((line, match.group(1)))
    found: list[Conflict] = []
    seen: set[tuple] = set()
    for ban, status in prohibitions:
        pattern = re.compile(
            rf"\bwhile {re.escape(status)}\b(?!\s+enemies\b)",
            re.IGNORECASE,
        )
        for line in lines:
            if line.citation == ban.citation:
                continue
            if _PROHIBIT.match(line.cleaned):
                continue
            if not pattern.search(line.cleaned):
                continue
            key = (
                status.casefold(),
                ban.citation.name,
                ban.citation.source_path,
                ban.citation.excerpt,
                line.citation.name,
                line.citation.source_path,
                line.citation.excerpt,
            )
            if key in seen:
                continue
            seen.add(key)
            found.append(
                Conflict(
                    kind="status",
                    via=status,
                    steps=(ban.citation, line.citation),
                    reason=f"The first line forbids {status}. The second line requires {status}.",
                )
            )
    return found


def _aura_conflicts(lines: Sequence[_Line]) -> list[Conflict]:
    # "Aura Skills other than X are Disabled" names X as an aura. A different
    # line that requires another name from that same set cannot be active
    # while the disable line is.
    disables: list[tuple[_Line, str]] = []
    auras: dict[str, str] = {}
    for line in lines:
        match = _AURA_OFF.match(line.cleaned)
        if not match:
            continue
        name = match.group(1).strip()
        if len(name) < 3:
            continue
        disables.append((line, name))
        auras.setdefault(name.casefold(), name)
    found: list[Conflict] = []
    seen: set[tuple] = set()
    for line in lines:
        effect = _condition_aura(line.cleaned, auras)
        if effect is None:
            continue
        for ban, exception in disables:
            if exception.casefold() == effect.casefold():
                continue
            if _same_mod(ban.citation, line.citation):
                continue
            key = (
                effect.casefold(),
                ban.citation.name,
                ban.citation.excerpt,
                line.citation.name,
                line.citation.excerpt,
            )
            if key in seen:
                continue
            seen.add(key)
            found.append(
                Conflict(
                    kind="aura-disabled",
                    via=effect,
                    steps=(ban.citation, line.citation),
                    reason=(
                        f"One line disables aura skills other than its own, "
                        f"and the other line requires {effect}."
                    ),
                )
            )
    return found


def _condition_aura(cleaned: str, auras: dict[str, str]) -> str | None:
    match = _WHILE.search(cleaned) or _AFFECTED_LINE.match(cleaned)
    if not match:
        return None
    name = match.group(1).strip()
    return auras.get(name.casefold())


def _same_mod(left: Citation, right: Citation) -> bool:
    return left.kind == "mod" and right.kind == "mod" and left.name == right.name and left.source_path == right.source_path


def _chain_sort(chain: Chain) -> tuple:
    return (
        chain.link,
        chain.via.casefold(),
        tuple((step.kind, step.name, step.source_path, step.excerpt) for step in chain.steps),
    )


def _conflict_sort(conflict: Conflict) -> tuple:
    return (
        conflict.kind,
        conflict.via.casefold(),
        tuple((step.kind, step.name, step.source_path, step.excerpt) for step in conflict.steps),
    )
