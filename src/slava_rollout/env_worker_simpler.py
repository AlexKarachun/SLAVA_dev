"""SimplerEnv/bridge env-worker HTTP service. Runs inside the `slava-simpler`
conda env (Python 3.10 / numpy 1.24.4 pinned / ManiSkill2_real2sim+SAPIEN —
see .claude/skills/slava-model-rollouts/SKILL.md before touching this file).

Usage: conda run -n slava-simpler python -m slava_rollout.env_worker_simpler --port 8702
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

from slava_rollout.contacts import SimplerContactTracker  # noqa: E402
from slava_rollout.imaging import encode_png_b64  # noqa: E402

os.environ.setdefault("MUJOCO_GL", "egl")

app = Flask(__name__)

STATE: dict[str, Any] = {"env": None, "tracker": None, "step_count": 0}


def _ee_pose_xyzquat(env: Any) -> list[float]:
    """WidowX end-effector world pose as [x,y,z,qw,qx,qy,qz].

    BridgeData-style models (GreenVLA, and likely the lerobot bridge policies
    for pi0/pi0.5/SmolVLA — see slava-model-rollouts SKILL.md) expect
    proprioception as EE pose, not joint qpos. `ee_gripper_link` matches the
    link name used by WidowX's own action space (see
    ManiSkill2_real2sim/agents/robots/widowx.py Actor list).
    """
    for link in env.agent.robot.get_links():
        if link.get_name() == "ee_gripper_link":
            pose = link.get_pose()
            return [*pose.p.tolist(), *pose.q.tolist()]
    raise RuntimeError("ee_gripper_link not found on WidowX robot")


def _build_obs(raw_obs: dict[str, Any], env: Any) -> dict[str, Any]:
    rgb = np.asarray(raw_obs["image"]["3rd_view_camera"]["rgb"])[..., :3]
    qpos = np.asarray(env.agent.robot.get_qpos(), dtype=float)
    closedness = float(np.mean(env.agent.get_gripper_closedness()))
    proprio = np.concatenate([qpos, [closedness]]).tolist()
    return {
        "agentview_rgb": encode_png_b64(rgb),
        "wrist_rgb": None,
        "proprioception": proprio,
        "ee_pose": _ee_pose_xyzquat(env),
        "gripper_closedness": closedness,
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
    return jsonify({"ok": True, "environment": "SimplerEnv"})


@app.route("/reset", methods=["POST"])
def reset():
    import simpler_env

    payload = request.get_json(force=True)
    task_name = payload["task_name"]
    episode_id = payload.get("episode_id", 0)
    reset_seed = payload.get("reset_seed", 0)

    _close_current()

    env = simpler_env.make(task_name)
    obs, reset_info = env.reset(
        seed=reset_seed, options={"obj_init_options": {"episode_id": episode_id}}
    )

    unwrapped = env.unwrapped
    actor_map = {actor.name: actor.name for actor in unwrapped.episode_objs}
    tracker = SimplerContactTracker(unwrapped, actor_map)

    STATE["env"] = env
    STATE["tracker"] = tracker
    STATE["step_count"] = 0

    return jsonify({"obs": _build_obs(obs, unwrapped), "done": False})


@app.route("/step", methods=["POST"])
def step():
    env = STATE.get("env")
    tracker: Optional[SimplerContactTracker] = STATE.get("tracker")
    if env is None:
        return jsonify({"error": "call /reset first"}), 400

    payload = request.get_json(force=True)
    action = np.asarray(payload["action"], dtype=np.float32)
    obs, reward, terminated, truncated, info = env.step(action)
    tracker.step()
    STATE["step_count"] += 1

    unwrapped = env.unwrapped
    object_poses = {
        actor.name: np.asarray(actor.pose.p, dtype=float).tolist()
        for actor in unwrapped.episode_objs
    }

    return jsonify(
        {
            "obs": _build_obs(obs, unwrapped),
            "reward": float(reward),
            "done": bool(terminated or truncated),
            "info": {
                "success": bool(info.get("success", False)),
                "first_contact_object": tracker.first_contact_object,
                "touched_objects": sorted(tracker.forbidden_touched),
                "object_poses": object_poses,
                "gripper_state": float(np.mean(unwrapped.agent.get_gripper_closedness())),
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
    parser.add_argument("--port", type=int, default=8702)
    args = parser.parse_args()
    app.run(host="127.0.0.1", port=args.port, threaded=False)


if __name__ == "__main__":
    main()
