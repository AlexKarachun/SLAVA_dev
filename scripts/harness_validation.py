#!/usr/bin/env python3
"""Does our pipeline reproduce the numbers the model authors publish?

Reads any rollout-annotations file (default: the pilot's), keeps `en_canonical`
only — the authors' own English task string, unmodified — and puts the observed
success rate with its Wilson interval next to data/published_baselines.json.

Only en_canonical belongs here. A model aggregate mixes canonical English with
deliberately perturbed variants and cannot be compared with a paper.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    parser.add_argument("--pool", default="pilot_v0",
                        help="Episode pool under rollouts/final/ (see rollouts/RUNS.md).")
    parser.add_argument("--annotations", type=Path, default=None,
                        help="Explicit annotations file; overrides --pool.")
    parser.add_argument("--by-task", action="store_true", help="also break down by task_uid prefix")
    args = parser.parse_args()

    annotations = args.annotations or (
        PROJECT_ROOT / "rollouts" / "final" / args.pool / "rollout_annotations.jsonl"
    )
    rows = [json.loads(line) for line in annotations.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if r["variant"] == "en_canonical"]
    baselines = json.loads((PROJECT_ROOT / "data" / "published_baselines.json").read_text())["baselines"]

    totals = collections.Counter(r["model"] for r in rows)
    hits = collections.Counter(r["model"] for r in rows if r["success"])
    print(f"{annotations} — {len(rows)} en_canonical episodes\n")
    print(f"{'модель':34s} {'наше':>12s} {'95% CI':>16s}  {'заявлено':>10s}  вывод")
    for model in sorted(totals):
        total, hit = totals[model], hits[model]
        low, high = wilson(hit, total)
        published = (baselines.get(model) or {}).get("sr")
        if published is None:
            verdict = "нет опубликованного числа"
        elif high - low > 0.40:
            # Width first, containment second: an interval that wide accepts
            # almost any published number, so "совпадает" would be meaningless.
            verdict = "не проверяемо (интервал шире 40 п.п.)"
        elif low <= published <= high:
            verdict = "совпадает"
        else:
            verdict = "НЕ совпадает"
        shown = f"{published:.1%}" if published is not None else "—"
        print(f"{model:34s} {hit:3d}/{total:<3d} {hit / total:5.1%} "
              f"[{low:5.1%};{high:5.1%}]  {shown:>10s}  {verdict}")

    if args.by_task:
        print()
        for model in sorted(totals):
            per_task = collections.Counter()
            per_task_hit = collections.Counter()
            for r in rows:
                if r["model"] != model:
                    continue
                task = r["task_uid"].split("__")[1] if "__" in r["task_uid"] else r["task_uid"]
                per_task[task] += 1
                per_task_hit[task] += bool(r["success"])
            line = "  ".join(f"{t}: {per_task_hit[t]}/{per_task[t]}" for t in sorted(per_task))
            print(f"{model:34s} {line}")


if __name__ == "__main__":
    main()
