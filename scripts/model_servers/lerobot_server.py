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
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

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

        real_cameras = []
        if obs.get("wrist_rgb") is not None:
            real_cameras.append(np.asarray(obs["wrist_rgb"]))
        real_cameras.append(np.asarray(obs["agentview_rgb"]))

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

        proprio = np.asarray(obs.get("proprioception", []), dtype=np.float32)
        expected_dim = self.state_feature.shape[0]
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
