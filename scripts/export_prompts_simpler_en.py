#!/usr/bin/env python3
"""Export en_canonical-only SimplerEnv prompts from data/full_set/simpler_inventory.jsonl.

Why this exists, separately from scripts/export_prompts.py: harness validation
asks a different question from the benchmark itself. The pilot's four SimplerEnv
scenes are all `widowx_stack_cube` — one task, and the hardest of the four bridge
tasks — so a published average that also covers spoon/carrot/eggplant cannot be
set against it. To check "does our pipeline reproduce a known number", we need
the authors' own task set on their own English strings, with n large enough for
the interval to mean something.

Output rows use the same flat schema as data/pilot_v0_release/prompts_v0.jsonl,
so scripts/run_rollouts.py consumes them unchanged. Only `en_canonical` is
emitted: no instruction variants, nothing to compare across languages here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def convert(record: dict) -> dict:
    source = record["source"]
    slots = record.get("candidate_slots") or {}
    task_uid = record["task_uid"]
    predicates = []
    for predicate in record.get("success_predicates") or []:
        # The inventory speaks the simulator's language (`src_on_target`), the
        # prompt schema speaks the frame's (`spatial_relation`). SimplerEnv
        # success itself comes from the simulator, not from these; they only
        # feed auto-labelling of what was touched and where it ended up.
        if predicate.get("type") == "src_on_target":
            predicates.append({
                "type": "spatial_relation",
                "relation": "on",
                "arg1": predicate.get("source"),
                "arg2": predicate.get("target"),
            })
        else:
            predicates.append(predicate)
    return {
        "prompt_id": f"{task_uid}__en_canonical",
        "task_uid": task_uid,
        "variant": "en_canonical",
        "instruction": record["canonical_en"],
        "suite": record["suite"],
        "environment": "SimplerEnv",
        "task_name": source["task_name"],
        "bddl_file": None,
        "init_state_id": None,
        "episode_id": source.get("episode_id", 0),
        "reset_seed": source.get("reset_seed", 0),
        "gym_env_name": source.get("gym_env_name"),
        "images": record.get("images", {}),
        "action": slots.get("action"),
        "target_object": slots.get("target"),
        "reference_object": slots.get("reference"),
        "relation": slots.get("relation"),
        "forbidden_objects": slots.get("forbidden_candidates") or [],
        "success_predicates": predicates,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default=PROJECT_ROOT / "data/full_set/simpler_inventory.jsonl", type=Path)
    parser.add_argument("--output", default=PROJECT_ROOT / "data/full_set/prompts_simpler_en.jsonl", type=Path)
    args = parser.parse_args()

    records = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    rows = [convert(record) for record in records]
    args.output.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    print(f"{len(rows)} prompts -> {args.output}")


if __name__ == "__main__":
    main()
