from __future__ import annotations

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from pob_knowledge.errors import KnowledgeError

SOURCE = "PathOfBuildingCommunity/PathOfBuilding"
SOURCE_REPO = "https://github.com/PathOfBuildingCommunity/PathOfBuilding"


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "engine" / "pin.json").is_file():
            return parent
    raise KnowledgeError("Could not find the repository root from the knowledge package.")


@dataclass(frozen=True)
class KnowledgePaths:
    root: Path
    pin_path: Path
    pin: dict
    src: Path
    checkout: Path
    luajit: Path
    runtime: Path
    exporter: Path


def resolve_paths() -> KnowledgePaths:
    root = repo_root()
    pin_path = root / "engine" / "pin.json"
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    src = Path(os.environ.get("POB_SRC", root / ".pob" / "PathOfBuilding" / "src"))
    return KnowledgePaths(
        root=root,
        pin_path=pin_path,
        pin=pin,
        src=src,
        checkout=src.parent,
        luajit=Path(os.environ.get("POB_LUA", root / ".pob" / "bin" / "luajit")),
        runtime=Path(os.environ.get("POB_RUNTIME", root / "engine" / "vendor" / "runtime")),
        exporter=Path(__file__).resolve().parent / "export_game_data.lua",
    )


def knowledge_db_path() -> Path:
    override = os.environ.get("POB_KNOWLEDGE")
    path = Path(override) if override else repo_root() / "data" / "knowledge.sqlite"
    return path


def git_head(checkout: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise KnowledgeError(
            f"Could not read the Path of Building revision in {checkout}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def manifest_version(checkout: Path) -> str:
    root = ET.parse(checkout / "manifest.xml").getroot()
    version = root.find("Version")
    if version is None or "number" not in version.attrib:
        raise KnowledgeError(f"{checkout / 'manifest.xml'} has no Version number.")
    return version.attrib["number"]


def assert_checkout_matches_pin(paths: KnowledgePaths) -> tuple[str, str]:
    """Refuse to import when the checkout is not the pinned engine."""
    if not paths.exporter.is_file():
        raise KnowledgeError(f"Missing data exporter: {paths.exporter}")
    if not paths.luajit.is_file():
        raise KnowledgeError(f"LuaJIT is not built at {paths.luajit}. Run ./scripts/bootstrap_engine.sh.")
    if not (paths.src / "HeadlessWrapper.lua").is_file():
        raise KnowledgeError(f"Path of Building source is not checked out at {paths.src}.")
    commit = git_head(paths.checkout)
    expected = paths.pin["commit"]
    if commit != expected:
        raise KnowledgeError(
            f"Path of Building checkout {commit} does not match the pin {expected}. "
            "The knowledge import will not read a different tree."
        )
    manifest = manifest_version(paths.checkout)
    if manifest != paths.pin["manifestVersion"]:
        raise KnowledgeError(
            f"manifest.xml says {manifest}, but the pin records {paths.pin['manifestVersion']}."
        )
    return commit, manifest
