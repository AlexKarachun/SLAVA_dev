---
name: slava-model-rollouts
description: Shared architecture, contracts, and cross-model lessons for the SLAVA rollout pass (5 models x LIBERO/SimplerEnv), producing rollout_annotations.jsonl per task.md. Per-model debugging detail lives in slava-openvla-oft / slava-lerobot-policies / slava-greenvla.
---

# SLAVA model rollouts — implementation notes

**Split 2026-08-05** into this general skill (architecture, env-worker/
model-server contracts, process management, cross-model lessons) plus one
skill per model family, since the model-specific debugging history had
grown large enough to bury the shared material:

- `slava-openvla-oft` — OpenVLA-OFT API + its 4 found-and-fixed bugs.
- `slava-lerobot-policies` — pi0/pi0.5/SmolVLA (shared `lerobot_server.py`)
  API, cuDNN crash fix, and the camera-swap bug that was the real root
  cause of their near-0% SR on LIBERO.
- `slava-greenvla` — GreenVLA R0/R1/R2 (shared `greenvla_server.py`) API,
  embodiment/norm_stats check, and the gripper-range-mismatch fix.

Read this file first for the shared design, then whichever per-model skill
matches what you're actually touching.

Session: 2026-08-04, GPU server (Tesla V100-SXM2-32GB, driver 580.126.09,
CUDA 13.0 max — Volta, fp16 tensor cores yes, **bf16 no**). User explained
the plan, confirmed architecture and open-question answers in chat, then
left for ~1h and explicitly delegated remaining implementation decisions
("поставь себя на моё место, реши сам; отложи в беклог то, что реально
требует меня"). This doc is the durable record — read it before touching
`src/slava_rollout/` or `scripts/run_rollouts.py`.

## Why client-server, not one big script

`slava-libero` (Python 3.8.13, torch pinned to 1.11+cu113 by LIBERO's own
`requirements.txt`/robosuite) and `slava-simpler` (Python 3.10, numpy pinned
to 1.24.4 by SimplerEnv/ManiSkill2_real2sim) are the *rendering* envs from
`scripts/bootstrap.sh` — both intentionally frozen for MuJoCo/SAPIEN
compatibility, and mutually incompatible with each other and with any
modern VLA checkpoint's torch/transformers requirements. The 5 target
models also don't share one stack (GreenVLA needs a recent
transformers/Qwen3-VL; OpenVLA-OFT needs the openvla fork's pinned
transformers; lerobot needs its own recent torch). Trying to cram all of
this into `slava-libero`/`slava-simpler` would break rendering.

**Decision:** every environment and every model gets its own conda env and
runs as a standalone local HTTP service. An orchestrator (`scripts/
run_rollouts.py`, run from `slava-notebook` — the only env with no
conflicting pins, just needs `requests`) drives the episode loop by
calling two HTTP APIs:

```
env-worker   (one per environment: LIBERO port 8701, SimplerEnv port 8702)
  POST /reset {task_uid, bddl_file?, init_state_id?, gym_env_name?, episode_id?, reset_seed?}
       -> {obs: {agentview_rgb: base64 png, wrist_rgb: base64 png|null,
                 proprioception: [float,...]}, done: false}
  POST /step {action: [float,...]}
       -> {obs: {...}, reward, done, info: {success: bool,
                 contacts: [{gripper_geom, other_body, sim_handle|null}],
                 object_poses: {sim_handle: [x,y,z]}, gripper_state: float}}
  GET  /health -> {ok: true, environment: "LIBERO"}

model-server (one per model: ports 8801-8805, see registry below)
  POST /predict {instruction: str, images: {agentview: b64png, wrist: b64png|null},
                 proprioception: [float,...]}
       -> {action: [float,...]}
  GET  /health -> {ok: true, model: "pi0", checkpoint: "..."}
```

