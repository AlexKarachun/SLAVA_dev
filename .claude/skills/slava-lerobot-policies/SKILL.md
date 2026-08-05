---
name: slava-lerobot-policies
description: pi0/pi0.5/SmolVLA model-server specifics for SLAVA rollouts (shared lerobot_server.py) — API, cuDNN crash fix, camera-swap bug, open items. Read slava-model-rollouts first for shared architecture.
---

# pi0 / pi0.5 / SmolVLA — model-server notes

Split out of `slava-model-rollouts` 2026-08-05 (that skill now holds only
cross-model architecture; read it first). All three of these models share
one file, `scripts/model_servers/lerobot_server.py`, and one conda env,
`slava-lerobot` (`huggingface/lerobot`, real upstream, `pip install -e
"<repo>[smolvla]"` — covers pi0/pi0.5 too, same package) — everything below
applies to all three unless noted otherwise.

## Architecture reference: SmolVLA (from the official paper/repo, added 2026-08-05)

Added so future debugging can reason from *why* a convention exists, not
just pattern-match prior bugs. Sourced from Shukor/Aubakirova/Capuano et al.,
*"SmolVLA: A Vision-Language-Action Model for Affordable and Efficient
Robotics"* (arXiv:2506.01844), cross-checked against
`src/lerobot/policies/smolvla/{configuration,modeling}_smolvla.py` directly
(pi0/π0.5's own architecture reference is the next section down).

**Backbone: SmolVLM2, truncated.** Vision-language backbone is
`HuggingFaceTB/SmolVLM2-500M-Video-Instruct` (SigLIP vision encoder +
SmolLM2 language decoder) — but SmolVLA only runs the **first 16 of
SmolLM2's layers** (`num_vlm_layers: 16`, paper §3.1: "rather than using the
last layer features, our action expert has access to all features up to a
specified layer N... N=L/2 offers a good tradeoff"), halving VLM compute
per inference step since deeper layers are never even computed. Total
system: **450M params, ~100M of which is the action expert** — i.e. the
"backbone" contribution is smaller than the nominal 500M checkpoint size
because of this truncation.

**Action expert: a separate, narrower transformer with interleaved
cross/self-attention** — not a head bolted onto the VLM's final hidden
state. It runs at `0.75×` the VLM's hidden width
(`expert_width_multiplier: 0.75`) and alternates cross-attention blocks
(attending the VLM's — layer≤16 — features) with causal self-attention
blocks every 2 layers (`attention_mode: "cross_attn"`,
`self_attn_every_n_layers: 2`). Action generation is **flow matching**
(same family as pi0's action expert below, not autoregressive/tokenized
like OpenVLA or pi0-FAST): noise is added to real action sequences during
training, and the expert learns to predict the correction vector back to
the true trajectory.

**Two more efficiency tricks with direct pipeline consequences:**
- **Visual token reduction**: each camera frame is compressed to a fixed
  **64 tokens** via pixel-shuffle before it reaches cross-attention — this
  bounds the KV sequence length independent of camera count.
- **Async inference**: a `RobotClient` (drains a queued action chunk in the
  control loop) and `PolicyServer` (computes the next chunk off the
  critical path) run separately, with an "early trigger" once the queue
  drops below a threshold and a "chunk fusion" merge rule for overlapping
  chunks — claimed ~30% faster task completion, ~2x throughput vs.
  synchronous execution (paper §3.3, HF blog).

**Images**: resized to **512×512 with padding** (`resize_imgs_with_padding:
(512, 512)` — note the released checkpoint's *stored* feature shape is
smaller, `[3,256,256]`; the upscale happens in preprocessing, not at rest),
then rescaled `[0,1] → [-1,1]` for SigLIP. State: MEAN_STD normalized,
padded to `max_state_dim`.

**The `camera1`/`camera2`/`camera3` question — researched twice, second
pass is the more authoritative one.** First pass quoted the paper's §3.2
("prioritizing top, wrist, and side perspectives... renamed them as
`OBS_IMAGE_1/2/3`") as if directly read from the full text. A **second,
independent research pass** (full repo clone + live HF Hub `config.json`
checks + GitHub API, not just doc/paper reading) could only find that exact
sentence *quoted secondhand inside a GitHub issue* — it explicitly could
not verify it against the arXiv full text itself and flagged this rather
than asserting it. Treat the "documented priority order" claim as
**unverified pending a direct primary-source re-check**, not established
fact.

**What IS directly, conclusively confirmed (live checkpoint comparison,
not a doc reading):** the wrist camera lands in a **different numbered
slot across different released `smolvla_*` checkpoints** —
`smolvla_vlabench` maps wrist→`camera3`, `smolvla_robocasa` and
`smolvla_robocerebra` both map wrist→`camera2` (confirmed via each
checkpoint's actual `--rename_map` in `docs/source/{vlabench,robocasa,
robocerebra}.mdx`). This is definitive: **there is no canonical semantic
for `camera1`/`camera2`/`camera3`** — which slot gets which physical camera
is purely an artifact of whatever `--rename_map` a specific checkpoint's
fine-tuning happened to use, checkpoint by checkpoint. A closed maintainer
issue (`huggingface/lerobot#2262`, closed by NikodemBartnik) confirms this
directly: *"camera1/2/3 mismatch... is now handled with `--rename_map`..."*
— i.e. the mismatch is expected/mechanical, not a semantic contract to
honor. `#1763` (open, no maintainer reply) is a user independently reaching
the same "no semantic distinction preserved at runtime" conclusion by
reading `prepare_images`/`embed_prefix` directly — worth noting there's
**no learned per-camera identity/positional embedding** distinguishing
slot 1 from slot 2 from slot 3 either (confirmed from `embed_prefix`'s
source: image embeddings are just concatenated in list order, no per-slot
tag) unless `add_image_special_tokens=True` (defaults `False`).

**Also worth knowing**: pi0's own "semantic" `base_0_rgb`/`left_wrist_0_rgb`
naming (used elsewhere in this file) is **not universal either** — it's
specific to checkpoints ported directly from Physical Intelligence's own
openpi pretraining (`lerobot/pi0_base`, `pi0fast-base`). Once a checkpoint
is benchmark-fine-tuned, lerobot drops that convention: `pi0_libero_base`
uses LIBERO's own env-native `image`/`image2` keys, and the legacy
`pi0_old` checkpoint uses the exact same generic `camera0/1/2` style as
SmolVLA. So "pi0 has semantic names, SmolVLA doesn't" is an oversimplification
— SmolVLA's arbitrariness is closer to the norm across the repo; pi0's
semantic names are the exception tied to one specific upstream lineage.
**Actionable guidance either way**: keep camera order consistent between
fine-tuning and inference (order is what a specific checkpoint actually
learned on, not name) — check that checkpoint's own `config.json` and any
`--rename_map` example in its docs page, don't assume a slot name
transfers across checkpoints, even within the same model family.

**Missing-camera handling — confirmed genuine `empty_cameras` mechanism,
shared with pi0/pi0.5 (see below).** For any of the config's declared
image slots absent from the batch (up to `empty_cameras` count), the
policy pads a **zero image AND zeroes the attention mask** — a real,
working "this camera doesn't exist, ignore it" signal, not a duplicated
real frame. This is the same mechanism `_BASE_WRIST_CAMERA_NAME_MAP`'s
`continue` (omit) fallback in `lerobot_server.py` relies on for pi0_base/
pi05_base's wrist slots and, incidentally, for SmolVLA's own overflow slots
too (see "Still open" below — confirms that fix is correct for SmolVLA by
the same mechanism, not by analogy alone).

## Architecture reference: pi0 / pi0.5 (from the official papers/repos, added 2026-08-05)

Sourced from Black et al., *"π0: A Vision-Language-Action Flow Model for
General Robot Control"* (arXiv:2410.24164), Physical Intelligence et al.,
*"π0.5: a Vision-Language-Action Model with Open-World Generalization"*
(arXiv:2504.16054), and Driess et al., *"Knowledge Insulating VLA Models"*
(arXiv:2505.23705, a separate follow-up paper — don't conflate it with
π0.5's own paper), cross-checked against `lerobot/policies/pi0/
modeling_pi0.py`, `pi05/modeling_pi05.py`, `policies/common/flow_matching.py`,
and openpi's `droid_policy.py`/`libero_policy.py` directly.

**Backbone: PaliGemma (SigLIP-So400m + Gemma-2B, ~3B total).** The SigLIP
vision tower's stem is an ordinary `conv2d` patchifier — almost certainly
the layer behind the cuDNN "no engine" crash already documented below (it's
plain ViT patchification, not an exotic flow-matching op), which narrows
where to look for *analogous* crashes: other generic conv/attention kernels
on old hardware, not "something about flow matching."

**The action expert is a second, separate ~300M-param transformer — NOT
OpenVLA's single-backbone design.** Quoting the π0 paper directly: *"using
a separate set of weights for the robotics-specific (action and state)
tokens led to an improvement... analogous to a mixture of experts with two
mixture elements."* Mechanically: image+language ("prefix") and
state+action ("suffix") tokens are concatenated into **one sequence**,
processed by **one joint self-attention per layer**, but each token is
transformed by *its own expert's* weights (PaliGemma's for prefix,
action-expert's for suffix). A block attention mask enforces: prefix
attends only to prefix (bidirectional); suffix attends to all of prefix +
itself (bidirectional); **prefix cannot see into the suffix at all**. This
is architecturally distinct from OpenVLA (single backbone, actions as
discretized vocabulary tokens generated autoregressively by that same
backbone) — contrast this with the OpenVLA-OFT skill's architecture section
if reasoning about why a bug looks different on this model family.

**Flow matching, mechanically** (not just "diffusion-like" — the actual
math): trains a velocity field `v_θ(x_t,t)` transporting Gaussian noise to
the true action chunk along a straight line:
```
x_t = t·noise + (1−t)·actions   # t: 1→0
u_t = noise − actions            # training target
loss = MSE(v_θ(x_t, o_t), u_t)
```
At inference: **forward-Euler integration from t=1 (noise) to t=0 (clean
actions) in 10 fixed steps** (`num_inference_steps=10`, both paper and
lerobot default) — an order of magnitude fewer steps than typical image
diffusion because the straight-line path is easier to integrate.
**Critically: only the ~300M action expert re-runs at each of the 10
steps** — the expensive ~3B VLM forward pass over images+language happens
**once**, its KV cache reused for all 10 steps (`past_key_values` passed
into `denoise_step` unchanged). This is the actual mechanical reason this
architecture can run flow matching in real time despite carrying a 3B
backbone — not a detail to skip when explaining why this differs from
OpenVLA-OFT's parallel-decoding approach to the same "make it fast" problem.

**What changed in π0.5**: state stops being a continuous embedding
(`state_proj` linear layer) and becomes **discretized into 256 bins and
spliced into the language prompt as literal text** (`"Task: {instr}, State:
{s1 s2 ...};\nAction: "` — the VLM reads joint state as digits next to the
instruction, not as its own embedding token); time-conditioning moves to
AdaRMS (adaptive RMSNorm) inside the action expert only; tokenizer budget
grows 48→200 tokens for the extra state text. But the bigger π0.5 story is
training recipe, not architecture: co-training on web multimodal
data/verbal coaching/subtask labels/cross-embodiment data alongside ~400h
of real mobile-manipulation demos across 100+ homes, plus **"knowledge
insulation"** (a *separate*, later paper, arXiv:2505.23705) —
stop-gradienting the action expert from the VLM backbone so action-space
training doesn't corrupt the pretrained semantic representations, cutting
training compute ~7.5x while improving generalization.

**Inference pipeline, the parts that matter for debugging:**
1. Images resized (aspect-preserving, padded) to **224×224 square**
   (enforced at construction — "PaliGemma expects square resolution"),
   rescaled `[0,1]→[-1,1]` for SigLIP — same convention as SmolVLA above.
2. **`empty_cameras` masking — confirmed identical mechanism to SmolVLA's**
   (shared code: `for _ in range(missing): img=-1-filled, mask=0`). The
   zero mask actually matters more than the -1 fill value: it sets
   `pad_mask=0`, which excludes those tokens from the attention mask
   entirely — masked image tokens are structurally invisible, not just
   visually blank. openpi's own `droid_policy.py` shows the same pattern
   from the *source* side: `image_masks=(True,True,False)` for DROID's 2
   real cameras against 3 declared slots.
   **Why the camera-swap bug class recurs here specifically**: a swapped
   camera→slot mapping doesn't crash and doesn't NaN — inference "succeeds"
   while looking at the wrong physical camera. Any time cameras get
   renamed/reordered (new env, new dataset, new robot), that's the seam —
   grep the `--rename_map`/declared `image_features` order, don't assume
   the runtime camera list matches by name.
3. State/action are zero-padded to fixed maxima (`max_state_dim=32`,
   `max_action_dim=32`) regardless of your robot's real DOF, truncated back
   down on output. A DOF mismatch or off-by-one in the real
   `output_features[ACTION].shape[0]` fails **silently** (garbage-padded
   output, not an exception) — worth checking explicitly if an output looks
   truncated/off rather than assuming a shape error would have crashed.

   **CONFIRMED HIT, not just a theoretical warning (found 2026-08-05,
   immediately after writing the paragraph above from architecture
   research): `lerobot/pi0_base` and `lerobot/pi05_base` are cross-
   embodiment BASE checkpoints, never fine-tuned to any specific robot —
   their own `config.json` genuinely declares `output_features["action"]
   .shape == (32,)` (confirmed via direct `PreTrainedConfig.from_pretrained
   (...).output_features` query, not guessed). Unlike `pi0_libero_
   finetuned` (real fine-tune, real declared 7/8-dim output),
   `predict_action()`'s postprocessor has no way to know this specific
   checkpoint's output should be truncated to WidowX/bridge's real 7-dim
   action space — it correctly truncates to whatever the checkpoint SAYS
   its output is, which for a base checkpoint is the full 32-dim padded
   space. This is NOT a silent garbage-output failure as the paragraph
   above predicted for the general case — it's a loud one here, because
   SimplerEnv/ManiSkill2's own controller asserts `action.shape ==
   (action_dim,)` and crashes with `AssertionError: ((32,), 7)` on every
   single `/step` call. Fixed in `lerobot_server.py::predict()`: if
   `not is_libero and action.shape[0] != 7: action = action[:7]` — matches
   the `pad_vector()` convention (real values first, zeros appended after)
   and the exact same truncation GreenVLA's own `BridgeOutputsTransform`
   does (`actions[:, :7]`) for this identical embodiment.**
4. The action queue: `select_action()` only calls `predict_action_chunk()`
   (the actual flow-matching sampling loop) when its internal
   `deque(maxlen=n_action_steps)` is empty, then executes the *whole*
   chunk open-loop before the next real observation is read at all —
   `n_action_steps` defaults to 50 (=chunk_size) but is commonly set lower
   (π0.5's own LIBERO recipe uses 10). This is exactly why missing
   physics-settle time *before* the observation that refills the queue
   matters so much: whatever's in that one observation governs every
   action in the next `n_action_steps`-long open-loop run, no mid-chunk
   correction possible.
5. **Rotation/gripper convention is dataset-defined, not architecture-
   defined — and that fact is itself the important takeaway.** openpi's own
   example configs differ: DROID uses absolute joint positions (8-dim,
   no cartesian pose, no rotation representation at all); LIBERO uses
   robosuite `OSC_POSE`-style Δposition+Δorientation+gripper. The π0 paper
   itself describes state/action generically as raw configuration-space
   vectors, zero-padded to the widest embodiment in the mix, with **no
   universal end-effector rotation convention documented at the model
   level, anywhere**. There is no architectural guardrail against a
   mismatched rotation representation, gripper polarity, or action range
   between your environment and a checkpoint's training data — this is a
   silent, non-crashing bug class by construction (see GreenVLA's rotation
   bug for exactly this failure mode on a different model). The only fix is
   "go read what convention THAT SPECIFIC checkpoint's fine-tuning dataset
   used" — never inferable from the model code itself.

**Code — the actual Euler loop** (`policies/common/flow_matching.py`,
shared by pi0/pi05/smolvla):
```python
dt = -1.0 / num_steps
x_t = noise                      # t=1, pure Gaussian noise
for step in range(num_steps):
    time = 1.0 + step * dt
    v_t = denoise_fn(x_t, time)  # ONE action-expert pass, reuses cached VLM prefix K/V
    x_t = x_t + dt * v_t
# x_t is now the denoised action chunk, t=0
```
**The queue** (`modeling_pi0.py`, exact source):
```python
def reset(self):
    self._action_queue = deque(maxlen=self.config.n_action_steps)

@torch.no_grad()
def select_action(self, batch):
    if len(self._action_queue) == 0:
        actions = self.predict_action_chunk(batch)[:, : self.config.n_action_steps]
        self._action_queue.extend(actions.transpose(0, 1))
    return self._action_queue.popleft()
```
`policy.reset()` must be called on env reset — easy to forget in a custom
eval loop, and forgetting it means the queue from the *previous* episode
gets drained into the new one.

## Confirmed real API (read directly from `huggingface/lerobot`, not guessed)

Originally planned to import lerobot's own `LiberoEnv` gym class
(`src/lerobot/envs/libero.py`) for the LIBERO side. **Reading that file
showed it's a thin gymnasium wrapper around the exact same
`libero.libero.envs.OffScreenRenderEnv` our own `env_worker_libero.py`
already drives** (same `camera_names=["agentview_image",
"robot0_eye_in_hand_image"]`, same underlying robosuite env) — there is no
separate "lerobot LIBERO physics" to integrate. **One shared env-worker per
environment, used by every model that runs there:** `env_worker_libero.py`
(port 8701 default) serves OpenVLA-OFT and all three lerobot models on
LIBERO alike; `env_worker_simpler.py` (port 8702 default) serves GreenVLA
and all three lerobot models on SimplerEnv/bridge alike. Each model-server
adapts the env-worker's raw obs dict to whatever its own checkpoint expects
— the env side never needs to know which model is consuming it.

```python
from lerobot.configs.policies import PreTrainedConfig      # NOT lerobot.common.*
from lerobot.policies.factory import get_policy_class, make_pre_post_processors  # NOT lerobot.common.*
from lerobot.common.control_utils import predict_action    # this one IS under .common

policy_cfg = PreTrainedConfig.from_pretrained(checkpoint)
policy = get_policy_class(policy_cfg.type).from_pretrained(checkpoint)
preprocessor, postprocessor = make_pre_post_processors(policy_cfg, pretrained_path=checkpoint)
action = predict_action(observation, policy, device, preprocessor, postprocessor, use_amp=False, task=instruction)
```

`policy_cfg.input_features` (dict of name -> `PolicyFeature`, `.type` is a
`FeatureType` **enum** whose `.value` is the UPPERCASE string
`"VISUAL"`/`"STATE"` — compare against the enum members directly, not a
lowercased string; comparing `.value == "visual"` silently matches nothing,
a real bug caught here) tells you exactly which raw observation keys and
state dimensionality *this specific checkpoint* expects —
`lerobot_server.py` reads this at startup instead of hardcoding key names,
because LIBERO-finetuned and bridge-zero-shot checkpoints do **not**
necessarily share the same key names/dims.

**Action chunking needs no manual replay queue here**, unlike OpenVLA-OFT
(see `slava-openvla-oft`): confirmed by reading
`lerobot.policies.pi0.modeling_pi0.PI0Policy.select_action()` (and
SmolVLA's equivalent) — they already maintain their own internal
`_action_queue` (a `deque`), only running a real forward pass when it's
empty and popping one action per call otherwise. Calling `predict_action()`
once per env step already gets correct open-loop chunk replay for free, as
long as the same `self.policy` instance persists across steps (it does).

## Real bugs found getting the backend to actually run

1. **`FeatureType` comparison bug** (see above) — `image_features` came
   back empty for every checkpoint until fixed.
2. **`lerobot/pi0_libero_finetuned` (and pi0.5/SmolVLA's LIBERO checkpoints)
   declare 3 image input features, not 2:** `observation.images.image`,
   `observation.images.image2`, and `observation.images.empty_camera_0`
   (224×224, smaller than the two real 256×256 camera slots) — a
   placeholder the checkpoint always saw as a zero image during training.
   `lerobot_server.py` feeds `np.zeros(...)` for any feature name containing
   `"empty_camera"` rather than duplicating a real frame into it (a real
   frame there would be out-of-distribution input the model never saw at
   that slot during training).
3. **`compile_model=True` on `lerobot/pi0_libero_finetuned` crashes on a
   V100:** passing `compile_model=False` as a kwarg to `PreTrainedConfig.
   from_pretrained()` does **nothing** — it silently falls into
   `**policy_kwargs`, which that method only forwards as draccus
   `cli_overrides` (CLI-style strings), not arbitrary field overrides. Real
   fix: load the config, mutate `policy_cfg.compile_model = False` directly
   (guarded by `hasattr`), then call `policy_cls.from_pretrained(checkpoint,
   config=policy_cfg)` — the explicit `config=` kwarg is required, otherwise
   `from_pretrained` reloads its own fresh (un-mutated) config internally
   and the override is lost. Leaving `compile_model=True` makes
   `torch.compile(mode="max-autotune")` JIT-compile via Triton/Inductor on
   first call — on a V100 (Volta) + this torch/Triton combination that fails
   outright (`RuntimeError: PassManager::run failed`, an MLIR pass crash),
   not just slow.

## cuDNN "no engine" crash on SigLIP conv2d (V100) — pi0/pi0.5 only

pi0 and pi0.5 (both PaliGemma/SigLIP-based; SmolVLA has a different vision
backbone and is unaffected) hit `RuntimeError: GET was unable to find an
engine to execute this computation` on every `/predict_chunk` call, traced
(via direct reproduction against a live env-worker, not guessed) to
SigLIP's patch-embedding `Conv2d` inside `paligemma.model.vision_tower` — a
cuDNN "no kernel found for this op/dtype/shape on this hardware" error, not
a memory or shape bug. **First attempted fix (didn't work): overriding
`policy_cfg.dtype = "float32"`** (same mutate-then-`from_pretrained(...,
config=policy_cfg)` pattern as `compile_model` above) — pi0.5's config
defaults to `dtype="bfloat16"`, pi0's already defaults to `"float32"`, yet
**both** kept crashing identically even after the override visibly took
effect. **Actual fix:** `torch.backends.cudnn.enabled = False` at module
import time in `lerobot_server.py`, before any model loads — forces
PyTorch's native (non-cuDNN) conv2d fallback for the whole process. Blunter
than pinning dtype, but the one that actually resolved it. Only affects this
process; env-workers and other model-servers are separate
processes/conda envs, untouched.

## LIBERO proprioception layout

Needed the same `eef_pos(3)+axis_angle(3)+gripper_qpos(2)` conversion as
OpenVLA-OFT, not env-worker's raw 9-dim `[gripper_qpos(2), eef_pos(3),
eef_quat(4)]` layout — lerobot's own docs (`docs/source/libero.mdx`,
"Policy inputs and outputs") state `observation.state` is exactly this
8-dim layout. The previous code just zero-padded/truncated the raw 9-dim
array blindly (`proprio[:8]`) — garbage input (wrong order, truncated
un-renormalized quaternion), not an approximation. Fixed with the same
`scipy.spatial.transform.Rotation` axis-angle conversion
`openvla_oft_server.py` uses.

## `num_steps_wait=10` — needed here too, not just OpenVLA-OFT

`huggingface/lerobot`'s own `LiberoEnv.__init__` independently defaults to
`num_steps_wait: int = 10` — not something borrowed from OpenVLA-OFT,
confirmed by reading their source directly. Spotted after pi0/pi0.5/SmolVLA
got stuck on `no_action_or_timeout` on a scene OpenVLA-OFT (which already
had the settle-step fix) succeeded on repeatedly. Added to
`LIBERO_NUM_STEPS_WAIT` in `run_rollouts.py` for all three.

## RESOLVED: agentview/wrist cameras were swapped on LIBERO

**The actual root cause of the near-0% SR / "first_contact_object always
None" pattern on LIBERO — not image orientation, not gripper range, a
camera-assignment bug.** Orientation was directly A/B-tested (see the
dead `if False:` block still in `lerobot_server.py`, kept with a note —
rendering the "undo env-worker's flip" version showed a genuinely
upside-down/disoriented image and did NOT change the SR, ruling out flip
direction as the cause) — but the actual bug was one level up from
orientation: *which camera feed* was going into *which named slot*.

Traced by reading lerobot's own reference `LiberoEnv`
(`src/lerobot/envs/libero.py:158-159`, `camera_name_mapping`):
`"agentview_image": "image"`, `"robot0_eye_in_hand_image": "image2"` — i.e.
the feature named `"image"` is the MAIN/agentview view and `"image2"` is
the WRIST view. Confirmed via `PreTrainedConfig.from_pretrained(...)
.input_features` that all three LIBERO-finetuned checkpoints
(`lerobot/pi0_libero_finetuned`, `lerobot/pi05_libero_finetuned`,
`HuggingFaceVLA/smolvla_libero`) declare exactly these two names — generic,
containing no `"wrist"` substring. `lerobot_server.py`'s `_wrist_first`
helper sorts by that substring, so for these checkpoints it was a silent
no-op, and the code fell through to positional assignment
(`image_feature_names[0] <- real_cameras[0]`, where
`real_cameras = [wrist, agentview]`) — feeding the wrist closeup into the
`"image"` slot the model was trained to treat as the main scene, and the
actual scene into `"image2"`, the slot it was trained to treat as a wrist
closeup. **Fully backwards, for every pi0/pi0.5/SmolVLA LIBERO episode ever
collected before this fix (2026-08-05).**

Fixed via an explicit `_LIBERO_CAMERA_NAME_MAP` in `lerobot_server.py` that
overrides the generic heuristic for exactly these two feature names
(mirroring lerobot's own mapping, not a new guess). All pre-fix pi0/pi0.5/
SmolVLA LIBERO episodes were purged from `rollout_annotations.jsonl`
(backed up to `.bak_before_lerobot_camera_swap_fix`, episode dirs archived
to `rollouts/episodes_archived_lerobot_pre_camera_swap_fix/`) so a rerun
collects fresh data under the same run_ids rather than being skipped by
`load_completed_run_ids()`. `generate_rollout_report.py`'s
`annotate_provenance()` also independently catches this class of issue (by
comparing each episode's first-frame mtime to the server file's mtime) as
a defense-in-depth check for whenever the *next* server fix lands.

## Still open / not yet investigated

- **NEW, unexplained (found 2026-08-05 once the camera-swap fix's full
  LIBERO rerun completed, 127/127 each): pi0 and pi0.5 diverge sharply on
  LIBERO despite sharing an architecture family.** Post-fix,
  `failure_type_auto` shows pi0.5 doing real, if imperfect, grounding
  (`target_grounding_error`×25 + `relation_binding_error`×43 out of 99 —
  i.e. contact is happening, targeting is just off) — the camera fix
  clearly worked. **pi0 instead shows `no_action_or_timeout` on 90/99** —
  it's barely acting at all, a categorically different failure mode from
  pi0.5's. This is NOT the camera-swap bug (both got the identical fix,
  same rerun, same code) — something else is different about `pi0` vs
  `pi05` specifically (different checkpoint, evidently not just a scaled
  variant of the same behavior). Not investigated further this session —
  candidate next steps: compare the two checkpoints' actual output action
  magnitudes/action-head architecture (pi0 uses a different flow-matching
  config than pi0.5 per their respective `configuration_pi0.py`/
  `configuration_pi05.py` defaults — worth diffing), or reproduce a single
  `no_action_or_timeout` pi0 episode directly against the live model-server
  to inspect its raw predicted actions before blaming the harness again.
- **RESOLVED 2026-08-05: pi0_base/pi05_base's `base_0_rgb`/`left_wrist_0_rgb`/
  `right_wrist_0_rgb` camera assignment on SimplerEnv.** WidowX/bridge has
  no real wrist camera at all (`env_worker_simpler.py` never sets
  `wrist_rgb`) — with `_wrist_first` alone, the single real camera got
  positionally consumed by `left_wrist_0_rgb` (sorted first for containing
  "wrist"), leaving `base_0_rgb` — the slot that should get it — empty, and
  `right_wrist_0_rgb` picking up a duplicated real frame via the overflow
  fallback. Confirmed via openpi's own reference input adapters
  (`physical-intelligence/openpi`, `src/openpi/policies/{droid,aloha}
  _policy.py`, read directly): `base_0_rgb` is always the exterior camera,
  `left_wrist_0_rgb`/`right_wrist_0_rgb` are wrist cameras, and a genuinely
  missing camera is **omitted from the observation entirely** (not
  duplicated) — the policy's own `_preprocess_images()`
  (`lerobot/policies/pi0/modeling_pi0.py`) auto-detects any declared image
  feature absent from the batch and masks it (-1 padding, `mask=False`)
  itself, no manual masking needed on our side. Fixed via an explicit
  `_BASE_WRIST_CAMERA_NAME_MAP` (same pattern as `_LIBERO_CAMERA_NAME_MAP`)
  plus changing the generic overflow fallback from "duplicate the last real
  frame" to "omit the key" — the latter also fixes any *other* checkpoint
  with more declared camera slots than real cameras, not just this one.
  **Confirmed still-stale in the current dataset, not yet validated on a
  live rerun:** the fix was applied to `lerobot_server.py` while pi0/pi0.5's
  full rerun (launched for the LIBERO camera-swap fix) was already running
  in memory — that rerun's 28-episode SimplerEnv portion for each model
  finished under the OLD (pre-`_BASE_WRIST_CAMERA_NAME_MAP`) code, same
  "process doesn't hot-reload on file edit" gotcha as everywhere else in
  this project. `generate_rollout_report.py`'s `annotate_provenance()` will
  correctly flag these 56 episodes as stale (their frame mtimes predate
  this fix) and exclude them from metrics — but they still need an actual
  rerun to get real numbers, not just an exclusion.
- **CHECKED, then re-checked more deeply 2026-08-05: SmolVLA's `camera1/
  camera2/camera3` has a documented-but-unenforced convention** — see the
  "Architecture reference" section above for the full finding (paper §3.2's
  top>wrist>side curation-time priority mapping, confirmed not enforced at
  runtime, confirmed as a live unresolved community ambiguity via
  `huggingface/lerobot#1763`/`#2753`). **Not a separate open bug for us
  though**: the generic overflow-fallback fix (duplicate → omit) already
  applies here too — with only 1 real camera and no wrist-detection
  heuristic match (none of camera1/2/3 contain "wrist"), `camera1` gets the
  real frame positionally and `camera2`/`camera3` are correctly omitted
  (auto-masked, confirmed as the real `empty_cameras` mechanism, not a
  guess), not duplicated. Confirmed all 8 SmolVLA SimplerEnv episodes
  collected so far have frame mtimes after this fix landed — not stale, no
  rerun needed on this account.
- **Whether the zero-shot `*_base` checkpoints are usable on SimplerEnv at
  all** — SAPIEN-rendered frames vs. real-camera training data is a genuine
  floor-effect risk the user explicitly accepted; if SR stays near 0% even
  after the camera-assignment issue above is checked, that's the more
  likely explanation, not a remaining code bug.
- **Repeats: n=1** was the user's explicit call (simplicity of comparison
  tables) overriding a suggestion to split by action-head type. Caveat:
  pi0/pi0.5/SmolVLA sample from a flow-matching/diffusion action head, so
  their SR at n=1 may have more variance than OpenVLA-OFT/GreenVLA's more
  deterministic decoding — flag this if Δlang results for these three
  models look noisy relative to their sample size.
