#!/usr/bin/env python3
"""Fold manual verdicts from data/label_review.html into the repository and
report how often the auto-labeller agreed.

The human verdicts are the ground truth here (user decision, 07.08.2026): where
they disagree with `auto_label.py`, the disagreement is a bug report against the
labeller, not noise to average away. Verdicts are stored separately, in
the pool's manual_labels.jsonl — the annotations file stays machine-generated, so
the dataset never becomes a silent mixture of two label sources.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ROLLOUTS = PROJECT_ROOT / "rollouts" / "final" / "pilot_v0"


def wilson(successes: int, total: int) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    z = 1.959963984540054
    phat = successes / total
    denom = 1 + z * z / total
    centre = (phat + z * z / (2 * total)) / denom
    margin = z * ((phat * (1 - phat) / total + z * z / (4 * total * total)) ** 0.5) / denom
    return (max(centre - margin, 0.0), min(centre + margin, 1.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("verdicts", type=Path, help="label_review_verdicts.json exported from the dashboard")
    parser.add_argument("--output", type=Path, default=ROLLOUTS / "manual_labels.jsonl")
    args = parser.parse_args()

    verdicts = {v["run_id"]: v for v in json.loads(args.verdicts.read_text())}
    auto = {
        r["run_id"]: r
        for r in (json.loads(line) for line in (ROLLOUTS / "rollout_annotations.jsonl").read_text().splitlines() if line.strip())
    }

    missing = [run_id for run_id in verdicts if run_id not in auto]
    if missing:
        raise SystemExit(f"{len(missing)} verdicts reference unknown run_ids, e.g. {missing[0]}")

    rows = []
    for run_id, verdict in verdicts.items():
        record = auto[run_id]
        rows.append({
            "run_id": run_id,
            "model": record["model"],
            "variant": record["variant"],
            "success_auto": record["success"],
            "success_manual": verdict["success"],
            "failure_type_auto": record["failure_type_auto"],
            "failure_type_manual": verdict.get("failure_type_manual"),
            "note": verdict.get("note"),
        })
    args.output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))

    n = len(rows)
    success_ok = sum(1 for r in rows if r["success_auto"] == r["success_manual"])
    labelled = [r for r in rows if r["failure_type_manual"]]
    label_ok = sum(1 for r in labelled if r["failure_type_auto"] == r["failure_type_manual"])
    low, high = wilson(success_ok, n)
    print(f"{n} проверено -> {args.output}")
    print(f"success:  {success_ok}/{n} = {success_ok / max(n, 1):.1%}  Wilson [{low:.1%}; {high:.1%}]")
    if labelled:
        low2, high2 = wilson(label_ok, len(labelled))
        print(f"метка:    {label_ok}/{len(labelled)} = {label_ok / len(labelled):.1%}  Wilson [{low2:.1%}; {high2:.1%}]")

    confusion = collections.Counter(
        (r["failure_type_auto"], r["failure_type_manual"]) for r in labelled
        if r["failure_type_auto"] != r["failure_type_manual"]
    )
    if confusion:
        print("\nрасхождения (авто -> человек):")
        for (a, m), count in confusion.most_common():
            print(f"  {a:26s} -> {m:26s} {count}")


if __name__ == "__main__":
    main()
