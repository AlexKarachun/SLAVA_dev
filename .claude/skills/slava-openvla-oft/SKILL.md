---
name: slava-openvla-oft
description: OpenVLA-OFT model-server specifics for SLAVA rollouts — API, gripper-action bug, chunk-replay/orientation/settle-step bugs found fixing SR=0%. Read slava-model-rollouts first for shared architecture.
---

# OpenVLA-OFT — model-server notes

Split out of `slava-model-rollouts` 2026-08-05 (that skill now holds only
cross-model architecture; read it first for the client-server design, env-
worker contracts, and process-management lessons that apply to every model).
This file is everything specific to `scripts/model_servers/openvla_oft_server.py`
and the `moojink/openvla-oft` upstream it wraps.

## Architecture reference (from the official papers/repos, added 2026-08-05)

Added so future debugging can reason from *why* a convention exists instead
of only pattern-matching prior bugs — every bug found on this model so far
(gripper range/polarity, missing chunk replay, image mirroring) lives
exactly in the gap this section is about: what the model's raw output units
are vs. what the target controller expects. Sourced from Kim/Pertsch et al.,
*"OpenVLA: An Open-Source Vision-Language-Action Model"* (arXiv:2406.09246)
and Kim/Finn/Liang, *"Fine-Tuning Vision-Language-Action Models: Optimizing
Speed and Success"* (arXiv:2502.19645, the OFT paper), cross-checked against
`openvla/openvla` and `moojink/openvla-oft`'s actual source.

**Backbone.** OpenVLA is a fine-tuned **Prismatic-7B** VLM, not a
bespoke architecture: a fused **SigLIP + DINOv2** vision encoder (each runs
separately over 224×224 patches, outputs concatenated channel-wise — DINoV2
was added specifically because Prismatic's own ablations showed it improves
spatial reasoning, which matters for control precision), a 2-layer MLP
projector into the LLM's embedding space, and a **Llama 2 7B** language
model. Vanilla OpenVLA's "action head" is just the LLM's existing
next-token-prediction head aimed at 256 repurposed vocabulary slots — there
is no separate action module at all in the base model.

**Vanilla OpenVLA action representation: discretized, autoregressive.**
Each of the 7 action dims (xyz, roll/pitch/yaw, gripper) is independently
binned into 256 uniform bins spanning the training data's 1st-99th
percentile for that dim (outliers clipped). These 256 tokens **overwrite
the 256 least-used slots at the end of the Llama tokenizer's vocabulary** —
action prediction is literally next-token prediction over a hijacked slice
of the language vocabulary, decoded one dimension at a time, autoregressively,
7 forward passes per control step. This is the actual reason vanilla
OpenVLA is slow (~0.33s/step on an A100, ≈6Hz) — not a hardware limit, an
architectural one.

**What OFT changes, and why — four independent changes, not one:**

| Change | Mechanism |
|---|---|
| Parallel decoding | Action positions get learned "empty" placeholder embeddings + bidirectional attention (not causal) over just those positions — the whole chunk comes out in one forward pass instead of D sequential ones |
| Action chunking | Predict K future timesteps per query (K=8 for LIBERO/Bridge — this is where `NUM_ACTIONS_CHUNK=8` in `prismatic/vla/constants.py` comes from) |
| Continuous L1-regression head | A small MLPResNet (`L1RegressionActionHead`) maps final hidden states straight to continuous values via L1 loss — no binning, no detokenization at all |
| Proprioception input | Robot state is projected (`ProprioProjector`, 2-layer MLP+GELU) into the LLM embedding space as one more input token |

Measured impact on LIBERO (from the OFT paper): 76.5% (vanilla, 4.2Hz) →
90.2% (+chunking/parallel decoding, 108.8Hz) → 95.3% (+continuous L1 head,
109.7Hz) → 97.1% (+wrist cam+proprio, "OFT+", 71.4Hz). A diffusion action
head instead of L1 regression gets statistically the same accuracy (95.4%)
but 26x slower (50 denoising steps reintroduce the sequential bottleneck L1
regression exists specifically to remove) — this is *why* L1 regression was
chosen over the more common diffusion-head pattern used by pi0/SmolVLA.