Considered `allenai/vla-evaluation-harness` (also client-server,
LIBERO+SimplerEnv, 13+ models) instead of building this — deliberately not
adopted: unclear whether it supports a fixed `init_state_id` + custom
instruction text per episode (that's our whole experimental design), and
it has its own SQLite log schema that would still need translating into
`rollout_annotations.jsonl`. Only the client-server *pattern* is borrowed
from it as validation the approach is standard, not its code.

## Repeats: n=1

User's explicit call, overriding my suggestion to split by action-head
type (deterministic vs stochastic). Rationale given: simplicity of the
comparison tables. Caveat for later: π0/π0.5/SmolVLA sample from a
flow-matching/diffusion action head, so their SR at n=1 may have more
variance than OpenVLA-OFT/GreenVLA's more deterministic decoding — flag
this if Δlang results for those three models look noisy.

## Model registry, checkpoints, environments

Source of truth in code: `src/slava_rollout/schema.py::MODEL_REGISTRY`.
Summary (checkpoints found via WebSearch/HF in the 2026-08-04 session,
re-verify if picked up much later):

| model_key | env(s) | checkpoint | zero-shot? |
| --- | --- | --- | --- |
| greenvla_r0 | SimplerEnv | `SberRoboticsCenter/GreenVLA-5b-base-stride-1` | no |
| greenvla_r1_bridge | SimplerEnv | `SberRoboticsCenter/GreenVLA-5b-stride-1-R1-bridge` | no |
| openvla_oft | LIBERO | `moojink/openvla-7b-oft-finetuned-libero-spatial-object-goal-10` | no |
| pi0 | LIBERO / SimplerEnv | `lerobot/pi0_libero_finetuned` / `lerobot/pi0_base` | no / **yes** |
| pi05 | LIBERO / SimplerEnv | `lerobot/pi05_libero_finetuned` / `lerobot/pi05_base` | no / **yes** |
| smolvla | LIBERO / SimplerEnv | `HuggingFaceVLA/smolvla_libero` / `lerobot/smolvla_base` | no / **yes** |

No official bridge/WidowX finetune exists for π0/π0.5/SmolVLA (one
unverified community one, `juexzz/INTACT-pi0-finetune-bridge`, not used).
**Risk accepted explicitly by the user:** these 3 models on SimplerEnv/
bridge run zero-shot on SAPIEN-rendered frames despite being pretrained on
real camera frames — floor-effect SR (near 0 regardless of language) is
possible; if the smoke test shows this, revisit before the full run rather
than reporting a meaningless Δlang for those 3×4 cells.

GreenVLA repo: `github.com/greenvla/GreenVLA` (public, HEAD
`952a80c` as of this session).

## Per-model conda envs

Each model-server gets its own env under `/opt/miniforge3/envs/` (or a
`venv` if pip-only is simpler) — do not reuse `slava-libero`/`slava-simpler`
for model weights:

- `slava-openvla` — openvla-oft's own pinned transformers/torch (see the
  openvla-oft repo's `requirements.txt`; it forks transformers for
  flash-attn action-head details, don't freelance the version).
- `slava-lerobot` — `pip install -e ".[libero]"` from the `huggingface/
  lerobot` repo. This single env serves pi0, pi0.5, and smolvla model-
  servers (same `PreTrainedPolicy.from_pretrained(checkpoint)` factory,
  just a different `checkpoint` string) **and** is the one used for the
  LIBERO-side env class mentioned below.
- `slava-greenvla` — GreenVLA's own repo requirements (Qwen3-VL backbone
  needs a recent transformers; confirm exact pin from
  `github.com/greenvla/GreenVLA/requirements.txt` when building this env,
  don't assume it matches lerobot's or openvla's transformers pin).

All model-server envs need `fastapi`/`flask` + `uvicorn` + `pillow` +
`requests` on top of the model's own stack, and `HF_TOKEN` (already in
`~/.bashrc` on this server — read it with
`export HF_TOKEN=$(awk -F'"' '/^export HF_TOKEN=/{print $2}' ~/.bashrc)`,
**never** `source ~/.bashrc` or `grep` with context lines: an earlier
attempt in this session did exactly that and leaked the raw token value
into tool output, the same class of mistake as the `DEEPL_API_KEY`
incident in `slava-mt-russian`. **User should consider rotating this HF
token** since its value briefly entered the session transcript.

## Shared env-worker design (one per environment, used by every model)

Originally planned per-model-family env duplication; corrected once the
actual upstream APIs were read: `lerobot`'s own `LiberoEnv`
(`src/lerobot/envs/libero.py`) turned out to be a thin gymnasium wrapper
around the exact same `libero.libero.envs.OffScreenRenderEnv` our own
`env_worker_libero.py` already drives (same `camera_names`, same
underlying robosuite env) — there is no separate "lerobot LIBERO physics"
to integrate, and no reason for a separate env-worker per model family.

**One shared env-worker per environment, used by every model that runs
there.** `env_worker_libero.py` (port 8701 default, in `slava-libero`)
serves OpenVLA-OFT and all three lerobot models on LIBERO alike.
`env_worker_simpler.py` (port 8702 default, in `slava-simpler`) serves
GreenVLA and all three lerobot models on SimplerEnv/bridge alike. Each
model-server receives the env-worker's raw obs dict (`agentview_rgb`,
`wrist_rgb`, `proprioception`, plus SimplerEnv-only `ee_pose`/
`gripper_closedness`) over HTTP and adapts it to whatever its own
checkpoint expects — the env side never needs to know which model is
consuming it. Per-model API details (which observation keys/layout each
checkpoint actually wants) live in the per-model skills, not here.

