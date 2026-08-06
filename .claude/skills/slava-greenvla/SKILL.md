---
name: slava-greenvla
description: GreenVLA (R0/R1/R2) model-server specifics for SLAVA rollouts — API, chunk-shape bug, embodiment/norm_stats check, the gripper-range-mismatch fix that took SR from 0% to real numbers. Read slava-model-rollouts first for shared architecture.
---

# GreenVLA (R0 / R1-bridge / R2-bridge) — model-server notes

Split out of `slava-model-rollouts` 2026-08-05 (that skill now holds only
cross-model architecture; read it first). All three stages share one file,
`scripts/model_servers/greenvla_server.py`, and one conda env,
`slava-greenvla` — built from GreenVLA's own repo
(`github.com/greenvla/GreenVLA`, public, HEAD `952a80c` as of the original
session), **not** `huggingface/lerobot`. GreenVLA's repo is an older
*vendored* lerobot fork (its own `lerobot/common/policies/greenvla_policy/`)
— confusingly similar import paths to the real lerobot but a different
codebase; don't assume anything checked against `huggingface/lerobot`
(see `slava-lerobot-policies`) also holds here.

Curriculum: **R0** (`SberRoboticsCenter/GreenVLA-5b-base-stride-1`,
cross-embodiment generalist) → **R1**
(`SberRoboticsCenter/GreenVLA-5b-stride-1-R1-bridge`, WidowX/bridge-
specialized fine-tune) → **R2**
(`SberRoboticsCenter/GreenVLA-5b-stride-1-R2-bridge`, "RL-aligned" final
stage, discovered mid-project; published SR Partial 94.5%/Entire 80.5% vs
R1's Partial 89.6%/Entire 72.9%). SimplerEnv/bridge only for all three —
GreenVLA has no LIBERO checkpoint in scope here.

## Architecture reference (from the official repo/paper, added 2026-08-05)

Sourced from direct reads of `github.com/greenvla/GreenVLA`'s actual source
(not just docs) plus arXiv:2602.00919 ("Green-VLA: Staged Vision-Language-
Action Model for Generalist Robots"). Confidence is marked per claim below:
**[CODE]**/**[CONFIG]** = read the actual file/`config.json` byte-for-byte
(treat as ground truth), **[DOC]**/**[PAPER]** = from README/docs/paper
prose (accurate but not hand-verified char-by-char), **[UNDOCUMENTED]** =
genuinely not found anywhere, stated as absent rather than guessed.

**Not one fixed architecture — a policy class with 3 modes.**
`GreenVLAPolicy` supports `model_mode ∈ {flow_matching, token_prediction,
mixed}` **[CODE]** — the repo also contains FAST-tokenizer autoregressive
code, but **all three checkpoints we use (R0-base, R1-bridge, R2-bridge)
have `model_mode: "flow_matching"` in their actual `config.json`** **[CONFIG,
verified for all three]**. So for us: flow-matching regression, full stop —
not autoregressive, not DDPM-diffusion, not plain MSE.

**Backbone: Qwen3-VL-4B-Instruct, but Sber's own action-augmented variant.**
All three checkpoints point `base_vlm_model` at
`SberRoboticsCenter/Qwen3-VL-4B-Instruct-action` **[CONFIG]**, not the stock
Qwen checkpoint. Earlier Green-VLA iterations used PaliGemma (3B) instead —
per the paper directly: *"In earlier versions we used PaliGemma... In its
latest configuration [Qwen3-VL-4B-Instruct]"* **[PAPER §5]** — which is why
some internal helper names/comments in the codebase still carry
PaliGemma/`big_vision`-style naming, inherited from that earlier lineage.

**Action expert: a second transformer, attending the VLM's *cached* KV —
architecturally the Physical Intelligence π0 pattern** (README credits
`openpi`/π0 and `starVLA` as references **[DOC]** — cross-reference
`slava-lerobot-policies`'s pi0/pi0.5 architecture section for the same
underlying idea from its original source). At each flow-matching step, the
action-expert's layers attend to the frozen VLM's **cached** key/value
states — the VLM is not re-run per denoising step **[CODE —
`modeling_greenvla_policy.py::denoise_step`]**. `expert_block_stride`
controls how often (every Nth VLM layer) — this is exactly what the
**"stride-1" vs "stride-4" checkpoint naming means**: stride-1 = action
expert attends every VLM layer (more compute, what all our Bridge
checkpoints use, confirmed `"expert_block_stride": 1` **[CONFIG]**);
stride-4 = only every 4th layer (cheaper, used by the fractal/calvin
lineage, not ours).

**Flow matching: 10-step Euler integration, same family as pi0/pi0.5/
SmolVLA** (see `slava-lerobot-policies` for the shared math) —
`num_steps=10` for all three checkpoints **[CONFIG]**:
```python
noise = sample_noise((bsize, n_action_steps, max_action_dim), device)
dt = -1.0 / self.config.num_steps
x_t, time = noise, 1.0
while time >= -dt / 2:
    v_t = self.denoise_step(state, ..., x_t, time.expand(bsize))
    x_t += dt * v_t
    time += dt
return x_t   # (batch, n_action_steps=10, max_action_dim=48)
```
**[CODE, `sample_actions()`]** — training even reuses π0's Beta(1.5,1.0)
time-sampling trick (`greenvla_utils.py::sample_beta`) **[CODE]**.

**A unified 64-dim cross-embodiment action space exists in code but is
OFF for the checkpoints we use.** The paper's headline idea — *"a unified
action space 𝒜u⊂ℝ64 with a fixed semantic layout"* **[PAPER §4.3]** — has
concrete, code-confirmed slot assignments (identical across
`bridge.py`/`fractal.py`/`calvin.py`): xyz→slots 35:38, roll/pitch/yaw→
slots 42:45, gripper→slot 13:14 **[CODE]**. But **all three of our
checkpoints have `"map_to_unified_space": false`** **[CONFIG, verified for
all three]** — state/action stay in the embodiment's native 7/8-dim layout,
just zero-padded to `max_action_dim=48`, not actually remapped into the
shared space at inference. Whether R0's *pretraining* used unified-space
mapping before it got turned off for R1/R2 fine-tuning wasn't confirmed
(training YAMLs weren't checked) — flag this if ever touching R0 directly
for a genuinely new embodiment.

**R0's ~19-robot claim, independently confirmed (not just repeated):**
the per-embodiment transform directory
(`lerobot/common/datasets/data_transforms/robots/`) has exactly 19 files
— counted directly, matches the figure already in our own notes.

**Training curriculum — what R2's "RL-aligned" stage literally means (this
was previously undocumented, now sourced).** R2 is **literal offline RL**,
two distinct named mechanisms, both quoted directly from the paper §4.5:
1. **Implicit Q-Learning (IQL)** — a value/Q-function fit via expectile
   regression from offline trajectories, then *"the gradient of the
   Q-function with respect to the action is computed... added to the
   original action"* — Q-guided action refinement on top of the R1 SFT
   policy, conceptually similar to Diffusion-QL-style critic steering.
2. **Source-distribution ("noise actor") optimization** — a small separate
   actor network learns to shape the *initial noise* seeding the
   flow-matching ODE, trained via policy-gradient RL to maximize return.
   R2-bridge's own model card describes training data as *"Bridge dataset
   plus SimplerEnv rollouts for the WidowX robot"* — i.e. R2 was
   specifically optimized against episode return **in SimplerEnv itself**,
   not just against matching the demonstration distribution. This is a
   real, substantive difference from R1, not a marketing label — and it's
   why R2's behavior can differ from R1's in edge cases even on the exact
   same task. **[UNDOCUMENTED]**: the actual reward function optimized
   (task success? distance-to-goal? something denser?) is never stated
   anywhere public.

**The rotation/gripper bug, now conclusively confirmed at the source level
— not inferred, checked directly.** The entire `greenvla_policy` module
(`modeling_greenvla_policy.py`, `greenvla_tokenizer.py`,
`greenvla_utils.py`, `configuration_greenvla_policy.py`) was grepped for
`euler|rotvec|axis_angle|quaternion|rotation|gripper` — **zero matches**
**[CODE]**. `BridgeInputsTransform`/`BridgeOutputsTransform` (the full
extent of Bridge-specific logic in the model's own inference path — see
below) do nothing but slice/pad/zero-fill; they never touch rotation
representation or gripper range at all. **This means GreenVLA was never
silently doing a conversion we missed — it genuinely performs none, ever,
for Bridge.** Whatever Euler convention (radians, intrinsic/extrinsic, axis
order — all **[UNDOCUMENTED]**, never stated anywhere) and whatever gripper
range the source dataset (`IPEC-COMMUNITY/bridge_orig_lerobot`, itself
derived from BridgeData-V2/Open-X-Embodiment) happens to use is exactly
what comes out, unchanged, labeled only by the variable names `roll,
pitch, yaw`. **Adaptation to any downstream controller's actual convention
is 100% the integrator's responsibility, with zero help or hint from
GreenVLA's own code or docs** — exactly the gap our gripper-rescale and
`euler2axangle` fixes had to fill from scratch.

**`action_horizon=2` benchmarking note — verified verbatim, and what it
actually means mechanically.** `docs/INFERENCE.md`: *"For Bridge (WidowX)
benchmarking on SimplerEnv we used `action_horizon=2`."* The model natively
predicts a 10-step chunk per forward pass (`n_action_steps=10`) — this note
means Sber's own eval harness only **executes the first 2 timesteps
open-loop before re-invoking the model** (closed-loop replanning every 2
env steps, not every 10) — an eval-harness choice documented only in prose,
stored in no checkpoint config. Matches exactly what our own
`BRIDGE_ACTION_HORIZON = 2` in `greenvla_server.py` already replicates.

## Confirmed real API (from `examples/example_inference_bridge.py` +
`docs/INFERENCE.md`, read directly, not guessed)

```python
from lerobot.common.policies.factory import load_pretrained_policy
policy, input_transforms, output_transforms = load_pretrained_policy(checkpoint, data_config_name="bridge")
# raw obs: {"observation/state": float32[8] (x,y,z,roll,pitch,yaw,_pad_,gripper),
#           "observation/image": uint8 HWC, "prompt": str}
# policy.select_action(batch) -> normalized actions (action_horizon x 7)
# output_transforms({"actions":..., "state":...}) -> real actions (x,y,z,roll,pitch,yaw,gripper)
```

`data_config_name="bridge"` resolves WidowX-specific `norm_stats/bridge/
norm_stats.json` — confirmed present on all three checkpoints (R0, R1, R2)
via direct `huggingface_hub.list_repo_files()` inspection, not guessed from
the checkpoint name.

The 8-dim state is **end-effector pose**, not joint qpos —
`env_worker_simpler.py` exposes this separately as `obs["ee_pose"]`
([x,y,z,qw,qx,qy,qz], read from the `ee_gripper_link` global pose) +
`obs["gripper_closedness"]`, alongside the joint-qpos-based
`proprioception` field other backends use. Roll/pitch/yaw are derived from
the quaternion via `scipy.spatial.transform.Rotation` (SAPIEN's `wxyz` →
scipy's `xyzw` reorder — checked correct during the transform-factory
audit below).

`actions` from `output_transforms(...)["actions"]` carries a leading batch
dim of 1 in addition to the `(action_horizon, 7)` shape the README's
single-sample example implies (that example's `actions[0]` already assumed
batch=1 was squeezed away, which isn't the case here) — a real bug caught
the hard way: a live rollout crashed downstream with `action.shape ==
(10, 7)` instead of `(7,)` once handed to `env.step()`, because
`actions[0]` was pulling the whole horizon instead of one action. Fixed
with `np.asarray(actions).reshape(-1, action_dim)` first, correct whether
or not a batch dim is present.

## Open-loop chunk size: `action_horizon=2`

GreenVLA's own `docs/INFERENCE.md` "Benchmarking Notes": "For Bridge
(WidowX) benchmarking on SimplerEnv we used action_horizon=2" — found by
re-reading their docs after R0/R1's low SR, not a guess. The model's own
`n_action_steps=10` is fixed/baked into the checkpoint (not runtime-
adjustable); `predict_chunk()` takes only the first 2 of the predicted
10-length chunk and the orchestrator executes them open-loop via the same
generic `/predict_chunk` mechanism built for OpenVLA-OFT (see
`slava-openvla-oft`) — matches their reported protocol exactly.
Empirically: implementing this did **not**, on its own, change R0's
freezing symptom (37/60 identical consecutive-hash frames pre- and
post-fix) — ruled out as the *sole* cause of R0/R1's low SR, though still a
valid correctness fix worth keeping.

## The actual root cause: gripper range mismatch (found 2026-08-05, fixed)

**This is the fix that took R2 from 0% to a real, non-zero, growing SR**
(1/1 → 1/3=33.3% → kept climbing as more episodes completed) — found on the
4th investigation pass, after embodiment/norm_stats checks and a deep
transform-factory audit (both below) turned up nothing.

GreenVLA's raw gripper channel values observed in real rollouts stay
entirely within ~[0.02, 0.98] (never negative) — a [0,1] convention
(0=close, 1=open), consistent with common real-robot BridgeData action
encodings. But SimplerEnv/ManiSkill2's WidowX gripper controller
(`PDJointPosMimicControllerConfig` in
`ManiSkill2_real2sim/mani_skill2_real2sim/agents/configs/widowx/
defaults.py`) is built with `normalize_action=True`, which expects actions
in **[-1, 1]** mapped linearly to the joint's `[lower, upper]` range —
sending a raw [0,1] value straight through means a "fully close" command
of ~0 only reaches the *midpoint* of the joint range (half-closed), never a
firm grasp. `env_worker_simpler.py` applies no gripper post-processing at
all (unlike LIBERO/OpenVLA-OFT, which needed normalize+invert — see
`slava-openvla-oft`). Empirical evidence that confirmed this before writing
the fix: `gripper_state` (actual physical closedness) never exceeded ~0.6
in observed rollouts even when the model clearly intended a firm grasp
(contact with target registered, action near 0).

**Fix**, in `predict_chunk()` right before returning the chunk:
```python
chunk[:, -1] = 2.0 * chunk[:, -1] - 1.0
```
Rescales [0,1] → [-1,1] without needing a sign flip — the polarity already
matches (GreenVLA's ~1=open maps to +1=open, ~0=close maps to -1=close
under this env's convention). Shared across R0/R1/R2 since they share this
one file; **confirmed empirically on R2** (0% → real, growing SR); **R0/R1
got the code fix at the same time but were not immediately re-validated**
(deferred to backlog under time pressure, all GPUs given to R2 first) — a
subsequent session reran R0/R1 with this fix in place, check
`docs/rollout_report.html`'s per-model breakdown / `AGENTS.md`'s backlog
history for the actual resulting numbers rather than trusting this note.

**All pre-fix R0/R1/R2 episodes were purged** from
`rollout_annotations.jsonl` (episode dirs archived, not deleted — see
`rollouts/episodes_archived_greenvla_pre_action_horizon_fix/` and the
corresponding `.bak_*` files) so reruns collected fresh data under the same
run_ids. `generate_rollout_report.py`'s `annotate_provenance()` also
independently catches this class of issue by comparing each episode's
first-frame mtime to `greenvla_server.py`'s mtime, as a defense-in-depth
check for the *next* fix.

## R0/R1 embodiment check (user question, answered from source)

Confirmed via `huggingface_hub.list_repo_files()` on both checkpoints (not
guessed from the name): **both R0 and R1 ship a
`norm_stats/bridge/norm_stats.json`**, so `data_config_name="bridge"`
resolves WidowX-bridge normalization for both — not Google Robot/fractal.
**But R0 is a cross-embodiment generalist base checkpoint** — its repo has
norm_stats for 19 different robots (agibotworld, biplay, bridge, droid,
fractal, galaxeaworld, rdt, several robocoin/robomind variants) — while
**R1's repo has ONLY `norm_stats/bridge/`**, confirming it's the
bridge-specialized fine-tune stage. Real, source-verified explanation for
why R0 tends to freeze/underperform R1: R0 was never specifically
fine-tuned toward WidowX, it just has the right normalization stats to be
*evaluated* on it — matches the R0-base → R1-bridge → R2-RL-aligned
curriculum.

## Deep audit of the actual transform factory — no bug found there

Re-checked against GreenVLA's own source (not just the quick-start
example) given R0/R1's low SR, before the gripper-range fix above was
found. Read `lerobot/common/policies/factory.py::load_pretrained_policy`
(which `greenvla_server.py` calls directly — we do NOT reimplement their
pipeline, we use their real `input_transforms`/`output_transforms`),
`lerobot/common/utils/inference_transforms.py::get_torch_{input,output}_
transforms`, `lerobot/common/datasets/data_transforms/robots/bridge.py`
(`BridgeInputsTransform`/`BridgeOutputsTransform`), and
`lerobot/common/datasets/torch_transforms.py::parse_image_helper`.
Findings: state layout (`[x,y,z,roll,pitch,yaw,pad,gripper]`, pad-masking)
matches `greenvla_server.py` exactly; the output pipeline is
`Unnormalize(norm_stats) → slice-to-7-dims`, nothing else, already done via
their own `output_transforms`; `parse_image_helper` does **no**
flip/rotation at all (dtype/CHW→HWC only), so there's no hidden orientation
expectation to mismatch — consistent with `env_worker_simpler.py` not
flipping. Quaternion→euler conversion checked correct. **No bug surfaced
this pass** — the gripper-range mismatch above was one level lower (in
`env_worker_simpler.py`'s controller config, not in GreenVLA's own
transform pipeline) and needed a different kind of check (comparing the
env's controller expectations against the model's observed output range,
not re-reading the model's own transform code again).

## Deep audit pass #3 (2026-08-05, after the user flagged the gap as a "red flag" against GreenVLA's own README numbers)

User's concern: GreenVLA's README reports R1 SimplerEnv-bridge Entire Avg
72.9% (R2: 80.5%), while our R1 rerun (with the gripper fix) got 0/28 raw
SR — asked to check every non-obvious place before accepting that as
"expected." Checked, in order, with a spare GPU freed up for live probing:

1. **Episode length / TimeLimit truncation.** Confirmed via `register_env`
   calls in `put_on_in_scene.py`: `StackGreenCubeOnYellowCubeBakedTexInScene-
   v0` is registered with `max_episode_steps=60` (not all bridge tasks share
   one value — `PutEggplantInBasketScene-v0` is 120). Our env-worker's
   `done = terminated or truncated` correctly picks up gym's own `TimeLimit`
   truncation at exactly step 60 — verified empirically on a live episode's
   `steps.jsonl`. **A one-off scare while investigating this:** one archived
   episode file showed step numbers going 1→60→1→18→1→... — looked like a
   138-step episode at first glance (138 lines in the file), but is actually
   3 separate past episode ATTEMPTS appended to the same log file (from
   earlier purges/reruns this session), each correctly capped at ≤60. Not a
   bug — a reminder that `steps.jsonl` files are append-only across re-runs
   of the same `run_id` and line count ≠ step count.
2. **Visual-matching / `prepackaged_config`.** SimplerEnv's `simpler_env.
   make()` (`simpler_env/__init__.py`) unconditionally sets `prepackaged_
   config=True` and `obs_mode="rgbd"` for every task, including
   `widowx_stack_cube` — confirmed our env-worker calls `simpler_env.make
   (task_name)` (not raw `gym.make()`), so this is applied correctly, not
   bypassed.
3. **Delta-vs-absolute action framing.** WidowX's own controller config
   (`ManiSkill2_real2sim/agents/configs/widowx/defaults.py`) is
   `PDEEPoseControllerConfig(frame="ee", ...)` under an `arm_pd_ee_delta_
   pose` name — genuinely delta, EE-frame actions, not absolute pose. This
   was worth checking because `example_inference_bridge.py`'s own docstring
   describes the output transforms as doing "denormalize + delta-to-
   absolute conversion" — alarming phrasing. Read the actual
   `BridgeOutputsTransform` code (`data_transforms/robots/bridge.py`): it
   only slices `actions[:, :7]`, no addition of `state`, no pose-frame
   conversion at all. The docstring's "delta-to-absolute" is loose/
   inaccurate wording for "denormalize a delta from token-space into real
   physical units" — not a literal relative→absolute pose conversion. No
   mismatch with WidowX's delta-frame controller.
4. **`evaluate()`'s actual success condition** (`put_on_in_scene.py`):
   standard bbox-overlap (`xy_flag`+`z_flag`, 2cm z-tolerance) plus a
   contact-exclusivity check (source object must not be touching anything
   besides the target/robot). Nothing exotic, nothing we're bypassing or
   passing different kwargs into.
5. **GreenVLA's own repo has no dedicated SimplerEnv eval script at all** —
   checked both the local clone and the live GitHub repo (`examples/`
   contains only 4 inference-example scripts, no benchmark harness). Their
   reported numbers must come from an external eval script following
   SimplerEnv's own standard pattern (the one already cross-checked above),
   not some undocumented GreenVLA-specific eval convention we're missing.

**Interim conclusion after these 5 checks (superseded below — kept for the
audit trail):** GreenVLA's README reports only an aggregate "Entire Avg"
across **all 4** WidowX/bridge tasks (spoon-on-towel, carrot-on-plate,
**stack-cube**, eggplant-in-basket) — confirmed via direct WebFetch of the
README table, no per-task breakdown published anywhere. Stacking is
plausibly the hardest of the four (precise grasp AND precise placement AND
zero extraneous contact), so comparing our single-task 0/28 against the
4-task aggregate was likely never fair, independent of pipeline
correctness. This was the best available explanation at the time — but a
real code bug was found on the very next pass (below), so treat this
aggregate-comparison point as a real *contributing* factor, not the whole
story.

## 6th check, the actual bug: rotation representation mismatch (found 2026-08-05)

User pushed back on the "aggregate comparison" conclusion above and asked
to keep checking non-obvious places. Read
`PDEEPoseController.compute_target_pose()`
(`ManiSkill2_real2sim/agents/controllers/pd_ee_pose.py:192-195`):
```python
delta_pos, delta_rot = action[0:3], action[3:6]
delta_quat = Rotation.from_rotvec(delta_rot).as_quat()[[3, 0, 1, 2]]
```
`Rotation.from_rotvec()` — the controller expects the rotation part of the
action to be an **axis-angle rotation vector**, not three Euler angles.
GreenVLA's own docs describe both state and action as
`[x,y,z,roll,pitch,yaw,gripper]` — genuine Euler-angle terminology (the
BridgeData/RT-X convention), in explicit contrast to LIBERO/OpenVLA-OFT's
proprioception, which its own docs call "axis_angle" for the equivalent
quantity — different embodiments' docs deliberately using different words
for different representations, not interchangeable.

**Confirmed this conversion is actually required, not guessed,** by reading
SimplerEnv's own reference RT1 policy wrapper
(`simpler_env/policies/rt1/rt1_model.py:197-205`): it has an explicit
`action_rotation_mode == "rpy"` branch that does exactly
`euler2axangle(roll, pitch, yaw)` before hooking the result up to
`action["rot_axangle"]` and sending it to this same env — i.e. this is the
documented, standard way SimplerEnv's own harness handles a policy whose
native rotation output is Euler. `greenvla_server.py` sent roll/pitch/yaw
straight through with no conversion at all. For small rotations the two
representations are numerically close (first-order approximation), which is
exactly why rough reaching/grasping still worked (real contact with the
correct object, per the `target_grounding_error`/`relation_binding_error`
split seen in R1's data) while precise stacking — which needs the source
cube's final orientation within a tight tolerance — never quite landed.

**Fix:** in `predict_chunk()`, right after the existing gripper 2x-1
rescale, convert each chunk row's rotation columns via
`transforms3d.euler.euler2axangle(roll, pitch, yaw)` (installed into
`slava-greenvla` — wasn't a prior dependency). Applies to R0/R1/R2 alike
(shared file).

**Validated two ways, same session:**
1. **Pure-upstream reproduction** — a fresh conda env
   (`greenvla-simpler-repro`) with zero SLAVA_dev code, running GreenVLA's
   own `load_pretrained_policy()` + SimplerEnv's own env/eval-loop pattern
   directly, with only the same class of minimal glue every other policy
   wrapper in that repo needs (building `observation/state` from the raw
   env, applying the same gripper+rotation fixes before `env.step()`).
   Building this env hit a **second, independent, genuinely interesting
   bug**: `sapien==2.2.2` (built pre-numpy-2.0) segfaults on `env.step()`
   with numpy≥2 — confirmed by diffing installed package versions against
   the already-working `slava-simpler` env (numpy 1.24.4 there vs 2.4.6 in
   the fresh env, silently pulled in transitively by the GreenVLA/
   transformers stack). Fixed by pinning `numpy==1.26.4` (the newest 1.x
   release — satisfies both SAPIEN's ABI requirement and GreenVLA's own
   `pandas`/`datasets` dependency, which needs `>=1.26.0`). `conda create
   --clone` (tried on both `slava-greenvla` and `slava-simpler`) failed
   both times with a conda-solver error choking on pip-only packages during
   clone — a known conda limitation with mixed conda+pip envs, not specific
   to this project; building the env fresh with plain `pip install` sidestepped it.
2. **Our own pipeline, rerun with the fix** — purged the 28+28 pre-fix R0/R1
   episodes (archived to `rollouts/episodes_archived_greenvla_r0_r1_pre_
   rotation_fix/`, backed up to `.bak_before_greenvla_rotation_fix`) and
   relaunched both.

Check `docs/rollout_report.html` / AGENTS.md's most recent session log for
the actual resulting numbers from both — this file was updated mid-run,
before either finished.

## `normalization_mode`: real asymmetry in R0's config, real drift, but NOT the SR explanation (2026-08-05)

Investigated after R0 finished its rotation-fix rerun at 0/28 with all 28
episodes labeled `unclear` and `first_contact_object=null` — i.e. R0 never
touched anything, while the paper (arXiv:2602.00919, Table 4) reports R0 at
**91.7% pick / 33.3% success on Cubes**. That gap (91.7% pick → 0% contact)
is not "a generalist checkpoint underperforms"; it demanded a mechanism.

**Config diff, R0 vs R1** (`config.json` on the Hub, read directly, and the
only three fields that differ at all):

| field | R0 | R1 |
| --- | --- | --- |
| `normalization_mode` | `quantile` | `mean_std` |
| `is_knowledge_insulation` | `false` | `true` |
| `tokenizer_max_length` | `832` | `356` |

`norm_stats/bridge/norm_stats.json` is **byte-identical** between R0 and R1
(checked key by key, both `state` and `actions`) — so the difference is
purely which formula consumes those stats.

**The mechanism** (`UnnormalizeTorch` in
`lerobot/common/datasets/torch_transforms.py`, read directly):
```python
# quantile
return (data_tensor + 1.0) / 2.0 * ((q99 - q01) + 1e-6) + q01
# mean_std
return data_tensor * (std + 1e-6) + mean
```
mean_std maps raw 0 → `mean` (≈0 for delta actions: z-dim mean=0.0013).
quantile maps raw 0 → `(q99+q01)/2`, the **midpoint of the quantile band**,
which is only 0 if the band is symmetric. For the z-dimension it is not:
`q01=-0.0252, q99=0.0427` → raw 0 unnormalizes to **+0.00875 m per step**.
A policy whose raw output hovers near zero therefore gets a constant upward
push instead of standing still.

**Verified numerically, not inferred.** Measured R0's actual raw
(pre-unnormalize) `select_action()` output on live steps: z-dim values sat
in ≈[-0.10, +0.01]. Feeding those exact measured values through both
formulas predicts **+0.45 m** cumulative z-drift over 60 steps under
quantile vs **+0.05 m** under mean_std. Observed in real rollouts:
**+0.26…+0.43 m** under R0's native quantile, **~0.01…0.03 m** with
mean_std forced. Prediction matches observation; the arm visibly flies up
out of frame by step 60 (confirmed on camera PNGs across 8/8 episodes).

**But forcing `mean_std` does NOT restore success — this is the important
negative result.** Ran, all with both existing fixes on:

| run | n | SR |
| --- | --- | --- |
| R0 + `mean_std` override, plain seed loop | 20 | 0/20 |
| R0 + `mean_std` override, real `prompts_v0.jsonl` grid | 28 | 0/28 |
| R1 + `quantile` override (symmetric control) | 20 | 1/20 |

With mean_std the arm stops flying away — and then just hovers, never
reaching the cube. The symmetric control matters: forcing R1 into quantile
does *not* reproduce R0's total failure (R1 still lands a success), so
`normalization_mode` alone is not sufficient to explain a 0% SR.

**Conclusion, and why the official numbers were left alone.** The quantile
zero-point asymmetry is real, is R0-specific, and really does cause the
drift. It is *not* our bug — it is what the checkpoint's own config asks
for. Since overriding it does not recover success, there is no evidence the
authors' config is wrong, and overriding it for the official run would mean
benchmarking R0 under a protocol its authors never specified. Official
R0/R1/R2 results are therefore reported as-configured, no override. Do not
"fix" this without new evidence.

**Ruled out in the same pass** (checked, not assumed): `is_knowledge_insulation`
is dead code for us (only read when `model_mode == "mixed"`; all three of our
checkpoints are `flow_matching`). `tokenizer_max_length` 832-vs-356 is a
deliberate upstream choice documented in their own
`conf/finetune_greenvla_bridge.yaml` ("for a bridge (there is a one image, we
can reduce the amount of tokens)"), read from each checkpoint's config
automatically. Tokenizers for all three stages resolve from
`config.base_vlm_model` — identical across R0/R1/R2, not a source of divergence.

## R0 fails on the EASY tasks too — the strongest open signal (2026-08-05)

To separate "stacking is just hard" from "something systematic is broken",
ran native R0 (no override, both fixes on) on the other bridge tasks via the
pure-upstream harness:

| task | our R0 | paper's R0 (Table 4, success) |
| --- | --- | --- |
| `widowx_put_eggplant_in_basket` | **0/10** | **88.5%** |
| `widowx_carrot_on_plate` | **0/10** | 25.0% |
| `widowx_stack_cube` | 0/20 | 33.3% |

**Eggplant is the paper's easiest bridge task and we score zero on it.**
A generalist checkpoint being weak does not produce 0/10 where the authors
report 88.5%. Treat this as the strongest evidence that a systematic bug
remains somewhere in the SimplerEnv path — shared by all three GreenVLA
stages (R2's 21% would then be R2's RL-alignment partially compensating,
not proof the path is correct).

**Top lead, found but NOT yet tested** (2026-08-05, end of session):
SimplerEnv's own reference wrapper for this exact embodiment
(`simpler_env/policies/octo/octo_model.py`, `policy_setup == "widowx_bridge"`)
**binarizes** the gripper:
```python
action["gripper"] = 2.0 * (raw_action["open_gripper"] > 0.5) - 1.0
```
Our `greenvla_server.py` instead passes the continuous value through
`chunk[:, -1] = 2.0 * chunk[:, -1] - 1.0`. Same affine shape, but no
threshold: a model output of 0.6 becomes a weak `+0.2` instead of a decisive
`+1.0`, and 0.4 becomes `-0.2` instead of `-1.0` — the gripper never fully
closes. **This is precisely the bug class already confirmed on OpenVLA-OFT**
(see `slava-openvla-oft`: missing `normalize_gripper_action(binarize=True)`
took it from 0% to 74.7%). The earlier "gripper range fix" note above got
the *range* right and the *binarization* wrong. Test this first next
session, on all three GreenVLA stages, and check whether the lerobot
policies on SimplerEnv need the same treatment. Note the same file also
shows the Google-robot branch using a *relative* (previous − current)
sticky-gripper scheme — that one is embodiment-specific, do not copy it to
WidowX.

## PROPRIOCEPTION FED IN THE WRONG COORDINATE FRAME (found 2026-08-05, strongest root-cause candidate yet)

**The checkpoint's own `norm_stats` tell you the expected frame — read them
before trusting any prose about the state layout.** For the Bridge state
xyz slots:

| slot | q01 | q99 |
| --- | --- | --- |
| x | 0.1708 | 0.4532 |
| y | -0.1692 | 0.2355 |
| z | -0.0555 | 0.1952 |

x strictly positive in [0.17, 0.45], y roughly symmetric about 0, z small
and centred near 0 — that is unmistakably a **robot-base frame**, not world
coordinates.

What we actually fed: `link.get_pose()` on `ee_gripper_link`, which in
SAPIEN is the **global/world** pose. Measured at reset in
`widowx_stack_cube`:

```
robot root pose p:          [0.147, 0.028, 0.870]
ee_gripper_link GLOBAL p:   [-0.145, 0.034, 1.005]   <- what we fed
ee_gripper_link BASE   p:   [ 0.292, -0.006, 0.135]  <- what the model expects
```

The WidowX base sits at z≈0.87 in these scenes, so the global z is ~5x above
q99, and the global x is *negative* — the opposite sign of the entire
training range. After the checkpoint's own quantile normalization:

```
global (what we fed) -> [-3.24, 0.00, 7.46]
base   (correct)     -> [-0.14, -0.19, 0.52]
```

Normalized proprioception should land roughly in [-1, 1]. We were handing
the model **-3.2 and +7.5 on every single step, of every episode, for all
three GreenVLA stages.** That is far outside anything it saw in training and
is sufficient on its own to explain near-zero SR regardless of how correct
the action-side handling is.

**Fix:** convert to base frame before building the state —
`pose = env.unwrapped.agent.robot.get_root_pose().inv() * pose` — and derive
roll/pitch/yaw from that same base-relative pose, not the global one.

**Status of the behavioural confirmation — read before claiming this fixed
anything.** The *input* error is proven arithmetically and is not in
dispute: the values fed were far outside the checkpoint's own quantiles, on
every step. What is **not** yet established is how much SR it buys back. A
4-way ablation on `widowx_stack_cube` (R1, plain seed loop, n=10 each:
world+closedness / base+closedness / base+openness, plus R0 on eggplant with
both fixes) was still running when this was written and had **not separated**
the arms — roughly 1/6 for the unfixed control vs 2/7 for each fixed arm at
that point. Two things to be careful about when finishing it:

1. n=10 per arm cannot resolve a difference between, say, 10% and 30%. Do
   not read a 1-episode gap as a result.
2. The control arm scoring **anything** (1/6) is itself a discrepancy worth
   explaining: the production run of R1 scored 0/28. The diagnostic resets
   with a plain `env.reset(seed=k)` loop, whereas production resets with
   `options={"obj_init_options": {"episode_id": ...}}` over 4 fixed
   episode_ids × 7 variants. Those are different object layouts, and the
   4 production episode_ids may simply be harder. Worth confirming before
   comparing any diagnostic number against a production number — they are
   not the same distribution.

**Why every previous investigation missed it, and the methodological lesson.**
The "pure-upstream reproduction" that was treated as independent
confirmation was not independent on this axis: its `build_state()` was
hand-written from the same prose docs and used the same global
`pose.p`. So it reproduced the bug rather than detecting it, and its
2/20=10% agreeing with our 0/28 confirmed a *shared* defect, not
correctness. **Treat "our pipeline agrees with my from-scratch reimplementation"
as evidence only for the parts the two implementations do differently.**
When a checkpoint ships `norm_stats`, comparing the actual observation values
against q01/q99 is a cheap, decisive check for exactly this class of bug —
do it first for any new embodiment, before any behavioral debugging.

## Gripper *state* convention also looks inverted (same state vector, found alongside the frame bug)

`norm_stats` for the state's gripper slot: mean **0.709**, q01 0.052, q99
1.010. A gripper cannot be *closed* 71% of the time across a manipulation
dataset; *open* 71% of the time is entirely normal. Bridge/Octo document the
matching action channel as "range [0,1]; 1 = open". So the state slot is
**openness**.

We feed ManiSkill2's `get_gripper_closedness()`, which its source defines as
`(upper - qpos) / (upper - lower)` → **0 = open, 1 = closed**. Inverted.

Corroborating behavioral evidence, measured over real recorded episodes
(gripper channel actually sent to the env): R1 commands "open" on **94%** of
steps and "close" on 6% — implausible for a pick-and-place task, and exactly
what you would expect from a policy that is being told its gripper is in the
opposite state from reality. Fix: feed `1.0 - closedness`.

Note this is a *different* thing from the action-side gripper range rescale
already in `predict_chunk()` — that one is about the commanded value's range,
this one is about the observed value's polarity.

**Also worth testing but NOT the main issue:** SimplerEnv's own octo wrapper
binarizes the *commanded* gripper for `widowx_bridge`
(`2.0 * (open_gripper > 0.5) - 1.0`) while we pass a continuous `2x-1`.
Measured over real episodes, the fraction of commands landing in the
indecisive middle band is R0 97%, R1 0%, R2 7% — so binarization would
matter a lot for R0 and almost nothing for R1/R2. It is not the universal
explanation; the frame bug is the one that hits all three stages equally.

## Still open

- **R0/R1 rerun with the gripper fix completed (2026-08-05, 28/28 each) —
  result is honest and mixed, not a clean win like R2.** R0: 0/28 SR, and
  all 28 episodes labeled `unclear` — consistent with the *already
  re-checked* freezing symptom below, i.e. the gripper fix did NOT resolve
  R0's freezing. R1: 0/28 raw SR too, but a categorically different and
  healthier pattern — `target_grounding_error`×7 + `relation_binding_error`
  ×16, meaning real contact and real (if unsuccessful) stacking attempts
  are happening, unlike R0. So the fix clearly helped R1's *behavior*
  without (yet) producing a completed stack in this sample — plausibly a
  smaller sample-size/precision issue rather than a remaining bug, but not
  confirmed either way. Don't conflate this with R2's real 6/28 successes;
  R0/R1 have not reproduced that.
- SAPIEN-rendered visual domain gap vs. the real camera frames GreenVLA was
  trained on is a risk the user explicitly accepted at project start — if
  SR plateaus well below GreenVLA's own reported numbers even after the
  gripper fix, this is the more likely remaining explanation, not a
  further code bug.
- **R0's freezing symptom — re-checked with the gripper fix in place,
  STILL PRESENT** (see point above: 28/28 `unclear` post-fix). The gripper
  controller theory (half-executing every close command causing apparent
  "freezing") is therefore not the (sole) explanation either — R0 remains
  the weakest of the three stages, consistent with its embodiment-check
  finding above (never WidowX-specifically tuned). Not investigated
  further this session.
