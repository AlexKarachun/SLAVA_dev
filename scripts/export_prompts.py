#!/usr/bin/env python3
"""Export data/pilot_v0_release/frames_v0.jsonl into flat prompts for the first model rollouts
-- task.md's "Definition of Done: pilot v0" ("Есть export_prompts.py",
"Есть первые prompts для OpenVLA/GreenVLA-style eval").

task.md doesn't specify an output format; decided with the user: JSONL, one
line per (task_uid, variant), covering the 6 primary variants from task.md's
"Сначала затравка" list (en_canonical, en_paraphrase, ru_literal,
ru_case_swap, ru_negation, code_switch) plus mt_russian -- not the full
Tier-1+желательные set. mt_russian was added once a real MT pass filled it
(also its own row in task.md's "Table - behavioral pilot"); if it's null
this script would just skip it per-record like any other axis_na variant,
so re-running against a draft frames_v0.jsonl still works. A record's
axis_na variants (e.g. ru_case_swap on a scene without a reference) are
skipped, not emitted as null prompts.

Each line carries the reset metadata (LIBERO bddl_file/init_state_id or
SimplerEnv episode_id/reset_seed/gym_env_name) and the target/reference/
forbidden/success_predicates slots an eval harness needs to auto-label a
rollout per task.md's rollout_annotations.jsonl fields (first_contact_object,
target_object, reference_object, forbidden_object_touched, ...) -- not just
the instruction string.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl, save_jsonl  # noqa: E402

DEFAULT_FRAMES = PROJECT_ROOT / "data" / "pilot_v0_release" / "frames_v0.jsonl"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "pilot_v0_release" / "prompts_v0.jsonl"

# task.md "Сначала затравка": "6 primary-вариантов: en_canonical,
# en_paraphrase, ru_literal, ru_case_swap, ru_negation, code_switch".
# mt_russian added once it stopped being null (real MT pass done) -- it's
# also its own row in task.md's "Table - behavioral pilot", so it belongs
# in the first rollouts alongside the other 6.
PRIMARY_VARIANTS = [
    "en_canonical",
    "en_paraphrase",
    "mt_russian",
    "ru_literal",
    "ru_case_swap",
    "ru_negation",
    "code_switch",
]


def build_prompts(frames: list[dict]) -> list[dict]:
    prompts = []
    for frame in frames:
        variants = frame["variants"]
        slots = frame["slots"]
        for variant in PRIMARY_VARIANTS:
            instruction = variants[variant]
            if instruction is None:
                continue  # axis_na for this scene -- no prompt to emit
            prompts.append(
                {
                    "prompt_id": f"{frame['task_uid']}__{variant}",
                    "task_uid": frame["task_uid"],
                    "variant": variant,
                    "instruction": instruction,
                    "suite": frame["suite"],
                    "environment": frame["environment"],
                    "task_name": frame["task_name"],
                    "bddl_file": frame["bddl_file"],
                    "init_state_id": frame["init_state_id"],
                    "episode_id": frame["episode_id"],
                    "reset_seed": frame["reset_seed"],
                    "gym_env_name": frame["gym_env_name"],
                    "images": {
                        "agentview_rgb": frame["images"]["agentview_rgb"],
                        "wrist_rgb": frame["images"]["wrist_rgb"],
                    },
                    "action": slots["action"],
                    "target_object": slots["target"],
                    "reference_object": slots["reference"],
                    "relation": slots["relation"],
                    "forbidden_objects": slots["forbidden"],
                    "success_predicates": slots["success_predicates"],
                }
            )
    return prompts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    frames = load_jsonl(args.frames)
    prompts = build_prompts(frames)
    save_jsonl(prompts, args.output)
    print(f"Exported {len(prompts)} prompts from {len(frames)} scenes -> {args.output}")


if __name__ == "__main__":
    main()
