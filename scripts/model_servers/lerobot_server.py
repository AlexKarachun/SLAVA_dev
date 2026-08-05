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

        self.preprocessor, self.postprocessor = make_pre_post_processors(
            policy_cfg, pretrained_path=checkpoint
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
            if camera_idx < len(real_cameras):
                raw_obs[name] = real_cameras[camera_idx]
                camera_idx += 1
            else:
                # More real (non-placeholder) camera slots than the env has
                # real cameras — repeat the last available frame rather than
                # crash. Distinct from the empty_camera_N case above, which
                # must stay zero.
                raw_obs[name] = real_cameras[-1]

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
        return np.asarray(action.cpu(), dtype=float).reshape(-1).tolist()


def main() -> None:
    parser = base_arg_parser()
    args = parser.parse_args()
    backend = LerobotBackend(args.checkpoint, args.device)
    serve(backend, args.port)


if __name__ == "__main__":
    main()
