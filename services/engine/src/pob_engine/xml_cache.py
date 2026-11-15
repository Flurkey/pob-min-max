"""Read cached PlayerStat tags from a Path of Building XML file.

PoB writes these tags from the calculation output at save time. Loading a build
does not apply them. Nothing in the engine service calls this module.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET


def stored_player_stats(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    stats: dict[str, str] = {}
    for node in root.iter("PlayerStat"):
        name = node.attrib.get("stat")
        if name and name not in stats:
            stats[name] = node.attrib.get("value", "")
    return stats
