---
name: slava-model-rollouts
description: Architecture, APIs, and decisions for the first model-rollout pass (5 models x LIBERO/SimplerEnv), producing rollout_annotations.jsonl per task.md.
---

# SLAVA model rollouts — implementation notes

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

## LIBERO inference for lerobot policies (π0/π0.5/SmolVLA) — CORRECTED after reading the real repos

Originally planned to import lerobot's own `LiberoEnv` gym class
(`src/lerobot/envs/libero.py` in `huggingface/lerobot`) for the LIBERO side
of pi0/pi0.5/SmolVLA. **Reading that file showed it's a thin gymnasium
wrapper around the exact same `libero.libero.envs.OffScreenRenderEnv` our
own `env_worker_libero.py` already drives** (same `camera_names=
["agentview_image","robot0_eye_in_hand_image"]`, same underlying robosuite
env). There is no separate "lerobot LIBERO physics" to integrate.

**Simplified, verified design: one shared env-worker per environment, used
by every model that runs there.** `env_worker_libero.py` (port 8701, in
`slava-libero`) serves OpenVLA-OFT, pi0, pi0.5, and SmolVLA on LIBERO alike.
`env_worker_simpler.py` (port 8702, in `slava-simpler`) serves GreenVLA-R0/
R1, pi0, pi0.5, and SmolVLA on SimplerEnv/bridge alike. Each model-server
receives the env-worker's raw obs dict (`agentview_rgb`, `wrist_rgb`,
`proprioception`, plus SimplerEnv-only `ee_pose`/`gripper_closedness`) over
HTTP and adapts it to whatever its own checkpoint expects — the env side
never needs to know which model is consuming it. This is cleaner than the
originally-planned per-model-family env duplication and was not a user
decision to re-confirm, just a code-quality correction once the actual APIs
were visible — recorded here per the "log decisions for later review" rule.

`slava-lerobot` therefore does **not** need the `[libero]` extra (that pulls
`hf-libero` and its own env plumbing we don't use) — installed as
`pip install -e "<lerobot_repo>[smolvla]"` (covers pi0/pi0.5 too, same
package) instead.

### Confirmed real API (read directly from `huggingface/lerobot`, not guessed)

```python
from lerobot.configs.policies import PreTrainedConfig      # NOT lerobot.common.*
from lerobot.policies.factory import get_policy_class, make_pre_post_processors  # NOT lerobot.common.*
from lerobot.common.control_utils import predict_action    # this one IS under .common

policy_cfg = PreTrainedConfig.from_pretrained(checkpoint)
policy = get_policy_class(policy_cfg.type).from_pretrained(checkpoint)
preprocessor, postprocessor = make_pre_post_processors(policy_cfg, pretrained_path=checkpoint)
action = predict_action(observation, policy, device, preprocessor, postprocessor, use_amp=False, task=instruction)
```

`policy_cfg.input_features` (dict of name -> `PolicyFeature`, `.type.value`
`"visual"`/`"state"`) tells you exactly which raw observation keys and
state dimensionality *this specific checkpoint* expects — `scripts/
model_servers/lerobot_server.py` reads this at startup instead of
hardcoding key names, because LIBERO-finetuned and bridge-zero-shot
checkpoints do NOT necessarily share the same key names/dims.

## GreenVLA inference — confirmed real API (from github.com/greenvla/GreenVLA directly)

GreenVLA's own repo is an older *vendored* lerobot fork (its own
`lerobot/common/policies/greenvla_policy/`, not related to the modern
`huggingface/lerobot` above) — so `slava-greenvla` is its own env, built
from `pip install -e .` inside a clone of that repo, not from
`huggingface/lerobot`. Confirmed end-to-end from `examples/
example_inference_bridge.py` + `docs/INFERENCE.md`:

```python
from lerobot.common.policies.factory import load_pretrained_policy
policy, input_transforms, output_transforms = load_pretrained_policy(checkpoint, data_config_name="bridge")
# raw obs: {"observation/state": float32[8] (x,y,z,roll,pitch,yaw,_pad_,gripper),
#           "observation/image": uint8 HWC, "prompt": str}
# policy.select_action(batch) -> normalized actions (action_horizon x 7)
# output_transforms({"actions":..., "state":...}) -> real actions (x,y,z,roll,pitch,yaw,gripper)
```

