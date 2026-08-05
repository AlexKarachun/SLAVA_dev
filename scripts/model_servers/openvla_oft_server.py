"""OpenVLA-OFT model-server (LIBERO only). Runs inside `slava-openvla`, built
from github.com/moojink/openvla-oft (cloned to $OPENVLA_OFT_ROOT — see
.claude/skills/slava-model-rollouts/SKILL.md).

Reuses their own experiments/robot/{robot_utils,openvla_utils}.py and
experiments/robot/libero/libero_utils.py loading/inference functions directly
rather than reimplementing OFT's parallel-decoding + proprio-projector +
L1-regression-head pipeline — LIBERO.md documents that the released
`moojink/openvla-7b-oft-finetuned-*` checkpoints just need the script's
*default* GenerateConfig values (num_images_in_input=2, use_proprio=True,
use_l1_regression=True, center_crop=True), so we build the same cfg they do
and reuse `get_model`/`get_processor`/`get_action_head`/`get_proprio_projector`/
`get_action` unchanged.

`unnorm_key` is keyed by LIBERO suite name (libero_spatial/object/goal), not
derivable from pixels — comes from `meta["suite"]` per request, matched to
`.claude/skills/slava-model-rollouts/SKILL.md`'s note that this must be
looked up at run time, not hardcoded.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

sys.path.insert(0, str(Path(__file__).resolve().parent))
from base_server import base_arg_parser, serve  # noqa: E402

OPENVLA_OFT_ROOT = Path(os.environ.get("OPENVLA_OFT_ROOT", "/workspace/openvla_oft_repo"))
sys.path.insert(0, str(OPENVLA_OFT_ROOT))

# experiments/robot/libero/run_libero_eval.py imports `from libero.libero import
# benchmark` at module level just to define GenerateConfig — `pip install -e` for
# the LIBERO package in this env hit a real conflict with openvla-oft's own PEP
# 660 editable-install import finder (its __editable__ finder on sys.path shadows
# resolution for other editable packages; `import libero` silently 404s even
# though `pip show libero` reports it installed). Sidestepping via plain
# sys.path injection instead of `pip install -e /workspace/LIBERO` — this env
# never touches LIBERO's actual physics/rendering (that's env_worker_libero.py's
# job, in the separate `slava-libero` env), so no editable-install machinery is
# needed here at all, just the plain package on the import path.
LIBERO_ROOT = Path(os.environ.get("LIBERO_ROOT", "/workspace/LIBERO"))
sys.path.insert(0, str(LIBERO_ROOT))


class OpenVLAOFTBackend:
    def __init__(self, checkpoint: str, device: str):
        from experiments.robot.libero.run_libero_eval import GenerateConfig
        from experiments.robot.openvla_utils import get_action_head, get_processor, get_proprio_projector
        from experiments.robot.robot_utils import get_model, set_seed_everywhere

        self.display_name = "OpenVLA-OFT"
        self.checkpoint = checkpoint
        self.device = device
        # Defaults match run_libero_eval.py's GenerateConfig exactly — see LIBERO.md:
        # "we set them to the default values that work with the OpenVLA-OFT checkpoints above."
        self.cfg = GenerateConfig(pretrained_checkpoint=checkpoint)
        set_seed_everywhere(self.cfg.seed)

        self.model = get_model(self.cfg)
        self.processor = get_processor(self.cfg)
        self.proprio_projector = (
            get_proprio_projector(self.cfg, self.model.llm_dim, proprio_dim=8)
            if self.cfg.use_proprio
            else None
        )
        self.action_head = (
            get_action_head(self.cfg, self.model.llm_dim)
            if (self.cfg.use_l1_regression or self.cfg.use_diffusion)
            else None
        )
        self._unnorm_key_checked_for: set[str] = set()

    def _ensure_unnorm_key(self, suite: str) -> None:
        if suite in self._unnorm_key_checked_for:
            return
        candidates = [suite, f"{suite}_no_noops"]
        for key in candidates:
            if key in self.model.norm_stats:
                self.cfg.unnorm_key = key
                self._unnorm_key_checked_for.add(suite)
                return
        raise RuntimeError(
            f"No unnorm_key found for suite {suite!r} in checkpoint norm_stats "
            f"({list(self.model.norm_stats.keys())})"
        )

    def predict(self, instruction: str, obs: dict, meta: dict) -> list[float]:
        from experiments.robot.robot_utils import get_action, invert_gripper_action, normalize_gripper_action

        suite = meta.get("suite")
        if not suite:
            raise ValueError("openvla_oft_server requires meta.suite (libero_spatial/object/goal/...)")
        self._ensure_unnorm_key(suite)

        proprio = np.asarray(obs["proprioception"], dtype=np.float32)
        # env_worker_libero proprioception layout: [gripper_qpos(2), eef_pos(3), eef_quat(4)] (xyzw).
        gripper_qpos, eef_pos, eef_quat = proprio[:2], proprio[2:5], proprio[5:9]
        axis_angle = Rotation.from_quat(eef_quat).as_rotvec()
        state = np.concatenate([eef_pos, axis_angle, gripper_qpos]).astype(np.float32)

        observation = {
            "full_image": obs["agentview_rgb"],
            "wrist_image": obs["wrist_rgb"],
            "state": state,
        }
        action = get_action(
            self.cfg,
            self.model,
            observation,
            instruction,
            processor=self.processor,
            action_head=self.action_head,
            proprio_projector=self.proprio_projector,
            use_film=self.cfg.use_film,
        )
        # get_action returns a chunk (NUM_ACTIONS_CHUNK, 7); we execute one env
        # step per /predict call, so take the first action of the chunk. This
        # forgoes OFT's open-loop chunk-replay speed optimization for a first
        # correctness pass — action-chunk replay is a later optimization, not
        # needed to validate the pipeline (see SKILL.md smoke-test scope).
        action = np.asarray(action[0] if isinstance(action, (list, tuple)) else action, dtype=float)
        # REQUIRED post-processing, matching run_libero_eval.py's process_action()
        # exactly — missing this was a real bug (caught via 13 straight
        # no_action_or_timeout results with a suspiciously flat gripper_state
        # log across two different tasks, not by re-reading the reference
        # script more carefully). Without it, the gripper channel is left in
        # OpenVLA's dataloader convention (0=close,1=open, range [0,1]) instead
        # of what the env's OSC_POSE controller expects (-1=open,+1=close,
        # range [-1,1]) — i.e. gripper commands were both mis-scaled AND
        # inverted (open commanded as close and vice versa).
        action = normalize_gripper_action(action, binarize=True)
        action = invert_gripper_action(action)
        return action.tolist()


def main() -> None:
    parser = base_arg_parser()
    args = parser.parse_args()
    backend = OpenVLAOFTBackend(args.checkpoint, args.device)
    serve(backend, args.port)


if __name__ == "__main__":
    main()
