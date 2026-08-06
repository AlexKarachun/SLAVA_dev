#!/usr/bin/env python3
"""Recompute the derived label fields of rollout_annotations.jsonl from each
episode's raw `steps.jsonl`, using the current `slava_rollout.auto_label`.

Why this exists: `failure_type_auto` and friends are DERIVED quantities. When
the labeling rules are corrected (as they were for the environment-dependent
`no_action_or_timeout`/`unclear` artifact — see auto_label.label_episode), the
already-collected dataset is stale. Re-running 550 GPU episodes to fix a
labeling bug would be absurd; hand-editing the labels would be indistinguishable
from fudging results. So we recompute them from the raw per-step record that was
logged at collection time, and print exactly what changed.

What is re-derived vs. carried over:
  * re-derived  — success, failure_type_auto, wrong_object,
                  forbidden_object_touched, final_relation_success,
                  conditional_execution_success
  * carried over — first_contact_object (a raw observation from the contact
                  tracker at collection time; `steps.jsonl` stores the
                  cumulative touched SET, alphabetically sorted, so first-touch
                  ORDER cannot be recovered from it after the fact)
  * re-read      — target/reference/forbidden/relation/success_predicates, from
                  data/pilot_v0_release/prompts_v0.jsonl (the frozen contract)

Usage:
    python3 scripts/relabel_rollouts.py              # dry run, prints the diff
    python3 scripts/relabel_rollouts.py --write      # rewrite, keeping a backup
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from slava_rollout.auto_label import label_episode  # noqa: E402
from slava_rollout.schema import validate_rollout_annotation  # noqa: E402

ANNOTATIONS = PROJECT_ROOT / "rollouts" / "rollout_annotations.jsonl"
EPISODES = PROJECT_ROOT / "rollouts" / "episodes"
PROMPTS = PROJECT_ROOT / "data" / "pilot_v0_release" / "prompts_v0.jsonl"

DERIVED_FIELDS = (
    "success",
    "failure_type_auto",
    "wrong_object",
    "forbidden_object_touched",
    "final_relation_success",
    "conditional_execution_success",
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_steps(run_id: str) -> list[dict[str, Any]]:
    path = EPISODES / run_id / "steps.jsonl"
    if not path.is_file():
        return []
    out = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def relabel(row: dict[str, Any], prompts: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any] | None:
    """Return a new row with re-derived fields, or None if raw data is missing."""
    steps = read_steps(row["run_id"])
    if not steps:
        return None
    prompt = prompts.get((row["task_uid"], row["variant"]))
    if prompt is None:
        return None

    last = steps[-1]
    label = label_episode(
        env_success=bool(last.get("success_so_far", False)),
        # Raw tracker observation, not a derived label — see module docstring.
        first_contact_object=row.get("first_contact_object"),
        touched_objects=list(last.get("contacts") or []),
        target_object=prompt.get("target_object"),
        reference_object=prompt.get("reference_object"),
        forbidden_objects=prompt.get("forbidden_objects") or [],
        relation=prompt.get("relation"),
        action=prompt.get("action"),
        final_object_poses=last.get("object_poses") or {},
        success_predicates=prompt.get("success_predicates") or [],
        step_count=len(steps),
        # Every row that exists in rollout_annotations.jsonl was written after
        # its episode loop finished normally: run_episode() only appends after
        # the loop, and any error propagates out of it so no row is written at
        # all (see scripts/run_rollouts.py's per-episode try/except). So an
        # annotated episode is by construction one that ran its full horizon.
        ran_to_completion=True,
    )
    return {**row, **label}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="rewrite the file (default: dry run)")
    parser.add_argument("--annotations", type=Path, default=ANNOTATIONS)
    args = parser.parse_args()

    rows = load_jsonl(args.annotations)
    prompts = {(p["task_uid"], p["variant"]): p for p in load_jsonl(PROMPTS)}

    new_rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    transitions: Counter = Counter()
    field_changes: Counter = Counter()

    for row in rows:
        new = relabel(row, prompts)
        if new is None:
            skipped.append(row["run_id"])
            new_rows.append(row)
            continue
        for field in DERIVED_FIELDS:
            if row.get(field) != new.get(field):
                field_changes[field] += 1
        if row.get("failure_type_auto") != new.get("failure_type_auto"):
            transitions[(row.get("failure_type_auto"), new.get("failure_type_auto"))] += 1
        validate_rollout_annotation(new)
        new_rows.append(new)

    print(f"episodes: {len(rows)}   relabeled: {len(rows) - len(skipped)}   skipped (no raw data): {len(skipped)}")
    if skipped:
        for run_id in skipped[:5]:
            print(f"  skipped: {run_id}")
        if len(skipped) > 5:
            print(f"  ... and {len(skipped) - 5} more")

    print("\nchanged fields:")
    if not field_changes:
        print("  (none — current labels already match the current rules)")
    for field, n in field_changes.most_common():
        print(f"  {field:32s} {n}")

    if transitions:
        print("\nfailure_type_auto transitions:")
        for (old, new), n in transitions.most_common():
            print(f"  {old or '-':26s} -> {new or '-':26s} {n}")

    # A relabel must never change `success`: it comes from the environment's own
    # checker, recorded per step at collection time. If it moves, the raw data
    # and the annotations disagree about what happened, which is a data-integrity
    # problem, not a labeling one.
    if field_changes.get("success"):
        print(
            f"\nREFUSING TO WRITE: `success` changed on {field_changes['success']} episodes. "
            "That value comes from the environment, not from these rules — "
            "investigate the raw steps.jsonl before trusting either file.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    if not args.write:
        print("\ndry run — nothing written. Re-run with --write to apply.")
        return

    backup = args.annotations.with_suffix(args.annotations.suffix + ".bak_before_relabel")
    shutil.copy2(args.annotations, backup)
    with open(args.annotations, "w", encoding="utf-8") as handle:
        for row in new_rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\nwrote {args.annotations} ({len(new_rows)} rows); backup at {backup.name}")


if __name__ == "__main__":
    main()
