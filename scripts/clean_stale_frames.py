#!/usr/bin/env python3
"""Remove frames left over from an earlier run of the same run_id.

Re-collecting an episode overwrote frames 1..N but never deleted N+1..M from a
longer previous attempt, so those directories hold two different episodes
stitched together. `storage.ensure_episode_dirs` now clears the directory up
front; this script repairs the episodes collected before that fix.

steps.jsonl is the authority on how long the episode actually was: the valid
frames are 1..len(steps), plus the terminal frame len(steps)+1 when it was
written by the same run (checked by mtime, not assumed).

    python3 scripts/clean_stale_frames.py            # report only
    python3 scripts/clean_stale_frames.py --delete   # actually remove
"""
from __future__ import annotations

import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def stale_frames(episode: Path) -> list[Path]:
    steps_file = episode / "steps.jsonl"
    if not steps_file.exists():
        return []
    n_steps = sum(1 for line in steps_file.read_text().splitlines() if line.strip())
    if not n_steps:
        return []
    stale: list[Path] = []
    for camera in ("agentview", "wrist"):
        directory = episode / "camera" / camera
        if not directory.is_dir():
            continue
        frames = sorted(directory.glob("step_*.png"))
        if not frames:
            continue
        kept = [f for f in frames if int(f.stem.split("_")[1]) <= n_steps]
        newest_kept = max((f.stat().st_mtime for f in kept), default=0.0)
        for frame in frames:
            index = int(frame.stem.split("_")[1])
            if index <= n_steps:
                continue
            # The terminal frame is legitimate only if this run wrote it.
            if index == n_steps + 1 and frame.stat().st_mtime >= newest_kept:
                continue
            stale.append(frame)
    return stale


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", default="pilot_v0")
    parser.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    episodes_root = PROJECT_ROOT / "rollouts" / "final" / args.pool / "episodes"
    affected = 0
    removed = 0
    for episode in sorted(p for p in episodes_root.iterdir() if p.is_dir()):
        stale = stale_frames(episode)
        if not stale:
            continue
        affected += 1
        removed += len(stale)
        print(f"{episode.name}: {len(stale)} лишних кадров")
        if args.delete:
            for frame in stale:
                frame.unlink()
    verb = "удалено" if args.delete else "нашлось (запустите с --delete)"
    print(f"\n{affected} эпизодов, {removed} кадров {verb}")


if __name__ == "__main__":
    main()
