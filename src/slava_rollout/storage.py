from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Single unified directory for every model/run's logs — user's explicit requirement,
# not split per model or per launch. See AGENTS.md "Выход и требования к запуску".
ROLLOUTS_ROOT = PROJECT_ROOT / "rollouts"


def annotations_path() -> Path:
    return ROLLOUTS_ROOT / "rollout_annotations.jsonl"


def episode_dir(run_id: str) -> Path:
    return ROLLOUTS_ROOT / "episodes" / run_id


def steps_path(run_id: str) -> Path:
    return episode_dir(run_id) / "steps.jsonl"


def camera_dir(run_id: str, camera: str) -> Path:
    return episode_dir(run_id) / "camera" / camera


def run_log_path(run_id: str) -> Path:
    return ROLLOUTS_ROOT / "logs" / f"{run_id}.log"


def ensure_episode_dirs(run_id: str, has_wrist: bool) -> None:
    camera_dir(run_id, "agentview").mkdir(parents=True, exist_ok=True)
    if has_wrist:
        camera_dir(run_id, "wrist").mkdir(parents=True, exist_ok=True)
    run_log_path(run_id).parent.mkdir(parents=True, exist_ok=True)


def append_jsonl_locked(record: dict[str, Any], path: Path) -> None:
    """Append one JSON line with an exclusive file lock.

    Multiple env-workers (one per model, run sequentially per the launcher's design —
    see scripts/run_rollouts.py) may still overlap briefly during handoff, so every
    writer to the single shared rollout_annotations.jsonl takes this lock rather than
    assuming exclusive access.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_annotation(record: dict[str, Any]) -> None:
    from .schema import validate_rollout_annotation

    validate_rollout_annotation(record)
    append_jsonl_locked(record, annotations_path())


def load_completed_run_ids() -> set[str]:
    """Resume support: run_ids already present in rollout_annotations.jsonl."""
    path = annotations_path()
    if not path.exists():
        return set()
    completed = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            completed.add(json.loads(line)["run_id"])
    return completed
