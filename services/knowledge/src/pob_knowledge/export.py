from __future__ import annotations

import json
import os
import subprocess

from pob_knowledge.errors import KnowledgeError
from pob_knowledge.paths import KnowledgePaths, assert_checkout_matches_pin


def export_checkout(paths: KnowledgePaths) -> tuple[dict, str, str]:
    """Load the pinned checkout's data files and return the parsed document.

    The Lua process only reads data tables. It does not start the calculation runtime.
    """
    commit, manifest = assert_checkout_matches_pin(paths)
    env = os.environ.copy()
    env["POB_RUNTIME"] = str(paths.runtime)
    completed = subprocess.run(
        [str(paths.luajit), str(paths.exporter)],
        cwd=paths.src,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "data export failed").strip()
        raise KnowledgeError(detail[-4000:])
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise KnowledgeError(f"Data export did not return JSON: {exc}") from exc
    tree_version = document.get("treeVersion")
    if tree_version != paths.pin["latestTreeVersion"]:
        raise KnowledgeError(
            f"Checkout tree {tree_version} does not match the pin {paths.pin['latestTreeVersion']}."
        )
    if document.get("treeDisplay") != paths.pin["latestTreeDisplay"]:
        raise KnowledgeError(
            f"Checkout tree display {document.get('treeDisplay')} does not match "
            f"the pin {paths.pin['latestTreeDisplay']}."
        )
    return document, commit, manifest
