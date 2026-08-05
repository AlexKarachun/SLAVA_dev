"""LIBERO env-worker HTTP service. Runs inside the `slava-libero` conda env
(pinned Python 3.8 / torch 1.11+cu113 / robosuite 1.4.0 — see
.claude/skills/slava-model-rollouts/SKILL.md before touching this file).

Usage: conda run -n slava-libero python -m slava_rollout.env_worker_libero --port 8701
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
from flask import Flask, jsonify, request

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_rollout.contacts import LiberoContactTracker  # noqa: E402
from slava_rollout.imaging import encode_png_b64  # noqa: E402

os.environ.setdefault("MUJOCO_GL", "egl")

app = Flask(__name__)

STATE: dict[str, Any] = {"env": None, "tracker": None, "step_count": 0}


def _libero_root() -> Path:
    return Path(os.environ.get("LIBERO_ROOT", PROJECT_ROOT.parent / "LIBERO"))


def _build_obs(raw_obs: dict[str, Any]) -> dict[str, Any]:
    agentview = np.asarray(raw_obs["agentview_image"])[::-1]
    wrist = np.asarray(raw_obs["robot0_eye_in_hand_image"])[::-1]
    proprio = np.concatenate(
        [raw_obs["robot0_gripper_qpos"], raw_obs["robot0_eef_pos"], raw_obs["robot0_eef_quat"]]
    ).astype(float)
    return {
        "agentview_rgb": encode_png_b64(agentview),
        "wrist_rgb": encode_png_b64(wrist),
        "proprioception": proprio.tolist(),
    }


def _close_current() -> None:
    env = STATE.get("env")
    if env is not None:
        try:
            env.close()
        except Exception:
            pass
    STATE["env"] = None
    STATE["tracker"] = None
    STATE["step_count"] = 0


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True, "environment": "LIBERO"})


@app.route("/reset", methods=["POST"])
def reset():
    from libero.libero.envs import OffScreenRenderEnv

    payload = request.get_json(force=True)
    bddl_file = payload["bddl_file"]
    init_state_id = payload.get("init_state_id", 0)
    image_size = payload.get("image_size", 256)
    reset_seed = payload.get("reset_seed", 0)

    _close_current()

    bddl_path = _libero_root() / bddl_file
    env = OffScreenRenderEnv(
        bddl_file_name=str(bddl_path),
        camera_names=["agentview", "robot0_eye_in_hand"],
        camera_heights=image_size,
        camera_widths=image_size,
    )
    env.seed(reset_seed)
    env.reset()

    # Resolve init states the same way scripts/collect_libero.py does: via the
    # benchmark suite's registered init-state file for this bddl task, not a
    # bespoke path guess.
    from libero.libero import benchmark

    suite_name = payload["suite"]
    task_name = payload["task_name"]
    suite = benchmark.get_benchmark_dict()[suite_name]()
    task_id = None
    for i in range(suite.get_num_tasks()):
        if suite.get_task(i).name == task_name:
            task_id = i
            break
    if task_id is None:
        _close_current()
        return jsonify({"error": f"task_name {task_name} not found in suite {suite_name}"}), 400
    init_states = suite.get_task_init_states(task_id)
    obs = env.set_init_state(init_states[init_state_id])

    # Optional physics-settle steps before the first obs is handed to a model,
    # matching openvla-oft's run_libero_eval.py `num_steps_wait` convention
    # ("Do nothing for the first few timesteps to let objects stabilize in
    # sim"), found 2026-08-05 while investigating SR=0%. Uses their exact
    # dummy action [0,0,0,0,0,0,-1] (gripper held open, no motion). Opt-in via
    # payload (default 0 = previous behavior, unchanged for models that don't
    # request it) rather than a blanket change to every LIBERO episode for
    # every model — only the orchestrator decides which models need this.
    num_steps_wait = int(payload.get("num_steps_wait", 0))
    for _ in range(num_steps_wait):
        obs, _, _, _ = env.step(np.array([0, 0, 0, 0, 0, 0, -1], dtype=np.float32))

    obj_body_id = dict(env.env.obj_body_id)
    tracker = LiberoContactTracker(env, obj_body_id)

    STATE["env"] = env
    STATE["tracker"] = tracker
    STATE["obj_body_id"] = obj_body_id
    STATE["step_count"] = 0

    return jsonify({"obs": _build_obs(obs), "done": False})


@app.route("/step", methods=["POST"])
def step():
    env = STATE.get("env")
    tracker: Optional[LiberoContactTracker] = STATE.get("tracker")
    if env is None:
        return jsonify({"error": "call /reset first"}), 400

    payload = request.get_json(force=True)
    action = np.asarray(payload["action"], dtype=np.float32)
    obs, reward, done, info = env.step(action)
    tracker.step()
    STATE["step_count"] += 1

    object_poses = {
        handle: env.sim.data.body_xpos[body_id].astype(float).tolist()
        for handle, body_id in STATE["obj_body_id"].items()
    }
    success = bool(env.check_success())

    return jsonify(
        {
            "obs": _build_obs(obs),
            "reward": float(reward),
            "done": bool(done),
            "info": {
                "success": success,
                "first_contact_object": tracker.first_contact_object,
                "touched_objects": sorted(tracker.forbidden_touched),
                "object_poses": object_poses,
                "gripper_state": float(np.mean(obs["robot0_gripper_qpos"])),
                "step_count": STATE["step_count"],
            },
        }
    )


@app.route("/close", methods=["POST"])
def close():
    _close_current()
    return jsonify({"ok": True})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8701)
    args = parser.parse_args()
    app.run(host="127.0.0.1", port=args.port, threaded=False)


if __name__ == "__main__":
    main()
