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

## Starting from nothing: third-party repos and envs are NOT part of this repo

**Read this first if `ls ../` doesn't show `LIBERO/`, `SimplerEnv/`,
`greenvla_repo/`, `openvla_oft_repo/`, `lerobot_repo/`, or if
`conda env list` doesn't show the `slava-*` envs.** None of that is
tracked in git — it is external code plus multi-GB conda environments, and
a fresh clone of SLAVA_dev on a new machine has none of it. Everything
below is reproducible from two scripts; do not hand-install and do not
assume the paths that happen to exist on whatever machine you're reading
this from.

```bash
# 1. D1-D4 + the two env-workers: clones LIBERO and SimplerEnv (pinned
#    commits), creates slava-notebook / slava-libero / slava-simpler.
bash scripts/bootstrap.sh                       # add --skip-libero-datasets
                                                # for inference-only work
# 2. D5 model-servers: clones greenvla_repo / openvla_oft_repo /
#    lerobot_repo (pinned commits), creates slava-greenvla / slava-openvla /
#    slava-lerobot.
bash scripts/bootstrap_models.sh
```

**Where they land.** Both scripts default to the *sibling* directory of
this repo (`$(dirname SLAVA_dev)`), i.e. a checkout at `/anything/SLAVA_dev`
puts LIBERO at `/anything/LIBERO`. Override with `SLAVA_DEPS_DIR=/some/path`
(honoured by both scripts and by the runtime: `run_rollouts.py` and
`openvla_oft_server.py` resolve their defaults the same way, and
`LIBERO_ROOT`/`SIMPLERENV_ROOT`/`OPENVLA_OFT_ROOT` still override
per-repo). Nothing in the codebase should hardcode an absolute path — if
you find one, that's a bug; it was true of `/workspace/*` until 2026-08-05.

**What the two scripts are worth trusting for.** `bootstrap.sh` has been
run end-to-end successfully more than once and is idempotent (re-running
skips what already exists). `bootstrap_models.sh` was *reconstructed* from
the live state of envs that had been built by hand across sessions — it
encodes every pin and workaround that was actually needed, but has not
itself been executed on a clean machine. If a step fails, check the exact
error against the per-model skill (`slava-greenvla`, `slava-openvla-oft`,
`slava-lerobot-policies`) before improvising: most of the non-obvious
lines in it exist because of a specific, documented upstream bug.

**Non-obvious things baked into those scripts, so you don't rediscover them:**

- GreenVLA's `pyproject.toml` does not build with plain `pip install -e .`
  — `[project]` has no `version` (their README's `uv sync` tolerates it),
  and `[tool.poetry]` declares no `packages`, so poetry-core looks for a
  `greenvla/` dir that doesn't exist (their code lives in `lerobot/` — the
  repo is an old *vendored fork of lerobot*). Both are patched locally by
  the script; upstream is untouched.
- **`greenvla_repo` and `lerobot_repo` both provide a top-level `lerobot`
  package, and they are different, incompatible codebases.** GreenVLA's
  fork uses `lerobot.common.policies.*`; current huggingface/lerobot uses
  `lerobot.policies.*` (no `common`). They live in separate conda envs for
  exactly this reason — never cross-reference import paths between them,
  and don't "fix" an import in one based on the other. A wrong-but-
  plausible import here will resolve to the wrong repo and waste a lot of
  time.
- `huggingface/lerobot` requires **python>=3.12** (not 3.10/3.11).
- Pin `torch==2.7.1` explicitly. An unpinned resolver picks 2.11.0+cu130,
  which supports only compute capability >=7.5 — wrong for the V100s
  (cc 7.0) this project has been run on.
- openvla-oft's inference path eagerly imports tensorflow/
  tensorflow_datasets/dlimp; its declared `tensorflow==2.15.0` pin drags in
  a protobuf incompatible with `tensorflow_metadata`'s compiled `_pb2.py`.
  Upgrading to `tensorflow>=2.16` + `protobuf>=6.31.1,<7` fixes it; pip's
  resulting "declared pin mismatch" warning is expected and harmless
  (tensorflow is never on the inference path).
- `sapien==2.2.2` segfaults on `env.step()` with numpy>=2 — pin
  `numpy==1.26.4` in any env that touches SimplerEnv rendering.
- `conda create --clone` fails on these mixed conda+pip envs (known conda
  limitation). Build fresh instead.

**Sanity-check before a real run**, in this order — each step isolates a
different layer:

```bash
conda run -n slava-greenvla python -c 'from lerobot.common.policies.factory import load_pretrained_policy'
conda run -n slava-openvla  python -c 'import prismatic'
conda run -n slava-lerobot  python -c 'from lerobot.policies.factory import get_policy_class'
# env-worker alone, real physics, no model involved:
conda run -n slava-simpler env PYTHONPATH=$PWD/src python -m slava_rollout.env_worker_simpler --port 9911 &
curl -s -X POST localhost:9911/reset -H 'Content-Type: application/json' \
  -d '{"task_name":"widowx_stack_cube","episode_id":0,"reset_seed":0}' | head -c 200
# then the whole chain:
conda run -n slava-notebook python scripts/run_rollouts.py --smoke-test
```