## Per-model APIs and bugs — see the per-model skills

`slava-openvla-oft` / `slava-lerobot-policies` / `slava-greenvla` each have
their model's confirmed real upstream API (read from the actual vendor
repo, not the quick-start docs) and every bug found getting that backend to
actually work — several were not right on the first try, and re-deriving
them from scratch would waste real time. Skim the relevant one before
touching a model-server file.

## Env-worker internals (our own code, not vendored)

### LIBERO (`slava-libero`, robosuite 1.4.0, mujoco 3.2.3, python 3.8)

- Reset via `libero.libero.envs.OffScreenRenderEnv(bddl_file=..., camera_names=["agentview","robot0_eye_in_hand"], ...)`, then a fixed-seed re-sample using the scene's `init_state_id` (same pattern as `scripts/collect_libero.py` — reuse its env-construction code, don't reinvent).
- Camera frames: `obs["agentview_image"][::-1]` and
  `obs["robot0_eye_in_hand_image"][::-1]` (robosuite renders upside down —
  confirmed by `scripts/collect_libero.py:87-88`, must flip the same way
  here or camera frames from rollouts won't match the D1 reference images).
- Proprioception: `obs["robot0_gripper_qpos"] + obs["robot0_eef_pos"] + obs["robot0_eef_quat"]` (matches `bddl_base_domain.py:828`).
- Native success: `env.check_success()` (wraps BDDL `_check_success()` —
  every frame's `success_predicates` already mirrors the same BDDL goal
  state, so **`success` and `final_relation_success` are the same signal
  here** — not computing a second independent spatial check, since the
  BDDL predicate already *is* the spatial/state check task.md describes).
  This is a simplification worth flagging to the user: task.md's schema
  keeps them as separate fields for generality (e.g. cases with sub-goals),
  but our 20 frames each have exactly one predicate, so in practice they
  collapse to one value.
- Contacts / `first_contact_object`: robosuite's `env.check_contact(geoms_1, geoms_2)` / raw `env.sim.data.contact[:env.sim.data.ncon]` with `env.sim.model.geom_id2name(...)`. Our approach: collect the gripper's own geom names once from `env.env.robots[0].gripper.important_geoms` (flatten all lists), then each step scan `sim.data.contact` for a gripper-geom vs. non-gripper/non-robot/non-table geom pair, resolve the other geom's body via `geom_bodyid` -> `body_id2name`, and match against the reverse of `env.env.obj_body_id` (sim_handle -> body_id, from `scripts/collect_libero.py:32`) to get the touched `sim_handle`. First such contact across the episode = `first_contact_object`. This is a heuristic, same class of approximation task.md already expects to be checked against the mandatory first-100-rollouts manual audit — don't treat it as exact ground truth before that audit.
- Action space: robosuite OSC_POSE controller, `Box(-1, 1, shape=(7,))` (dx,dy,dz,drx,dry,drz,gripper) — read `env.action_dim`/`env.action_spec` at runtime rather than hardcoding, in case a task's controller config differs.

### SimplerEnv/bridge (`slava-simpler`, ManiSkill2_real2sim, SAPIEN, python 3.10)

- Camera frame: `obs["image"]["3rd_view_camera"]["rgb"]` (first 3 channels — matches `scripts/collect_simpler.py:91`), **no wrist camera** (WidowX bridge setup has none — already noted in AGENTS.md/schema.py `CAMERA_FORMAT` comment).
- Native success: `env.evaluate(...)["success"]` (each `*_in_scene.py` task class implements its own `evaluate()`, e.g. `put_on_in_scene.py:43` — call the env's own method, don't reimplement the geometric check).
- Contacts: `env._scene.get_contacts()` → list of SAPIEN `Contact` objects with `.actor0`/`.actor1` (see `mani_skill2_real2sim/envs/custom_scenes/put_on_in_scene.py:96-102` and `utils/sapien_utils.py` helpers `get_pairwise_contacts`/`get_actor_contacts`). Gripper links identified by name (WidowX finger links — confirm exact names from `mani_skill2_real2sim/agents/robots/widowx.py` when implementing, don't guess blind). Same first-touch heuristic as LIBERO, same manual-audit caveat.
- Action space: read `env.action_space` at runtime (WidowX bridge convention is xyz + rotation + gripper, but let the env report its own bounds rather than hardcoding).

## Camera logging

User's explicit decision: one PNG per step per camera (not video, not every
N steps), stored at
`rollouts/episodes/<run_id>/camera/{agentview,wrist}/step_<NNNN>.png`
(`wrist/` omitted entirely for SimplerEnv episodes, not written as empty).

## Unified output layout

Everything lands under `rollouts/` at the project root (`src/slava_rollout/
storage.py` is the single source of truth for these paths — import it,
don't reconstruct paths inline in new scripts):

```
rollouts/
  rollout_annotations.jsonl      # one line per episode, ALL models/runs appended here
  episodes/<run_id>/
    steps.jsonl                  # per-step log: object poses, contacts, gripper state, action, instruction, task_uid, seed, model
    camera/agentview/step_0000.png ...
    camera/wrist/step_0000.png ...   # only if the environment has a wrist camera
  logs/<run_id>.log              # env-worker/model-server stdout for that episode's run, for debugging
```

`run_id` convention: `<prompt_id>__<model_key>__seed<seed:03d>` (see
`schema.py::build_run_id`) — `prompt_id` already uniquely identifies
`(task_uid, variant)` from `data/pilot_v0_release/prompts_v0.jsonl`, this
just appends model+seed. task.md's own `run_id` example
(`openvla_libero_spatial_003_ru_literal_seed000`) is illustrative prose,
not a strict grammar we have to match character-for-character.

Multiple env-workers could in principle write to the same
`rollout_annotations.jsonl` concurrently if runs are ever parallelized —
`storage.append_jsonl_locked` takes an `flock` on every write for that
reason, even though the current orchestrator design runs one (model, env)
pair at a time sequentially.

## Smoke test

`scripts/run_rollouts.py --smoke-test` restricts to **2 task_uids per
model** (first 2 scenes in that model's environment(s), in prompts_v0.jsonl
order) and **only the `en_canonical` variant** — fast end-to-end check of
env-worker + model-server + logging before the full 127-prompt run.

## What's still open / needs the user when they're back

- Whether `first_contact_object`/contact-based auto-labeling holds up —
  only the mandatory first-100-rollout manual audit (task.md line ~1224)
  can confirm this; treat early `rollout_annotations.jsonl` output as
  provisional until that audit happens. In particular, `relation_binding_error`
  vs `reference_grounding_error` cannot be told apart from a single
  first-contact signal alone (see `src/slava_rollout/auto_label.py` comment)
  — our auto-labeler defaults to `relation_binding_error` for that ambiguous
  case; the manual audit should specifically check whether that default is
  right more often than not, or needs a second contact-tracking signal added.
- Whether the zero-shot `*_base` checkpoints for π0/π0.5/SmolVLA on
  SimplerEnv/bridge are usable at all (see floor-effect risk above) — a
  call to make after seeing smoke-test SR on those 12 cells (3 models × 4
  scenes).
- **Update 2026-08-05: all three model-server backends now confirmed working
  against real checkpoints** (see "Real bugs found" section below for what it
  took to get there — several were not right on the first try). Unit-verified
  via direct `backend.predict()` calls: GreenVLA (`GreenVLA-5b-base-stride-1`),
  pi0 (`pi0_libero_finetuned`), SmolVLA (`smolvla_libero`) — all three
  returned correctly-shaped action arrays. Verified through the **actual
  orchestrator** (`scripts/run_rollouts.py --smoke-test`, not just the
  backend in isolation): OpenVLA-OFT completed a full 300-step LIBERO episode
  end-to-end (env-worker reset/step, model-server predict, auto-labeling,
  `rollout_annotations.jsonl` write — ~394s wall-clock for that one episode).
  The full run (all 5 models × 127 prompts) was launched right after on this
  basis. `pi0_base` (SimplerEnv/bridge zero-shot) hit a CUDA OOM once, but
  that was from two heavy unit tests running concurrently on one GPU during
  debugging, not a code bug — not reproducible under the real orchestrator,
  which now unloads each model before loading the next (see below).
- OpenVLA-OFT hardcodes bf16; on this server's V100 that's slow-but-correct,
  not broken — don't "fix" it preemptively, only patch if it actually causes
  wrong numerics (unlikely) or unacceptable smoke-test latency.
- **Update 2026-08-05, later same day: the full run was stopped early by the
  user (time budget), not completed.** Final coverage: GreenVLA-R0 28/28,
  GreenVLA-R1 28/28, OpenVLA-OFT 21/99, pi0/pi0.5/SmolVLA 0/127 each — 77
  episodes total in `rollouts/rollout_annotations.jsonl`. To resume the
  remaining models: env-workers were stopped too (clean `kill -TERM`, not
  crashed) before the machine migration below, so first restart them
  (`conda run -n slava-libero python -m slava_rollout.env_worker_libero
  --port 8701` and `conda run -n slava-simpler python -m slava_rollout.
  env_worker_simpler --port 8702`, both backgrounded), then `conda run -n
  slava-notebook python scripts/run_rollouts.py --models pi0 pi05 smolvla`
  — resume-by-run_id in `load_completed_run_ids()` will skip the 77 already
  done, no risk of duplicating or corrupting them. **This entire rollout
  pipeline needs CUDA and the exact conda envs set up on the (Vast.ai V100)
  GPU server — it cannot run on a CPU-only local machine.** If picking this
  back up from a local laptop, either rent/reuse a CUDA machine for this
  part, or treat the 77 episodes already collected as the final dataset for
  now and move on to analysis (see `scripts/generate_rollout_report.py`,
  which needs only the JSONL + episode PNGs, no GPU).
- **Sanity-checking technique worth reusing on any future rollout run:**
  don't just check `success`/`failure_type_auto` for plausibility — a model
  that's silently gone inert (outputs near-zero actions, stops interacting
  with the scene) can still produce plausible-looking non-`no_action_or_
  timeout` labels if it made brief contact early then stalled. Caught this
  concretely on GreenVLA-R0: md5-hashing each episode's saved agentview PNGs
  and checking the longest run of *consecutive identical hashes* showed
  R0 frozen for 24–40 of its 60 steps in every sampled episode, vs 1–14 for
  R1 (same shared env-worker code, so not an infra artifact) and ~1 (never
  frozen) for OpenVLA-OFT on a completely different sim. A few lines of
  Python (`hashlib.md5` per PNG, longest equal-hash run per episode) surfaces
  this in seconds and is worth running once per model on a small sample
  before trusting its behavioral metrics, especially SR — a model that's
  gone inert produces a real SR of 0% without a single genuine grounding
  attempt, which reads very differently in a report than "tried and failed."

## Memory: one model resident at a time, not one per (model, env-worker) pool lifetime

`scripts/run_rollouts.py`'s `WorkerPool` originally cached every model-server
it ever started for the whole process lifetime (same pattern as env-workers,
which is fine for them — no large weights). For models that's wrong: a
single `run_rollouts.py` invocation covering multiple models (the default,
no `--models` filter) would keep accumulating resident checkpoints — 5
models spanning 0.5B (SmolVLA) to 7B (OpenVLA-OFT) params would almost
certainly OOM a 32GB GPU by the 3rd or 4th model. Fixed: `WorkerPool.
stop_model(model_key)` tears down that model's subprocess right after its
episodes finish, called from `main()`'s per-model loop — at most one
model-server is resident at any time. Env-workers are left running across
models (cheap, and reused when the next model needs the same environment).

## Running two models in parallel on one GPU (SimplerEnv only, user's call)

Once the full run was live, GPU util sat at ~25% with ~20GB of 32GB free —
the env-worker/model-server split means a lot of each step's wall-clock is
CPU-bound (SAPIEN rendering, image preprocessing), not GPU compute, so a
single sequential process leaves real GPU headroom idle. User's explicit
call: run a second independent `run_rollouts.py` process in parallel — but
**only on SimplerEnv for now**; LIBERO's concurrent resource use (robosuite/
MuJoCo rendering doubled up) needs checking separately before doing the same
there, don't extend this to LIBERO without that check.

