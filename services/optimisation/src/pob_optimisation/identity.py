"""Canonical build identity for the calculation cache.

PlayerStat tags are a save-time cache. They are not part of the build, so two
XML files that differ only there share a hash. The configuration profile is
returned separately and is part of the cache key beside the PoB revision.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET

from pob_optimisation.errors import OptimisationError

_IGNORED_BUILD_ATTRIBUTES = {"viewMode"}


def canonical_build(xml: str) -> tuple[str, str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise OptimisationError(f"Build XML is not valid: {exc}") from exc
    if root.tag != "PathOfBuilding":
        raise OptimisationError("Build XML root is not PathOfBuilding.")
    payload = {
        "build": _build_attributes(root.find("Build")),
        "items": _active_items(root.find("Items")),
        "skills": _skills(root.find("Skills")),
        "tree": _active_tree(root.find("Tree")),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return digest, _configuration_profile(root.find("Config"))


def _build_attributes(build: ET.Element | None) -> dict[str, str]:
    if build is None:
        return {}
    return {
        key: value
        for key, value in sorted(build.attrib.items())
        if key not in _IGNORED_BUILD_ATTRIBUTES
    }


def _active_items(items: ET.Element | None) -> list[dict[str, str]]:
    if items is None:
        return []
    bodies = {
        item.attrib.get("id", ""): "".join(item.itertext()).strip()
        for item in items.findall("Item")
    }
    active = items.attrib.get("activeItemSet")
    equipped: list[dict[str, str]] = []
    for item_set in items.findall("ItemSet"):
        if active is not None and item_set.attrib.get("id") != active:
            continue
        for slot in item_set.findall("Slot"):
            item_id = slot.attrib.get("itemId")
            if item_id in (None, "", "0"):
                continue
            equipped.append(
                {
                    "slot": slot.attrib.get("name", ""),
                    "text": bodies.get(item_id, ""),
                }
            )
    equipped.sort(key=lambda row: (row["slot"], row["text"]))
    return equipped


def _skills(skills: ET.Element | None) -> list[dict]:
    if skills is None:
        return []
    active = skills.attrib.get("activeSkillSet")
    groups: list[dict] = []
    for skill_set in skills.findall("SkillSet"):
        if active is not None and skill_set.attrib.get("id") != active:
            continue
        for skill in skill_set.findall("Skill"):
            gems = ["".join(gem.itertext()).strip() for gem in skill.findall("Gem")]
            groups.append(
                {
                    "slot": skill.attrib.get("slot", ""),
                    "enabled": skill.attrib.get("enabled", ""),
                    "gems": gems,
                }
            )
    return groups


def _active_tree(tree: ET.Element | None) -> dict:
    if tree is None:
        return {}
    active = tree.attrib.get("activeSpec")
    spec = None
    for candidate in tree.findall("Spec"):
        if active is None or candidate.attrib.get("id", active) == active:
            spec = candidate
            break
    if spec is None:
        return {}
    nodes = sorted(
        int(part)
        for part in spec.attrib.get("nodes", "").split(",")
        if part.strip().isdigit()
    )
    return {
        "classId": spec.attrib.get("classId", ""),
        "ascendClassId": spec.attrib.get("ascendClassId", ""),
        "treeVersion": spec.attrib.get("treeVersion", ""),
        "masteryEffects": spec.attrib.get("masteryEffects", ""),
        "nodes": nodes,
    }


def _configuration_profile(config: ET.Element | None) -> str:
    if config is None:
        return "none"
    active = config.attrib.get("activeConfigSet", "")
    chosen = None
    for child in config.findall("ConfigSet"):
        if child.attrib.get("id") == active:
            chosen = child
            break
    values: list[dict[str, str]] = []
    if chosen is not None:
        for node in list(chosen):
            if node.tag == "Placeholder":
                values.append(
                    {
                        "name": node.attrib.get("name", ""),
                        "number": node.attrib.get("number", ""),
                    }
                )
            else:
                values.append(
                    {
                        "tag": node.tag,
                        "enabled": node.attrib.get("enabled", ""),
                        "title": node.attrib.get("title", ""),
                        "text": "".join(node.itertext()).strip(),
                    }
                )
    values.sort(key=lambda row: json.dumps(row, sort_keys=True))
    return json.dumps({"active": active, "values": values}, sort_keys=True, separators=(",", ":"))
