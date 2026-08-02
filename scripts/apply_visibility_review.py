#!/usr/bin/env python3
"""Apply corrections exported from data/visibility_review.html to task_inventory.jsonl.

The dashboard's "Download corrections" button produces a JSON array of
{task_uid, sim_handle, field, value} entries for every cell the user changed
from what was on screen. This script applies them on top of the *current*
task_inventory.jsonl, validates the result, and saves it atomically.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = PROJECT_ROOT / "data" / "task_inventory.jsonl"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl, save_jsonl  # noqa: E402
from slava_inventory.schema import normalize_inventory_record, validate_inventory  # noqa: E402

VALID_FIELDS = {"visible_agentview", "visible_wrist"}
VALID_VALUES = {True, False, "visible_partial", None}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corrections", type=Path, help="visibility_corrections.json from the dashboard")
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    corrections = json.loads(args.corrections.read_text())
    inventory = load_jsonl(args.inventory)
    obj_index = {}
    for record in inventory:
        for obj in record.get("objects_raw", []):
            obj_index[(record["task_uid"], obj["sim_handle"])] = obj

    applied = 0
    errors = []
    for entry in corrections:
        field = entry.get("field")
        value = entry.get("value")
        key = (entry.get("task_uid"), entry.get("sim_handle"))
        if field not in VALID_FIELDS:
            errors.append(f"{key}: bad field {field!r}")
            continue
        if value not in VALID_VALUES:
            errors.append(f"{key}: bad value {value!r}")
            continue
        obj = obj_index.get(key)
        if obj is None:
            errors.append(f"{key}: not found in {args.inventory}")
            continue
        obj[field] = value
        applied += 1

    if errors:
        print(f"{len(errors)} correction(s) could not be applied:")
        for e in errors:
            print("  -", e)

    records = [normalize_inventory_record(r) for r in inventory]
    validate_inventory(records)
    save_jsonl(records, args.inventory)
    print(f"Applied {applied}/{len(corrections)} corrections to {args.inventory}")


if __name__ == "__main__":
    main()
