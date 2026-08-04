#!/usr/bin/env python3
"""Validate frames_v0.jsonl against the v0.2 grounded semantic frame schema.

Beyond the pure-data schema (src/slava_inventory/frames_schema.py), this CLI
also covers two QA-pipeline rules from task.md that need filesystem/inventory
context rather than just the record itself:
  1. Все обязательные файлы картинок существуют.
  2. Все sim_handle существуют в живой среде (proxied here against
     data/task_inventory.jsonl, the source of truth for what the live
     LIBERO/SimplerEnv collectors actually saw).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl  # noqa: E402
from slava_inventory.frames_schema import validate_frames  # noqa: E402

DEFAULT_FILES = [PROJECT_ROOT / "data" / "pilot_v0_release" / "frames_v0.jsonl"]
DEFAULT_INVENTORY = PROJECT_ROOT / "data" / "task_inventory.jsonl"
IMAGES_BASE_DIR = PROJECT_ROOT / "data"


def check_images_exist(records: list[dict], base_dir: Path) -> list[str]:
    errors = []
    for record in records:
        for field in ("agentview_rgb", "wrist_rgb"):
            rel_path = record["images"][field]
            if rel_path is None:
                continue
            if not (base_dir / rel_path).is_file():
                errors.append(f"{record['task_uid']}: images.{field} missing on disk: {rel_path}")
    return errors


def check_sim_handles(records: list[dict], inventory_path: Path) -> list[str]:
    errors = []
    if not inventory_path.is_file():
        return [f"cannot cross-check sim_handle: {inventory_path} not found"]
    inventory = {r["task_uid"]: r for r in load_jsonl(inventory_path)}
    for record in records:
        uid = record["task_uid"]
        source_record = inventory.get(uid)
        if source_record is None:
            errors.append(f"{uid}: not found in {inventory_path.name}, cannot verify sim_handle")
            continue
        live_handles = {o["sim_handle"] for o in source_record["objects_raw"]}
        for obj in record["scene"]["objects"]:
            if obj["sim_handle"] not in live_handles:
                errors.append(
                    f"{uid}: scene.objects id={obj['id']!r} sim_handle={obj['sim_handle']!r} "
                    f"not among live objects_raw in {inventory_path.name}"
                )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="*", default=DEFAULT_FILES)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    args = parser.parse_args()
    for path in args.files:
        records = load_jsonl(path)
        validate_frames(records)
        errors = check_images_exist(records, IMAGES_BASE_DIR) + check_sim_handles(records, args.inventory)
        if errors:
            print(f"FAIL: {path} ({len(records)} records, {len(errors)} issue(s)):")
            for error in errors:
                print("  -", error)
            raise SystemExit(1)
        print(f"OK: {path} ({len(records)} records)")


if __name__ == "__main__":
    main()
