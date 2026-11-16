"""Attribute totals for one library copy, taken from the running engine.

The copy is a new library build. The source revision's XML stays as it was.
Str, Dex, and Int are copied out of that engine result. This module does not
add a jewel and does not derive a bonus the engine did not return.
"""

from __future__ import annotations

from pob_endgame.errors import EndgameError

# mainOutput names for the three attributes. A missing key is an error.
ATTRIBUTE_STATS: tuple[str, ...] = ("Str", "Dex", "Int")


def attribute_stack(service, build_id: str, revision_id: str | None = None) -> dict:
    """Calculate a library copy and report the engine's attribute totals."""
    detail = service.history(build_id)
    source_name = detail["build"]["name"]
    saved_id = detail["build"]["savedRevisionId"]
    parent_id = revision_id or saved_id
    if not parent_id:
        raise EndgameError("This build has no stored revision to copy.")
    original_xml = service.store.get(parent_id)["xml"]

    copied = service.library_copy(
        build_id,
        parent_id,
        name=f"{source_name} (attributes)",
        label="attributes",
    )
    revision = copied["revision"]
    if revision["buildId"] == build_id or copied["parentId"] != parent_id:
        raise EndgameError("The attribute copy was written onto the source build.")
    if copied["sourceBuild"]["savedRevisionId"] != saved_id:
        raise EndgameError("The attribute copy moved the stored revision.")
    _require_source_unchanged(service, build_id, parent_id, saved_id, original_xml)

    calculation = service.calculate(revision["id"])
    if calculation.get("source") != "pob-engine":
        raise EndgameError("The attribute result did not come from the engine.")
    stats = calculation.get("stats")
    if not isinstance(stats, dict):
        raise EndgameError("The engine did not return a stat table.")
    missing = [name for name in ATTRIBUTE_STATS if name not in stats]
    if missing:
        raise EndgameError(
            "The engine did not return " + ", ".join(missing) + "."
        )
    _require_source_unchanged(service, build_id, parent_id, saved_id, original_xml)

    return {
        "sourceBuildId": build_id,
        "parentId": parent_id,
        "savedRevisionId": saved_id,
        "copy": {
            "build": copied["build"],
            "revision": revision,
        },
        "calculation": calculation,
        "attributes": {name: stats[name] for name in ATTRIBUTE_STATS},
    }


def _require_source_unchanged(service, build_id: str, parent_id: str, saved_id: str, original_xml: str) -> None:
    if service.store.get(parent_id)["xml"] != original_xml:
        raise EndgameError("The attribute check changed the source XML.")
    if service.store.get_build(build_id)["saved_revision_id"] != saved_id:
        raise EndgameError("The attribute check moved the stored revision.")
