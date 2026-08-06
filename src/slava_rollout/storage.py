from __future__ import annotations

import fcntl
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ROLLOUTS_ROOT = PROJECT_ROOT / "rollouts"

# One directory per *pool* of episodes, not per model and not per launch: a pool
# is a set of episodes that were collected by one code state and may be
# aggregated together. `final/` holds the pools that current results are read
# from; `archive/` holds superseded ones, kept because they are the only record
# of what compromised runs actually did. Every pool directory carries a README.md
# saying what it is, on what hardware, and whether it may be trusted — see
# rollouts/RUNS.md for the index.
#
# The active pool is overridable so a run can be collected into a fresh pool
# without touching the finished ones (SLAVA_RUN_POOL=<name>, resolved under
# final/). Everything downstream — resume, episode frames, per-episode logs —
# follows from here, so there is exactly one place that decides where a run
# lands.
import os as _os

DEFAULT_POOL = "pilot_v0"
POOL_NAME = _os.environ.get("SLAVA_RUN_POOL", DEFAULT_POOL)


def pool_root(pool: str | None = None) -> Path:
    return ROLLOUTS_ROOT / "final" / (pool or POOL_NAME)


def annotations_path(pool: str | None = None) -> Path:
    return pool_root(pool) / "rollout_annotations.jsonl"


def episode_dir(run_id: str, pool: str | None = None) -> Path:
    return pool_root(pool) / "episodes" / run_id


def steps_path(run_id: str) -> Path:
    return episode_dir(run_id) / "steps.jsonl"


def camera_dir(run_id: str, camera: str) -> Path:
    return episode_dir(run_id) / "camera" / camera


def run_log_path(run_id: str, pool: str | None = None) -> Path:
    return pool_root(pool) / "logs" / f"{run_id}.log"


def ensure_episode_dirs(run_id: str, has_wrist: bool) -> None:
    """Prepare an episode directory — including clearing whatever a previous
    run of the same run_id left behind.

    Re-running an episode overwrites frames 1..N and appends to steps.jsonl,
    neither of which removes the tail of a longer earlier attempt. The result
    is a directory holding two different episodes: frames 1..N from the new
    run, frames N+1..M from the old one. Nothing in the metrics notices —
    annotations and steps.jsonl are authoritative — but every consumer of the
    frames (review dashboards, report clips) then shows one episode that
    teleports mid-way. Found 2026-08-07 when the user hit exactly that while
    reviewing rollout 8 of 100: a cube held above its target in one frame,
    lying on the table in the next.
    """
    for camera in ("agentview", "wrist"):
        directory = camera_dir(run_id, camera)
        if directory.is_dir():
            for frame in directory.glob("step_*.png"):
                frame.unlink()
    camera_dir(run_id, "agentview").mkdir(parents=True, exist_ok=True)
    if has_wrist:
        camera_dir(run_id, "wrist").mkdir(parents=True, exist_ok=True)
    # steps.jsonl is opened in append mode by the orchestrator, so a re-run
    # would otherwise interleave two attempts in one file.
    steps_path(run_id).unlink(missing_ok=True)
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