GPU note: these envs have only ever been exercised on 4×V100-32GB (Volta,
cc 7.0, **no bf16 tensor cores**) — checkpoints that default to bf16 must be
forced to fp16/fp32. On newer hardware that constraint disappears but the
torch pin above may need revisiting.

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

## Porting to different hardware — what is a V100 workaround, not a design choice

Everything in this project has only ever run on 4×Tesla V100-32GB (Volta,
cc 7.0, **no bf16 tensor cores**). Several fixes in the code exist solely
because of that and are a needless cost on Ampere or newer. If you are reading
this on an A100/H100/RTX-40xx, review these four before trusting the setup —
none of them will fail loudly on newer hardware, they will just quietly waste
time or memory:

| Workaround | Where | Why it exists | On cc≥8.0 |
| --- | --- | --- | --- |
| `torch.backends.cudnn.enabled = False` | top of `lerobot_server.py` | SigLIP's patch-embedding Conv2d hits `GET was unable to find an engine` on this GPU/cuDNN/torch combination | **Remove it.** Disabling cuDNN globally forces the slower native conv path for every model in that process |
| `policy_cfg.dtype = "float32"` | `LerobotBackend.__init__` | pi0.5 defaults to bf16, which Volta has no tensor cores for — a hard crash here, not a slowdown | Drop the override and let the checkpoint use bf16; faster and lower memory |
| `torch==2.7.1+cu126` pin | `bootstrap_models.sh` | newer official wheels support only cc≥7.5 | Free to move to current torch |
| `compile_model=False` | `LerobotBackend.__init__` | Triton/`torch.compile` fails on this Volta+torch combination | Re-enable if you run many episodes; it is a throughput win once JIT cost amortizes |

The observation/action-side fixes (camera slot mapping, proprioception frame,
gripper range/polarity, rotation representation, action truncation) are **not**
hardware-dependent — they are about matching each checkpoint's training
convention and must be kept everywhere.

Memory sizing is also V100-shaped: `stop_model()` unloads each model-server
before the next loads because 32GB could not hold several. With 80GB you can
keep more resident and parallelise across models rather than serialising —
but load sequentially even then (see the concurrent-load caveat below).

## Data-integrity audit (2026-08-06) — five defects and how to not reintroduce them

Run before handing results to anyone. Each of these produced plausible-looking
numbers, which is what made them dangerous: none of them crashed, and none
were visible in the output.

**1. Never let file mtimes decide what data is valid.** The report used to
infer "was this episode collected before the last bug fix?" by comparing the
episode's first frame mtime against the model-server file's mtime. mtimes do
not survive `git clone`, `tar -x`, `rsync` without `-t`, or a container
rebuild, and a comment-only edit bumps them. Measured consequence on identical
annotations: the committed report was built from 182 episodes (GreenVLA
R0/R1/R2 + OpenVLA-OFT), regenerating after a fresh clone gave 396 (GreenVLA-R2
+ SmolVLA + pi0 + pi0.5) — the two models carrying the headline result silently
dropped out, and it had already required a manual mtime reset once to rescue 99
valid episodes. Replaced by `data/rollout_provenance.json` + `slava_rollout.
provenance`: exclusions are declared as data, with a reason and a
`clears_when`, reviewable in a diff and identical everywhere. **If you exclude
episodes, say so in that file, never by touching the filesystem.**

**2. A label threshold that is unreachable in one environment.** The failure
ladder decided timeout via `step_count >= max_steps`, but `MAX_EPISODE_STEPS`
is our OUTER cap, while SimplerEnv's gymnasium `TimeLimit` fires at each task's
registered horizon (60 for StackGreenCubeOnYellowCube) — so on SimplerEnv the
condition was never true and every no-contact episode became `unclear` instead
of `no_action_or_timeout`. The dataset showed it perfectly: SimplerEnv 0 vs 115,
LIBERO 199 vs 0. **A metric that splits cleanly along an infrastructural
boundary is a bug until proven otherwise** — check every derived field for
correlation with environment/model/machine before believing it. Termination is
now passed in explicitly (`ran_to_completion`), not inferred from a step budget.

**3. Derived labels must be recomputable, never hand-edited.** Fixing #2
invalidated the labels on 550 already-collected episodes. Re-running GPU
episodes to fix a labeling bug is absurd; editing labels by hand is
indistinguishable from fudging. `scripts/relabel_rollouts.py` recomputes them
from each episode's raw `steps.jsonl`, prints the transition table, and refuses
to write if `success` changes (that value comes from the environment, so if it
moves, the raw data and the annotations disagree — a data problem, not a
labeling one). It reported exactly one transition class: 115 × `unclear` →
`no_action_or_timeout`. **Log enough raw signal per step that any derived field
can be rebuilt later** — that is what made this recoverable.