**Action decode/un-normalize pipeline (this is where the real bugs live):**
1. Raw output — vanilla: bin index → bin-center lookup
   (`ActionTokenizer.decode_token_ids_to_actions`, note the real code
   subtracts 1 from `np.digitize`'s 1-indexed bins before the lookup — an
   easy off-by-one for any reimplementation). OFT: the MLP head's output
   *is* the action, no lookup step exists.
2. **Un-normalization** — the result is still in training-normalized space
   (`BOUNDS_Q99`: dataset's 1st/99th percentile → [-1,1] for LIBERO/Bridge;
   plain `BOUNDS` min/max for ALOHA), selected by `unnorm_key`, stored per
   checkpoint in `dataset_statistics.json`. Wrong `unnorm_key` → right shape,
   wrong scale, silently — "runs but never completes" is exactly this
   failure signature, not a broken model.
3. **Gripper post-processing — the actual root cause of our SR=0% bug.**
   The Open-X-Embodiment/RLDS dataloader convention is gripper ∈ [0,1] with
   0=close/1=open (Bridge is the one dataset that's already [-1,1]) — but
   LIBERO/robosuite's OSC_POSE controller wants ∈[-1,+1] with **inverted**
   polarity, -1=open/+1=close. Applied in this exact order, every real eval
   run:
   ```python
   action = normalize_gripper_action(action, binarize=True)  # [0,1] -> [-1,+1]
   action = invert_gripper_action(action)                     # flip polarity
   ```
   Skip either step and the gripper is scaled wrong or inverted — reaches
   correctly, never grasps. This is a convention mismatch baked into how
   the *training data* was normalized vs. how the *target controller* is
   wired, structurally identical to the image-mirroring bug, just on the
   output side instead of the input side.
4. **Open-loop chunk replay (OFT specific).** The eval harness keeps a
   `deque(maxlen=num_open_loop_steps)`: query once when empty, extend with
   the *whole* predicted chunk, pop-and-execute one action per env step
   until drained before requerying. Executing only `popleft()` once per
   model call instead of draining the whole queue silently discards K-1 of
   every K actions — plausible root cause for "barely moves"/"times out"
   symptoms that look like a model problem but are a harness problem.

## Confirmed real API (from `moojink/openvla-oft` directly, not guessed)

Note the real GitHub org is **`moojink/openvla-oft`**, not `openvla/openvla-oft`
(that URL 404s/requires auth — don't reuse it). `LIBERO.md` confirms the
released `moojink/openvla-7b-oft-finetuned-*` checkpoints just need the
eval script's *default* `GenerateConfig` (`use_l1_regression=True`,
`num_images_in_input=2`, `use_proprio=True`, `center_crop=True`) — our
`openvla_oft_server.py` imports their own `GenerateConfig`/`get_model`/
`get_processor`/`get_action_head`/`get_proprio_projector`/`get_action`
unchanged rather than reimplementing OFT's parallel-decoding +
proprio-projector + L1-regression-head pipeline.

Their `attn_implementation="flash_attention_2"` is already **commented out**
in their own loading code — flash-attn is not required for inference,
skip that (slow, sometimes fragile) build step entirely.

Everything is hardcoded to `torch.bfloat16` in their code (not a flag we can
easily override without patching). On a V100 (no bf16 tensor cores) bf16 ops
still run correctly, just slower (software-emulated, not broken) — accepted
trade-off, not worth forking their repo to force fp16 unless it actually
blocks the smoke test.

`unnorm_key` is **keyed by LIBERO suite name** (`libero_spatial`/`_object`/
`_goal`, with a `_no_noops` fallback) and must be set per-episode from the
prompt's own `suite` field, not hardcoded — our combined
`-spatial-object-goal-10` checkpoint covers all three of our LIBERO suites,
but the unnorm stats are suite-specific. This is why the model-server
`/predict`/`/predict_chunk` contract carries a `meta` dict
(`{task_uid, suite, environment}`) alongside `obs`, not just
pixels+proprioception.

Their `prepare_observation()`/`get_action()` expect `state` =
`eef_pos(3) + axis_angle(3) + gripper_qpos(2)` (8-dim) — converted in
`openvla_oft_server.py` from `env_worker_libero.py`'s
`[gripper_qpos(2), eef_pos(3), eef_quat(4)]` proprioception via
`scipy.spatial.transform.Rotation.as_rotvec()`.

`libero` package needs to be importable in `slava-openvla` but must **not**
be `pip install -e`'d there: doing so hits a real conflict between LIBERO's
and openvla-oft's own PEP 660 editable-install import finders
(openvla-oft's `__editable__...finder.__path_hook__` on `sys.path` ends up
shadowing resolution for other editable packages — `pip show libero` reports
it installed, `import libero` 404s anyway). Fixed with plain
`sys.path.insert(0, LIBERO_ROOT)` instead — this env never touches LIBERO
physics/rendering (that's `env_worker_libero.py`'s job in the separate
`slava-libero` env), so no install machinery is needed, just the module on
the import path. Also needed (plain, mostly-unpinned pip packages — NOT the
old pins from `LIBERO/requirements.txt`, which would downgrade openvla-oft's
own numpy/transformers): `robosuite==1.4.0` (pinned — a newer PyPI
`robosuite` reorganized `robosuite.environments.manipulation.single_arm_env`
and breaks LIBERO's benchmark import), `bddl==1.0.1`, `easydict==1.9`, plus
unpinned `future`, `hydra-core`, `wandb`, `robomimic`, `thop`, `matplotlib`,
`cloudpickle`, `gym` — all pulled in transitively just by importing
`libero.libero.benchmark` for its `GenerateConfig`/task-suite dict, not
because openvla-oft's actual inference path uses them.

## SR=0% root cause (found 2026-08-05) — three independent bugs, all fixed

The 77-episode dataset from an earlier session had 0/77 successes on this
model. Reading `moojink/openvla-oft`'s actual
`experiments/robot/libero/run_libero_eval.py` line-by-line (not guessed)
turned up **three** real, independent bugs — fixing all three took the
smoke-test SR from 0/21 (real episodes, previous session) to **2/2**, at
33-76s/episode (down from ~394s/episode before the chunk-replay fix — 5-8x
faster too, expected since the model is now queried once per 8 steps instead
of every step). Full run afterward: **99/99 episodes, 74/99 = 74.7% SR.**

1. **Missing open-loop action-chunk replay.** `get_action()` returns the
   full predicted chunk (`NUM_ACTIONS_CHUNK=8` for LIBERO, confirmed by
   reading `prismatic/vla/constants.py` — it auto-detects platform from
   `sys.argv`, defaults to LIBERO when nothing matches, which is what our
   model-server's argv gives it). The reference script queries the model
   once, pushes the whole chunk into a `deque`, and pops one action per env
   step, **only requerying once the queue is empty** — i.e. actions 1-7 of
   every chunk are executed completely open-loop, no new observation
   involved. Our old code called `get_action()` fresh on every single env
   step and only ever used `action[0]`, discarding the other 7 — a different
   (always-closed-loop) execution strategy than what the checkpoint was ever
   evaluated with. Fixed via a new generic `/predict_chunk` endpoint
   (`base_server.py`, opt-in per backend via an optional `predict_chunk()`
   method) and a `pending_actions` queue in `run_rollouts.py::run_episode()`
   that drains one action per `env_client.step()` call before requesting a
   new chunk. Camera-frame saving and `success`/`done` checks still happen
   every single sim step (task.md requirement), only the *model query* is
   chunked.
2. **Image mirrored left-right — independent of the chunk bug, likely the
   bigger contributor.** `openvla-oft`'s own
   `experiments/robot/libero/libero_utils.py::get_libero_image()` does
   `img[::-1, ::-1]` on the raw `obs["agentview_image"]` (**both** axes
   reversed = 180° rotation), commented "IMPORTANT: rotate 180 degrees to
   match train preprocessing." Our shared `env_worker_libero.py::_build_obs()`
   does `raw[::-1]` (axis 0 only — a vertical flip, chosen for a
   human-legible D1-dashboard image, matching `scripts/collect_libero.py`'s
   convention — correct for *that* purpose but a different transform).
   Composing them, every frame OpenVLA-OFT received was `single_flip(raw)`
   where it needed `double_flip(raw)` — i.e. a **left-right mirror** of what
   it was trained on (robot arm on the wrong side, spatial relations
   flipped). This does not depend on instruction language at all, so it
   would have suppressed EN and RU success equally. Fixed *scoped to
   `openvla_oft_server.py` only* (`_build_observation()`'s docstring has the
   full derivation) — one extra `[:, ::-1]` mirror applied to the
   already-single-flipped `agentview_rgb`/`wrist_rgb` right before handing
   them to `get_action()`. `env_worker_libero.py` itself is untouched and
   stays neutral for other models.
3. **Missing `num_steps_wait=10` physics-settle steps.** The reference
   `run_episode()` executes 10 steps of the dummy action
   `[0,0,0,0,0,0,-1]` right after `env.set_init_state()`, *before* the
   policy is ever queried ("let objects stabilize in sim") — these steps are
   not logged, not counted against `TASK_MAX_STEPS`, and the model never
   sees them. Our env-worker queried immediately after `set_init_state()`.
   Fixed: `env_worker_libero.py::/reset` now takes an optional
   `num_steps_wait` payload field (default 0, so every other model's
   behavior is unchanged) and runs that many dummy steps internally before
   building the returned obs. Wired up from `run_rollouts.py` via
   `LIBERO_NUM_STEPS_WAIT["openvla_oft"] = 10` in `build_reset_payload()` —
   opt-in per model.

**Verification note:** the smoke-test's `en_canonical` prompt for
`open_the_middle_drawer_of_the_cabinet` ("open the middle drawer of the
cabinet") is an **exact, word-for-word match** to
`benchmark.get_benchmark_dict()["libero_goal"]().get_task(i).language`
(confirmed by calling the real benchmark API, not by reading the `.bddl`
file's own `:language` comment, which is a stale author note and does NOT
match what the benchmark actually serves). So the 2/2 smoke-test success was
run on the literal, unmodified original dataset prompt, not a SLAVA
paraphrase — ruling out "the pipeline only works on our reworded prompts" as
an explanation for the earlier SR=0%.

## OpenVLA-OFT: missing gripper action post-processing — the original bug

Caught earlier in the project by the user's explicit request to
sanity-check results, not by code review, and independent from the three
bugs above (fixed in a prior session, still the right context for anyone
re-deriving this). Symptom: 13 straight episodes across **two different
LIBERO tasks** (drawer-opening and plate-pushing) all failed with
`no_action_or_timeout`, `gripper_state` hovering near 0 the entire episode
in every one, `contacts` always empty despite the arm/proprioception clearly
moving with normal-looking magnitudes. Two different tasks failing
identically was the signal that this wasn't ordinary task difficulty
(OpenVLA-OFT reports ~97% SR on this exact combined checkpoint in their own
paper).

Root cause: `predict()` returned the raw output of `get_action()` directly.
The reference `run_libero_eval.py` never does this — every action it gets
from `get_action()` is piped through its own `process_action(action,
cfg.model_family)` before `env.step()`:
```python
action = normalize_gripper_action(action, binarize=True)  # [0,1] -> [-1,+1]
if model_family == "openvla":
    action = invert_gripper_action(action)  # sign flip
```
Both functions live in `experiments/robot/robot_utils.py`: the RLDS
dataloader convention is gripper ∈ [0,1] with 0=close/1=open, but the
LIBERO env's OSC_POSE controller expects ∈ [-1,+1] with -1=open/+1=close.
Skipping this step meant every gripper command was both wrong-scale AND
inverted — a close command could easily read as a small "open more" delta,
so the gripper effectively never closed. This produces plausible-*looking*
rollout data (real episode, real physics, real trajectory) with a
systematically broken actuator — the "results look fine but the model can't
actually do what it should" failure mode, hardest to catch from logs alone.

**Fix:** `predict_chunk()` now calls `normalize_gripper_action()` +
`invert_gripper_action()` on the **whole chunk array at once** (elementwise-
safe since both ops act on the last dim) before returning, matching
`process_action()` exactly. The 13 pre-fix episodes were purged from
`rollout_annotations.jsonl` (backed up, episode dirs archived, not deleted)
rather than left in the dataset.

**Takeaway for any other model-server backend:** each vendor's reference
eval script may apply action post-processing beyond what their "load model,
call predict" quick-start docs show — always check the *eval loop*, not
just the *inference call*, for a `process_action`/similar step before
assuming the raw model output is ready to hand to `env.step()`. (This exact
lesson generalized directly to the camera-swap bug found later in
pi0/pi0.5/SmolVLA — see `slava-lerobot-policies`.)
