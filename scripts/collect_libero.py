#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

import imageio.v3 as iio
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import append_jsonl, load_jsonl  # noqa: E402


SUITES = ("libero_spatial", "libero_object", "libero_goal")


def git_commit(repository: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(repository), "rev-parse", "HEAD"], text=True
    ).strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_record(env: Any, sim_handle: str, body: Any, kind: str) -> dict[str, Any]:
    body_id = env.env.obj_body_id[sim_handle]
    category = str(getattr(body, "category_name", sim_handle.rsplit("_", 1)[0]))
    return {
        "sim_handle": sim_handle,
        "raw_name": category,
        "category_en": category.replace("_", " "),
        "kind": kind,
        "pose_xyz": env.sim.data.body_xpos[body_id].astype(float).tolist(),
        "pose_quat_wxyz": env.sim.data.body_xquat[body_id].astype(float).tolist(),
        "visible_agentview": None,
        "visible_wrist": None,
        "lexicon_eligible": sim_handle not in {"main_table"},
    }


def collect(args: argparse.Namespace) -> None:
    libero_repo = args.libero_repo.resolve()
    output_root = args.output_root.resolve()
    manifest = output_root / "libero_inventory.jsonl"
    errors = output_root / "collection_errors.jsonl"

    if args.overwrite:
        manifest.unlink(missing_ok=True)
    existing = {row["task_uid"] for row in load_jsonl(manifest)}

    from libero.libero import benchmark
    from libero.libero.envs import OffScreenRenderEnv

    commit = git_commit(libero_repo)
    for suite_name in args.suites:
        suite = benchmark.get_benchmark_dict()[suite_name]()
        task_ids = args.task_ids if args.task_ids is not None else range(suite.get_num_tasks())
        for task_id in task_ids:
            if not 0 <= task_id < suite.get_num_tasks():
                raise ValueError(f"task_id {task_id} is invalid for {suite_name}")
            task = suite.get_task(task_id)
            bddl_path = Path(suite.get_task_bddl_file_path(task_id)).resolve()
            init_states = suite.get_task_init_states(task_id)
            for init_state_id in args.init_state_ids:
                uid = f"{suite_name}__{task.name}__init{init_state_id:03d}"
                if uid in existing:
                    print(f"[skip] {uid}", flush=True)
                    continue
                env = None
                try:
                    env = OffScreenRenderEnv(
                        bddl_file_name=str(bddl_path),
                        camera_names=["agentview", "robot0_eye_in_hand"],
                        camera_heights=args.image_size,
                        camera_widths=args.image_size,
                    )
                    env.seed(args.reset_seed)
                    env.reset()
                    obs = env.set_init_state(init_states[init_state_id])
                    for _ in range(args.settle_steps):
                        obs, _, _, _ = env.step(np.zeros(7, dtype=np.float32))

                    relative_agent = Path("images") / "libero" / f"{uid}__agentview.png"
                    relative_wrist = Path("images") / "libero" / f"{uid}__wrist.png"
                    (output_root / relative_agent).parent.mkdir(parents=True, exist_ok=True)
                    iio.imwrite(output_root / relative_agent, obs["agentview_image"][::-1])
                    iio.imwrite(output_root / relative_wrist, obs["robot0_eye_in_hand_image"][::-1])

                    objects = []
                    for handle, body in env.env.objects_dict.items():
                        objects.append(object_record(env, handle, body, "movable"))
                    for handle, body in env.env.fixtures_dict.items():
                        if handle in env.env.obj_body_id:
                            objects.append(object_record(env, handle, body, "fixture"))

                    parsed = env.env.parsed_problem
                    state = np.asarray(init_states[init_state_id])
                    record = {
                        "task_uid": uid,
                        "source": {
                            "environment": "LIBERO",
                            "repository": "LIBERO",
                            "repository_url": "https://github.com/Lifelong-Robot-Learning/LIBERO.git",
                            "root_env_var": "LIBERO_ROOT",
                            "commit": commit,
                        },
                        "suite": suite_name,
                        "task_id": task_id,
                        "task_name": task.name,
                        "init_state_id": init_state_id,
                        "canonical_en": task.language,
                        "bddl_file": str(bddl_path.relative_to(libero_repo)),
                        "bddl_sha256": sha256_file(bddl_path),
                        "init_state_sha256": hashlib.sha256(state.tobytes()).hexdigest(),
                        "init_state_shape": list(state.shape),
                        "render": {
                            "width": args.image_size,
                            "height": args.image_size,
                            "settle_steps": args.settle_steps,
                            "reset_seed": args.reset_seed,
                        },
                        "images": {
                            "agentview_rgb": str(relative_agent),
                            "wrist_rgb": str(relative_wrist),
                            "agentview_camera": "agentview",
                            "wrist_camera": "robot0_eye_in_hand",
                        },
                        "objects_raw": objects,
                        "initial_predicates": parsed.get("initial_state", []),
                        "success_predicates": parsed.get("goal_state", []),
                        "obj_of_interest": list(parsed.get("obj_of_interest", [])),
                        "candidate_slots": {
                            "action": None,
                            "target": None,
                            "reference": None,
                            "relation": None,
                            "forbidden_candidates": [],
                        },
                        "usable_for_slava": None,
                        "selected_for_v0": False,
                        "review_status": "pending",
                        "exclusion_reasons": [],
                        "notes": "",
                    }
                    append_jsonl(record, manifest)
                    existing.add(uid)
                    print(f"[saved] {uid}", flush=True)
                except Exception as exc:
                    append_jsonl(
                        {
                            "collector": "libero",
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
        "--libero-repo",
        type=Path,
        default=Path(os.environ.get("LIBERO_ROOT", PROJECT_ROOT.parent / "LIBERO")),
    )
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument("--suites", nargs="+", choices=SUITES, default=list(SUITES))
    parser.add_argument("--task-ids", type=int, nargs="+", default=None)
    parser.add_argument("--init-state-ids", type=int, nargs="+", default=[0, 17, 34])
    parser.add_argument("--reset-seed", type=int, default=0)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--settle-steps", type=int, default=0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    collect(parse_args())