The 8-dim state is **end-effector pose**, not joint qpos — `env_worker_simpler.py`
exposes this separately as `obs["ee_pose"]` ([x,y,z,qw,qx,qy,qz], read from
the `ee_gripper_link` global pose) + `obs["gripper_closedness"]`, alongside
the joint-qpos-based `proprioception` field other backends use. Roll/pitch/
yaw are derived from the quaternion via `scipy.spatial.transform.Rotation`
in `scripts/model_servers/greenvla_server.py`.

Only one action of the returned `action_horizon` is executed per `/predict`
call (the orchestrator calls once per sim step) — action-chunk replay for
speed is a later optimization, not needed to validate correctness first.
GreenVLA's own benchmarking notes recommend `action_horizon=2` for Bridge
and warn results vary ±6% run-to-run — expected, not a bug in our harness.

## OpenVLA-OFT — confirmed real API (from github.com/moojink/openvla-oft directly)

Note the real GitHub org is **`moojink/openvla-oft`**, not `openvla/openvla-oft`
(that URL 404s/requires auth — don't reuse it). `LIBERO.md` confirms the
released `moojink/openvla-7b-oft-finetuned-*` checkpoints just need the
eval script's *default* `GenerateConfig` (`use_l1_regression=True`,
`num_images_in_input=2`, `use_proprio=True`, `center_crop=True`) — our
`scripts/model_servers/openvla_oft_server.py` imports their own
`GenerateConfig`/`get_model`/`get_processor`/`get_action_head`/
`get_proprio_projector`/`get_action` unchanged rather than reimplementing
OFT's parallel-decoding + proprio-projector + L1-regression-head pipeline.

Their `attn_implementation="flash_attention_2"` is already **commented out**
in their own loading code — flash-attn is not required for inference,
skip that (slow, sometimes fragile) build step entirely.

Everything is hardcoded to `torch.bfloat16` in their code (not a flag we can
easily override without patching). On this server's V100 (no bf16 tensor
cores — see top of this doc) bf16 ops still run correctly, just slower
(software-emulated, not broken) — accepted trade-off for a first pass, not
worth forking their repo to force fp16 unless it proves to actually block
the smoke test.

`unnorm_key` is **keyed by LIBERO suite name** (`libero_spatial`/`_object`/
`_goal`, with a `_no_noops` fallback) and must be set per-episode from the
prompt's own `suite` field, not hardcoded — our combined `-spatial-object-goal-10`
checkpoint covers all three of our LIBERO suites, but the unnorm stats are
suite-specific. This is why the model-server `/predict` contract carries a
`meta` dict (`{task_uid, suite, environment}`) alongside `obs`, not just
pixels+proprioception — added specifically for this need but generically
useful for any future model needing episode context beyond the raw
observation.

Their `prepare_observation()`/`get_action()` expect `state` = `eef_pos(3) +
axis_angle(3) + gripper_qpos(2)` (8-dim) — converted in
`openvla_oft_server.py` from `env_worker_libero.py`'s
`[gripper_qpos(2), eef_pos(3), eef_quat(4)]` proprioception via
`scipy.spatial.transform.Rotation.as_rotvec()`.

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

## OpenVLA-OFT: missing gripper action post-processing — real bug, not task difficulty

Caught by the user's explicit request to sanity-check results, not by code
review. Symptom: 13 straight OpenVLA-OFT episodes across **two different
LIBERO tasks** (drawer-opening and plate-pushing) all failed with
`no_action_or_timeout`, `gripper_state` hovering near 0 the entire episode
in every one, `contacts` always empty despite the arm/proprioception clearly
moving with normal-looking magnitudes (confirmed both from `steps.jsonl`
action logs and camera frames — the arm moves, just apparently never
actually grips or reaches the intended target). Two different tasks failing
identically was the signal that this wasn't ordinary task difficulty
(compare: OpenVLA-OFT reports ~97% SR on this exact combined checkpoint in
their own paper).

