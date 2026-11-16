"""One library build per progression stage.

Each stage is a new saved build whose XML is a copy of the source revision.
The source build's saved revision is left where it was.
"""

from __future__ import annotations

from pob_progression.errors import ProgressionError

# Named stages only. A caller cannot add a stage this data does not name.
STAGES: tuple[str, ...] = ("campaign", "early maps", "endgame")


def progression_copies(service, build_id: str, revision_id: str | None = None) -> dict:
    """Copy one library build into a separate build for each stage."""
    detail = service.history(build_id)
    source_name = detail["build"]["name"]
    saved_id = detail["build"]["savedRevisionId"]
    parent_id = revision_id or saved_id
    if not parent_id:
        raise ProgressionError("This build has no stored revision to copy.")

    stages = []
    for stage in STAGES:
        copied = service.library_copy(
            build_id,
            parent_id,
            name=f"{source_name} ({stage})",
            label=stage,
        )
        revision = copied["revision"]
        if revision["label"] != stage or revision["status"] != "saved":
            raise ProgressionError("A stage copy was not stored as its own saved build.")
        if revision["buildId"] == build_id or copied["parentId"] != parent_id:
            raise ProgressionError("A stage copy was written onto the source build.")
        if copied["sourceBuild"]["savedRevisionId"] != saved_id:
            raise ProgressionError("A stage copy moved the stored revision.")
        stages.append(
            {
                "stage": stage,
                "build": copied["build"],
                "revision": revision,
            }
        )

    after = service.history(build_id)
    if after["build"]["savedRevisionId"] != saved_id:
        raise ProgressionError("Progression copies moved the stored revision.")
    source_ids = {row["id"] for row in after["revisions"]}
    copy_ids = {stage["revision"]["id"] for stage in stages}
    if source_ids & copy_ids:
        raise ProgressionError("A stage copy replaced a revision of the source build.")
    return {
        "sourceBuildId": build_id,
        "parentId": parent_id,
        "savedRevisionId": saved_id,
        "stages": stages,
    }
