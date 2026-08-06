"""Thin HTTP clients the orchestrator (scripts/run_rollouts.py) uses to talk to
env-workers and model-servers. Runs from the slava-notebook env (only needs
`requests`) — see .claude/skills/slava-model-rollouts/SKILL.md.
"""
from __future__ import annotations

import time
from typing import Any

import requests


def wait_for_health(base_url: str, timeout_s: float = 180.0) -> None:
    deadline = time.monotonic() + timeout_s
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            resp = requests.get(f"{base_url}/health", timeout=5)
            if resp.ok and resp.json().get("ok"):
                return
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(2)
    raise TimeoutError(f"{base_url} did not become healthy in {timeout_s}s: {last_error}")


class EnvClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def reset(self, payload: dict[str, Any]) -> dict[str, Any]:
        resp = requests.post(f"{self.base_url}/reset", json=payload, timeout=120)
        resp.raise_for_status()
        return resp.json()

    def step(self, action: list[float]) -> dict[str, Any]:
        resp = requests.post(f"{self.base_url}/step", json={"action": action}, timeout=60)
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        try:
            requests.post(f"{self.base_url}/close", timeout=10)
        except requests.RequestException:
            pass


class ModelClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def reset(self) -> None:
        """Tell the model-server a new episode is starting.

        Must be called after every env reset: a model-server process serves
        many episodes, and a policy holding per-episode state (lerobot's
        internal action queue) would otherwise carry the previous episode's
        instruction and observation into the next one. See base_server.py's
        `/reset` for the full rationale.
        """
        resp = requests.post(f"{self.base_url}/reset", timeout=60)
        resp.raise_for_status()

    def predict(self, instruction: str, obs: dict[str, Any], meta: dict[str, Any]) -> list[float]:
        """`obs` is the env-worker's raw obs dict (agentview_rgb, wrist_rgb,
        proprioception, and env-specific extras like ee_pose/gripper_closedness
        for SimplerEnv) — passed through as-is so each model-server backend can
        pick the fields its checkpoint actually needs. `meta` carries episode
        context (task_uid, suite, environment) that a handful of checkpoints
        need beyond the raw observation — e.g. OpenVLA-OFT's `unnorm_key`
        selection is keyed by LIBERO suite name (libero_spatial/object/goal),
        not something derivable from pixels/proprio alone.
        """
        resp = requests.post(
            f"{self.base_url}/predict",
            json={
                "instruction": instruction,
                "images": {"agentview": obs["agentview_rgb"], "wrist": obs.get("wrist_rgb")},
                "obs": obs,
                "meta": meta,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["action"]

    def predict_chunk(self, instruction: str, obs: dict[str, Any], meta: dict[str, Any]) -> list[list[float]]:
        """Like `predict`, but returns the backend's full predicted action chunk
        (length 1 for backends without open-loop chunk support — see
        base_server.py's `/predict_chunk` fallback). The orchestrator drains
        this queue one env-step at a time before requesting a new chunk, which
        is what makes this real open-loop replay for backends that support it
        (currently OpenVLA-OFT) and a no-op-equivalent re-prediction-every-step
        for backends that don't (unchanged behavior)."""
        resp = requests.post(
            f"{self.base_url}/predict_chunk",
            json={
                "instruction": instruction,
                "images": {"agentview": obs["agentview_rgb"], "wrist": obs.get("wrist_rgb")},
                "obs": obs,
                "meta": meta,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["action_chunk"]
