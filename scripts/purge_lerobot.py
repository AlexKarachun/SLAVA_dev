#!/usr/bin/env python3
"""Remove the lerobot-family episodes so they can be re-collected.

Resume keys on run_id (`load_completed_run_ids()`), so a stale episode is
skipped rather than redone -- re-collection therefore requires deleting the
annotation rows first. The episode directories are archived rather than
removed: they are the only record of what the compromised runs actually did,
and `scripts/relabel_rollouts.py` recomputes labels from them.

Scope: pi0, pi0.5, SmolVLA -- everything served by lerobot_server.py, whose
policy object held an un-reset action queue across episodes. GreenVLA and
OpenVLA-OFT are untouched: neither keeps chunk state inside the policy.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_KEYS = ("pi0", "pi05", "smolvla")
ARCHIVE = PROJECT_ROOT / "rollouts" / "archive" / "lerobot_pre_reset_fix" / "episodes"


def is_target(run_id: str) -> bool:
    return any(f"__{key}__" in run_id for key in MODEL_KEYS)


def main() -> None:
    annotations = PROJECT_ROOT / "rollouts" / "final" / "pilot_v0" / "rollout_annotations.jsonl"
    lines = [l for l in annotations.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [(json.loads(l)["run_id"], l) for l in lines]

    keep = [l for rid, l in rows if not is_target(rid)]
    drop = [rid for rid, _ in rows if is_target(rid)]

    backup = annotations.with_suffix(".jsonl.bak_before_reset_fix_rerun")
    if backup.exists():
        sys.exit(f"refusing to overwrite an existing backup: {backup}")
    shutil.copy2(annotations, backup)

    ARCHIVE.mkdir(parents=True, exist_ok=True)
    moved = 0
    for run_id in drop:
        src = PROJECT_ROOT / "rollouts" / "final" / "pilot_v0" / "episodes" / run_id
        if src.is_dir():
            dest = ARCHIVE / run_id
            if dest.exists():
                shutil.rmtree(dest)
            shutil.move(str(src), str(dest))
            moved += 1

    annotations.write_text("\n".join(keep) + "\n", encoding="utf-8")
    print(f"backup:   {backup.name}")
    print(f"было:     {len(rows)}")
    print(f"удалено:  {len(drop)} (папок в архив: {moved})")
    print(f"осталось: {len(keep)}")


if __name__ == "__main__":
    main()
