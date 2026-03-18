from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _looks_like_suite_root(path: Path) -> bool:
    return (path / "app" / "main.py").exists() and (path / "ros2_ws").exists()


def get_suite_root() -> str:
    env = os.environ.get("ANAFI_SUITE_ROOT", "").strip()
    if env:
        p = Path(env).expanduser().resolve()
        if _looks_like_suite_root(p):
            return str(p)

    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if _looks_like_suite_root(parent):
            return str(parent)

    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        if _looks_like_suite_root(parent):
            return str(parent)

    return str(here.parent)


def get_app_dir() -> str:
    return str(Path(get_suite_root()) / "app")


def get_runtime_dir() -> str:
    runtime = Path(get_suite_root()) / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    (runtime / "logs").mkdir(parents=True, exist_ok=True)
    return str(runtime)


def get_current_mission_path() -> str:
    return str(Path(get_runtime_dir()) / "current_mission.json")


def write_current_mission(mission: dict[str, Any]) -> str:
    path = Path(get_current_mission_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mission, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def read_current_mission() -> dict[str, Any]:
    path = Path(get_current_mission_path())
    if not path.exists():
        raise FileNotFoundError(f"No existe la misión actual: {path}")
    return json.loads(path.read_text(encoding="utf-8"))
