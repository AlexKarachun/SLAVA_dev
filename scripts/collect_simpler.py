#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import imageio.v3 as iio
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import append_jsonl, load_jsonl  # noqa: E402
from slava_inventory.schema import is_technical_object, validate_inventory_record  # noqa: E402


TASKS = (
    "widowx_spoon_on_towel",
    "widowx_carrot_on_plate",
    "widowx_stack_cube",
    "widowx_put_eggplant_in_basket",
)


def git_commit(repository: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()


def actor_record(actor: Any) -> dict[str, Any]:
    raw_name = str(actor.name)
    return {
        "sim_handle": raw_name,
        "raw_name": raw_name,
        "pose_xyz": np.asarray(actor.pose.p, dtype=float).tolist(),
        "visible_agentview": None,
        "visible_wrist": None,
    }


def collect(args: argparse.Namespace) -> None:
    simpler_repo = args.simpler_repo.resolve()
    output_root = args.output_root.resolve()
    manifest = output_root / "simpler_inventory.jsonl"
    errors = output_root / "collection_errors.jsonl"
    if args.overwrite:
        manifest.unlink(missing_ok=True)
    existing = {row["task_uid"] for row in load_jsonl(manifest)}

    import simpler_env

    commit = git_commit(simpler_repo)
    for task_name in args.tasks:
        env = None
        try:
            env = simpler_env.make(task_name)
            gym_env_name = simpler_env.ENVIRONMENT_MAP[task_name][0]
            for episode_id in args.episode_ids:
                uid = f"simpler__{task_name}__episode{episode_id:03d}__seed{args.reset_seed:03d}"
                if uid in existing:
                    print(f"[skip] {uid}", flush=True)
                    continue
                try:
                    obs, reset_info = env.reset(
                        seed=args.reset_seed,
                        options={"obj_init_options": {"episode_id": episode_id}},
                    )
                    unwrapped = env.unwrapped
                    rgb = np.asarray(obs["image"]["3rd_view_camera"]["rgb"])[..., :3]
                    relative_agent = Path("images") / "simpler" / f"{uid}__agentview.png"
                    (output_root / relative_agent).parent.mkdir(parents=True, exist_ok=True)
                    iio.imwrite(output_root / relative_agent, rgb)

                    objects = []
                    for actor in unwrapped.episode_objs:
                        if is_technical_object(actor.name, actor.name):
                            continue
                        objects.append(actor_record(actor))
                    if hasattr(unwrapped, "sink"):
                        objects.append(actor_record(unwrapped.sink))

                    source_handle = str(unwrapped.episode_source_obj.name)
                    destination_handle = str(unwrapped.episode_target_obj.name)
                    language_reference = (
                        None
                        if is_technical_object(destination_handle, destination_handle)
                        else destination_handle
                    )
                    record = {
                        "task_uid": uid,
                        "suite": "simpler_bridge",
                        "task_id": TASKS.index(task_name),
                        "canonical_en": unwrapped.get_language_instruction(),
                        "source": {
                            "environment": "SimplerEnv",
                            "commit": commit,
                            "task_name": task_name,
                            "gym_env_name": gym_env_name,
                            "episode_id": int(reset_info.get("episode_id", episode_id)),
                            "reset_seed": args.reset_seed,
                        },
                        "images": {
                            "agentview_rgb": str(relative_agent),
                            "wrist_rgb": None,
                        },
                        "objects_raw": objects,
                        "success_predicates": [
                            {
                                "type": "src_on_target",
                                "source": source_handle,
                                "target": destination_handle,
                            }
                        ],
                        "candidate_slots": {
                            "action": "stack" if "stack" in task_name else "place",
                            "target": source_handle,
                            "reference": language_reference,
                            "relation": "on" if "basket" not in task_name else "in",
                            "forbidden_candidates": [],
                        },
                        "usable_for_slava": None,
                        "notes": "",
                    }
                    validate_inventory_record(record)
                    append_jsonl(record, manifest)
                    existing.add(uid)
                    print(f"[saved] {uid}", flush=True)
                except Exception as exc:
                    append_jsonl(
                        {
                            "collector": "simpler",
                            "task_uid": uid,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                        errors,
                    )
                    print(f"[error] {uid}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
                    if args.fail_fast:
                        raise
        finally:
            if env is not None:
                env.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--simpler-repo",
        type=Path,
        default=Path(os.environ.get("SIMPLERENV_ROOT", PROJECT_ROOT.parent / "SimplerEnv")),
    )
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--tasks", nargs="+", choices=TASKS, default=list(TASKS))
    parser.add_argument("--episode-ids", type=int, nargs="+", default=[0, 8, 16])
    parser.add_argument("--reset-seed", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    collect(parse_args())
