"""GreenVLA (R0/R1-bridge) model-server. Runs inside `slava-greenvla`
(python -m venv/conda built from github.com/greenvla/GreenVLA — its own
vendored lerobot fork, NOT huggingface/lerobot; see
.claude/skills/slava-model-rollouts/SKILL.md). SimplerEnv/bridge only.

API confirmed directly from GreenVLA's own
examples/example_inference_bridge.py + docs/INFERENCE.md (2026-08-04):
  - load_pretrained_policy(checkpoint, data_config_name="bridge") -> (policy, input_transforms, output_transforms)
  - raw obs dict: {"observation/state": float32[8] (x,y,z,roll,pitch,yaw,_pad_,gripper),
                   "observation/image": uint8 HWC, "prompt": str}
  - input_transforms(raw_obs) -> transformed dict; torch_preprocess_dict_inference + move_dict_to_batch_for_inference
  - policy.select_action(batch) -> normalized actions (action_horizon x 7)
  - output_transforms({"actions": ..., "state": batch["state"]}) -> real-world actions (action_horizon x 7:
    x,y,z,roll,pitch,yaw,gripper)

Open-loop chunk size (found 2026-08-05, re-reading docs/INFERENCE.md's
"Benchmarking Notes" after low SR on R0/R1): "For Bridge (WidowX)
benchmarking on SimplerEnv we used action_horizon=2." `predict_chunk()`
below returns the first 2 actions of the predicted chunk and the
orchestrator executes them open-loop before requerying (same generic
`/predict_chunk` mechanism as openvla_oft_server.py) — matches their
reported protocol exactly, not a guess.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from base_server import base_arg_parser, serve  # noqa: E402


class GreenVLABackend:
    def __init__(self, checkpoint: str, device: str):
        from lerobot.common.policies.factory import load_pretrained_policy

        self.display_name = "GreenVLA"
        self.checkpoint = checkpoint
        self.device = device
        self.policy, self.input_transforms, self.output_transforms = load_pretrained_policy(
            checkpoint, data_config_name="bridge"
        )
        self.policy.to(device).eval()

    # Bridge (WidowX) open-loop chunk size, found 2026-08-05 re-checking
    # GreenVLA's own docs/INFERENCE.md "Benchmarking Notes": "For Bridge
    # (WidowX) benchmarking on SimplerEnv we used action_horizon=2." Our
    # server was previously re-querying the model every single env step and
    # only ever using the chunk's first action (fully closed-loop) — a
    # different execution mode than the one their own reported numbers were
    # produced with. Using the same generic `/predict_chunk` mechanism
    # already built for OpenVLA-OFT's open-loop replay (see
    # openvla_oft_server.py) to match this exactly: query once, execute 2
    # actions open-loop, then requery.
    BRIDGE_ACTION_HORIZON = 2

    @torch.inference_mode()
    def predict_chunk(self, instruction: str, obs: dict, meta: dict) -> list[list[float]]:
        from lerobot.common.utils.torch_observation import (
            move_dict_to_batch_for_inference,
            torch_preprocess_dict_inference,
        )

        ee_pose = obs["ee_pose"]  # [x,y,z,qw,qx,qy,qz], from env_worker_simpler._ee_pose_xyzquat
        roll, pitch, yaw = Rotation.from_quat(
            [ee_pose[4], ee_pose[5], ee_pose[6], ee_pose[3]]  # scipy wants xyzw
        ).as_euler("xyz")
        state = np.array(
            [ee_pose[0], ee_pose[1], ee_pose[2], roll, pitch, yaw, 0.0, obs["gripper_closedness"]],
            dtype=np.float32,
        )
        raw_obs = {
            "observation/state": state,
            "observation/image": obs["agentview_rgb"],
            "prompt": instruction,
        }
        transformed = self.input_transforms(raw_obs)
        preprocessed = torch_preprocess_dict_inference(transformed)
        batch = move_dict_to_batch_for_inference(preprocessed, device=self.device)
        raw_actions = self.policy.select_action(batch).cpu().numpy()
        actions = self.output_transforms(
            {"actions": raw_actions, "state": batch["state"].cpu().numpy()}
        )["actions"]
        # `actions` carries a leading batch dim of 1 in addition to the
        # (action_horizon, 7) shape the README's single-sample example
        # implies (that example's `actions[0]` already assumed batch=1 was
        # squeezed away, which isn't the case here) — confirmed the hard way:
        # a real rollout crashed downstream with action.shape == (10, 7)
        # instead of (7,) once this got passed to env.step(). Reshape to
        # (-1, 7) first so this is correct regardless of whether a batch dim
        # is present, then take the benchmarked-horizon prefix of the chunk.
        action_dim = actions.shape[-1]
        chunk = np.asarray(actions, dtype=float).reshape(-1, action_dim)[: self.BRIDGE_ACTION_HORIZON]
        # Gripper range fix (found 2026-08-05, debugging near-0 SR under time
        # pressure): GreenVLA's raw gripper channel values observed in real
        # rollouts stay entirely within ~[0.02, 0.98] (never negative) — a
        # [0,1] convention (0=close, 1=open), consistent with common
        # real-robot BridgeData action encodings. But SimplerEnv/ManiSkill2's
        # WidowX gripper controller (`PDJointPosMimicControllerConfig` in
        # ManiSkill2_real2sim/agents/configs/widowx/defaults.py) is built with
        # `normalize_action=True`, which expects actions in [-1, 1] mapped
        # linearly to the joint's [lower, upper] range — sending a raw [0,1]
        # value straight through means a "fully close" command of ~0 only
        # reaches the *midpoint* of the joint range (half-closed), never a
        # firm grasp. `env_worker_simpler.py` applies no gripper
        # post-processing at all (unlike LIBERO/OpenVLA-OFT, which needed
        # normalize+invert — see openvla_oft_server.py). Empirical evidence:
        # `gripper_state` (actual physical closedness) never exceeded ~0.6 in
        # observed rollouts even when the model clearly intended a firm grasp
        # (contact with target registered, action near 0). Rescaling [0,1] ->
        # [-1,1] via `2x-1` fixes the range without needing a sign flip (the
        # polarity already matches: GreenVLA's ~1=open maps to +1=open,
        # ~0=close maps to -1=close under this env's convention).
        chunk[:, -1] = 2.0 * chunk[:, -1] - 1.0
        return chunk.tolist()

    def predict(self, instruction: str, obs: dict, meta: dict) -> list[float]:
        return self.predict_chunk(instruction, obs, meta)[0]


def main() -> None:
    parser = base_arg_parser()
    args = parser.parse_args()
    backend = GreenVLABackend(args.checkpoint, args.device)
    serve(backend, args.port)


if __name__ == "__main__":
    main()