**4. Unpaired comparison of a paired design.** task.md specifies "парный
дизайн (одна сцена/сид, разные инструкции)", but Δlang was computed from
marginal per-variant success rates. Coverage is genuinely ragged —
`ru_case_swap` is authored for only 8 of 20 scenes (the rest legitimately
`axis_na`), and partial runs left some models with different scene sets per
variant — so those marginals describe different scene populations and their
difference mixes composition with language. Worse, the long-form report pooled
all models into one Δlang: pooled `Δlang_ru_literal` = +11.4 п.п. against a
per-model range of 0…+50, because models at ~0% SR in every language
contribute Δlang≈0 by construction and dilute the rest. Now in
`slava_rollout.stats`: every comparison runs on the anchor ∩ control ∩ variant
scene intersection, with a paired bootstrap that resamples SCENES, plus an
exact McNemar test (task.md asks for it explicitly). Effect on the headline:
OpenVLA-OFT ru_literal Δlang = +37.5 п.п., CI [+12;+62], p=0.031 — and
code_switch +6.2, p=1.000, which is the interesting contrast. GreenVLA-R1's
former "+50 п.п." is now correctly shown as 4 scenes, CI [0;100], p=1.000.

**5. Per-episode state inside a long-lived model-server.** A model-server
outlives every episode it serves. lerobot policies keep an internal
`_action_queue` and only run a real forward pass when it empties, so the tail
of one episode's chunk was executed as the opening actions of the next —
a different scene AND a different instruction variant, and since episodes run
grouped by variant, that leaked across the exact axis being measured. There is
now a `/reset` endpoint (`base_server.py`) called by the orchestrator after
every env reset. **Any state a backend caches between `predict()` calls needs
an explicit per-episode reset**; ask this of every new backend.

Also fixed while in there: SAPIEN contacts are now impulse-filtered
(`scene.get_contacts()` returns zero-force pairs too, which made
`first_contact_object` fire on near-misses and mis-attribute
`target_grounding_error`), and the terminal frame is saved (the loop stored the
pre-action observation and broke on success, so no success GIF ever showed the
completed task).

### Regression tests

`tests/` runs on a bare `python3`, no pip install, by design — this repository
is handed to other people:

```bash
python3 -m unittest discover -s tests -v
```

`test_auto_label.py` pins the label ladder (including that both environments
agree); `test_stats.py` pins Wilson/McNemar against published values and
asserts the composition confound from #4 cannot come back. Extend these rather
than re-deriving the rules from prose.

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

## Debugging low SR: check the INPUT distribution before anything else

Hard-won ordering, after a long run of sessions that each found a real bug
on the *action* side (gripper range, rotation representation, action
truncation, chunk replay) while the largest error of all sat on the
*observation* side, unexamined, for weeks. Actions are where behaviour is
visible, so that's where attention goes — but a policy fed out-of-
distribution proprioception cannot produce sane actions no matter how
correctly you post-process them.

**When a checkpoint ships normalization statistics, they are ground truth
about what it expects. Compare your actual observations against them.**
This is cheap, decisive, and catches an entire class of bugs (wrong frame,
wrong units, wrong polarity, wrong slot order) that no amount of behavioural
staring will isolate:

```python
# what the checkpoint expects
stats = json.load(open(hf_hub_download(ckpt, "norm_stats/bridge/norm_stats.json")))
q01, q99 = stats["norm_stats"]["state"]["q01"], stats["norm_stats"]["state"]["q99"]
# what we actually feed, on a real reset
print(build_state(env))
# then: does each element land inside [q01, q99]? what does it normalize to?
```

Normalized inputs should land roughly in `[-1, 1]`. On 2026-08-05 this check
took minutes and showed GreenVLA was being fed `[-3.24, 0.00, 7.46]` — a
world-frame EE pose where the checkpoint's own quantiles unambiguously
described a robot-base frame. See `slava-greenvla` for the full case.

Corollaries worth internalising:

- **Prose docs are not authoritative about frames or conventions.** GreenVLA's
  own docs say the state is `[x, y, z, roll, pitch, yaw, _pad_, gripper]` —
  true, and useless for deciding *which frame* or *which polarity*. Their own
  inference example fills it with `np.random.rand(8)`. The numbers in
  `norm_stats` were the only real evidence.
- **A from-scratch reimplementation is only independent where it differs.**
  The "pure-upstream reproduction" built to validate this pipeline shared its
  hand-written `build_state()` conventions with the pipeline it was checking,
  so it reproduced both bugs and its agreement was read as confirmation. When
  you build a reference implementation, deliberately derive the parts you're
  trying to validate from a *different* source (the checkpoint's stats, the
  upstream harness's own wrapper) — not from the same docs you already read.
- **If a checkpoint ships no stats for your embodiment, say so out loud.**
  `lerobot/pi0_base` and `pi05_base` ship none at all; `smolvla_base` ships
  stats only for the SO-100 arm. For those, no observation layout can be
  *verified* — pick the best-supported convention, and treat the resulting
  numbers as weakly specified rather than quietly reporting them alongside
  properly grounded ones.
- **Sanity-check against the upstream harness's own policy wrapper** for the
  same embodiment (for SimplerEnv/WidowX:
  `simpler_env/policies/octo/octo_model.py`, branch
  `policy_setup == "widowx_bridge"`). It encodes real conventions —
  camera choice, gripper binarization, euler→axangle — that the model repos
  themselves never document.

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