Root cause: `openvla_oft_server.py`'s `predict()` returned the raw output of
`get_action()` directly. The reference `run_libero_eval.py` never does
this — every action it gets from `get_action()` is piped through its own
`process_action(action, cfg.model_family)` before `env.step()`:
```python
action = normalize_gripper_action(action, binarize=True)  # [0,1] -> [-1,+1]
if model_family == "openvla":
    action = invert_gripper_action(action)  # sign flip
```
Both functions live in `experiments/robot/robot_utils.py` and are
documented there: the RLDS dataloader convention is gripper ∈ [0,1] with
0=close/1=open, but the LIBERO env's OSC_POSE controller expects
∈ [-1,+1] with -1=open/+1=close. Skipping this step meant every gripper
command was both wrong-scale AND inverted — a close command could easily
read as a small "open more" delta instead, so the gripper effectively never
closed. This silently produces plausible-*looking* rollout data (a real
episode, real physics, a real trajectory) with a systematically broken
actuator — exactly the "results look fine but the model can't actually do
what it should" failure mode that's hardest to catch from logs alone,
easiest to catch from an actual behavioral pattern (universal failure
across distinct tasks + a suspiciously flat gripper trace) or from
comparing hard numbers against the paper's reported SR.

**Fix:** `openvla_oft_server.py` now calls `normalize_gripper_action()` +
`invert_gripper_action()` on the action before returning it, matching
`process_action()` exactly. **The 13 episodes run before this fix were
purged** from `rollout_annotations.jsonl` (backed up to
`rollout_annotations.jsonl.bak_before_openvla_fix`) and their episode
directories moved to `rollouts/episodes_archived_buggy_openvla_gripper/`
(not deleted, kept for reference) rather than left in the dataset — do not
resurrect them, they're gripper-inverted and not representative of the
model's real behavior. The run resumed and correctly re-selected those 13
prompts as not-yet-done.

**Takeaway for reviewing the other 4 model-server backends similarly:**
each vendor's reference eval script may apply action post-processing steps
beyond what their "load model, call predict" quick-start docs show — always
check the *eval loop*, not just the *inference call*, for a
`process_action`/similar step before assuming the raw model output is
ready to hand to `env.step()`.

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

## Real bugs found once each backend actually ran (fixed, not hypothetical)

Each of these was caught by actually invoking the backend against a live
checkpoint, not by re-reading code — trust the smoke test over the plan
above when they disagree.

1. **`lerobot_server.py` `FeatureType` comparison bug:** `PolicyFeature.type.value`
   is the UPPERCASE string (`"VISUAL"`/`"STATE"`), not lowercase — comparing
   against lowercase silently matched nothing, so `image_features` came back
   empty for every checkpoint. Fixed by comparing against the enum members
   (`FeatureType.VISUAL`/`FeatureType.STATE`) directly instead of `.value` strings.
2. **`lerobot/pi0_libero_finetuned` declares 3 image input features, not 2:**
   `observation.images.image`, `observation.images.image2`, and
   `observation.images.empty_camera_0` (224×224, smaller than the two real
   256×256 camera slots) — a placeholder the checkpoint always saw as a zero
   image during training. `lerobot_server.py` now feeds `np.zeros(...)` for
   any feature name containing `"empty_camera"` rather than duplicating a
   real frame into it (a real frame there would be out-of-distribution input
   the model never saw at that slot during training).
3. **`compile_model=True` on `lerobot/pi0_libero_finetuned` crashes on this
   server:** passing `compile_model=False` as a kwarg to `PreTrainedConfig.
   from_pretrained()` does **nothing** — it silently falls into
   `**policy_kwargs`, which that method only forwards as draccus
   `cli_overrides` (a list of CLI-style strings), not arbitrary field
   overrides. The real fix: load the config, mutate
   `policy_cfg.compile_model = False` directly on the returned object (guarded
   by `hasattr`, since not every policy config has this field), then call
   `policy_cls.from_pretrained(checkpoint, config=policy_cfg)` — the explicit
   `config=` kwarg is required, otherwise `from_pretrained` reloads its own
   fresh (un-mutated) config internally and the override is lost anyway. Why
   this matters: leaving `compile_model=True` makes `torch.compile(mode=
   "max-autotune")` JIT-compile `sample_actions`/`forward` via Triton/Inductor
   on first call — on this V100 (Volta) + this torch/Triton combination that
   fails outright (`RuntimeError: PassManager::run failed`, an MLIR pass
   crash), not just slow. If a future checkpoint hits this on a newer GPU
   where Triton actually succeeds, it would just be slow-on-first-call, not
   broken — but disabling it is still correct for us since we run n=1 episodes
   sequentially (no amortization benefit from compiling).
