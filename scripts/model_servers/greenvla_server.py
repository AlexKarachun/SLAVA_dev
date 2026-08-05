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
    x,y,z,roll,pitch,yaw,gripper) — we execute only the first action of the horizon, one env step per /predict
    call (the orchestrator calls /predict once per sim step; action-chunking replay is a later optimization,
    not needed for a first correctness pass).
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

    @torch.inference_mode()
    def predict(self, instruction: str, obs: dict, meta: dict) -> list[float]:
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
        # is present, then take the first (current) timestep of the chunk.
        action_dim = actions.shape[-1]
        first_action = np.asarray(actions, dtype=float).reshape(-1, action_dim)[0]
        return first_action.tolist()


def main() -> None:
    parser = base_arg_parser()
    args = parser.parse_args()
    backend = GreenVLABackend(args.checkpoint, args.device)
    serve(backend, args.port)


if __name__ == "__main__":
    main()
