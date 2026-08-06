"""Which collected episodes are valid to aggregate, declared as data.

Replaces an earlier mechanism that inferred validity from FILE MTIMES: it
compared each episode's first saved frame against the mtime of the
model-server file that produced it, treating "frame older than server" as
"collected before the last bug fix". That was silently wrong in a way that
matters for a published result:

  * mtimes do not survive `git clone`, `tar -x`, `rsync` without `-t`, or a
    container rebuild. On a fresh clone every server file looks newer than
    every episode, so EVERYTHING is judged stale.
  * a cosmetic edit (a comment, a path default) bumped the mtime and
    invalidated good episodes, which had already forced a manual mtime reset
    to rescue 99 valid runs — i.e. the mechanism had to be defeated by hand
    to produce a correct report.
  * the verdict depended on which files happened to be present locally:
    episodes whose frames had not been downloaded were silently treated as
    "no evidence, assume fine", so the same JSONL yielded different metrics
    on different machines.

Observed consequence, on identical annotation data: the committed report was
built from 182 episodes (GreenVLA R0/R1/R2 + OpenVLA-OFT) while regenerating
it after a fresh clone produced 396 episodes (GreenVLA-R2 + SmolVLA + pi0 +
pi0.5) — the two models carrying the headline result silently dropped out.

The replacement is a plain JSON file (`data/rollout_provenance.json`) that
names the excluded episodes and WHY. It is version-controlled, reviewable in
a diff, identical on every machine, and — unlike a filesystem timestamp — it
is a scientific claim someone can argue with.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROVENANCE_PATH = PROJECT_ROOT / "data" / "rollout_provenance.json"


def environment_of(row: dict[str, Any]) -> str:
    """LIBERO vs SimplerEnv for one annotation row.

    `task_uid` carries the suite as its prefix (`simpler__widowx_...` vs
    `libero_spatial__...`), fixed by the D3/D4 manifests, so this needs no
    extra lookup. Kept as one function so the convention has a single home.
    """
    return "SimplerEnv" if str(row.get("task_uid", "")).startswith("simpler") else "LIBERO"


def load_exclusions(path: Optional[Path] = None) -> list[dict[str, Any]]:
    path = path or DEFAULT_PROVENANCE_PATH
    if not path.is_file():
        return []
    with open(path, encoding="utf-8") as handle:
        doc = json.load(handle)
    return list(doc.get("exclusions", []))


def _matches(row: dict[str, Any], rule: dict[str, Any]) -> bool:
    if "run_ids" in rule and row["run_id"] not in rule["run_ids"]:
        return False
    if "models" in rule and row["model"] not in rule["models"]:
        return False
    if "environment" in rule and environment_of(row) != rule["environment"]:
        return False
    if "variants" in rule and row.get("variant") not in rule["variants"]:
        return False
    # A rule with no selector at all would silently drop the whole dataset.
    return any(k in rule for k in ("run_ids", "models", "environment", "variants"))


def partition(
    annotations: list[dict[str, Any]], path: Optional[Path] = None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Split annotations into (valid, excluded, applied_rules).

    Each applied rule gets an `n_matched` count so the report can state the
    exclusion instead of quietly shrinking a denominator. A declared rule that
    matches nothing is reported with `n_matched: 0` rather than dropped — a
    stale rule is worth seeing.
    """
    rules = load_exclusions(path)
    for rule in rules:
        rule["n_matched"] = 0

    valid: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for row in annotations:
        hit = next((r for r in rules if _matches(row, r)), None)
        if hit is None:
            valid.append(row)
        else:
            hit["n_matched"] += 1
            excluded.append({**row, "_excluded_by": hit.get("id", "unnamed rule")})
    return valid, excluded, rules