4. **`openvla_oft_server.py` needs the `libero` package importable but must
   NOT `pip install -e` it in `slava-openvla`:** doing so hit a real conflict
   between LIBERO's and openvla-oft's own PEP 660 editable-install import
   finders (openvla-oft's `__editable__...finder.__path_hook__` on `sys.path`
   ends up shadowing resolution for other editable packages — `pip show libero`
   reports it installed, `import libero` 404s anyway). Fixed by plain
   `sys.path.insert(0, LIBERO_ROOT)` instead of a pip install — this env never
   touches LIBERO physics/rendering (that's `env_worker_libero.py`'s job in
   the separate `slava-libero` env), so no install machinery is needed here,
   just the module on the import path. Also needed (installed as plain,
   mostly-unpinned pip packages — NOT the old pins from `LIBERO/requirements.txt`,
   which would have downgraded openvla-oft's own numpy/transformers):
   `robosuite==1.4.0` (pinned — a newer PyPI `robosuite` reorganized
   `robosuite.environments.manipulation.single_arm_env` and breaks LIBERO's
   benchmark import), `bddl==1.0.1`, `easydict==1.9`, plus unpinned `future`,
   `hydra-core`, `wandb`, `robomimic`, `thop`, `matplotlib`, `cloudpickle`,
   `gym` — all pulled in transitively just by importing `libero.libero.
   benchmark` for its `GenerateConfig`/task-suite dict, not because
   openvla-oft's actual inference path uses them.
5. **`greenvla_server.py` returned a whole action chunk instead of one
   action** — found only once the *full run* (not the smoke test, which
   never touches GreenVLA) actually reached GreenVLA and crashed the env-
   worker with `AssertionError: ((10, 7), 7)`. GreenVLA's own README example
   does `actions[0]` to get "the first action" and calls that correct, but
   that example has no explicit batch dimension in its printed shape — ours
   does (`policy.select_action(batch)` returns `(batch=1, action_horizon,
   7)`), so `actions[0]` was pulling the whole `(10, 7)` horizon instead of
   one `(7,)` action. Fixed with `np.asarray(actions).reshape(-1, action_dim)[0]`,
   which is correct whether or not a batch dim is present. **Lesson: a
   vendor's own example script correctly matching its own printed shape
   doesn't guarantee your call site has the same shape — checked this one
   the hard way, by hitting the crash, not by re-reading the README more
   carefully.**
6. **Second HF_TOKEN leak incident in this same session** (see AGENTS.md
   "Текущее состояние проекта" for the full note and the first incident from
   the prior agent): writing `env HF_TOKEN=$HF_TOKEN <command>` as a literal
   shell command leaks the resolved value into tool-call output/logs whenever
   that command errors and gets echoed back (e.g. by `conda run`). Rule:
   `export HF_TOKEN=...` as its own statement in the shell, then invoke
   `conda run`/anything else without repeating the variable in that command's
   own text — the child process still inherits it from the environment.

## SR=0% root cause (found 2026-08-05, 3rd server/session) — three independent bugs, all fixed

The 77-episode dataset from the previous session had 0/77 successes. The
`AGENTS.md` handoff already ruled out an auto-labeling bug (`success` reads
`env.check_success()`/native `info["success"]` directly) and flagged the
missing open-loop chunk replay as the prime suspect for OpenVLA-OFT
specifically. On the new GPU server, reading `moojink/openvla-oft`'s actual
`experiments/robot/libero/run_libero_eval.py` line-by-line (not guessed)
turned up **three** real, independent bugs in our OpenVLA-OFT path — fixing
all three took the smoke-test SR from 0/21 (previous session, real episodes)
to **2/2** on this session's `--smoke-test` run, at 33-76s/episode (down from
~394s/episode before the chunk-replay fix — 5-8x faster too, expected since
the model is now queried once per 8 steps instead of every step).

7. **Missing open-loop action-chunk replay** (the one already flagged in the
   handoff, now actually fixed). `get_action()` returns the full predicted
   chunk (`NUM_ACTIONS_CHUNK=8` actions for LIBERO, confirmed by reading
   `prismatic/vla/constants.py` — it auto-detects platform from `sys.argv`,
   defaults to LIBERO when nothing matches, which is what our model-server's
   argv gives it, so no explicit override needed). The reference script
   queries the model once, pushes the whole chunk into a `deque`, and pops
   one action per env step, **only requerying once the queue is empty** —
   i.e. actions 1-7 of every chunk are executed completely open-loop, no new
   observation involved. Our old code called `get_action()` fresh on every
   single env step and only ever used `action[0]`, discarding the other 7 —
   a different (always-closed-loop) execution strategy than what the
   checkpoint was ever evaluated with. Fixed via a new generic
   `/predict_chunk` endpoint (`base_server.py`, opt-in per backend via an
   optional `predict_chunk()` method — falls back to a 1-action chunk built
   from plain `predict()` for every other backend, so GreenVLA/lerobot are
   byte-for-byte unaffected) and a `pending_actions` queue in
   `run_rollouts.py::run_episode()` that drains one action per `env_client
   .step()` call before requesting a new chunk. Camera-frame saving and
   `success`/`done` checks still happen every single sim step (task.md
   requirement), only the *model query* is now chunked.
