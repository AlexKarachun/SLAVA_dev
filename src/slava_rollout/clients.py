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
