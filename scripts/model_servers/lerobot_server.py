"""Shared model-server for every lerobot-native policy we run: pi0, pi0.5,
SmolVLA — on both LIBERO and SimplerEnv/bridge (see
.claude/skills/slava-model-rollouts/SKILL.md, "Model registry"). Runs inside
`slava-lerobot` (huggingface/lerobot, `pip install -e ".[libero]"`).

Design: rather than hardcoding each checkpoint's expected observation key
names (they differ: LIBERO-finetuned checkpoints use different image/state
keys than the bridge zero-shot `*_base` checkpoints), this reads
`policy_cfg.input_features` at startup and builds the raw observation dict
to match whatever that specific checkpoint actually declares. This is the
standard lerobot inference recipe (`lerobot.common.control_utils.
predict_action` + `lerobot.policies.factory.make_pre_post_processors`) — not
a bespoke pipeline.

Action chunking: unlike OpenVLA-OFT (see openvla_oft_server.py), no manual
open-loop replay queue is needed here — confirmed 2026-08-05 by reading
`lerobot.policies.pi0.modeling_pi0.PI0Policy.select_action()` (and smolvla's
equivalent): they already maintain their own internal `_action_queue`
(a `deque`), only running a real forward pass when it's empty and popping one
action per call otherwise. Calling `predict_action()` (which calls
`policy.select_action()`) once per env step already gets correct open-loop
chunk replay for free, as long as the same `self.policy` instance persists
across steps (it does — one `LerobotBackend` per model-server process
lifetime).
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from scipy.spatial.transform import Rotation

# Found 2026-08-05 debugging pi0/pi0.5 on this V100: SigLIP's patch-embedding
# Conv2d crashes with `RuntimeError: GET was unable to find an engine to
# execute this computation` — a cuDNN "no kernel for this op/dtype/shape
# combination" error. The `dtype="float32"` config override below (mirroring
# the existing compile_model override) did NOT fix it despite the class
# default already being float32 and the override visibly taking effect —
# something in cuDNN's algorithm search still can't find an engine for this
# exact SigLIP conv on this GPU/cuDNN/torch combination, dtype aside.
# SmolVLA (different, non-SigLIP vision backbone) is unaffected. Disabling
# cuDNN globally forces PyTorch's native (non-cuDNN) conv2d fallback, which
# sidesteps the whole error class regardless of root cause — a blunter fix
# than pinning dtype, but the one that actually works. Only affects this
# process (env-worker/other model-servers are separate processes/envs).
torch.backends.cudnn.enabled = False

sys.path.insert(0, str(Path(__file__).resolve().parent))
from base_server import base_arg_parser, serve  # noqa: E402


def _wrist_first(items):
    return sorted(items, key=lambda kv: 0 if "wrist" in kv[0].lower() else 1)


# LIBERO-finetuned checkpoints (lerobot/pi0_libero_finetuned, pi05_libero_
# finetuned, HuggingFaceVLA/smolvla_libero — confirmed identical across all
# three via PreTrainedConfig.from_pretrained(...).input_features, 2026-08-05)
# declare generic feature names "observation.images.image"/"...image2", which
# contain no "wrist" substring, so `_wrist_first` was a silent no-op for them
# and the code below fell through to positional (declaration-order)
# assignment: image <- camera_idx 0, image2 <- camera_idx 1. That is backwards.
# lerobot's OWN reference LIBERO env class defines the mapping directly
# (src/lerobot/envs/libero.py, camera_name_mapping): "agentview_image": "image",
# "robot0_eye_in_hand_image": "image2" — i.e. "image" is the MAIN/agentview
# camera and "image2" is the WRIST camera. Our positional assignment had this
# exactly swapped: the wrist closeup was fed into the "image" (main-view) slot
# and the global scene view into "image2" (wrist slot) for every pi0/pi0.5/
# SmolVLA LIBERO episode collected so far. A model reasoning about object
# layout from what it believes is the main scene, while actually looking at a
# wrist closeup, would plausibly never register contact with the right
# object — consistent with the near-0% SR / "first_contact_object always
# None" pattern on libero_object that image-orientation A/B testing (see
# REVERTED block below) did not explain.
_LIBERO_CAMERA_NAME_MAP = {
    "observation.images.image": "agentview",
    "observation.images.image2": "wrist",
}

# openpi's own reference input adapters (physical-intelligence/openpi,
# src/openpi/policies/{droid,aloha}_policy.py — confirmed by reading them
# directly, 2026-08-05) use this exact naming convention across every
# embodiment: "base_0_rgb" is always the exterior/3rd-person camera,
# "left_wrist_0_rgb"/"right_wrist_0_rgb" are wrist cameras (right_wrist only
# for bimanual robots). `lerobot/pi0_base`/`pi05_base` inherit these names.
# `_wrist_first` alone is not enough here: when there's no real wrist camera
# at all (SimplerEnv/WidowX bridge — env_worker_simpler.py never sets
# wrist_rgb), `_wrist_first` still sorts left_wrist_0_rgb ahead of
# base_0_rgb, so the lone real (agentview) camera would be positionally
# consumed by the WRIST slot, leaving base_0_rgb — the slot that should get
# it — empty. Explicit mapping avoids this: base_0_rgb always gets the main
# camera; the wrist slots only get a real frame if a real wrist camera
# exists, otherwise they're omitted (see the `continue` fallback below,
# which relies on lerobot's own `PI0Policy._preprocess_images()` treating
# any declared image feature absent from the batch as "missing" and
# auto-masking it with -1 padding — matching openpi's own missing-camera
# handling, not a guess).
_BASE_WRIST_CAMERA_NAME_MAP = {
    "observation.images.base_0_rgb": "agentview",
    "observation.images.left_wrist_0_rgb": "wrist",
    "observation.images.right_wrist_0_rgb": "wrist",
}


class LerobotBackend:
    def __init__(self, checkpoint: str, device: str):
        from lerobot.policies.factory import (
            get_policy_class,
            make_pre_post_processors,
        )
        from lerobot.configs.policies import PreTrainedConfig
        from lerobot.configs.types import FeatureType

        self.checkpoint = checkpoint
        self.device = torch.device(device)

        policy_cfg = PreTrainedConfig.from_pretrained(checkpoint)
        # compile_model=False override, applied by mutating the loaded config
        # object directly (passing compile_model=False as a kwarg to
        # from_pretrained does NOT work — it silently falls into **policy_kwargs,
        # which PreTrainedConfig.from_pretrained only forwards as draccus
        # `cli_overrides`, not arbitrary field overrides — confirmed the hard
        # way: it had no effect and a real run below hit
        # `RuntimeError: PassManager::run failed` from Triton/torch.compile,
        # which this server's target checkpoints (e.g.
        # lerobot/pi0_libero_finetuned, saved with compile_model=True) trigger
        # on this V100 + this torch/triton combination). We run one episode at
        # a time (n=1 repeats, see SKILL.md), so torch.compile's amortized
        # throughput benefit doesn't pay for its own JIT cost anyway —
        # disabled for correctness-first iteration, not a permanent choice.
        # `config=policy_cfg` below is required so `from_pretrained` uses this
        # mutated object instead of silently reloading a fresh one from the
        # checkpoint (it accepts `config=` explicitly for exactly this reason).
        if hasattr(policy_cfg, "compile_model"):
            policy_cfg.compile_model = False
        # dtype=float32 override (found 2026-08-05 debugging pi0.5): default
        # is "bfloat16" (see lerobot.policies.pi05.modeling_pi05's
        # `precision: Literal["bfloat16","float32"] = "bfloat16"`, read from
        # `config.dtype`). On this V100 (Volta, no bf16 tensor cores) that
        # doesn't just run slow like OpenVLA-OFT's bf16 path — the SigLIP
        # vision tower's patch-embedding Conv2d in bf16 hits a hard
        # `RuntimeError: GET was unable to find an engine to execute this
        # computation` (no cuDNN kernel for bf16 conv2d on pre-Ampere
        # hardware), a real crash, not a slowdown. Forcing float32 (same
        # override pattern as compile_model above — mutate the loaded config,
        # pass `config=` explicitly to from_pretrained) sidesteps this
        # entirely. Same hasattr guard so this is a no-op for any backend
        # without a `dtype` field.
        if hasattr(policy_cfg, "dtype"):
            policy_cfg.dtype = "float32"
        policy_cls = get_policy_class(policy_cfg.type)
        self.policy = policy_cls.from_pretrained(checkpoint, config=policy_cfg)
        self.policy.to(self.device).eval()
        self.display_name = policy_cfg.type

        # device_processor override (found 2026-08-05, debugging a pi0.5-only
        # crash): without it, `RuntimeError: Expected all tensors to be on
        # the same device, but found at least two devices, cuda:0 and cpu!`
        # inside `embed_language_tokens` -> `get_input_embeddings()`. Root
        # cause: pi0.5 builds its language tokens *inside the preprocessor*
        # (state gets discretized and spliced into the text prompt before
        # tokenization — see slava-lerobot-policies' architecture section),
        # unlike pi0, which embeds state as a separate continuous tensor
        # elsewhere. `predict_action()`'s own device move
        # (`prepare_observation_for_inference(..., device)`) happens on the
        # *result* of the preprocessor, so it can't fix tokens that were
        # already created on the wrong device inside the preprocessor
        # itself — the preprocessor's own device has to be set explicitly.
        # Matches the exact override lerobot's own SmolVLA tutorial
        # (`examples/tutorial/smolvla/using_smolvla_example.py`) uses, which
        # we were missing. Harmless for pi0/SmolVLA (whose tokenization
        # doesn't depend on preprocessor device the same way), but confirmed
        # required for pi05.
        self.preprocessor, self.postprocessor = make_pre_post_processors(
            policy_cfg,
            pretrained_path=checkpoint,
            preprocessor_overrides={"device_processor": {"device": str(self.device)}},
        )

        # NOTE: PolicyFeature.type is a FeatureType enum whose .value is the
        # UPPERCASE string ("VISUAL"/"STATE") — compare against the enum
        # members directly, not a lowercased string (caught a real bug here:
        # `ft.type.value == "visual"` silently matched nothing).
        image_features = {
            name: ft for name, ft in (policy_cfg.input_features or {}).items()
            if ft.type is FeatureType.VISUAL
        }
        state_features = {
            name: ft for name, ft in (policy_cfg.input_features or {}).items()
            if ft.type is FeatureType.STATE
        }
        if not image_features:
            raise RuntimeError(f"{checkpoint}: no VISUAL input_features found — cannot map cameras")
        if len(state_features) != 1:
            raise RuntimeError(
                f"{checkpoint}: expected exactly one STATE input feature, got {list(state_features)}"
            )
        self.image_feature_names = [name for name, _ in _wrist_first(image_features.items())]
        # Some checkpoints declare a placeholder camera slot ("empty_camera_N")
        # for architectures trained with a fixed number of camera inputs where
        # this deployment doesn't have that many real cameras — those must get
        # a zero image, not a duplicated real frame (real frame would feed the
        # model out-of-distribution data in a slot it learned to treat as
        # always-blank). Confirmed present on lerobot/pi0_libero_finetuned
        # (2 real cameras + 1 "empty_camera_0").
        self.image_features = image_features
        self.state_feature_name, self.state_feature = next(iter(state_features.items()))

    def reset(self) -> None:
        """Clear the policy's internal action queue between episodes.

        `PreTrainedPolicy.reset()` is lerobot's own per-episode hook and is
        what their evaluation loops call on every `env.reset()`. We were not
        calling it: this server holds ONE policy instance for its whole
        lifetime (see the module docstring — that persistence is deliberate,
        it is what gives correct open-loop chunk replay WITHIN an episode),
        and `select_action()` pops from `_action_queue` and only runs a real
        forward pass when the queue is empty.

        So whatever remained in the queue when an episode ended — typically
        most of a chunk, since episodes stop on success/termination rather
        than on a chunk boundary — was replayed as the first actions of the
        next episode, computed from the previous episode's observation and
        the previous episode's instruction. Episodes are ordered by variant,
        so that contaminated across variants: precisely the axis SLAVA
        measures. Affects pi0/pi0.5/SmolVLA; OpenVLA-OFT is unaffected because
        its chunk queue lives in the orchestrator as a per-episode local.
        """
        self.policy.reset()

    @torch.inference_mode()
    def predict(self, instruction: str, obs: dict, meta: dict) -> list[float]:
        from lerobot.common.control_utils import predict_action

        is_libero = meta.get("environment") == "LIBERO"

        agentview = np.asarray(obs["agentview_rgb"])
        wrist = np.asarray(obs["wrist_rgb"]) if obs.get("wrist_rgb") is not None else None
        if False:  # noqa: SIM108 — see REVERTED note below, kept for reference
            # REVERTED 2026-08-05: this "undo env-worker's flip to recover raw
            # robosuite orientation" theory (derived from reading lerobot's
            # *live eval* LiberoEnv._format_raw_obs(), which doesn't flip) was
            # empirically WRONG. On libero_object (the easiest LIBERO suite —
            # OpenVLA-OFT gets 6/6 on every task there), pi0/pi0.5 with this
            # "fix" produced 0/18 episodes with `first_contact_object=None` —
            # zero contact ever, not just failed grasps. Rendered the actual
            # image the model received (undo env-worker's flip, i.e. this
            # code path) and it's visibly upside-down/disoriented (arm at
            # bottom, floor/objects at top) — not a plausible robot-eye view.
            # Root cause theory: the LIVE env class's raw-passthrough
            # behavior doesn't necessarily match how `lerobot/pi0_libero_
            # finetuned`'s actual TRAINING dataset (`lerobot/libero` /
            # `HuggingFaceVLA/libero`, built by a separate offline HDF5-
            # conversion pipeline, not this live env class) was oriented —
            # never verified that conversion script directly, given time
            # constraints. Reverted to passing through env-worker's existing
            # single-flip (upright, human-legible) orientation unchanged —
            # same convention already saved to the camera PNG dashboard.
            # `.copy()` note kept for whoever revisits this: a bare `[::-1]`
            # is a negative-stride view, `torch.from_numpy()` rejects it.
            agentview = agentview[::-1].copy()
            if wrist is not None:
                wrist = wrist[::-1].copy()

        real_cameras = []
        if wrist is not None:
            real_cameras.append(wrist)
        real_cameras.append(agentview)

        raw_obs: dict[str, np.ndarray] = {}
        camera_idx = 0
        for name in self.image_feature_names:
            if "empty_camera" in name:
                c, h, w = self.image_features[name].shape
                raw_obs[name] = np.zeros((h, w, c), dtype=np.uint8)
                continue
            if name in _LIBERO_CAMERA_NAME_MAP:
                # Explicit LIBERO mapping (see _LIBERO_CAMERA_NAME_MAP above)
                # overrides the generic positional fallback below — it's a
                # known, checked mapping rather than a heuristic.
                want = _LIBERO_CAMERA_NAME_MAP[name]
                raw_obs[name] = wrist if (want == "wrist" and wrist is not None) else agentview
                continue
            if name in _BASE_WRIST_CAMERA_NAME_MAP:
                # Explicit base/wrist mapping (see _BASE_WRIST_CAMERA_NAME_MAP
                # above) — base_0_rgb always gets the main camera; a wrist
                # slot only gets a real frame if a real wrist camera exists,
                # otherwise it's omitted (auto-masked by the policy) rather
                # than positionally stealing the main camera's frame.
                want = _BASE_WRIST_CAMERA_NAME_MAP[name]
                if want == "agentview":
                    raw_obs[name] = agentview
                elif wrist is not None:
                    raw_obs[name] = wrist
                # else: no real wrist camera for this slot — omit it.
                continue
            if camera_idx < len(real_cameras):
                raw_obs[name] = real_cameras[camera_idx]
                camera_idx += 1
            else:
                # More declared (non-placeholder) camera slots than the env
                # has real cameras — e.g. lerobot/pi0_base and pi05_base
                # declare base_0_rgb + left_wrist_0_rgb + right_wrist_0_rgb
                # (a bimanual-robot convention) but SimplerEnv/WidowX bridge
                # has exactly one real camera and no wrist camera at all
                # (env_worker_simpler.py never sets wrist_rgb). Previously
                # this duplicated `real_cameras[-1]` into the extra slot(s)
                # — a real (if lower-priority) bug of the same shape as the
                # camera-swap one above: feeding a real frame into a slot
                # the model was trained to treat as absent. Confirmed via
                # openpi's own reference input adapters (`DroidInputs`/
                # `AlohaInputs` in physical-intelligence/openpi,
                # `src/openpi/policies/{droid,aloha}_policy.py`): missing
                # cameras are left OUT of the observation entirely, zero-
                # filled and explicitly masked (`image_mask=False`) by the
                # model itself, not duplicated. lerobot's own
                # `PI0Policy._preprocess_images()` (`modeling_pi0.py`)
                # implements exactly this: it computes `missing_img_keys =
                # [k for k in self.config.image_features if k not in
                # batch]` and auto-masks those with `-1`-padding — i.e. we
                # don't need to build the mask ourselves, we just need to
                # NOT put a real frame in `raw_obs` for a camera that
                # doesn't exist. Fixed: skip the key entirely rather than
                # populating it.
                continue

        expected_dim = self.state_feature.shape[0]
        if is_libero and expected_dim == 8 and len(obs.get("proprioception", [])) == 9:
            # Proprioception layout fix (found 2026-08-05, same class of bug as
            # OpenVLA-OFT's gripper-postprocessing miss). lerobot's LIBERO docs
            # (docs/source/libero.mdx, "Policy inputs and outputs") state
            # `observation.state` is "8-dim proprioceptive features (eef
            # position, axis-angle orientation, gripper qpos)" — identical
            # layout to what OpenVLA-OFT expects. env_worker_libero.py's raw
            # `proprioception` is 9-dim `[gripper_qpos(2), eef_pos(3),
            # eef_quat(4)]` (quaternion, different field order). The previous
            # code just zero-padded/truncated this blindly to `expected_dim`
            # (`proprio[:8]` = 2 gripper + 3 eef_pos + first 3 of 4 quat
            # components, in the wrong order and with a truncated,
            # renormalized-nowhere quaternion) — garbage input, not a
            # approximation. Fixed with the same axis-angle conversion
            # openvla_oft_server.py already uses.
            proprio_raw = np.asarray(obs["proprioception"], dtype=np.float32)
            gripper_qpos, eef_pos, eef_quat = proprio_raw[:2], proprio_raw[2:5], proprio_raw[5:9]
            axis_angle = Rotation.from_quat(eef_quat).as_rotvec()
            proprio = np.concatenate([eef_pos, axis_angle, gripper_qpos]).astype(np.float32)
        elif obs.get("ee_pose") is not None:
            # SimplerEnv/bridge (WidowX). Same class of bug as the LIBERO
            # branch above, found 2026-08-05: this used to zero-pad the raw
            # 9-dim `proprioception` (joint qpos + gripper closedness) into
            # whatever `expected_dim` the checkpoint declared. Joint qpos is
            # not what a bridge-pretrained policy reads — the pi0 family's
            # bridge convention is end-effector pose plus gripper, the same
            # [x, y, z, roll, pitch, yaw, pad, gripper] layout GreenVLA uses
            # (GreenVLA is a pi0-derived architecture and copied it).
            # `ee_pose` from env_worker_simpler is base-relative (see the long
            # note there — the world-frame version was a major bug), and the
            # gripper slot is openness, not closedness, for the same reason
            # documented in greenvla_server.py.
            #
            # IMPORTANT CAVEAT, do not oversell this fix: `lerobot/pi0_base`
            # and `pi05_base` ship NO normalization stats at all, and
            # `smolvla_base` ships stats only for the SO-100 arm (hence its
            # 6-dim state) — never for WidowX/bridge. So unlike GreenVLA,
            # where the checkpoint's own norm_stats decide the question, there
            # is no ground truth here to verify against; this layout is the
            # best-supported convention, not a confirmed one. Treat these three
            # models' SimplerEnv numbers as weakly specified regardless.
            ee_pose = np.asarray(obs["ee_pose"], dtype=np.float32)
            roll, pitch, yaw = Rotation.from_quat(
                [ee_pose[4], ee_pose[5], ee_pose[6], ee_pose[3]]  # scipy wants xyzw
            ).as_euler("xyz")
            gripper_openness = 1.0 - float(obs.get("gripper_closedness", 0.0))
            bridge_state = np.array(
                [ee_pose[0], ee_pose[1], ee_pose[2], roll, pitch, yaw, 0.0, gripper_openness],
                dtype=np.float32,
            )
            proprio = np.zeros(expected_dim, dtype=np.float32)
            proprio[: min(expected_dim, bridge_state.shape[0])] = bridge_state[:expected_dim]
        else:
            proprio = np.asarray(obs.get("proprioception", []), dtype=np.float32)
            if proprio.shape[0] != expected_dim:
                fixed = np.zeros(expected_dim, dtype=np.float32)
                fixed[: min(expected_dim, proprio.shape[0])] = proprio[:expected_dim]
                proprio = fixed
        raw_obs[self.state_feature_name] = proprio

        action = predict_action(
            observation=raw_obs,
            policy=self.policy,
            device=self.device,
            preprocessor=self.preprocessor,
            postprocessor=self.postprocessor,
            use_amp=False,
            task=instruction,
        )
        action = np.asarray(action.cpu(), dtype=float).reshape(-1)
        if not is_libero and action.shape[0] != 7:
            # Found 2026-08-05: lerobot/pi0_base's own config.json declares
            # output_features["action"].shape == (32,) — the generic
            # max_action_dim padded space, NOT bridge/WidowX's real 7-dim
            # action space. Unlike a checkpoint actually fine-tuned on a
            # specific robot (e.g. pi0_libero_finetuned, whose own declared
            # output dim is already correct), pi0_base/pi05_base are
            # cross-embodiment BASE checkpoints that were never told what
            # THIS robot's real action space is — predict_action()'s
            # postprocessor has no way to know to truncate, since the
            # checkpoint's own metadata says 32 is correct. Confirmed via
            # `PreTrainedConfig.from_pretrained("lerobot/pi0_base").
            # output_features` returning exactly `shape=(32,)` directly, not
            # guessed — and via the crash this caused: SimplerEnv/WidowX's
            # controller asserts `action.shape == (action_dim,)` with
            # action_dim=7, raising `AssertionError: ((32,), 7)` on every
            # single /step call. Training's own `pad_vector()` convention
            # (documented in slava-lerobot-policies' architecture section)
            # appends zeros AFTER the real action values, so the real 7
            # values are the first 7 elements — truncating to `action[:7]`
            # is the correct inverse, the same convention GreenVLA's own
            # `BridgeOutputsTransform` uses (`actions[:, :7]`) for the exact
            # same embodiment.
            action = action[:7]
        return action.tolist()


def main() -> None:
    parser = base_arg_parser()
    args = parser.parse_args()
    backend = LerobotBackend(args.checkpoint, args.device)
    serve(backend, args.port)


if __name__ == "__main__":
    main()
