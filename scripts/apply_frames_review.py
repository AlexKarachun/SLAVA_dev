#!/usr/bin/env python3
"""Apply corrections exported from data/frames_review.html to frames_v0.jsonl.

The dashboard's "Download corrections" button produces a JSON array of ops:
  {op: "set_role", task_uid, object_id, value ("target"|"reference"|"distractor"|"background")}
  {op: "toggle_forbidden", task_uid, object_id, value (bool)}
  {op: "set_slot", task_uid, field ("action"|"relation"), value}
  {op: "set_variant", task_uid, field, value}
  {op: "set_axis_na", task_uid, field, enabled, reason, text}
  {op: "set_score", task_uid, field, metric, value}
  {op: "set_validation", task_uid, field ("native_check"|"notes"), value}

slots.target/reference are re-derived from scene.objects[].role after every
"set_role" op (exactly one target, at most one reference). forbidden is NOT
a role -- task.md's frame template only has target/reference/distractor --
so it is an independent id list toggled directly via "toggle_forbidden",
scoped to whatever the object's role happens to be (usually "distractor",
but a "reference" object can double as forbidden, e.g. the wrong object to
grasp in a stacking task).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FRAMES = PROJECT_ROOT / "data" / "pilot_v0_release" / "frames_v0.jsonl"
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_inventory.io_utils import load_jsonl, save_jsonl  # noqa: E402
from slava_inventory.frames_schema import validate_frames  # noqa: E402


def recompute_target_reference(frame: dict) -> None:
    """target/reference are 1-per-scene structural roles, so re-derive them
    from scene.objects[].role after a role edit. forbidden is NOT a role
    (task.md's template only has target/reference/distractor) -- it is an
    independent subset of distractor ids, toggled directly via
    "toggle_forbidden" ops and left untouched here."""
    objects = frame["scene"]["objects"]
    target = next((o["id"] for o in objects if o["role"] == "target"), None)
    reference = next((o["id"] for o in objects if o["role"] == "reference"), None)
    if target is not None:
        frame["slots"]["target"] = target
    frame["slots"]["reference"] = reference
    if frame["slots"]["relation"] is None:
        frame["slots"]["reference"] = None


def apply_ops(frames_by_uid: dict[str, dict], ops: list[dict]) -> tuple[int, list[str]]:
    applied = 0
    errors = []
    touched: set[str] = set()
    for entry in ops:
        op = entry.get("op")
        uid = entry.get("task_uid")
        frame = frames_by_uid.get(uid)
        if frame is None:
            errors.append(f"{uid}: unknown task_uid")
            continue
        try:
            if op == "set_role":
                obj = next(o for o in frame["scene"]["objects"] if o["id"] == entry["object_id"])
                obj["role"] = entry["value"]
                touched.add(uid)
            elif op == "toggle_forbidden":
                oid = entry["object_id"]
                forbidden = frame["slots"]["forbidden"]
                if entry["value"]:
                    if oid not in forbidden:
                        forbidden.append(oid)
                else:
                    frame["slots"]["forbidden"] = [f for f in forbidden if f != oid]
            elif op == "set_slot":
                field = entry["field"]
                value = entry["value"] or None
                if field not in ("action", "relation"):
                    raise ValueError(f"bad slot field {field!r}")
                frame["slots"][field] = value
                touched.add(uid)
            elif op == "set_variant":
                field = entry["field"]
                text = entry["value"].strip()
                frame["variants"][field] = text or None
            elif op == "set_axis_na":
                field = entry["field"]
                if entry["enabled"]:
                    frame["variants"][field] = None
                    reason = (entry.get("reason") or "").strip()
                    if reason:
                        frame["axis_na"][field] = reason
                else:
                    frame["axis_na"].pop(field, None)
                    text = (entry.get("text") or "").strip()
                    if text:
                        frame["variants"][field] = text
            elif op == "set_score":
                field, metric, value = entry["field"], entry["metric"], entry["value"]
                if value is None:
                    frame["validation"][metric].pop(field, None)
                else:
                    frame["validation"][metric][field] = int(value)
            elif op == "set_validation":
                field = entry["field"]
                if field not in ("native_check", "notes"):
                    raise ValueError(f"bad validation field {field!r}")
                frame["validation"][field] = entry["value"]
            else:
                raise ValueError(f"unknown op {op!r}")
            applied += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{uid}: {op} failed: {exc}")

    for uid in touched:
        recompute_target_reference(frames_by_uid[uid])
    return applied, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corrections", type=Path, help="frames_review_corrections.json from the dashboard")
    parser.add_argument("--frames", type=Path, default=DEFAULT_FRAMES)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ops = json.loads(args.corrections.read_text())
    frames = load_jsonl(args.frames)
    frames_by_uid = {f["task_uid"]: f for f in frames}

    applied, errors = apply_ops(frames_by_uid, ops)
    if errors:
        print(f"{len(errors)} op(s) could not be applied:")
        for e in errors:
            print("  -", e)

    validate_frames(frames)
    save_jsonl(frames, args.frames)
    print(f"Applied {applied}/{len(ops)} ops to {args.frames}")


if __name__ == "__main__":
    main()
