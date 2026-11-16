from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "engine" / "pin.json").is_file():
            return parent
    raise RuntimeError("Could not find the repository root from the engine package.")


@dataclass(frozen=True)
class EnginePaths:
    root: Path
    adapter: Path
    pin_path: Path
    pin: dict
    src: Path
    luajit: Path
    runtime: Path
    utf8_dir: Path
    fixture: Path


def resolve_paths() -> EnginePaths:
    root = repo_root()
    pin_path = root / "engine" / "pin.json"
    pin = json.loads(pin_path.read_text(encoding="utf-8"))
    return EnginePaths(
        root=root,
        adapter=root / "engine" / "adapter.lua",
        pin_path=pin_path,
        pin=pin,
        src=Path(os.environ.get("POB_SRC", root / ".pob" / "PathOfBuilding" / "src")),
        luajit=Path(os.environ.get("POB_LUA", root / ".pob" / "bin" / "luajit")),
        runtime=Path(os.environ.get("POB_RUNTIME", root / "engine" / "vendor" / "runtime")),
        utf8_dir=Path(os.environ.get("POB_UTF8_DIR", root / ".pob" / "utf8")),
        fixture=root / "fixtures" / "builds" / "scion-baseline.xml",
    )


def library_path() -> Path:
    """Local SQLite library. This is not a Path of Building Builds directory."""
    override = os.environ.get("POB_LIBRARY")
    path = Path(override) if override else repo_root() / "data" / "library.sqlite"
    return path


def git_head(src: Path) -> str:
    completed = subprocess.run(
        ["git", "-C", str(src), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Could not read the Path of Building revision in {src}: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()