Mechanism: `ENV_WORKER_SPEC` ports are now overridable via
`SLAVA_LIBERO_PORT`/`SLAVA_SIMPLERENV_PORT` env vars specifically so a second
process can run its own env-worker *instance* rather than sharing one — an
env-worker's `STATE` is a single global mutable dict (one episode at a time
by design, see env_worker module docstrings), so two orchestrator clients
hitting the *same* instance would interleave reset/step calls and corrupt
each other's episode. Model-server ports already differ per model_key so no
override was needed there. Concretely, running `greenvla_r0` and
`greenvla_r1_bridge` concurrently: main run excludes `greenvla_r1_bridge`
via `--models`, a second process runs just that model with
`SLAVA_SIMPLERENV_PORT=8712` (its own SimplerEnv env-worker + GreenVLA-R1's
own model-server port 8802 — no clash). GPU util went 25% → 50% with this,
~20GB still free, confirming the idle-GPU theory rather than guessing.

**Tried and reverted 2026-08-05: 2 OpenVLA-OFT processes on one GPU.** Unlike
the SimplerEnv/GreenVLA precedent above (small models, genuinely idle GPU
compute), OpenVLA-OFT is a 7B checkpoint using ~16.5GB/32GB per instance —
memory, not compute, is the binding constraint here. Ran two full model-
servers on one V100 anyway (user's explicit call, to verify empirically
rather than guess): GPU hit 32.4/32.8GB total, and the second instance
degraded to 100%-failure-rate on every `/predict_chunk` call (500 errors,
fast/uniform cadence — no crash traceback surfaces through Flask's caught-
exception JSON response, had to `curl` the endpoint directly with a real
observation to see `torch`'s actual CUDA OOM underneath) before eventually
dying outright a few minutes in. Its own orchestrator process cleaned up
correctly on this natural exit (unlike the SIGTERM case below). No corrupted
data — episodes that error before completion are logged as `[error]` and
never reach `append_annotation`, so nothing bad landed in
`rollout_annotations.jsonl`, just ~16 wasted episode-attempts and a few
minutes of wall-clock. **Multi-GPU sharding (1 process per physical GPU) is
fine and confirmed working** (3-way concurrent LIBERO across 3 separate
V100s, no cross-talk, no errors — this was the previously-unconfirmed risk
flagged in the paragraph above, now checked); doubling up processes on the
*same* GPU only makes sense for models small enough to leave real headroom
after a second full weight+activation footprint, check actual `nvidia-smi`
memory (not just utilization%) before trying it for any given model.

**Also found while rebalancing shards: killing `run_rollouts.py`'s own PID
directly (not its process group) skips its `finally: pool.stop_all()`
cleanup**, since a bare SIGTERM to a Python process doesn't run `finally`
blocks the way a caught exception does — orphans its env-worker/model-server
children exactly like the `conda run` signal-forwarding bug above, just via
a different mechanism (killing the wrong *level* of the tree, not signal
forwarding). Hit this 3 times in a row during manual shard rebalancing before
fixing it properly: `main()` now installs a `signal.SIGTERM` handler
(`_handle_sigterm`) that raises `SystemExit`, which — unlike a raw kill —
*does* run `finally` blocks, so `pool.stop_all()` executes and children are
torn down correctly. Plain `kill <pid>` (or the user's own Ctrl+C on a real
run) now cleans up properly; no more need to manually `kill -TERM -<pgid>`
each child by hand.

Considered and explicitly **not** doing right now: true batched inference
(N environments stepped in lockstep, one batched model forward pass per
step) — more GPU-efficient per FLOP, but needs env-worker support for
multiple concurrent environment instances and every one of the 5 model-
server backends (3 different upstream codebases) to accept a batch
dimension. Given how much per-backend debugging correctness already took
today, that rewrite risk isn't worth it for a first pilot pass — process-
level parallelism was the lower-risk lever available and it was tried
first.

## `conda run` does not forward termination signals to its child — real OOM caused by this

Found live during the full run, not in review: `WorkerPool.stop_model()`/
`stop_all()` originally called `proc.terminate()`/`proc.kill()` on the
`subprocess.Popen` object for each `conda run -n <env> python <script>...`
command. `conda run` does **not** reliably forward SIGTERM/SIGKILL to the
actual python process it launches — terminating the `conda run` wrapper PID
left the real model-server/env-worker process (GPU weights and all) running
indefinitely, orphaned, after the orchestrator had already moved to the next
model. This happened for real, twice, within the same hour: GreenVLA-R0's
model-server outlived the main process's transition to OpenVLA-OFT, and
separately GreenVLA-R1-bridge's model-server + its SimplerEnv env-worker
outlived the parallel process exiting entirely. Between the two, 4 leftover
processes held ~31GB of the 32GB GPU, and the next model (OpenVLA-OFT, 7B)
crashed with a genuine `CUDA out of memory` trying to load — a real failure,
not a close call.

**Fix:** `start_subprocess()` now launches every child with
`start_new_session=True` (equivalent to `setsid`), making it the leader of
its own process group; `stop_process()` signals the **whole group** via
`os.killpg(os.getpgid(proc.pid), signal.SIGTERM)` (SIGKILL fallback on
timeout) instead of `proc.terminate()` on just the wrapper PID. This reaches
`conda run` and its actual child together regardless of whether `conda run`
itself forwards anything. **If you ever see a model-server process still
running after its orchestrator has moved to a different model, check
whether that orchestrator process is still using this fix** (an
already-running `run_rollouts.py` process has the old code in memory even
after the source file is patched — it needed a restart to pick this up,
which is what actually happened here).

## Per-model bugs — see the per-model skills

Several real bugs were only caught by actually invoking a backend against a
live checkpoint, not by re-reading code — trust the smoke test over any
written plan when they disagree. All model-specific ones (lerobot's
`FeatureType` comparison bug, checkpoint-declared placeholder camera
features, `compile_model`/cuDNN crashes, the camera-swap bug, GreenVLA's
chunk-shape bug, OpenVLA-OFT's gripper/chunk/orientation bugs, etc.) now
live in `slava-openvla-oft` / `slava-lerobot-policies` / `slava-greenvla` —
read whichever matches the model you're touching rather than re-deriving
these from scratch.

**HF_TOKEN leak lesson (generic, happened twice in one session):** writing
`env HF_TOKEN=$HF_TOKEN <command>` as a literal shell command leaks the
resolved value into tool-call output/logs whenever that command errors and
gets echoed back (e.g. by `conda run`). Rule: `export HF_TOKEN=...` as its
own statement in the shell, then invoke `conda run`/anything else without
repeating the variable in that command's own text — the child process
still inherits it from the environment. Extract the token with
`awk -F'"' '/^export HF_TOKEN=/{print $2}' ~/.bashrc`, never `source
~/.bashrc` or `grep` with context lines (same failure mode).

**Process-management lesson from debugging this under time pressure:** don't
let a `--models X` full run keep executing once you suspect every episode is
failing — burned through dozens of wasted (fast-failing, ~2-4s each so not
much wall-clock, but still noise in the logs and confusing on resume) episode
attempts on pi0.5 before killing it, when a single direct `curl`/`requests`
reproduction against the live model-server (bypassing the orchestrator
entirely) would have shown the real traceback in seconds. Prefer: at the
first `[error]` on a *new* model, pause and reproduce directly rather than
watching several more `[error]` lines scroll by first.

**Second process-management lesson: `kill -TERM <pid>` on the PID printed by
your own `nohup ... &` isn't always the orchestrator.** `CONDA_BIN run
--no-capture-output -n <env> python scripts/run_rollouts.py ...` backgrounded
with `&` gives you the **`conda run` wrapper's** PID, not the actual
`python scripts/run_rollouts.py` process it launches as a child (a different
PID, visible via `ps aux | grep run_rollouts.py`) — same wrapper-vs-child
split documented above for the `conda run` signal-forwarding bug, but this
time it bit via *manual* `kill`, not the orchestrator's own child cleanup.
The SIGTERM handler (`_handle_sigterm`) lives inside the inner python
process — signaling the outer wrapper PID does nothing to it, leaves the
whole run (env-worker, model-server, everything) still running. Always
`ps aux | grep run_rollouts.py` first and target the actual
`python scripts/run_rollouts.py --models ...` PID, not the `conda run` one.