8. **Image mirrored left-right — independent of the chunk bug, likely the
   bigger contributor.** `openvla-oft`'s own
   `experiments/robot/libero/libero_utils.py::get_libero_image()` does
   `img[::-1, ::-1]` on the raw `obs["agentview_image"]` (**both** axes
   reversed = 180° rotation), commented "IMPORTANT: rotate 180 degrees to
   match train preprocessing." Our shared `env_worker_libero.py::_build_obs()`
   does `raw[::-1]` (axis 0 only — a vertical flip, chosen to produce a
   human-legible image for the D1 screenshot review dashboard, matching
   `scripts/collect_libero.py`'s same single-flip convention — correct for
   *that* purpose). These are different transforms, not one a subset of the
   other: composing them, every frame OpenVLA-OFT received was
   `single_flip(raw)` where it needed `double_flip(raw)` — i.e. a **left-right
   mirror** of what it was trained on (robot arm on the wrong side, spatial
   relations flipped). This does not depend on instruction language at all,
   so it would have suppressed EN and RU success equally — a real,
   independent confound on top of the chunk bug. Fixed *scoped to
   `openvla_oft_server.py` only* (`_build_observation()`'s docstring has the
   full derivation) — one extra `[:, ::-1]` mirror applied to the
   already-single-flipped `agentview_rgb`/`wrist_rgb` right before handing
   them to `get_action()`. `env_worker_libero.py` itself is untouched and
   stays neutral — pi0/pi0.5/SmolVLA on LIBERO have **not** been checked
   against their own training image-orientation convention yet, do that
   before trusting their LIBERO results (see "What's still open" below).
9. **Missing `num_steps_wait=10` physics-settle steps.** The reference
   `run_episode()` executes 10 steps of the dummy action `[0,0,0,0,0,0,-1]`
   right after `env.set_init_state()`, *before* the policy is ever queried
   ("let objects stabilize in sim") — these steps are not logged, not counted
   against `TASK_MAX_STEPS`, and the model never sees them. Our env-worker
   queried immediately after `set_init_state()`. Smaller effect than #8, but
   free to fix: `env_worker_libero.py::/reset` now takes an optional
   `num_steps_wait` payload field (default 0, so every other model's behavior
   is unchanged) and runs that many dummy steps internally before building
   the returned obs. Wired up from `run_rollouts.py` via a
   `LIBERO_NUM_STEPS_WAIT = {"openvla_oft": 10}` lookup in
   `build_reset_payload()` — opt-in per model, not a blanket change to every
   LIBERO episode.

