"""Shared Flask scaffold for every per-model inference server.

Each concrete model server (openvla_oft_server.py, lerobot_server.py,
greenvla_server.py) implements a `Backend` (load(checkpoint) once at
startup, predict(instruction, agentview, wrist, proprioception) -> action
list) and calls `serve(backend, port)`. See
.claude/skills/slava-model-rollouts/SKILL.md for the per-model checkpoint
registry and why each model gets its own conda env / process.
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path
from typing import Any, Optional, Protocol

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from flask import Flask, jsonify, request  # noqa: E402

from slava_rollout.imaging import decode_png_b64  # noqa: E402


class Backend(Protocol):
    display_name: str
    checkpoint: str

    def predict(self, instruction: str, obs: dict[str, Any], meta: dict[str, Any]) -> list[float]:
        """`obs` is the env-worker's raw obs dict, decoded (agentview_rgb/wrist_rgb
        already replaced by decoded numpy arrays under the same keys) plus
        whatever env-specific extras (proprioception, ee_pose, gripper_closedness)
        the env-worker sent — pick what your checkpoint needs, ignore the rest.
        `meta` carries {task_uid, suite, environment} episode context."""
        ...

    # Optional: a backend that supports open-loop action-chunk execution (e.g.
    # OpenVLA-OFT, trained/evaluated with `num_open_loop_steps` action replay —
    # see openvla_oft_server.py) can implement this to return the FULL predicted
    # chunk instead of just the first action. Not part of the Protocol (most
    # backends don't have it) — serve() below falls back to a 1-action chunk
    # via plain predict() when it's absent, so this is fully opt-in and doesn't
    # change behavior for any backend that doesn't define it.
    # def predict_chunk(self, instruction: str, obs: dict[str, Any], meta: dict[str, Any]) -> list[list[float]]: ...


def serve(backend: Backend, port: int) -> None:
    app = Flask(__name__)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"ok": True, "model": backend.display_name, "checkpoint": backend.checkpoint})

    @app.route("/predict", methods=["POST"])
    def predict():
        payload = request.get_json(force=True)
        try:
            obs = dict(payload["obs"])
            obs["agentview_rgb"] = decode_png_b64(obs["agentview_rgb"])
            obs["wrist_rgb"] = decode_png_b64(obs["wrist_rgb"]) if obs.get("wrist_rgb") else None
            action = backend.predict(
                instruction=payload["instruction"], obs=obs, meta=payload.get("meta", {})
            )
            return jsonify({"action": list(action)})
        except Exception as exc:  # noqa: BLE001 — surface full traceback to the orchestrator's log
            return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500

    @app.route("/predict_chunk", methods=["POST"])
    def predict_chunk():
        payload = request.get_json(force=True)
        try:
            obs = dict(payload["obs"])
            obs["agentview_rgb"] = decode_png_b64(obs["agentview_rgb"])
            obs["wrist_rgb"] = decode_png_b64(obs["wrist_rgb"]) if obs.get("wrist_rgb") else None
            kwargs = dict(instruction=payload["instruction"], obs=obs, meta=payload.get("meta", {}))
            if hasattr(backend, "predict_chunk"):
                chunk = backend.predict_chunk(**kwargs)
            else:
                chunk = [backend.predict(**kwargs)]
            return jsonify({"action_chunk": [list(a) for a in chunk]})
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc), "traceback": traceback.format_exc()}), 500

    app.run(host="127.0.0.1", port=port, threaded=False)


def base_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=str, required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--device", type=str, default="cuda")
    return parser
