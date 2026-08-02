#!/usr/bin/env python3
"""Propagate objects_raw visibility from task_inventory.jsonl into selected_tasks_v0.jsonl.

selected_tasks_v0.jsonl is a frozen snapshot of 20 rows pulled from
task_inventory.jsonl at D3 selection time. Everything about those 20 rows
stays frozen except visible_agentview / visible_wrist, which should track
task_inventory.jsonl as visibility review continues (e.g. after applying
corrections from data/visibility_review.html via apply_visibility_review.py).

Run after any change to task_inventory.jsonl's visibility fields:

    python scripts/sync_selected_tasks_visibility.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl, save_jsonl  # noqa: E402
from slava_inventory.schema import validate_inventory  # noqa: E402


def main() -> None:
    inventory_path = PROJECT_ROOT / "data" / "task_inventory.jsonl"
    selected_path = PROJECT_ROOT / "data" / "selected_tasks_v0.jsonl"

    inventory = {r["task_uid"]: r for r in load_jsonl(inventory_path)}
    selected = load_jsonl(selected_path)

    updated = 0
    missing_uid = []
    for row in selected:
        src = inventory.get(row["task_uid"])
        if src is None:
            missing_uid.append(row["task_uid"])
            continue
        src_objects = {o["sim_handle"]: o for o in src["objects_raw"]}
        for obj in row["objects_raw"]:
            src_obj = src_objects.get(obj["sim_handle"])
            if src_obj is None:
                continue
            if (
                obj["visible_agentview"] != src_obj["visible_agentview"]
                or obj["visible_wrist"] != src_obj["visible_wrist"]
            ):
                obj["visible_agentview"] = src_obj["visible_agentview"]
                obj["visible_wrist"] = src_obj["visible_wrist"]
                updated += 1

    if missing_uid:
        print(f"WARNING: task_uid in {selected_path.name} missing from {inventory_path.name}: {missing_uid}")

    validate_inventory(selected)
    save_jsonl(selected, selected_path)
    print(f"Updated visibility on {updated} object rows across {len(selected)} selected tasks")


if __name__ == "__main__":
    main()