**Verification note:** the smoke-test's `en_canonical` prompt for
`open_the_middle_drawer_of_the_cabinet` ("open the middle drawer of the
cabinet") is not just "close to" the original LIBERO task text — it's an
**exact, word-for-word match** to `benchmark.get_benchmark_dict()
["libero_goal"]().get_task(i).language` (confirmed by calling the real
benchmark API, not by reading the `.bddl` file's own `:language` comment,
which is a stale author note and does NOT match what the benchmark actually
serves — e.g. it says "Open the middle layer of the drawer" for this same
task, which is *not* what gets used anywhere in eval). So the 2/2 smoke-test
success was already run on the literal, unmodified original dataset prompt,
not a SLAVA paraphrase — ruling out "the pipeline only works on our reworded
prompts" as an explanation for the earlier SR=0%.

**Not yet done:** these fixes only touch the OpenVLA-OFT path. pi0/pi0.5/
SmolVLA/GreenVLA have their own separate image-preprocessing and
action-execution conventions that have NOT been checked against this same
level of scrutiny (reading their actual reference eval/training code, not
just the quick-start inference example) — do that before trusting their
results, per the same methodology used here (read the reference eval loop,
not just the "load model, call predict" quick-start).

## pi0/pi0.5: cuDNN "no engine" crash on SigLIP conv2d (V100), found + fixed 2026-08-05

Same session, after the OpenVLA-OFT fixes above. `lerobot_server.py` also
needed two LIBERO-specific fixes mirroring the OpenVLA-OFT pattern (own
docstring in that file has the full derivation): (1) lerobot's own
`LiberoEnv._format_raw_obs()` (`lerobot.envs.libero`) feeds the policy the
**raw, unflipped** camera frame — a third distinct orientation convention,
different from both OpenVLA-OFT's 180°-rotation and our env-worker's
single-flip — confirmed against `docs/source/libero.mdx` too; (2)
proprioception needed the same `eef_pos(3)+axis_angle(3)+gripper_qpos(2)`
conversion as OpenVLA-OFT, not env-worker's raw 9-dim quaternion layout.
`[::-1].copy()` (not just `[::-1]`) required — `torch.from_numpy()` rejects
negative-stride views outright. All confirmed working via SmolVLA's live
run (different vision backbone, unaffected by the next bug below).

pi0 and pi0.5 (both PaliGemma/SigLIP-based) additionally hit a **third, more
stubborn bug** SmolVLA doesn't have: every `/predict_chunk` call crashed with
`RuntimeError: GET was unable to find an engine to execute this computation`,
traced (via direct reproduction against a live env-worker, not guessed) to
SigLIP's patch-embedding `Conv2d` inside `paligemma.model.vision_tower` — a
cuDNN "no kernel found for this op/dtype/shape on this hardware" error, not a
memory or shape bug. **First attempted fix (didn't work): overriding
`policy_cfg.dtype = "float32"`** — same mutate-then-`from_pretrained(...,
config=policy_cfg)` pattern already used for `compile_model=False`. pi0.5's
config actually defaults to `dtype="bfloat16"`, pi0's already defaults to
`"float32"` — yet **both** kept crashing identically even after the override
visibly took effect (checked `cfg.dtype` before/after). Something in cuDNN's
own algorithm search still can't find an engine for this specific SigLIP
conv on this GPU/cuDNN/torch combination, independent of the dtype the model
ends up running in. **Actual fix:** `torch.backends.cudnn.enabled = False` at
module import time in `lerobot_server.py`, before any model loads — forces
PyTorch's native (non-cuDNN) conv2d fallback for the whole process. Blunter
than pinning dtype, but the one that actually resolved it — confirmed via a
live `predict_chunk` request returning 200 immediately after. Only affects
this process; env-workers and other model-servers are separate
processes/conda envs, untouched.

**GreenVLA R0/R1 embodiment check (user question, answered from source
2026-08-05).** Confirmed via `huggingface_hub.list_repo_files()` on both
checkpoints (not guessed from the name): **both R0
(`GreenVLA-5b-base-stride-1`) and R1 (`GreenVLA-5b-stride-1-R1-bridge`) ship
a `norm_stats/bridge/norm_stats.json`**, so `load_pretrained_policy(...,
data_config_name="bridge")` in `greenvla_server.py` resolves WidowX-bridge
normalization for both — not Google Robot/fractal. The env is WidowX too
(`widowx_stack_cube`, `ee_gripper_link` in `env_worker_simpler.py` is
WidowX-specific). **But R0 is a cross-embodiment generalist base checkpoint**
— its repo has norm_stats for 19 different robots (agibotworld, biplay,
bridge, droid, fractal, galaxeaworld, rdt, several robocoin/robomind
variants) — while **R1's repo has ONLY `norm_stats/bridge/`**, confirming
it's the bridge-specialized fine-tune stage. This is a real, source-verified
explanation (not speculation) for why R0 freezes more than R1: R0 was never
specifically fine-tuned toward WidowX, it just has the right normalization
stats to be *evaluated* on it — matches the R0-base → R1-bridge curriculum
description already in AGENTS.md.

**Deep audit of GreenVLA's actual transform factory (not just the quick-start
example), same session — no new bug found.** User asked to re-check against
GreenVLA's own source given R0/R1's low SR. Read
`lerobot/common/policies/factory.py::load_pretrained_policy` (which our
`greenvla_server.py` already calls directly — we are NOT reimplementing
their pipeline, we use their real `input_transforms`/`output_transforms`),
`lerobot/common/utils/inference_transforms.py::get_torch_{input,output}_
transforms`, `lerobot/common/datasets/data_transforms/robots/bridge.py`
(`BridgeInputsTransform`/`BridgeOutputsTransform`), and
`lerobot/common/datasets/torch_transforms.py::parse_image_helper`. Findings:
state layout (`[x,y,z,roll,pitch,yaw,pad,gripper]`, pad-masking) matches our
`greenvla_server.py` exactly; the output pipeline is `Unnormalize(norm_stats)
→ slice-to-7-dims`, nothing else, and we already do this via their own
`output_transforms` callable; `parse_image_helper` does **no** flip/rotation
at all (dtype/CHW→HWC only), so there's no hidden orientation expectation
on their side to mismatch — consistent with `env_worker_simpler.py` not
flipping. Quaternion→euler conversion in `greenvla_server.py` (SAPIEN `wxyz`
→ scipy `xyzw` reorder) checked correct. **No further actionable bug
surfaced this pass.** Current best explanation for R0/R1's ~0% SR remains:
R0's genuine lack of WidowX-specific tuning (see above) plus SimplerEnv's
SAPIEN-rendered visual domain gap vs the real camera frames both checkpoints
were trained on (risk explicitly accepted by the user at project start, see
AGENTS.md "Модели — 5, не 4" section) — not a code bug we've found evidence
for after two independent audit passes.

**Fourth bug, same session: lerobot LIBERO models also needed
`num_steps_wait=10`.** `LIBERO_NUM_STEPS_WAIT` in `run_rollouts.py` originally
only covered `openvla_oft`. Spotted a real pattern after ~15 episodes: pi0,
pi0.5, and SmolVLA were all stuck on `no_action_or_timeout` on the exact same
LIBERO-goal scene (`open_the_middle_drawer_of_the_cabinet`) that OpenVLA-OFT
(which already had the settle-step fix) succeeded on repeatedly. Checked
`huggingface/lerobot`'s own `LiberoEnv.__init__` (`src/lerobot/envs/
libero.py`) again — it independently defaults to the identical
`num_steps_wait: int = 10`, not something borrowed from OpenVLA-OFT. Added
`pi0`/`pi05`/`smolvla` to the same dict (`10` each). All 3 running processes
were killed and restarted to pick this up (module-level constant, doesn't
apply retroactively to an already-running process) — not yet enough
post-fix episodes at time of writing to say whether this changes their SR;
check `data/rollout_report.html`'s per-model breakdown for the current
numbers rather than trusting this note's absence of a verdict.

**Fifth issue, still OPEN/unresolved: pi0/pi0.5 show 0% SR with `first_contact_
object=None` on `libero_object` (the EASIEST LIBERO suite — OpenVLA-OFT gets
6/6 on every task there).** Found 2026-08-05 while monitoring the live run:
after ~65 episodes, pi0 hit `libero_object__pick_up_the_{butter,cream_cheese,
milk}_and_place_it_in_the_basket` and went 0/18 with **zero contact ever**
(not just wrong-object contact) — a cleaner, more systematic-looking pattern
than the `libero_goal` failures (where at least `target_grounding_error`/real
contact happened sometimes). Rendered the actual image pi0 was receiving
(after the "undo env-worker's flip" logic above) and it looked genuinely
upside-down/disoriented (arm at bottom, floor objects at top) — not a
plausible robot-eye view. **Reverted the image-flip fix** (the `if False:`
block in `lerobot_server.py` — kept, not deleted, with a note) back to
passing through env-worker's existing upright orientation unchanged, and
retested on a fresh `libero_object` episode. **Result: still 0% SR, still
`first_contact_object=None`.** So the flip direction is NOT the (sole) root
cause of this specific pattern — ruled out via direct A/B test on live data,
not guessed. Action deltas in the raw `steps.jsonl` are non-degenerate
(comparable magnitude to OpenVLA-OFT's successful episodes) but never
accumulate into a decisive reach toward the object. **Not resolved — left
running as-is (reverted/no-extra-flip state, since that matches the
already-validated convention used everywhere else in the pipeline, absent
positive evidence for the alternative) given the session's hard time budget
and the user's explicit reprioritization toward GreenVLA-R0/R1 coverage.**
Whoever picks this up next: the libero_goal vs libero_object asymmetry
(*some* grounding on one, *zero* on the other) is the most promising lead —
check whether libero_object's specific object set/scene geometry does
something the proprioception or action-space conversion doesn't handle
(different starting reach distances? different init state characteristics?),
rather than re-litigating image orientation, which is now directly tested
both ways.

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
