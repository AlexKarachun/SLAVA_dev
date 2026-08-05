#!/usr/bin/env python3
"""Orchestrator for the first SLAVA model rollouts (see
.claude/skills/slava-model-rollouts/SKILL.md for the full architecture).

Run from the `slava-notebook` conda env (only needs `requests`+stdlib — the
heavy per-model/per-env stacks live in their own conda envs, started as
subprocesses by this script).

Usage:
    conda run -n slava-notebook python scripts/run_rollouts.py \
        --models openvla_oft pi0 --smoke-test

    conda run -n slava-notebook python scripts/run_rollouts.py   # full 5-model x 127-prompt run
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
# Sibling-directory convention for third-party sim/model repos (LIBERO,
# SimplerEnv, ...), same default as scripts/bootstrap*.sh's SLAVA_DEPS_DIR:
# they live next to this repo, not at a machine-specific absolute path.
# Override per-repo with LIBERO_ROOT/SIMPLERENV_ROOT, or all at once with
# SLAVA_DEPS_DIR.
DEPS_DIR = Path(os.environ.get("SLAVA_DEPS_DIR", str(PROJECT_ROOT.parent)))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_rollout.auto_label import label_episode  # noqa: E402
from slava_rollout.clients import EnvClient, ModelClient, wait_for_health  # noqa: E402
from slava_rollout.schema import (  # noqa: E402
    MAX_EPISODE_STEPS,
    MODEL_REGISTRY,
    build_run_id,
    checkpoint_for,
    environments_for_model,
)
from slava_rollout.storage import (  # noqa: E402
    append_annotation,
    camera_dir,
    ensure_episode_dirs,
    load_completed_run_ids,
    run_log_path,
    steps_path,
)
from slava_rollout.imaging import decode_png_b64, save_png  # noqa: E402

CONDA_BIN = os.environ.get("CONDA_EXE", "/opt/miniforge3/bin/conda")

# Ports overridable via env var so a second, independent `run_rollouts.py`
# process can run concurrently against the same environment without two
# clients racing the same env-worker's global mutable STATE (reset/step
# would interleave and corrupt each other's episode). Each env-worker
# instance is single-episode-at-a-time by design (see contacts.py/env_worker
# module docstrings) — concurrency is achieved by running a second *instance*
# on a second port, not by making one instance thread-safe.
ENV_WORKER_SPEC = {
    "LIBERO": {
        "conda_env": "slava-libero", "module": "slava_rollout.env_worker_libero",
        "port": int(os.environ.get("SLAVA_LIBERO_PORT", 8701)),
    },
    "SimplerEnv": {
        "conda_env": "slava-simpler", "module": "slava_rollout.env_worker_simpler",
        "port": int(os.environ.get("SLAVA_SIMPLERENV_PORT", 8702)),
    },
}

# Default ports, overridable per model_key via SLAVA_MODEL_PORT_<MODEL_KEY_UPPER>
# (e.g. SLAVA_MODEL_PORT_OPENVLA_OFT=8813) — needed so multiple concurrent
# run_rollouts.py processes running the SAME model (multi-GPU sharding, see
# --shard-index/--num-shards) don't collide on one hardcoded port. Mirrors the
# existing SLAVA_LIBERO_PORT/SLAVA_SIMPLERENV_PORT pattern for env-workers.
_DEFAULT_MODEL_PORTS = {
    "greenvla_r0": 8801,
    "greenvla_r1_bridge": 8802,
    "openvla_oft": 8803,
    "pi0": 8804,
    "pi05": 8805,
    "smolvla": 8806,
    "greenvla_r2_bridge": 8807,
}

MODEL_SERVER_SPEC = {
    "greenvla_r0": {"conda_env": "slava-greenvla", "script": "greenvla_server.py"},
    "greenvla_r1_bridge": {"conda_env": "slava-greenvla", "script": "greenvla_server.py"},
    "openvla_oft": {"conda_env": "slava-openvla", "script": "openvla_oft_server.py"},
    "pi0": {"conda_env": "slava-lerobot", "script": "lerobot_server.py"},
    "pi05": {"conda_env": "slava-lerobot", "script": "lerobot_server.py"},
    "smolvla": {"conda_env": "slava-lerobot", "script": "lerobot_server.py"},
    "greenvla_r2_bridge": {"conda_env": "slava-greenvla", "script": "greenvla_server.py"},
}
for _key, _default_port in _DEFAULT_MODEL_PORTS.items():
    MODEL_SERVER_SPEC[_key]["port"] = int(
        os.environ.get(f"SLAVA_MODEL_PORT_{_key.upper()}", _default_port)
    )


def load_prompts() -> list[dict[str, Any]]:
    path = PROJECT_ROOT / "data" / "pilot_v0_release" / "prompts_v0.jsonl"
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_frames() -> dict[str, dict[str, Any]]:
    path = PROJECT_ROOT / "data" / "pilot_v0_release" / "frames_v0.jsonl"
    frames = {}
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            frames[record["task_uid"]] = record
    return frames


def start_subprocess(cmd: list[str], log_path: Path, env_overrides: dict[str, str]) -> subprocess.Popen:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_file = open(log_path, "a")
    env = {**os.environ, **env_overrides}
    # start_new_session=True (setsid) makes this process the leader of its own
    # process group, so stop_process() below can signal the WHOLE group —
    # required because `conda run <cmd>` does not reliably forward SIGTERM to
    # the actual model-server/env-worker python process it launches.
    # Confirmed the hard way: proc.terminate() on just the conda-run PID left
    # a 7B-checkpoint model-server running for hours after its orchestrator
    # had already exited, silently holding GPU memory.
    return subprocess.Popen(
        cmd, stdout=log_file, stderr=subprocess.STDOUT, env=env, start_new_session=True
    )


def stop_process(proc: subprocess.Popen, timeout_s: float = 15.0) -> None:
    if proc.poll() is not None:
        return
    try:
        pgid = os.getpgid(proc.pid)
        os.killpg(pgid, signal.SIGTERM)
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


class WorkerPool:
    """Starts/reuses env-worker and model-server subprocesses, one at a time
    per (environment) / (model), matching the sequential-run design in
    SKILL.md (n=1 repeats, no need for concurrent workers)."""

    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.processes: dict[str, subprocess.Popen] = {}
        self.env_clients: dict[str, EnvClient] = {}
        self.model_clients: dict[str, ModelClient] = {}

    def env_client(self, environment: str) -> EnvClient:
        if environment in self.env_clients:
            return self.env_clients[environment]
        spec = ENV_WORKER_SPEC[environment]
        cmd = [
            CONDA_BIN, "run", "--no-capture-output", "-n", spec["conda_env"],
            "python", "-m", spec["module"], "--port", str(spec["port"]),
        ]
        env_overrides = {"PYTHONPATH": str(PROJECT_ROOT / "src")}
        if environment == "LIBERO":
            env_overrides["LIBERO_ROOT"] = os.environ.get("LIBERO_ROOT", str(DEPS_DIR / "LIBERO"))
        else:
            env_overrides["SIMPLERENV_ROOT"] = os.environ.get(
                "SIMPLERENV_ROOT", str(DEPS_DIR / "SimplerEnv")
            )
        # Port in the log filename (not just environment/model_key) so
        # multiple concurrent run_rollouts.py shards (multi-GPU sharding, see
        # --shard-index/--num-shards) each get their own log file instead of
        # interleaving writes into the same one.
        proc = start_subprocess(cmd, self.logs_dir / f"env_worker_{environment}_{spec['port']}.log", env_overrides)
        self.processes[f"env:{environment}"] = proc
        base_url = f"http://127.0.0.1:{spec['port']}"
        wait_for_health(base_url)
        client = EnvClient(base_url)
        self.env_clients[environment] = client
        return client

    def model_client(self, model_key: str, checkpoint: str) -> ModelClient:
        if model_key in self.model_clients:
            return self.model_clients[model_key]
        spec = MODEL_SERVER_SPEC[model_key]
        script_path = PROJECT_ROOT / "scripts" / "model_servers" / spec["script"]
        cmd = [
            CONDA_BIN, "run", "--no-capture-output", "-n", spec["conda_env"],
            "python", str(script_path), "--checkpoint", checkpoint, "--port", str(spec["port"]),
        ]
        env_overrides = {"PYTHONPATH": str(PROJECT_ROOT / "src")}
        proc = start_subprocess(cmd, self.logs_dir / f"model_server_{model_key}_{spec['port']}.log", env_overrides)
        self.processes[f"model:{model_key}"] = proc
        base_url = f"http://127.0.0.1:{spec['port']}"
        wait_for_health(base_url, timeout_s=600.0)  # model weights download/load can be slow
        client = ModelClient(base_url)
        self.model_clients[model_key] = client
        return client

    def stop_model(self, model_key: str) -> None:
        """Tear down a model-server once its model's episodes are done.

        Model checkpoints range from ~0.5B (SmolVLA) to ~7B (OpenVLA-OFT)
        params; this server's single V100 has 32GB total. Keeping every
        model-server this process ever started resident for the whole run
        (the naive read of "cache by model_key forever") risks OOM once 3+
        models have been touched — so a multi-model invocation of this script
        unloads each model right after its episodes finish, not at final
        pool.stop_all(). Env-workers (no large weights) are left running.
        """
        proc = self.processes.pop(f"model:{model_key}", None)
        self.model_clients.pop(model_key, None)
        if proc is not None:
            stop_process(proc, timeout_s=30.0)

    def stop_all(self) -> None:
        for key, client in list(self.env_clients.items()):
            client.close()
        for key, proc in self.processes.items():
            stop_process(proc, timeout_s=15.0)


# Physics-settle steps before the first policy query, per model. openvla_oft
# matches openvla-oft's own run_libero_eval.py `num_steps_wait=10`. Extended
# 2026-08-05 to pi0/pi05/smolvla too, after independently confirming
# huggingface/lerobot's OWN reference LiberoEnv (src/lerobot/envs/libero.py)
# defaults to the identical `num_steps_wait: int = 10` — same convention, not
# a guess. Found while investigating a real pattern: all 3 lerobot models
# stuck on `no_action_or_timeout` on the same LIBERO_goal scene that
# OpenVLA-OFT (which already had this fix) succeeded on repeatedly.
LIBERO_NUM_STEPS_WAIT = {"openvla_oft": 10, "pi0": 10, "pi05": 10, "smolvla": 10}


def build_reset_payload(prompt: dict[str, Any], model_key: str) -> dict[str, Any]:
    if prompt["environment"] == "LIBERO":
        return {
            "bddl_file": prompt["bddl_file"],
            "suite": prompt["suite"],
            "task_name": prompt["task_name"],
            "init_state_id": prompt["init_state_id"],
            "reset_seed": prompt.get("reset_seed") or 0,
            "num_steps_wait": LIBERO_NUM_STEPS_WAIT.get(model_key, 0),
        }
    return {
        "task_name": prompt["task_name"],
        "episode_id": prompt["episode_id"],
        "reset_seed": prompt.get("reset_seed") or 0,
    }


def run_episode(
    pool: WorkerPool,
    model_key: str,
    prompt: dict[str, Any],
    seed: int,
) -> dict[str, Any]:
    environment = prompt["environment"]
    checkpoint = checkpoint_for(model_key, environment)
    env_client = pool.env_client(environment)
    model_client = pool.model_client(model_key, checkpoint)

    run_id = build_run_id(model_key, prompt["prompt_id"], seed)
    has_wrist = environment == "LIBERO"
    ensure_episode_dirs(run_id, has_wrist)
    steps_file = steps_path(run_id)
    max_steps = MAX_EPISODE_STEPS[environment]

    reset_resp = env_client.reset(build_reset_payload(prompt, model_key))
    obs = reset_resp["obs"]
    meta = {"task_uid": prompt["task_uid"], "suite": prompt.get("suite"), "environment": environment}

    touched_objects: set[str] = set()
    first_contact_object: Optional[str] = None
    final_object_poses: dict[str, list[float]] = {}
    env_success = False
    step_count = 0
    # Action-chunk queue: drained one env-step at a time; refilled by a new
    # /predict_chunk call once empty. Length 1 for every backend except
    # OpenVLA-OFT (see clients.py::predict_chunk / openvla_oft_server.py) —
    # so this is a no-op-equivalent for the other 4 models (still one predict
    # call per env step, unchanged behavior), and real open-loop chunk replay
    # only for OpenVLA-OFT.
    pending_actions: list[list[float]] = []

    with open(steps_file, "a", encoding="utf-8") as steps_handle:
        for step_count in range(1, max_steps + 1):
            save_png(decode_png_b64(obs["agentview_rgb"]), camera_dir(run_id, "agentview") / f"step_{step_count:04d}.png")
            if has_wrist and obs.get("wrist_rgb"):
                save_png(decode_png_b64(obs["wrist_rgb"]), camera_dir(run_id, "wrist") / f"step_{step_count:04d}.png")

            if not pending_actions:
                pending_actions = list(model_client.predict_chunk(prompt["instruction"], obs, meta))
            action = pending_actions.pop(0)
            step_resp = env_client.step(action)
            obs = step_resp["obs"]
            info = step_resp["info"]

            touched_objects.update(info.get("touched_objects", []))
            if first_contact_object is None:
                first_contact_object = info.get("first_contact_object")
            final_object_poses = info.get("object_poses", final_object_poses)
            env_success = info.get("success", False)

            steps_handle.write(
                json.dumps(
                    {
                        "run_id": run_id,
                        "step": step_count,
                        "task_uid": prompt["task_uid"],
                        "variant": prompt["variant"],
                        "instruction": prompt["instruction"],
                        "seed": seed,
                        "model": model_key,
                        "action": list(action),
                        "gripper_state": info.get("gripper_state"),
                        "object_poses": final_object_poses,
                        "contacts": info.get("touched_objects", []),
                        "success_so_far": env_success,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

            if step_resp.get("done") or env_success:
                break

    env_client.close()

    label = label_episode(
        env_success=env_success,
        first_contact_object=first_contact_object,
        touched_objects=sorted(touched_objects),
        target_object=prompt.get("target_object"),
        reference_object=prompt.get("reference_object"),
        forbidden_objects=prompt.get("forbidden_objects") or [],
        relation=prompt.get("relation"),
        action=prompt.get("action"),
        final_object_poses=final_object_poses,
        success_predicates=prompt.get("success_predicates") or [],
        step_count=step_count,
        max_steps=max_steps,
    )

    record = {
        "run_id": run_id,
        "model": MODEL_REGISTRY[model_key]["display_name"],
        "task_uid": prompt["task_uid"],
        "variant": prompt["variant"],
        "instruction": prompt["instruction"],
        "seed": seed,
        "notes": "",
        **label,
        "target_object": prompt.get("target_object"),
        "reference_object": prompt.get("reference_object"),
    }
    append_annotation(record)
    return record


def select_prompts(
    prompts: list[dict[str, Any]], model_key: str, smoke_test: bool
) -> list[dict[str, Any]]:
    envs = environments_for_model(model_key)
    filtered = [p for p in prompts if p["environment"] in envs]
    if not smoke_test:
        return filtered
    # smoke-test: 2 task_uids, en_canonical only (SKILL.md "Smoke test"). For a
    # model that runs on both environments (pi0/pi05/smolvla), 2-scenes-total-
    # in-file-order would silently pick 2 LIBERO scenes and never exercise the
    # SimplerEnv code path (different checkpoint, different obs shape) before
    # the full run — so split 1 scene per environment when there's more than
    # one, else take 2 from the model's single environment.
    seen_task_uids: list[str] = []
    per_env_quota = 1 if len(envs) > 1 else 2
    for environment in envs:
        count = 0
        for p in filtered:
            if p["environment"] != environment:
                continue
            if p["task_uid"] not in seen_task_uids:
                seen_task_uids.append(p["task_uid"])
                count += 1
            if count >= per_env_quota:
                break
    return [p for p in filtered if p["task_uid"] in seen_task_uids and p["variant"] == "en_canonical"]


def _handle_sigterm(signum: int, frame: Any) -> None:
    # A bare SIGTERM to this process does NOT run `finally` blocks (unlike a
    # caught exception) — found 2026-08-05 manually stopping a shard during
    # multi-GPU rebalancing: the orchestrator died but its env-worker/model-
    # server children (each its own process group via start_new_session=True,
    # see start_subprocess()) were left orphaned holding GPU memory, same
    # symptom as the `conda run` signal-forwarding bug this file already works
    # around, just via a different mechanism. Translating SIGTERM into
    # SystemExit here makes main()'s `finally: pool.stop_all()` actually run,
    # so `kill <pid>` (or the user's own Ctrl+C during a real run) cleans up
    # properly instead of requiring a manual `kill -TERM -<pgid>` per child.
    raise SystemExit(143)  # 128 + SIGTERM(15), conventional exit code


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_sigterm)
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="+", choices=list(MODEL_REGISTRY.keys()), default=list(MODEL_REGISTRY.keys()))
    parser.add_argument("--smoke-test", action="store_true", help="2 scenes/model, en_canonical only")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--num-shards", type=int, default=1,
        help="Split each model's selected episodes across N independent processes for "
             "multi-GPU parallelism. Each shard must be launched as its own process with "
             "a distinct --shard-index, a distinct CUDA_VISIBLE_DEVICES, and distinct "
             "SLAVA_LIBERO_PORT/SLAVA_SIMPLERENV_PORT/SLAVA_MODEL_PORT_<KEY> env vars "
             "(else concurrent env-worker/model-server instances collide — see SKILL.md).",
    )
    parser.add_argument("--shard-index", type=int, default=0, help="This process's shard, in [0, num_shards).")
    args = parser.parse_args()
    if not (0 <= args.shard_index < args.num_shards):
        parser.error("--shard-index must be in [0, num_shards)")

    prompts = load_prompts()
    completed = load_completed_run_ids()
    pool = WorkerPool(PROJECT_ROOT / "rollouts" / "logs")

    try:
        for model_key in args.models:
            selected = select_prompts(prompts, model_key, args.smoke_test)
            if args.num_shards > 1:
                # Round-robin by index: every row is an independent (task_uid,
                # variant) episode with its own reset/run_id, so any disjoint
                # partition is safe — no shard needs to see another's rows.
                selected = selected[args.shard_index :: args.num_shards]
            print(
                f"[{model_key}] {len(selected)} episodes selected"
                + (f" (shard {args.shard_index}/{args.num_shards})" if args.num_shards > 1 else ""),
                flush=True,
            )
            for prompt in selected:
                run_id = build_run_id(model_key, prompt["prompt_id"], args.seed)
                if run_id in completed:
                    print(f"[skip] {run_id} already in rollout_annotations.jsonl", flush=True)
                    continue
                t0 = time.monotonic()
                try:
                    record = run_episode(pool, model_key, prompt, args.seed)
                    print(
                        f"[done] {run_id} success={record['success']} "
                        f"failure={record['failure_type_auto']} ({time.monotonic() - t0:.1f}s)",
                        flush=True,
                    )
                except Exception as exc:  # noqa: BLE001
                    print(f"[error] {run_id}: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
            pool.stop_model(model_key)
    finally:
        pool.stop_all()


if __name__ == "__main__":
    main()
